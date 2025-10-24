import os
import uuid
import chromadb
import requests
import aiohttp
from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sentence_transformers import SentenceTransformer
from datetime import datetime, timedelta, timezone
import pytz
import spacy
from neo4j.time import DateTime, Date
import random
import asyncio
import json
import smtplib
from email.message import EmailMessage
import uvicorn

# Indian Standard Time timezone
IST = pytz.timezone('Asia/Kolkata')

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

driver = get_driver()
print("Neo4j connection successful.")

print("Initializing AI model configuration...")

model = None
classifier_model = None
label_prototypes = {}
nlp = None

PREFER_SKIP = os.getenv('SKIP_MODEL_LOAD', '0') == '1'
EMBED_MODEL = os.getenv('EMBED_MODEL') or 'sentence-transformers/all-mpnet-base-v2'
CLASSIFIER_MODEL = os.getenv('CLASSIFIER_MODEL')

if PREFER_SKIP:
    print("SKIP_MODEL_LOAD=1 detected — skipping heavy model downloads for faster startup (dev mode).")
else:
    try:
        model = SentenceTransformer(EMBED_MODEL)
        print(f"Loaded embedding model: {EMBED_MODEL}")
    except Exception as e:
        print(f"Could not load embedding model {EMBED_MODEL}: {e}")
        raise RuntimeError("Failed to load embedding model.")

    if CLASSIFIER_MODEL:
        try:
            classifier_model = SentenceTransformer(CLASSIFIER_MODEL)
            print(f"Loaded classifier model: {CLASSIFIER_MODEL}")
        except Exception as e:
            print(f"Warning: could not load classifier model {CLASSIFIER_MODEL}: {e}")

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
    except Exception as e:
        print(f"Warning: could not create prototype label embeddings: {e}")

chroma_client = chromadb.Client()
vector_db = chroma_client.get_or_create_collection(name="dynamic_task_scheduler_neo4j")
print("AI Models and Vector DB are ready.")

