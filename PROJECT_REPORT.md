# TrackEneer — Cognitive Learning Ecosystem
## Comprehensive Project Report

---

## 1. Executive Summary

**TrackEneer** is an AI-powered Cognitive Learning Ecosystem designed to revolutionize how engineering students prepare, learn, and track their academic progress. The platform combines cutting-edge AI techniques including Knowledge Graphs, Natural Language Processing, adaptive learning algorithms, and career analytics to provide a **personalized, intelligent learning experience**.

The system automatically extracts knowledge from uploaded educational materials (PDFs, syllabi, notes), constructs visual concept maps, tracks student mastery over time, provides AI-powered mentoring through Socratic questioning, and predicts career readiness — all through a modern, interactive web interface.

### Key Highlights

| Metric | Value |
|--------|-------|
| Total Backend Modules | 8+ (Scheduler, Study, Placement, Knowledge Graph, Mentor, Knowledge Tracing, Career Readiness, Insights) |
| AI Models Used | Gemini 2.5 Flash, Sentence Transformers (MiniLM-L6), spaCy NLP |
| Databases | Neo4j (Graph DB), ChromaDB (Vector DB), MongoDB |
| Frontend Framework | Next.js 15, React 19, TailwindCSS 4 |
| API Endpoints | 30+ RESTful endpoints |
| Algorithms | NSGA-II, PSI-KT, Ebbinghaus Forgetting Curve, Force-Directed Graph Layout, SBERT Similarity |

---

## 2. Problem Statement

Engineering students face multiple challenges:

1. **Information Overload**: Syllabi contain hundreds of interconnected concepts with no clear visual structure
2. **Passive Learning**: Traditional study methods lack personalization and adaptability
3. **Unknown Weak Spots**: Students often don't know which foundational concepts they're missing
4. **No Feedback Loop**: There's no system tracking what they've learned vs. what they've forgotten
5. **Career Disconnect**: Students can't see how academic concepts map to industry-required skills
6. **Schedule Chaos**: Balancing multiple subjects with varying difficulty is overwhelming

**TrackEneer solves all of these** through an integrated AI-driven ecosystem.

---

## 3. System Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                      Next.js 15 Frontend                       │
│  Dashboard │ Knowledge Graph │ AI Mentor │ Mastery │ Career    │
│  Schedule  │ Study Plans     │ Placement │ Insights│ Timetable │
└────────────────────────┬──────────────────────────────────────┘
                         │ REST API (JSON)
┌────────────────────────┴──────────────────────────────────────┐
│              Unified FastAPI Backend (Port 5000)                │
│                                                                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────┐  │
│  │ knowledge_      │  │ mentor.py       │  │ knowledge_    │  │
│  │ graph.py        │  │ GraphRAG +      │  │ tracing.py    │  │
│  │ EduKG Engine    │  │ Socratic AI     │  │ PSI-KT Engine │  │
│  └────────┬────────┘  └────────┬────────┘  └───────┬───────┘  │
│           │                    │                    │          │
│  ┌────────┴────────┐  ┌───────┴─────────┐  ┌──────┴───────┐  │
│  │ career_         │  │ nsga2_          │  │ scheduler.py │  │
│  │ readiness.py    │  │ scheduler.py    │  │ study.py     │  │
│  │ Syllabus2Skill  │  │ Multi-Objective │  │ placement.py │  │
│  └─────────────────┘  └─────────────────┘  └──────────────┘  │
└────────────────────────┬──────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────────┐
        │                │                    │
   ┌────┴─────┐   ┌──────┴───────┐   ┌───────┴────────┐
   │  Neo4j   │   │  ChromaDB    │   │  Gemini API    │
   │ Graph DB │   │  Vector DB   │   │  + spaCy NLP   │
   │          │   │  (Embeddings)│   │  + SBERT       │
   └──────────┘   └──────────────┘   └────────────────┘
