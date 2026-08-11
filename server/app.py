"""Unified FastAPI application consolidating TrackEneer services behind one server."""
from __future__ import annotations

import sys, io
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import os
from typing import Optional

# Load .env before any module imports so all os.getenv() calls see the values
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass  # dotenv not installed; rely on system environment variables

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from bm25_index import BM25Index
from db import close_driver, get_driver
from insights import app as insights_app
from placement import app as placement_app
from scheduler import app as scheduler_app
from study import app as study_app

# ─── Cognitive Learning Ecosystem Modules ───
try:
    from knowledge_graph import app as kg_app
    HAS_KG = True
except Exception as e:
    print(f"[WARN] Knowledge Graph module not loaded: {e}")
    HAS_KG = False

try:
    from mentor import app as mentor_app
    HAS_MENTOR = True
except Exception as e:
    print(f"[WARN] AI Mentor module not loaded: {e}")
    HAS_MENTOR = False

try:
    from knowledge_tracing import app as kt_app
    HAS_KT = True
except Exception as e:
    print(f"[WARN] Knowledge Tracing module not loaded: {e}")
    HAS_KT = False

try:
    from career_readiness import app as career_app
    HAS_CAREER = True
except Exception as e:
    print(f"[WARN] Career Readiness module not loaded: {e}")
    HAS_CAREER = False

# Import document processor for PDF extraction with Hybrid + Local NLP
from document_processor import DocumentProcessor, llm_whisperer, ai_extractor

# Initialize document processor
doc_processor = DocumentProcessor()

ALLOWED_ORIGINS = ["http://localhost:3000"]

# ── BM25 Search Index ────────────────────────────────────────────────
bm25_tasks = BM25Index()
bm25_notes = BM25Index()
bm25_subjects = BM25Index()

app = FastAPI(title="TrackEneer Unified API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _propagate_lifespan_events(source_app: FastAPI, target_app: FastAPI) -> None:
    """Copy startup/shutdown event handlers from one FastAPI app into another."""
    for handler in source_app.router.on_startup:
        target_app.add_event_handler("startup", handler)
    for handler in source_app.router.on_shutdown:
        target_app.add_event_handler("shutdown", handler)


def _remove_conflicting_root_routes(source_app: FastAPI) -> None:
    """Drop `GET /` routes to avoid duplicate health endpoints when combining apps."""
    filtered_routes = []
    for route in source_app.router.routes:
        if getattr(route, "path", None) == "/" and "GET" in getattr(route, "methods", set()):
            continue
        filtered_routes.append(route)
    source_app.router.routes[:] = filtered_routes


def _include_app(source_app: FastAPI, *, prefix: str | None = None) -> None:
    """Include routes ancyd lifespan handlers from a source FastAPI application."""
    _remove_conflicting_root_routes(source_app)
    if prefix:
        app.include_router(source_app.router, prefix=prefix)
    else:
        app.include_router(source_app.router)
    _propagate_lifespan_events(source_app, app)


_include_app(scheduler_app)
_include_app(study_app)
_include_app(insights_app)
_include_app(placement_app)

# ─── Cognitive Learning Ecosystem ───
# NOTE: /api/knowledge-graph/* routes are now inlined in study_app (study.py)
# so kg_app is intentionally skipped to avoid duplicate route registration.
# if HAS_KG: _include_app(kg_app)  ← disabled; routes live in study_app now
print("[OK] Knowledge Graph routes loaded via study module")
if HAS_MENTOR:
    _include_app(mentor_app)
    print("[OK] AI Mentor module loaded")
if HAS_KT:
    _include_app(kt_app)
    print("[OK] Knowledge Tracing module loaded")
if HAS_CAREER:
    _include_app(career_app)
    print("[OK] Career Readiness module loaded")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "modules": {
            "scheduler": True,
            "study": True,
            "insights": True,
            "career": HAS_CAREER,  # Primary career experience (formerly separated as placement + career_readiness)
            "placement": "legacy_compatibility_only",  # Legacy routes delegate to /api/career/*
            "knowledge_graph": HAS_KG,
            "ai_mentor": HAS_MENTOR,
            "knowledge_tracing": HAS_KT,
            "career_readiness": HAS_CAREER,  # Kept for backward compatibility in status reporting
        },
        "knowledge_graph_pipeline": {
            "preprocessing_stages": [
                "Stage 1: Fix hyphenation (word-\\nbreak → wordbreak)",
                "Stage 2a: Remove URLs",
                "Stage 2b: Remove emails",
                "Stage 3: Remove standalone page numbers",
                "Stage 4a: Collapse multiple spaces/tabs",
                "Stage 4b: Collapse excessive newlines (3+ → 2)",
                "Stage 5: Strip non-printable characters",
            ],
            "extraction_strategies": ["llm (MiniLM-L6 SIF+MMR)", "embedding (SentenceTransformer)", "nlp (SpaCy + heuristic)"],
            "logging": "Per-stage char reduction logged at INFO level via EduKGPipeline._preprocess_text()"
        } if HAS_KG else None
    }