# WebSocket connection manager
connected_webs = set()
NOTIFIED_TASK_KEYS = set()

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
            session.run("""
                MERGE (d:Day {date: date($task_date)})
                CREATE (t:Task {
                    id: $id, title: $title, description: $description, 
                    startTime: datetime($start_time), endTime: datetime($end_time), 
                    status: 'pending', 
                    dueDate: CASE WHEN $due_date IS NOT NULL THEN datetime($due_date) ELSE null END, 
                    createdAt: datetime(), priority: $priority, category: $category, 
                    estimatedDuration: $estimated_duration, aiEnhanced: $ai_enhanced,
                    timezone: 'IST'
                })
                MERGE (d)-[:HAS_TASK]->(t)
            """,
                task_date=start_dt_ist.date() if start_dt_ist else datetime.now(IST).date(), 
                id=task_id, 
                title=data['title'],
                description=data['description'], 
                start_time=start_dt_ist, 
                end_time=end_dt_ist, 
                due_date=due_datetime_to_store,
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

@app.get("/api/schedule")
async def get_schedule(date: str):
    try:
        query_date = datetime.strptime(date, '%Y-%m-%d').date()
        with driver.session() as session:
            result = session.run("""
                MATCH (:Day {date: date($d)})-[:HAS_TASK]->(t:Task) 
                RETURN t 
                ORDER BY t.startTime
            """, d=query_date)
            tasks = [neo4j_to_serializable(record['t']) for record in result]
        return {"date": date, "tasks": tasks}
    except Exception as e:
        print(f"Error in get_schedule: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve schedule.")

@app.get("/api/upcoming-deadlines")
async def get_upcoming_deadlines():
    try:
        today = datetime.utcnow().date()
        with driver.session() as session:
            result = session.run("MATCH (t:Task) WHERE t.status = 'pending' RETURN t")
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

async def _fetch_external_quote_api(tags: list = None):
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

def _generate_contextual_quote_with_ai(module: str = None, task_data: dict = None):
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
async def get_quote(module: str = None, use_ai: bool = False):
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
async def recommend_tasks(topic: str | None = None):
    try:
        forced = topic
        if forced:
            t = forced.lower()
            if t in ('projects', 'project'):
                recs = []
                try:
                    with driver.session() as session:
                        res = session.run("""
                            MATCH (t:Task) 
                            WHERE toLower(coalesce(t.category,'')) CONTAINS 'project' 
                            OR toLower(coalesce(t.title,'')) CONTAINS 'project' 
                            RETURN t.id as id, t.title as title, t.estimatedDuration as est 
                            LIMIT 20
                        """)
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
                return {'topic': t, 'recommendations': recs}
            
            recs = _recommendations_for_topic(t)
            return {'topic': t, 'recommendations': recs}

        # Auto-detect topic
        with driver.session() as session:
            result = session.run("""
                MATCH (t:Task) 
                WHERE t.status='pending' AND t.description IS NOT NULL 
                RETURN t.description AS desc, t.title AS title 
                LIMIT 1
            """)
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
                        MATCH (t:Task) 
                        WHERE toLower(coalesce(t.category,'')) CONTAINS 'project' 
                        OR toLower(coalesce(t.title,'')) CONTAINS 'project' 
                        RETURN t.id as id, t.title as title, t.estimatedDuration as est 
                        LIMIT 20
                    """)
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
async def api_eisenhower_schedule(max: int | None = None):
    """Return Eisenhower matrix schedule."""
    try:
        # Delegate heavy lifting to helper that computes quadrants and prioritized list
        quadrants, prioritized_final = _compute_eisenhower_quadrants(max_items=max)
        return JSONResponse(content={
            'quadrants': quadrants,
            'prioritized': prioritized_final
        }, status_code=200)
    except Exception as e:
        print(f"Error in api_eisenhower_schedule: {e}")
        return JSONResponse(content={'error': 'Could not compute Eisenhower schedule'}, status_code=500)


def _compute_eisenhower_quadrants(max_items: int | None = None):
    """Compute Eisenhower quadrants and return (quadrants_dict, prioritized_list).

    This function encapsulates the logic previously in the endpoint so it can be
    reused by other endpoints. It returns:
      - quadrants: dict mapping quadrant name -> list of enriched items
      - prioritized_final: final prioritized/scheduled list (possibly truncated)
    """
    max_items = max_items
    with driver.session() as session:
        result = session.run("MATCH (t:Task) WHERE t.status = 'pending' RETURN t")
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
async def api_eisenhower_matrix():
    """Return a concise Eisenhower matrix summary (counts + brief task list per quadrant)."""
    try:
        quadrants, _ = _compute_eisenhower_quadrants(max_items=None)
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
async def api_login(request: Request):
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
            user_obj = {k: neo4j_to_serializable(v) for k,v in dict(user).items()} if hasattr(user, 'items') else dict(user)
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
        email_hdr = request.headers.get('x-user-email') or request.headers.get('X-User-Email')
        with driver.session() as session:
            if email_hdr:
                rec = session.run("MATCH (u:User {email: $email}) RETURN u", email=email_hdr).single()
            else:
                rec = session.run("MATCH (u:User) RETURN u LIMIT 1").single()

        if not rec:
            return {'id': None, 'name': 'Guest', 'email': None}

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

@app.post('/api/auth/signup')
async def api_signup(request: Request):
    try:
        data = await request.json()
        name = data.get('name')
        email = data.get('email')
        password = data.get('password')
        if not name or not email or not password:
            raise HTTPException(status_code=400, detail='Missing fields')

        user_id = str(uuid.uuid4())
        with driver.session() as session:
            existing = session.run("MATCH (u:User {email: $email}) RETURN u", email=email).single()
            if existing:
                raise HTTPException(status_code=409, detail='User already exists')
            session.run("""
                CREATE (u:User {
                    id: $id, 
                    name: $name, 
                    email: $email, 
                    password: $password, 
                    createdAt: datetime()
                })
            """, id=user_id, name=name, email=email, password=password)

        return JSONResponse(status_code=201, content={
            'message': 'User created',
            'id': user_id
        })
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in api_signup: {e}")
        raise HTTPException(status_code=500, detail='Internal error')

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
            rec = session.run("MATCH (u:User {email: $email}) RETURN u", email=email).single()
            if not rec:
                user_id = str(uuid.uuid4())
                session.run("""
                    CREATE (u:User {id: $id, email: $email, createdAt: datetime()})
                """, id=user_id, email=email)
            
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
                    exp_dt = datetime.fromisoformat(otp_expiry)
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
async def api_notifications_pending():
    """Get pending notifications with IST timezone support."""
    try:
        now_utc = datetime.now(timezone.utc)
        now_ist = now_utc.astimezone(IST)
        
        notifications = []
        
        with driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.status = 'pending' 
                AND t.startTime IS NOT NULL
                AND datetime(t.startTime) > datetime()
                AND datetime(t.startTime) <= datetime() + duration({minutes: 15})
                RETURN t.id AS id, t.title AS title, t.startTime AS startTime, 
                       'start' AS type
                ORDER BY t.startTime
                LIMIT 20
            """)
            
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
                MATCH (t:Task)
                WHERE t.status = 'pending' 
                AND t.dueDate IS NOT NULL
                RETURN t.id AS id, t.title AS title, t.dueDate AS dueDate,
                       'due' AS type
                ORDER BY t.dueDate
                LIMIT 50
            """)
            
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
            total = count_result.single()['total']
            
            pending_result = session.run("""
                MATCH (t:Task) 
                WHERE t.status = 'pending' 
                RETURN count(t) as count
            """)
            pending = pending_result.single()['count']
            
            today = datetime.now(IST).date()
            today_result = session.run("""
                MATCH (:Day {date: date($d)})-[:HAS_TASK]->(t:Task) 
                RETURN count(t) as count
            """, d=today)
            today_count = today_result.single()['count']
        
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