```

### Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | Next.js 15 + React 19 | Server-side rendered UI with app router |
| **Styling** | TailwindCSS 4 + Framer Motion | Responsive, animated design |
| **Backend** | Python FastAPI | High-performance async REST API |
| **Graph Database** | Neo4j | Stores concept graphs, prerequisites, relationships |
| **Vector Database** | ChromaDB | Stores document embeddings for RAG retrieval |
| **LLM** | Google Gemini 2.5 Flash | Concept extraction, mentoring, quiz generation |
| **Embeddings** | Sentence Transformers (MiniLM-L6-v2) | Semantic similarity, keyphrase extraction |
| **NLP** | spaCy (en_core_web_sm) | Named Entity Recognition, noun chunk extraction |
| **Authentication** | NextAuth.js | Google OAuth + credential-based login |
| **Scheduling** | NSGA-II (custom implementation) | Multi-objective study schedule optimization |

---

## 4. Core Modules — Detailed Analysis

---

### 4.1 Educational Knowledge Graph (EduKG) Engine

**File**: `server/knowledge_graph.py` (944 lines)  
**Frontend**: `client/src/app/knowledge-graph/page.jsx`

#### What It Does

The EduKG Engine automatically transforms unstructured educational documents (PDFs, text notes, syllabi) into a structured, visual **Knowledge Graph**. Each concept becomes a node, and relationships (prerequisites, part-of, related-to, leads-to) become edges in the graph.

#### How It Works

```
PDF/Text Upload → Text Extraction → Concept Extraction → Relation Discovery → Neo4j Storage → Visualization
```

**Step 1: Text Extraction**
- Uses `pdfplumber` to extract text from uploaded PDFs
- Handles multi-page documents with page-level tracking

**Step 2: Concept Extraction (Triple Strategy)**

The system uses three strategies, cascading from highest to lowest quality:

| Strategy | Method | Quality | Speed |
|----------|--------|---------|-------|
| **LLM** (Primary) | Gemini 2.5 Flash | ⭐⭐⭐⭐⭐ | Slow |
| **Embedding** (Secondary) | SBERT keyphrase extraction | ⭐⭐⭐⭐ | Medium |
| **NLP** (Fallback) | spaCy NER + heuristics | ⭐⭐⭐ | Fast |

For each concept, the system extracts:
- **Name**: Short descriptive name (e.g., "Binary Search Tree")
- **Description**: 1-2 sentence explanation
- **Category**: topic, subtopic, skill, theorem, algorithm, definition, formula
- **Difficulty**: easy, medium, hard
- **Bloom's Level**: remember, understand, apply, analyze, evaluate, create
- **Source Document**: Which uploaded file it came from
- **Source Page**: Page number in the original document

**Step 3: Relation Discovery**

Relations between concepts are discovered through:
- **LLM reasoning**: Gemini identifies prerequisite/part-of/related-to/leads-to relationships
- **Embedding similarity**: Cosine similarity > 0.6 between concept vectors = related
- **Document order heuristic**: Sequential concepts get prerequisite relationships

**Step 4: Graph Storage (Neo4j)**

```cypher
MERGE (concept:Concept {name: "Binary Search", userEmail: "student@example.com"})
ON CREATE SET concept.category = "algorithm", concept.difficulty = "medium"
MERGE (user)-[:HAS_CONCEPT]->(concept)
```

**Step 5: Graph Visualization**

The frontend renders an interactive **force-directed graph** with:
- **Physics simulation**: Nodes repel each other; edges attract connected nodes
- **Drag interaction**: Click and drag nodes to rearrange
- **Zoom/Pan**: Mouse wheel zoom, click-drag to pan
- **Smart labels**: Labels appear contextually (on hover, for connected nodes, when zoomed in)
- **Category coloring**: Each concept type gets a unique color
- **Mastery arcs**: Colored rings around nodes show mastery percentage
- **Document filtering**: View graph per-document to avoid clutter

#### Key Algorithms

**Bloom's Taxonomy Classifier** — Maps keywords to cognitive levels:
```
"define", "list", "recall" → Remember
"describe", "explain"      → Understand  
"implement", "solve"       → Apply
"compare", "contrast"      → Analyze
"assess", "justify"        → Evaluate
"design", "construct"      → Create
```

**Root Cause Analysis** — When a student struggles with a concept:
1. Traverse backward through the prerequisite chain
2. Find the prerequisite with the lowest mastery score
3. Recommend reviewing that foundational concept first

#### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/knowledge-graph/build` | Build KG from text input |
| POST | `/api/knowledge-graph/upload` | Build KG from uploaded PDF |
| GET | `/api/knowledge-graph` | Get full graph (with optional document filter) |
| GET | `/api/knowledge-graph/documents` | List uploaded source documents |
| GET | `/api/knowledge-graph/prerequisites/{concept}` | Get prerequisite chain |
| GET | `/api/knowledge-graph/subgraph/{concept}` | Get local subgraph (for RAG) |
| POST | `/api/knowledge-graph/mastery` | Update concept mastery |
| GET | `/api/knowledge-graph/weaknesses` | Get weak concepts (< threshold) |
| GET | `/api/knowledge-graph/root-cause/{concept}` | Root cause analysis |
| POST | `/api/knowledge-graph/enrich` | LLM-powered graph enrichment |
| DELETE | `/api/knowledge-graph` | Delete user's entire graph |

