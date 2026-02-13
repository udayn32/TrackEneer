"""
GraphRAG Socratic AI Mentor
============================

Implements an intelligent tutoring chatbot that combines:
1. GraphRAG – Knowledge Graph traversal + vector similarity retrieval
2. Socratic Prompting – Guided discovery through probing questions
3. Citation Grounding – All responses cite specific source material
4. Hallucination Guardrails – Confidence thresholds & graph constraints

The mentor operates in multiple pedagogical modes:
- EXPLAIN: Break down a concept clearly
- SOCRATIC: Guide through questions (default)  
- QUIZ: Test understanding with adaptive questions
- CONNECT: Relate concepts across the knowledge graph
- PLAN: Generate study plans using prerequisite chains
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

# ─── Internal modules ───
from db import get_driver
from graph_helpers import ensure_user_and_day, normalize_day

# ─── Knowledge Graph ───
from knowledge_graph import KnowledgeGraphStore, EduKGPipeline

# ─── Embeddings ───
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    HAS_SBERT = True
except ImportError:
    HAS_SBERT = False
    np = None

# ─── ChromaDB for vector storage ───
try:
    import chromadb
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False

# ─── Gemini ───
try:
    import google.generativeai as genai
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "AIzaSyDL1SqUudycymjYNnlm4z7ajfFkL3ht77k"
    genai.configure(api_key=GEMINI_API_KEY)
    _gemini = genai.GenerativeModel("gemini-2.5-flash")
    HAS_GEMINI = True
except Exception:
    HAS_GEMINI = False
    _gemini = None


# ============================================================================
# GRAPHRAG RETRIEVER
# ============================================================================

class GraphRAGRetriever:
    """
    Combines graph traversal with vector similarity for rich context assembly.
    
    When a student asks a question:
    1. Entity Mapping – Identify concepts in the query
    2. Graph Traversal – Retrieve prerequisite chains & related subgraphs
    3. Vector Search – Find similar text chunks from uploaded notes
    4. Context Assembly – Merge structured graph context + text chunks
    """

    def __init__(self):
        self.kg_store = KnowledgeGraphStore()
        self._embed_model = None
        self._chroma_client = None
        self._collection = None

    @property
    def embed_model(self):
        if self._embed_model is None and HAS_SBERT:
            model_path = os.getenv("EMBED_MODEL", "./all-MiniLM-L6-v2")
            try:
                self._embed_model = SentenceTransformer(model_path)
            except Exception:
                pass
        return self._embed_model

    @property
    def collection(self):
        if self._collection is None and HAS_CHROMA:
            self._chroma_client = chromadb.Client()
            self._collection = self._chroma_client.get_or_create_collection(
                name="mentor_knowledge_base",
            )
        return self._collection

    def index_text(self, text: str, user_email: str, source: str = "", metadata: dict = None):
        """Index text chunks into the vector store for RAG retrieval."""
        if not self.embed_model or not self.collection:
            return

        # Chunk the text
        chunks = self._chunk_text(text, chunk_size=500, overlap=100)

        for i, chunk in enumerate(chunks):
            chunk_id = f"{user_email}_{source}_{i}"
            embedding = self.embed_model.encode([chunk])[0].tolist()

            meta = {
                "user_email": user_email,
                "source": source,
                "chunk_index": i,
            }
            if metadata:
                meta.update(metadata)

            self.collection.upsert(
                ids=[chunk_id],
                embeddings=[embedding],
                documents=[chunk],
                metadatas=[meta],
            )

    def retrieve(self, query: str, user_email: str, top_k: int = 5) -> dict:
        """
        Full GraphRAG retrieval pipeline:
        1. Identify concepts in query
        2. Retrieve graph context (prerequisites, related concepts)
        3. Retrieve similar text chunks from vector store
        4. Assemble unified context
        """
        # Step 1: Identify concepts mentioned in the query
        graph_context = self._retrieve_graph_context(query, user_email)

        # Step 2: Retrieve text chunks from vector store
        vector_context = self._retrieve_vector_context(query, user_email, top_k)

        # Step 3: Assemble context
        context = self._assemble_context(graph_context, vector_context)

        return context

    def _retrieve_graph_context(self, query: str, user_email: str) -> dict:
        """Retrieve structured context from the Knowledge Graph."""
        # Get the full graph to find matching concepts
        graph = self.kg_store.get_full_graph(user_email)
        if not graph["nodes"]:
            return {"concepts": [], "prerequisites": [], "relations": []}

        # Find concepts mentioned in query (fuzzy match)
        query_lower = query.lower()
        matching_concepts = []
        for node in graph["nodes"]:
            name_lower = node["name"].lower()
            if name_lower in query_lower or any(
                word in query_lower for word in name_lower.split() if len(word) > 3
            ):
                matching_concepts.append(node)

        # If no direct matches, use embedding similarity
        if not matching_concepts and self.embed_model:
            try:
                query_emb = self.embed_model.encode([query])[0]
                concept_names = [n["name"] for n in graph["nodes"]]
                concept_embs = self.embed_model.encode(concept_names)

                similarities = []
                for i, emb in enumerate(concept_embs):
                    sim = float(np.dot(query_emb, emb) / (np.linalg.norm(query_emb) * np.linalg.norm(emb) + 1e-8))
                    similarities.append((graph["nodes"][i], sim))

                similarities.sort(key=lambda x: x[1], reverse=True)
                matching_concepts = [s[0] for s in similarities[:3] if s[1] > 0.3]
            except Exception:
                pass

        # Retrieve prerequisites and subgraphs for matching concepts
        all_prereqs = []
        all_related = []
        for concept in matching_concepts[:3]:
            try:
                prereqs = self.kg_store.get_prerequisites(concept["name"], user_email)
                all_prereqs.extend(prereqs)
            except Exception:
                pass
            try:
                subgraph = self.kg_store.get_subgraph(concept["name"], user_email, hops=1)
                all_related.extend(subgraph.get("nodes", []))
            except Exception:
                pass

        return {
            "concepts": matching_concepts[:5],
            "prerequisites": all_prereqs[:10],
            "relations": graph["edges"][:20],
            "related": all_related[:10],
        }

    def _retrieve_vector_context(self, query: str, user_email: str, top_k: int = 5) -> List[dict]:
        """Retrieve similar text chunks from the vector store."""
        if not self.embed_model or not self.collection:
            return []

        try:
            query_embedding = self.embed_model.encode([query])[0].tolist()
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where={"user_email": user_email},
            )

            chunks = []
            if results and results["documents"]:
                for i, doc in enumerate(results["documents"][0]):
                    meta = results["metadatas"][0][i] if results["metadatas"] else {}
                    distance = results["distances"][0][i] if results["distances"] else 1.0
                    chunks.append({
                        "text": doc,
                        "source": meta.get("source", "unknown"),
                        "relevance": max(0, 1 - distance),
                    })

            return chunks
        except Exception as e:
            print(f"⚠ Vector retrieval failed: {e}")
            return []

    def _assemble_context(self, graph_context: dict, vector_chunks: List[dict]) -> dict:
        """Assemble a unified context from graph and vector retrieval."""
        # Build structured context string
        parts = []

        # Graph context
        if graph_context["concepts"]:
            parts.append("## Relevant Concepts from Knowledge Graph")
            for c in graph_context["concepts"]:
                desc = f" - {c.get('description', '')}" if c.get('description') else ""
                mastery = f" (Mastery: {int(c.get('mastery', 0) * 100)}%)" if c.get('mastery') else ""
                parts.append(f"- **{c['name']}** [{c.get('difficulty', 'medium')}]{desc}{mastery}")

        if graph_context["prerequisites"]:
            parts.append("\n## Prerequisites")
            for p in graph_context["prerequisites"]:
                mastery = f" (Mastery: {int((p.get('mastery') or 0) * 100)}%)" if p.get('mastery') is not None else ""
                parts.append(f"- {p['name']}{mastery}")

        if graph_context.get("related"):
            parts.append("\n## Related Concepts")
            for r in graph_context["related"][:5]:
                if isinstance(r, dict):
                    parts.append(f"- {r.get('name', '')} [{r.get('category', '')}]")

        # Vector context
        if vector_chunks:
            parts.append("\n## Relevant Notes (from your uploaded materials)")
            for chunk in vector_chunks:
                if chunk.get("relevance", 0) > 0.3:
                    parts.append(f"\n**Source: {chunk['source']}** (Relevance: {chunk['relevance']:.0%})")
                    parts.append(chunk["text"][:500])

        context_text = "\n".join(parts) if parts else "No specific context found in your materials."

        return {
            "context_text": context_text,
            "graph_concepts": graph_context["concepts"],
            "prerequisites": graph_context["prerequisites"],
            "vector_chunks": vector_chunks,
            "has_graph_context": bool(graph_context["concepts"]),
            "has_vector_context": bool(vector_chunks),
        }

    def _chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 100) -> List[str]:
        """Split text into overlapping chunks."""
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk.strip())
            start += chunk_size - overlap

        return chunks


# ============================================================================
# SOCRATIC MENTOR ENGINE
# ============================================================================

class SocraticMentor:
    """
    AI tutoring engine implementing pedagogical strategies:
    - Socratic Questioning (elenchus + maieutics)
    - Chain-of-Thought Prompting
    - Adaptive Scaffolding
    - Misconception Analysis
    """

    # ─── Pedagogical Mode System Prompts ───

    SYSTEM_PROMPTS = {
        "socratic": """You are a Socratic tutor for a university student. Your role is to guide the student 
