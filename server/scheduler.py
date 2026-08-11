import os
import sys
import uuid
import chromadb
import requests  # Re-added
import aiohttp
import re
import shutil

# Force UTF-8 stdout/stderr so Unicode symbols don't crash on Windows cp1252
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# huggingface_hub >= 0.16 removed `cached_download`, but sentence-transformers
# still imports it. Provide a shim so newer versions remain compatible.
import huggingface_hub  # Re-added
import hashlib  # Re-added
from urllib.parse import urlparse  # Re-added

def _cached_download(url: str | None = None, cache_dir: str | None = None, force_download: bool = False, resume_download: bool = False, extract_compressed_file: bool = False, *args, **kwargs):
    """
    Compatibility shim for `cached_download` expected by older libs.
    This is the full shim, restored to handle both URL and repo_id downloads.
    """
    # If a direct URL is provided, download and cache it.
    if url:
        if cache_dir is None:
            cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")
        os.makedirs(cache_dir, exist_ok=True)

        parsed = urlparse(url)
        ext = os.path.splitext(parsed.path)[1] or ""
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        out_name = f"{key}{ext}"
        out_path = os.path.join(cache_dir, out_name)

        if not os.path.exists(out_path) or force_download:
            # stream download
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                tmp_path = out_path + ".tmp"
                with open(tmp_path, "wb") as fh:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            fh.write(chunk)
                os.replace(tmp_path, out_path)

        return out_path

    # Otherwise, try to delegate to hf_hub_download (newer API)
    try:
        from huggingface_hub import hf_hub_download
        
        # Pass all relevant kwargs to the new function
        all_kwargs = kwargs.copy()
        all_kwargs.update({
            'cache_dir': cache_dir,
            'force_download': force_download,
            'resume_download': resume_download,
        })
        
        return hf_hub_download(*args, **all_kwargs)
    except Exception:
        print("Failed to use hf_hub_download, falling back.")
        raise


# Ensure the compatibility function is available under the old name
if not hasattr(huggingface_hub, "cached_download"):
    huggingface_hub.cached_download = _cached_download  # type: ignore[attr-defined]


from sentence_transformers import SentenceTransformer
from datetime import datetime, timedelta, timezone
import pytz
import spacy
from neo4j.time import DateTime, Date
from pymongo.errors import PyMongoError
from mongo import get_mongo_db
import hashlib
from fastapi import File, Form, UploadFile
from pathlib import Path
import random
import asyncio
import json
import smtplib
from email.message import EmailMessage
import uvicorn

from typing import Optional, List

# Import document processor for PDF handling and CSP timetable generation
from document_processor import (
    DocumentProcessor, 
    StudyConstraints, 
    Subject, 
    AcademicEvent, 
    ExamSchedule,
    CSPTimetableGenerator,
    universal_extractor
)

# Initialize document processor
doc_processor = DocumentProcessor()

from typing import Optional
from pydantic import BaseModel, Field


# Indian Standard Time timezone
IST = pytz.timezone('Asia/Kolkata')

# Import NSGA-II Scheduler
from nsga2_scheduler import generate_study_schedule

# --- 1. FastAPI App Initialization ---
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Helper function for JSON serialization ---
def neo4j_to_serializable(obj):
    """Recursively converts Neo4j objects to JSON serializable formats."""
    if isinstance(obj, (DateTime, Date)):
        return obj.isoformat()
    if hasattr(obj, 'items'):
        return {key: neo4j_to_serializable(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [neo4j_to_serializable(element) for element in obj]
    return obj

def _parse_iso_to_dt(val):
    """Parse ISO string or datetime/date-like into a naive UTC datetime."""
    if not val:
        return None
    try:
        if isinstance(val, datetime):
            dt = val
        else:
            if isinstance(val, str) and len(val) == 10 and val.count('-') == 2:
                dt = datetime.fromisoformat(val + 'T00:00:00')
            else:
                dt = datetime.fromisoformat(str(val))
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None

# --- 2. Database & AI Model Setup ---
from db import get_driver
from graph_helpers import ensure_user_and_day, normalize_day, touch_user_login

driver = get_driver()
print("Neo4j connection successful.")

DEFAULT_USER_EMAIL = os.getenv('DEFAULT_USER_EMAIL', 'demo@trackeneer.local')


def _resolve_user_email(request: Request, payload: Optional[dict] = None) -> str:
    """Resolve the user email from payload or headers, applying defaults."""
    email = None
    if payload:
        email = payload.get('userEmail') or payload.get('email')
    email = email or request.headers.get('x-user-email') or request.headers.get('X-User-Email')
    if not email:
        email = DEFAULT_USER_EMAIL
    if not email:
        raise HTTPException(status_code=400, detail='User email is required')
    return email.strip().lower()

print("Initializing AI model configuration...")

model = None
classifier_model = None
label_prototypes = {}
nlp = None

PREFER_SKIP = os.getenv('SKIP_MODEL_LOAD', '0') == '1'
EMBED_MODEL = os.getenv('EMBED_MODEL') or './all-MiniLM-L6-v2'
CLASSIFIER_MODEL = os.getenv('CLASSIFIER_MODEL')


def _clean_pooling_config(model_dir: Path) -> None:
    """Remove pooling parameters unsupported by older sentence-transformers versions.

    Newer HuggingFace model cards ship params like ``pooling_mode_weightedmean_tokens``,
    ``pooling_mode_lasttoken`` and ``include_prompt`` which cause a TypeError on
    sentence-transformers < 2.3.  Stripping them is safe because only ``mean`` pooling
    is active for MiniLM.
    """
    pooling_config = model_dir / "1_Pooling" / "config.json"
    if not pooling_config.exists():
        return
    SUPPORTED_KEYS = {
        "word_embedding_dimension",
        "pooling_mode_cls_token",
        "pooling_mode_mean_tokens",
        "pooling_mode_max_tokens",
        "pooling_mode_mean_sqrt_len_tokens",
    }
    try:
        with open(pooling_config, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        unknown = set(cfg.keys()) - SUPPORTED_KEYS
        if unknown:
            for k in unknown:
                del cfg[k]
            with open(pooling_config, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4)
            print(f"Cleaned pooling config at {pooling_config}: removed unsupported keys {unknown}")
    except Exception as e:
        print(f"Warning: could not clean pooling config at {pooling_config}: {e}")


def _load_sentence_transformer(model_name: str) -> SentenceTransformer:
    """Load a SentenceTransformer model, cleaning broken cache directories if needed."""
    cache_root = Path(os.getenv("SENTENCE_TRANSFORMERS_HOME", Path.home() / ".cache" / "sentence_transformers"))
    cache_root.mkdir(parents=True, exist_ok=True)

    safe_folder = model_name.replace("/", "_")
    candidate_dir = cache_root / safe_folder

    expected_files = (
        "pytorch_model.bin",
        "model.safetensors",
        "tf_model.h5",
        "model.ckpt.index",
        "flax_model.msgpack",
    )

    if candidate_dir.exists() and not any((candidate_dir / fname).exists() for fname in expected_files):
        print(f"Incomplete cached model detected for {model_name}. Removing {candidate_dir} and retrying download.")
        shutil.rmtree(candidate_dir, ignore_errors=True)

    # Clean pooling config for the local model path (if it's a directory)
    local_path = Path(model_name)
    if local_path.is_dir():
        _clean_pooling_config(local_path)

    # Clean pooling config for the cached copy (if it exists)
    if candidate_dir.exists():
        _clean_pooling_config(candidate_dir)

    return SentenceTransformer(model_name, cache_folder=str(cache_root))

def _initialize_models() -> None:
    global model, classifier_model, nlp, label_prototypes

    if PREFER_SKIP:
        print("SKIP_MODEL_LOAD=1 detected — skipping heavy model downloads for faster startup (dev mode).")
        return

    try:
        model = _load_sentence_transformer(EMBED_MODEL)
        print(f"Loaded embedding model: {EMBED_MODEL}")

    except Exception as exc:
        print(f"Could not load embedding model {EMBED_MODEL}: {exc}")
        print("Falling back to lightweight model 'sentence-transformers/all-MiniLM-L6-v2'.")
        model = _load_sentence_transformer("sentence-transformers/all-MiniLM-L6-v2")
        print("Loaded fallback embedding model: sentence-transformers/all-MiniLM-L6-v2")

    if CLASSIFIER_MODEL:
        try:
            classifier_model = _load_sentence_transformer(CLASSIFIER_MODEL)

            print(f"Loaded classifier model: {CLASSIFIER_MODEL}")
        except Exception as exc:
            print(f"Warning: could not load classifier model {CLASSIFIER_MODEL}: {exc}")

    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        print("spaCy model not found. Attempting to download...")
        os.system('python -m spacy download en_core_web_sm')
        nlp = spacy.load("en_core_web_sm")

    try:
        proto_labels = ['urgent', 'not urgent', 'important', 'not important',
                        'dsa', 'aptitude', 'system design', 'machine learning', 'projects', 'reading', 'general']
        proto_source = classifier_model or model
        proto_embs = proto_source.encode(proto_labels)
        for lab, emb in zip(proto_labels, proto_embs):
            label_prototypes[lab] = emb
    except Exception as exc:
        print(f"Warning: could not create prototype label embeddings: {exc}")


_initialize_models()

chroma_client = chromadb.Client()
vector_db = chroma_client.get_or_create_collection(name="dynamic_task_scheduler_neo4j")
print("AI Models and Vector DB are ready.")

# WebSocket connection manager
connected_webs = set()
NOTIFIED_TASK_KEYS = set()

SEGMENT_SPLIT_PATTERN = re.compile(r"[\n\r]+|(?<=[.!?])\s+(?=[A-Z0-9])")
FALLBACK_DATE_PATTERN = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
    r"Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)(?:\s+\d{1,2}(?:st|nd|rd|th)?(?:,\s*\d{2,4})?)?)\b",
    re.IGNORECASE,
)
FALLBACK_TIME_PATTERN = re.compile(r"\b\d{1,2}:\d{2}\s*(?:am|pm)?|\b\d{1,2}\s*(?:am|pm)\b", re.IGNORECASE)


def _segment_knowledge_text(text: str) -> list[str]:
    segments = [seg.strip(" \t•-_") for seg in SEGMENT_SPLIT_PATTERN.split(text) if seg.strip()]
    if not segments:
        lone = text.strip()
        return [lone] if lone else []
    return segments


def _extract_temporal_hints(snippet: str) -> list[str]:
    hints: list[str] = []
    global nlp
    try:
        if nlp:
            doc = nlp(snippet)
            hints.extend(ent.text for ent in doc.ents if ent.label_ in {"DATE", "TIME"})
    except Exception as exc:
        print(f"Warning: could not run spaCy for knowledge hints: {exc}")
    if not hints:
        hints.extend(FALLBACK_DATE_PATTERN.findall(snippet))
        hints.extend(FALLBACK_TIME_PATTERN.findall(snippet))
    unique_hints: list[str] = []
    for hint in hints:
        normalized = hint.strip()
        if normalized and normalized not in unique_hints:
            unique_hints.append(normalized)
    return unique_hints


class KnowledgePayload(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, description="User submitted note to ingest")
    pagePath: Optional[str] = Field(None, max_length=200, description="Front-end route where the note originated")


# --- Actionable Task Extraction from Knowledge Notes ---

# Patterns that indicate an actionable event / task
_ACTION_KEYWORDS = re.compile(
    r"\b(meeting|deadline|submit|presentation|exam|interview|call|appointment|"
    r"class|lecture|workshop|seminar|webinar|viva|demo|review|standup|sync|"
    r"due|hand.?in|turn.?in|deliver|defend|session|conference|hackathon|test)\b",
    re.IGNORECASE,
)

# Regex to extract time like "4 pm", "16:00", "4:30 PM", "at 2", etc.
_TIME_RE = re.compile(
    r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM)\b"
    r"|\b(?:at\s+)(\d{1,2})(?::(\d{2}))?\b"
    r"|\b(\d{1,2}):(\d{2})\b",
    re.IGNORECASE,
)

# Regex for relative day references
_RELATIVE_DAY_RE = re.compile(
    r"\b(today|tonight|tomorrow|day after tomorrow)\b", re.IGNORECASE
)

# Regex for absolute dates like "3rd Nov", "March 15", "15/03", "2026-03-15"
_ABSOLUTE_DATE_RE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"(?:\s+(\d{4}))?\b"
    r"|\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{4}))?\b"
    r"|\b(\d{4})-(\d{2})-(\d{2})\b"
    r"|\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b",
    re.IGNORECASE,
)

_MONTH_MAP = {
    'jan': 1, 'january': 1, 'feb': 2, 'february': 2,
    'mar': 3, 'march': 3, 'apr': 4, 'april': 4,
    'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
    'aug': 8, 'august': 8, 'sep': 9, 'september': 9,
    'oct': 10, 'october': 10, 'nov': 11, 'november': 11,
    'dec': 12, 'december': 12,
}

_DEFAULT_DURATION_MINUTES = 60


def _parse_time_from_text(text: str) -> Optional[tuple]:
    """Extract (hour, minute) in 24h format from text. Returns None if not found."""
    m = _TIME_RE.search(text)
    if not m:
        return None
    groups = m.groups()
    # Pattern 1: "4 pm", "4:30 PM"
    if groups[0] is not None:
        hour = int(groups[0])
        minute = int(groups[1]) if groups[1] else 0
        meridiem = (groups[2] or '').lower()
        if meridiem == 'pm' and hour != 12:
            hour += 12
        elif meridiem == 'am' and hour == 12:
            hour = 0
        return (hour, minute)
    # Pattern 2: "at 2", "at 14:30"
    if groups[3] is not None:
        hour = int(groups[3])
        minute = int(groups[4]) if groups[4] else 0
        # Heuristic: if hour <= 6 assume PM for common phrases like "at 4"
        if hour <= 6:
            hour += 12
        return (hour, minute)
    # Pattern 3: "16:00"
    if groups[5] is not None:
        return (int(groups[5]), int(groups[6]))
    return None


