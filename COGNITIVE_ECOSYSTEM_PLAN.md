# Cognitive Learning Ecosystem – Implementation Plan

## Architecture Overview

```
┌───────────────────────────────────────────────────────────┐
│                     Next.js Frontend                       │
│  Knowledge Graph │ AI Mentor │ Mastery │ Career Readiness  │
└──────────────────────────┬────────────────────────────────┘
                           │ REST API
┌──────────────────────────┴────────────────────────────────┐
│                  Unified FastAPI (port 5000)               │
│  ┌──────────────┐ ┌────────────┐ ┌───────────────────┐    │
│  │knowledge_    │ │ mentor.py  │ │knowledge_tracing  │    │
│  │graph.py      │ │ GraphRAG + │ │.py PSI-KT Engine  │    │
│  │ EduKG Engine │ │ Socratic AI│ │ Adaptive Quizzing │    │
│  └──────┬───────┘ └─────┬──────┘ └────────┬──────────┘    │
│         │               │                 │               │
│  ┌──────┴───────┐ ┌─────┴──────┐ ┌────────┴──────────┐   │
│  │career_       │ │ scheduler  │ │ study / placement  │   │
│  │readiness.py  │ │ .py        │ │ / insights .py     │   │
│  │ Syllabus2Skill│ │ NSGA-II    │ │ (existing modules) │   │
│  └──────────────┘ └────────────┘ └───────────────────┘    │
└──────────────────────────┬────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
     ┌────┴────┐    ┌──────┴──────┐  ┌──────┴──────┐
     │  Neo4j  │    │  ChromaDB   │  │   Gemini    │
     │Graph DB │    │ Vector DB   │  │   LLM API   │
     └─────────┘    └─────────────┘  └─────────────┘
```

## Existing Stack
- **Frontend**: Next.js 15, React 19, TailwindCSS 4, Framer Motion
- **Backend**: Python FastAPI (unified at port 5000)
- **Databases**: Neo4j (Graph DB), ChromaDB (Vector DB)
- **AI**: Sentence Transformers, spaCy, Gemini, Cohere

---

## Implementation Status

### Phase 1: Educational Knowledge Graph (EduKG) ✅ COMPLETE
**File**: `server/knowledge_graph.py`
- Multi-strategy concept extraction (LLM, embedding, NLP)
- Neo4j storage with prerequisite chains
- Graph traversal, subgraph retrieval
- Mastery tracking, root cause analysis
- PDF/text upload with background processing
- LLM-based graph enrichment
- **Frontend**: `client/src/app/knowledge-graph/page.jsx`

### Phase 2: GraphRAG + Socratic AI Mentor ✅ COMPLETE
**File**: `server/mentor.py`
- GraphRAG retriever (KG traversal + vector similarity)
- 5 pedagogical modes: Socratic, Explain, Quiz, Connect, Plan
- Citation grounding and confidence scoring
- Hallucination guardrails (threshold-based)
- Conversation history management
- Study recommendations engine
- **Frontend**: `client/src/app/mentor/page.jsx`

### Phase 3: Knowledge Tracing Engine (PSI-KT) ✅ COMPLETE
**File**: `server/knowledge_tracing.py`
- PSI-KT with adaptive learning/forgetting rates
- Ebbinghaus forgetting curve modeling
- Bloom's Taxonomy alignment
- Gap analysis with root cause detection
- Spaced repetition scheduling
- Adaptive quiz generation (LLM-based)
- Quiz evaluation with mastery updates
- **Frontend**: `client/src/app/knowledge-tracing/page.jsx`

### Phase 4: Career Readiness & Syllabus2Skill ✅ COMPLETE
**File**: `server/career_readiness.py`
- ESCO/O*NET-inspired skills taxonomy
- SBERT-based concept→skill mapping
- 6 job role templates with requirements
- Placement readiness prediction with XAI
- Feature contribution analysis (SHAP-like)
- Resume analysis with Gemini
- **Frontend**: `client/src/app/career/page.jsx`

### Phase 5: Unified Backend Integration ✅ COMPLETE
**File**: `server/app.py`
- All 4 modules integrated with graceful fallback
- Health endpoint reports module status
- Automatic module discovery with error handling

### Phase 6: Frontend Dashboard ✅ COMPLETE
**File**: `client/src/app/dashboard/page.js`
- 8-module quick access grid (4 original + 4 new)
- Links to Knowledge Graph, AI Mentor, Mastery, Career

---

## API Endpoints Summary

### Knowledge Graph (`/api/knowledge-graph/*`)
- `POST /build` – Build KG from text
- `POST /upload` – Build KG from file
- `GET /` – Get full graph
- `GET /prerequisites/{concept}` – Get prerequisites
- `GET /subgraph/{concept}` – Get subgraph
- `POST /mastery` – Update concept mastery
- `GET /weaknesses` – Get weak concepts
- `GET /root-cause/{concept}` – Root cause analysis
- `POST /enrich` – Enrich with LLM
- `DELETE /` – Delete user's graph

### AI Mentor (`/api/mentor/*`)
- `POST /chat` – Chat with mentor (modes: socratic/explain/quiz/connect/plan)
- `GET /recommendations` – Study recommendations
- `GET /history/{session_id}` – Conversation history
- `DELETE /history/{session_id}` – Clear conversation
- `POST /index` – Index notes for RAG

### Knowledge Tracing (`/api/knowledge-tracing/*`)
- `GET /state` – Full knowledge state
- `POST /update` – Update mastery after interaction
- `GET /gaps` – Gap analysis with root causes
- `GET /due-review` – Spaced repetition concepts

### Quiz (`/api/quiz/*`)
- `POST /generate` – Generate adaptive quiz
- `POST /evaluate` – Evaluate answer + update KT

### Career Readiness (`/api/career/*`)
- `POST /map-skills` – Map concepts to skills
- `GET /skill-profile` – Student's skill profile
- `POST /predict-readiness` – Placement prediction with XAI
- `GET /roles` – Available target roles
- `POST /analyze-resume` – Resume analysis