to understand concepts through thoughtful, probing questions rather than giving direct answers.

RULES:
1. NEVER give the direct answer immediately. Instead, ask a guiding question.
2. Break complex topics into smaller, manageable steps.
3. Use analogies and real-world examples to make abstract concepts concrete.
4. If the student is stuck, provide a small hint, then ask another guiding question.
5. When the student arrives at the correct understanding, reinforce it positively.
6. Reference their specific course materials when possible (see CONTEXT below).
7. Always cite the source (e.g., "As covered in your notes on...").
8. If the topic is NOT in their materials, say: "This topic isn't in your uploaded materials, but here's what I know..."

PEDAGOGICAL TECHNIQUES:
- Elenchus: Ask questions that expose contradictions in the student's reasoning
- Maieutics: Guide the student to "give birth" to ideas through their own reasoning
- Chain-of-Thought: "Let's think step by step..."
- Scaffolding: Start simple, gradually increase complexity

FORMAT:
- Use markdown for clear formatting
- Include 💡 for hints, ❓ for questions, ✅ for confirmations
- Keep responses concise but pedagogically rich""",

        "explain": """You are an expert educational tutor. Explain the requested concept clearly and thoroughly.

RULES:
1. Start with a simple, intuitive explanation.
2. Then dive deeper with technical details.
3. Provide at least one concrete example or analogy.
4. Reference the student's specific course materials (see CONTEXT below).
5. Cite sources: "According to your [source document], ..."
6. Mention prerequisites if relevant.
7. End with a brief comprehension check question.