---

### 4.2 GraphRAG + Socratic AI Mentor

**File**: `server/mentor.py` (401 lines)  
**Frontend**: `client/src/app/mentor/page.jsx`

#### What It Does

An AI tutoring system that combines **Graph-based Retrieval Augmented Generation (GraphRAG)** with pedagogical strategies. Instead of just answering questions, it teaches through guided questioning, explanation, and connecting ideas across the knowledge graph.

#### How It Works

```
Student Question → GraphRAG Retrieval → Mode Selection → LLM Response → Citation + Confidence Scoring
```

**GraphRAG Retriever**:
1. Find the most relevant concept node in the Knowledge Graph
2. Retrieve the local subgraph (2-hop neighborhood)  
3. Query ChromaDB for semantically similar document chunks
4. Combine graph context + vector context for the LLM prompt

#### 5 Pedagogical Modes

| Mode | Teaching Style | Example Behavior |
|------|---------------|------------------|
| **Socratic** | Guided questioning | "What do you think happens when we insert into a balanced tree?" |
| **Explain** | Clear explanation | "A B-tree is a self-balancing search tree that maintains sorted data..." |
| **Quiz** | Test knowledge | "Q: What is the time complexity of binary search? A/B/C/D" |
| **Connect** | Cross-concept links | "Binary search is similar to how a balanced BST works because..." |
| **Plan** | Study planning | "Based on your weak areas, I recommend: 1. Review sorting, 2. Practice..." |

#### Safety Features

- **Citation Grounding**: Every claim links back to source documents
- **Confidence Scoring**: 0.0–1.0 score based on retrieval quality
- **Hallucination Guardrails**: If confidence drops below threshold, the mentor admits uncertainty
- **Conversation History**: Multi-turn context awareness within a session

#### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/mentor/chat` | Chat with the AI mentor (specify mode) |
| GET | `/api/mentor/recommendations` | Get personalized study recommendations |
| GET | `/api/mentor/history/{session}` | Retrieve conversation history |
| DELETE | `/api/mentor/history/{session}` | Clear a conversation session |
| POST | `/api/mentor/index` | Index new notes into the vector store |

---

### 4.3 Knowledge Tracing Engine (PSI-KT)

**File**: `server/knowledge_tracing.py` (723 lines)  
**Frontend**: `client/src/app/knowledge-tracing/page.jsx`

#### What It Does

The **Prerequisite-aware Spaced-repetition Intelligent Knowledge Tracing (PSI-KT)** engine models each student's learning state at a granular concept level. It tracks what they know, predicts what they've forgotten, identifies knowledge gaps, and generates adaptive quizzes.