def _parse_date_from_text(text: str, reference: datetime = None) -> Optional[datetime]:
    """Extract a date from the text. Returns a datetime (date only, time=00:00) or None."""
    if reference is None:
        reference = datetime.now(IST)

    # Check relative days first
    rm = _RELATIVE_DAY_RE.search(text)
    if rm:
        word = rm.group(1).lower()
        if word in ('today', 'tonight'):
            return reference.replace(hour=0, minute=0, second=0, microsecond=0)
        elif word == 'tomorrow':
            return (reference + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif word == 'day after tomorrow':
            return (reference + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)

    # Check spaCy DATE entities
    if nlp:
        try:
            doc = nlp(text)
            for ent in doc.ents:
                if ent.label_ == 'DATE':
                    ent_lower = ent.text.lower().strip()
                    if ent_lower in ('today', 'tonight', 'now'):
                        return reference.replace(hour=0, minute=0, second=0, microsecond=0)
                    if ent_lower == 'tomorrow':
                        return (reference + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        except Exception:
            pass

    # Check absolute date patterns
    am = _ABSOLUTE_DATE_RE.search(text)
    if am:
        groups = am.groups()
        try:
            # "3rd Nov", "3 November 2026"
            if groups[0] is not None and groups[1] is not None:
                day = int(groups[0])
                month = _MONTH_MAP.get(groups[1].lower()[:3], 0)
                year = int(groups[2]) if groups[2] else reference.year
                if month:
                    return reference.replace(year=year, month=month, day=day,
                                             hour=0, minute=0, second=0, microsecond=0)
            # "Nov 3", "November 3, 2026"
            elif groups[3] is not None and groups[4] is not None:
                month = _MONTH_MAP.get(groups[3].lower()[:3], 0)
                day = int(groups[4])
                year = int(groups[5]) if groups[5] else reference.year
                if month:
                    return reference.replace(year=year, month=month, day=day,
                                             hour=0, minute=0, second=0, microsecond=0)
            # "2026-03-15"
            elif groups[6] is not None:
                return reference.replace(year=int(groups[6]), month=int(groups[7]),
                                         day=int(groups[8]),
                                         hour=0, minute=0, second=0, microsecond=0)
            # "15/03" or "15/03/2026"
            elif groups[9] is not None and groups[10] is not None:
                d, mo = int(groups[9]), int(groups[10])
                yr = int(groups[11]) if groups[11] else reference.year
                if yr < 100:
                    yr += 2000
                if mo > 12 and d <= 12:
                    d, mo = mo, d
                return reference.replace(year=yr, month=mo, day=d,
                                         hour=0, minute=0, second=0, microsecond=0)
        except (ValueError, TypeError):
            pass

    return None


def _build_task_title(text: str) -> str:
    """Build a concise task title from the raw text."""
    # Remove time/date references to create a cleaner title
    title = _TIME_RE.sub('', text)
    title = _RELATIVE_DAY_RE.sub('', title)
    title = _ABSOLUTE_DATE_RE.sub('', title)
    # Clean up leftover prepositions and whitespace
    title = re.sub(r'\b(at|on|by|from|to|the)\s*$', '', title, flags=re.IGNORECASE)
    title = re.sub(r'^\s*(i have a|i have|i got a|i got|there is a|there is|my)\s+', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s{2,}', ' ', title).strip(' .,;:-')
    if title:
        title = title[0].upper() + title[1:]
    return title or 'Task from knowledge note'


def _extract_actionable_tasks(text: str, reference_time: datetime = None) -> list[dict]:
    """
    Analyse a knowledge note and extract actionable tasks.
    Returns a list of dicts with keys: title, description, startTime, endTime, source.
    """
    if reference_time is None:
        reference_time = datetime.now(IST)

    segments = _segment_knowledge_text(text)
    tasks = []

    for segment in segments:
        # Only consider segments with actionable keywords
        if not _ACTION_KEYWORDS.search(segment):
            continue

        parsed_time = _parse_time_from_text(segment)
        parsed_date = _parse_date_from_text(segment, reference_time)

        # If we have at least a time or a date, create a task
        if parsed_time is None and parsed_date is None:
            continue

        # Default date = today if only time given
        if parsed_date is None:
            parsed_date = reference_time.replace(hour=0, minute=0, second=0, microsecond=0)

        if parsed_time is not None:
            start_dt = parsed_date.replace(hour=parsed_time[0], minute=parsed_time[1], second=0, microsecond=0)
        else:
            # If only date given, default to 9 AM
            start_dt = parsed_date.replace(hour=9, minute=0, second=0, microsecond=0)

        end_dt = start_dt + timedelta(minutes=_DEFAULT_DURATION_MINUTES)

        title = _build_task_title(segment)

        tasks.append({
            'title': title,
            'description': segment.strip(),
            'startTime': start_dt,
            'endTime': end_dt,
            'source': 'knowledge-capture',
        })

    return tasks


def _create_task_from_knowledge(task_info: dict, user_email: str) -> Optional[str]:
    """Create a Task node in Neo4j from extracted knowledge. Returns task_id or None."""
    try:
        task_id = str(uuid.uuid4())
        start_dt = task_info['startTime']
        end_dt = task_info['endTime']

        ai_analysis = auto_schedule_task({
            'title': task_info['title'],
            'description': task_info['description'],
        })

        task_day_iso = start_dt.date().isoformat()

        with driver.session() as sess:
            ensure_user_and_day(sess, user_email, day=task_day_iso)
            sess.run("""
                MATCH (u:User {email: $email})-[:HAS_DAY]->(d:Day {date: date($task_date), email: $email})
                CREATE (t:Task {
                    id: $id, title: $title, description: $description,
                    startTime: datetime($start_time), endTime: datetime($end_time),
                    status: 'pending',
                    dueDate: datetime($end_time),
                    createdAt: datetime(), priority: $priority, category: $category,
                    estimatedDuration: $estimated_duration, aiEnhanced: $ai_enhanced,
                    timezone: 'IST', ownerEmail: $email, dayDate: $task_date,
                    source: 'knowledge-capture'
                })
                MERGE (d)-[:HAS_TASK]->(t)
            """,
            task_date=task_day_iso,
            id=task_id,
            title=task_info['title'],
            description=task_info['description'],
            start_time=start_dt,
            end_time=end_dt,
            email=user_email,
            **ai_analysis)

        # Add embedding
        try:
            if model is not None:
                vector_db.add(
                    ids=[task_id],
                    embeddings=[model.encode(task_info['description']).tolist()]
                )
        except Exception as e:
            print(f"Warning: could not add embedding for knowledge task: {e}")

        print(f"✅ Auto-created task from knowledge: '{task_info['title']}' at {start_dt.isoformat()}")
        return task_id
    except Exception as e:
        print(f"Warning: failed to auto-create task from knowledge: {e}")
        return None

async def notify_clients(payload: dict):
    """Broadcast a JSON payload to all connected websocket clients."""
    to_remove = []
    text = json.dumps(payload, default=str)
    for ws in list(connected_webs):
        try:
            await ws.send_text(text)
        except Exception as e:
            print(f"Warning: failed to send websocket message: {e}")
            to_remove.append(ws)
    for ws in to_remove:
        try:
            connected_webs.discard(ws)
        except Exception:
            pass

async def background_push_watcher():
    """Background watcher for task notifications."""
    print('Background push watcher started')
    while True:
        try:
            now = datetime.utcnow()
            window_end = now + timedelta(seconds=40)
            with driver.session() as session:
                res = session.run("""
                    MATCH (t:Task) 
                    WHERE t.status='pending' 
                    AND (t.startTime IS NOT NULL OR t.endTime IS NOT NULL OR t.dueDate IS NOT NULL) 
                    RETURN t.id AS id, t.title AS title, t.startTime AS startTime, 
                           t.endTime AS endTime, t.dueDate AS dueDate 
                    LIMIT 200
                """)
                rows = [r.data() for r in res]

            for r in rows:
                try:
                    tid = r.get('id')
                    title = r.get('title') or 'Untitled'
                    raw_start = neo4j_to_serializable(r.get('startTime'))
                    raw_end = neo4j_to_serializable(r.get('endTime'))
                    raw_due = neo4j_to_serializable(r.get('dueDate'))

                    # Check start time
                    if raw_start:
                        ds = _parse_iso_to_dt(raw_start)
                        if ds and now <= ds <= window_end:
                            key = f"{tid}-start-{ds.isoformat()}"
                            if key not in NOTIFIED_TASK_KEYS:
                                await notify_clients({'type': 'task_start', 'task': {'id': tid, 'title': title, 'startTime': ds.isoformat()}})
                                NOTIFIED_TASK_KEYS.add(key)
                                print(f"✅ Notification sent: Task '{title}' is starting!")

                    # Check end time
                    if raw_end:
                        de = _parse_iso_to_dt(raw_end)
                        if de and now <= de <= window_end:
                            key = f"{tid}-end-{de.isoformat()}"
                            if key not in NOTIFIED_TASK_KEYS:
                                await notify_clients({'type': 'task_end', 'task': {'id': tid, 'title': title, 'endTime': de.isoformat()}})
                                NOTIFIED_TASK_KEYS.add(key)
                                print(f"✅ Notification sent: Task '{title}' is ending!")

                    # Check due date
                    if raw_due:
                        dd = _parse_iso_to_dt(raw_due)
                        if dd and now <= dd <= window_end:
                            key = f"{tid}-due-{dd.isoformat()}"
                            if key not in NOTIFIED_TASK_KEYS:
                                await notify_clients({'type': 'task_due', 'task': {'id': tid, 'title': title, 'dueDate': dd.isoformat()}})
                                NOTIFIED_TASK_KEYS.add(key)
                                print(f"✅ Notification sent: Task '{title}' is due!")
                except Exception as e:
                    print(f"Error evaluating push candidate: {e}")
        except Exception as e:
            print(f"Background push watcher error: {e}")
        await asyncio.sleep(10)

@app.on_event('startup')
async def _start_background_tasks():
    try:
        asyncio.create_task(background_push_watcher())
    except Exception as e:
        print(f"Failed to start background push watcher: {e}")

# Load cached embeddings
CACHE_META = None
CACHE_PATH = os.path.join(os.path.dirname(__file__), 'model_cache.npz')
CACHE_META_PATH = os.path.join(os.path.dirname(__file__), 'model_cache_meta.json')

try:
    if os.path.exists(CACHE_PATH):
        import numpy as _np
        arr = _np.load(CACHE_PATH, allow_pickle=True)
        ids = arr['ids'].tolist() if 'ids' in arr else []
        embeddings = arr['embeddings'].tolist() if 'embeddings' in arr else []
        if ids and embeddings:
            try:
                vector_db.upsert(ids=ids, embeddings=embeddings)
                print(f"Loaded {len(ids)} cached embeddings into Vector DB")
            except Exception as e:
                print(f"Warning: failed to upsert cached embeddings: {e}")
        try:
            if os.path.exists(CACHE_META_PATH):
                with open(CACHE_META_PATH, 'r', encoding='utf-8') as mf:
                    CACHE_META = json.load(mf)
        except Exception:
            CACHE_META = None
except Exception as e:
    print(f"Error loading cache file: {e}")

# --- 3. Task Automation Functions ---
def auto_schedule_task(task_data):
    """Auto-detect priority and category from task data."""
    description = task_data.get('description', '')
    title = task_data.get('title', '')
    
    priority = "medium"
    if nlp:
        desc_lower = description.lower()
        if any(k in desc_lower for k in ["urgent", "asap", "deadline", "critical"]):
            priority = "high"
        elif any(k in desc_lower for k in ["maybe", "later", "someday", "eventually"]):
            priority = "low"
    
    category = "general"
    try:
        s = (title + ' ' + description).lower()
        if any(k in s for k in ['work', 'project', 'job', 'capgemini', 'placement']):
            category = 'work'
        elif any(k in s for k in ['health', 'exercise', 'cardio']):
            category = 'health'
        elif any(k in s for k in ['read', 'study', 'dsa', 'machine learning', 'ml', 'aptitude']):
            category = 'education'
        elif any(k in s for k in ['buy', 'purchase', 'shopping']):
            category = 'shopping'
        elif any(k in s for k in ['finance', 'payment', 'invoice']):
            category = 'finance'
    except Exception:
        category = 'general'
    
    return {
        "priority": priority,
        "category": category,
        "estimated_duration": 30,
        "ai_enhanced": True
    }

def infer_finish_to_start_relations(max_distance_hours: int = 72):
    """Infer finish-to-start precedence relations between tasks."""
    try:
        with driver.session() as session:
            res = session.run("""
                MATCH (t:Task) 
                WHERE t.status='pending' 
                AND t.startTime IS NOT NULL 
                AND t.endTime IS NOT NULL 
                RETURN t.id AS id, t.title AS title, t.startTime AS startTime, 
                       t.endTime AS endTime, t.category AS category 
                LIMIT 500
            """)
            rows = [r.data() for r in res]

        tasks = []
        for r in rows:
            sdt = _parse_iso_to_dt(r.get('startTime'))
            edt = _parse_iso_to_dt(r.get('endTime'))
            if not sdt or not edt:
                continue
            tasks.append({
                'id': r.get('id'),
                'title': r.get('title') or '',
                'start': sdt,
                'end': edt,
                'category': (r.get('category') or '').lower()
            })

        for a in tasks:
            for b in tasks:
                if a['id'] == b['id']:
                    continue
                if a['end'] <= b['start']:
                    gap = (b['start'] - a['end']).total_seconds() / 3600.0
                    if gap <= max_distance_hours:
                        if a['category'] and a['category'] == b['category']:
                            try:
                                with driver.session() as session:
                                    session.run("""
                                        MATCH (a:Task {id:$aid}), (b:Task {id:$bid}) 
                                        MERGE (a)-[:FINISH_TO_START]->(b)
                                    """, aid=a['id'], bid=b['id'])
                            except Exception as e:
                                print(f"Warning: could not create relation: {e}")
                        else:
                            atoks = set([t for t in a['title'].lower().split() if len(t) > 3])
                            btoks = set([t for t in b['title'].lower().split() if len(t) > 3])
                            if atoks & btoks:
                                try:
                                    with driver.session() as session:
                                        session.run("""
                                            MATCH (a:Task {id:$aid}), (b:Task {id:$bid}) 
                                            MERGE (a)-[:FINISH_TO_START]->(b)
                                        """, aid=a['id'], bid=b['id'])
                                except Exception as e:
                                    print(f"Warning: could not create relation: {e}")
    except Exception as e:
        print(f"Error in infer_finish_to_start_relations: {e}")

# --- 4. API Endpoints ---


@app.post("/knowledge")
async def ingest_knowledge(payload: KnowledgePayload, request: Request):
    cleaned = (payload.text or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Please add a short description before submitting.")

    segments = _segment_knowledge_text(cleaned)
    if not segments:
        raise HTTPException(status_code=400, detail="We could not parse your note into any entries.")

    entries = [
        {
            "text": segment,
            "temporalHints": _extract_temporal_hints(segment),
            "pagePath": payload.pagePath,
            "index": idx,
        }
        for idx, segment in enumerate(segments)
    ]

    user_email = _resolve_user_email(request, payload.dict(exclude_none=True))
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    try:
        with driver.session() as session:
            day_iso = ensure_user_and_day(session, user_email, now=now)
            result = session.run(
                """
                MATCH (u:User {email: $email})
                MATCH (d:Day {date: date($day), email: $email})
                WITH u, d
                UNWIND $entries AS entry
                CREATE (k:KnowledgeItem {
                    id: randomUUID(),
                    text: entry.text,
                    pagePath: entry.pagePath,
                    createdAt: datetime($now),
                    sentenceIndex: entry.index,
                    source: 'user-entry',
                    temporalHints: entry.temporalHints,
                    originalSubmission: $raw
                })
                MERGE (u)-[:ADDED_KNOWLEDGE {createdAt: datetime($now)}]->(k)
                MERGE (k)-[:RELATES_TO_DAY]->(d)
                RETURN {
                    id: k.id,
                    text: k.text,
                    temporalHints: k.temporalHints,
                    pagePath: k.pagePath
                } AS item
                """,
                email=user_email,
                day=day_iso,
                entries=entries,
                now=now_iso,
                raw=cleaned,
            ).data()
    except HTTPException:
        raise
    except Exception as exc:
        print(f"Error storing knowledge for {user_email}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to store the knowledge entry.")

    stored_items = [neo4j_to_serializable(record["item"]) for record in result]

    # --- Auto-create tasks from actionable knowledge entries ---
    auto_created_tasks = []
    try:
        now_ist = datetime.now(IST)
        extracted = _extract_actionable_tasks(cleaned, reference_time=now_ist)
        for task_info in extracted:
            task_id = _create_task_from_knowledge(task_info, user_email)
            if task_id:
                auto_created_tasks.append({
                    'taskId': task_id,
                    'title': task_info['title'],
                    'startTime': task_info['startTime'].isoformat(),
                    'endTime': task_info['endTime'].isoformat(),
                    'source': 'knowledge-capture',
                })
                # Notify connected clients about the new task
                try:
                    notification_payload = {
                        'type': 'task_added',
                        'taskId': task_id,
                        'title': task_info['title'],
                        'description': task_info['description'],
                        'startTime': task_info['startTime'].isoformat(),
                        'endTime': task_info['endTime'].isoformat(),
                        'task': {
                            'id': task_id,
                            'title': task_info['title'],
                            'description': task_info['description'],
                            'startTime': task_info['startTime'].isoformat(),
                            'endTime': task_info['endTime'].isoformat(),
                        }
                    }
                    asyncio.create_task(notify_clients(notification_payload))
                except Exception:
                    pass
        if auto_created_tasks:
            print(f"✅ Auto-created {len(auto_created_tasks)} task(s) from knowledge capture")
    except Exception as exc:
        print(f"Warning: task extraction from knowledge failed: {exc}")

    return {
        "added": len(stored_items),
        "items": stored_items,
        "autoCreatedTasks": auto_created_tasks,
    }


@app.post("/api/add-task")
async def add_task(request: Request):
    try:
        data = await request.json()
        if not all(k in data for k in ['title', 'description', 'startTime', 'endTime']):
            raise HTTPException(status_code=400, detail="Missing required task fields.")

        task_id = str(uuid.uuid4())
        
        # Parse datetime fields
        try:
            start_dt = datetime.fromisoformat(data['startTime'].replace('Z', '+00:00'))
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            start_dt_ist = start_dt.astimezone(IST)
        except Exception as e:
            print(f"Error parsing startTime: {e}")
            start_dt_ist = None

        try:
            end_dt = datetime.fromisoformat(data['endTime'].replace('Z', '+00:00'))
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
            end_dt_ist = end_dt.astimezone(IST)
        except Exception as e:
            print(f"Error parsing endTime: {e}")
            end_dt_ist = None

        ai_analysis = auto_schedule_task(data)

        user_email = _resolve_user_email(request, data)
        user_name = data.get('userName')
        task_local_date = start_dt_ist.date() if start_dt_ist else datetime.now(IST).date()
        task_day_iso = task_local_date.isoformat()

        # Handle due date
        provided_due = data.get('dueDate')
        due_datetime_to_store = None
        
        if provided_due:
            try:
                due_dt = datetime.fromisoformat(provided_due.replace('Z', '+00:00'))
                if due_dt.tzinfo is None:
                    due_dt = due_dt.replace(tzinfo=timezone.utc)
                due_datetime_to_store = due_dt.astimezone(IST)
            except Exception as e:
                print(f"Error parsing dueDate: {e}")
        elif end_dt_ist:
            due_datetime_to_store = end_dt_ist
        elif start_dt_ist:
            try:
                est = int(data.get('estimatedDuration') or ai_analysis.get('estimated_duration', 60))
                due_datetime_to_store = start_dt_ist + timedelta(minutes=est)
            except Exception:
                due_datetime_to_store = start_dt_ist + timedelta(hours=1)

        with driver.session() as session:
            ensure_user_and_day(session, user_email, day=task_day_iso, name=user_name)
            session.run("""
                MATCH (u:User {email: $email})-[:HAS_DAY]->(d:Day {date: date($task_date), email: $email})
                CREATE (t:Task {
                    id: $id, title: $title, description: $description, 
                    startTime: datetime($start_time), endTime: datetime($end_time), 
                    status: 'pending', 
                    dueDate: CASE WHEN $due_date IS NOT NULL THEN datetime($due_date) ELSE null END, 
                    createdAt: datetime(), priority: $priority, category: $category, 
                    estimatedDuration: $estimated_duration, aiEnhanced: $ai_enhanced,
                    timezone: 'IST', ownerEmail: $email, ownerName: coalesce($user_name, $email), dayDate: $task_date
                })
                MERGE (d)-[:HAS_TASK]->(t)
            """,
            task_date=task_day_iso,
            id=task_id, 
            title=data['title'],
            description=data['description'], 
            start_time=start_dt_ist, 
            end_time=end_dt_ist, 
            due_date=due_datetime_to_store,
            email=user_email,
            user_name=user_name,
            **ai_analysis)

        # Add embedding to vector DB
        try:
            if model is not None:
                vector_db.add(ids=[task_id], embeddings=[model.encode(data['description']).tolist()])
        except Exception as e:
            print(f"Warning: could not add embedding: {e}")

        # Infer relationships and notify
        try:
            infer_finish_to_start_relations()
            notification_payload = {
                'type': 'task_added',
                'taskId': task_id,
                'title': data.get('title'),
                'description': data.get('description'),
                'startTime': start_dt_ist.isoformat() if start_dt_ist else None,
                'endTime': end_dt_ist.isoformat() if end_dt_ist else None,
                'task': {
                    'id': task_id,
                    'title': data.get('title'),
                    'description': data.get('description'),
                    'startTime': start_dt_ist.isoformat() if start_dt_ist else None,
                    'endTime': end_dt_ist.isoformat() if end_dt_ist else None
                }
            }
            asyncio.create_task(notify_clients(notification_payload))
            print(f"✅ WebSocket notification sent for new task: {data.get('title')}")
        except Exception as e:
            print(f"Warning: notification failed: {e}")

        return JSONResponse(status_code=201, content={"message": "Task added successfully", "taskId": task_id})
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in add_task: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred while adding the task.")

@app.put("/api/tasks/{task_id}")
async def update_task(task_id: str, request: Request):
    try:
        data = await request.json()
        user_email = _resolve_user_email(request, data)
        
        # Parse datetime fields if present
        start_dt_ist = None
        if data.get('startTime'):
            try:
                start_dt = datetime.fromisoformat(data['startTime'].replace('Z', '+00:00'))
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                start_dt_ist = start_dt.astimezone(IST)
            except Exception as e:
                print(f"Error parsing startTime: {e}")

        end_dt_ist = None
        if data.get('endTime'):
            try:
                end_dt = datetime.fromisoformat(data['endTime'].replace('Z', '+00:00'))
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
                end_dt_ist = end_dt.astimezone(IST)
            except Exception as e:
                print(f"Error parsing endTime: {e}")

        due_datetime_to_store = None
        if data.get('dueDate'):
            try:
                due_dt = datetime.fromisoformat(data['dueDate'].replace('Z', '+00:00'))
                if due_dt.tzinfo is None:
                    due_dt = due_dt.replace(tzinfo=timezone.utc)
                due_datetime_to_store = due_dt.astimezone(IST)
            except Exception as e:
                print(f"Error parsing dueDate: {e}")

        with driver.session() as session:
            # Verify ownership and update
            # We use COALESCE to keep existing values if not provided (PATCH-like behavior)
            query = """
                MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_TASK]->(t:Task {id: $task_id})
                SET t.title = coalesce($title, t.title),
                    t.description = coalesce($description, t.description),
                    t.startTime = coalesce($start_time, t.startTime),
                    t.endTime = coalesce($end_time, t.endTime),
                    t.dueDate = $due_date,  
                    t.updatedAt = datetime()
                RETURN t
            """
            
            # Note: dueDate is special because we might want to clear it if explicitly null? 
            # For now, we assume if it's sent, it updates. If not in payload, we skip updating it?
            # Actually, `data.get('dueDate')` returns None if missing. 
            # If user wants to clear it, they might send null.
            # Let's check keys.
            
            params = {
                'email': user_email,
                'task_id': task_id,
                'title': data.get('title'),
                'description': data.get('description'),
                'start_time': start_dt_ist,
                'end_time': end_dt_ist,
                'due_date': due_datetime_to_store
            }
            
            # If keys are missing from `data`, we pass None, and COALESCE keeps original.
            # However, for dueDate, we might want to allow setting to NULL.
            # The query above uses $due_date. If $due_date is None, Neo4j sets it to null? No.
            # Neo4j property set to null removes the property.
            # But if I pass None to python driver, it usually passes null.
            # If I want to partial update dueDate only if provided:
            # I should handle the SET clause dynamically or be smarter.
            
            # Simplified approach: Only update fields present in data keys.
            sets = []
            if 'title' in data: sets.append("t.title = $title")
            if 'description' in data: sets.append("t.description = $description")
            if 'startTime' in data: sets.append("t.startTime = $start_time")
            if 'endTime' in data: sets.append("t.endTime = $end_time")
            if 'dueDate' in data: sets.append("t.dueDate = $due_date")
            sets.append("t.updatedAt = datetime()")
            
            if not sets:
                return JSONResponse(content={"message": "No fields to update"}, status_code=200)

            final_query = f"""
                MATCH (u:User {{email: $email}})-[:HAS_DAY]->(:Day)-[:HAS_TASK]->(t:Task {{id: $task_id}})
                SET {', '.join(sets)}
                RETURN t
            """
            
            res = session.run(final_query, **params)
            if not res.peek():
                raise HTTPException(status_code=404, detail="Task not found or owned by user")
                
            # Update embedding if description changed
            if 'description' in data and model is not None:
                try:
                    vector_db.upsert(ids=[task_id], embeddings=[model.encode(data['description']).tolist()])
                except Exception as e:
                    print(f"Warning: could not update embedding: {e}")

        return JSONResponse(content={"message": "Task updated successfully"}, status_code=200)

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating task: {e}")
        raise HTTPException(status_code=500, detail="Failed to update task")

@app.get("/api/schedule")
async def get_schedule(date: str, request: Request, email: Optional[str] = None):
    try:
        user_email = _resolve_user_email(request, {'email': email} if email else None)
        query_date = normalize_day(date)
        with driver.session() as session:
            ensure_user_and_day(session, user_email, day=query_date)
            result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_DAY]->(d:Day {date: date($d), email: $email})-[:HAS_TASK]->(t:Task)
                RETURN t 
                ORDER BY t.startTime
            """, d=query_date, email=user_email)
            tasks = [neo4j_to_serializable(record['t']) for record in result]
        return {"date": query_date, "tasks": tasks}
    except Exception as e:
        print(f"Error in get_schedule: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve schedule.")

@app.get("/api/upcoming-deadlines")
async def get_upcoming_deadlines(request: Request, email: Optional[str] = None):
    try:
        user_email = _resolve_user_email(request, {'email': email} if email else None)
        today = datetime.utcnow().date()
        with driver.session() as session:
            result = session.run(
                """
                MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_TASK]->(t:Task)
                WHERE t.status = 'pending'
                RETURN t
                """,
                email=user_email,
            )
            raw = [r['t'] for r in result]

        entries = []
        for t in raw:
            try:
                task_obj = {k: neo4j_to_serializable(v) for k, v in dict(t).items()} if hasattr(t, 'items') else dict(t)
                cand = task_obj.get('dueDate') or task_obj.get('endTime') or task_obj.get('startTime')
                dt = _parse_iso_to_dt(cand)
                if not dt:
                    continue
                if dt.date() >= today:
                    entries.append({
                        'title': task_obj.get('title'),
                        'dueDate': dt.isoformat(),
                        'priority': task_obj.get('priority') or 'medium'
                    })
            except Exception as e:
                print(f"Skipping task in deadlines: {e}")
                continue

        entries = sorted(entries, key=lambda x: _parse_iso_to_dt(x['dueDate']) or datetime.max)[:5]
        return {"deadlines": entries}
    except Exception as e:
        print(f"Error fetching deadlines: {e}")
        raise HTTPException(status_code=500, detail="Could not fetch upcoming deadlines")

# --- Study Schedule Endpoints ---

@app.post("/api/study/generate")
async def api_generate_study_schedule(request: Request):
    """Generate an optimized study schedule based on exams."""
    try:
        data = await request.json()
        exams = data.get('exams', [])
        if not exams:
            raise HTTPException(status_code=400, detail="No exams provided")
        
        # Run NSGA-II on the backend
        result = generate_study_schedule(exams)
        return result
    except Exception as e:
        print(f"Error generating study schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/study/save")
async def api_save_study_schedule(request: Request):
    """Save the generated study schedule to the user's calendar."""
    try:
        data = await request.json()
        schedule = data.get('schedule', [])
        user_email = _resolve_user_email(request, data)
        
        if not schedule:
            raise HTTPException(status_code=400, detail="No schedule provided to save")

        count = 0
        with driver.session() as session:
            for day_sched in schedule:
                date_str = day_sched.get('date')
                if not date_str:
                    continue
                
                # Ensure day exists
                ensure_user_and_day(session, user_email, day=date_str)
                
                for session_item in day_sched.get('sessions', []):
                    subject = session_item.get('subject')
                    start_time_str = session_item.get('start_time') # "HH:MM"
                    end_time_str = session_item.get('end_time')     # "HH:MM"
                    
                    if not subject or not start_time_str or not end_time_str:
                        continue
                        
                    # Construct full iso datetimes
                    try:
                        start_iso = f"{date_str}T{start_time_str}:00"
                        end_iso = f"{date_str}T{end_time_str}:00"
                        
                        # Add timezone info (simplified)
                        sdt = datetime.fromisoformat(start_iso).replace(tzinfo=IST)
                        edt = datetime.fromisoformat(end_iso).replace(tzinfo=IST)
                    except Exception:
                        continue
                        
                    tasks_list = session_item.get('tasks', [])
                    description = f"Study Session for {subject}.\n"
                    if tasks_list:
                        description += "Tasks:\n" + "\n".join([f"- {t.get('task')} ({t.get('duration')}h)" for t in tasks_list])
                    
                    task_id = str(uuid.uuid4())
                    
                    session.run("""
                        MATCH (u:User {email: $email})-[:HAS_DAY]->(d:Day {date: date($task_date), email: $email})
                        CREATE (t:Task {
                            id: $id, 
                            title: $title, 
                            description: $description, 
                            startTime: datetime($start_time), 
                            endTime: datetime($end_time), 
                            status: 'pending', 
                            createdAt: datetime(), 
                            priority: $priority, 
                            category: 'education', 
                            aiEnhanced: true,
                            timezone: 'IST', 
                            ownerEmail: $email, 
                            dayDate: $task_date
                        })
                        MERGE (d)-[:HAS_TASK]->(t)
                    """, 
                    email=user_email,
                    task_date=date_str,
                    id=task_id,
                    title=f"Study: {subject}",
                    description=description,
                    start_time=sdt,
                    end_time=edt,
                    priority=session_item.get('priority', 'medium')
                    )
                    count += 1
        
        return {"message": f"Successfully saved {count} study sessions to calendar.", "count": count}

    except Exception as e:
        print(f"Error saving study schedule: {e}")
        raise HTTPException(status_code=500, detail="Failed to save schedule to calendar")


@app.post("/api/study/add-to-knowledge-graph")
async def api_add_schedule_to_knowledge_graph(request: Request):
    """Import the NSGA-II generated study schedule into the Neo4j knowledge graph.

    This creates:
    - A :StudyTimetable node representing the overall schedule
    - :StudySession nodes for each daily session
    - :Subject nodes for each unique subject (merged with existing Concepts)
    - Relationships: User -[:HAS_TIMETABLE]-> StudyTimetable
                     StudyTimetable -[:HAS_SESSION]-> StudySession
                     StudySession -[:COVERS_SUBJECT]-> Subject/Concept
    """
    try:
        data = await request.json()
        schedule = data.get('schedule', [])
        user_email = _resolve_user_email(request, data)
        timetable_name = data.get('name', 'NSGA-II Study Timetable')

        if not schedule:
            raise HTTPException(status_code=400, detail="No schedule provided")

        timetable_id = str(uuid.uuid4())
        total_days = len(schedule)
        total_sessions = 0
        total_hours = 0
        subjects_seen = set()

        with driver.session() as session:
            # 1. Ensure user exists
            ensure_user_and_day(session, user_email)

            # 2. Create the StudyTimetable node
            session.run("""
                MATCH (u:User {email: $email})
                MERGE (tt:StudyTimetable {id: $tt_id})
                ON CREATE SET
                    tt.name = $name,
                    tt.totalDays = $total_days,
                    tt.createdAt = datetime(),
                    tt.source = 'nsga2',
                    tt.ownerEmail = $email
                ON MATCH SET
                    tt.name = $name,
                    tt.totalDays = $total_days,
                    tt.updatedAt = datetime()
                MERGE (u)-[:HAS_TIMETABLE]->(tt)
            """,
                email=user_email,
                tt_id=timetable_id,
                name=timetable_name,
                total_days=total_days,
            )

            # 3. Create sessions and link to subjects
            for day_sched in schedule:
                date_str = day_sched.get('date')
                if not date_str:
                    continue
                # Normalize date to YYYY-MM-DD
                if isinstance(date_str, str) and 'T' in date_str:
                    date_str = date_str.split('T')[0]

                for sess in day_sched.get('sessions', []):
                    subject = sess.get('subject')
                    if not subject:
                        continue

                    session_id = str(uuid.uuid4())
                    start_time = sess.get('start_time', sess.get('startTime', '09:00'))
                    end_time = sess.get('end_time', sess.get('endTime', '10:00'))
                    hours = sess.get('hours', 1)
                    priority = sess.get('priority', 'normal')
                    days_until_exam = sess.get('days_until_exam', sess.get('daysUntilExam', 999))
                    tasks_list = sess.get('tasks', [])

                    total_sessions += 1
                    total_hours += hours
                    subjects_seen.add(subject)

                    tasks_desc = "; ".join(
                        [f"{t.get('task', '')} ({t.get('duration', '')}h, {t.get('type', '')})" for t in tasks_list]
                    ) if tasks_list else ""

                    # Create StudySession node and link to timetable
                    session.run("""
                        MATCH (tt:StudyTimetable {id: $tt_id})
                        CREATE (ss:StudySession {
                            id: $ss_id,
                            date: $date,
                            subject: $subject,
                            startTime: $start_time,
                            endTime: $end_time,
                            hours: $hours,
                            priority: $priority,
                            daysUntilExam: $days_until_exam,
                            tasks: $tasks_desc,
                            createdAt: datetime(),
                            ownerEmail: $email
                        })
                        MERGE (tt)-[:HAS_SESSION]->(ss)
                    """,
                        tt_id=timetable_id,
                        ss_id=session_id,
                        date=date_str,
                        subject=subject,
                        start_time=start_time,
                        end_time=end_time,
                        hours=hours,
                        priority=priority,
                        days_until_exam=days_until_exam,
                        tasks_desc=tasks_desc,
                        email=user_email,
                    )

                    # Link session to a Concept/Subject node (merge so existing concepts are reused)
                    session.run("""
                        MATCH (ss:StudySession {id: $ss_id})
                        MATCH (u:User {email: $email})
                        MERGE (subj:Concept {name: $subject_name, userEmail: $email})
                        ON CREATE SET
                            subj.id = randomUUID(),
                            subj.category = 'subject',
                            subj.difficulty = 'medium',
                            subj.source_document = 'nsga2_timetable',
                            subj.createdAt = datetime()
                        MERGE (u)-[:HAS_CONCEPT]->(subj)
                        MERGE (ss)-[:COVERS_SUBJECT]->(subj)
                    """,
                        ss_id=session_id,
                        subject_name=subject,
                        email=user_email,
                    )

            # 4. Update timetable totals
            session.run("""
                MATCH (tt:StudyTimetable {id: $tt_id})
                SET tt.totalSessions = $total_sessions,
                    tt.totalHours = $total_hours,
                    tt.subjectCount = $subject_count
            """,
                tt_id=timetable_id,
                total_sessions=total_sessions,
                total_hours=total_hours,
                subject_count=len(subjects_seen),
            )

        return {
            "message": f"Timetable added to knowledge graph with {total_sessions} sessions across {total_days} days.",
            "timetableId": timetable_id,
            "totalSessions": total_sessions,
            "totalHours": total_hours,
            "subjects": list(subjects_seen),
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error adding schedule to knowledge graph: {e}")
        raise HTTPException(status_code=500, detail="Failed to add schedule to knowledge graph")


# --- Quote Cache for External API ---
QUOTE_CACHE = {}
QUOTE_CACHE_TAGS = {
    'schedule': ['productivity', 'planning', 'time management'],
    'study': ['learning', 'knowledge', 'education'],
    'insights': ['success', 'growth', 'motivation'],
    'placement': ['work', 'career', 'success']
}

# Fallback quotes (static list)
FALLBACK_QUOTES = [
    {"content": "The beautiful thing about learning is that no one can take it away from you.", "author": "B.B. King", "category": "study"},
    {"content": "Live as if you were to die tomorrow. Learn as if you were to live forever.", "author": "Mahatma Gandhi", "category": "study"},
    {"content": "The expert in anything was once a beginner.", "author": "Helen Hayes", "category": "study"},
    {"content": "Success is the sum of small efforts, repeated day in and day out.", "author": "Robert Collier", "category": "schedule"},
    {"content": "There are no shortcuts to any place worth going.", "author": "Beverly Sills", "category": "schedule"},
    {"content": "The only place where success comes before work is in the dictionary.", "author": "Vidal Sassoon", "category": "work"},
    {"content": "I find that the harder I work, the more luck I seem to have.", "author": "Thomas Jefferson", "category": "work"},
    {"content": "Don't wish it were easier; wish you were better.", "author": "Jim Rohn", "category": "schedule"},
    {"content": "Education is the passport to the future, for tomorrow belongs to those who prepare for it today.", "author": "Malcolm X", "category": "study"},
    {"content": "It does not matter how slowly you go as long as you do not stop.", "author": "Confucius", "category": "study"},
    {"content": "The key to success is to focus on goals, not obstacles.", "author": "Brian Tracy", "category": "schedule"},
    {"content": "Excellence is not a destination; it is a continuous journey that never ends.", "author": "Brian Tracy", "category": "placement"},
]

async def _fetch_external_quote_api(tags: list | None = None):
    """Fetch quote from external API (Quotable API or Zenquotes)."""
    try:
        # Try Quotable API first (free, no auth needed)
        tags_str = ','.join(tags) if tags else ''
        url = 'https://api.quotable.io/random'
        if tags_str:
            url += f'?tags={tags_str}'
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        'content': data.get('content', ''),
                        'author': data.get('author', 'Unknown'),
                        'source': 'quotable_api',
                        'tags': data.get('tags', [])
                    }
    except Exception as e:
        print(f"Quotable API failed: {e}")
    
    try:
        # Fallback to Zenquotes API
        async with aiohttp.ClientSession() as session:
            async with session.get('https://zenquotes.io/api/random', timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data and isinstance(data, list) and len(data) > 0:
                        quote = data[0]
                        return {
                            'content': quote.get('q', ''),
                            'author': quote.get('a', 'Unknown').replace(', type.inspiration', ''),
                            'source': 'zenquotes_api'
                        }
    except Exception as e:
        print(f"Zenquotes API failed: {e}")
    
    return None

def _generate_contextual_quote_with_ai(module: str | None = None, task_data: dict | None = None):
    """Generate AI-based contextual quote using embeddings."""
    try:
        if not model:
            return None
        
        # Map module to key phrases
        module_prompts = {
            'schedule': 'productivity and time management',
            'study': 'learning and educational growth',
            'insights': 'personal growth and success',
            'placement': 'career development and professional excellence',
            'general': 'motivation and personal development'
        }
        
        prompt = module_prompts.get(module or 'general', 'motivation')
        
        # Get contextual text
        context_text = prompt
        if task_data:
            title = task_data.get('title', '')
            desc = task_data.get('description', '')
            category = task_data.get('category', '')
            context_text = f"{title} {desc} {category} {prompt}"
        
        # Use existing sentiment analysis to generate contextual quote
        context_embedding = model.encode(context_text)
        
        # Match against static quotes to find most relevant
        best_match = None
        best_score = -1
        
        for quote in FALLBACK_QUOTES:
            quote_embedding = model.encode(quote['content'])
            
            # Simple cosine similarity
            score = sum(a*b for a, b in zip(context_embedding, quote_embedding))
            score /= (sum(a*a for a in context_embedding) ** 0.5 * sum(b*b for b in quote_embedding) ** 0.5 + 1e-10)
            
            if score > best_score:
                best_score = score
                best_match = quote
        
        if best_match:
            return {
                **best_match,
                'source': 'ai_contextual',
                'relevance_score': round(float(best_score), 3)
            }
    except Exception as e:
        print(f"AI quote generation failed: {e}")
    
    return None

@app.get("/api/quote")
async def get_quote(module: str | None = None, use_ai: bool = False):
    """
    Return a motivational quote with multiple fallback strategies.
    
    Args:
        module: 'schedule', 'study', 'insights', 'placement', or 'general'
        use_ai: Force AI-based quote generation
    
    Fallback chain:
    1. External API (Quotable/Zenquotes) - for unique quotes
    2. AI-Generated contextual quote - personalized to module
    3. Static fallback quotes - guaranteed to work
    """
    
    print(f"📝 Quote endpoint called - module: {module}, use_ai: {use_ai}")
    
    # Ensure module is valid
    if module not in QUOTE_CACHE_TAGS and module:
        module = 'general'
    
    quote_result = None
    
    # Strategy 1: Try external API (unless explicitly using AI)
    if not use_ai:
        try:
            tags = QUOTE_CACHE_TAGS.get(module or 'general', [])
            external_quote = await _fetch_external_quote_api(tags)
            if external_quote:
                print(f"✅ Quote fetched from external API: {external_quote['source']}")
                return {
                    **external_quote,
                    'module': module or 'general',
                    'strategy': 'external_api'
                }
        except Exception as e:
            print(f"External API strategy failed: {e}")
    
    # Strategy 2: AI-Generated contextual quote
    try:
        if use_ai or model:
            ai_quote = _generate_contextual_quote_with_ai(module=module)
            if ai_quote:
                print(f"✅ Quote generated using AI")
                return {
                    **ai_quote,
                    'module': module or 'general',
                    'strategy': 'ai_contextual'
                }
    except Exception as e:
        print(f"AI quote strategy failed: {e}")
    
    # Strategy 3: Fallback to static quotes (filtered by module)
    try:
        if module and module in QUOTE_CACHE_TAGS:
            # Filter quotes by category
            filtered_quotes = [q for q in FALLBACK_QUOTES if q.get('category') == module]
            if not filtered_quotes:
                filtered_quotes = FALLBACK_QUOTES
        else:
            filtered_quotes = FALLBACK_QUOTES
        
        selected_quote = random.choice(filtered_quotes)
        print(f"✅ Quote selected from fallback list")
        return {
            'content': selected_quote['content'],
            'author': selected_quote['author'],
            'module': module or 'general',
            'strategy': 'fallback_static',
            'source': 'trackeneer_builtin'
        }
    except Exception as e:
        print(f"Fallback strategy failed: {e}")
        # Last resort - return a generic quote
        return {
            'content': "Success is the sum of small efforts, repeated day in and day out.",
            'author': "Robert Collier",
            'module': module or 'general',
            'strategy': 'hardcoded_fallback',
            'source': 'trackeneer_builtin'
        }

def _recommendations_for_topic(topic_detected: str):
    """Generate dynamic recommendations for a topic."""
    avg_dur = None
    texts = []
    
    try:
        with driver.session() as session:
            q = """
            MATCH (t:Task)
            WHERE t.status = 'pending' AND (
                toLower(coalesce(t.category, '')) = $topic OR
                toLower(coalesce(t.title, '')) CONTAINS $topic OR
                toLower(coalesce(t.description, '')) CONTAINS $topic)
            RETURN t.title AS title, t.description AS description, t.estimatedDuration AS est
            """
            res = session.run(q, topic=topic_detected)
            vals = []
            for r in res:
                title = r.get('title') or ''
                desc = r.get('description') or ''
                if title:
                    texts.append(str(title))
                if desc:
                    texts.append(str(desc))
                est = r.get('est')
                if est is not None:
                    try:
                        vals.append(int(est))
                    except Exception:
                        try:
                            vals.append(int(float(est)))
                        except Exception:
                            continue
            if vals:
                avg_dur = sum(vals) / len(vals)
    except Exception as e:
        print(f"Warning: could not gather task data: {e}")

    # Extract keywords
    keywords = []
    try:
        big_text = '\n'.join(texts)
        if big_text.strip():
            if nlp:
                doc = nlp(big_text)
                lemmas = [token.lemma_.lower() for token in doc if token.pos_ in ('NOUN', 'PROPN') and len(token.lemma_) > 2]
                freq = {}
                for l in lemmas:
                    freq[l] = freq.get(l, 0) + 1
                keywords = sorted(freq.keys(), key=lambda k: -freq[k])[:3]
            else:
                import re
                toks = re.findall(r"\w{3,}", big_text.lower())
                freq = {}
                for t in toks:
                    if t in ('the', 'and', 'for', 'with', 'that', 'this', 'project'):
                        continue
                    freq[t] = freq.get(t, 0) + 1
                keywords = sorted(freq.keys(), key=lambda k: -freq[k])[:3]
    except Exception as e:
        print(f"Keyword extraction failed: {e}")

    if not keywords:
        keywords = [topic_detected]

    # Choose templates based on topic
    if topic_detected and topic_detected.lower() in ('projects', 'project'):
        templates = ['implement {}', 'break {}', 'write {}']
    elif topic_detected and topic_detected.lower() in ('dsa', 'algorithms', 'data structure', 'algorithm'):
        templates = ['practice {}', 'review {}', 'mock {}']
    elif topic_detected and topic_detected.lower() in ('aptitude',):
        templates = ['timed {}', 'practice {}', 'review {}']
    else:
        templates = ['practice {}', 'read about {}', 'implement {}']

    action_scale = {'practice': 1.0, 'read': 0.6, 'implement': 1.5}

    recs = []
    for i, kw in enumerate(keywords):
        tmpl = templates[i % len(templates)]
        label = tmpl.format(kw)
        action = tmpl.split()[0]

        if topic_detected and kw and kw.lower() in (topic_detected.lower(), 'project', 'projects'):
            if action.lower() == 'practice':
                if 'implement {}' in templates:
                    label = ('implement {}').format(kw)
                    action = 'implement'
                else:
                    label = ('break {}').format(kw)
                    action = 'break'

        if avg_dur:
            est = max(5, int(round(avg_dur * action_scale.get(action, 1.0))))
        else:
            est = 30 if action == 'practice' else (20 if action == 'read' else 60)

        rec_type = action
        l = label.lower()
        if l.startswith('practice') or 'practice' in l or 'quiz' in l or 'mock' in l:
            rec_type = 'practice'
        elif l.startswith('read') or 'read' in l or 'study' in l or 'article' in l:
            rec_type = 'read'
        elif l.startswith('implement') or 'implement' in l or 'build' in l or 'project' in l:
            rec_type = 'implement'
        elif l.startswith('write') or 'write' in l or 'document' in l or 'readme' in l:
            rec_type = 'write'
        elif l.startswith('break') or 'break' in l:
            rec_type = 'break'

        confidence = 0.6
        recs.append({
            'label': label,
            'estimate_minutes': est,
            'type': rec_type,
            'confidence': round(confidence, 3)
        })

    return recs

@app.get('/api/recommend-tasks')
async def recommend_tasks(request: Request, topic: str | None = None, email: Optional[str] = None):
    try:
        forced = (topic or '').strip().lower() if topic else None
        # Prefer session cookie for authentication, fall back to header and default
        cookie_email = None
        cookie_token = request.cookies.get('trackeneer_session')
        if cookie_token:
            try:
                db = get_mongo_db()
                sess = db.sessions.find_one({'token': cookie_token})
                if sess:
                    exp = sess.get('expiresAt')
                    resolved_email = sess.get('email')
                    if exp:
                        try:
                            exp_dt = _parse_iso_to_dt(exp)
                            if exp_dt and exp_dt < datetime.utcnow():
                                resolved_email = None
                        except Exception:
                            pass
                    cookie_email = resolved_email
            except Exception as e:
                print(f"Warning: session lookup failed: {e}")

        header_email = request.headers.get('x-user-email') or request.headers.get('X-User-Email')
        preferred_email = email or cookie_email or header_email
        payload = {'email': preferred_email} if preferred_email else None
        user_email = _resolve_user_email(request, payload)

        # Ensure user/day nodes exist even if the topic is forced via query string
        with driver.session() as session:
            ensure_user_and_day(session, user_email)

        if forced:
            recs = _recommendations_for_topic(forced)
            return {'topic': forced, 'recommendations': recs}

        # Auto-detect topic
        with driver.session() as session:
            result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_TASK]->(t:Task)
                WHERE t.status='pending' AND t.description IS NOT NULL 
                RETURN t.description AS desc, t.title AS title 
                LIMIT 1
            """, email=user_email)
            seed = result.single()

        seed_text = ''
        if seed:
            seed_text = ((seed.get('title') or '') + '\n' + (seed.get('desc') or ''))[:512]

        topic_detected = None
        s = (seed_text or '').lower()
        if any(k in s for k in ['dsa', 'data structure', 'algorithm', 'leetcode', 'gfg']):
            topic_detected = 'dsa'
        elif any(k in s for k in ['aptitude', 'quant', 'logical', 'reasoning']):
            topic_detected = 'aptitude'
        elif any(k in s for k in ['system design', 'architecture', 'scalability']):
            topic_detected = 'system design'
        elif any(k in s for k in ['machine learning', 'ml', 'model', 'training']):
            topic_detected = 'machine learning'
        elif any(k in s for k in ['project', 'implement', 'build']):
            topic_detected = 'projects'
        else:
            topic_detected = 'general'

        if topic_detected and topic_detected.lower() in ('projects', 'project'):
            recs = []
            try:
                with driver.session() as session:
                    res = session.run("""
                        MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_TASK]->(t:Task)
                        WHERE toLower(coalesce(t.category,'')) CONTAINS 'project' 
                        OR toLower(coalesce(t.title,'')) CONTAINS 'project' 
                        RETURN t.id as id, t.title as title, t.estimatedDuration as est 
                        LIMIT 20
                    """, email=user_email)
                    rows = [r.data() for r in res]
                
                for r in rows:
                    tid = r.get('id')
                    title = r.get('title') or 'Untitled Project'
                    est = None
                    try:
                        est = int(r.get('est')) if r.get('est') is not None else None
                    except Exception:
                        try:
                            est = int(float(r.get('est')))
                        except Exception:
                            est = None
                    base = est or 60
                    plan = max(10, int(round(base * 0.2)))
                    implement = max(15, int(round(base * 0.6)))
                    verify = max(5, int(round(base * 0.2)))
                    recs.append({'label': f'Plan — {title}', 'type': 'plan', 'estimate_minutes': plan, 'taskId': tid, 'taskTitle': title})
                    recs.append({'label': f'Implement — {title}', 'type': 'implement', 'estimate_minutes': implement, 'taskId': tid, 'taskTitle': title})
                    recs.append({'label': f'Verify — {title}', 'type': 'verify', 'estimate_minutes': verify, 'taskId': tid, 'taskTitle': title})
            except Exception as e:
                print(f"Error generating project splits: {e}")
            return {'topic': topic_detected, 'recommendations': recs}

        short_recs = _recommendations_for_topic(topic_detected)
        return {'topic': topic_detected, 'recommendations': short_recs}
    except Exception as e:
        print(f"Error in recommend_tasks: {e}")
        raise HTTPException(status_code=500, detail='Could not generate topic recommendations.')

@app.get('/api/health')
async def api_health():
    """Health check endpoint."""
    try:
        return {
            'status': 'ok',
            'model_loaded': model is not None,
            'embed_model': EMBED_MODEL,
            'classifier_model_configured': bool(CLASSIFIER_MODEL),
            'classifier_model_loaded': classifier_model is not None,
            'skip_model_load_env': os.getenv('SKIP_MODEL_LOAD', '0') == '1',
            'cache_meta': CACHE_META
        }
    except Exception as e:
        print(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail='Health check failed')

def _priority_value(p):
    """Return numeric sort value for priority strings."""
    return {'high': 1, 'medium': 2, 'low': 3}.get(p, 2)

def _ai_scores(task):
    """Return AI-derived scores for urgency/importance."""
    if (not model and not classifier_model) or not label_prototypes:
        return None

    try:
        text = ((task.get('title') or '') + '\n' + (task.get('description') or ''))[:1024]
        if not text.strip():
            return None

        encoder = classifier_model or model
        emb = encoder.encode([text])[0]

        def cos(a, b):
            da = sum(x*x for x in a) ** 0.5
            db = sum(x*x for x in b) ** 0.5
            if da == 0 or db == 0:
                return 0.0
            return sum(x*y for x, y in zip(a, b)) / (da * db)

        u_score = max(0.0, cos(emb, label_prototypes.get('urgent', emb)))
        i_score = max(0.0, cos(emb, label_prototypes.get('important', emb)))
        return {'urgent': float(u_score), 'important': float(i_score)}
    except Exception as e:
        print(f"AI scoring failed: {e}")
        return None

def _overlaps(a_start, a_end, b_start, b_end):
    """Check if two datetime intervals overlap."""
    try:
        a_s = _parse_iso_to_dt(a_start)
        a_e = _parse_iso_to_dt(a_end)
        b_s = _parse_iso_to_dt(b_start)
        b_e = _parse_iso_to_dt(b_end)
        if not a_s or not a_e or not b_s or not b_e:
            return False
        return not (a_e <= b_s or b_e <= a_s)
    except Exception:
        return False

def _partial_order_plan(items):
    """Order items by urgency/importance/deadline."""
    def key_fn(it):
        ai_u = (it.get('ai_scores') or {}).get('urgent', 0.0)
        ai_i = (it.get('ai_scores') or {}).get('important', 0.0)
        pval = _priority_value(it.get('priority'))
        dl = _parse_iso_to_dt(it.get('deadline'))
        dl_sort = dl if dl else datetime.max
        return (-ai_u, -ai_i, dl_sort, pval)
    return sorted(items, key=key_fn)

def _greedy_by_deadline(items, max_horizon=None):
    """Greedy schedule by earliest deadline."""
    scheduled = []
    def key_deadline(it):
        dl = _parse_iso_to_dt(it.get('deadline'))
        dl_sort = dl if dl else datetime.max
        return (dl_sort, _priority_value(it.get('priority')))

    candidates = sorted(items, key=key_deadline)
    for c in candidates:
        conflict = False
        for s in scheduled:
            if _overlaps(c.get('startTime'), c.get('endTime'), s.get('startTime'), s.get('endTime')):
                conflict = True
                break
        if not conflict:
            scheduled.append(c)
    return scheduled

def _predictive_schedule(tasks, horizon_days: int = 7):
    """Create predictive schedule for next horizon_days."""
    now = datetime.utcnow()
    horizon_end = now + timedelta(days=horizon_days)

    pred_map = {}
    try:
        with driver.session() as session:
            rels = session.run("""
                MATCH (a:Task)-[:FINISH_TO_START]->(b:Task) 
                RETURN a.id AS a, b.id AS b
            """)
            for r in rels:
                d = r.data()
                pred_map.setdefault(d['a'], []).append(d['b'])
    except Exception:
        pred_map = {}

    def get_est(it):
        try:
            return int(it.get('estimatedDuration') or it.get('estimated_duration') or 30)
        except Exception:
            return 30

    def sort_key(it):
        dl = _parse_iso_to_dt(it.get('dueDate') or it.get('endTime') or it.get('startTime'))
        dl_sort = dl if dl else datetime.max
        p = _priority_value(it.get('priority'))
        scores = _ai_scores(it) or {'urgent': 0.0, 'important': 0.0}
        return (dl_sort, p, -scores.get('urgent', 0.0), -scores.get('important', 0.0))

    tasks_sorted = sorted(tasks, key=sort_key)
    scheduled = []
    calendar = []

    for t in tasks_sorted:
        s = _parse_iso_to_dt(t.get('startTime'))
        e = _parse_iso_to_dt(t.get('endTime'))
        if s and e:
            calendar.append((s, e))

    def find_slot(duration_minutes, earliest=None):
        if earliest is None:
            earliest = now
        candidate_start = earliest
        step = timedelta(minutes=15)
        dur = timedelta(minutes=duration_minutes)
        
        while candidate_start + dur <= horizon_end:
            candidate_end = candidate_start + dur
            overlap = False
            for (as_, ae) in calendar:
                if not (candidate_end <= as_ or candidate_start >= ae):
                    overlap = True
                    break
            if not overlap:
                calendar.append((candidate_start, candidate_end))
                return candidate_start, candidate_end
            candidate_start = candidate_start + step
        return None, None

    placed = set()
    for t in tasks_sorted:
        tid = t.get('id')
        if tid in placed:
            continue

        preds = [k for k, vs in pred_map.items() if tid in vs]
        earliest = now
        for p in preds:
            p_end = None
            for s in scheduled:
                if s['id'] == p:
                    p_end = _parse_iso_to_dt(s.get('end'))
                    break
            if p_end and p_end > earliest:
                earliest = p_end + timedelta(minutes=5)

        est = get_est(t)
        s_start, s_end = find_slot(est, earliest)
        if s_start and s_end:
            scheduled.append({
                'id': tid,
                'title': t.get('title'),
                'start': s_start.isoformat(),
                'end': s_end.isoformat(),
                'estimate_minutes': est
            })
            placed.add(tid)

    return scheduled

@app.get('/api/schedule/predictive')
async def api_predictive_schedule(horizon_days: int = 7, limit: int = 50):
    """Return predictive schedule."""
    try:
        with driver.session() as session:
            res = session.run("MATCH (t:Task) WHERE t.status='pending' RETURN t LIMIT $lim", lim=limit)
            tasks = [neo4j_to_serializable(r['t']) for r in res]

        sched = _predictive_schedule(tasks, horizon_days=horizon_days)
        return JSONResponse(content={'scheduled': sched}, status_code=200)
    except Exception as e:
        print(f"Error in api_predictive_schedule: {e}")
        raise HTTPException(status_code=500, detail='Could not compute predictive schedule')

def _is_urgent(task):
    """Check if task is urgent."""
    try:
        title = (task.get('title') or '')
        desc = (task.get('description') or '')
        text = (title + ' ' + desc).lower()
        urgent_keywords = ['urgent', 'asap', 'immediately', 'due', 'deadline', 'today', 'now', 'critical']
        if any(k in text for k in urgent_keywords):
            return True

        due = _parse_iso_to_dt(task.get('dueDate') or task.get('endTime') or task.get('startTime'))
        if due:
            try:
                if due <= datetime.utcnow() + timedelta(hours=24):
                    return True
            except Exception:
                pass

        try:
            scores = _ai_scores(task)
            if scores and scores.get('urgent') and scores['urgent'] >= 0.6:
                return True
        except Exception:
            pass

        return False
    except Exception:
        return False

def _is_important(task):
    """Check if task is important."""
    try:
        p = (task.get('priority') or '').lower()
        if p == 'high':
            return True

        cat = (task.get('category') or '').lower()
        if cat in ['work', 'education', 'health', 'finance']:
            return True

        text = ((task.get('title') or '') + ' ' + (task.get('description') or '')).lower()
        important_keywords = ['exam', 'interview', 'project', 'milestone', 'payment', 'important', 'deadline']
        if any(k in text for k in important_keywords):
            return True

        try:
            scores = _ai_scores(task)
            if scores and scores.get('important') and scores['important'] >= 0.6:
                return True
        except Exception:
            pass

        return False
    except Exception:
        return False

@app.get('/api/schedule/eisenhower')
async def api_eisenhower_schedule(request: Request, max: int | None = None, email: Optional[str] = None):
    """Return Eisenhower matrix schedule."""
    try:
        user_email = _resolve_user_email(request, {'email': email} if email else None)
        quadrants, prioritized_final = _compute_eisenhower_quadrants(max_items=max, email=user_email)
        return JSONResponse(content={
            'quadrants': quadrants,
            'prioritized': prioritized_final
        }, status_code=200)
    except Exception as e:
        print(f"Error in api_eisenhower_schedule: {e}")
        return JSONResponse(content={'error': 'Could not compute Eisenhower schedule'}, status_code=500)


def _compute_eisenhower_quadrants(max_items: int | None = None, *, email: Optional[str] = None):
    """Compute Eisenhower quadrants and return (quadrants_dict, prioritized_list).

    This function encapsulates the logic previously in the endpoint so it can be
    reused by other endpoints. It returns:
      - quadrants: dict mapping quadrant name -> list of enriched items
      - prioritized_final: final prioritized/scheduled list (possibly truncated)
    """
    max_items = max_items
    with driver.session() as session:
        active_email = email or DEFAULT_USER_EMAIL
        ensure_user_and_day(session, active_email)
        result = session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_TASK]->(t:Task)
            WHERE t.status = 'pending'
            RETURN t
            """,
            email=active_email,
        )
        tasks = [neo4j_to_serializable(r['t']) for r in result]
        print(f"📊 Eisenhower helper - Found {len(tasks)} pending tasks")

    quadrants = {
        "Do Now (Q1)": [],
        "Schedule (Q2)": [],
        "Delegate (Q3)": [],
        "Eliminate (Q4)": []
    }

    enriched = []
    for t in tasks:
        try:
            task_obj = {k: neo4j_to_serializable(v) for k, v in t.items()} if hasattr(t, 'items') else dict(t)
            ai_scores = _ai_scores(task_obj) or {'urgent': 0.0, 'important': 0.0}
            urgent = _is_urgent(task_obj)
            important = _is_important(task_obj)

            if urgent and important:
                qname = "Do Now (Q1)"
            elif (not urgent) and important:
                qname = "Schedule (Q2)"
            elif urgent and (not important):
                qname = "Delegate (Q3)"
            else:
                qname = "Eliminate (Q4)"

            deadline = _parse_iso_to_dt(task_obj.get('dueDate') or task_obj.get('endTime') or task_obj.get('startTime'))

            enriched_item = {
                'id': task_obj.get('id'),
                'title': task_obj.get('title'),
                'description': task_obj.get('description'),
                'priority': task_obj.get('priority'),
                'category': task_obj.get('category'),
                'deadline': deadline.isoformat() if deadline else None,
                'startTime': task_obj.get('startTime'),
                'endTime': task_obj.get('endTime'),
                'urgent': urgent,
                'important': important,
                'ai_scores': ai_scores,
                'quadrant': qname
            }

            quadrants[qname].append(enriched_item)
            enriched.append(enriched_item)
        except Exception as task_e:
            print(f"Error processing task (skipping): {task_e}")
            continue

    def sort_key(item):
        d = item.get('deadline')
        try:
            dt = _parse_iso_to_dt(d) if d else None
            dt_sort = dt if dt else datetime.max
        except Exception:
            dt_sort = datetime.max
        return (dt_sort, _priority_value(item.get('priority')))

    for k in quadrants:
        quadrants[k] = sorted(quadrants[k], key=sort_key)

    order = ["Do Now (Q1)", "Schedule (Q2)", "Delegate (Q3)", "Eliminate (Q4)"]
    prioritized = []
    for name in order:
        prioritized.extend(quadrants.get(name, []))

    if max_items:
        prioritized = prioritized[:max_items]

    for item in prioritized:
        q = item.get('quadrant')
        if q == 'Do Now (Q1)':
            item['suggested'] = 'Do immediately'
        elif q == 'Schedule (Q2)':
            item['suggested'] = 'Schedule on calendar'
        elif q == 'Delegate (Q3)':
            item['suggested'] = 'Delegate to someone'
        else:
            item['suggested'] = 'Consider dropping'

    try:
        reordered = _partial_order_plan(prioritized)
        scheduled = _greedy_by_deadline(reordered)
        
        if max_items and len(scheduled) < max_items:
            for it in reordered:
                if it not in scheduled:
                    scheduled.append(it)
                if len(scheduled) >= max_items:
                    break

        prioritized_final = scheduled if scheduled else prioritized
    except Exception as e:
        print(f"Warning: scheduling refinement failed: {e}")
        prioritized_final = prioritized

    return quadrants, prioritized_final