FORMAT: Use markdown with headers, bullet points, and code blocks where appropriate.""",

        "quiz": """You are an adaptive quiz master. Generate questions that test the student's understanding.

RULES:
1. Generate 3-5 questions of varying difficulty (aligned to Bloom's Taxonomy).
2. Include: 1 Remember/Understand, 1-2 Apply/Analyze, 1 Evaluate/Create level question.
3. Mix question types: multiple choice, short answer, and problem-solving.
4. Base questions on the student's course materials (see CONTEXT below).
5. After each question, be ready to explain the correct answer if needed.
6. Track which Bloom level each question targets.

FORMAT:
**Question 1** [Bloom Level: Remember] 📝
...

**Question 2** [Bloom Level: Apply] 🔧
...""",

        "connect": """You are a knowledge connector. Help the student see relationships between concepts.

RULES:
1. Identify explicit and implicit connections between the concepts mentioned.
2. Use the knowledge graph relationships (CONTEXT below) to trace paths.
3. Explain WHY concepts are related, not just THAT they are.
4. Use visual metaphors (e.g., "Think of X as the foundation on which Y is built").
5. Highlight prerequisite relationships and their practical implications.

FORMAT: Use a clear narrative flow with markdown formatting.""",

        "plan": """You are an intelligent study planner. Create a structured learning plan.

RULES:
1. Analyze the student's current mastery levels (from CONTEXT).
2. Identify gaps using prerequisite chain analysis.
3. Create a step-by-step study plan respecting prerequisite order.
4. Estimate time based on difficulty and current mastery.
5. Prioritize weak areas that are prerequisites for upcoming topics.
6. Include specific study activities for each step.

FORMAT:
## 📚 Your Personalized Study Plan

### Week 1: Foundation Building
- [ ] **Topic 1** (Est. 2 hours) - Current mastery: 30%
  - Activity: Review notes from [source], complete practice problems
...""",
    }

    CONFIDENCE_THRESHOLD = 0.3  # Minimum retrieval confidence to use

    def __init__(self):
        self.retriever = GraphRAGRetriever()
        self.kg_store = KnowledgeGraphStore()
        self.conversation_history: Dict[str, List[dict]] = {}  # session_id -> messages

    def chat(
        self,
        message: str,
        user_email: str,
        mode: str = "socratic",
        session_id: str = "",
        concept_focus: str = "",
    ) -> dict:
        """
        Process a student message and generate a pedagogically-informed response.
        
        Args:
            message: Student's question or response
            user_email: Student identifier
            mode: Pedagogical mode (socratic, explain, quiz, connect, plan)
            session_id: Conversation session ID for context continuity
            concept_focus: Optional specific concept to focus on
        
        Returns:
            Response dict with answer, citations, and metadata
        """
        if not HAS_GEMINI or not _gemini:
            return self._fallback_response(message)

        # Step 1: Retrieve context via GraphRAG
        context = self.retriever.retrieve(message, user_email)

        # Step 2: Build the LLM prompt
        system_prompt = self.SYSTEM_PROMPTS.get(mode, self.SYSTEM_PROMPTS["socratic"])

        # Add conversation history for continuity
        if not session_id:
            session_id = str(uuid.uuid4())

        history = self.conversation_history.get(session_id, [])

        # Step 3: Construct the full prompt
        full_prompt = self._build_prompt(
            system_prompt=system_prompt,
            context=context,
            message=message,
            history=history,
            concept_focus=concept_focus,
            mode=mode,
        )

        # Step 4: Generate response
        try:
            response = _gemini.generate_content(full_prompt)
            answer = response.text.strip()
        except Exception as e:
            return {
                "answer": f"I'm having trouble generating a response right now. Error: {str(e)}",
                "session_id": session_id,
                "mode": mode,
                "error": True,
            }

        # Step 5: Post-process and extract citations
        citations = self._extract_citations(context)
        confidence = self._calculate_response_confidence(context)

        # Step 6: Add confidence warning if low
        if confidence < self.CONFIDENCE_THRESHOLD and context["has_graph_context"]:
            answer += "\n\n⚠️ *Note: My confidence in this answer is limited. The topic may not be fully covered in your uploaded materials. Please verify with your instructor.*"

        # Step 7: Update conversation history
        history.append({"role": "student", "content": message})
        history.append({"role": "mentor", "content": answer})
        self.conversation_history[session_id] = history[-20:]  # Keep last 20 messages

        # Step 8: Detect concepts discussed for KT tracking
        discussed_concepts = [c["name"] for c in context.get("graph_concepts", [])]

        return {
            "answer": answer,
            "session_id": session_id,
            "mode": mode,
            "citations": citations,
            "confidence": confidence,
            "discussed_concepts": discussed_concepts,
            "has_graph_context": context["has_graph_context"],
            "has_vector_context": context["has_vector_context"],
            "prerequisites": [p.get("name") for p in context.get("prerequisites", [])],
        }

    def _build_prompt(
        self,
        system_prompt: str,
        context: dict,
        message: str,
        history: List[dict],
        concept_focus: str,
        mode: str,
    ) -> str:
        """Construct the full prompt with system instructions, context, and history."""
        parts = [system_prompt]

        # Add context from GraphRAG
        parts.append(f"\n\n--- CONTEXT FROM STUDENT'S MATERIALS ---\n{context['context_text']}")

        # Add concept focus if specified
        if concept_focus:
            parts.append(f"\n\n--- FOCUS CONCEPT ---\nThe student wants to focus on: {concept_focus}")

        # Add conversation history
        if history:
            parts.append("\n\n--- CONVERSATION HISTORY ---")
            for msg in history[-6:]:  # Last 6 messages
                role = "Student" if msg["role"] == "student" else "Mentor"
                parts.append(f"{role}: {msg['content'][:300]}")

        # Add the current message
        parts.append(f"\n\n--- CURRENT STUDENT MESSAGE ---\n{message}")

        # Add mode-specific instructions
        if mode == "socratic":
            parts.append("\nRemember: Guide through questions, don't give direct answers!")
        elif mode == "quiz":
            parts.append("\nGenerate quiz questions based on the context above.")
        elif mode == "plan":
            parts.append("\nCreate a concrete, actionable study plan based on the mastery levels shown.")

        return "\n".join(parts)

    def _extract_citations(self, context: dict) -> List[dict]:
        """Extract citation information from the retrieved context."""
        citations = []

        for chunk in context.get("vector_chunks", []):
            if chunk.get("relevance", 0) > 0.3:
                citations.append({
                    "source": chunk.get("source", "Unknown"),
                    "relevance": chunk.get("relevance", 0),
                    "type": "notes",
                })

        for concept in context.get("graph_concepts", []):
            if concept.get("source_document"):
                citations.append({
                    "source": concept["source_document"],
                    "concept": concept["name"],
                    "type": "knowledge_graph",
                })

        return citations

    def _calculate_response_confidence(self, context: dict) -> float:
        """Calculate confidence score based on retrieval quality."""
        confidence = 0.0

        # Graph context boosts confidence
        if context["has_graph_context"]:
            confidence += 0.4

        # Vector context boosts confidence
        if context["has_vector_context"]:
            avg_relevance = sum(
                c.get("relevance", 0) for c in context.get("vector_chunks", [])
            ) / max(len(context.get("vector_chunks", [])), 1)
            confidence += avg_relevance * 0.4

        # Prerequisites found adds context
        if context.get("prerequisites"):
            confidence += 0.2

        return min(confidence, 1.0)

    def _fallback_response(self, message: str) -> dict:
        """Fallback when Gemini is not available."""
        return {
            "answer": "I'm currently unable to generate AI responses. Please ensure the Gemini API is configured. "
                      "In the meantime, try reviewing your uploaded notes or checking the Knowledge Graph for related concepts.",
            "session_id": str(uuid.uuid4()),
            "mode": "fallback",
            "citations": [],
            "confidence": 0,
            "error": True,
        }

    def get_study_recommendations(self, user_email: str) -> dict:
        """Generate study recommendations based on knowledge state."""
        weaknesses = self.kg_store.get_weak_concepts(user_email)
        graph = self.kg_store.get_full_graph(user_email)

        if not weaknesses:
            return {
                "recommendations": [],
                "message": "Great job! You seem to have a solid grasp of all your concepts.",
                "overall_mastery": 1.0,
            }

        # Calculate overall mastery
        all_masteries = [n.get("mastery", 0) or 0 for n in graph["nodes"]]
        overall = sum(all_masteries) / max(len(all_masteries), 1)

        # Prioritize: weak concepts that are prerequisites for other weak concepts
        priority_concepts = []
        for weakness in weaknesses[:10]:
            # Check if this concept is a prerequisite for others
            is_prerequisite = any(
                e["source"] == weakness["name"] and e["relation"] == "PREREQUISITE_OF"
                for e in graph["edges"]
            )
            priority_concepts.append({
                **weakness,
                "is_prerequisite": is_prerequisite,
                "priority": "high" if is_prerequisite else "medium",
            })

        # Sort: prerequisites first, then by mastery
        priority_concepts.sort(key=lambda x: (not x["is_prerequisite"], x["mastery"]))

        recommendations = []
        for concept in priority_concepts[:5]:
            rec = {
                "concept": concept["name"],
                "current_mastery": concept["mastery"],
                "priority": concept["priority"],
                "difficulty": concept.get("difficulty", "medium"),
                "action": self._suggest_action(concept),
            }
            recommendations.append(rec)

        return {
            "recommendations": recommendations,
            "overall_mastery": overall,
            "total_weak_concepts": len(weaknesses),
            "message": f"You have {len(weaknesses)} concepts below 50% mastery. "
                       f"Focus on the highlighted prerequisites first.",
        }

    def _suggest_action(self, concept: dict) -> str:
        mastery = concept.get("mastery", 0)
        difficulty = concept.get("difficulty", "medium")
        bloom = concept.get("bloom_level", "understand")

        if mastery < 0.2:
            return f"Start with basic review. Read your notes on '{concept['name']}' and try to define it in your own words."
        elif mastery < 0.5:
            return f"Practice applying '{concept['name']}'. Try solving 2-3 problems related to this concept."
        elif mastery < 0.8:
            return f"Deepen your understanding. Try explaining '{concept['name']}' to someone else or write a summary."
        else:
            return f"Good mastery! Review periodically to prevent forgetting."


# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

app = FastAPI(title="TrackEneer AI Mentor")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_USER_EMAIL = os.getenv("DEFAULT_USER_EMAIL", "demo@trackeneer.local")
mentor = SocraticMentor()


def _resolve_email(request: Request, provided: Optional[str] = None) -> str:
    if provided:
        return provided
    return request.headers.get("x-user-email", "") or DEFAULT_USER_EMAIL


# ─── Health ───

@app.get("/")
async def root():
    return {"service": "ai-mentor", "status": "ok"}


# ─── Chat endpoint ───

@app.post("/api/mentor/chat")
async def mentor_chat(
    request: Request,
    message: str = Form(...),
    mode: str = Form("socratic"),  # socratic, explain, quiz, connect, plan
    session_id: str = Form(""),
    concept_focus: str = Form(""),
    email: Optional[str] = Form(None),
):
    """
    Chat with the AI Mentor.
    
    Modes:
    - socratic: Guide through questions (default)
    - explain: Clear, detailed explanation
    - quiz: Generate adaptive quiz questions
    - connect: Show relationships between concepts
    - plan: Generate a study plan
    """
    user_email = _resolve_email(request, email)
    result = mentor.chat(
        message=message,
        user_email=user_email,
        mode=mode,
        session_id=session_id,
        concept_focus=concept_focus,
    )
    return {"status": "ok", **result}


# ─── Study recommendations ───

@app.get("/api/mentor/recommendations")
async def get_recommendations(request: Request, email: Optional[str] = None):
    """Get personalized study recommendations based on knowledge state."""
    user_email = _resolve_email(request, email)
    result = mentor.get_study_recommendations(user_email)
    return {"status": "ok", **result}


# ─── Conversation history ───

@app.get("/api/mentor/history/{session_id}")
async def get_conversation_history(session_id: str):
    """Retrieve conversation history for a session."""
    history = mentor.conversation_history.get(session_id, [])
    return {"status": "ok", "session_id": session_id, "messages": history}


# ─── Clear conversation ───

@app.delete("/api/mentor/history/{session_id}")
async def clear_conversation(session_id: str):
    """Clear conversation history for a session."""
    if session_id in mentor.conversation_history:
        del mentor.conversation_history[session_id]
    return {"status": "ok", "message": "Conversation cleared"}


# ─── Index notes for RAG ───

@app.post("/api/mentor/index")
async def index_notes(
    request: Request,
    text: str = Form(...),
    source: str = Form(""),
    email: Optional[str] = Form(None),
):
    """Index text content into the vector store for RAG retrieval."""
    user_email = _resolve_email(request, email)
    mentor.retriever.index_text(text, user_email, source=source)
    return {"status": "ok", "message": f"Indexed content from '{source}'"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5006)
