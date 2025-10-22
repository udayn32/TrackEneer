import osimport os

import uuidimport uuid

import chromadbimport chromadb

import requestsimport requests

from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnectfrom fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect

from fastapi.middleware.cors import CORSMiddlewarefrom fastapi.middleware.cors import CORSMiddleware

from fastapi.responses import JSONResponsefrom fastapi.responses import JSONResponse

from sentence_transformers import SentenceTransformerfrom sentence_transformers import SentenceTransformer

from neo4j import GraphDatabasefrom neo4j import GraphDatabase

from datetime import datetime, timedelta, timezonefrom datetime import datetime, timedelta, timezone

import pytz  # Add pytz for timezone supportimport pytz  # Add pytz for timezone support

import spacyimport spacy

from neo4j.time import DateTime, Datefrom neo4j.time import DateTime, Date

import random # Import the random moduleimport random # Import the random module

import asyncioimport asyncio

import jsonimport json

import smtplibimport smtplib

from email.message import EmailMessagefrom email.message import EmailMessage

import uvicornimport uvicorn



# Indian Standard Time timezone# Indian Standard Time timezone

IST = pytz.timezone('Asia/Kolkata')IST = pytz.timezone('Asia/Kolkata')



# --- 1. FastAPI App Initialization ---# --- 1. FastAPI App Initialization ---

app = FastAPI()app = FastAPI()

# Allow requests from the Next.js dev server# Allow requests from the Next.js dev server

app.add_middleware(app.add_middleware(

    CORSMiddleware,    CORSMiddleware,

    allow_origins=["http://localhost:3000"],    allow_origins=["http://localhost:3000"],

    allow_credentials=True,    allow_credentials=True,

    allow_methods=["*"],    allow_methods=["*"],

    allow_headers=["*"],    allow_headers=["*"],

))



# --- Helper function for JSON serialization ---# --- Helper function for JSON serialization ---

def neo4j_to_serializable(obj):def neo4j_to_serializable(obj):

    """Recursively converts Neo4j objects to JSON serializable formats."""    """Recursively converts Neo4j objects to JSON serializable formats."""

    if isinstance(obj, (DateTime, Date)):    if isinstance(obj, (DateTime, Date)):

        return obj.isoformat()        return obj.isoformat()

    if hasattr(obj, 'items'): # Handles Records, Nodes, etc.    if hasattr(obj, 'items'): # Handles Records, Nodes, etc.

        return {key: neo4j_to_serializable(value) for key, value in obj.items()}        return {key: neo4j_to_serializable(value) for key, value in obj.items()}

    if isinstance(obj, list):    if isinstance(obj, list):

        return [neo4j_to_serializable(element) for element in obj]        return [neo4j_to_serializable(element) for element in obj]

    return obj    return obj



# --- 2. Database & AI Model Setup ---# --- 2. Database & AI Model Setup ---

NEO4J_URI = "neo4j://127.0.0.1:7687"NEO4J_URI = "neo4j://127.0.0.1:7687"

NEO4J_USER = "neo4j"NEO4J_USER = "neo4j"

NEO4J_PASSWORD = "8828142901"NEO4J_PASSWORD = "8828142901"



try:try:

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    driver.verify_connectivity()    driver.verify_connectivity()

    print("Neo4j connection successful.")    print("Neo4j connection successful.")

except Exception as e:except Exception as e:

    print(f"Error connecting to Neo4j: {e}")    print(f"Error connecting to Neo4j: {e}")

    exit()    exit()



print("Initializing AI model configuration...")print("Initializing AI model configuration...")

# Support either a single powerful model (default) or an optional separate classifier model.# Support either a single powerful model (default) or an optional separate classifier model.

# Environment variables:# Environment variables:

#  - SKIP_MODEL_LOAD=1  -> dev mode: skip heavy downloads#  - SKIP_MODEL_LOAD=1  -> dev mode: skip heavy downloads

#  - EMBED_MODEL        -> embedding model to use (overrides default)#  - EMBED_MODEL        -> embedding model to use (overrides default)

#  - CLASSIFIER_MODEL   -> optional separate model to use for prototype/classification#  - CLASSIFIER_MODEL   -> optional separate model to use for prototype/classification



model = None  # embedding model used for vector DB and general encodingsmodel = None  # embedding model used for vector DB and general encodings

classifier_model = None  # optional model used specifically for lightweight classification/prototypesclassifier_model = None  # optional model used specifically for lightweight classification/prototypes

label_prototypes = {}label_prototypes = {}

PREFER_SKIP = os.getenv('SKIP_MODEL_LOAD', '0') == '1'PREFER_SKIP = os.getenv('SKIP_MODEL_LOAD', '0') == '1'

EMBED_MODEL = os.getenv('EMBED_MODEL') or 'sentence-transformers/all-mpnet-base-v2'EMBED_MODEL = os.getenv('EMBED_MODEL') or 'sentence-transformers/all-mpnet-base-v2'

CLASSIFIER_MODEL = os.getenv('CLASSIFIER_MODEL')  # optionalCLASSIFIER_MODEL = os.getenv('CLASSIFIER_MODEL')  # optional



if PREFER_SKIP:if PREFER_SKIP:

    print("SKIP_MODEL_LOAD=1 detected — skipping heavy model downloads for faster startup (dev mode).")    print("SKIP_MODEL_LOAD=1 detected — skipping heavy model downloads for faster startup (dev mode).")

    model = None    model = None

    classifier_model = None    classifier_model = None

    nlp = None    nlp = None

else:else:

    # Load embedding model    # Load embedding model

    try:    try:

        model = SentenceTransformer(EMBED_MODEL)        model = SentenceTransformer(EMBED_MODEL)

        print(f"Loaded embedding model: {EMBED_MODEL}")        print(f"Loaded embedding model: {EMBED_MODEL}")

    except Exception as e:    except Exception as e:

        print(f"Could not load embedding model {EMBED_MODEL}: {e}")        print(f"Could not load embedding model {EMBED_MODEL}: {e}")

        raise RuntimeError("Failed to load embedding model. Ensure internet access or install models locally.")        raise RuntimeError("Failed to load embedding model. Ensure internet access or install models locally.")



    # Optionally load a separate classifier model for prototype similarity if provided    # Optionally load a separate classifier model for prototype similarity if provided

    if CLASSIFIER_MODEL:    if CLASSIFIER_MODEL:

        try:        try:

            classifier_model = SentenceTransformer(CLASSIFIER_MODEL)            classifier_model = SentenceTransformer(CLASSIFIER_MODEL)

            print(f"Loaded classifier model: {CLASSIFIER_MODEL}")            print(f"Loaded classifier model: {CLASSIFIER_MODEL}")

        except Exception as e:        except Exception as e:

            print(f"Warning: could not load classifier model {CLASSIFIER_MODEL}: {e}")            print(f"Warning: could not load classifier model {CLASSIFIER_MODEL}: {e}")

            classifier_model = None            classifier_model = None



    # spaCy for keyword extraction (best-effort)    # spaCy for keyword extraction (best-effort)

    try:    try:

        nlp = spacy.load("en_core_web_sm")        nlp = spacy.load("en_core_web_sm")

    except OSError:    except OSError:

        print("spaCy model not found. Attempting to download...")        print("spaCy model not found. Attempting to download...")

        os.system('python -m spacy download en_core_web_sm')        os.system('python -m spacy download en_core_web_sm')

        nlp = spacy.load("en_core_web_sm")        nlp = spacy.load("en_core_web_sm")



    # Prepare small set of prototype label embeddings for lightweight classification    # Prepare small set of prototype label embeddings for lightweight classification

    try:    try:

        proto_labels = ['urgent', 'not urgent', 'important', 'not important',        proto_labels = ['urgent', 'not urgent', 'important', 'not important',

                        'dsa', 'aptitude', 'system design', 'machine learning', 'projects', 'reading', 'general']                        'dsa', 'aptitude', 'system design', 'machine learning', 'projects', 'reading', 'general']

        proto_source = classifier_model or model        proto_source = classifier_model or model

        proto_embs = proto_source.encode(proto_labels)        proto_embs = proto_source.encode(proto_labels)

        for lab, emb in zip(proto_labels, proto_embs):        for lab, emb in zip(proto_labels, proto_embs):

            label_prototypes[lab] = emb            label_prototypes[lab] = emb

    except Exception as e:    except Exception as e:

        print(f"Warning: could not create prototype label embeddings: {e}")        print(f"Warning: could not create prototype label embeddings: {e}")



chroma_client = chromadb.Client()chroma_client = chromadb.Client()

vector_db = chroma_client.get_or_create_collection(name="dynamic_task_scheduler_neo4j")vector_db = chroma_client.get_or_create_collection(name="dynamic_task_scheduler_neo4j")

print("AI Models and Vector DB are ready.")print("AI Models and Vector DB are ready.")



# WebSocket connection manager for instant notifications# WebSocket connection manager for instant notifications

connected_webs = set()connected_webs = set()

NOTIFIED_TASK_KEYS = set()NOTIFIED_TASK_KEYS = set()



async def notify_clients(payload: dict):async def notify_clients(payload: dict):

    """Broadcast a JSON payload to all connected websocket clients."""    """Broadcast a JSON payload to all connected websocket clients."""

    to_remove = []    to_remove = []

    text = json.dumps(payload, default=str)    text = json.dumps(payload, default=str)

    for ws in list(connected_webs):    for ws in list(connected_webs):

        try:        try:

            await ws.send_text(text)            await ws.send_text(text)

        except Exception as e:        except Exception as e:

            print(f"Warning: failed to send websocket message: {e}")            print(f"Warning: failed to send websocket message: {e}")

            to_remove.append(ws)            to_remove.append(ws)

    for ws in to_remove:    for ws in to_remove:

        try:        try:

            connected_webs.discard(ws)            connected_webs.discard(ws)

        except Exception:        except Exception:

            pass            pass





async def background_push_watcher():async def background_push_watcher():

    """Background watcher that finds tasks starting, ending, or due in the immediate window and notifies clients."""    """Background watcher that finds tasks starting, ending, or due in the immediate window and notifies clients."""

    print('Background push watcher started')    print('Background push watcher started')

    while True:    while True:

        try:        try:

            now = datetime.utcnow()            now = datetime.utcnow()

            window_end = now + timedelta(seconds=40)            window_end = now + timedelta(seconds=40)

            with driver.session() as session:            with driver.session() as session:

                # Return candidate tasks with startTime, endTime, or dueDate                # Return candidate tasks with startTime, endTime, or dueDate

                res = session.run("MATCH (t:Task) WHERE t.status='pending' AND (t.startTime IS NOT NULL OR t.endTime IS NOT NULL OR t.dueDate IS NOT NULL) RETURN t.id AS id, t.title AS title, t.startTime AS startTime, t.endTime AS endTime, t.dueDate AS dueDate LIMIT 200")                res = session.run("MATCH (t:Task) WHERE t.status='pending' AND (t.startTime IS NOT NULL OR t.endTime IS NOT NULL OR t.dueDate IS NOT NULL) RETURN t.id AS id, t.title AS title, t.startTime AS startTime, t.endTime AS endTime, t.dueDate AS dueDate LIMIT 200")

                rows = [r.data() for r in res]                rows = [r.data() for r in res]



            for r in rows:            for r in rows:

                try:                try:

                    tid = r.get('id')                    tid = r.get('id')

                    title = r.get('title') or 'Untitled'                    title = r.get('title') or 'Untitled'

                    raw_start = neo4j_to_serializable(r.get('startTime'))                    raw_start = neo4j_to_serializable(r.get('startTime'))

                    raw_end = neo4j_to_serializable(r.get('endTime'))                    raw_end = neo4j_to_serializable(r.get('endTime'))

                    raw_due = neo4j_to_serializable(r.get('dueDate'))                    raw_due = neo4j_to_serializable(r.get('dueDate'))

                                        

                    # Check start time                    # Check start time

                    if raw_start:                    if raw_start:

                        ds = _parse_iso_to_dt(raw_start)                        ds = _parse_iso_to_dt(raw_start)

                        if ds and now <= ds <= window_end:                        if ds and now <= ds <= window_end:

                            key = f"{tid}-start-{ds.isoformat()}"                            key = f"{tid}-start-{ds.isoformat()}"

                            if key not in NOTIFIED_TASK_KEYS:                            if key not in NOTIFIED_TASK_KEYS:

                                await notify_clients({'type': 'task_start', 'task': {'id': tid, 'title': title, 'startTime': ds.isoformat()}})                                await notify_clients({'type': 'task_start', 'task': {'id': tid, 'title': title, 'startTime': ds.isoformat()}})

                                NOTIFIED_TASK_KEYS.add(key)                                NOTIFIED_TASK_KEYS.add(key)

                                print(f"✅ Notification sent: Task '{title}' is starting!")                                print(f"✅ Notification sent: Task '{title}' is starting!")

                                        

                    # Check end time                    # Check end time

                    if raw_end:                    if raw_end:

                        de = _parse_iso_to_dt(raw_end)                        de = _parse_iso_to_dt(raw_end)

                        if de and now <= de <= window_end:                        if de and now <= de <= window_end:

                            key = f"{tid}-end-{de.isoformat()}"                            key = f"{tid}-end-{de.isoformat()}"

                            if key not in NOTIFIED_TASK_KEYS:                            if key not in NOTIFIED_TASK_KEYS:

                                await notify_clients({'type': 'task_end', 'task': {'id': tid, 'title': title, 'endTime': de.isoformat()}})                                await notify_clients({'type': 'task_end', 'task': {'id': tid, 'title': title, 'endTime': de.isoformat()}})

                                NOTIFIED_TASK_KEYS.add(key)                                NOTIFIED_TASK_KEYS.add(key)

                                print(f"✅ Notification sent: Task '{title}' is ending!")                                print(f"✅ Notification sent: Task '{title}' is ending!")

                                        

                    # Check due date                    # Check due date

                    if raw_due:                    if raw_due:

                        dd = _parse_iso_to_dt(raw_due)                        dd = _parse_iso_to_dt(raw_due)

                        if dd and now <= dd <= window_end:                        if dd and now <= dd <= window_end:

                            key = f"{tid}-due-{dd.isoformat()}"                            key = f"{tid}-due-{dd.isoformat()}"

                            if key not in NOTIFIED_TASK_KEYS:                            if key not in NOTIFIED_TASK_KEYS:

                                await notify_clients({'type': 'task_due', 'task': {'id': tid, 'title': title, 'dueDate': dd.isoformat()}})                                await notify_clients({'type': 'task_due', 'task': {'id': tid, 'title': title, 'dueDate': dd.isoformat()}})

                                NOTIFIED_TASK_KEYS.add(key)                                NOTIFIED_TASK_KEYS.add(key)

                                print(f"✅ Notification sent: Task '{title}' is due!")                                print(f"✅ Notification sent: Task '{title}' is due!")

                except Exception as e:                except Exception as e:

                    print(f"Error evaluating push candidate: {e}")                    print(f"Error evaluating push candidate: {e}")

        except Exception as e:        except Exception as e:

            print(f"Background push watcher error: {e}")            print(f"Background push watcher error: {e}")

        await asyncio.sleep(10)        await asyncio.sleep(10)





@app.on_event('startup')@app.on_event('startup')

async def _start_background_tasks():async def _start_background_tasks():

    try:    try:

        asyncio.create_task(background_push_watcher())        asyncio.create_task(background_push_watcher())

    except Exception as e:    except Exception as e:

        print(f"Failed to start background push watcher: {e}")        print(f"Failed to start background push watcher: {e}")



