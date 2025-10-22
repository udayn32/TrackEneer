"""
Study Module Backend - FastAPI endpoints for managing study materials, notes, and resources
"""
import os
import uuid
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from datetime import datetime
import json
from pathlib import Path
from typing import List, Optional
import shutil

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

SUBJECTS_FILE = Path("subjects.json")
NOTES_FILE = Path("notes.json")

# --- Data Models ---
def load_subjects():
    """Load subjects from JSON file"""
    if SUBJECTS_FILE.exists():
        with open(SUBJECTS_FILE, "r") as f:
            return json.load(f)
    return []

def save_subjects(subjects):
    """Save subjects to JSON file"""
    with open(SUBJECTS_FILE, "w") as f:
        json.dump(subjects, f, indent=2)

def load_notes():
    """Load notes from JSON file"""
    if NOTES_FILE.exists():
        with open(NOTES_FILE, "r") as f:
            return json.load(f)
    return []

def save_notes(notes):
    """Save notes to JSON file"""
    with open(NOTES_FILE, "w") as f:
        json.dump(notes, f, indent=2)

# --- API Endpoints ---

@app.get("/")
def root():
    """Health check endpoint"""
    return {"status": "Study module is running", "timestamp": datetime.now().isoformat()}

# ===== SUBJECTS =====

@app.get("/api/subjects")
def get_subjects():
    """Get all subjects"""
    subjects = load_subjects()
    return {"subjects": subjects}

@app.post("/api/subjects")
def create_subject(name: str = Form(...), description: str = Form(None)):
    """Create a new subject"""
    subjects = load_subjects()
    
    subject = {
        "id": str(uuid.uuid4()),
        "name": name,
        "description": description or "",
        "createdAt": datetime.now().isoformat(),
        "notesCount": 0
    }
    
    subjects.append(subject)
    save_subjects(subjects)
    
    return {"message": "Subject created successfully", "subject": subject}

@app.delete("/api/subjects/{subject_id}")
def delete_subject(subject_id: str):
    """Delete a subject"""
    subjects = load_subjects()
    notes = load_notes()
    
    # Remove subject
    subjects = [s for s in subjects if s["id"] != subject_id]
    save_subjects(subjects)
    
    # Remove associated notes
    notes = [n for n in notes if n["subjectId"] != subject_id]
    save_notes(notes)
    
    return {"message": "Subject deleted successfully"}

# ===== NOTES & FILES =====

@app.get("/api/notes")
def get_notes(subject_id: str = None):
    """Get all notes, optionally filtered by subject"""
    notes = load_notes()
    
    if subject_id:
        notes = [n for n in notes if n.get("subjectId") == subject_id]
    
    # Sort by upload date (newest first)
    notes.sort(key=lambda x: x.get("uploadedAt", ""), reverse=True)
    
    return {"notes": notes}

@app.post("/api/notes/upload")
async def upload_note(
    file: UploadFile = File(...),
    subject_id: str = Form(...),
    title: str = Form(None),
    description: str = Form(None)
):
    """Upload a study note/file"""
    try:
        # Generate unique filename
        file_ext = os.path.splitext(file.filename)[1]
        file_id = str(uuid.uuid4())
        unique_filename = f"{file_id}{file_ext}"
        file_path = UPLOAD_FOLDER / unique_filename
        
        # Save file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Create note record
        notes = load_notes()
        
        note = {
            "id": file_id,
            "subjectId": subject_id,
            "title": title or file.filename,
            "description": description or "",
            "filename": file.filename,
            "storedFilename": unique_filename,
            "fileType": file_ext.replace(".", "").upper(),
            "fileSize": os.path.getsize(file_path),
            "uploadedAt": datetime.now().isoformat()
        }
        
        notes.append(note)
        save_notes(notes)
        
        # Update subject notes count
        subjects = load_subjects()
        for subject in subjects:
            if subject["id"] == subject_id:
                subject["notesCount"] = subject.get("notesCount", 0) + 1
        save_subjects(subjects)
        
        return {"message": "File uploaded successfully", "note": note}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/api/notes/{note_id}/download")
async def download_note(note_id: str):
    """Download a note file"""
    notes = load_notes()
    note = next((n for n in notes if n["id"] == note_id), None)
    
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    file_path = UPLOAD_FOLDER / note["storedFilename"]
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=file_path,
        filename=note["filename"],
        media_type="application/octet-stream"
    )

@app.get("/api/notes/{note_id}/preview")
async def preview_note(note_id: str):
    """Preview a note file in browser"""
    notes = load_notes()
    note = next((n for n in notes if n["id"] == note_id), None)
    
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    file_path = UPLOAD_FOLDER / note["storedFilename"]
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Determine media type based on file extension
    file_ext = note.get("fileType", "").lower()
    media_type_map = {
        "pdf": "application/pdf",
        "txt": "text/plain",
        "md": "text/markdown",
        "json": "application/json",
        "html": "text/html",
        "css": "text/css",
        "js": "application/javascript",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "svg": "image/svg+xml",
    }
    
    media_type = media_type_map.get(file_ext, "application/octet-stream")
    
    return FileResponse(
        path=file_path,
        media_type=media_type,
        headers={"Content-Disposition": f"inline; filename={note['filename']}"}
    )

@app.delete("/api/notes/{note_id}")
def delete_note(note_id: str):
    """Delete a note"""
    notes = load_notes()
    note = next((n for n in notes if n["id"] == note_id), None)
    
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    # Delete file
    file_path = UPLOAD_FOLDER / note["storedFilename"]
    if file_path.exists():
        file_path.unlink()
    
    # Remove from notes
    notes = [n for n in notes if n["id"] != note_id]
    save_notes(notes)
    
    # Update subject notes count
    subjects = load_subjects()
    for subject in subjects:
        if subject["id"] == note["subjectId"]:
            subject["notesCount"] = max(0, subject.get("notesCount", 0) - 1)
    save_subjects(subjects)
    
    return {"message": "Note deleted successfully"}

@app.get("/api/notes/recent")
def get_recent_notes(limit: int = 5):
    """Get recently uploaded notes"""
    notes = load_notes()
    notes.sort(key=lambda x: x.get("uploadedAt", ""), reverse=True)
    return {"notes": notes[:limit]}

# ===== STATISTICS =====

@app.get("/api/study/stats")
def get_study_stats():
    """Get study statistics"""
    subjects = load_subjects()
    notes = load_notes()
    
    total_subjects = len(subjects)
    total_notes = len(notes)
    total_size = sum(note.get("fileSize", 0) for note in notes)
    
    # File types breakdown
    file_types = {}
    for note in notes:
        file_type = note.get("fileType", "OTHER")
        file_types[file_type] = file_types.get(file_type, 0) + 1
    
    return {
        "totalSubjects": total_subjects,
        "totalNotes": total_notes,
        "totalSize": total_size,
        "fileTypes": file_types
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5002)
