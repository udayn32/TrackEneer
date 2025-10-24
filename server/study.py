"""Study module backed by Neo4j for subjects and notes management."""

import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from db import get_driver

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

driver = get_driver()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_subject(node, notes_count: int) -> dict:
    return {
        "id": node["id"],
        "name": node.get("name", ""),
        "description": node.get("description", ""),
        "createdAt": node.get("createdAt"),
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
    }


def _get_note_node(note_id: str):
    with driver.session() as session:
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
def get_subjects():
    with driver.session() as session:
        results = session.run(
            """
            MATCH (s:Subject)
            OPTIONAL MATCH (s)-[:HAS_NOTE]->(n:Note)
            RETURN s AS subject, count(n) AS notesCount
            ORDER BY subject.createdAt DESC
            """
        )
        subjects = [
            _serialize_subject(record["subject"], record["notesCount"])
            for record in results
        ]
    return {"subjects": subjects}


@app.post("/api/subjects")
def create_subject(name: str = Form(...), description: Optional[str] = Form(None)):
    subject_id = str(uuid.uuid4())
    created_at = _now_iso()
    with driver.session() as session:
        session.run(
            """
            CREATE (s:Subject {
                id: $id,
                name: $name,
                description: $description,
                createdAt: $created_at
            })
            """,
            id=subject_id,
            name=name,
            description=description or "",
            created_at=created_at,
        )

    subject = {
        "id": subject_id,
        "name": name,
        "description": description or "",
        "createdAt": created_at,
        "notesCount": 0,
    }
    return {"message": "Subject created successfully", "subject": subject}


@app.delete("/api/subjects/{subject_id}")
def delete_subject(subject_id: str):
    stored_files = []
    with driver.session() as session:
        records = session.run(
            """
            MATCH (s:Subject {id: $id})-[:HAS_NOTE]->(n:Note)
            RETURN n.storedFilename AS storedFilename
            """,
            id=subject_id,
        )
        stored_files = [record["storedFilename"] for record in records if record["storedFilename"]]

        result = session.run(
            "MATCH (s:Subject {id: $id}) RETURN s",
            id=subject_id,
        ).single()
        if not result:
            raise HTTPException(status_code=404, detail="Subject not found")

        session.run(
            "MATCH (s:Subject {id: $id}) DETACH DELETE s",
            id=subject_id,
        )

    for filename in stored_files:
        file_path = UPLOAD_FOLDER / filename
        if file_path.exists():
            file_path.unlink()

    return {"message": "Subject deleted successfully"}


@app.get("/api/notes")
def get_notes(subject_id: Optional[str] = None):
    with driver.session() as session:
        results = session.run(
            """
            MATCH (n:Note)
            WHERE $subject_id IS NULL OR n.subjectId = $subject_id
            RETURN n
            ORDER BY n.uploadedAt DESC
            """,
            subject_id=subject_id,
        )
        notes = [_serialize_note(record["n"]) for record in results]
    return {"notes": notes}


@app.post("/api/notes/upload")
async def upload_note(
    file: UploadFile = File(...),
    subject_id: str = Form(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
):
    with driver.session() as session:
        subject_exists = session.run(
            "MATCH (s:Subject {id: $id}) RETURN s",
            id=subject_id,
        ).single()
        if not subject_exists:
            raise HTTPException(status_code=404, detail="Subject not found")

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
            MATCH (s:Subject {id: $subject_id})
            CREATE (s)-[:HAS_NOTE]->(n:Note {
                id: $id,
                subjectId: $subject_id,
                title: $title,
                description: $description,
                filename: $filename,
                storedFilename: $stored_filename,
                fileType: $file_type,
                fileSize: $file_size,
                uploadedAt: $uploaded_at
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
        )

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
    }
    return {"message": "File uploaded successfully", "note": note}


@app.get("/api/notes/{note_id}/download")
async def download_note(note_id: str):
    note = _get_note_node(note_id)
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
async def preview_note(note_id: str):
    note = _get_note_node(note_id)
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
def delete_note(note_id: str):
    note = _get_note_node(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    with driver.session() as session:
        session.run("MATCH (n:Note {id: $id}) DETACH DELETE n", id=note_id)

    file_path = UPLOAD_FOLDER / note["storedFilename"]
    if file_path.exists():
        file_path.unlink()

    return {"message": "Note deleted successfully"}


@app.get("/api/notes/recent")
def get_recent_notes(limit: int = 5):
    with driver.session() as session:
        results = session.run(
            """
            MATCH (n:Note)
            RETURN n
            ORDER BY n.uploadedAt DESC
            LIMIT $limit
            """,
            limit=limit,
        )
        notes = [_serialize_note(record["n"]) for record in results]
    return {"notes": notes}


@app.get("/api/study/stats")
def get_study_stats():
    with driver.session() as session:
        subjects_count = session.run("MATCH (s:Subject) RETURN count(s) AS count").single()["count"]
        note_records = list(
            session.run(
                """
                MATCH (n:Note)
                RETURN coalesce(n.fileType, 'OTHER') AS type, n.fileSize AS fileSize
                """
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5002)