@app.get('/api/schedule/eisenhower/matrix')
async def api_eisenhower_matrix(request: Request, email: Optional[str] = None):
    """Return a concise Eisenhower matrix summary (counts + brief task list per quadrant)."""
    try:
        user_email = _resolve_user_email(request, {'email': email} if email else None)
        quadrants, _ = _compute_eisenhower_quadrants(max_items=None, email=user_email)
        matrix_summary = {}
        for k, items in quadrants.items():
            matrix_summary[k] = {
                'count': len(items),
                'tasks': [{'id': it.get('id'), 'title': it.get('title'), 'deadline': it.get('deadline')} for it in items[:10]]
            }
        return JSONResponse(content={'matrix': matrix_summary}, status_code=200)
    except Exception as e:
        print(f"Error in api_eisenhower_matrix: {e}")
        raise HTTPException(status_code=500, detail='Could not compute Eisenhower matrix')

# --- Authentication Endpoints ---
@app.post('/api/auth/login')
async def api_login(request: Request, response: Response):
    try:
        data = await request.json()
        email = data.get('email')
        password = data.get('password')
        if not email or not password:
            raise HTTPException(status_code=400, detail='Missing credentials')

        with driver.session() as session:
            result = session.run("""
                MATCH (u:User {email: $email, password: $password}) 
                RETURN u
            """, email=email, password=password)
            rec = result.single()
            if not rec:
                raise HTTPException(status_code=401, detail='Invalid credentials')

            user = rec['u']

            user_obj = {k: neo4j_to_serializable(v) for k, v in dict(user).items()} if hasattr(user, 'items') else dict(user)


            # Create a server-side session token stored in Mongo and set an HttpOnly cookie
            try:
                db = get_mongo_db()
                sessions = db.sessions
                token = uuid.uuid4().hex
                expires_at = (datetime.utcnow() + timedelta(days=7)).isoformat()
                sessions.insert_one({
                    'token': token,
                    'userId': user_obj.get('id'),
                    'email': user_obj.get('email'),
                    'createdAt': datetime.utcnow().isoformat(),
                    'expiresAt': expires_at
                })
                response.set_cookie(
                    'trackeneer_session',
                    token,
                    httponly=True,
                    samesite='lax',
                    path='/',
                    max_age=7 * 24 * 3600,
                )
            except Exception as e:
                print(f"Warning: could not create server session: {e}")


            touch_user_login(session, email=email, name=str(user_obj.get('name') or ''))
            ensure_user_and_day(session, email=email, name=str(user_obj.get('name') or ''))

            return {
                'id': user_obj.get('id'),
                'name': user_obj.get('name'),
                'email': user_obj.get('email')
            }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in api_login: {e}")
        raise HTTPException(status_code=500, detail='Internal error')