#### Core Algorithm: Mastery Update

```python
# Step 1: Apply Ebbinghaus forgetting curve
hours_elapsed = time_since_last_interaction
decay = e^(-forgetting_rate × hours_elapsed)
mastery = mastery × decay

# Step 2: Prerequisite mastery bonus
prereq_mastery = average_mastery_of_prerequisites(concept)

# Step 3: Update based on correctness
if correct:
    gain = BASE_GAIN × (1 + prereq_bonus) × streak_multiplier
    mastery = min(0.99, mastery + gain)
else:
    mastery = max(0.01, mastery - LOSS_PENALTY)
```

#### Key Features

**1. Forgetting Curve Modeling (Ebbinghaus)**
- Mastery decays exponentially over time when not reviewed
- Decay rate adapts per student: fast forgetter → more frequent review
- Formula: `M(t) = M₀ × e^(-λt)` where λ = forgetting rate

**2. Adaptive Learning Rate**
- Students who consistently answer correctly get faster mastery gains
- Students who struggle get slower, more gradual improvements
- Learning rate adjusts based on rolling accuracy

**3. Prerequisite-Aware Updates**
- Mastering prerequisites gives a bonus when learning advanced concepts
- If you know "Sorting Algorithms" well, learning "Merge Sort" is boosted
- Uses the Knowledge Graph's prerequisite chain for calculations

**4. Gap Analysis with Root Cause Detection**
```
Weak Concepts → Root Cause Traversal → Time-to-Mastery Estimation → Prioritized Plan
```
For each weak concept:
- Traces back through prerequisites to find the "root cause"
- Estimates hours needed to reach mastery
- Generates a prioritized remediation plan

**5. Spaced Repetition Scheduler**
- Uses the forgetting curve to predict when mastery will drop below threshold
- Schedules review at the optimal moment (just before forgetting)
- Concepts requiring review are ranked by urgency

**6. Adaptive Quiz Generation**
- Uses Gemini to generate questions tailored to the student's level
- Adjusts Bloom's Taxonomy level based on current mastery:
  - Low mastery → Remember/Understand questions
  - Medium mastery → Apply/Analyze questions
  - High mastery → Evaluate/Create questions
- Mixes question types: multiple choice, true/false, short answer
- Auto-evaluates answers and updates mastery state

#### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/knowledge-tracing/state` | Get full knowledge state for all concepts |
| POST | `/api/knowledge-tracing/update` | Update mastery after an interaction |
| GET | `/api/knowledge-tracing/gaps` | Gap analysis with root causes |
| GET | `/api/knowledge-tracing/due-review` | Get concepts due for spaced review |
| POST | `/api/quiz/generate` | Generate adaptive quiz questions |
| POST | `/api/quiz/evaluate` | Evaluate answer and update KT state |

---

### 4.4 Career Readiness & Syllabus2Skill Pipeline

**File**: `server/career_readiness.py` (709 lines)  
**Frontend**: `client/src/app/career/page.jsx`

#### What It Does

Maps academic knowledge to industry skills, predicts placement readiness, and provides actionable career guidance — bridging the gap between classroom learning and job requirements.

#### Core Components

**1. Syllabus2Skill Mapper**

Uses SBERT (Sentence-BERT) to semantically match academic concepts to an industry skills taxonomy:

```
Academic Concept: "Binary Search Tree"
     ↓ SBERT Encoding → 384-dim vector
     ↓ Cosine Similarity against skill taxonomy
Matched Skills:
  - Data Structures    (0.92 similarity)
  - Algorithm Design   (0.85 similarity)
  - Problem Solving    (0.78 similarity)
```

The skills taxonomy is inspired by ESCO/O*NET and covers:
- Software Development (15 skills)
- Data Science (10 skills)
- Systems & Infrastructure (10 skills)
- Professional Skills (8 skills)