# Try to load cached embeddings if present (useful when SKIP_MODEL_LOAD=1)# Try to load cached embeddings if present (useful when SKIP_MODEL_LOAD=1)

CACHE_META = NoneCACHE_META = None

CACHE_PATH = os.path.join(os.path.dirname(__file__), 'model_cache.npz')CACHE_PATH = os.path.join(os.path.dirname(__file__), 'model_cache.npz')

CACHE_META_PATH = os.path.join(os.path.dirname(__file__), 'model_cache_meta.json')CACHE_META_PATH = os.path.join(os.path.dirname(__file__), 'model_cache_meta.json')

try:try:

    if os.path.exists(CACHE_PATH):    if os.path.exists(CACHE_PATH):

        import numpy as _np        import numpy as _np

        arr = _np.load(CACHE_PATH, allow_pickle=True)        arr = _np.load(CACHE_PATH, allow_pickle=True)

        ids = arr['ids'].tolist() if 'ids' in arr else []        ids = arr['ids'].tolist() if 'ids' in arr else []

        embeddings = arr['embeddings'].tolist() if 'embeddings' in arr else []        embeddings = arr['embeddings'].tolist() if 'embeddings' in arr else []

        if ids and embeddings:        if ids and embeddings:

            try:            try:

                vector_db.upsert(ids=ids, embeddings=embeddings)                vector_db.upsert(ids=ids, embeddings=embeddings)

                print(f"Loaded {len(ids)} cached embeddings into Vector DB from {CACHE_PATH}")                print(f"Loaded {len(ids)} cached embeddings into Vector DB from {CACHE_PATH}")

            except Exception as e:            except Exception as e:

                print(f"Warning: failed to upsert cached embeddings: {e}")                print(f"Warning: failed to upsert cached embeddings: {e}")

        try:        try:

            import json as _json            import json as _json

            if os.path.exists(CACHE_META_PATH):            if os.path.exists(CACHE_META_PATH):

                with open(CACHE_META_PATH, 'r', encoding='utf-8') as mf:                with open(CACHE_META_PATH, 'r', encoding='utf-8') as mf:

                    CACHE_META = _json.load(mf)                    CACHE_META = _json.load(mf)

        except Exception:        except Exception:

            CACHE_META = None            CACHE_META = None

except Exception as e:except Exception as e:

    print(f"Error loading cache file: {e}")    print(f"Error loading cache file: {e}")





# --- 4. Task Automation Functions ---# --- 4. Task Automation Functions ---

def auto_schedule_task(task_data):def auto_schedule_task(task_data):

    description = task_data.get('description', '')    description = task_data.get('description', '')

    title = task_data.get('title', '')    title = task_data.get('title', '')

        

    priority = "medium"    priority = "medium"

    if nlp:    if nlp:

        desc_lower = description.lower()        desc_lower = description.lower()

        if any(k in desc_lower for k in ["urgent", "asap", "deadline", "critical"]): priority = "high"        if any(k in desc_lower for k in ["urgent", "asap", "deadline", "critical"]): priority = "high"

        elif any(k in desc_lower for k in ["maybe", "later", "someday", "eventually"]): priority = "low"        elif any(k in desc_lower for k in ["maybe", "later", "someday", "eventually"]): priority = "low"

                

    category = "general"    category = "general"

    # Simple keyword heuristics for category detection (avoid external classifiers)    # Simple keyword heuristics for category detection (avoid external classifiers)

    try:    try:

        s = (title + ' ' + description).lower()        s = (title + ' ' + description).lower()

        if any(k in s for k in ['work', 'project', 'job', 'capgemini', 'placement']):        if any(k in s for k in ['work', 'project', 'job', 'capgemini', 'placement']):

            category = 'work'            category = 'work'

        elif any(k in s for k in ['health', 'exercise', 'cardio']):        elif any(k in s for k in ['health', 'exercise', 'cardio']):

            category = 'health'            category = 'health'

        elif any(k in s for k in ['read', 'study', 'dsa', 'machine learning', 'ml', 'aptitude']):        elif any(k in s for k in ['read', 'study', 'dsa', 'machine learning', 'ml', 'aptitude']):

            category = 'education'            category = 'education'

        elif any(k in s for k in ['buy', 'purchase', 'shopping']):        elif any(k in s for k in ['buy', 'purchase', 'shopping']):

            category = 'shopping'            category = 'shopping'

        elif any(k in s for k in ['finance', 'payment', 'invoice']):        elif any(k in s for k in ['finance', 'payment', 'invoice']):

            category = 'finance'            category = 'finance'

        else:        else:

            category = 'general'            category = 'general'

    except Exception:    except Exception:

        category = 'general'        category = 'general'



    return {    return {

        "priority": priority,        "priority": priority,

        "category": category,        "category": category,

        "estimated_duration": 30, # Default duration, can be enhanced later        "estimated_duration": 30, # Default duration, can be enhanced later

        "ai_enhanced": True        "ai_enhanced": True

    }    }



# --- 5. API Endpoints ---# --- 5. API Endpoints ---



@app.post("/api/add-task")@app.post("/api/add-task")

async def add_task(request: Request):async def add_task(request: Request):

    try:    try:

        data = await request.json()        data = await request.json()

        if not all(k in data for k in ['title', 'description', 'startTime', 'endTime']):        if not all(k in data for k in ['title', 'description', 'startTime', 'endTime']):

            raise HTTPException(status_code=400, detail="Missing required task fields.")            raise HTTPException(status_code=400, detail="Missing required task fields.")



        task_id = str(uuid.uuid4())        task_id = str(uuid.uuid4())

        # Parse ISO datetime strings and convert to IST-aware datetime        # Parse ISO datetime strings and convert to IST-aware datetime

        try:        try:

            start_dt = datetime.fromisoformat(data['startTime'].replace('Z', '+00:00'))            start_dt = datetime.fromisoformat(data['startTime'].replace('Z', '+00:00'))

            if start_dt.tzinfo is None:            if start_dt.tzinfo is None:

                start_dt = start_dt.replace(tzinfo=timezone.utc)                start_dt = start_dt.replace(tzinfo=timezone.utc)

            # Convert to IST for storage            # Convert to IST for storage

            start_dt_ist = start_dt.astimezone(IST)            start_dt_ist = start_dt.astimezone(IST)

        except Exception as e:        except Exception as e:

            print(f"Error parsing startTime: {e}")            print(f"Error parsing startTime: {e}")

            start_dt = None            start_dt = None

            start_dt_ist = None            start_dt_ist = None

                

        try:        try:

            end_dt = datetime.fromisoformat(data['endTime'].replace('Z', '+00:00'))            end_dt = datetime.fromisoformat(data['endTime'].replace('Z', '+00:00'))

            if end_dt.tzinfo is None:            if end_dt.tzinfo is None:

                end_dt = end_dt.replace(tzinfo=timezone.utc)                end_dt = end_dt.replace(tzinfo=timezone.utc)

            # Convert to IST for storage            # Convert to IST for storage

            end_dt_ist = end_dt.astimezone(IST)            end_dt_ist = end_dt.astimezone(IST)

        except Exception as e:        except Exception as e:

            print(f"Error parsing endTime: {e}")            print(f"Error parsing endTime: {e}")

            end_dt = None            end_dt = None

            end_dt_ist = None            end_dt_ist = None



        ai_analysis = auto_schedule_task(data)        ai_analysis = auto_schedule_task(data)



        # Handle due date with IST timezone        # Handle due date with IST timezone

        provided_due = data.get('dueDate')        provided_due = data.get('dueDate')

        due_datetime_to_store = None        due_datetime_to_store = None

                

        if provided_due:        if provided_due:

            try:            try:

                # Parse provided due date (should be ISO format from frontend)                # Parse provided due date (should be ISO format from frontend)

                due_dt = datetime.fromisoformat(provided_due.replace('Z', '+00:00'))                due_dt = datetime.fromisoformat(provided_due.replace('Z', '+00:00'))

                if due_dt.tzinfo is None:                if due_dt.tzinfo is None:

                    due_dt = due_dt.replace(tzinfo=timezone.utc)                    due_dt = due_dt.replace(tzinfo=timezone.utc)

                # Convert to IST                # Convert to IST

                due_dt_ist = due_dt.astimezone(IST)                due_dt_ist = due_dt.astimezone(IST)

                due_datetime_to_store = due_dt_ist                due_datetime_to_store = due_dt_ist

            except Exception as e:            except Exception as e:

                print(f"Error parsing dueDate: {e}")                print(f"Error parsing dueDate: {e}")

                due_datetime_to_store = None                due_datetime_to_store = None

        elif end_dt_ist:        elif end_dt_ist:

            # Use end time as due date if no due date provided            # Use end time as due date if no due date provided

            due_datetime_to_store = end_dt_ist            due_datetime_to_store = end_dt_ist

        elif start_dt_ist:        elif start_dt_ist:

            # Use start time + estimated duration            # Use start time + estimated duration

            try:            try:

                est = int(data.get('estimatedDuration') or data.get('estimated_duration') or ai_analysis.get('estimated_duration', 60))                est = int(data.get('estimatedDuration') or data.get('estimated_duration') or ai_analysis.get('estimated_duration', 60))

                due_datetime_to_store = start_dt_ist + timedelta(minutes=est)                due_datetime_to_store = start_dt_ist + timedelta(minutes=est)

            except Exception:            except Exception:

                due_datetime_to_store = start_dt_ist + timedelta(hours=1)                due_datetime_to_store = start_dt_ist + timedelta(hours=1)



        with driver.session() as session:        with driver.session() as session:

            session.run("""            session.run("""

                MERGE (d:Day {date: date($task_date)})                MERGE (d:Day {date: date($task_date)})

                CREATE (t:Task {                CREATE (t:Task {

                    id: $id, title: $title, description: $description,                     id: $id, title: $title, description: $description, 

                    startTime: datetime($start_time), endTime: datetime($end_time),                     startTime: datetime($start_time), endTime: datetime($end_time), 

                    status: 'pending',                     status: 'pending', 

                    dueDate: CASE WHEN $due_date IS NOT NULL THEN datetime($due_date) ELSE null END,                     dueDate: CASE WHEN $due_date IS NOT NULL THEN datetime($due_date) ELSE null END, 

                    createdAt: datetime(), priority: $priority, category: $category,                     createdAt: datetime(), priority: $priority, category: $category, 

                    estimatedDuration: $estimated_duration, aiEnhanced: $ai_enhanced,                    estimatedDuration: $estimated_duration, aiEnhanced: $ai_enhanced,

                    timezone: 'IST'                    timezone: 'IST'

                })                })

                MERGE (d)-[:HAS_TASK]->(t)                MERGE (d)-[:HAS_TASK]->(t)

                """,                """,

                task_date=start_dt_ist.date() if start_dt_ist else datetime.now(IST).date(),                 task_date=start_dt_ist.date() if start_dt_ist else datetime.now(IST).date(), 

                id=task_id,                 id=task_id, 

                title=data['title'],                title=data['title'],

                description=data['description'],                 description=data['description'], 

                start_time=start_dt_ist,                 start_time=start_dt_ist, 

                end_time=end_dt_ist,                 end_time=end_dt_ist, 

                due_date=due_datetime_to_store,                due_date=due_datetime_to_store,

                **ai_analysis)                **ai_analysis)



        # Add embedding to vector DB if model loaded; in dev mode SKIP_MODEL_LOAD the model may be None        # Add embedding to vector DB if model loaded; in dev mode SKIP_MODEL_LOAD the model may be None

        try:        try:

            if model is not None:            if model is not None:

                vector_db.add(ids=[task_id], embeddings=[model.encode(data['description']).tolist()])                vector_db.add(ids=[task_id], embeddings=[model.encode(data['description']).tolist()])

        except Exception as e:        except Exception as e:

            print(f"Warning: could not add embedding for task {task_id}: {e}")            print(f"Warning: could not add embedding for task {task_id}: {e}")



        # After creating the task, attempt to infer and create finish-to-start relationships among pending tasks        # After creating the task, attempt to infer and create finish-to-start relationships among pending tasks

        try:        try:

            infer_finish_to_start_relations()            infer_finish_to_start_relations()

            # notify websocket clients instantly about new task with complete payload            # notify websocket clients instantly about new task with complete payload

            try:            try:

                notification_payload = {                notification_payload = {

                    'type': 'task_added',                    'type': 'task_added',

                    'taskId': task_id,                    'taskId': task_id,

                    'title': data.get('title'),                    'title': data.get('title'),

                    'description': data.get('description'),                    'description': data.get('description'),

                    'startTime': start_dt_ist.isoformat() if start_dt_ist else None,                    'startTime': start_dt_ist.isoformat() if start_dt_ist else None,

                    'endTime': end_dt_ist.isoformat() if end_dt_ist else None,                    'endTime': end_dt_ist.isoformat() if end_dt_ist else None,

                    'task': {                    'task': {

                        'id': task_id,                        'id': task_id,

                        'title': data.get('title'),                        'title': data.get('title'),

                        'description': data.get('description'),                        'description': data.get('description'),

                        'startTime': start_dt_ist.isoformat() if start_dt_ist else None,                        'startTime': start_dt_ist.isoformat() if start_dt_ist else None,

                        'endTime': end_dt_ist.isoformat() if end_dt_ist else None                        'endTime': end_dt_ist.isoformat() if end_dt_ist else None

                    }                    }

                }                }

                asyncio.create_task(notify_clients(notification_payload))                asyncio.create_task(notify_clients(notification_payload))

                print(f"✅ WebSocket notification sent for new task: {data.get('title')}")                print(f"✅ WebSocket notification sent for new task: {data.get('title')}")

            except Exception as e:            except Exception as e:

                print(f"Warning: could not notify websocket clients: {e}")                print(f"Warning: could not notify websocket clients: {e}")

        except Exception as e:        except Exception as e:

            print(f"Warning: finish-to-start inference failed: {e}")            print(f"Warning: finish-to-start inference failed: {e}")



        return JSONResponse(status_code=201, content={"message": "Task added successfully", "taskId": task_id})        return JSONResponse(status_code=201, content={"message": "Task added successfully", "taskId": task_id})

    except HTTPException:    except HTTPException:

        raise        raise

    except Exception as e:    except Exception as e:

        print(f"Error in add_task: {e}")        print(f"Error in add_task: {e}")

        raise HTTPException(status_code=500, detail="An internal error occurred while adding the task.")        raise HTTPException(status_code=500, detail="An internal error occurred while adding the task.")



@app.get("/api/schedule")@app.get("/api/schedule")

async def get_schedule(date: str):async def get_schedule(date: str):

    try:    try:

        query_date = datetime.strptime(date, '%Y-%m-%d').date()        query_date = datetime.strptime(date, '%Y-%m-%d').date()

        with driver.session() as session:        with driver.session() as session:

            result = session.run("MATCH (:Day {date: date($d)})-[:HAS_TASK]->(t:Task) RETURN t ORDER BY t.startTime", d=query_date)            result = session.run("MATCH (:Day {date: date($d)})-[:HAS_TASK]->(t:Task) RETURN t ORDER BY t.startTime", d=query_date)

            tasks = [neo4j_to_serializable(record['t']) for record in result]            tasks = [neo4j_to_serializable(record['t']) for record in result]

        return {"date": date, "tasks": tasks}        return {"date": date, "tasks": tasks}

    except Exception as e:    except Exception as e:

        print(f"Error in get_schedule: {e}")        print(f"Error in get_schedule: {e}")

        raise HTTPException(status_code=500, detail="Failed to retrieve schedule.")        raise HTTPException(status_code=500, detail="Failed to retrieve schedule.")