@app.get('/api/auth/me')
async def api_me(request: Request):
    """Return current user info."""
    try:

        email_candidate = request.headers.get('x-user-email') or request.headers.get('X-User-Email')
        payload = {'email': email_candidate} if email_candidate else None
        user_email = _resolve_user_email(request, payload)

        # Prefer session cookie for authentication, fall back to header

        # Prefer server-side session cookie if available, then fall back to headers/default
        cookie_email: Optional[str] = None

        cookie_token = request.cookies.get('trackeneer_session')
        if cookie_token:
            try:
                db = get_mongo_db()
                sess = db.sessions.find_one({'token': cookie_token})
                if sess:
                    resolved_email = sess.get('email')
                    exp = sess.get('expiresAt')
                    if exp:
                        try:
                            exp_dt = _parse_iso_to_dt(exp)
                            if exp_dt and exp_dt < datetime.utcnow():
                                resolved_email = None
                        except Exception:
                            pass
                    cookie_email = resolved_email
            except Exception as e:
                print(f"Warning: session lookup failed: {e}")


        header_email = request.headers.get('x-user-email') or request.headers.get('X-User-Email')
        preferred_email = cookie_email or header_email
        payload = {'email': preferred_email} if preferred_email else None
        user_email = _resolve_user_email(request, payload)


        with driver.session() as session:
            ensure_user_and_day(session, user_email)
            rec = session.run("MATCH (u:User {email: $email}) RETURN u", email=user_email).single()

        if not rec:
            return {'id': None, 'name': 'Guest', 'email': user_email}

        user = rec['u']
        user_obj = {k: neo4j_to_serializable(v) for k, v in dict(user).items()} if hasattr(user, 'items') else dict(user)
        return {
            'id': user_obj.get('id'),
            'name': user_obj.get('name') or user_obj.get('email') or 'User',
            'email': user_obj.get('email')
        }
    except Exception as e:
        print(f"Error in api_me: {e}")
        raise HTTPException(status_code=500, detail='Internal error')


