"""Study module backed by Neo4j for subjects and notes management."""

import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from db import get_driver
from graph_helpers import ensure_user_and_day, normalize_day
from nsga2_scheduler import generate_study_schedule, clean_paper_name

try:
    import google.generativeai as genai
except Exception:
    genai = None

# --- FastAPI App Initialization ---
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Configuration ---
UPLOAD_FOLDER = Path("uploads")
UPLOAD_FOLDER.mkdir(exist_ok=True)

DEFAULT_USER_EMAIL = os.getenv("DEFAULT_USER_EMAIL", "demo@trackeneer.local")

# Gemini (Google) configuration for study module
# NOTE: Storing API keys in source is unsafe. Prefer setting GOOGLE_API_KEY/GEMINI_API_KEY in the environment.
GEMINI_API_KEY = "AIzaSyDL1SqUudycymjYNnlm4z7ajfFkL3ht77k"
if genai:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')
    except Exception as e:
        print("Warning: failed to configure Gemini in study.py:", e)
        model = None
else:
    model = None

driver = get_driver()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_user_email(request: Request, provided: Optional[str] = None) -> str:
    email = provided or request.headers.get("x-user-email") or request.headers.get("X-User-Email")
    if not email:
        email = DEFAULT_USER_EMAIL
    if not email:
        raise HTTPException(status_code=400, detail="User email is required")
    return email.strip().lower()


def _serialize_subject(node, notes_count: int) -> dict:
    return {
        "id": node["id"],
        "name": node.get("name", ""),
        "description": node.get("description", ""),
        "createdAt": node.get("createdAt"),
        "dayDate": node.get("dayDate"),
        "notesCount": int(notes_count or 0),
    }


def _serialize_note(node) -> dict:
    return {
        "id": node["id"],
        "subjectId": node.get("subjectId"),
        "title": node.get("title"),
        "description": node.get("description", ""),
        "filename": node.get("filename"),
        "storedFilename": node.get("storedFilename"),
        "fileType": node.get("fileType"),
        "fileSize": int(node.get("fileSize", 0) or 0),
        "uploadedAt": node.get("uploadedAt"),
        "dayDate": node.get("dayDate"),
        "ownerEmail": node.get("ownerEmail"),
    }


def _get_note_node(note_id: str, email: Optional[str] = None):
    with driver.session() as session:
        if email:
            record = session.run(
                """
                MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_SUBJECT]->(:Subject)-[:HAS_NOTE]->(n:Note {id: $note_id})
                RETURN n
                """,
                note_id=note_id,
                email=email,
            ).single()
        else:
            record = session.run(
                """
                MATCH (n:Note {id: $note_id})
                RETURN n
                """,
                note_id=note_id,
            ).single()
        return record["n"] if record else None


@app.get("/")
def root():
    return {"status": "Study module is running", "timestamp": _now_iso()}

@app.get("/api/subjects")
def get_subjects(request: Request, day: Optional[str] = None, email: Optional[str] = None):
    user_email = _resolve_user_email(request, email)
    day_iso = normalize_day(day)
    with driver.session() as session:
        day_iso = ensure_user_and_day(session, user_email, day=day_iso)
        results = session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(d:Day {date: date($day), email: $email})-[:HAS_SUBJECT]->(s:Subject)
            OPTIONAL MATCH (s)-[:HAS_NOTE]->(n:Note)
            RETURN s AS subject, count(n) AS notesCount
            ORDER BY subject.createdAt DESC
            """,
            email=user_email,
            day=day_iso,
        )
        subjects = [
            _serialize_subject(record["subject"], record["notesCount"])
            for record in results
        ]
    return {"subjects": subjects}


@app.post("/api/subjects")
async def create_subject(
    request: Request,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    day: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
):
    user_email = _resolve_user_email(request, email)
    subject_id = str(uuid.uuid4())
    created_at = _now_iso()
    day_iso = normalize_day(day)
    with driver.session() as session:
        day_iso = ensure_user_and_day(session, user_email, day=day_iso)
        session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(d:Day {date: date($day), email: $email})
            CREATE (d)-[:HAS_SUBJECT]->(s:Subject {
                id: $id,
                name: $name,
                description: $description,
                createdAt: $created_at,
                ownerEmail: $email,
                dayDate: $day
            })
            """,
            id=subject_id,
            name=name,
            description=description or "",
            created_at=created_at,
            email=user_email,
            day=day_iso,
        )

    subject = {
        "id": subject_id,
        "name": name,
        "description": description or "",
        "createdAt": created_at,
        "dayDate": day_iso,
        "notesCount": 0,
    }
    return {"message": "Subject created successfully", "subject": subject}