@app.get("/api/upcoming-deadlines")@app.get("/api/upcoming-deadlines")

async def get_upcoming_deadlines():async def get_upcoming_deadlines():

    try:    try:

        today = datetime.utcnow().date()        today = datetime.utcnow().date()

        # Fetch pending tasks and do robust date parsing in Python because stored dueDate        # Fetch pending tasks and do robust date parsing in Python because stored dueDate

        # may be a Neo4j Date, a datetime string, or absent. We consider dueDate, endTime,        # may be a Neo4j Date, a datetime string, or absent. We consider dueDate, endTime,

        # then startTime as fallbacks.        # then startTime as fallbacks.

        with driver.session() as session:        with driver.session() as session:

            result = session.run("MATCH (t:Task) WHERE t.status = 'pending' RETURN t")            result = session.run("MATCH (t:Task) WHERE t.status = 'pending' RETURN t")

            raw = [r['t'] for r in result]            raw = [r['t'] for r in result]



        entries = []        entries = []

        for t in raw:        for t in raw:

            try:            try:

                task_obj = {k: neo4j_to_serializable(v) for k, v in dict(t).items()} if hasattr(t, 'items') else dict(t)                task_obj = {k: neo4j_to_serializable(v) for k, v in dict(t).items()} if hasattr(t, 'items') else dict(t)

                # pick a candidate datetime field in order of preference                # pick a candidate datetime field in order of preference

                cand = task_obj.get('dueDate') or task_obj.get('endTime') or task_obj.get('startTime')                cand = task_obj.get('dueDate') or task_obj.get('endTime') or task_obj.get('startTime')

                dt = _parse_iso_to_dt(cand)                dt = _parse_iso_to_dt(cand)

                if not dt:                if not dt:

                    continue                    continue

                if dt.date() >= today:                if dt.date() >= today:

                    entries.append({'title': task_obj.get('title'), 'dueDate': dt.isoformat(), 'priority': task_obj.get('priority') or 'medium'})                    entries.append({'title': task_obj.get('title'), 'dueDate': dt.isoformat(), 'priority': task_obj.get('priority') or 'medium'})

            except Exception as e:            except Exception as e:

                print(f"Skipping task when building deadlines list due to parse error: {e}")                print(f"Skipping task when building deadlines list due to parse error: {e}")

                continue                continue



        # sort by datetime ascending and limit        # sort by datetime ascending and limit

        entries = sorted(entries, key=lambda x: _parse_iso_to_dt(x['dueDate']) or datetime.max)[:5]        entries = sorted(entries, key=lambda x: _parse_iso_to_dt(x['dueDate']) or datetime.max)[:5]

        return {"deadlines": entries}        return {"deadlines": entries}

    except Exception as e:    except Exception as e:

        print(f"Error fetching deadlines: {e}")        print(f"Error fetching deadlines: {e}")

        raise HTTPException(status_code=500, detail="Could not fetch upcoming deadlines")        raise HTTPException(status_code=500, detail="Could not fetch upcoming deadlines")



@app.get("/api/quote")@app.get("/api/quote")

async def get_quote():async def get_quote():

    # A curated list of study-motivation quotes    # A curated list of study-motivation quotes

    study_quotes = [    study_quotes = [

        {"content": "The beautiful thing about learning is that no one can take it away from you.", "author": "B.B. King"},        {"content": "The beautiful thing about learning is that no one can take it away from you.", "author": "B.B. King"},

        {"content": "Live as if you were to die tomorrow. Learn as if you were to live forever.", "author": "Mahatma Gandhi"},        {"content": "Live as if you were to die tomorrow. Learn as if you were to live forever.", "author": "Mahatma Gandhi"},

        {"content": "The expert in anything was once a beginner.", "author": "Helen Hayes"},        {"content": "The expert in anything was once a beginner.", "author": "Helen Hayes"},

        {"content": "Success is the sum of small efforts, repeated day in and day out.", "author": "Robert Collier"},        {"content": "Success is the sum of small efforts, repeated day in and day out.", "author": "Robert Collier"},

        {"content": "There are no shortcuts to any place worth going.", "author": "Beverly Sills"},        {"content": "There are no shortcuts to any place worth going.", "author": "Beverly Sills"},

        {"content": "The only place where success comes before work is in the dictionary.", "author": "Vidal Sassoon"},        {"content": "The only place where success comes before work is in the dictionary.", "author": "Vidal Sassoon"},

        {"content": "I find that the harder I work, the more luck I seem to have.", "author": "Thomas Jefferson"},        {"content": "I find that the harder I work, the more luck I seem to have.", "author": "Thomas Jefferson"},

        {"content": "Don't wish it were easier; wish you were better.", "author": "Jim Rohn"},        {"content": "Don't wish it were easier; wish you were better.", "author": "Jim Rohn"},

        {"content": "Education is the passport to the future, for tomorrow belongs to those who prepare for it today.", "author": "Malcolm X"},        {"content": "Education is the passport to the future, for tomorrow belongs to those who prepare for it today.", "author": "Malcolm X"},

        {"content": "It does not matter how slowly you go as long as you do not stop.", "author": "Confucius"}        {"content": "It does not matter how slowly you go as long as you do not stop.", "author": "Confucius"}

    ]    ]

    return random.choice(study_quotes)    return random.choice(study_quotes)



@app.get('/api/recommend-tasks')@app.get('/api/recommend-tasks')

async def recommend_tasks(topic: str | None = None):async def recommend_tasks(topic: str | None = None):

    try:    try:

        forced = topic        forced = topic

        if forced:        if forced:

            t = forced.lower()            t = forced.lower()

            # If client explicitly requests 'projects', return split subtasks for each project task            # If client explicitly requests 'projects', return split subtasks for each project task

            if t == 'projects' or t == 'project':            if t == 'projects' or t == 'project':

                recs = []                recs = []

                try:                try:

                    with driver.session() as session:                    with driver.session() as session:

                        res = session.run("MATCH (t:Task) WHERE toLower(coalesce(t.category,'')) CONTAINS 'project' OR toLower(coalesce(t.title,'')) CONTAINS 'project' RETURN t.id as id, t.title as title, t.estimatedDuration as est LIMIT 20")                        res = session.run("MATCH (t:Task) WHERE toLower(coalesce(t.category,'')) CONTAINS 'project' OR toLower(coalesce(t.title,'')) CONTAINS 'project' RETURN t.id as id, t.title as title, t.estimatedDuration as est LIMIT 20")

                        rows = [r.data() for r in res]                        rows = [r.data() for r in res]

                    for r in rows:                    for r in rows:

                        tid = r.get('id')                        tid = r.get('id')

                        title = r.get('title') or 'Untitled Project'                        title = r.get('title') or 'Untitled Project'

                        est = None                        est = None

                        try:                        try:

                            est = int(r.get('est')) if r.get('est') is not None else None                            est = int(r.get('est')) if r.get('est') is not None else None

                        except Exception:                        except Exception:

                            try:                            try:

                                est = int(float(r.get('est')))                                est = int(float(r.get('est')))

                            except Exception:                            except Exception:

                                est = None                                est = None

                        base = est or 60                        base = est or 60

                        plan = max(10, int(round(base * 0.2)))                        plan = max(10, int(round(base * 0.2)))

                        implement = max(15, int(round(base * 0.6)))                        implement = max(15, int(round(base * 0.6)))

                        verify = max(5, int(round(base * 0.2)))                        verify = max(5, int(round(base * 0.2)))

                        recs.append({'label': f'Plan — {title}', 'type': 'plan', 'estimate_minutes': plan, 'taskId': tid, 'taskTitle': title})                        recs.append({'label': f'Plan — {title}', 'type': 'plan', 'estimate_minutes': plan, 'taskId': tid, 'taskTitle': title})

                        recs.append({'label': f'Implement — {title}', 'type': 'implement', 'estimate_minutes': implement, 'taskId': tid, 'taskTitle': title})                        recs.append({'label': f'Implement — {title}', 'type': 'implement', 'estimate_minutes': implement, 'taskId': tid, 'taskTitle': title})

                        recs.append({'label': f'Verify — {title}', 'type': 'verify', 'estimate_minutes': verify, 'taskId': tid, 'taskTitle': title})                        recs.append({'label': f'Verify — {title}', 'type': 'verify', 'estimate_minutes': verify, 'taskId': tid, 'taskTitle': title})

                except Exception as e:                except Exception as e:

                    print(f"Error generating project splits for forced topic: {e}")                    print(f"Error generating project splits for forced topic: {e}")

                return {'topic': t, 'recommendations': recs}                return {'topic': t, 'recommendations': recs}



            # otherwise, if client explicitly requests a topic, provide structured recommendations            # otherwise, if client explicitly requests a topic, provide structured recommendations

            recs = _recommendations_for_topic(t)            recs = _recommendations_for_topic(t)

            return {'topic': t, 'recommendations': recs}            return {'topic': t, 'recommendations': recs}



        # pick a seed task to detect topic; if none, default to 'general'        # pick a seed task to detect topic; if none, default to 'general'

        with driver.session() as session:        with driver.session() as session:

            result = session.run("MATCH (t:Task) WHERE t.status='pending' AND t.description IS NOT NULL RETURN t.description AS desc, t.title AS title LIMIT 1")            result = session.run("MATCH (t:Task) WHERE t.status='pending' AND t.description IS NOT NULL RETURN t.description AS desc, t.title AS title LIMIT 1")

            seed = result.single()            seed = result.single()



        seed_text = ''        seed_text = ''

        if seed:        if seed:

            seed_text = ((seed.get('title') or '') + '\n' + (seed.get('desc') or ''))[:512]            seed_text = ((seed.get('title') or '') + '\n' + (seed.get('desc') or ''))[:512]



        topic_detected = None        topic_detected = None

        # Topic detection based purely on data heuristics (do not rely on external zero-shot classifiers)        # Topic detection based purely on data heuristics (do not rely on external zero-shot classifiers)

        # We look for keywords in the seed text and infer the topic. This avoids external model calls.        # We look for keywords in the seed text and infer the topic. This avoids external model calls.



        # Fallback keyword heuristics        # Fallback keyword heuristics

        if not topic_detected:        if not topic_detected:

            s = (seed_text or '').lower()            s = (seed_text or '').lower()

            if any(k in s for k in ['dsa', 'data structure', 'algorithm', 'leetcode', 'gfg']):            if any(k in s for k in ['dsa', 'data structure', 'algorithm', 'leetcode', 'gfg']):

                topic_detected = 'dsa'                topic_detected = 'dsa'

            elif any(k in s for k in ['aptitude', 'quant', 'logical', 'reasoning']):            elif any(k in s for k in ['aptitude', 'quant', 'logical', 'reasoning']):

                topic_detected = 'aptitude'                topic_detected = 'aptitude'

            elif any(k in s for k in ['system design', 'architecture', 'scalability']):            elif any(k in s for k in ['system design', 'architecture', 'scalability']):

                topic_detected = 'system design'                topic_detected = 'system design'

            elif any(k in s for k in ['machine learning', 'ml', 'model', 'training']):            elif any(k in s for k in ['machine learning', 'ml', 'model', 'training']):

                topic_detected = 'machine learning'                topic_detected = 'machine learning'

            elif any(k in s for k in ['project', 'implement', 'build']):            elif any(k in s for k in ['project', 'implement', 'build']):

                topic_detected = 'projects'                topic_detected = 'projects'

            else:            else:

                topic_detected = 'general'                topic_detected = 'general'



        # If detected topic is projects, automatically generate split recommendations        # If detected topic is projects, automatically generate split recommendations

        if topic_detected and topic_detected.lower() in ('projects', 'project'):        if topic_detected and topic_detected.lower() in ('projects', 'project'):

            # reuse forced path logic quickly            # reuse forced path logic quickly

            recs = []            recs = []

            try:            try:

                with driver.session() as session:                with driver.session() as session:

                    res = session.run("MATCH (t:Task) WHERE toLower(coalesce(t.category,'')) CONTAINS 'project' OR toLower(coalesce(t.title,'')) CONTAINS 'project' RETURN t.id as id, t.title as title, t.estimatedDuration as est LIMIT 20")                    res = session.run("MATCH (t:Task) WHERE toLower(coalesce(t.category,'')) CONTAINS 'project' OR toLower(coalesce(t.title,'')) CONTAINS 'project' RETURN t.id as id, t.title as title, t.estimatedDuration as est LIMIT 20")

                    rows = [r.data() for r in res]                    rows = [r.data() for r in res]

                for r in rows:                for r in rows:

                    tid = r.get('id')                    tid = r.get('id')

                    title = r.get('title') or 'Untitled Project'                    title = r.get('title') or 'Untitled Project'

                    est = None                    est = None

                    try:                    try:

                        est = int(r.get('est')) if r.get('est') is not None else None                        est = int(r.get('est')) if r.get('est') is not None else None

                    except Exception:                    except Exception:

                        try:                        try:

                            est = int(float(r.get('est')))                            est = int(float(r.get('est')))

                        except Exception:                        except Exception:

                            est = None                            est = None

                    base = est or 60                    base = est or 60

                    plan = max(10, int(round(base * 0.2)))                    plan = max(10, int(round(base * 0.2)))

                    implement = max(15, int(round(base * 0.6)))                    implement = max(15, int(round(base * 0.6)))

                    verify = max(5, int(round(base * 0.2)))                    verify = max(5, int(round(base * 0.2)))

                    recs.append({'label': f'Plan — {title}', 'type': 'plan', 'estimate_minutes': plan, 'taskId': tid, 'taskTitle': title})                    recs.append({'label': f'Plan — {title}', 'type': 'plan', 'estimate_minutes': plan, 'taskId': tid, 'taskTitle': title})

                    recs.append({'label': f'Implement — {title}', 'type': 'implement', 'estimate_minutes': implement, 'taskId': tid, 'taskTitle': title})                    recs.append({'label': f'Implement — {title}', 'type': 'implement', 'estimate_minutes': implement, 'taskId': tid, 'taskTitle': title})

                    recs.append({'label': f'Verify — {title}', 'type': 'verify', 'estimate_minutes': verify, 'taskId': tid, 'taskTitle': title})                    recs.append({'label': f'Verify — {title}', 'type': 'verify', 'estimate_minutes': verify, 'taskId': tid, 'taskTitle': title})

            except Exception as e:            except Exception as e:

                print(f"Error generating project splits for detected topic: {e}")                print(f"Error generating project splits for detected topic: {e}")

            return {'topic': topic_detected, 'recommendations': recs}            return {'topic': topic_detected, 'recommendations': recs}



        # small mapping of short recommendation keywords per topic (structured)        # small mapping of short recommendation keywords per topic (structured)

        short_recs = _recommendations_for_topic(topic_detected)        short_recs = _recommendations_for_topic(topic_detected)

        return {'topic': topic_detected, 'recommendations': short_recs}        return {'topic': topic_detected, 'recommendations': short_recs}

    except Exception as e:    except Exception as e:

        print(f"Error in recommend_tasks: {e}")        print(f"Error in recommend_tasks: {e}")

        raise HTTPException(status_code=500, detail='Could not generate topic recommendations.')        raise HTTPException(status_code=500, detail='Could not generate topic recommendations.')