@app.get('/api/auth/exists')
async def api_user_exists(email: str | None = None):
    """Return whether a user with the given email exists in Mongo (fast check for OAuth flows)."""
    try:
        if not email:
            raise HTTPException(status_code=400, detail='Missing email')
        db = get_mongo_db()
        users = db.users
        exists = users.find_one({'email': email}) is not None
        return {'exists': bool(exists)}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in api_user_exists: {e}")
        raise HTTPException(status_code=500, detail='Internal error')

@app.post('/api/auth/signup')
async def api_signup(request: Request):
    try:
        data = await request.json()
        name = data.get('name')
        email = data.get('email')
        password = data.get('password')
        if not name or not email or not password:
            raise HTTPException(status_code=400, detail='Missing fields')

        # Persist user in MongoDB (for auth and basic profile)
        user_id = str(uuid.uuid4())
        db = get_mongo_db()
        try:
            users = db.users
            if users.find_one({'email': email}):
                raise HTTPException(status_code=409, detail='User already exists')

            # simple sha256 hashing (replace with bcrypt for production)
            pwd_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
            users.insert_one({
                'id': user_id,
                'name': name,
                'email': email,
                'password': pwd_hash,
                'createdAt': datetime.utcnow().isoformat()
            })
        except PyMongoError as me:
            print(f"MongoDB error: {me}")
            raise HTTPException(status_code=500, detail='Could not save user')

        # Create a Neo4j user node (and a profile node placeholder for career info)
        try:
            with driver.session() as session:
                session.run(
                    """
                    CREATE (u:User {id:$id, name:$name, email:$email, createdAt: datetime()})
                    CREATE (p:Profile {careerGoal: '', weaknesses: '', challenges: '', wantsHelp: ''})
                    CREATE (u)-[:HAS_PROFILE]->(p)
                    """,
                    id=user_id, name=name, email=email,
                )
                touch_user_login(session, email=email, name=name)
                ensure_user_and_day(session, email=email, name=name)
        except Exception as e:
            print(f"Warning: could not create Neo4j user/profile: {e}")

        return JSONResponse(status_code=201, content={'message': 'User created', 'id': user_id})
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in api_signup: {e}")
        raise HTTPException(status_code=500, detail='Internal error')


