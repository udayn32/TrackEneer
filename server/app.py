"""Unified FastAPI application consolidating TrackEneer services behind one server."""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import close_driver
from insights import app as insights_app
from placement import app as placement_app
from scheduler import app as scheduler_app
from study import app as study_app

# ─── Cognitive Learning Ecosystem Modules ───
try:
    from knowledge_graph import app as kg_app
    HAS_KG = True
except Exception as e:
    print(f"⚠ Knowledge Graph module not loaded: {e}")
    HAS_KG = False

try:
    from mentor import app as mentor_app
    HAS_MENTOR = True
except Exception as e:
    print(f"⚠ AI Mentor module not loaded: {e}")
    HAS_MENTOR = False

try:
    from knowledge_tracing import app as kt_app
    HAS_KT = True
except Exception as e:
    print(f"⚠ Knowledge Tracing module not loaded: {e}")
    HAS_KT = False

try:
    from career_readiness import app as career_app
    HAS_CAREER = True
except Exception as e:
    print(f"⚠ Career Readiness module not loaded: {e}")
    HAS_CAREER = False

# Import document processor for PDF extraction with Hybrid + Local NLP
from document_processor import DocumentProcessor, llm_whisperer, ai_extractor

# Initialize document processor
doc_processor = DocumentProcessor()

ALLOWED_ORIGINS = ["http://localhost:3000"]

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
if HAS_KG:
    _include_app(kg_app)
    print("✓ Knowledge Graph module loaded")
if HAS_MENTOR:
    _include_app(mentor_app)
    print("✓ AI Mentor module loaded")
if HAS_KT:
    _include_app(kt_app)
    print("✓ Knowledge Tracing module loaded")
if HAS_CAREER:
    _include_app(career_app)
    print("✓ Career Readiness module loaded")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "modules": {
            "scheduler": True,
            "study": True,
            "insights": True,
            "placement": True,
            "knowledge_graph": HAS_KG,
            "ai_mentor": HAS_MENTOR,
            "knowledge_tracing": HAS_KT,
            "career_readiness": HAS_CAREER,
        }
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


@app.on_event("shutdown")
async def shutdown_driver() -> None:
    close_driver()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", 5000)), reload=False)