def _recommendations_for_topic(topic_detected: str):def _recommendations_for_topic(topic_detected: str):

    """Dynamically generate short recommendations for the detected topic.    """Dynamically generate short recommendations for the detected topic.



    Strategy:    Strategy:

    - Query tasks matching the topic (category/title/description).    - Query tasks matching the topic (category/title/description).

    - Extract top keywords from their title/description (use spaCy if available, else simple token frequency).    - Extract top keywords from their title/description (use spaCy if available, else simple token frequency).

    - Produce recommendation labels such as 'practice {kw}', 'read about {kw}', 'implement {kw}'.    - Produce recommendation labels such as 'practice {kw}', 'read about {kw}', 'implement {kw}'.

    - Estimate minutes by scaling the average estimatedDuration of matching tasks. Fall back to defaults.    - Estimate minutes by scaling the average estimatedDuration of matching tasks. Fall back to defaults.

    """    """

    # compute average estimatedDuration for matching tasks    # compute average estimatedDuration for matching tasks

    avg_dur = None    avg_dur = None

    texts = []    texts = []

    try:    try:

        with driver.session() as session:        with driver.session() as session:

            q = """            q = """

            MATCH (t:Task)            MATCH (t:Task)

            WHERE t.status = 'pending' AND (            WHERE t.status = 'pending' AND (

                toLower(coalesce(t.category, '')) = $topic OR                toLower(coalesce(t.category, '')) = $topic OR

                toLower(coalesce(t.title, '')) CONTAINS $topic OR                toLower(coalesce(t.title, '')) CONTAINS $topic OR

                toLower(coalesce(t.description, '')) CONTAINS $topic)                toLower(coalesce(t.description, '')) CONTAINS $topic)

            RETURN t.title AS title, t.description AS description, t.estimatedDuration AS est            RETURN t.title AS title, t.description AS description, t.estimatedDuration AS est

            """            """

            res = session.run(q, topic=topic_detected)            res = session.run(q, topic=topic_detected)

            vals = []            vals = []

            for r in res:            for r in res:

                title = r.get('title') or ''                title = r.get('title') or ''

                desc = r.get('description') or ''                desc = r.get('description') or ''

                if title:                if title:

                    texts.append(str(title))                    texts.append(str(title))

                if desc:                if desc:

                    texts.append(str(desc))                    texts.append(str(desc))

                est = r.get('est')                est = r.get('est')

                if est is None:                if est is None:

                    continue                    continue

                try:                try:

                    vals.append(int(est))                    vals.append(int(est))

                except Exception:                except Exception:

                    try:                    try:

                        vals.append(int(float(est)))                        vals.append(int(float(est)))

                    except Exception:                    except Exception:

                        continue                        continue

            if vals:            if vals:

                avg_dur = sum(vals) / len(vals)                avg_dur = sum(vals) / len(vals)

    except Exception as e:    except Exception as e:

        print(f"Warning: could not gather task data for topic {topic_detected}: {e}")        print(f"Warning: could not gather task data for topic {topic_detected}: {e}")



    # extract keywords    # extract keywords

    keywords = []    keywords = []

    try:    try:

        big_text = '\n'.join(texts)        big_text = '\n'.join(texts)

        if big_text.strip():        if big_text.strip():

            if nlp:            if nlp:

                doc = nlp(big_text)                doc = nlp(big_text)

                # collect noun lemmas                # collect noun lemmas

                lemmas = [token.lemma_.lower() for token in doc if token.pos_ in ('NOUN', 'PROPN') and len(token.lemma_) > 2]                lemmas = [token.lemma_.lower() for token in doc if token.pos_ in ('NOUN', 'PROPN') and len(token.lemma_) > 2]

                # frequency                # frequency

                freq = {}                freq = {}

                for l in lemmas:                for l in lemmas:

                    freq[l] = freq.get(l, 0) + 1                    freq[l] = freq.get(l, 0) + 1

                keywords = sorted(freq.keys(), key=lambda k: -freq[k])[:3]                keywords = sorted(freq.keys(), key=lambda k: -freq[k])[:3]

            else:            else:

                # simple fallback: split on non-word, count tokens                # simple fallback: split on non-word, count tokens

                import re                import re

                toks = re.findall(r"\w{3,}", big_text.lower())                toks = re.findall(r"\w{3,}", big_text.lower())

                freq = {}                freq = {}

                for t in toks:                for t in toks:

                    if t in ('the', 'and', 'for', 'with', 'that', 'this', 'project'):                    if t in ('the', 'and', 'for', 'with', 'that', 'this', 'project'):

                        continue                        continue

                    freq[t] = freq.get(t, 0) + 1                    freq[t] = freq.get(t, 0) + 1

                keywords = sorted(freq.keys(), key=lambda k: -freq[k])[:3]                keywords = sorted(freq.keys(), key=lambda k: -freq[k])[:3]

    except Exception as e:    except Exception as e:

        print(f"Keyword extraction failed: {e}")        print(f"Keyword extraction failed: {e}")



    # if no keywords found, fall back to using the topic itself    # if no keywords found, fall back to using the topic itself

    if not keywords:    if not keywords:

        keywords = [topic_detected]        keywords = [topic_detected]



    # compose recommendation labels    # compose recommendation labels

    # Choose templates based on the detected topic to avoid nonsensical combos    # Choose templates based on the detected topic to avoid nonsensical combos

    if topic_detected and topic_detected.lower() in ('projects', 'project'):    if topic_detected and topic_detected.lower() in ('projects', 'project'):

        templates = ['implement {}', 'break {}', 'write {}']        templates = ['implement {}', 'break {}', 'write {}']

    elif topic_detected and topic_detected.lower() in ('dsa', 'algorithms', 'data structure', 'algorithm'):    elif topic_detected and topic_detected.lower() in ('dsa', 'algorithms', 'data structure', 'algorithm'):

        templates = ['practice {}', 'review {}', 'mock {}']        templates = ['practice {}', 'review {}', 'mock {}']

    elif topic_detected and topic_detected.lower() in ('aptitude',):    elif topic_detected and topic_detected.lower() in ('aptitude',):

        templates = ['timed {}', 'practice {}', 'review {}']        templates = ['timed {}', 'practice {}', 'review {}']

    else:    else:

        templates = ['practice {}', 'read about {}', 'implement {}']        templates = ['practice {}', 'read about {}', 'implement {}']

    # scale factors per action type    # scale factors per action type

    action_scale = {'practice': 1.0, 'read': 0.6, 'implement': 1.5}    action_scale = {'practice': 1.0, 'read': 0.6, 'implement': 1.5}



    recs = []    recs = []

    for i, kw in enumerate(keywords):    for i, kw in enumerate(keywords):

        tmpl = templates[i % len(templates)]        tmpl = templates[i % len(templates)]

        label = tmpl.format(kw)        label = tmpl.format(kw)

        action = tmpl.split()[0]        action = tmpl.split()[0]

        # If the target equals the topic (e.g. 'projects') and the template uses 'practice',        # If the target equals the topic (e.g. 'projects') and the template uses 'practice',

        # swap to a more sensible action for that target.        # swap to a more sensible action for that target.

        if topic_detected and kw and kw.lower() in (topic_detected.lower(), 'project', 'projects'):        if topic_detected and kw and kw.lower() in (topic_detected.lower(), 'project', 'projects'):

            if action.lower() == 'practice':            if action.lower() == 'practice':

                # prefer implementing or breaking down projects                # prefer implementing or breaking down projects

                if 'implement {}' in templates:                if 'implement {}' in templates:

                    label = ('implement {}').format(kw)                    label = ('implement {}').format(kw)

                    action = 'implement'                    action = 'implement'

                else:                else:

                    label = ('break {}').format(kw)                    label = ('break {}').format(kw)

                    action = 'break'                    action = 'break'

        if avg_dur:        if avg_dur:

            est = max(5, int(round(avg_dur * action_scale.get(action, 1.0))))            est = max(5, int(round(avg_dur * action_scale.get(action, 1.0))))

        else:        else:

            # default reasonable values            # default reasonable values

            est = 30 if action == 'practice' else (20 if action == 'read' else 60)            est = 30 if action == 'practice' else (20 if action == 'read' else 60)

        # classification: type and confidence        # classification: type and confidence

        rec_type = action        rec_type = action

        confidence = 1.0        confidence = 1.0



        # classification heuristics (no external classifier): infer from action word or keywords        # classification heuristics (no external classifier): infer from action word or keywords

        l = label.lower()        l = label.lower()

        if l.startswith('practice') or 'practice' in l or 'quiz' in l or 'mock' in l:        if l.startswith('practice') or 'practice' in l or 'quiz' in l or 'mock' in l:

            rec_type = 'practice'            rec_type = 'practice'

        elif l.startswith('read') or 'read' in l or 'study' in l or 'article' in l:        elif l.startswith('read') or 'read' in l or 'study' in l or 'article' in l:

            rec_type = 'read'            rec_type = 'read'

        elif l.startswith('implement') or 'implement' in l or 'build' in l or 'project' in l:        elif l.startswith('implement') or 'implement' in l or 'build' in l or 'project' in l:

            rec_type = 'implement'            rec_type = 'implement'

        elif l.startswith('write') or 'write' in l or 'document' in l or 'readme' in l:        elif l.startswith('write') or 'write' in l or 'document' in l or 'readme' in l:

            rec_type = 'write'            rec_type = 'write'

        elif l.startswith('break') or 'break' in l:        elif l.startswith('break') or 'break' in l:

            rec_type = 'break'            rec_type = 'break'

        else:        else:

            rec_type = action            rec_type = action

        confidence = 0.6        confidence = 0.6



        recs.append({'label': label, 'estimate_minutes': est, 'type': rec_type, 'confidence': round(confidence, 3)})        recs.append({'label': label, 'estimate_minutes': est, 'type': rec_type, 'confidence': round(confidence, 3)})



    return recs    return recs





@app.get('/api/health')@app.get('/api/health')

async def api_health():async def api_health():

    """Lightweight health endpoint useful in dev to check model/loading status."""    """Lightweight health endpoint useful in dev to check model/loading status."""

    try:    try:

        return {        return {

            'status': 'ok',            'status': 'ok',

            'model_loaded': model is not None,            'model_loaded': model is not None,

            'embed_model': EMBED_MODEL if 'EMBED_MODEL' in globals() else None,            'embed_model': EMBED_MODEL if 'EMBED_MODEL' in globals() else None,

            'classifier_model_configured': bool(CLASSIFIER_MODEL),            'classifier_model_configured': bool(CLASSIFIER_MODEL),

            'classifier_model_loaded': classifier_model is not None,            'classifier_model_loaded': classifier_model is not None,

            'skip_model_load_env': os.getenv('SKIP_MODEL_LOAD', '0') == '1',            'skip_model_load_env': os.getenv('SKIP_MODEL_LOAD', '0') == '1',

            'cache_meta': CACHE_META            'cache_meta': CACHE_META

        }        }

    except Exception as e:    except Exception as e:

        print(f"Health check failed: {e}")        print(f"Health check failed: {e}")

        raise HTTPException(status_code=500, detail='Health check failed')        raise HTTPException(status_code=500, detail='Health check failed')





def _priority_value(p):def _priority_value(p):

    """Return numeric sort value for priority strings."""    """Return numeric sort value for priority strings."""

    return {'high': 1, 'medium': 2, 'low': 3}.get(p, 2)    return {'high': 1, 'medium': 2, 'low': 3}.get(p, 2)





def _ai_scores(task):def _ai_scores(task):

    """Return a dict with ai-derived scores for urgency/importance in [0,1].    """Return a dict with ai-derived scores for urgency/importance in [0,1].



    Uses the zero-shot `category_classifier` when available. Returns    Uses the zero-shot `category_classifier` when available. Returns

    {'urgent': score, 'important': score}. If classifier isn't available    {'urgent': score, 'important': score}. If classifier isn't available

    or fails, returns None.    or fails, returns None.

    """    """

    # Use prototype similarity. Prefer classifier_model for encoding prototypes if available,    # Use prototype similarity. Prefer classifier_model for encoding prototypes if available,

    # otherwise use the main embedding model. If neither model is available, return None.    # otherwise use the main embedding model. If neither model is available, return None.

    if (not model and not classifier_model) or not label_prototypes:    if (not model and not classifier_model) or not label_prototypes:

        return None        return None

    try:    try:

        text = ((task.get('title') or '') + '\n' + (task.get('description') or ''))[:1024]        text = ((task.get('title') or '') + '\n' + (task.get('description') or ''))[:1024]

        if not text.strip():        if not text.strip():

            return None            return None

        encoder = classifier_model or model        encoder = classifier_model or model

        emb = encoder.encode([text])[0]        emb = encoder.encode([text])[0]

        # compute cosine similarity helper        # compute cosine similarity helper

        def cos(a, b):        def cos(a, b):

            import math            import math

            da = sum(x*x for x in a) ** 0.5            da = sum(x*x for x in a) ** 0.5

            db = sum(x*x for x in b) ** 0.5            db = sum(x*x for x in b) ** 0.5

            if da == 0 or db == 0:            if da == 0 or db == 0:

                return 0.0                return 0.0

            return sum(x*y for x, y in zip(a, b)) / (da * db)            return sum(x*y for x, y in zip(a, b)) / (da * db)

        # label_prototypes were created from whichever model was available at startup        # label_prototypes were created from whichever model was available at startup

        u_score = max(0.0, cos(emb, label_prototypes.get('urgent', emb)))        u_score = max(0.0, cos(emb, label_prototypes.get('urgent', emb)))

        i_score = max(0.0, cos(emb, label_prototypes.get('important', emb)))        i_score = max(0.0, cos(emb, label_prototypes.get('important', emb)))

        return {'urgent': float(u_score), 'important': float(i_score)}        return {'urgent': float(u_score), 'important': float(i_score)}

    except Exception as e:    except Exception as e:

        print(f"AI scoring failed: {e}")        print(f"AI scoring failed: {e}")

        return None        return None





def _overlaps(a_start, a_end, b_start, b_end):def _overlaps(a_start, a_end, b_start, b_end):

    """Return True if two datetime intervals overlap. Treat None as open-ended.    """Return True if two datetime intervals overlap. Treat None as open-ended.



    Accepts ISO strings or datetime objects.    Accepts ISO strings or datetime objects.

    """    """

    try:    try:

        a_s = _parse_iso_to_dt(a_start)        a_s = _parse_iso_to_dt(a_start)

        a_e = _parse_iso_to_dt(a_end)        a_e = _parse_iso_to_dt(a_end)

        b_s = _parse_iso_to_dt(b_start)        b_s = _parse_iso_to_dt(b_start)

        b_e = _parse_iso_to_dt(b_end)        b_e = _parse_iso_to_dt(b_end)

        if not a_s or not a_e or not b_s or not b_e:        if not a_s or not a_e or not b_s or not b_e:

            return False            return False

        return not (a_e <= b_s or b_e <= a_s)        return not (a_e <= b_s or b_e <= a_s)

    except Exception:    except Exception:

        return False        return False