@app.delete("/api/subjects/{subject_id}")
def delete_subject(subject_id: str, request: Request, email: Optional[str] = None):
    user_email = _resolve_user_email(request, email)
    stored_files = []
    with driver.session() as session:
        records = session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_SUBJECT]->(s:Subject {id: $id})
            OPTIONAL MATCH (s)-[:HAS_NOTE]->(n:Note)
            RETURN n.storedFilename AS storedFilename
            """,
            id=subject_id,
            email=user_email,
        )
        stored_files = [record["storedFilename"] for record in records if record["storedFilename"]]

        result = session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_SUBJECT]->(s:Subject {id: $id})
            RETURN s
            """,
            id=subject_id,
            email=user_email,
        ).single()
        if not result:
            raise HTTPException(status_code=404, detail="Subject not found")

        session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_SUBJECT]->(s:Subject {id: $id})
            DETACH DELETE s
            """,
            id=subject_id,
            email=user_email,
        )

    for filename in stored_files:
        file_path = UPLOAD_FOLDER / filename
        if file_path.exists():
            file_path.unlink()

    return {"message": "Subject deleted successfully"}

@app.get("/api/notes")
def get_notes(
    request: Request,
    subject_id: Optional[str] = None,
    day: Optional[str] = None,
    email: Optional[str] = None,
):
    user_email = _resolve_user_email(request, email)
    with driver.session() as session:
        if subject_id:
            results = session.run(
                """
                MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_SUBJECT]->(s:Subject {id: $subject_id})-[:HAS_NOTE]->(n:Note)
                RETURN n
                ORDER BY n.uploadedAt DESC
                """,
                email=user_email,
                subject_id=subject_id,
            )
        else:
            day_iso = ensure_user_and_day(session, user_email, day=normalize_day(day))
            results = session.run(
                """
                MATCH (u:User {email: $email})-[:HAS_DAY]->(d:Day {date: date($day), email: $email})-[:HAS_SUBJECT]->(:Subject)-[:HAS_NOTE]->(n:Note)
                RETURN n
                ORDER BY n.uploadedAt DESC
                """,
                email=user_email,
                day=day_iso,
            )
        notes = [_serialize_note(record["n"]) for record in results]
    return {"notes": notes}


@app.post("/api/notes/upload")
async def upload_note(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    subject_id: str = Form(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
):
    user_email = _resolve_user_email(request, email)
    with driver.session() as session:
        subject_exists = session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(d:Day)-[:HAS_SUBJECT]->(s:Subject {id: $id})
            RETURN s, d
            """,
            id=subject_id,
            email=user_email,
        ).single()
        if not subject_exists:
            raise HTTPException(status_code=404, detail="Subject not found")

        day_node = subject_exists["d"]
        day_iso = normalize_day(None)
        if day_node:
            try:
                day_value = day_node["date"]
                if hasattr(day_value, "to_native"):
                    day_iso = day_value.to_native().isoformat()
                elif hasattr(day_value, "isoformat"):
                    day_iso = day_value.isoformat()
                else:
                    day_iso = normalize_day(str(day_value))
            except (KeyError, TypeError):
                pass
        ensure_user_and_day(session, user_email, day=day_iso)

    file_ext = os.path.splitext(file.filename)[1]
    note_id = str(uuid.uuid4())
    stored_filename = f"{note_id}{file_ext}"
    file_path = UPLOAD_FOLDER / stored_filename

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        file.file.close()

    file_size = file_path.stat().st_size if file_path.exists() else 0
    uploaded_at = _now_iso()

    with driver.session() as session:
        session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_SUBJECT]->(s:Subject {id: $subject_id})
            CREATE (s)-[:HAS_NOTE]->(n:Note {
                id: $id,
                subjectId: $subject_id,
                title: $title,
                description: $description,
                filename: $filename,
                storedFilename: $stored_filename,
                fileType: $file_type,
                fileSize: $file_size,
                uploadedAt: $uploaded_at,
                ownerEmail: $email,
                dayDate: $day
            })
            """,
            subject_id=subject_id,
            id=note_id,
            title=title or file.filename,
            description=description or "",
            filename=file.filename,
            stored_filename=stored_filename,
            file_type=file_ext.replace(".", "").upper(),
            file_size=file_size,
            uploaded_at=uploaded_at,
            email=user_email,
            day=day_iso,
        )

    # schedule background processing to convert the uploaded file into the knowledge graph
    try:
        background_tasks.add_task(process_file_background, file_path, user_email)
    except Exception as e:
        print(f"Warning: failed to schedule background processing for {file_path}: {e}")

    note = {
        "id": note_id,
        "subjectId": subject_id,
        "title": title or file.filename,
        "description": description or "",
        "filename": file.filename,
        "storedFilename": stored_filename,
        "fileType": file_ext.replace(".", "").upper(),
        "fileSize": file_size,
        "uploadedAt": uploaded_at,
        "dayDate": day_iso,
        "ownerEmail": user_email,
    }
    return {"message": "File uploaded successfully", "note": note}


@app.get("/api/notes/{note_id}/download")
async def download_note(note_id: str, request: Request, email: Optional[str] = None):
    user_email = _resolve_user_email(request, email)
    note = _get_note_node(note_id, user_email)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    file_path = UPLOAD_FOLDER / note["storedFilename"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=file_path,
        filename=note["filename"],
        media_type="application/octet-stream",
    )


@app.get("/api/notes/{note_id}/preview")
async def preview_note(note_id: str, request: Request, email: Optional[str] = None):
    user_email = _resolve_user_email(request, email)
    note = _get_note_node(note_id, user_email)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    file_path = UPLOAD_FOLDER / note["storedFilename"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    media_type_map = {
        "PDF": "application/pdf",
        "TXT": "text/plain",
        "MD": "text/markdown",
        "JSON": "application/json",
        "HTML": "text/html",
        "CSS": "text/css",
        "JS": "application/javascript",
        "PNG": "image/png",
        "JPG": "image/jpeg",
        "JPEG": "image/jpeg",
        "GIF": "image/gif",
        "SVG": "image/svg+xml",
    }

    media_type = media_type_map.get(note.get("fileType", "").upper(), "application/octet-stream")

    return FileResponse(
        path=file_path,
        media_type=media_type,
        headers={"Content-Disposition": f"inline; filename={note['filename']}"},
    )


@app.delete("/api/notes/{note_id}")
def delete_note(note_id: str, request: Request, email: Optional[str] = None):
    user_email = _resolve_user_email(request, email)
    note = _get_note_node(note_id, user_email)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    with driver.session() as session:
        session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_SUBJECT]->(:Subject)-[:HAS_NOTE]->(n:Note {id: $id})
            DETACH DELETE n
            """,
            id=note_id,
            email=user_email,
        )

    file_path = UPLOAD_FOLDER / note["storedFilename"]
    if file_path.exists():
        file_path.unlink()

    return {"message": "Note deleted successfully"}