@app.post('/api/auth/register')
async def api_register(
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    branch: str = Form(...),
    year: str = Form(...),
    career_goal: str | None = Form(None),
    weaknesses: str | None = Form(None),
    challenges: str | None = Form(None),
    wants_help: str | None = Form(None),
    resume: UploadFile | None = File(None),
):
    """Full registration endpoint that:
    - stores auth/basic profile in MongoDB
    - stores career/profile info in Neo4j
    - saves uploaded resume to local storage
    """
    try:
        db = get_mongo_db()
        users = db.users
        if users.find_one({'email': email}):
            raise HTTPException(status_code=409, detail='User already exists')

        user_id = str(uuid.uuid4())
        pwd_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
        users.insert_one({
            'id': user_id,
            'name': name,
            'email': email,
            'password': pwd_hash,
            'branch': branch,
            'year': year,
            'createdAt': datetime.utcnow().isoformat(),
        })

        # Save resume if provided
        stored_filename = None
        if resume:
            dest_dir = Path(os.path.join(os.path.dirname(__file__), 'uploads', 'resumes'))
            dest_dir.mkdir(parents=True, exist_ok=True)
            stored_filename = f"{user_id}_{resume.filename}"
            dest_path = dest_dir / stored_filename
            with open(dest_path, 'wb') as fh:
                fh.write(await resume.read())
            # update mongo record with resume info
            users.update_one({'id': user_id}, {'$set': {'resume': {'filename': resume.filename, 'storedFilename': str(stored_filename)}}})

        # Create or update Neo4j user and attach/update profile info (use MERGE on email to avoid duplicates)
        with driver.session() as session:
            session.run(
                """
                MERGE (u:User {email:$email})
                ON CREATE SET u.id = $id, u.name = $name, u.createdAt = datetime()
                MERGE (p:Profile {userEmail:$email})
                SET p.careerGoal = $career_goal, p.weaknesses = $weaknesses, p.challenges = $challenges, p.wantsHelp = $wants_help
                MERGE (u)-[:HAS_PROFILE]->(p)
                """,
                id=user_id, name=name, email=email,
                career_goal=career_goal or '', weaknesses=weaknesses or '', challenges=challenges or '', wants_help=wants_help or '',
            )

        return JSONResponse(status_code=201, content={'message': 'User registered', 'id': user_id})
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in api_register: {e}")
        raise HTTPException(status_code=500, detail='Registration failed')


@app.post('/api/auth/oauth-register')
async def api_oauth_register(
    response: Response,
    name: str = Form(...),
    email: str = Form(...),
    branch: str | None = Form(None),
    year: str | None = Form(None),
    career_goal: str | None = Form(None),
    weaknesses: str | None = Form(None),
    challenges: str | None = Form(None),
    wants_help: str | None = Form(None),
    resume: UploadFile | None = File(None),
):
    """Register an OAuth user after OAuth step. Password is auto-generated and stored as hash.
    Fields from OAuth (name,email) are used; additional profile fields and resume are saved here.
    """
    try:
        db = get_mongo_db()
        users = db.users
        existing = users.find_one({'email': email})
        if existing:
            # update profile info if provided (only set fields that are non-empty)
            update_fields = {}
            if branch:
                update_fields['branch'] = branch
            if year:
                update_fields['year'] = year
            if update_fields:
                users.update_one({'email': email}, {'$set': update_fields})
            user_id = existing['id']
        else:
            user_id = str(uuid.uuid4())
            # generate a random password token and store its hash
            token = uuid.uuid4().hex
            pwd_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
            users.insert_one({
                'id': user_id,
                'name': name,
                'email': email,
                'password': pwd_hash,
                'branch': branch or '',
                'year': year or '',
                'createdAt': datetime.utcnow().isoformat(),
            })

        # resume
        stored_filename = None
        if resume:
            dest_dir = Path(os.path.join(os.path.dirname(__file__), 'uploads', 'resumes'))
            dest_dir.mkdir(parents=True, exist_ok=True)
            stored_filename = f"{user_id}_{resume.filename}"
            dest_path = dest_dir / stored_filename
            with open(dest_path, 'wb') as fh:
                fh.write(await resume.read())
            users.update_one({'id': user_id}, {'$set': {'resume': {'filename': resume.filename, 'storedFilename': str(stored_filename)}}})

        # create or update neo4j profile
        with driver.session() as session:
            session.run(
                """
                MERGE (u:User {email:$email})
                ON CREATE SET u.id = $id, u.name = $name, u.createdAt = datetime()
                MERGE (p:Profile {userEmail:$email})
                SET p.careerGoal = $career_goal, p.weaknesses = $weaknesses, p.challenges = $challenges, p.wantsHelp = $wants_help
                MERGE (u)-[:HAS_PROFILE]->(p)
                """,
                id=user_id, name=name, email=email,
                career_goal=career_goal or '', weaknesses=weaknesses or '', challenges=challenges or '', wants_help=wants_help or '',
            )

            # Create a server-side session and set an HttpOnly cookie so OAuth users
            # are logged in immediately after completing the OAuth registration/flow.
            try:
                db = get_mongo_db()
                sessions = db.sessions
                token = uuid.uuid4().hex
                expires_at = (datetime.utcnow() + timedelta(days=7)).isoformat()
                sessions.insert_one({
                    'token': token,
                    'userId': user_id,
                    'email': email,
                    'createdAt': datetime.utcnow().isoformat(),
                    'expiresAt': expires_at
                })
                response.set_cookie('trackeneer_session', token, httponly=True, samesite='lax', path='/', max_age=7*24*3600)
            except Exception as e:
                print(f"Warning: could not create server session for oauth user: {e}")

            return JSONResponse(status_code=201, content={'message': 'OAuth user registered', 'id': user_id})
    except Exception as e:
        print(f"Error in api_oauth_register: {e}")
        raise HTTPException(status_code=500, detail='OAuth registration failed')


@app.post('/api/auth/logout')
async def api_logout(request: Request, response: Response):
    """Logout endpoint: removes server-side session and clears cookie."""
    try:
        cookie_token = request.cookies.get('trackeneer_session')
        if cookie_token:
            try:
                db = get_mongo_db()
                db.sessions.delete_many({'token': cookie_token})
            except Exception as e:
                print(f"Warning: could not delete session from DB: {e}")
        # clear cookie
        response.delete_cookie('trackeneer_session', path='/')
        return {'message': 'Logged out'}
    except Exception as e:
        print(f"Error in api_logout: {e}")
        raise HTTPException(status_code=500, detail='Logout failed')

@app.post('/api/auth/forgot-password')
async def api_forgot_password(request: Request):
    try:
        data = await request.json() or {}
        email = data.get('email')
        smtp_user = os.getenv('SMTP_USER')
        
        if not email:
            if smtp_user:
                email = smtp_user
            else:
                raise HTTPException(status_code=400, detail='Missing email')

        with driver.session() as session:
            session.run("""
                MERGE (u:User {email: $email})
                    ON CREATE SET u.id = randomUUID(), u.createdAt = datetime()
            """, email=email)
            touch_user_login(session, email=email)
            ensure_user_and_day(session, email=email)
            
            otp = str(random.randint(100000, 999999))
            expiry = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
            session.run("""
                MATCH (u:User {email: $email}) 
                SET u.otp = $otp, u.otpExpiry = $expiry
            """, email=email, otp=otp, expiry=expiry)

        smtp_host = os.getenv('SMTP_HOST')
        smtp_port = int(os.getenv('SMTP_PORT', '587'))
        smtp_user = os.getenv('SMTP_USER')
        smtp_pass = os.getenv('SMTP_PASS')
        email_from = os.getenv('EMAIL_FROM', smtp_user)

        if email_from and '@' in email_from and '<' not in email_from:
            if ' ' in email_from:
                parts = email_from.rsplit(' ', 1)
                display = parts[0].strip()
                addr = parts[1].strip()
                email_from = f"{display} <{addr}>"
            else:
                email_from = f"TrackEneer <{email_from}>"

        email_sent = False
        if smtp_host and smtp_user and smtp_pass:
            try:
                msg = EmailMessage()
                msg['Subject'] = 'TrackEneer Password Reset OTP'
                msg['From'] = email_from
                msg['To'] = email
                msg.set_content(f"Your TrackEneer password reset code is: {otp}\nThis code expires in 10 minutes.")

                with smtplib.SMTP(smtp_host, smtp_port) as server:
                    server.starttls()
                    server.login(smtp_user, smtp_pass)
                    server.send_message(msg)
                email_sent = True
            except Exception as e:
                print(f"Error sending OTP email: {e}")

        if email_sent:
            return {'message': 'OTP generated and sent to email'}
        else:
            print(f"OTP for {email}: {otp} (expires {expiry})")
            return {
                'message': 'OTP generated (dev mode - SMTP not configured)',
                'otpHint': 'OTP printed to server logs for dev'
            }
    except Exception as e:
        print(f"Error in api_forgot_password: {e}")
        raise HTTPException(status_code=500, detail='Internal error')