def _partial_order_plan(items):def _partial_order_plan(items):

    """Try to order items by soft precedence: urgent-important first, then important, then others.    """Try to order items by soft precedence: urgent-important first, then important, then others.



    This is a simple partial ordering implemented via stable sort using multiple keys.    This is a simple partial ordering implemented via stable sort using multiple keys.

    Returns a re-ordered list.    Returns a re-ordered list.

    """    """

    def key_fn(it):    def key_fn(it):

        # Higher urgency/importance first; earlier deadline first        # Higher urgency/importance first; earlier deadline first

        ai_u = (it.get('ai_scores') or {}).get('urgent', 0.0)        ai_u = (it.get('ai_scores') or {}).get('urgent', 0.0)

        ai_i = (it.get('ai_scores') or {}).get('important', 0.0)        ai_i = (it.get('ai_scores') or {}).get('important', 0.0)

        pval = _priority_value(it.get('priority'))        pval = _priority_value(it.get('priority'))

        dl = _parse_iso_to_dt(it.get('deadline'))        dl = _parse_iso_to_dt(it.get('deadline'))

        dl_sort = dl if dl else datetime.max        dl_sort = dl if dl else datetime.max

        # negative ai scores to sort descending        # negative ai scores to sort descending

        return (-ai_u, -ai_i, dl_sort, pval)        return (-ai_u, -ai_i, dl_sort, pval)



    return sorted(items, key=key_fn)    return sorted(items, key=key_fn)





def _greedy_by_deadline(items, max_horizon=None):def _greedy_by_deadline(items, max_horizon=None):

    """Greedy schedule: pick earliest deadline items first, skipping those that overlap previously picked items.    """Greedy schedule: pick earliest deadline items first, skipping those that overlap previously picked items.



    Returns scheduled list.    Returns scheduled list.

    """    """

    scheduled = []    scheduled = []

    # sort by deadline asc, then priority    # sort by deadline asc, then priority

    def key_deadline(it):    def key_deadline(it):

        dl = _parse_iso_to_dt(it.get('deadline'))        dl = _parse_iso_to_dt(it.get('deadline'))

        dl_sort = dl if dl else datetime.max        dl_sort = dl if dl else datetime.max

        return (dl_sort, _priority_value(it.get('priority')))        return (dl_sort, _priority_value(it.get('priority')))



    candidates = sorted(items, key=key_deadline)    candidates = sorted(items, key=key_deadline)

    for c in candidates:    for c in candidates:

        conflict = False        conflict = False

        for s in scheduled:        for s in scheduled:

            if _overlaps(c.get('startTime'), c.get('endTime'), s.get('startTime'), s.get('endTime')):            if _overlaps(c.get('startTime'), c.get('endTime'), s.get('startTime'), s.get('endTime')):

                conflict = True                conflict = True

                break                break

        if not conflict:        if not conflict:

            scheduled.append(c)            scheduled.append(c)

    return scheduled    return scheduled





def _parse_iso_to_dt(val):def _parse_iso_to_dt(val):

    """Parse ISO string or datetime/date-like into a naive UTC datetime.    """Parse ISO string or datetime/date-like into a naive UTC datetime.



    Returns None if parsing fails.    Returns None if parsing fails.

    """    """

    if not val:    if not val:

        return None        return None

    try:    try:

        if isinstance(val, datetime):        if isinstance(val, datetime):

            dt = val            dt = val

        else:        else:

            # Some values may be dates (YYYY-MM-DD) or datetimes            # Some values may be dates (YYYY-MM-DD) or datetimes

            if isinstance(val, str) and len(val) == 10 and val.count('-') == 2:            if isinstance(val, str) and len(val) == 10 and val.count('-') == 2:

                # date only                # date only

                dt = datetime.fromisoformat(val + 'T00:00:00')                dt = datetime.fromisoformat(val + 'T00:00:00')

            else:            else:

                dt = datetime.fromisoformat(str(val))                dt = datetime.fromisoformat(str(val))

        # Normalize to UTC-naive for consistent comparisons        # Normalize to UTC-naive for consistent comparisons

        if dt.tzinfo:        if dt.tzinfo:

            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)

        return dt        return dt

    except Exception:    except Exception:

        return None        return None





def infer_finish_to_start_relations(max_distance_hours: int = 72):def infer_finish_to_start_relations(max_distance_hours: int = 72):

    """Infer finish-to-start precedence relations between tasks and create a lightweight relationship in Neo4j.    """Infer finish-to-start precedence relations between tasks and create a lightweight relationship in Neo4j.



    Heuristic: if Task A ends before Task B starts and they are in the same category/project or titles share keywords,    Heuristic: if Task A ends before Task B starts and they are in the same category/project or titles share keywords,

    and the gap between A.end and B.start is <= max_distance_hours, create (A)-[:FINISH_TO_START]->(B).    and the gap between A.end and B.start is <= max_distance_hours, create (A)-[:FINISH_TO_START]->(B).

    The function is idempotent and will not duplicate relationships if they exist.    The function is idempotent and will not duplicate relationships if they exist.

    """    """

    try:    try:

        with driver.session() as session:        with driver.session() as session:

            # Gather pending tasks with start/end            # Gather pending tasks with start/end

            res = session.run("MATCH (t:Task) WHERE t.status='pending' AND t.startTime IS NOT NULL AND t.endTime IS NOT NULL RETURN t.id AS id, t.title AS title, t.startTime AS startTime, t.endTime AS endTime, t.category AS category LIMIT 500")            res = session.run("MATCH (t:Task) WHERE t.status='pending' AND t.startTime IS NOT NULL AND t.endTime IS NOT NULL RETURN t.id AS id, t.title AS title, t.startTime AS startTime, t.endTime AS endTime, t.category AS category LIMIT 500")

            rows = [r.data() for r in res]            rows = [r.data() for r in res]

        tasks = []        tasks = []

        for r in rows:        for r in rows:

            sid = r.get('startTime')            sid = r.get('startTime')

            eid = r.get('endTime')            eid = r.get('endTime')

            sdt = _parse_iso_to_dt(sid)            sdt = _parse_iso_to_dt(sid)

            edt = _parse_iso_to_dt(eid)            edt = _parse_iso_to_dt(eid)

            if not sdt or not edt:            if not sdt or not edt:

                continue                continue

            tasks.append({'id': r.get('id'), 'title': r.get('title') or '', 'start': sdt, 'end': edt, 'category': (r.get('category') or '').lower()})            tasks.append({'id': r.get('id'), 'title': r.get('title') or '', 'start': sdt, 'end': edt, 'category': (r.get('category') or '').lower()})



        # simple pairwise check        # simple pairwise check

        for a in tasks:        for a in tasks:

            for b in tasks:            for b in tasks:

                if a['id'] == b['id']:                if a['id'] == b['id']:

                    continue                    continue

                # if A ends before B starts and within the window                # if A ends before B starts and within the window

                if a['end'] <= b['start']:                if a['end'] <= b['start']:

                    gap = (b['start'] - a['end']).total_seconds() / 3600.0                    gap = (b['start'] - a['end']).total_seconds() / 3600.0

                    if gap <= max_distance_hours:                    if gap <= max_distance_hours:

                        # category/title similarity heuristic                        # category/title similarity heuristic

                        if a['category'] and a['category'] == b['category']:                        if a['category'] and a['category'] == b['category']:

                            try:                            try:

                                with driver.session() as session:                                with driver.session() as session:

                                    session.run("MATCH (a:Task {id:$aid}), (b:Task {id:$bid}) MERGE (a)-[:FINISH_TO_START]->(b)", aid=a['id'], bid=b['id'])                                    session.run("MATCH (a:Task {id:$aid}), (b:Task {id:$bid}) MERGE (a)-[:FINISH_TO_START]->(b)", aid=a['id'], bid=b['id'])

                            except Exception as e:                            except Exception as e:

                                print(f"Warning: could not create relation {a['id']}->{b['id']}: {e}")                                print(f"Warning: could not create relation {a['id']}->{b['id']}: {e}")

                        else:                        else:

                            # title keyword overlap                            # title keyword overlap

                            atoks = set([t for t in a['title'].lower().split() if len(t) > 3])                            atoks = set([t for t in a['title'].lower().split() if len(t) > 3])

                            btoks = set([t for t in b['title'].lower().split() if len(t) > 3])                            btoks = set([t for t in b['title'].lower().split() if len(t) > 3])

                            if atoks & btoks:                            if atoks & btoks:

                                try:                                try:

                                    with driver.session() as session:                                    with driver.session() as session:

                                        session.run("MATCH (a:Task {id:$aid}), (b:Task {id:$bid}) MERGE (a)-[:FINISH_TO_START]->(b)", aid=a['id'], bid=b['id'])                                        session.run("MATCH (a:Task {id:$aid}), (b:Task {id:$bid}) MERGE (a)-[:FINISH_TO_START]->(b)", aid=a['id'], bid=b['id'])

                                except Exception as e:                                except Exception as e:

                                    print(f"Warning: could not create relation {a['id']}->{b['id']}: {e}")                                    print(f"Warning: could not create relation {a['id']}->{b['id']}: {e}")

    except Exception as e:    except Exception as e:

        print(f"Error in infer_finish_to_start_relations: {e}")        print(f"Error in infer_finish_to_start_relations: {e}")





def _predictive_schedule(tasks, horizon_days: int = 7):def _predictive_schedule(tasks, horizon_days: int = 7):

    """Create a predictive schedule for the next `horizon_days` using simple heuristics.    """Create a predictive schedule for the next `horizon_days` using simple heuristics.



    Strategy:    Strategy:

    - Order tasks by (deadline asc, priority, ai_scores urgency/importance)    - Order tasks by (deadline asc, priority, ai_scores urgency/importance)

    - Place tasks into the next available time slots from now, respecting estimatedDuration (minutes) and existing start/end times    - Place tasks into the next available time slots from now, respecting estimatedDuration (minutes) and existing start/end times

    - Respect FINISH_TO_START relations by scheduling dependents after predecessors    - Respect FINISH_TO_START relations by scheduling dependents after predecessors

    Returns a list of scheduled items with suggested start/end datetimes.    Returns a list of scheduled items with suggested start/end datetimes.

    """    """

    now = datetime.utcnow()    now = datetime.utcnow()

    horizon_end = now + timedelta(days=horizon_days)    horizon_end = now + timedelta(days=horizon_days)



    # build map for precedence    # build map for precedence

    pred_map = {}    pred_map = {}

    try:    try:

        with driver.session() as session:        with driver.session() as session:

            rels = session.run("MATCH (a:Task)-[:FINISH_TO_START]->(b:Task) RETURN a.id AS a, b.id AS b")            rels = session.run("MATCH (a:Task)-[:FINISH_TO_START]->(b:Task) RETURN a.id AS a, b.id AS b")

            for r in rels:            for r in rels:

                d = r.data()                d = r.data()

                pred_map.setdefault(d['a'], []).append(d['b'])                pred_map.setdefault(d['a'], []).append(d['b'])

    except Exception:    except Exception:

        pred_map = {}        pred_map = {}



    # helper to get estimated duration (minutes)    # helper to get estimated duration (minutes)

    def get_est(it):    def get_est(it):

        try:        try:

            return int(it.get('estimatedDuration') or it.get('estimated_duration') or 30)            return int(it.get('estimatedDuration') or it.get('estimated_duration') or 30)

        except Exception:        except Exception:

            return 30            return 30



    # sort tasks    # sort tasks

    def sort_key(it):    def sort_key(it):

        dl = _parse_iso_to_dt(it.get('dueDate') or it.get('endTime') or it.get('startTime'))        dl = _parse_iso_to_dt(it.get('dueDate') or it.get('endTime') or it.get('startTime'))

        dl_sort = dl if dl else datetime.max        dl_sort = dl if dl else datetime.max

        p = _priority_value(it.get('priority'))        p = _priority_value(it.get('priority'))

        scores = _ai_scores(it) or {'urgent': 0.0, 'important': 0.0}        scores = _ai_scores(it) or {'urgent': 0.0, 'important': 0.0}

        return (dl_sort, p, -scores.get('urgent', 0.0), -scores.get('important', 0.0))        return (dl_sort, p, -scores.get('urgent', 0.0), -scores.get('important', 0.0))



    tasks_sorted = sorted(tasks, key=sort_key)    tasks_sorted = sorted(tasks, key=sort_key)



    scheduled = []    scheduled = []

    calendar = []  # list of (start,end)    calendar = []  # list of (start,end)



    # incorporate existing tasks into calendar to avoid overlaps    # incorporate existing tasks into calendar to avoid overlaps

    for t in tasks_sorted:    for t in tasks_sorted:

        s = _parse_iso_to_dt(t.get('startTime'))        s = _parse_iso_to_dt(t.get('startTime'))

        e = _parse_iso_to_dt(t.get('endTime'))        e = _parse_iso_to_dt(t.get('endTime'))

        if s and e:        if s and e:

            calendar.append((s, e))            calendar.append((s, e))



    # simple function to find next free slot of duration minutes between now and horizon_end    # simple function to find next free slot of duration minutes between now and horizon_end

    def find_slot(duration_minutes, earliest=None):    def find_slot(duration_minutes, earliest=None):

        if earliest is None:        if earliest is None:

            earliest = now            earliest = now

        candidate_start = earliest        candidate_start = earliest

        # try candidate_start and move forward by 15-minute increments        # try candidate_start and move forward by 15-minute increments

        step = timedelta(minutes=15)        step = timedelta(minutes=15)

        dur = timedelta(minutes=duration_minutes)        dur = timedelta(minutes=duration_minutes)

        while candidate_start + dur <= horizon_end:        while candidate_start + dur <= horizon_end:

            candidate_end = candidate_start + dur            candidate_end = candidate_start + dur

            overlap = False            overlap = False

            for (as_, ae) in calendar:            for (as_, ae) in calendar:

                if not (candidate_end <= as_ or candidate_start >= ae):                if not (candidate_end <= as_ or candidate_start >= ae):

                    overlap = True                    overlap = True

                    break                    break

            if not overlap:            if not overlap:

                # reserve it                # reserve it

                calendar.append((candidate_start, candidate_end))                calendar.append((candidate_start, candidate_end))

                return candidate_start, candidate_end                return candidate_start, candidate_end

            candidate_start = candidate_start + step            candidate_start = candidate_start + step

        return None, None        return None, None



    # schedule respecting precedence by simple topological-like pass (not full topo sort)    # schedule respecting precedence by simple topological-like pass (not full topo sort)

    placed = set()    placed = set()

    for t in tasks_sorted:    for t in tasks_sorted:

        tid = t.get('id')        tid = t.get('id')

        if tid in placed:        if tid in placed:

            continue            continue

        # ensure predecessors are placed first        # ensure predecessors are placed first

        preds = [k for k, vs in pred_map.items() if tid in vs]        preds = [k for k, vs in pred_map.items() if tid in vs]

        earliest = now        earliest = now

        for p in preds:        for p in preds:

            # find placed predecessor end            # find placed predecessor end

            p_end = None            p_end = None

            for s in scheduled:            for s in scheduled:

                if s['id'] == p:                if s['id'] == p:

                    p_end = _parse_iso_to_dt(s.get('end'))                    p_end = _parse_iso_to_dt(s.get('end'))

                    break                    break

            if p_end and p_end > earliest:            if p_end and p_end > earliest:

                earliest = p_end + timedelta(minutes=5)                earliest = p_end + timedelta(minutes=5)



        est = get_est(t)        est = get_est(t)

        s_start, s_end = find_slot(est, earliest)        s_start, s_end = find_slot(est, earliest)

        if s_start and s_end:        if s_start and s_end:

            scheduled.append({'id': tid, 'title': t.get('title'), 'start': s_start.isoformat(), 'end': s_end.isoformat(), 'estimate_minutes': est})            scheduled.append({'id': tid, 'title': t.get('title'), 'start': s_start.isoformat(), 'end': s_end.isoformat(), 'estimate_minutes': est})

            placed.add(tid)            placed.add(tid)



    return scheduled    return scheduled