@app.get("/api/notes/recent")
def get_recent_notes(request: Request, limit: int = 5, email: Optional[str] = None):
    user_email = _resolve_user_email(request, email)
    with driver.session() as session:
        results = session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_SUBJECT]->(:Subject)-[:HAS_NOTE]->(n:Note)
            RETURN n
            ORDER BY n.uploadedAt DESC
            LIMIT $limit
            """,
            limit=limit,
            email=user_email,
        )
        notes = [_serialize_note(record["n"]) for record in results]
    return {"notes": notes}


@app.get("/api/study/stats")
def get_study_stats(request: Request, email: Optional[str] = None):
    user_email = _resolve_user_email(request, email)
    with driver.session() as session:
        subjects_count = (
            session.run(
                """
                MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_SUBJECT]->(s:Subject)
                RETURN count(s) AS count
                """,
                email=user_email,
            ).single()["count"]
        )
        note_records = list(
            session.run(
                """
                MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_SUBJECT]->(:Subject)-[:HAS_NOTE]->(n:Note)
                RETURN coalesce(n.fileType, 'OTHER') AS type, n.fileSize AS fileSize
                """,
                email=user_email,
            )
        )

    total_notes = len(note_records)
    total_size = 0
    file_type_counts: dict[str, int] = {}

    for record in note_records:
        note_type = record["type"] or "OTHER"
        file_type_counts[note_type] = file_type_counts.get(note_type, 0) + 1

        value = record["fileSize"]
        if isinstance(value, (int, float)):
            total_size += int(value)
        elif isinstance(value, str):
            digits = "".join(ch for ch in value if ch.isdigit())
            if digits:
                try:
                    total_size += int(digits)
                except ValueError:
                    continue

    return {
        "totalSubjects": int(subjects_count or 0),
        "totalNotes": total_notes,
        "totalSize": total_size,
        "fileTypes": {k: int(v) for k, v in file_type_counts.items()},
    }


# ---------------------------
# Notes extraction & graph
# ---------------------------
def extract_text_from_file(path: Path) -> str:
    """Try to extract text from common file types (PDF, DOCX, plain text).
    Falls back to reading bytes as latin-1 if parsing libraries aren't available.
    """
    text = ""
    try:
        if path.suffix.lower() == ".pdf":
            try:
                from PyPDF2 import PdfReader

                reader = PdfReader(str(path))
                for p in reader.pages:
                    page_text = p.extract_text()
                    if page_text:
                        text += page_text + "\n\n"
            except Exception:
                # Best-effort fallback
                with open(path, "rb") as f:
                    data = f.read()
                    try:
                        text = data.decode("utf-8")
                    except Exception:
                        text = data.decode("latin-1", errors="ignore")
        elif path.suffix.lower() in (".docx", ".doc"):
            try:
                import docx

                doc = docx.Document(str(path))
                for para in doc.paragraphs:
                    text += para.text + "\n"
            except Exception:
                with open(path, "rb") as f:
                    data = f.read()
                    try:
                        text = data.decode("utf-8")
                    except Exception:
                        text = data.decode("latin-1", errors="ignore")
        else:
            # plain text or unknown; try to read as text
            with open(path, "rb") as f:
                data = f.read()
                try:
                    text = data.decode("utf-8")
                except Exception:
                    text = data.decode("latin-1", errors="ignore")
    except Exception:
        # Last resort: return empty string
        text = ""
    return text


def call_gemini_extract(text: str) -> dict:
    """Call Gemini/Google Generative API to extract structured JSON from the notes text.
    If the google.generativeai package is not available or API key is not set, returns a
    very small heuristic extraction (topics/subtopics) as a fallback.
    """
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        # simple heuristic: split by double-newline into sections
        topics = []
        parts = [p.strip() for p in text.split("\n\n") if p.strip()]
        for i, p in enumerate(parts[:20]):
            lines = [l.strip() for l in p.splitlines() if l.strip()]
            title = lines[0][:120] if lines else f"Topic {i+1}"
            body = "\n".join(lines[1:]) if len(lines) > 1 else ""
            topics.append({"title": title, "content": body, "subtopics": []})
        return {"topics": topics}

    try:
        try:
            import google.generativeai as genai
        except Exception:
            return {"topics": []}

        genai.configure(api_key=api_key)
        # Use a simple prompt asking Gemini to extract topics/subtopics/depends_on
        prompt = (
            "Extract a JSON object with keys: topics (array). Each topic should have title, "
            "subtopics (array of strings) and depends_on (array of topic titles). "
            "Return ONLY valid JSON.\n\nText:\n" + text[:60000]
        )

        response = genai.predict(model="gemini", prompt=prompt)
        # The response may contain text; try to parse JSON from it
        import re, json

        m = re.search(r"\{.*\}", response.text or "", re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return {"topics_text": response.text}
        return {"topics_text": response.text}
    except Exception:
        return {"topics": []}


def process_and_store_notes(extracted: dict, user_email: str):
    """Given the extracted JSON, store topics/subtopics and dependencies into Neo4j.
    This function is idempotent for repeated uploads of the same content.
    """
    topics = extracted.get("topics") or []
    if not topics:
        return

    with driver.session() as session:
        for t in topics:
            title = t.get("title") or t.get("name") or "Untitled"
            content = t.get("content") or ""
            # Create or merge topic node
            session.run(
                """
                MERGE (top:Topic {title: $title, ownerEmail: $email})
                SET top.content = coalesce(top.content, $content), top.updatedAt = datetime()
                """,
                title=title,
                content=content,
                email=user_email,
            )

            # handle subtopics
            for s in t.get("subtopics", []):
                session.run(
                    """
                    MATCH (top:Topic {title: $title, ownerEmail: $email})
                    MERGE (sub:Subtopic {title: $sub, ownerEmail: $email})
                    MERGE (top)-[:HAS_SUBTOPIC]->(sub)
                    """,
                    title=title,
                    sub=s,
                    email=user_email,
                )

            # handle dependencies
            for dep in t.get("depends_on", []):
                session.run(
                    """
                    MATCH (a:Topic {title: $title, ownerEmail: $email})
                    MATCH (b:Topic {title: $dep, ownerEmail: $email})
                    MERGE (a)-[:DEPENDS_ON]->(b)
                    """,
                    title=title,
                    dep=dep,
                    email=user_email,
                )


def process_file_background(path: Path, user_email: str):
    """Background worker: extract text from a file, call Gemini/heuristic, store topics into Neo4j.
    This is a module-level helper so multiple endpoints can reuse the same logic.
    """
    try:
        txt = extract_text_from_file(path)
        extracted = call_gemini_extract(txt)
        process_and_store_notes(extracted, user_email)
    except Exception as e:
        # Log exception info so we can debug background failures
        import traceback
        print(f"Exception in background extraction for {path}: {e}")
        traceback.print_exc()


@app.post("/api/notes/extract")
def notes_extract_endpoint(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    request: Request = None,
    email: Optional[str] = None,
):
    """Accept an uploaded file, store it, and enqueue background extraction + storage to Neo4j.
    Returns a job-like response (immediate)."""
    user_email = _resolve_user_email(request, email)
    uid = str(uuid.uuid4())
    stored_name = f"{uid}_{file.filename}"
    dest = UPLOAD_FOLDER / stored_name
    with open(dest, "wb") as f:
        f.write(file.file.read())

    # schedule background processing using shared helper
    try:
        background_tasks.add_task(process_file_background, dest, user_email)
    except Exception as e:
        print(f"Warning: failed to schedule background processing for {dest}: {e}")

    return {"message": "File received; extraction queued", "storedFilename": stored_name}


@app.get("/api/notes/graph")
def get_notes_graph(request: Request, email: Optional[str] = None):
    """Return a simple graph (nodes and edges) representing Topics and Subtopics for the user."""
    user_email = _resolve_user_email(request, email)
    nodes = []
    edges = []
    with driver.session() as session:
        res = session.run(
            """
            MATCH (t:Topic {ownerEmail: $email})
            OPTIONAL MATCH (t)-[:HAS_SUBTOPIC]->(s:Subtopic)
            OPTIONAL MATCH (t)-[:DEPENDS_ON]->(d:Topic)
            RETURN t, collect(DISTINCT s) AS subs, collect(DISTINCT d) AS deps
            """,
            email=user_email,
        )
        for record in res:
            t = record["t"]
            t_id = f"topic:{t['title']}"
            nodes.append({"data": {"id": t_id, "label": t["title"]}})
            for s in record["subs"]:
                if not s:
                    continue
                s_id = f"sub:{s['title']}"
                nodes.append({"data": {"id": s_id, "label": s["title"]}})
                edges.append({"data": {"source": t_id, "target": s_id, "label": "has_subtopic"}})
            for d in record["deps"]:
                if not d:
                    continue
                d_id = f"topic:{d['title']}"
                nodes.append({"data": {"id": d_id, "label": d["title"]}})
                edges.append({"data": {"source": t_id, "target": d_id, "label": "depends_on"}})

    # de-duplicate nodes
    seen = set()
    uniq_nodes = []
    for n in nodes:
        nid = n["data"]["id"]
        if nid in seen:
            continue
        seen.add(nid)
        uniq_nodes.append(n)

    return {"nodes": uniq_nodes, "edges": edges}


@app.post("/api/notes/seed")
def seed_notes_graph(request: Request, email: Optional[str] = None):
    """Create sample Topic/Subtopic nodes for the current user to verify the frontend graph UI."""
    user_email = _resolve_user_email(request, email)
    sample = [
        {"title": "Introduction to IoT", "subtopics": ["Sensors", "Actuators", "Protocols"], "depends_on": []},
        {"title": "Sensors", "subtopics": ["Temperature", "Humidity"], "depends_on": ["Introduction to IoT"]},
        {"title": "Communication Protocols", "subtopics": ["MQTT", "HTTP"], "depends_on": ["Introduction to IoT"]},
    ]

    with driver.session() as session:
        for t in sample:
            title = t["title"]
            session.run(
                """
                MERGE (top:Topic {title: $title, ownerEmail: $email})
                SET top.createdAt = coalesce(top.createdAt, datetime())
                """,
                title=title,
                email=user_email,
            )
            for s in t.get("subtopics", []):
                session.run(
                    """
                    MATCH (top:Topic {title: $title, ownerEmail: $email})
                    MERGE (sub:Subtopic {title: $sub, ownerEmail: $email})
                    MERGE (top)-[:HAS_SUBTOPIC]->(sub)
                    """,
                    title=title,
                    sub=s,
                    email=user_email,
                )
            for dep in t.get("depends_on", []):
                session.run(
                    """
                    MATCH (a:Topic {title: $title, ownerEmail: $email})
                    MERGE (b:Topic {title: $dep, ownerEmail: $email})
                    MERGE (a)-[:DEPENDS_ON]->(b)
                    """,
                    title=title,
                    dep=dep,
                    email=user_email,
                )

    return {"message": "Seeded sample topics", "sampleCount": len(sample)}


@app.post("/api/notes/process_stored")
def process_stored_file(request: Request, storedFilename: str = None, email: Optional[str] = None):
    """Debug endpoint: process a previously uploaded file (from uploads/) synchronously.
    Returns the extracted JSON and any errors. Use this to troubleshoot why a file didn't produce graph nodes.
    """
    user_email = _resolve_user_email(request, email)
    if not storedFilename:
        raise HTTPException(status_code=400, detail="storedFilename is required")

    file_path = UPLOAD_FOLDER / storedFilename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Stored file not found: {file_path}")

    try:
        txt = extract_text_from_file(file_path)
        extracted = call_gemini_extract(txt)
        # return the extracted result to the caller for inspection
        # and also attempt to store into Neo4j
        process_and_store_notes(extracted, user_email)
        return {"status": "processed", "extracted": extracted}
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"Error processing stored file {file_path}: {e}\n{tb}")
        raise HTTPException(status_code=500, detail={"error": str(e), "traceback": tb})


# ============== NSGA-II STUDY SCHEDULE ENDPOINTS ==============

class ExamInput(BaseModel):
    """Single exam input model"""
    paper: str = ""
    subject: str = ""
    date: str = ""
    start_time: str = ""
    end_time: str = ""


class ScheduleRequest(BaseModel):
    """Request model for schedule generation"""
    exams: List[Dict]


@app.post("/api/study/generate-schedule")
def api_generate_schedule(request_data: ScheduleRequest):
    """
    Generate an optimized study schedule using NSGA-II algorithm.
    
    The algorithm optimizes for three objectives:
    1. Even distribution of study sessions (minimize cramming)
    2. Reduced context switching between subjects
    3. Priority for subjects with upcoming exams
    
    Request body:
    {
        "exams": [
            {"paper": "Machine Learning", "subject": "ML", "date": "2025-11-10"},
            ...
        ]
    }
    
    Returns:
    {
        "schedule": [...],
        "num_days": 60,
        "num_subjects": 10,
        "start_date": "2025-01-25T...",
        "objectives": {"cramming": ..., "switching": ..., "revision": ...}
    }
    """
    try:
        exams = request_data.exams
        
        if not exams:
            raise HTTPException(status_code=400, detail="No exams provided")
        
        # Generate schedule using NSGA-II
        result = generate_study_schedule(exams)
        
        return result
    
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"Error generating schedule: {e}\n{tb}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/study/clean-paper-names")
def api_clean_paper_names(request_data: ScheduleRequest):
    """
    Clean paper names from exam data, removing OCR artifacts and course codes.
    
    Request body:
    {
        "exams": [
            {"paper": "Machine Learning & Blockchain - P IoTCSBCC701", "subject": "Machine"},
            ...
        ]
    }
    
    Returns cleaned exam data with paper_name field.
    """
    try:
        cleaned_exams = []
        
        for exam in request_data.exams:
            paper = exam.get('paper', '')
            subject = exam.get('subject', '')
            
            cleaned_name = clean_paper_name(paper, subject)
            
            cleaned_exam = dict(exam)
            cleaned_exam['paper_name'] = cleaned_name
            cleaned_exams.append(cleaned_exam)
        
        return {"exams": cleaned_exams}
    
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"Error cleaning paper names: {e}\n{tb}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5002)