**2. Placement Readiness Predictor**

A multi-factor prediction model that computes readiness based on:

| Factor | Weight | Description |
|--------|--------|-------------|
| Technical Skills Coverage | 30% | % of required skills the student has |
| Average Mastery | 25% | Mean mastery across all concepts |
| Skill Diversity | 15% | Breadth of skills across domains |
| Total Concepts | 10% | Volume of concepts learned |
| High Mastery Ratio | 10% | % of concepts with mastery > 0.7 |
| Learning Consistency | 10% | Regularity of learning activity |

**3. XAI (Explainable AI) Feature Contributions**

For every prediction, the system explains **why** by showing each factor's contribution:
```
📊 Readiness: 72%

Feature Contributions:
  ✅ Technical Skills:  +24%  (Strong coverage of required skills)
  ✅ Average Mastery:   +18%  (Good understanding of concepts)
  ⚠️  Skill Diversity:  +8%   (Could explore more domains)
  ❌ High Mastery:      +5%   (Few concepts at expert level)
```

**4. Resume Analysis**

Uses Gemini to analyze uploaded resumes and provide:
- Skill extraction from resume text
- Gap analysis vs. target role requirements
- Actionable improvement suggestions
- Alignment score with desired career path

#### 6 Target Job Roles

| Role | Key Skill Areas |
|------|----------------|
| Software Developer | Programming, Web Dev, Databases |
| Data Scientist | ML, Statistics, Data Visualization |
| DevOps Engineer | Cloud, CI/CD, Infrastructure |
| ML Engineer | Deep Learning, NLP, Model Deployment |
| Full Stack Developer | Frontend, Backend, Databases, APIs |
| Cybersecurity Analyst | Network Security, Encryption, Forensics |

#### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/career/map-skills` | Map concepts to industry skills |
| GET | `/api/career/skill-profile` | Get student's skill profile |
| POST | `/api/career/predict-readiness` | Placement prediction with XAI |
| GET | `/api/career/roles` | List available target roles |
| POST | `/api/career/analyze-resume` | AI-powered resume analysis |

---

### 4.5 NSGA-II Study Schedule Optimizer

**File**: `server/nsga2_scheduler.py` (29K bytes)

#### What It Does

Uses the **Non-dominated Sorting Genetic Algorithm II (NSGA-II)** — a multi-objective evolutionary optimization algorithm — to generate optimal study schedules that balance multiple conflicting goals.

#### Optimization Objectives

The algorithm simultaneously optimizes:

1. **Minimize Stress**: Avoid overloading difficult subjects consecutively
2. **Maximize Coverage**: Ensure all subjects get adequate study time
3. **Minimize Gaps**: Reduce large breaks between studying the same subject
4. **Balance Difficulty**: Distribute hard and easy subjects throughout the week

#### How NSGA-II Works

```
Initialize Population (random schedules)
    ↓ Repeat for N generations:
    ├── Non-dominated Sorting (Pareto fronts)
    ├── Crowding Distance Assignment
    ├── Tournament Selection
    ├── Crossover (swap time slots between parents)
    ├── Mutation (randomly change subject allocation)
    └── Survivor Selection
    ↓
Output: 3 Schedule Options (Balanced, Low Stress, High Focus)
```

The output provides **three distinct schedule options** on the Pareto front:
- **Balanced**: Equal weightage across all objectives
- **Low Stress**: Prioritizes minimal cognitive load
- **High Focus**: Maximizes deep work sessions for hard subjects

---

### 4.6 Existing Core Modules

#### Study Plan Generator (`study.py`)
- Generates personalized study plans based on syllabus analysis
- Time allocation based on subject difficulty and exam proximity
- Resource recommendations (textbooks, online courses)

#### Placement Preparation (`placement.py`)
- Company-wise preparation guides based on `companies.json` (27K data)
- Technical interview topic prioritization
- Resume and soft skills guidance