@app.get('/api/schedule/predictive')@app.get('/api/schedule/predictive')

async def api_predictive_schedule(horizon_days: int = 7, limit: int = 50):async def api_predictive_schedule(horizon_days: int = 7, limit: int = 50):

    """Return a predictive schedule for pending tasks within the next horizon_days.    """Return a predictive schedule for pending tasks within the next horizon_days.



    The endpoint uses simple heuristics and respects FINISH_TO_START relationships.    The endpoint uses simple heuristics and respects FINISH_TO_START relationships.

    """    """

    try:    try:

        with driver.session() as session:        with driver.session() as session:

            res = session.run("MATCH (t:Task) WHERE t.status='pending' RETURN t LIMIT $lim", lim=limit)            res = session.run("MATCH (t:Task) WHERE t.status='pending' RETURN t LIMIT $lim", lim=limit)

            tasks = [neo4j_to_serializable(r['t']) for r in res]            tasks = [neo4j_to_serializable(r['t']) for r in res]



        sched = _predictive_schedule(tasks, horizon_days=horizon_days)        sched = _predictive_schedule(tasks, horizon_days=horizon_days)

        return JSONResponse(content={'scheduled': sched}, status_code=200)        return JSONResponse(content={'scheduled': sched}, status_code=200)

    except Exception as e:    except Exception as e:

        print(f"Error in api_predictive_schedule: {e}")        print(f"Error in api_predictive_schedule: {e}")

        raise HTTPException(status_code=500, detail='Could not compute predictive schedule')        raise HTTPException(status_code=500, detail='Could not compute predictive schedule')





def _is_urgent(task):def _is_urgent(task):

    """Heuristic to decide if a task is urgent.    """Heuristic to decide if a task is urgent.



    Uses due dates within 24h and keyword detection; optionally uses zero-shot classifier    Uses due dates within 24h and keyword detection; optionally uses zero-shot classifier

    when available. Returns boolean.    when available. Returns boolean.

    """    """

    try:    try:

        title = (task.get('title') or '')        title = (task.get('title') or '')

        desc = (task.get('description') or '')        desc = (task.get('description') or '')

        text = (title + ' ' + desc).lower()        text = (title + ' ' + desc).lower()



        urgent_keywords = ['urgent', 'asap', 'immediately', 'due', 'deadline', 'today', 'now', 'critical']        urgent_keywords = ['urgent', 'asap', 'immediately', 'due', 'deadline', 'today', 'now', 'critical']

        if any(k in text for k in urgent_keywords):        if any(k in text for k in urgent_keywords):

            return True            return True



        # due soon        # due soon

        due = _parse_iso_to_dt(task.get('dueDate') or task.get('endTime') or task.get('startTime'))        due = _parse_iso_to_dt(task.get('dueDate') or task.get('endTime') or task.get('startTime'))

        if due:        if due:

            try:            try:

                if due <= datetime.utcnow() + timedelta(hours=24):                if due <= datetime.utcnow() + timedelta(hours=24):

                    return True                    return True

            except Exception:            except Exception:

                pass                pass



        # optional classifier-derived score        # optional classifier-derived score

        try:        try:

            scores = _ai_scores(task)            scores = _ai_scores(task)

            if scores and scores.get('urgent') and scores['urgent'] >= 0.6:            if scores and scores.get('urgent') and scores['urgent'] >= 0.6:

                return True                return True

        except Exception:        except Exception:

            pass            pass



        return False        return False

    except Exception:    except Exception:

        return False        return False





def _is_important(task):def _is_important(task):

    """Heuristic to decide if a task is important.    """Heuristic to decide if a task is important.



    Uses explicit priority, category, keywords, and optional classifier.    Uses explicit priority, category, keywords, and optional classifier.

    """    """

    try:    try:

        p = (task.get('priority') or '').lower()        p = (task.get('priority') or '').lower()

        if p == 'high':        if p == 'high':

            return True            return True



        cat = (task.get('category') or '').lower()        cat = (task.get('category') or '').lower()

        if cat in ['work', 'education', 'health', 'finance']:        if cat in ['work', 'education', 'health', 'finance']:

            return True            return True



        text = ((task.get('title') or '') + ' ' + (task.get('description') or '')).lower()        text = ((task.get('title') or '') + ' ' + (task.get('description') or '')).lower()

        important_keywords = ['exam', 'interview', 'project', 'milestone', 'payment', 'important', 'deadline']        important_keywords = ['exam', 'interview', 'project', 'milestone', 'payment', 'important', 'deadline']

        if any(k in text for k in important_keywords):        if any(k in text for k in important_keywords):

            return True            return True



        # optional classifier-derived score        # optional classifier-derived score

        try:        try:

            scores = _ai_scores(task)            scores = _ai_scores(task)

            if scores and scores.get('important') and scores['important'] >= 0.6:            if scores and scores.get('important') and scores['important'] >= 0.6:

                return True                return True

        except Exception:        except Exception:

            pass            pass



        return False        return False

    except Exception:    except Exception:

        return False        return False





@app.get('/api/schedule/eisenhower')@app.get('/api/schedule/eisenhower')

async def api_eisenhower_schedule(max: int | None = None):async def api_eisenhower_schedule(max: int | None = None):

    """Return tasks grouped into Eisenhower quadrants and a prioritized linear schedule.    """Return tasks grouped into Eisenhower quadrants and a prioritized linear schedule.



    Response format:    Response format:

      { quadrants: { 'Do Now (Q1)': [..], ... }, prioritized: [..] }      { quadrants: { 'Do Now (Q1)': [..], ... }, prioritized: [..] }

    """    """

    try:    try:

        max_items = max        max_items = max



        with driver.session() as session:        with driver.session() as session:

            result = session.run("MATCH (t:Task) WHERE t.status = 'pending' RETURN t")            result = session.run("MATCH (t:Task) WHERE t.status = 'pending' RETURN t")

            tasks = [neo4j_to_serializable(r['t']) for r in result]            tasks = [neo4j_to_serializable(r['t']) for r in result]

            print(f"📊 Eisenhower endpoint called - Found {len(tasks)} pending tasks")            print(f"📊 Eisenhower endpoint called - Found {len(tasks)} pending tasks")



        # Compute flags and group        # Compute flags and group

        quadrants = {"Do Now (Q1)": [], "Schedule (Q2)": [], "Delegate (Q3)": [], "Eliminate (Q4)": []}        quadrants = {"Do Now (Q1)": [], "Schedule (Q2)": [], "Delegate (Q3)": [], "Eliminate (Q4)": []}

        enriched = []        enriched = []

        for t in tasks:        for t in tasks:

            try:            try:

                # ensure keys are simple types                # ensure keys are simple types

                task_obj = {k: neo4j_to_serializable(v) for k, v in t.items()} if hasattr(t, 'items') else dict(t)                task_obj = {k: neo4j_to_serializable(v) for k, v in t.items()} if hasattr(t, 'items') else dict(t)

                # compute AI scores (if available) and heuristics                # compute AI scores (if available) and heuristics

                ai_scores = _ai_scores(task_obj) or {'urgent': 0.0, 'important': 0.0}                ai_scores = _ai_scores(task_obj) or {'urgent': 0.0, 'important': 0.0}

                urgent = _is_urgent(task_obj)                urgent = _is_urgent(task_obj)

                important = _is_important(task_obj)                important = _is_important(task_obj)

                qname = None                qname = None

                if urgent and important:                if urgent and important:

                    qname = "Do Now (Q1)"                    qname = "Do Now (Q1)"

                elif (not urgent) and important:                elif (not urgent) and important:

                    qname = "Schedule (Q2)"                    qname = "Schedule (Q2)"

                elif urgent and (not important):                elif urgent and (not important):

                    qname = "Delegate (Q3)"                    qname = "Delegate (Q3)"

                else:                else:

                    qname = "Eliminate (Q4)"                    qname = "Eliminate (Q4)"



                # parse deadline for sorting                # parse deadline for sorting

                deadline = _parse_iso_to_dt(task_obj.get('dueDate') or task_obj.get('endTime') or task_obj.get('startTime'))                deadline = _parse_iso_to_dt(task_obj.get('dueDate') or task_obj.get('endTime') or task_obj.get('startTime'))

                enriched_item = {                enriched_item = {

                    'id': task_obj.get('id'),                    'id': task_obj.get('id'),

                    'title': task_obj.get('title'),                    'title': task_obj.get('title'),

                    'description': task_obj.get('description'),                    'description': task_obj.get('description'),

                    'priority': task_obj.get('priority'),                    'priority': task_obj.get('priority'),

                    'category': task_obj.get('category'),                    'category': task_obj.get('category'),

                    'deadline': deadline.isoformat() if deadline else None,                    'deadline': deadline.isoformat() if deadline else None,

                    'startTime': task_obj.get('startTime'),                    'startTime': task_obj.get('startTime'),

                    'endTime': task_obj.get('endTime'),                    'endTime': task_obj.get('endTime'),

                    'urgent': urgent,                    'urgent': urgent,

                    'important': important,                    'important': important,

                    'ai_scores': ai_scores,                    'ai_scores': ai_scores,

                    'quadrant': qname                    'quadrant': qname

                }                }

                quadrants[qname].append(enriched_item)                quadrants[qname].append(enriched_item)

                enriched.append(enriched_item)                enriched.append(enriched_item)

            except Exception as task_e:            except Exception as task_e:

                print(f"Error processing task for Eisenhower schedule (skipping): {task_e}")                print(f"Error processing task for Eisenhower schedule (skipping): {task_e}")

                continue                continue



        # sort within each quadrant by (deadline asc, priority asc)        # sort within each quadrant by (deadline asc, priority asc)

        def sort_key(item):        def sort_key(item):

            d = item.get('deadline')            d = item.get('deadline')

            try:            try:

                dt = _parse_iso_to_dt(d) if d else None                dt = _parse_iso_to_dt(d) if d else None

                dt_sort = dt if dt else datetime.max                dt_sort = dt if dt else datetime.max

            except Exception:            except Exception:

                dt_sort = datetime.max                dt_sort = datetime.max

            return (dt_sort, _priority_value(item.get('priority')))            return (dt_sort, _priority_value(item.get('priority')))



        for k in quadrants:        for k in quadrants:

            quadrants[k] = sorted(quadrants[k], key=sort_key)            quadrants[k] = sorted(quadrants[k], key=sort_key)



        # prioritized linear schedule Q1->Q2->Q3->Q4        # prioritized linear schedule Q1->Q2->Q3->Q4

        order = ["Do Now (Q1)", "Schedule (Q2)", "Delegate (Q3)", "Eliminate (Q4)"]        order = ["Do Now (Q1)", "Schedule (Q2)", "Delegate (Q3)", "Eliminate (Q4)"]

        prioritized = []        prioritized = []

        for name in order:        for name in order:

            prioritized.extend(quadrants.get(name, []))            prioritized.extend(quadrants.get(name, []))



        if max_items:        if max_items:

            prioritized = prioritized[:max_items]            prioritized = prioritized[:max_items]



        # suggested actions        # suggested actions

        for item in prioritized:        for item in prioritized:

            q = item.get('quadrant')            q = item.get('quadrant')

            if q == 'Do Now (Q1)':            if q == 'Do Now (Q1)':

                item['suggested'] = 'Do immediately'                item['suggested'] = 'Do immediately'

            elif q == 'Schedule (Q2)':            elif q == 'Schedule (Q2)':

                item['suggested'] = 'Schedule on calendar'                item['suggested'] = 'Schedule on calendar'

            elif q == 'Delegate (Q3)':            elif q == 'Delegate (Q3)':

                item['suggested'] = 'Delegate to someone'                item['suggested'] = 'Delegate to someone'

            else:            else:

                item['suggested'] = 'Consider dropping'                item['suggested'] = 'Consider dropping'



        # If there are overlapping start/end times or identical times, try to enforce a partial order        # If there are overlapping start/end times or identical times, try to enforce a partial order

        try:        try:

            # Reorder by AI-driven partial order (soft precedence)            # Reorder by AI-driven partial order (soft precedence)

            reordered = _partial_order_plan(prioritized)            reordered = _partial_order_plan(prioritized)

            # Then apply greedy selection by deadline to avoid overlaps            # Then apply greedy selection by deadline to avoid overlaps

            scheduled = _greedy_by_deadline(reordered)            scheduled = _greedy_by_deadline(reordered)

            # If greedy removed items but max_items requested, fill up from reordered            # If greedy removed items but max_items requested, fill up from reordered

            if max_items and len(scheduled) < max_items:            if max_items and len(scheduled) < max_items:

                # append non-scheduled items in reordered order until max_items                # append non-scheduled items in reordered order until max_items

                for it in reordered:                for it in reordered:

                    if it not in scheduled:                    if it not in scheduled:

                        scheduled.append(it)                        scheduled.append(it)

                    if len(scheduled) >= max_items:                    if len(scheduled) >= max_items:

                        break                        break

            # If no max_items, return the scheduled order but include dropped items in quadrants (they still exist there)            # If no max_items, return the scheduled order but include dropped items in quadrants (they still exist there)

            prioritized_final = scheduled if scheduled else prioritized            prioritized_final = scheduled if scheduled else prioritized

        except Exception as e:        except Exception as e:

            print(f"Warning: scheduling refinement failed: {e}")            print(f"Warning: scheduling refinement failed: {e}")

            prioritized_final = prioritized            prioritized_final = prioritized



        return JSONResponse(content={'quadrants': quadrants, 'prioritized': prioritized_final}, status_code=200)        return JSONResponse(content={'quadrants': quadrants, 'prioritized': prioritized_final}, status_code=200)

    except Exception as e:    except Exception as e:

        print(f"Error in api_eisenhower_schedule: {e}")        print(f"Error in api_eisenhower_schedule: {e}")

        return JSONResponse(content={'error': 'Could not compute Eisenhower schedule'}, status_code=500)        return JSONResponse(content={'error': 'Could not compute Eisenhower schedule'}, status_code=500)





# --- Authentication endpoints using Neo4j ---# --- Authentication endpoints using Neo4j ---

@app.post('/api/auth/login')@app.post('/api/auth/login')

async def api_login(request: Request):async def api_login(request: Request):

    try:    try:

        data = await request.json()        data = await request.json()

        email = data.get('email')        email = data.get('email')

        password = data.get('password')        password = data.get('password')

        if not email or not password:        if not email or not password:

            raise HTTPException(status_code=400, detail='Missing credentials')            raise HTTPException(status_code=400, detail='Missing credentials')

        with driver.session() as session:        with driver.session() as session:

            result = session.run("MATCH (u:User {email: $email, password: $password}) RETURN u", email=email, password=password)            result = session.run("MATCH (u:User {email: $email, password: $password}) RETURN u", email=email, password=password)

            rec = result.single()            rec = result.single()

            if not rec:            if not rec:

                raise HTTPException(status_code=401, detail='Invalid credentials')                raise HTTPException(status_code=401, detail='Invalid credentials')

            user = rec['u']            user = rec['u']

            user_obj = {k: neo4j_to_serializable(v) for k,v in dict(user).items()} if hasattr(user, 'items') else dict(user)            user_obj = {k: neo4j_to_serializable(v) for k,v in dict(user).items()} if hasattr(user, 'items') else dict(user)

            return {'id': user_obj.get('id'), 'name': user_obj.get('name'), 'email': user_obj.get('email')}            return {'id': user_obj.get('id'), 'name': user_obj.get('name'), 'email': user_obj.get('email')}

    except HTTPException:    except HTTPException:

        raise        raise

    except Exception as e:    except Exception as e:

        print(f"Error in api_login: {e}")        print(f"Error in api_login: {e}")

        raise HTTPException(status_code=500, detail='Internal error')        raise HTTPException(status_code=500, detail='Internal error')