@app.post('/api/auth/reset-password')
async def api_reset_password(request: Request):
    try:
        data = await request.json()
        email = data.get('email')
        otp = data.get('otp')
        new_password = data.get('newPassword')
        
        if not email or not otp or not new_password:
            raise HTTPException(status_code=400, detail='Missing fields')

        with driver.session() as session:
            rec = session.run("MATCH (u:User {email: $email}) RETURN u", email=email).single()
            if not rec:
                raise HTTPException(status_code=404, detail='User not found')

            user = rec['u']
            user_obj = {k: neo4j_to_serializable(v) for k,v in dict(user).items()} if hasattr(user, 'items') else dict(user)
            stored_otp = user_obj.get('otp')
            otp_expiry = user_obj.get('otpExpiry')

            if not stored_otp or stored_otp != str(otp):
                raise HTTPException(status_code=401, detail='Invalid OTP')

            if otp_expiry:
                try:
                    exp_dt = datetime.fromisoformat(str(otp_expiry))
                    if datetime.utcnow() > exp_dt:
                        raise HTTPException(status_code=410, detail='OTP expired')
                except HTTPException:
                    raise
                except Exception:
                    pass

            session.run("""
                MATCH (u:User {email: $email}) 
                SET u.password = $pw 
                REMOVE u.otp, u.otpExpiry
            """, email=email, pw=new_password)
            touch_user_login(session, email=email)
            ensure_user_and_day(session, email=email)

        return {'message': 'Password reset successful'}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in api_reset_password: {e}")
        raise HTTPException(status_code=500, detail='Internal error')

# --- WebSocket and Notification Endpoints ---
@app.websocket('/ws/notifications')
async def websocket_notifications(ws: WebSocket):
    """WebSocket endpoint for push notifications."""
    await ws.accept()
    connected_webs.add(ws)
    print("WebSocket client connected. Total:", len(connected_webs))
    
    try:
        while True:
            msg = await ws.receive_text()
            try:
                await ws.send_text(json.dumps({'type': 'ack', 'payload': msg}))
            except Exception:
                pass
    except WebSocketDisconnect:
        print('WebSocket client disconnected')
        try:
            connected_webs.discard(ws)
        except Exception:
            pass
    except Exception as e:
        print(f"WebSocket error: {e}")
        try:
            connected_webs.discard(ws)
        except Exception:
            pass

@app.post('/api/notifications/subscribe')
async def api_notifications_subscribe(request: Request):
    """Subscribe user to notifications."""
    try:
        data = await request.json()
        user_id = data.get('userId')
        if not user_id:
            raise HTTPException(status_code=400, detail='Missing userId')
        return {'message': 'Subscription successful', 'userId': user_id}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in api_notifications_subscribe: {e}")
        raise HTTPException(status_code=500, detail='Internal error')

@app.post('/api/notifications/mark-sent')
async def api_notifications_mark_sent(request: Request):
    """Mark notification as sent."""
    try:
        data = await request.json()
        nid = data.get('notificationId')
        if not nid:
            raise HTTPException(status_code=400, detail='notificationId is required')

        try:
            NOTIFIED_TASK_KEYS.add(str(nid))
            print(f"🔕 Marked notification as sent: {nid}")
        except Exception as e:
            print(f"Warning: could not mark notification: {e}")

        return {'success': True, 'notificationId': nid}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in api_notifications_mark_sent: {e}")
        raise HTTPException(status_code=500, detail='Internal error')

@app.get('/api/notifications/pending')
async def api_notifications_pending(request: Request, email: Optional[str] = None):
    """Get pending notifications with IST timezone support (user-scoped)."""
    try:
        user_email = _resolve_user_email(request, {'email': email} if email else None)
        now_utc = datetime.now(timezone.utc)
        now_ist = now_utc.astimezone(IST)
        
        notifications = []
        
        with driver.session() as session:
            result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_TASK]->(t:Task)
                WHERE t.status = 'pending' 
                AND t.startTime IS NOT NULL
                AND datetime(t.startTime) > datetime()
                AND datetime(t.startTime) <= datetime() + duration({minutes: 15})
                RETURN t.id AS id, t.title AS title, t.startTime AS startTime, 
                       'start' AS type
                ORDER BY t.startTime
                LIMIT 20
            """, email=user_email)
            
            for record in result:
                start_time = record['startTime']
                if isinstance(start_time, DateTime):
                    start_dt = start_time.to_native()
                else:
                    start_dt = datetime.fromisoformat(str(start_time))
                
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                start_ist = start_dt.astimezone(IST)
                
                time_diff = start_ist - now_ist
                minutes_until = int(time_diff.total_seconds() / 60)
                
                if minutes_until > 0 and minutes_until <= 15:
                    notifications.append({
                        'id': f"start-{record['id']}",
                        'title': record['title'],
                        'type': 'start',
                        'minutesUntil': minutes_until,
                        'scheduledTime': start_ist.strftime('%I:%M %p IST')
                    })
            
            result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_TASK]->(t:Task)
                WHERE t.status = 'pending' 
                AND t.dueDate IS NOT NULL
                RETURN t.id AS id, t.title AS title, t.dueDate AS dueDate,
                       'due' AS type
                ORDER BY t.dueDate
                LIMIT 50
            """, email=user_email)
            
            for record in result:
                due_date = record['dueDate']
                try:
                    if isinstance(due_date, Date):
                        due_dt = datetime.combine(
                            due_date.to_native(),
                            datetime.max.time()
                        ).replace(tzinfo=IST)
                    elif isinstance(due_date, DateTime):
                        due_dt = due_date.to_native()
                        if due_dt.tzinfo is None:
                            due_dt = due_dt.replace(tzinfo=timezone.utc)
                        due_dt = due_dt.astimezone(IST)
                    else:
                        due_dt = datetime.fromisoformat(str(due_date))
                        if due_dt.tzinfo is None:
                            due_dt = due_dt.replace(tzinfo=IST)
                    
                    time_diff = due_dt - now_ist
                    minutes_until = int(time_diff.total_seconds() / 60)
                    
                    if -60 <= minutes_until <= 1440:
                        notifications.append({
                            'id': f"due-{record['id']}",
                            'title': record['title'],
                            'type': 'due',
                            'minutesUntil': minutes_until,
                            'dueTime': due_dt.strftime('%I:%M %p IST')
                        })
                except Exception as e:
                    print(f"Error processing due date for task {record['id']}: {e}")
                    continue
        
        filtered_notifications = [n for n in notifications if n['id'] not in NOTIFIED_TASK_KEYS]
        print(f"📬 Returning {len(filtered_notifications)} notifications (IST) - filtered from {len(notifications)} total")
        return {
            'notifications': filtered_notifications,
            'currentTime': now_ist.strftime('%I:%M %p IST')
        }
    except Exception as e:
        print(f"Error in api_notifications_pending: {e}")
        raise HTTPException(status_code=500, detail='Internal error')