#### Academic Insights (`insights.py`)
- Year-wise, branch-wise preparation guides stored in `insights.json`
- AI-generated comprehensive guides covering:
  - Key focus areas
  - Study strategies
  - Technical skills roadmap
  - Project ideas with difficulty and time estimates
  - Placement preparation timeline
  - Career guidance

#### Document Processor (`document_processor.py`)
- Advanced PDF processing (188K lines — the largest module)
- Text extraction, OCR support, layout analysis
- Multi-format document handling

---

## 5. Frontend Architecture

### Pages & Routes

| Route | Page | Description |
|-------|------|-------------|
| `/` | Landing Page | Hero section, feature showcase |
| `/login` | Login | Google OAuth + credential login |
| `/dashboard` | Dashboard | 8-module quick access grid |
| `/knowledge-graph` | Knowledge Graph | Interactive force-directed graph visualization |
| `/mentor` | AI Mentor | Chat interface with 5 pedagogical modes |
| `/knowledge-tracing` | Mastery Tracker | Mastery rings, gap analysis, adaptive quizzing |
| `/career` | Career Readiness | Placement prediction, skill mapping, resume analysis |
| `/schedule` | Study Schedule | NSGA-II optimized schedules |
| `/study` | Study Plans | Subject-wise preparation guides |
| `/placement` | Placement Prep | Company-wise interview preparation |
| `/insights` | Academic Insights | Year/branch-wise preparation guides |
| `/timetable` | Timetable | Class schedule management |
| `/research` | Research | Academic research tools |

### Design System

- **Dark theme** with gradient backgrounds (`slate-950` → `slate-900`)
- **Glassmorphism** cards with `backdrop-blur` and semi-transparent borders
- **Gradient text** for headings (cyan-400 → blue-500)
- **Micro-animations** on hover, transitions on state changes
- **Responsive** layout adapting to all screen sizes
- **Color-coded** elements: emerald=good, amber=warning, red=critical

---

## 6. Data Flow Diagrams

### Knowledge Graph Build Pipeline
```
Student uploads PDF
    → pdfplumber extracts text
    → Gemini extracts concepts + relations (JSON)
    → Concepts stored as Neo4j nodes  
    → Relations stored as Neo4j edges
    → Frontend polls for completion
    → Document auto-selected in dropdown
    → Force-directed graph renders
```

### AI Mentor Chat Flow
```
Student asks question
    → GraphRAG: search KG for relevant concept
    → Retrieve 2-hop subgraph from Neo4j
    → Query ChromaDB for similar passages
    → Combine context + mode instruction
    → Gemini generates pedagogical response
    → Citation grounding + confidence scoring
    → Response displayed with citations
```

### Knowledge Tracing Update Flow
```
Student answers quiz question
    → Apply forgetting curve decay
    → Check prerequisite mastery bonus
    → Update mastery (gain if correct, loss if incorrect)
    → Adjust learning rate based on streak
    → Recalculate spaced review schedule
    → Update mastery rings on frontend
```

### Career Readiness Prediction Flow
```
Student requests readiness check
    → Fetch all concept mastery states
    → SBERT encode concepts → match to skills
    → Compute 6-factor readiness score
    → Generate XAI feature contributions
    → Display prediction with explanations
```

---

## 7. Database Schema

### Neo4j Graph Schema

```
(:User {email, name, year, branch})
    -[:HAS_CONCEPT]->
(:Concept {
    name, description, category, difficulty,
    bloom_level, mastery, source_document,
    source_page, createdAt, updatedAt
})

(:Concept)-[:PREREQUISITE_OF {confidence, source}]->(:Concept)
(:Concept)-[:PART_OF {confidence}]->(:Concept)
(:Concept)-[:RELATED_TO {confidence}]->(:Concept)
(:Concept)-[:LEADS_TO {confidence}]->(:Concept)
```

### ChromaDB Collections
- **Document chunks**: Embedded text passages for RAG retrieval
- **Concept embeddings**: 384-dim vectors for semantic search