@app.get("/api/document-processor/status")
async def document_processor_status() -> dict:
    """Check the status of document processing capabilities."""
    return {
        "status": "ok",
        "capabilities": {
            "hybrid_pipeline": {
                "digital_path": "Camelot (tables) + pdfplumber (text/layout)",
                "ocr_path": "pytesseract + pdf2image (scanned PDFs)",
                "nlp_extraction": "Local NLP (regex + NLTK) - fast, no API calls"
            },
            "llm_whisperer": {
                "enabled": llm_whisperer.enabled,
                "description": "Optional OCR fallback (disabled by default)"
            },
            "local_nlp": {
                "enabled": ai_extractor.enabled,
                "description": "Fast local text mining - no API rate limits"
            },
            "document_processor": {
                "ai_enabled": doc_processor.ai_enabled,
                "ocr_enabled": doc_processor.ocr_enabled
            }
        },
        "supported_documents": [
            "Syllabus PDF → subjects, topics, difficulty, hours",
            "Academic Calendar PDF → events, holidays",
            "Exam Timetable PDF → exam schedule"
        ]
    }


# ── BM25 Population ─────────────────────────────────────────────────
def _populate_bm25():
    """Load existing Neo4j data into the BM25 indexes on startup."""
    driver = get_driver()
    with driver.session() as session:
        # Index tasks
        records = session.run(
            "MATCH (t:Task) RETURN t.id AS id, t.title AS title, t.description AS desc"
        ).data()
        for r in records:
            text = f"{r.get('title') or ''} {r.get('desc') or ''}".strip()
            if text and r.get("id"):
                bm25_tasks.index(r["id"], text)

        # Index notes
        records = session.run(
            "MATCH (n:Note) RETURN n.id AS id, n.title AS title, n.description AS desc"
        ).data()
        for r in records:
            text = f"{r.get('title') or ''} {r.get('desc') or ''}".strip()
            if text and r.get("id"):
                bm25_notes.index(r["id"], text)

        # Index subjects
        records = session.run(
            "MATCH (s:Subject) RETURN s.id AS id, s.name AS name, s.description AS desc"
        ).data()
        for r in records:
            text = f"{r.get('name') or ''} {r.get('desc') or ''}".strip()
            if text and r.get("id"):
                bm25_subjects.index(r["id"], text)

    print(
        f"✓ BM25 indexes populated: "
        f"{bm25_tasks.doc_count} tasks, "
        f"{bm25_notes.doc_count} notes, "
        f"{bm25_subjects.doc_count} subjects"
    )


@app.on_event("startup")
async def startup_populate_bm25() -> None:
    try:
        _populate_bm25()
    except Exception as e:
        print(f"⚠ BM25 population skipped: {e}")


# ── Unified BM25 Search Endpoint ────────────────────────────────────
@app.get("/api/search")
async def bm25_search(
    request: Request,
    q: str,
    top_k: int = 10,
    category: Optional[str] = None,
):
    """
    Search across tasks, notes, and subjects using BM25 ranking.

    Query params:
      - q: search query (required)
      - top_k: max results per category (default 10)
      - category: 'tasks', 'notes', or 'subjects' to limit scope
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required.")

    results: dict[str, list] = {}

    if category in (None, "tasks"):
        results["tasks"] = [
            {"id": doc_id, "score": round(score, 4)}
            for doc_id, score in bm25_tasks.search(q, top_k=top_k)
        ]

    if category in (None, "notes"):
        results["notes"] = [
            {"id": doc_id, "score": round(score, 4)}
            for doc_id, score in bm25_notes.search(q, top_k=top_k)
        ]

    if category in (None, "subjects"):
        results["subjects"] = [
            {"id": doc_id, "score": round(score, 4)}
            for doc_id, score in bm25_subjects.search(q, top_k=top_k)
        ]

    total = sum(len(v) for v in results.values())
    return {"query": q, "total": total, "results": results}


@app.post("/api/search/reindex")
async def reindex_bm25():
    """Re-populate BM25 indexes from Neo4j (e.g. after bulk data changes)."""
    global bm25_tasks, bm25_notes, bm25_subjects
    bm25_tasks = BM25Index()
    bm25_notes = BM25Index()
    bm25_subjects = BM25Index()
    try:
        _populate_bm25()
        return {
            "status": "ok",
            "tasks": bm25_tasks.doc_count,
            "notes": bm25_notes.doc_count,
            "subjects": bm25_subjects.doc_count,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reindex failed: {e}")


@app.on_event("shutdown")
async def shutdown_driver() -> None:
    close_driver()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 5000)), reload=False)