@app.get('/api/debug/tasks')
async def debug_tasks():
    """Debug endpoint to check all tasks."""
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (t:Task) 
                RETURN t.id as id, t.title as title, t.status as status, 
                       t.startTime as startTime, t.createdAt as createdAt
                ORDER BY t.createdAt DESC
                LIMIT 20
            """)
            tasks = [dict(r) for r in result]
            
            count_result = session.run("MATCH (t:Task) RETURN count(t) as total")
            count_row = count_result.single()
            total = count_row['total'] if count_row else 0
            
            pending_result = session.run("""
                MATCH (t:Task) 
                WHERE t.status = 'pending' 
                RETURN count(t) as count
            """)
            pending_row = pending_result.single()
            pending = pending_row['count'] if pending_row else 0
            
            today = datetime.now(IST).date()
            today_result = session.run("""
                MATCH (:Day {date: date($d)})-[:HAS_TASK]->(t:Task) 
                RETURN count(t) as count
            """, d=today)
            today_row = today_result.single()
            today_count = today_row['count'] if today_row else 0
        
        return {
            'total_tasks': total,
            'pending_tasks': pending,
            'today_tasks': today_count,
            'today_date': str(today),
            'recent_tasks': tasks
        }
    except Exception as e:
        print(f"Error in debug endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Vector DB Population ---
def populate_vector_db():
    """Populate vector database with task embeddings."""
    if model is None:
        print("Skipping vector DB population — embedding model not loaded.")
        return

    with driver.session() as session:
        results = session.run("""
            MATCH (t:Task) 
            WHERE t.description IS NOT NULL 
            RETURN t.id AS id, t.description AS description
        """)
        all_tasks = [r.data() for r in results]

    if all_tasks:
        ids = [t['id'] for t in all_tasks]
        descs = [t['description'] for t in all_tasks]
        vector_db.upsert(ids=ids, embeddings=model.encode(descs).tolist())
        print(f"Vector DB populated with {len(ids)} tasks.")


# ============================================================================
# DOCUMENT UPLOAD & TIMETABLE GENERATION ENDPOINTS
# ============================================================================

# In-memory storage for user document paths (in production, use database)
USER_DOCUMENTS = {}  # email -> {syllabus: path, calendar: path, exam_timetable: path}
USER_CONSTRAINTS = {}  # email -> StudyConstraints


@app.post('/api/documents/extract')
async def extract_any_document(
    request: Request,
    file: UploadFile = File(...),
    email: Optional[str] = Form(None)
):
    """
    🚀 UNIVERSAL PDF EXTRACTOR - Auto-detect and extract from ANY PDF!
    
    Automatically detects if the PDF is a syllabus, calendar, or exam timetable
    and extracts all relevant data using LLM Whisperer OCR + Gemini AI.
    
    Returns:
        - document_type: 'syllabus' | 'calendar' | 'timetable' | 'mixed'
        - subjects: List of extracted subjects (if syllabus)
        - events: List of extracted events (if calendar)
        - exams: List of extracted exams (if timetable)
        - extraction_method: 'llm_whisperer+gemini' or 'rule_based'
    """
    try:
        user_email = _resolve_user_email(request, {'email': email} if email else None)
        
        # Validate file type
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail='Only PDF files are supported')
        
        # Save file temporarily
        content = await file.read()
        file_path = doc_processor.save_file(content, file.filename, 'auto')
        
        # Universal extraction - auto-detect and extract
        result = doc_processor.process_any_pdf(file_path)
        
        # Store based on detected type
        if user_email not in USER_DOCUMENTS:
            USER_DOCUMENTS[user_email] = {}
        USER_DOCUMENTS[user_email]['last_upload'] = file_path
        USER_DOCUMENTS[user_email]['last_type'] = result['document_type']
        
        print(f"📄 Universal extraction for {user_email}: {result['document_type']} detected")
        
        return JSONResponse(content={
            'message': f"Document processed successfully as {result['document_type']}",
            'file_path': file_path,
            'document_type': result['document_type'],
            'extraction_method': result['extraction_method'],
            'subjects_count': len(result['subjects']),
            'events_count': len(result['events']),
            'exams_count': len(result['exams']),
            'subjects': result['subjects'],
            'events': result['events'],
            'exams': result['exams'],
            'raw_text_preview': result['raw_text'][:1000] if result['raw_text'] else ''
        }, status_code=200)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in universal extraction: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f'Failed to process document: {str(e)}')


@app.post('/api/documents/upload/syllabus')
async def upload_syllabus(
    request: Request,
    file: UploadFile = File(...),
    email: Optional[str] = Form(None)
):
    """
    Upload syllabus PDF for text extraction and subject parsing.
    Returns extracted subjects with topics, difficulty, and estimated hours.
    """
    try:
        user_email = _resolve_user_email(request, {'email': email} if email else None)
        
        # Validate file type
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail='Only PDF files are supported')
        
        # Save file
        content = await file.read()
        file_path = doc_processor.save_file(content, file.filename, 'syllabus')
        
        # Extract subjects
        subjects = doc_processor.process_syllabus(file_path)
        
        # Store path for user
        if user_email not in USER_DOCUMENTS:
            USER_DOCUMENTS[user_email] = {}
        USER_DOCUMENTS[user_email]['syllabus'] = file_path
        
        # Update constraints
        if user_email not in USER_CONSTRAINTS:
            USER_CONSTRAINTS[user_email] = StudyConstraints()
        USER_CONSTRAINTS[user_email].subjects = subjects
        
        print(f"📚 Syllabus uploaded for {user_email}: {len(subjects)} subjects extracted")
        
        return JSONResponse(content={
            'message': 'Syllabus uploaded successfully',
            'file_path': file_path,
            'subjects_count': len(subjects),
            'subjects': [
                {
                    'name': s.name,
                    'topics': s.topics,  # All topics for table display
                    'topics_count': len(s.topics),
                    'difficulty': s.difficulty,
                    'estimated_hours': s.estimated_hours,
                    'weekly_target_hours': s.weekly_target_hours,
                    'priority': s.priority
                }
                for s in subjects
            ]
        }, status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error uploading syllabus: {e}")
        raise HTTPException(status_code=500, detail=f'Failed to process syllabus: {str(e)}')


@app.post('/api/documents/upload/calendar')
async def upload_academic_calendar(
    request: Request,
    file: UploadFile = File(...),
    email: Optional[str] = Form(None)
):
    """
    Upload academic calendar PDF for event and holiday extraction.
    Returns extracted events with dates and types.
    """
    try:
        user_email = _resolve_user_email(request, {'email': email} if email else None)
        
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail='Only PDF files are supported')
        
        content = await file.read()
        file_path = doc_processor.save_file(content, file.filename, 'calendar')
        
        events = doc_processor.process_calendar(file_path)
        
        if user_email not in USER_DOCUMENTS:
            USER_DOCUMENTS[user_email] = {}
        USER_DOCUMENTS[user_email]['calendar'] = file_path
        
        if user_email not in USER_CONSTRAINTS:
            USER_CONSTRAINTS[user_email] = StudyConstraints()
        USER_CONSTRAINTS[user_email].academic_events = events
        
        print(f"📅 Calendar uploaded for {user_email}: {len(events)} events extracted")
        
        # Categorize events
        holidays = [e for e in events if e.is_holiday]
        exams = [e for e in events if e.event_type == 'exam']
        deadlines = [e for e in events if e.event_type == 'deadline']
        other = [e for e in events if e.event_type not in ['holiday', 'exam', 'deadline']]
        
        return JSONResponse(content={
            'message': 'Academic calendar uploaded successfully',
            'file_path': file_path,
            'events_count': len(events),
            'summary': {
                'holidays': len(holidays),
                'exams': len(exams),
                'deadlines': len(deadlines),
                'other_events': len(other)
            },
            'events': [
                {
                    'name': e.name,
                    'date': e.date,
                    'end_date': e.end_date,
                    'event_type': e.event_type,
                    'is_holiday': e.is_holiday
                }
                for e in events[:20]  # First 20 events
            ]
        }, status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error uploading calendar: {e}")
        raise HTTPException(status_code=500, detail=f'Failed to process calendar: {str(e)}')


@app.post('/api/documents/upload/exam-timetable')
async def upload_exam_timetable(
    request: Request,
    file: UploadFile = File(...),
    email: Optional[str] = Form(None)
):
    """
    Upload exam timetable PDF for exam schedule extraction.
    Returns extracted exams with dates, times, and subjects.
    """
    try:
        user_email = _resolve_user_email(request, {'email': email} if email else None)
        
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail='Only PDF files are supported')
        
        content = await file.read()
        file_path = doc_processor.save_file(content, file.filename, 'exam_timetable')
        
        exams = doc_processor.process_exam_timetable(file_path)
        
        if user_email not in USER_DOCUMENTS:
            USER_DOCUMENTS[user_email] = {}
        USER_DOCUMENTS[user_email]['exam_timetable'] = file_path
        
        if user_email not in USER_CONSTRAINTS:
            USER_CONSTRAINTS[user_email] = StudyConstraints()
        USER_CONSTRAINTS[user_email].exams = exams
        
        print(f"📝 Exam timetable uploaded for {user_email}: {len(exams)} exams extracted")
        
        return JSONResponse(content={
            'message': 'Exam timetable uploaded successfully',
            'file_path': file_path,
            'exams_count': len(exams),
            'exams': [
                {
                    'subject': e.subject,
                    'date': e.date,
                    'start_time': e.start_time,
                    'end_time': e.end_time,
                    'venue': e.venue,
                    'exam_type': e.exam_type
                }
                for e in exams
            ]
        }, status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error uploading exam timetable: {e}")
        raise HTTPException(status_code=500, detail=f'Failed to process exam timetable: {str(e)}')


@app.post('/api/documents/upload/all')
async def upload_all_documents(
    request: Request,
    syllabus: Optional[UploadFile] = File(None),
    calendar: Optional[UploadFile] = File(None),
    exam_timetable: Optional[UploadFile] = File(None),
    email: Optional[str] = Form(None)
):
    """
    Upload all documents (syllabus, calendar, exam timetable) at once.
    At least one document must be provided.
    """
    try:
        user_email = _resolve_user_email(request, {'email': email} if email else None)
        
        if not any([syllabus, calendar, exam_timetable]):
            raise HTTPException(status_code=400, detail='At least one document must be provided')
        
        results: dict = {
            'syllabus': None,
            'calendar': None,
            'exam_timetable': None
        }
        
        if user_email not in USER_DOCUMENTS:
            USER_DOCUMENTS[user_email] = {}
        if user_email not in USER_CONSTRAINTS:
            USER_CONSTRAINTS[user_email] = StudyConstraints()
        
        # Process syllabus
        if syllabus and syllabus.filename:
            if not syllabus.filename.lower().endswith('.pdf'):
                results['syllabus'] = {'error': 'Only PDF files are supported'}
            else:
                content = await syllabus.read()
                file_path = doc_processor.save_file(content, syllabus.filename, 'syllabus')
                subjects = doc_processor.process_syllabus(file_path)
                USER_DOCUMENTS[user_email]['syllabus'] = file_path
                USER_CONSTRAINTS[user_email].subjects = subjects
                results['syllabus'] = {
                    'subjects_count': len(subjects),
                    'subjects': [
                        {
                            'name': s.name,
                            'topics': s.topics,
                            'topics_count': len(s.topics),
                            'difficulty': s.difficulty,
                            'estimated_hours': s.estimated_hours,
                            'weekly_target_hours': s.weekly_target_hours,
                            'priority': s.priority
                        }
                        for s in subjects
                    ]
                }
        
        # Process calendar
        if calendar and calendar.filename:
            if not calendar.filename.lower().endswith('.pdf'):
                results['calendar'] = {'error': 'Only PDF files are supported'}
            else:
                content = await calendar.read()
                file_path = doc_processor.save_file(content, calendar.filename, 'calendar')
                events = doc_processor.process_calendar(file_path)
                USER_DOCUMENTS[user_email]['calendar'] = file_path
                USER_CONSTRAINTS[user_email].academic_events = events
                results['calendar'] = {
                    'events_count': len(events),
                    'holidays': len([e for e in events if e.is_holiday]),
                    'events': [
                        {
                            'name': e.name,
                            'date': e.date.isoformat() if hasattr(e.date, 'isoformat') else str(e.date),
                            'is_holiday': e.is_holiday,
                            'is_exam': e.event_type == 'exam'
                        }
                        for e in events[:20]
                    ]
                }
        
        # Process exam timetable
        if exam_timetable and exam_timetable.filename:
            if not exam_timetable.filename.lower().endswith('.pdf'):
                results['exam_timetable'] = {'error': 'Only PDF files are supported'}
            else:
                content = await exam_timetable.read()
                file_path = doc_processor.save_file(content, exam_timetable.filename, 'exam_timetable')
                exams = doc_processor.process_exam_timetable(file_path)
                USER_DOCUMENTS[user_email]['exam_timetable'] = file_path
                USER_CONSTRAINTS[user_email].exams = exams
                results['exam_timetable'] = {
                    'exams_count': len(exams),
                    'exams': [
                        {
                            'subject': e.subject,
                            'date': e.date.isoformat() if hasattr(e.date, 'isoformat') else str(e.date),
                            'start_time': e.start_time,
                            'end_time': e.end_time,
                            'venue': e.venue,
                            'exam_type': e.exam_type
                        }
                        for e in exams
                    ]
                }
        
        print(f"📂 Documents uploaded for {user_email}: {results}")
        
        return JSONResponse(content={
            'message': 'Documents uploaded successfully',
            'results': results
        }, status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error uploading documents: {e}")
        raise HTTPException(status_code=500, detail=f'Failed to process documents: {str(e)}')


@app.get('/api/documents/status')
async def get_document_status(request: Request, email: Optional[str] = None):
    """
    Get status of uploaded documents for a user.
    Returns which documents have been uploaded and their extraction summary.
    """
    try:
        user_email = _resolve_user_email(request, {'email': email} if email else None)
        
        docs = USER_DOCUMENTS.get(user_email, {})
        constraints = USER_CONSTRAINTS.get(user_email)
        
        status: dict = {
            'syllabus_uploaded': 'syllabus' in docs,
            'calendar_uploaded': 'calendar' in docs,
            'exam_timetable_uploaded': 'exam_timetable' in docs,
            'ready_for_generation': bool(constraints and constraints.subjects)
        }
        
        if constraints:
            status['summary'] = {
                'subjects_count': len(constraints.subjects),
                'events_count': len(constraints.academic_events),
                'exams_count': len(constraints.exams)
            }
        
        return JSONResponse(content=status, status_code=200)
    except Exception as e:
        print(f"Error getting document status: {e}")
        raise HTTPException(status_code=500, detail='Failed to get document status')


@app.post('/api/timetable/generate')
async def generate_study_timetable(request: Request):
    """
    Generate personalized study timetable using CSP algorithm.
    
    Uses uploaded documents (syllabus, calendar, exam timetable) to create
    an optimized study schedule that:
    - Prioritizes subjects based on exam proximity
    - Respects holidays and events from calendar
    - Balances weekly hours per subject
    - Considers subject difficulty
    
    Request body (optional):
    {
        "email": "user@example.com",
        "preferences": {
            "study_start_hour": 8,
            "study_end_hour": 20,
            "max_daily_hours": 6,
            "days_ahead": 14,
            "slot_duration_minutes": 60
        }
    }
    """
    try:
        data = await request.json() if request.headers.get('content-type') == 'application/json' else {}
        user_email = _resolve_user_email(request, data)
        preferences = data.get('preferences', {})
        
        constraints = USER_CONSTRAINTS.get(user_email)
        
        if not constraints or not constraints.subjects:
            raise HTTPException(
                status_code=400, 
                detail='No subjects found. Please upload a syllabus first.'
            )
        
        # Update preferences
        constraints.preferences = preferences
        
        # Generate timetable using CSP
        generator = CSPTimetableGenerator(constraints)
        timetable = generator.generate()
        
        print(f"📅 Timetable generated for {user_email}: {len(timetable)} study slots")
        
        # Group by date for better presentation
        by_date = {}
        for slot in timetable:
            date = slot['date']
            if date not in by_date:
                by_date[date] = {
                    'date': date,
                    'day': slot['day'],
                    'slots': []
                }
            by_date[date]['slots'].append({
                'start_time': slot['start_time'],
                'end_time': slot['end_time'],
                'subject': slot['subject'],
                'difficulty': slot['difficulty'],
                'topics': slot.get('topics', [])
            })
        
        # Calculate statistics
        subject_hours = {}
        for slot in timetable:
            subj = slot['subject']
            subject_hours[subj] = subject_hours.get(subj, 0) + 1
        
        return JSONResponse(content={
            'message': 'Timetable generated successfully',
            'total_slots': len(timetable),
            'total_hours': len(timetable),
            'days_covered': len(by_date),
            'subject_distribution': subject_hours,
            'schedule': list(by_date.values()),
            'raw_slots': timetable[:50]  # First 50 slots for detailed view
        }, status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error generating timetable: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f'Failed to generate timetable: {str(e)}')


@app.post('/api/timetable/generate-manual')
async def generate_timetable_manual(request: Request):
    """
    Generate timetable with manually provided subjects (no PDF upload needed).
    
    Request body:
    {
        "subjects": [
            {
                "name": "Data Structures",
                "difficulty": "hard",
                "estimated_hours": 40,
                "weekly_target_hours": 8,
                "priority": 9,
                "topics": ["Arrays", "Trees", "Graphs"]
            }
        ],
        "exams": [
            {
                "subject": "Data Structures",
                "date": "2026-02-01",
                "start_time": "09:00"
            }
        ],
        "holidays": ["2026-01-26", "2026-01-31"],
        "preferences": {
            "study_start_hour": 8,
            "study_end_hour": 20,
            "max_daily_hours": 6,
            "days_ahead": 14
        }
    }
    """
    try:
        data = await request.json()
        
        # Parse subjects
        subjects_data = data.get('subjects', [])
        if not subjects_data:
            raise HTTPException(status_code=400, detail='At least one subject is required')
        
        subjects = []
        for s in subjects_data:
            subjects.append(Subject(
                name=s.get('name', 'Unknown'),
                topics=s.get('topics', []),
                difficulty=s.get('difficulty', 'medium'),
                estimated_hours=s.get('estimated_hours', 20),
                priority=s.get('priority', 5),
                weekly_target_hours=s.get('weekly_target_hours', 4),
                prerequisites=s.get('prerequisites', [])
            ))
        
        # Parse exams
        exams_data = data.get('exams', [])
        exams = []
        for e in exams_data:
            exams.append(ExamSchedule(
                subject=e.get('subject', ''),
                date=e.get('date', ''),
                start_time=e.get('start_time'),
                end_time=e.get('end_time'),
                exam_type=e.get('exam_type', 'exam')
            ))
        
        # Parse holidays
        holidays = data.get('holidays', [])
        events = [
            AcademicEvent(name='Holiday', date=d, is_holiday=True)
            for d in holidays if d
        ]
        
        # Create constraints
        constraints = StudyConstraints(
            subjects=subjects,
            academic_events=events,
            exams=exams,
            preferences=data.get('preferences', {})
        )
        
        # Generate timetable
        generator = CSPTimetableGenerator(constraints)
        timetable = generator.generate()
        
        # Group by date
        by_date = {}
        for slot in timetable:
            date = slot['date']
            if date not in by_date:
                by_date[date] = {'date': date, 'day': slot['day'], 'slots': []}
            by_date[date]['slots'].append({
                'start_time': slot['start_time'],
                'end_time': slot['end_time'],
                'subject': slot['subject'],
                'difficulty': slot['difficulty']
            })
        
        return JSONResponse(content={
            'message': 'Timetable generated successfully',
            'total_slots': len(timetable),
            'schedule': list(by_date.values())
        }, status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error generating manual timetable: {e}")
        raise HTTPException(status_code=500, detail=f'Failed to generate timetable: {str(e)}')


@app.get('/api/timetable/constraints')
async def get_current_constraints(request: Request, email: Optional[str] = None):
    """
    Get current constraints (subjects, events, exams) for a user.
    Useful for reviewing what was extracted before generating timetable.
    """
    try:
        user_email = _resolve_user_email(request, {'email': email} if email else None)
        
        constraints = USER_CONSTRAINTS.get(user_email)
        
        if not constraints:
            return JSONResponse(content={
                'message': 'No constraints found. Please upload documents first.',
                'constraints': None
            }, status_code=200)
        
        return JSONResponse(content={
            'constraints': constraints.to_dict()
        }, status_code=200)
    except Exception as e:
        print(f"Error getting constraints: {e}")
        raise HTTPException(status_code=500, detail='Failed to get constraints')


@app.put('/api/timetable/constraints/subjects')
async def update_subject_constraints(request: Request):
    """
    Update subject constraints (priority, weekly hours, difficulty) after extraction.
    Allows user to fine-tune before generating timetable.
    
    Request body:
    {
        "email": "user@example.com",
        "subjects": [
            {
                "name": "Data Structures",
                "priority": 10,
                "weekly_target_hours": 10,
                "difficulty": "hard"
            }
        ]
    }
    """
    try:
        data = await request.json()
        user_email = _resolve_user_email(request, data)
        
        constraints = USER_CONSTRAINTS.get(user_email)
        if not constraints:
            raise HTTPException(status_code=400, detail='No constraints found. Upload documents first.')
        
        updates = {s['name'].lower(): s for s in data.get('subjects', [])}
        
        for subject in constraints.subjects:
            update = updates.get(subject.name.lower())
            if update:
                if 'priority' in update:
                    subject.priority = update['priority']
                if 'weekly_target_hours' in update:
                    subject.weekly_target_hours = update['weekly_target_hours']
                if 'difficulty' in update:
                    subject.difficulty = update['difficulty']
                if 'estimated_hours' in update:
                    subject.estimated_hours = update['estimated_hours']
        
        return JSONResponse(content={
            'message': 'Subject constraints updated successfully',
            'subjects': [
                {
                    'name': s.name,
                    'priority': s.priority,
                    'weekly_target_hours': s.weekly_target_hours,
                    'difficulty': s.difficulty
                }
                for s in constraints.subjects
            ]
        }, status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating constraints: {e}")
        raise HTTPException(status_code=500, detail='Failed to update constraints')


# --- Robust Document Extraction Endpoints ---

@app.post("/api/extract-syllabus")
async def extract_syllabus_endpoint(syllabus_pdf: UploadFile = File(...)):
    """Extract syllabus using robust Universal Extractor (Digital + OCR + AI)."""
    try:
        # Save uploaded file temporarily
        file_path = f"temp_{uuid.uuid4()}.pdf"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(syllabus_pdf.file, buffer)
            
        try:
            # Use the robust universal extractor
            result = universal_extractor.extract_any_pdf(file_path)
            
            # If explicit syllabus detected or just mixed, return subjects
            subjects = result.get('subjects', [])
            return {"subjects": subjects, "meta": result.get('extraction_method')}
            
        finally:
            # Clean up
            if os.path.exists(file_path):
                os.remove(file_path)
                
    except Exception as e:
        print(f"Error extracting syllabus: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/extract-exam-timetable")
async def extract_exam_endpoint(timetable_pdf: UploadFile = File(...)):
    """Extract exam timetable using robust Universal Extractor."""
    try:
        file_path = f"temp_{uuid.uuid4()}.pdf"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(timetable_pdf.file, buffer)
            
        try:
            result = universal_extractor.extract_any_pdf(file_path)
            exams = result.get('exams', [])
            return {"exams": exams, "meta": result.get('extraction_method')}
            
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
                
    except Exception as e:
        print(f"Error extracting exam timetable: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/extract-calendar")
async def extract_calendar_endpoint(calendar_pdf: UploadFile = File(...)):
    """Extract academic calendar using robust Universal Extractor."""
    try:
        file_path = f"temp_{uuid.uuid4()}.pdf"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(calendar_pdf.file, buffer)
            
        try:
            result = universal_extractor.extract_any_pdf(file_path)
            events = result.get('events', [])
            return {"events": events, "meta": result.get('extraction_method')}
            
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
                
    except Exception as e:
        print(f"Error extracting calendar: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Main Execution ---
if __name__ == '__main__':
    if os.getenv('SKIP_MODEL_LOAD', '0') == '1' or model is None:
        print("SKIP_MODEL_LOAD active - skipping vector DB population for faster startup.")
    else:
        try:
            populate_vector_db()
        except Exception as e:
            print(f"Warning: populate_vector_db failed: {e}")

    print("\nStarting FastAPI server... accessible at http://0.0.0.0:5000")
    
    try:
        uvicorn.run(app, host='0.0.0.0', port=5000, log_level='info')
    except Exception:
        uvicorn.run(app, host='0.0.0.0', port=5000, log_level='info')