@app.websocket('/ws/notifications')@app.websocket('/ws/notifications')

async def websocket_notifications(ws: WebSocket):async def websocket_notifications(ws: WebSocket):

    """WebSocket endpoint for push notifications to browser clients."""    """WebSocket endpoint for push notifications to browser clients."""

    await ws.accept()    await ws.accept()

    connected_webs.add(ws)    connected_webs.add(ws)

    print("WebSocket client connected. Total:", len(connected_webs))    print("WebSocket client connected. Total:", len(connected_webs))

    try:    try:

        while True:        while True:

            # keep the connection alive, echo pings or handle incoming messages if needed            # keep the connection alive, echo pings or handle incoming messages if needed

            msg = await ws.receive_text()            msg = await ws.receive_text()

            # clients can send a 'ping' or 'ready' message; ignore for now            # clients can send a 'ping' or 'ready' message; ignore for now

            # If client sends subscribe preferences, we could persist them here            # If client sends subscribe preferences, we could persist them here

            # For now just acknowledge            # For now just acknowledge

            try:            try:

                await ws.send_text(json.dumps({'type': 'ack', 'payload': msg}))                await ws.send_text(json.dumps({'type': 'ack', 'payload': msg}))

            except Exception:            except Exception:

                pass                pass

    except WebSocketDisconnect:    except WebSocketDisconnect:

        print('WebSocket client disconnected')        print('WebSocket client disconnected')

        try:        try:

            connected_webs.discard(ws)            connected_webs.discard(ws)

        except Exception:        except Exception:

            pass            pass

    except Exception as e:    except Exception as e:

        print(f"WebSocket error: {e}")        print(f"WebSocket error: {e}")

        try:        try:

            connected_webs.discard(ws)            connected_webs.discard(ws)

        except Exception:        except Exception:

            pass            pass





@app.get('/api/auth/me')@app.get('/api/auth/me')

async def api_me(request: Request):async def api_me(request: Request):

    """Return basic info about the current user.    """Return basic info about the current user.



    Prefers an explicit header 'X-User-Email' to identify the user. If not provided,    Prefers an explicit header 'X-User-Email' to identify the user. If not provided,

    returns the first user node found in the DB, or a Guest fallback.    returns the first user node found in the DB, or a Guest fallback.

    """    """

    try:    try:

        email_hdr = request.headers.get('x-user-email') or request.headers.get('X-User-Email')        email_hdr = request.headers.get('x-user-email') or request.headers.get('X-User-Email')

        with driver.session() as session:        with driver.session() as session:

            if email_hdr:            if email_hdr:

                rec = session.run("MATCH (u:User {email: $email}) RETURN u", email=email_hdr).single()                rec = session.run("MATCH (u:User {email: $email}) RETURN u", email=email_hdr).single()

            else:            else:

                rec = session.run("MATCH (u:User) RETURN u LIMIT 1").single()                rec = session.run("MATCH (u:User) RETURN u LIMIT 1").single()

        if not rec:        if not rec:

            return {'id': None, 'name': 'Guest', 'email': None}            return {'id': None, 'name': 'Guest', 'email': None}

        user = rec['u']        user = rec['u']

        user_obj = {k: neo4j_to_serializable(v) for k, v in dict(user).items()} if hasattr(user, 'items') else dict(user)        user_obj = {k: neo4j_to_serializable(v) for k, v in dict(user).items()} if hasattr(user, 'items') else dict(user)

        return {'id': user_obj.get('id'), 'name': user_obj.get('name') or user_obj.get('email') or 'User', 'email': user_obj.get('email')}        return {'id': user_obj.get('id'), 'name': user_obj.get('name') or user_obj.get('email') or 'User', 'email': user_obj.get('email')}

    except Exception as e:    except Exception as e:

        print(f"Error in api_me: {e}")        print(f"Error in api_me: {e}")

        raise HTTPException(status_code=500, detail='Internal error')        raise HTTPException(status_code=500, detail='Internal error')





@app.post('/api/auth/signup')@app.post('/api/auth/signup')

async def api_signup(request: Request):async def api_signup(request: Request):

    try:    try:

        data = await request.json()        data = await request.json()

        name = data.get('name')        name = data.get('name')

        email = data.get('email')        email = data.get('email')

        password = data.get('password')        password = data.get('password')

        if not name or not email or not password:        if not name or not email or not password:

            raise HTTPException(status_code=400, detail='Missing fields')            raise HTTPException(status_code=400, detail='Missing fields')

        # create user node        # create user node

        user_id = str(uuid.uuid4())        user_id = str(uuid.uuid4())

        with driver.session() as session:        with driver.session() as session:

            # check exists            # check exists

            existing = session.run("MATCH (u:User {email: $email}) RETURN u", email=email).single()            existing = session.run("MATCH (u:User {email: $email}) RETURN u", email=email).single()

            if existing:            if existing:

                raise HTTPException(status_code=409, detail='User already exists')                raise HTTPException(status_code=409, detail='User already exists')

            session.run("CREATE (u:User {id: $id, name: $name, email: $email, password: $password, createdAt: datetime()})",            session.run("CREATE (u:User {id: $id, name: $name, email: $email, password: $password, createdAt: datetime()})",

                        id=user_id, name=name, email=email, password=password)                        id=user_id, name=name, email=email, password=password)

        return JSONResponse(status_code=201, content={'message': 'User created', 'id': user_id})        return JSONResponse(status_code=201, content={'message': 'User created', 'id': user_id})

    except HTTPException:    except HTTPException:

        raise        raise

    except Exception as e:    except Exception as e:

        print(f"Error in api_signup: {e}")        print(f"Error in api_signup: {e}")

        raise HTTPException(status_code=500, detail='Internal error')        raise HTTPException(status_code=500, detail='Internal error')





@app.post('/api/auth/forgot-password')@app.post('/api/auth/forgot-password')

async def api_forgot_password(request: Request):async def api_forgot_password(request: Request):

    try:    try:

        data = await request.json() or {}        data = await request.json() or {}

        email = data.get('email')        email = data.get('email')

        # If no email provided in request, fall back to SMTP_USER from env        # If no email provided in request, fall back to SMTP_USER from env

        smtp_user = os.getenv('SMTP_USER')        smtp_user = os.getenv('SMTP_USER')

        if not email:        if not email:

            if smtp_user:            if smtp_user:

                email = smtp_user                email = smtp_user

            else:            else:

                raise HTTPException(status_code=400, detail='Missing email')                raise HTTPException(status_code=400, detail='Missing email')

        with driver.session() as session:        with driver.session() as session:

            rec = session.run("MATCH (u:User {email: $email}) RETURN u", email=email).single()            rec = session.run("MATCH (u:User {email: $email}) RETURN u", email=email).single()

            if not rec:            if not rec:

                # Auto-create a user node if it doesn't exist so OTP can be associated and later used to reset password                # Auto-create a user node if it doesn't exist so OTP can be associated and later used to reset password

                user_id = str(uuid.uuid4())                user_id = str(uuid.uuid4())

                session.run("CREATE (u:User {id: $id, email: $email, createdAt: datetime()})", id=user_id, email=email)                session.run("CREATE (u:User {id: $id, email: $email, createdAt: datetime()})", id=user_id, email=email)

            otp = str(random.randint(100000, 999999))            otp = str(random.randint(100000, 999999))

            expiry = (datetime.utcnow() + timedelta(minutes=10)).isoformat()            expiry = (datetime.utcnow() + timedelta(minutes=10)).isoformat()

            session.run("MATCH (u:User {email: $email}) SET u.otp = $otp, u.otpExpiry = $expiry", email=email, otp=otp, expiry=expiry)            session.run("MATCH (u:User {email: $email}) SET u.otp = $otp, u.otpExpiry = $expiry", email=email, otp=otp, expiry=expiry)

        # Attempt to send OTP via SMTP if configured        # Attempt to send OTP via SMTP if configured

        smtp_host = os.getenv('SMTP_HOST')        smtp_host = os.getenv('SMTP_HOST')

        smtp_port = int(os.getenv('SMTP_PORT', '587'))        smtp_port = int(os.getenv('SMTP_PORT', '587'))

        smtp_user = os.getenv('SMTP_USER')        smtp_user = os.getenv('SMTP_USER')

        smtp_pass = os.getenv('SMTP_PASS')        smtp_pass = os.getenv('SMTP_PASS')

        email_from = os.getenv('EMAIL_FROM', smtp_user)        email_from = os.getenv('EMAIL_FROM', smtp_user)

    # Normalize EMAIL_FROM: if it looks like an address without display name, add 'TrackEneer <email>'    # Normalize EMAIL_FROM: if it looks like an address without display name, add 'TrackEneer <email>'

        if email_from and '@' in email_from and '<' not in email_from and '>' not in email_from:        if email_from and '@' in email_from and '<' not in email_from and '>' not in email_from:

            # If format is 'Trackneer email@domain' fix it, otherwise wrap            # If format is 'Trackneer email@domain' fix it, otherwise wrap

            if ' ' in email_from:            if ' ' in email_from:

                parts = email_from.rsplit(' ', 1)                parts = email_from.rsplit(' ', 1)

                display = parts[0].strip()                display = parts[0].strip()

                addr = parts[1].strip()                addr = parts[1].strip()

                email_from = f"{display} <{addr}>"                email_from = f"{display} <{addr}>"

            else:            else:

                email_from = f"TrackEneer <{email_from}>"                email_from = f"TrackEneer <{email_from}>"



        email_sent = False        email_sent = False

        if smtp_host and smtp_user and smtp_pass:        if smtp_host and smtp_user and smtp_pass:

            try:            try:

                msg = EmailMessage()                msg = EmailMessage()

                msg['Subject'] = 'TrackEneer Password Reset OTP'                msg['Subject'] = 'TrackEneer Password Reset OTP'

                msg['From'] = email_from                msg['From'] = email_from

                msg['To'] = email                msg['To'] = email

                msg.set_content(f"Your TrackEneer password reset code is: {otp}\nThis code expires in 10 minutes.")                msg.set_content(f"Your TrackEneer password reset code is: {otp}\nThis code expires in 10 minutes.")



                with smtplib.SMTP(smtp_host, smtp_port) as server:                with smtplib.SMTP(smtp_host, smtp_port) as server:

                    server.starttls()                    server.starttls()

                    server.login(smtp_user, smtp_pass)                    server.login(smtp_user, smtp_pass)

                    server.send_message(msg)                    server.send_message(msg)

                email_sent = True                email_sent = True

            except Exception as e:            except Exception as e:

                print(f"Error sending OTP email: {e}")                print(f"Error sending OTP email: {e}")



        # For production we should not return the OTP. In dev, if SMTP not configured, return a hint.        # For production we should not return the OTP. In dev, if SMTP not configured, return a hint.

        if email_sent:        if email_sent:

            return {'message': 'OTP generated and sent to email'}            return {'message': 'OTP generated and sent to email'}

        else:        else:

            print(f"Forgot-password OTP for {email}: {otp} (expires {expiry})")            print(f"Forgot-password OTP for {email}: {otp} (expires {expiry})")

            return {'message': 'OTP generated (dev mode - SMTP not configured)', 'otpHint': 'OTP printed to server logs for dev'}            return {'message': 'OTP generated (dev mode - SMTP not configured)', 'otpHint': 'OTP printed to server logs for dev'}

    except Exception as e:    except Exception as e:

        print(f"Error in api_forgot_password: {e}")        print(f"Error in api_forgot_password: {e}")

        raise HTTPException(status_code=500, detail='Internal error')        raise HTTPException(status_code=500, detail='Internal error')





@app.post('/api/auth/reset-password')@app.post('/api/auth/reset-password')

async def api_reset_password(request: Request):async def api_reset_password(request: Request):

    try:    try:

        data = await request.json()        data = await request.json()

        email = data.get('email')        email = data.get('email')

        otp = data.get('otp')        otp = data.get('otp')

        new_password = data.get('newPassword')        new_password = data.get('newPassword')

        if not email or not otp or not new_password:        if not email or not otp or not new_password:

            raise HTTPException(status_code=400, detail='Missing fields')            raise HTTPException(status_code=400, detail='Missing fields')

        with driver.session() as session:        with driver.session() as session:

            rec = session.run("MATCH (u:User {email: $email}) RETURN u", email=email).single()            rec = session.run("MATCH (u:User {email: $email}) RETURN u", email=email).single()

            if not rec:            if not rec:

                raise HTTPException(status_code=404, detail='User not found')                raise HTTPException(status_code=404, detail='User not found')

            user = rec['u']            user = rec['u']

            user_obj = {k: neo4j_to_serializable(v) for k,v in dict(user).items()} if hasattr(user, 'items') else dict(user)            user_obj = {k: neo4j_to_serializable(v) for k,v in dict(user).items()} if hasattr(user, 'items') else dict(user)

            stored_otp = user_obj.get('otp')            stored_otp = user_obj.get('otp')

            otp_expiry = user_obj.get('otpExpiry')            otp_expiry = user_obj.get('otpExpiry')

            if not stored_otp or stored_otp != str(otp):            if not stored_otp or stored_otp != str(otp):

                raise HTTPException(status_code=401, detail='Invalid OTP')                raise HTTPException(status_code=401, detail='Invalid OTP')

            if otp_expiry:            if otp_expiry:

                try:                try:

                    exp_dt = datetime.fromisoformat(otp_expiry)                    exp_dt = datetime.fromisoformat(otp_expiry)

                    if datetime.utcnow() > exp_dt:                    if datetime.utcnow() > exp_dt:

                        raise HTTPException(status_code=410, detail='OTP expired')                        raise HTTPException(status_code=410, detail='OTP expired')

                except HTTPException:                except HTTPException:

                    raise                    raise

                except Exception:                except Exception:

                    pass                    pass

            # update password and remove otp fields            # update password and remove otp fields

            session.run("MATCH (u:User {email: $email}) SET u.password = $pw REMOVE u.otp, u.otpExpiry", email=email, pw=new_password)            session.run("MATCH (u:User {email: $email}) SET u.password = $pw REMOVE u.otp, u.otpExpiry", email=email, pw=new_password)

        return {'message': 'Password reset successful'}        return {'message': 'Password reset successful'}

    except HTTPException:    except HTTPException:

        raise        raise

    except Exception as e:    except Exception as e:

        print(f"Error in api_reset_password: {e}")        print(f"Error in api_reset_password: {e}")

        raise HTTPException(status_code=500, detail='Internal error')        raise HTTPException(status_code=500, detail='Internal error')





@app.post('/api/notifications/subscribe')@app.post('/api/notifications/subscribe')