---

## 8. Security & Authentication

- **NextAuth.js** provides secure authentication
- Google OAuth 2.0 integration for single sign-on
- Credential-based login as fallback
- Session-based user identification across all API calls
- Per-user data isolation (all queries filtered by `userEmail`)

---

## 9. Key Innovations

### 1. Multi-Strategy Knowledge Extraction
Unlike single-method approaches, TrackEneer cascades through LLM → Embedding → NLP extraction, ensuring reliable concept extraction even when the LLM is unavailable.

### 2. Graph-Augmented RAG (GraphRAG)
Traditional RAG only uses vector similarity. TrackEneer combines **Knowledge Graph traversal** (structural context) with **vector search** (semantic context) for more accurate, grounded AI responses.

### 3. Prerequisite-Aware Learning
The PSI-KT engine doesn't just track mastery — it understands concept dependencies. If you're struggling with "Merge Sort", it traces back to "Recursion" and "Divide & Conquer" to find the actual root cause.

### 4. Explainable Career Prediction
Instead of a black-box "72% ready" score, the system shows exactly which factors contribute positively or negatively, empowering students to take targeted action.

### 5. Document-Scoped Knowledge Graphs
Students can view concept graphs filtered by source document, preventing information overload when dealing with multiple courses. Each uploaded PDF becomes its own navigable knowledge world.

### 6. Force-Directed Interactive Visualization
The custom-built canvas-based physics engine provides a fluid, interactive graph experience without heavy external libraries — draggable nodes, zoom, pan, hover highlighting, and smart label visibility.

---

## 10. Performance Characteristics

| Operation | Expected Latency |
|-----------|-----------------|
| Graph retrieval (full) | < 500ms |
| Concept extraction (LLM) | 3-8 seconds |
| Mentor chat response | 2-5 seconds |
| Quiz generation | 3-6 seconds |
| Career prediction | < 1 second |
| Force-directed layout | 60 FPS (canvas) |
| NSGA-II schedule | 5-15 seconds |

---

## 11. Deployment Requirements

| Component | Requirement |
|-----------|-------------|
| **Python** | 3.11+ |
| **Node.js** | 18+ |
| **Neo4j** | 5.x (Community or Enterprise) |
| **RAM** | 8GB minimum (Sentence Transformers model) |
| **API Keys** | Google Gemini API key |
| **GPU** | Not required (runs on CPU) |

### Environment Variables
```env
GEMINI_API_KEY=your_gemini_api_key
NEO4J_URI=neo4j://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
NEXT_PUBLIC_SCHEDULER_API=http://localhost:5000
```

---

## 12. Future Enhancements

1. **Collaborative Learning**: Multi-student knowledge graph comparison and group study recommendations
2. **Spaced Repetition Notifications**: Push notifications for review reminders
3. **Multi-Language Support**: Concept extraction from non-English educational materials
4. **Assessment Analytics**: Detailed exam performance trends and predictive scoring
5. **LMS Integration**: Direct integration with Moodle, Canvas, or Google Classroom
6. **Mobile Application**: React Native companion app for on-the-go learning
7. **Peer Tutoring Matching**: Match students with complementary strengths/weaknesses

---

## 13. Conclusion

TrackEneer's Cognitive Learning Ecosystem represents a **paradigm shift** in educational technology — moving from passive content delivery to **active, AI-powered learning guidance**. By combining Knowledge Graphs, adaptive learning algorithms, multi-modal AI, and career analytics into a single unified platform, it provides engineering students with the tools they need to learn smarter, track their progress, and prepare for their careers with confidence.

The system's modular architecture ensures each component can evolve independently while the unified FastAPI backend provides seamless integration. The modern Next.js frontend delivers a premium, interactive experience that makes complex academic data accessible and actionable.

---

*Report generated for TrackEneer v2.0 — February 2026*  
*Cognitive Learning Ecosystem — Xavier Institute of Engineering*