async def api_notifications_subscribe(request: Request):async def api_notifications_subscribe(request: Request):

    """Subscribe a user to notifications (currently handled via WebSocket)."""    """Subscribe a user to notifications (currently handled via WebSocket)."""

    try:    try:

        data = await request.json()        data = await request.json()

        user_id = data.get('userId')        user_id = data.get('userId')

        if not user_id:        if not user_id:

            raise HTTPException(status_code=400, detail='Missing userId')            raise HTTPException(status_code=400, detail='Missing userId')

        # In a full implementation, we'd persist subscription preferences in Neo4j        # In a full implementation, we'd persist subscription preferences in Neo4j

        # For now, return success since WebSocket handles real-time notifications        # For now, return success since WebSocket handles real-time notifications

        return {'message': 'Subscription successful', 'userId': user_id}        return {'message': 'Subscription successful', 'userId': user_id}

    except HTTPException:    except HTTPException:

        raise        raise

    except Exception as e:    except Exception as e:

        print(f"Error in api_notifications_subscribe: {e}")        print(f"Error in api_notifications_subscribe: {e}")

        raise HTTPException(status_code=500, detail='Internal error')        raise HTTPException(status_code=500, detail='Internal error')





@app.post('/api/notifications/mark-sent')@app.post('/api/notifications/mark-sent')

async def api_notifications_mark_sent(request: Request):async def api_notifications_mark_sent(request: Request):

    """Mark a notification as sent so it won't be repeatedly returned in polling.    """Mark a notification as sent so it won't be repeatedly returned in polling.



    This endpoint accepts JSON: { "notificationId": "start-<taskId>" }    This endpoint accepts JSON: { "notificationId": "start-<taskId>" }

    and stores the id in an in-memory set for the lifetime of the process.    and stores the id in an in-memory set for the lifetime of the process.

    """    """

    try:    try:

        data = await request.json()        data = await request.json()

        nid = data.get('notificationId')        nid = data.get('notificationId')

        if not nid:        if not nid:

            raise HTTPException(status_code=400, detail='notificationId is required')            raise HTTPException(status_code=400, detail='notificationId is required')



        try:        try:

            # store in the NOTIFIED_TASK_KEYS set so pending endpoint can filter            # store in the NOTIFIED_TASK_KEYS set so pending endpoint can filter

            NOTIFIED_TASK_KEYS.add(str(nid))            NOTIFIED_TASK_KEYS.add(str(nid))

            print(f"🔕 Marked notification as sent: {nid}")            print(f"🔕 Marked notification as sent: {nid}")

        except Exception as e:        except Exception as e:

            print(f"Warning: could not mark notification as sent: {e}")            print(f"Warning: could not mark notification as sent: {e}")



        return {'success': True, 'notificationId': nid}        return {'success': True, 'notificationId': nid}

    except HTTPException:    except HTTPException:

        raise        raise

    except Exception as e:    except Exception as e:

        print(f"Error in api_notifications_mark_sent: {e}")        print(f"Error in api_notifications_mark_sent: {e}")

        raise HTTPException(status_code=500, detail='Internal error')        raise HTTPException(status_code=500, detail='Internal error')





@app.get('/api/notifications/pending')@app.get('/api/notifications/pending')

async def api_notifications_pending():async def api_notifications_pending():

    """Get pending notifications with IST timezone support."""    """Get pending notifications with IST timezone support."""

    try:    try:

        # Get current time in IST        # Get current time in IST

        now_utc = datetime.now(timezone.utc)        now_utc = datetime.now(timezone.utc)

        now_ist = now_utc.astimezone(IST)        now_ist = now_utc.astimezone(IST)

                

        notifications = []        notifications = []

                

        with driver.session() as session:        with driver.session() as session:

            # Get tasks with upcoming start times            # Get tasks with upcoming start times

            result = session.run("""            result = session.run("""

                MATCH (t:Task)                MATCH (t:Task)

                WHERE t.status = 'pending'                 WHERE t.status = 'pending' 

                AND t.startTime IS NOT NULL                AND t.startTime IS NOT NULL

                AND datetime(t.startTime) > datetime()                AND datetime(t.startTime) > datetime()

                AND datetime(t.startTime) <= datetime() + duration({minutes: 15})                AND datetime(t.startTime) <= datetime() + duration({minutes: 15})

                RETURN t.id AS id, t.title AS title, t.startTime AS startTime,                 RETURN t.id AS id, t.title AS title, t.startTime AS startTime, 

                       'start' AS type                       'start' AS type

                ORDER BY t.startTime                ORDER BY t.startTime

                LIMIT 20                LIMIT 20

            """)            """)

                        

            for record in result:            for record in result:

                start_time = record['startTime']                start_time = record['startTime']

                if isinstance(start_time, DateTime):                if isinstance(start_time, DateTime):

                    start_dt = start_time.to_native()                    start_dt = start_time.to_native()

                else:                else:

                    start_dt = datetime.fromisoformat(str(start_time))                    start_dt = datetime.fromisoformat(str(start_time))

                                

                # Convert to IST                # Convert to IST

                if start_dt.tzinfo is None:                if start_dt.tzinfo is None:

                    start_dt = start_dt.replace(tzinfo=timezone.utc)                    start_dt = start_dt.replace(tzinfo=timezone.utc)

                start_ist = start_dt.astimezone(IST)                start_ist = start_dt.astimezone(IST)

                                

                time_diff = start_ist - now_ist                time_diff = start_ist - now_ist

                minutes_until = int(time_diff.total_seconds() / 60)                minutes_until = int(time_diff.total_seconds() / 60)

                                

                if minutes_until > 0 and minutes_until <= 15:                if minutes_until > 0 and minutes_until <= 15:

                    notifications.append({                    notifications.append({

                        'id': f"start-{record['id']}",                        'id': f"start-{record['id']}",

                        'title': record['title'],                        'title': record['title'],

                        'type': 'start',                        'type': 'start',

                        'minutesUntil': minutes_until,                        'minutesUntil': minutes_until,

                        'scheduledTime': start_ist.strftime('%I:%M %p IST')                        'scheduledTime': start_ist.strftime('%I:%M %p IST')

                    })                    })

                        

            # Get tasks with due dates approaching            # Get tasks with due dates approaching

            result = session.run("""            result = session.run("""

                MATCH (t:Task)                MATCH (t:Task)

                WHERE t.status = 'pending'                 WHERE t.status = 'pending' 

                AND t.dueDate IS NOT NULL                AND t.dueDate IS NOT NULL

                RETURN t.id AS id, t.title AS title, t.dueDate AS dueDate,                RETURN t.id AS id, t.title AS title, t.dueDate AS dueDate,

                       'due' AS type                       'due' AS type

                ORDER BY t.dueDate                ORDER BY t.dueDate

                LIMIT 50                LIMIT 50

            """)            """)

                        

            for record in result:            for record in result:

                due_date = record['dueDate']                due_date = record['dueDate']

                try:                try:

                    if isinstance(due_date, Date):                    if isinstance(due_date, Date):

                        # If it's a Date, create datetime at end of day IST                        # If it's a Date, create datetime at end of day IST

                        due_dt = datetime.combine(                        due_dt = datetime.combine(

                            due_date.to_native(),                            due_date.to_native(),

                            datetime.max.time()                            datetime.max.time()

                        ).replace(tzinfo=IST)                        ).replace(tzinfo=IST)

                    elif isinstance(due_date, DateTime):                    elif isinstance(due_date, DateTime):

                        due_dt = due_date.to_native()                        due_dt = due_date.to_native()

                        if due_dt.tzinfo is None:                        if due_dt.tzinfo is None:

                            due_dt = due_dt.replace(tzinfo=timezone.utc)                            due_dt = due_dt.replace(tzinfo=timezone.utc)

                        due_dt = due_dt.astimezone(IST)                        due_dt = due_dt.astimezone(IST)

                    else:                    else:

                        due_dt = datetime.fromisoformat(str(due_date))                        due_dt = datetime.fromisoformat(str(due_date))

                        if due_dt.tzinfo is None:                        if due_dt.tzinfo is None:

                            due_dt = due_dt.replace(tzinfo=IST)                            due_dt = due_dt.replace(tzinfo=IST)

                                        

                    time_diff = due_dt - now_ist                    time_diff = due_dt - now_ist

                    minutes_until = int(time_diff.total_seconds() / 60)                    minutes_until = int(time_diff.total_seconds() / 60)

                                        

                    # Include if within 24 hours                    # Include if within 24 hours

                    if -60 <= minutes_until <= 1440:  # From 1 hour ago to 24 hours ahead                    if -60 <= minutes_until <= 1440:  # From 1 hour ago to 24 hours ahead

                        notifications.append({                        notifications.append({

                            'id': f"due-{record['id']}",                            'id': f"due-{record['id']}",

                            'title': record['title'],                            'title': record['title'],

                            'type': 'due',                            'type': 'due',

                            'minutesUntil': minutes_until,                            'minutesUntil': minutes_until,

                            'dueTime': due_dt.strftime('%I:%M %p IST')                            'dueTime': due_dt.strftime('%I:%M %p IST')

                        })                        })

                except Exception as e:                except Exception as e:

                    print(f"Error processing due date for task {record['id']}: {e}")                    print(f"Error processing due date for task {record['id']}: {e}")

                    continue                    continue

                

        # Filter out notifications already marked as sent in-memory        # Filter out notifications already marked as sent in-memory

        filtered_notifications = [n for n in notifications if n['id'] not in NOTIFIED_TASK_KEYS]        filtered_notifications = [n for n in notifications if n['id'] not in NOTIFIED_TASK_KEYS]

        print(f"📬 Returning {len(filtered_notifications)} notifications (IST timezone) - filtered from {len(notifications)} total")        print(f"📬 Returning {len(filtered_notifications)} notifications (IST timezone) - filtered from {len(notifications)} total")

        return {'notifications': filtered_notifications, 'currentTime': now_ist.strftime('%I:%M %p IST')}        return {'notifications': filtered_notifications, 'currentTime': now_ist.strftime('%I:%M %p IST')}

    except Exception as e:    except Exception as e:

        print(f"Error in api_notifications_pending: {e}")        print(f"Error in api_notifications_pending: {e}")

        raise HTTPException(status_code=500, detail='Internal error')        raise HTTPException(status_code=500, detail='Internal error')

        





@app.get('/api/debug/tasks')@app.get('/api/debug/tasks')

async def debug_tasks():async def debug_tasks():

    """Debug endpoint to check all tasks in database"""    """Debug endpoint to check all tasks in database"""

    try:    try:

        with driver.session() as session:        with driver.session() as session:

            # Get all tasks            # Get all tasks

            result = session.run("""            result = session.run("""

                MATCH (t:Task)                 MATCH (t:Task) 

                RETURN t.id as id, t.title as title, t.status as status,                 RETURN t.id as id, t.title as title, t.status as status, 

                       t.startTime as startTime, t.createdAt as createdAt                       t.startTime as startTime, t.createdAt as createdAt

                ORDER BY t.createdAt DESC                ORDER BY t.createdAt DESC

                LIMIT 20                LIMIT 20

            """)            """)

            tasks = [dict(r) for r in result]            tasks = [dict(r) for r in result]

                        

            # Count tasks            # Count tasks

            count_result = session.run("MATCH (t:Task) RETURN count(t) as total")            count_result = session.run("MATCH (t:Task) RETURN count(t) as total")

            total = count_result.single()['total']            total = count_result.single()['total']

                        

            pending_result = session.run("MATCH (t:Task) WHERE t.status = 'pending' RETURN count(t) as count")            pending_result = session.run("MATCH (t:Task) WHERE t.status = 'pending' RETURN count(t) as count")

            pending = pending_result.single()['count']            pending = pending_result.single()['count']

                        

            # Count today's tasks            # Count today's tasks

            today = datetime.now(IST).date()            today = datetime.now(IST).date()

            today_result = session.run(            today_result = session.run(

                "MATCH (:Day {date: date($d)})-[:HAS_TASK]->(t:Task) RETURN count(t) as count",                "MATCH (:Day {date: date($d)})-[:HAS_TASK]->(t:Task) RETURN count(t) as count",

                d=today                d=today

            )            )

            today_count = today_result.single()['count']            today_count = today_result.single()['count']

                

        return {        return {

            'total_tasks': total,            'total_tasks': total,

            'pending_tasks': pending,            'pending_tasks': pending,

            'today_tasks': today_count,            'today_tasks': today_count,

            'today_date': str(today),            'today_date': str(today),

            'recent_tasks': tasks            'recent_tasks': tasks

        }        }

    except Exception as e:    except Exception as e:

        print(f"Error in debug endpoint: {e}")        print(f"Error in debug endpoint: {e}")

        raise HTTPException(status_code=500, detail=str(e))        raise HTTPException(status_code=500, detail=str(e))





# --- 6. App Execution ---# --- 6. App Execution ---

def populate_vector_db():def populate_vector_db():

    with driver.session() as session:    with driver.session() as session:

        results = session.run("MATCH (t:Task) WHERE t.description IS NOT NULL RETURN t.id AS id, t.description AS description")        results = session.run("MATCH (t:Task) WHERE t.description IS NOT NULL RETURN t.id AS id, t.description AS description")

        all_tasks = [r.data() for r in results]        all_tasks = [r.data() for r in results]

    if all_tasks:    if all_tasks:

        ids = [t['id'] for t in all_tasks]        ids = [t['id'] for t in all_tasks]

        descs = [t['description'] for t in all_tasks]        descs = [t['description'] for t in all_tasks]

        vector_db.upsert(ids=ids, embeddings=model.encode(descs).tolist())        vector_db.upsert(ids=ids, embeddings=model.encode(descs).tolist())

        print(f"Vector DB populated with {len(ids)} tasks.")        print(f"Vector DB populated with {len(ids)} tasks.")



if __name__ == '__main__':if __name__ == '__main__':

    # In dev we may skip model downloads / vector DB population to start quickly    # In dev we may skip model downloads / vector DB population to start quickly

    if os.getenv('SKIP_MODEL_LOAD', '0') == '1' or model is None:    if os.getenv('SKIP_MODEL_LOAD', '0') == '1' or model is None:

        print("SKIP_MODEL_LOAD active or no model loaded — skipping vector DB population for faster startup.")        print("SKIP_MODEL_LOAD active or no model loaded — skipping vector DB population for faster startup.")

    else:    else:

        try:        try:

            populate_vector_db()            populate_vector_db()

        except Exception as e:        except Exception as e:

            print(f"Warning: populate_vector_db failed: {e}")            print(f"Warning: populate_vector_db failed: {e}")

    print("\nStarting FastAPI server... accessible at http://0.0.0.0:5000")    print("\nStarting FastAPI server... accessible at http://0.0.0.0:5000")

    # start a background task for websocket watchers (cleaner if run under uvicorn)    # start a background task for websocket watchers (cleaner if run under uvicorn)

    async def _startup_tasks():    async def _startup_tasks():

        # placeholder for future background watchers        # placeholder for future background watchers

        return        return



    try:    try:

        import uvicorn        import uvicorn

        uvicorn.run(app, host='0.0.0.0', port=5000, log_level='info')        uvicorn.run(app, host='0.0.0.0', port=5000, log_level='info')

    except Exception:    except Exception:

        # fallback to direct uvicorn call if import above fails        # fallback to direct uvicorn call if import above fails

        uvicorn.run(app, host='0.0.0.0', port=5000, log_level='info')        uvicorn.run(app, host='0.0.0.0', port=5000, log_level='info')


