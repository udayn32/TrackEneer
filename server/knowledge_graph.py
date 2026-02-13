"""
Educational Knowledge Graph (EduKG) Engine
==========================================

Automated construction of structured Knowledge Graphs from unstructured
educational materials (PDFs, notes, syllabi). Implements:

1. Concept Extraction  – SentenceTransformer-based keyphrase extraction
2. Relation Extraction – Prerequisite / part-of / related-to discovery
3. Graph Storage       – Neo4j backed with full CRUD
4. Graph Traversal     – BFS / prerequisite chains / subgraph retrieval
5. LLM-Assisted Enrichment – Gemini-powered ontology completion
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

# ---------- Neo4j ----------
from db import get_driver
from graph_helpers import ensure_user_and_day, normalize_day

# ---------- NLP / Embeddings ----------
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    HAS_SBERT = True
except ImportError:
    HAS_SBERT = False

try:
    import spacy
    _nlp = spacy.load("en_core_web_sm")
    HAS_SPACY = True
except Exception:
    HAS_SPACY = False
    _nlp = None

# ---------- Gemini ----------
try:
    import google.generativeai as genai
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "AIzaSyDL1SqUudycymjYNnlm4z7ajfFkL3ht77k"
    genai.configure(api_key=GEMINI_API_KEY)
    _gemini_model = genai.GenerativeModel("gemini-2.5-flash")
    HAS_GEMINI = True
except Exception:
    HAS_GEMINI = False
    _gemini_model = None

# ---------- Transformers / MiniLM ----------
try:
    from transformers import AutoTokenizer, AutoModel
    import torch
    HAS_TRANSFORMERS = True
    _minilm_tokenizer = None
    _minilm_model = None
except ImportError:
    HAS_TRANSFORMERS = False

import time
import logging

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- PDF extraction (reuse existing) ----------
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

# ─── Embedding model (lightweight) ───
_embed_model: Optional[SentenceTransformer] = None

def _get_embed_model() -> Optional[SentenceTransformer]:
    global _embed_model
    if _embed_model is None and HAS_SBERT:
        model_path = os.getenv("EMBED_MODEL", "./all-MiniLM-L6-v2")
        try:
            _embed_model = SentenceTransformer(model_path)
        except Exception as e:
            print(f"⚠ Could not load embed model: {e}")
    return _embed_model


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class Concept:
    """A node in the Educational Knowledge Graph."""
    id: str = ""
    name: str = ""
    description: str = ""
    category: str = ""  # topic, subtopic, skill, theorem, etc.
    difficulty: str = "medium"  # easy, medium, hard
    bloom_level: str = "understand"  # remember, understand, apply, analyze, evaluate, create
    source_document: str = ""
    source_page: int = 0
    embedding: Optional[List[float]] = None

    def to_dict(self) -> dict:
        d = {
            "id": self.id or str(uuid.uuid4()),
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "difficulty": self.difficulty,
            "bloom_level": self.bloom_level,
            "source_document": self.source_document,
            "source_page": self.source_page,
        }
        return d


@dataclass
class Relation:
    """An edge in the Educational Knowledge Graph."""
    source_id: str = ""
    target_id: str = ""
    relation_type: str = "related_to"  # prerequisite_of, part_of, related_to, leads_to
    confidence: float = 0.8
    source: str = "auto"  # auto, manual, llm

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type,
            "confidence": self.confidence,
            "source": self.source,
        }


# ============================================================================
# CONCEPT EXTRACTION ENGINE
# ============================================================================

class ConceptExtractor:
    """
    Extracts educational concepts from text using a multi-strategy approach:
    1. LLM-based extraction (Gemini) – highest quality
    2. Embedding-based keyphrase extraction (SIFRank-inspired)
    3. SpaCy NER + heuristic fallback
    """

    # ── Bloom's Taxonomy keyword hints ──
    BLOOM_KEYWORDS = {
        "remember": ["define", "list", "recall", "identify", "name", "state"],
        "understand": ["describe", "explain", "summarize", "interpret", "classify"],
        "apply": ["implement", "solve", "use", "demonstrate", "calculate"],
        "analyze": ["compare", "contrast", "examine", "differentiate", "analyse"],
        "evaluate": ["assess", "evaluate", "justify", "critique", "judge"],
        "create": ["design", "construct", "develop", "formulate", "compose"],
    }

    DIFFICULTY_SIGNALS = {
        "easy": ["basic", "introduction", "fundamental", "overview", "simple"],
        "medium": ["intermediate", "standard", "typical", "common"],
        "hard": ["advanced", "complex", "optimization", "proof", "theorem"],
    }

    def __init__(self):
        self.embed = _get_embed_model()
        self._init_minilm()

    def _init_minilm(self):
        """Initialize all-MiniLM-L6-v2 model and tokenizer."""
        global _minilm_tokenizer, _minilm_model
        if HAS_TRANSFORMERS and _minilm_model is None:
            try:
                model_name = "sentence-transformers/all-MiniLM-L6-v2"
                _minilm_tokenizer = AutoTokenizer.from_pretrained(model_name)
                _minilm_model = AutoModel.from_pretrained(model_name)
                logger.info("✓ MiniLM-L6-v2 initialized successfully")
            except Exception as e:
                logger.error(f"✗ Failed to initialize MiniLM: {e}")

    # ─── Stopwords & noise filters for candidate quality ───
    _STOPWORD_PHRASES = {
        "the", "a", "an", "this", "that", "these", "those", "it", "its",
        "such", "other", "various", "following", "several", "many", "some",
        "also", "use", "using", "used", "may", "can", "will", "etc",
        "e.g", "i.e", "fig", "figure", "table", "page", "chapter",
        "section", "example", "note", "see", "given", "based",
        # Question / pronoun words (not concepts)
        "what", "which", "who", "whom", "whose", "where", "when", "why", "how",
        "he", "she", "they", "we", "you", "me", "him", "her", "them", "us",
        # Common non-concept words
        "each", "every", "all", "both", "few", "more", "most", "any", "no",
        "not", "only", "very", "just", "even", "well", "back", "still",
        "new", "old", "good", "bad", "first", "last", "next", "same",
        "time", "year", "way", "day", "part", "place", "case", "point",
        "number", "hand", "end", "set", "order", "level", "side",
        "work", "result", "form", "type", "kind", "area", "fact",
        "need", "name", "thing", "line", "term", "however", "therefore",
    }
    _JUNK_PATTERNS = re.compile(
        r"^(the |a |an |this |that |these |those |its |their |our |his |her )",
        re.IGNORECASE,
    )

    # ─── Strategy 1: MiniLM + SIF Ranking (Local, Refined) ───

    def extract_with_llm(self, text: str, source_doc: str = "") -> Tuple[List[Concept], List[Relation]]:
        """
        MiniLM-L6 + SIF-weighted extraction with chunked document processing,
        MMR diversification, fuzzy dedup, and contextual descriptions.
        """
        start_time = time.time()
        if not HAS_TRANSFORMERS or _minilm_model is None:
            logger.warning("MiniLM not available, falling back to NLP")
            return self.extract_with_nlp(text, source_doc)

        try:
            # 1. Extract & filter candidate phrases
            candidates = self._extract_candidate_phrases_refined(text)
            if not candidates:
                return self.extract_with_nlp(text, source_doc)

            # 2. Compute word frequencies for SIF weighting
            word_freq = self._compute_word_frequencies(text)

            # 3. Chunked document embedding (handles long PDFs)
            doc_embedding = self._embed_document_chunked(text, word_freq)

            # 4. Candidate embeddings with SIF weighting
            cand_embeddings = self._embed_candidates_sif(candidates, word_freq)

            # 5. PCA common-component removal (true SIF step)
            all_embeddings = np.vstack([doc_embedding.reshape(1, -1), cand_embeddings])
            all_embeddings = self._remove_principal_component(all_embeddings)
            doc_embedding = all_embeddings[0]
            cand_embeddings = all_embeddings[1:]

            # 6. Cosine similarity ranking
            similarities = self._cosine_rank(doc_embedding, cand_embeddings, candidates)

            # 7. MMR diversification (avoid redundant concepts)
            selected = self._mmr_select(
                similarities, cand_embeddings, candidates, top_k=25, lambda_param=0.6
            )

            # 8. Fuzzy deduplication
            selected = self._fuzzy_dedup(selected)

            # 9. Build sentence index for contextual descriptions
            sentence_map = self._build_sentence_index(text)

            # 10. Construct Concepts with rich metadata
            concepts = []
            sif_scores = []
            for name, score, emb_idx in selected:
                sif_scores.append(score)
                desc = self._find_context_sentence(name, sentence_map, source_doc)
                category = self._infer_category(name, score, text)
                concepts.append(Concept(
                    id=str(uuid.uuid4()),
                    name=name.title(),
                    description=desc,
                    category=category,
                    difficulty=self._infer_difficulty(name, text),
                    bloom_level=self._infer_bloom_level(text),
                    source_document=source_doc,
                ))

            # 11. Extract Relations with stricter thresholds
            sel_embeddings = np.array([cand_embeddings[idx] for _, _, idx in selected])
            relations = self._discover_relations_refined(concepts, sel_embeddings, text)

            # ── Metrics Logging ──
            duration = time.time() - start_time
            avg_sif = sum(sif_scores) / len(sif_scores) if sif_scores else 0
            min_sif = min(sif_scores) if sif_scores else 0
            max_sif = max(sif_scores) if sif_scores else 0
            logger.info("╔══ MiniLM-L6 Extraction Metrics ══╗")
            logger.info(f"║ Source        : {source_doc}")
            logger.info(f"║ Time Taken    : {duration:.3f}s")
            logger.info(f"║ Candidates    : {len(candidates)} raw → {len(selected)} selected")
            logger.info(f"║ Concepts      : {len(concepts)}")
            logger.info(f"║ Relations     : {len(relations)}")
            logger.info(f"║ SIF Scores    : avg={avg_sif:.4f}  min={min_sif:.4f}  max={max_sif:.4f}")
            logger.info(f"║ Text Length   : {len(text)} chars")
            logger.info("╚════════════════════════════════════╝")

            return concepts, relations

        except Exception as e:
            logger.error(f"⚠ MiniLM extraction failed: {e}", exc_info=True)
            return self.extract_with_nlp(text, source_doc)

    # ─── SIF Embedding Helpers ───

    def _compute_word_frequencies(self, text: str) -> Dict[str, float]:
        """Compute normalized word frequencies from document for SIF weighting."""
        words = re.findall(r'\b[a-z]+\b', text.lower())
        total = len(words) or 1
        freq: Dict[str, int] = {}
        for w in words:
            freq[w] = freq.get(w, 0) + 1
        return {w: c / total for w, c in freq.items()}

    def _sif_weight(self, word: str, word_freq: Dict[str, float], a: float = 1e-3) -> float:
        """SIF weight: a / (a + p(w)).  Rare words get weight ≈ 1, common words → 0."""
        p = word_freq.get(word.lower(), 1e-5)
        return a / (a + p)

    def _embed_document_chunked(self, text: str, word_freq: Dict[str, float],
                                 chunk_size: int = 450, overlap: int = 100) -> np.ndarray:
        """Embed the full document by chunking and averaging SIF-weighted embeddings."""
        tokens = text.split()
        chunks = []
        i = 0
        while i < len(tokens):
            chunk = " ".join(tokens[i:i + chunk_size])
            chunks.append(chunk)
            i += chunk_size - overlap
        if not chunks:
            chunks = [text[:512]]

        chunk_embeddings = []
        for chunk in chunks:
            inputs = _minilm_tokenizer(chunk, return_tensors="pt", truncation=True,
                                            max_length=512, padding=True)
            with torch.no_grad():
                outputs = _minilm_model(**inputs)
                token_embeds = outputs.last_hidden_state[0]  # (seq_len, hidden)

            # SIF-weighted average
            input_ids = inputs["input_ids"][0]
            decoded_tokens = _minilm_tokenizer.convert_ids_to_tokens(input_ids)
            weights = []
            for tok in decoded_tokens:
                clean = tok.replace("##", "").lower()
                if clean in ("[PAD]", "[CLS]", "[SEP]", ""):
                    weights.append(0.0)
                else:
                    weights.append(self._sif_weight(clean, word_freq))
            weights = np.array(weights, dtype=np.float32)
            w_sum = weights.sum() or 1.0
            weighted_emb = (token_embeds.numpy().T * weights).T.sum(axis=0) / w_sum
            chunk_embeddings.append(weighted_emb)

        return np.mean(chunk_embeddings, axis=0)

    def _embed_candidates_sif(self, candidates: List[str],
                               word_freq: Dict[str, float]) -> np.ndarray:
        """Embed each candidate phrase with SIF weighting."""
        all_embs = []
        # batch in groups of 32 for memory
        batch_size = 32
        for batch_start in range(0, len(candidates), batch_size):
            batch = candidates[batch_start:batch_start + batch_size]
            inputs = _minilm_tokenizer(batch, return_tensors="pt", truncation=True,
                                            max_length=64, padding=True)
            with torch.no_grad():
                outputs = _minilm_model(**inputs)

            for idx_in_batch in range(len(batch)):
                token_embeds = outputs.last_hidden_state[idx_in_batch]
                input_ids = inputs["input_ids"][idx_in_batch]
                decoded = _minilm_tokenizer.convert_ids_to_tokens(input_ids)
                weights = []
                for tok in decoded:
                    clean = tok.replace("##", "").lower()
                    if clean in ("[PAD]", "[CLS]", "[SEP]", ""):
                        weights.append(0.0)
                    else:
                        weights.append(self._sif_weight(clean, word_freq))
                weights = np.array(weights, dtype=np.float32)
                w_sum = weights.sum() or 1.0
                weighted = (token_embeds.numpy().T * weights).T.sum(axis=0) / w_sum
                all_embs.append(weighted)

        return np.array(all_embs)

    def _remove_principal_component(self, embeddings: np.ndarray) -> np.ndarray:
        """Remove projection on first principal component (SIF paper Eq. 2)."""
        if len(embeddings) < 2:
            return embeddings
        mean = np.mean(embeddings, axis=0)
        centered = embeddings - mean
        # SVD to get first principal component
        try:
            U, S, Vt = np.linalg.svd(centered, full_matrices=False)
            pc = Vt[0]  # first principal component
            # Remove projection
            projection = np.outer(centered @ pc, pc)
            return embeddings - projection
        except Exception:
            return embeddings

    # ─── Ranking & Selection ───

    def _cosine_rank(self, doc_emb: np.ndarray, cand_embs: np.ndarray,
                     candidates: List[str]) -> List[Tuple[str, float, int]]:
        """Rank candidates by cosine similarity to document."""
        norm_doc = np.linalg.norm(doc_emb)
        results = []
        for i, emb in enumerate(cand_embs):
            norm_c = np.linalg.norm(emb)
            if norm_doc > 0 and norm_c > 0:
                sim = float(np.dot(doc_emb, emb) / (norm_doc * norm_c))
            else:
                sim = 0.0
            results.append((candidates[i], sim, i))
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def _mmr_select(self, ranked: List[Tuple[str, float, int]],
                    cand_embs: np.ndarray, candidates: List[str],
                    top_k: int = 25, lambda_param: float = 0.6
                    ) -> List[Tuple[str, float, int]]:
        """Maximal Marginal Relevance to diversify selected concepts."""
        if len(ranked) <= top_k:
            return ranked

        selected = [ranked[0]]
        remaining = list(ranked[1:])

        while len(selected) < top_k and remaining:
            best_score = -1.0
            best_idx = 0
            for r_idx, (name, rel_score, emb_idx) in enumerate(remaining):
                # Max similarity to already-selected
                max_sim_to_selected = 0.0
                for _, _, sel_emb_idx in selected:
                    n1 = np.linalg.norm(cand_embs[emb_idx])
                    n2 = np.linalg.norm(cand_embs[sel_emb_idx])
                    if n1 > 0 and n2 > 0:
                        sim = float(np.dot(cand_embs[emb_idx], cand_embs[sel_emb_idx]) / (n1 * n2))
                        max_sim_to_selected = max(max_sim_to_selected, sim)

                mmr = lambda_param * rel_score - (1 - lambda_param) * max_sim_to_selected
                if mmr > best_score:
                    best_score = mmr
                    best_idx = r_idx

            selected.append(remaining.pop(best_idx))

        return selected

    def _fuzzy_dedup(self, items: List[Tuple[str, float, int]],
                     threshold: float = 0.85) -> List[Tuple[str, float, int]]:
        """Remove near-duplicate candidates (e.g. 'neural network' vs 'neural networks')."""
        deduped = []
        seen_lower = []
        for name, score, idx in items:
            name_lower = name.lower().strip()
            is_dup = False
            for existing in seen_lower:
                # Simple character-based similarity
                shorter = min(len(name_lower), len(existing))
                longer = max(len(name_lower), len(existing))
                if shorter == 0:
                    continue
                # Check if one is a substring of the other
                if name_lower in existing or existing in name_lower:
                    is_dup = True
                    break
                # Check edit ratio
                common = sum(1 for a, b in zip(name_lower, existing) if a == b)
                if common / longer > threshold:
                    is_dup = True
                    break
            if not is_dup:
                deduped.append((name, score, idx))
                seen_lower.append(name_lower)
        return deduped

    # ─── Context & Category Helpers ───

    def _build_sentence_index(self, text: str) -> List[str]:
        """Split text into sentences for contextual description lookup."""
        sentences = re.split(r'(?<=[.!?])\s+', text[:20000])
        return [s.strip() for s in sentences if len(s.strip()) > 10]

    def _find_context_sentence(self, concept_name: str, sentences: List[str],
                                source_doc: str) -> str:
        """Find the sentence that best describes a concept."""
        name_lower = concept_name.lower()
        for sent in sentences:
            if name_lower in sent.lower():
                # Truncate to reasonable length
                clean = sent.strip()[:200]
                if len(clean) > 20:
                    return clean
        return f"Concept extracted from {source_doc}" if source_doc else ""

    def _infer_category(self, name: str, score: float, text: str) -> str:
        """Infer concept category using contextual signals."""
        name_lower = name.lower()
        text_lower = text[:5000].lower()

        # Check for structural markers
        if re.search(rf"(?:module|unit|chapter)\s*\d*[:\-–]\s*{re.escape(name_lower)}", text_lower):
            return "topic"
        if re.search(rf"(?:theorem|lemma|corollary)\s*[:\-–]?\s*{re.escape(name_lower)}", text_lower):
            return "theorem"
        if re.search(rf"(?:algorithm|procedure)\s*[:\-–]?\s*{re.escape(name_lower)}", text_lower):
            return "algorithm"
        if re.search(rf"(?:definition|define)\s*[:\-–]?\s*{re.escape(name_lower)}", text_lower):
            return "definition"
        if re.search(rf"(?:formula|equation)\s*[:\-–]?\s*{re.escape(name_lower)}", text_lower):
            return "formula"

        # Fall back to score-based
        if score > 0.5:
            return "topic"
        elif score > 0.3:
            return "subtopic"
        else:
            return "skill"

    # ─── Refined Relation Discovery ───

    def _discover_relations_refined(self, concepts: List[Concept],
                                     embeddings: np.ndarray, text: str) -> List[Relation]:
        """Discover relations with stricter thresholds and prerequisite detection."""
        relations = []
        if len(embeddings) < 2:
            return relations

        text_lower = text[:30000].lower()

        for i in range(len(embeddings)):
            for j in range(i + 1, len(embeddings)):
                n1 = np.linalg.norm(embeddings[i])
                n2 = np.linalg.norm(embeddings[j])
                if n1 == 0 or n2 == 0:
                    continue
                sim = float(np.dot(embeddings[i], embeddings[j]) / (n1 * n2))

                if sim < 0.35:  # Lower threshold (PCA compresses cosine values)
                    continue

                # Try to determine relation type from text context
                name_i = concepts[i].name.lower()
                name_j = concepts[j].name.lower()
                rel_type = "related_to"

                # Check for prerequisite signals
                prereq_patterns = [
                    rf"{re.escape(name_i)}.*(?:requires?|prerequisite|before|prior to).*{re.escape(name_j)}",
                    rf"{re.escape(name_j)}.*(?:requires?|prerequisite|before|prior to).*{re.escape(name_i)}",
                ]
                for pattern in prereq_patterns:
                    if re.search(pattern, text_lower):
                        rel_type = "prerequisite_of"
                        break

                # Check for part-of signals
                if re.search(rf"{re.escape(name_j)}.*(?:includes?|contains?|consists? of).*{re.escape(name_i)}", text_lower):
                    rel_type = "part_of"
                elif re.search(rf"{re.escape(name_i)}.*(?:is part of|belongs to|within).*{re.escape(name_j)}", text_lower):
                    rel_type = "part_of"

                relations.append(Relation(
                    source_id=concepts[i].id,
                    target_id=concepts[j].id,
                    relation_type=rel_type,
                    confidence=round(sim, 3),
                    source="minilm_sif",
                ))

        # Document-order prerequisite chain (covers all concepts)
        for i in range(len(concepts) - 1):
            # Only add if not already related
            existing = {(r.source_id, r.target_id) for r in relations}
            if (concepts[i].id, concepts[i + 1].id) not in existing:
                relations.append(Relation(
                    source_id=concepts[i].id,
                    target_id=concepts[i + 1].id,
                    relation_type="prerequisite_of",
                    confidence=0.55,
                    source="sequence",
                ))

        return relations

    # ─── (Legacy Gemini Extraction - Removed/replaced above) ───

    # ─── Strategy 2: Embedding-based keyphrase extraction ───

    def extract_with_embeddings(self, text: str, source_doc: str = "", top_k: int = 20) -> Tuple[List[Concept], List[Relation]]:
        """SIFRank-inspired extraction using SentenceTransformer embeddings."""
        if not self.embed:
            return self.extract_with_nlp(text, source_doc)

        # Extract candidate phrases
        candidates = self._extract_candidate_phrases_refined(text)
        if not candidates:
            return self.extract_with_nlp(text, source_doc)

        # Encode document and candidates
        doc_embedding = self.embed.encode([text[:2000]])[0]
        candidate_embeddings = self.embed.encode(candidates)

        # Compute cosine similarity to document
        similarities = []
        for i, emb in enumerate(candidate_embeddings):
            sim = float(np.dot(doc_embedding, emb) / (np.linalg.norm(doc_embedding) * np.linalg.norm(emb) + 1e-8))
            similarities.append((candidates[i], sim))

        similarities.sort(key=lambda x: x[1], reverse=True)
        top_concepts_raw = similarities[:top_k]

        concepts = []
        for name, score in top_concepts_raw:
            concepts.append(Concept(
                id=str(uuid.uuid4()),
                name=name.title(),
                description=f"Concept extracted from {source_doc}" if source_doc else "",
                category="topic" if score > 0.5 else "subtopic",
                difficulty=self._infer_difficulty(name, text),
                bloom_level=self._infer_bloom_level(text),
                source_document=source_doc,
            ))

        # Discover relations via embedding similarity between concepts
        relations = self._discover_relations_by_embedding(concepts, candidate_embeddings[:top_k])

        return concepts, relations

    # ─── Strategy 3: SpaCy NER + heuristic fallback ───

    def extract_with_nlp(self, text: str, source_doc: str = "") -> Tuple[List[Concept], List[Relation]]:
        """Fallback extraction using SpaCy NER and heuristics."""
        concepts = []
        seen = set()

        # Strategy A: SpaCy NER
        if HAS_SPACY and _nlp:
            doc = _nlp(text[:50000])
            for ent in doc.ents:
                name = ent.text.strip()
                if len(name) > 2 and name.lower() not in seen:
                    seen.add(name.lower())
                    concepts.append(Concept(
                        id=str(uuid.uuid4()),
                        name=name,
                        description=f"Entity: {ent.label_}",
                        category="topic",
                        difficulty=self._infer_difficulty(name, text),
                        bloom_level=self._infer_bloom_level(text),
                        source_document=source_doc,
                    ))

            # Strategy B: Noun chunks
            for chunk in doc.noun_chunks:
                name = chunk.text.strip()
                if len(name) > 3 and name.lower() not in seen and not name[0].islower():
                    seen.add(name.lower())
                    concepts.append(Concept(
                        id=str(uuid.uuid4()),
                        name=name,
                        category="subtopic",
                        difficulty="medium",
                        source_document=source_doc,
                    ))

        # Strategy C: Regex-based header/topic extraction
        headers = re.findall(r"(?:Module|Unit|Chapter|Topic|Section)\s*[\d.:]*\s*[:\-–]?\s*(.+)", text, re.IGNORECASE)
        for h in headers:
            name = h.strip().rstrip(".")
            if len(name) > 2 and name.lower() not in seen:
                seen.add(name.lower())
                concepts.append(Concept(
                    id=str(uuid.uuid4()),
                    name=name,
                    category="topic",
                    difficulty=self._infer_difficulty(name, text),
                    source_document=source_doc,
                ))

        concepts = concepts[:30]  # Cap

        # Simple sequential prerequisite chain
        relations = []
        for i in range(len(concepts) - 1):
            relations.append(Relation(
                source_id=concepts[i].id,
                target_id=concepts[i + 1].id,
                relation_type="prerequisite_of",
                confidence=0.5,
                source="heuristic",
            ))

        return concepts, relations

    # ─── Helpers ───

    def _extract_candidate_phrases_refined(self, text: str) -> List[str]:
        """Extract high-quality candidate phrases with noise filtering."""
        candidates = []
        seen_lower = set()

        if HAS_SPACY and _nlp:
            doc = _nlp(text[:50000])

            # Pass 1: Structural headers (highest priority)
            headers = re.findall(
                r"(?:Module|Unit|Chapter|Topic|Section|Lesson)\s*[\d.:]*\s*[:\-–]?\s*(.+)",
                text, re.IGNORECASE,
            )
            for h in headers:
                name = h.strip().rstrip(".")
                if 3 < len(name) < 80 and name.lower() not in seen_lower:
                    seen_lower.add(name.lower())
                    candidates.append(name)

            # Pass 2: Named Entities (filter to relevant types)
            good_ent_labels = {"ORG", "PRODUCT", "WORK_OF_ART", "EVENT", "LAW",
                               "NORP", "FAC", "GPE", "LOC", "PERSON"}
            for ent in doc.ents:
                name = ent.text.strip()
                if (ent.label_ in good_ent_labels and
                        3 < len(name) < 60 and
                        name.lower() not in seen_lower and
                        not self._is_noise(name)):
                    seen_lower.add(name.lower())
                    candidates.append(name)

            # Pass 3: Noun chunks – filtered
            for chunk in doc.noun_chunks:
                # Remove leading determiners/articles
                phrase = self._JUNK_PATTERNS.sub("", chunk.text).strip()
                if (3 < len(phrase) < 60 and
                        phrase.lower() not in seen_lower and
                        not self._is_noise(phrase) and
                        len(phrase.split()) >= 1):
                    # Prefer multi-word or capitalized phrases
                    words = phrase.split()
                    if len(words) >= 2 or phrase[0].isupper():
                        seen_lower.add(phrase.lower())
                        candidates.append(phrase)
        else:
            # Fallback: capitalized multi-word phrases
            words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', text)
            for w in words:
                if len(w) > 5 and w.lower() not in seen_lower:
                    seen_lower.add(w.lower())
                    candidates.append(w)

        return candidates[:150]

    def _is_noise(self, phrase: str) -> bool:
        """Check if a candidate phrase is noise / non-educational."""
        phrase_lower = phrase.lower().strip()
        words = phrase_lower.split()
        word_set = set(words)
        # All words are stopwords
        if word_set.issubset(self._STOPWORD_PHRASES):
            return True
        # Single word that is a stopword or too generic
        if len(words) == 1 and phrase_lower in self._STOPWORD_PHRASES:
            return True
        # Single word that is too short (< 4 chars) or all uppercase single char
        if len(words) == 1 and len(phrase_lower) < 4:
            return True
        # Too short after cleaning
        cleaned = re.sub(r'[^a-zA-Z\s]', '', phrase).strip()
        if len(cleaned) < 3:
            return True
        # Pure numbers
        if re.match(r'^[\d\s.,%]+$', phrase):
            return True
        # Single common English word that is not a technical concept
        if len(words) == 1:
            common_words = {
                "what", "which", "who", "where", "when", "why", "how",
                "introduction", "conclusion", "overview", "summary",
                "student", "students", "teacher", "teachers",
                "answer", "question", "questions", "problem", "problems",
                "marks", "mark", "total", "semester", "exam",
                "hours", "hour", "credit", "credits",
                "reference", "references", "textbook", "textbooks",
                "objective", "objectives", "outcome", "outcomes",
            }
            if phrase_lower in common_words:
                return True
        return False

    def _extract_candidate_phrases(self, text: str) -> List[str]:
        """Extract candidate noun phrases from text (legacy, kept for Strategy 2)."""
        return self._extract_candidate_phrases_refined(text)

    def _discover_relations_by_embedding(self, concepts: List[Concept], embeddings) -> List[Relation]:
        """Discover semantic relations between concepts using embedding similarity."""
        relations = []
        if len(embeddings) < 2:
            return relations

        for i in range(len(embeddings)):
            for j in range(i + 1, len(embeddings)):
                sim = float(np.dot(embeddings[i], embeddings[j]) /
                           (np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[j]) + 1e-8))
                if sim > 0.6:
                    relations.append(Relation(
                        source_id=concepts[i].id,
                        target_id=concepts[j].id,
                        relation_type="related_to",
                        confidence=sim,
                        source="embedding",
                    ))

        # Sequential prerequisite heuristic (document order)
        for i in range(min(len(concepts) - 1, 15)):
            relations.append(Relation(
                source_id=concepts[i].id,
                target_id=concepts[i + 1].id,
                relation_type="prerequisite_of",
                confidence=0.6,
                source="sequence",
            ))

        return relations

    def _infer_difficulty(self, concept_name: str, context: str = "") -> str:
        text_lower = (concept_name + " " + context[:500]).lower()
        for diff, keywords in self.DIFFICULTY_SIGNALS.items():
            if any(kw in text_lower for kw in keywords):
                return diff
        return "medium"

    def _infer_bloom_level(self, text: str) -> str:
        text_lower = text[:1000].lower()
        for level, keywords in self.BLOOM_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                return level
        return "understand"


# ============================================================================
# KNOWLEDGE GRAPH STORE (Neo4j)
# ============================================================================

class KnowledgeGraphStore:
    """Manages CRUD operations for the EduKG in Neo4j."""

    def __init__(self):
        self.driver = get_driver()

    def store_concepts(self, concepts: List[Concept], user_email: str, day: str = None) -> int:
        """Store concepts as nodes in Neo4j."""
        day_iso = normalize_day(day)
        count = 0
        with self.driver.session() as session:
            ensure_user_and_day(session, user_email, day=day_iso)
            for c in concepts:
                c_dict = c.to_dict()
                session.run("""
                    MATCH (u:User {email: $email})
                    MERGE (concept:Concept {name: $name, userEmail: $email})
                    ON CREATE SET
                        concept.id = $id,
                        concept.description = $description,
                        concept.category = $category,
                        concept.difficulty = $difficulty,
                        concept.bloom_level = $bloom_level,
                        concept.source_document = $source_document,
                        concept.source_page = $source_page,
                        concept.createdAt = datetime()
                    ON MATCH SET
                        concept.description = CASE WHEN $description <> '' THEN $description ELSE concept.description END,
                        concept.category = $category,
                        concept.difficulty = $difficulty,
                        concept.bloom_level = $bloom_level,
                        concept.updatedAt = datetime()
                    MERGE (u)-[:HAS_CONCEPT]->(concept)
                """,
                    email=user_email,
                    id=c_dict["id"],
                    name=c_dict["name"],
                    description=c_dict["description"],
                    category=c_dict["category"],
                    difficulty=c_dict["difficulty"],
                    bloom_level=c_dict["bloom_level"],
                    source_document=c_dict["source_document"],
                    source_page=c_dict["source_page"],
                )
                count += 1
        return count

    def store_relations(self, relations: List[Relation], concepts: List[Concept], user_email: str) -> int:
        """Store relations as edges in Neo4j."""
        id_to_name = {c.id: c.name for c in concepts}
        count = 0
        with self.driver.session() as session:
            for r in relations:
                src_name = id_to_name.get(r.source_id, "")
                tgt_name = id_to_name.get(r.target_id, "")
                if not src_name or not tgt_name:
                    continue

                rel_type_safe = r.relation_type.upper().replace(" ", "_")
                session.run(f"""
                    MATCH (src:Concept {{name: $src_name, userEmail: $email}})
                    MATCH (tgt:Concept {{name: $tgt_name, userEmail: $email}})
                    MERGE (src)-[rel:{rel_type_safe}]->(tgt)
                    ON CREATE SET
                        rel.confidence = $confidence,
                        rel.source = $source,
                        rel.createdAt = datetime()
                """,
                    src_name=src_name,
                    tgt_name=tgt_name,
                    email=user_email,
                    confidence=r.confidence,
                    source=r.source,
                )
                count += 1
        return count

    def get_full_graph(self, user_email: str) -> dict:
        """Retrieve the complete EduKG for a user."""
        with self.driver.session() as session:
            # Nodes
            nodes_result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
                RETURN c
                ORDER BY c.createdAt DESC
            """, email=user_email)
            nodes = []
            for record in nodes_result:
                c = record["c"]
                nodes.append({
                    "id": c.get("id", ""),
                    "name": c.get("name", ""),
                    "description": c.get("description", ""),
                    "category": c.get("category", ""),
                    "difficulty": c.get("difficulty", ""),
                    "bloom_level": c.get("bloom_level", ""),
                    "mastery": c.get("mastery", 0.0),
                    "source_document": c.get("source_document", ""),
                })

            # Edges
            edges_result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(src:Concept)-[r]->(tgt:Concept)<-[:HAS_CONCEPT]-(u)
                WHERE type(r) IN ['PREREQUISITE_OF', 'PART_OF', 'RELATED_TO', 'LEADS_TO']
                RETURN src.name AS source, tgt.name AS target, type(r) AS relation, r.confidence AS confidence
            """, email=user_email)
            edges = []
            for record in edges_result:
                edges.append({
                    "source": record["source"],
                    "target": record["target"],
                    "relation": record["relation"],
                    "confidence": record.get("confidence", 0.8),
                })

            return {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}

    def get_prerequisites(self, concept_name: str, user_email: str, depth: int = 5) -> List[dict]:
        """Traverse prerequisite chain backwards for a concept."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH path = (prereq:Concept)-[:PREREQUISITE_OF*1..]->(target:Concept {name: $name, userEmail: $email})
                WHERE prereq.userEmail = $email
                UNWIND nodes(path) AS n
                WITH DISTINCT n
                RETURN n.name AS name, n.difficulty AS difficulty, n.mastery AS mastery, n.bloom_level AS bloom_level
            """, name=concept_name, email=user_email)
            return [dict(record) for record in result]

    def get_subgraph(self, concept_name: str, user_email: str, hops: int = 2) -> dict:
        """Retrieve a local subgraph around a concept for RAG context assembly."""
        with self.driver.session() as session:
            result = session.run(f"""
                MATCH path = (center:Concept {{name: $name, userEmail: $email}})-[*1..{hops}]-(neighbor:Concept)
                WHERE neighbor.userEmail = $email
                WITH nodes(path) AS ns, relationships(path) AS rs
                UNWIND ns AS n
                WITH DISTINCT n, rs
                RETURN collect(DISTINCT {{
                    name: n.name,
                    description: n.description,
                    category: n.category,
                    difficulty: n.difficulty,
                    mastery: n.mastery,
                    bloom_level: n.bloom_level
                }}) AS nodes,
                [r IN rs | {{
                    source: startNode(r).name,
                    target: endNode(r).name,
                    type: type(r)
                }}] AS edges
            """, name=concept_name, email=user_email)

            record = result.single()
            if record:
                return {"nodes": record["nodes"], "edges": record["edges"]}
            return {"nodes": [], "edges": []}

    def update_mastery(self, concept_name: str, user_email: str, mastery: float) -> bool:
        """Update the mastery score for a concept."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (c:Concept {name: $name, userEmail: $email})
                SET c.mastery = $mastery, c.lastAssessed = datetime()
                RETURN c.name AS name
            """, name=concept_name, email=user_email, mastery=mastery)
            return result.single() is not None

    def get_weak_concepts(self, user_email: str, threshold: float = 0.5) -> List[dict]:
        """Get concepts with mastery below threshold."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
                WHERE coalesce(c.mastery, 0) < $threshold
                RETURN c.name AS name, c.difficulty AS difficulty,
                       coalesce(c.mastery, 0) AS mastery, c.bloom_level AS bloom_level,
                       c.category AS category
                ORDER BY c.mastery ASC
            """, email=user_email, threshold=threshold)
            return [dict(r) for r in result]

    def root_cause_analysis(self, concept_name: str, user_email: str) -> dict:
        """
        When a student struggles with a concept, trace back through prerequisites
        to find the root cause (lowest mastery prerequisite).
        """
        prerequisites = self.get_prerequisites(concept_name, user_email)
        if not prerequisites:
            return {"root_cause": concept_name, "chain": [], "message": "No prerequisites found."}

        # Find the weakest prerequisite
        weakest = min(prerequisites, key=lambda p: p.get("mastery") or 0)
        chain = [p["name"] for p in prerequisites]

        return {
            "target_concept": concept_name,
            "root_cause": weakest["name"],
            "root_cause_mastery": weakest.get("mastery", 0),
            "prerequisite_chain": chain,
            "message": f"You are struggling with '{concept_name}' because your mastery of "
                       f"the prerequisite '{weakest['name']}' is only "
                       f"{int((weakest.get('mastery') or 0) * 100)}%. "
                       f"We recommend reviewing '{weakest['name']}' first.",
        }

    def get_source_documents(self, user_email: str) -> list:
        """Get distinct source documents for a user's concepts."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
                WHERE c.source_document IS NOT NULL AND c.source_document <> ''
                RETURN DISTINCT c.source_document AS document, count(c) AS concept_count
                ORDER BY document
            """, email=user_email)
            return [{"document": r["document"], "concept_count": r["concept_count"]} for r in result]

    def get_graph_by_document(self, user_email: str, source_document: str) -> dict:
        """Retrieve the EduKG filtered to a specific source document."""
        with self.driver.session() as session:
            nodes_result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
                WHERE c.source_document = $doc
                RETURN c
                ORDER BY c.createdAt DESC
            """, email=user_email, doc=source_document)
            nodes = []
            node_names = set()
            for record in nodes_result:
                c = record["c"]
                name = c.get("name", "")
                node_names.add(name)
                nodes.append({
                    "id": c.get("id", ""),
                    "name": name,
                    "description": c.get("description", ""),
                    "category": c.get("category", ""),
                    "difficulty": c.get("difficulty", ""),
                    "bloom_level": c.get("bloom_level", ""),
                    "mastery": c.get("mastery", 0.0),
                    "source_document": c.get("source_document", ""),
                })

            # Only edges where both endpoints belong to this document
            edges_result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(src:Concept)-[r]->(tgt:Concept)<-[:HAS_CONCEPT]-(u)
                WHERE src.source_document = $doc AND tgt.source_document = $doc
                  AND type(r) IN ['PREREQUISITE_OF', 'PART_OF', 'RELATED_TO', 'LEADS_TO']
                RETURN src.name AS source, tgt.name AS target, type(r) AS relation, r.confidence AS confidence
            """, email=user_email, doc=source_document)
            edges = []
            for record in edges_result:
                edges.append({
                    "source": record["source"],
                    "target": record["target"],
                    "relation": record["relation"],
                    "confidence": record.get("confidence", 0.8),
                })

            return {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}

    def delete_graph(self, user_email: str) -> int:
        """Delete all concepts and relations for a user."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
                DETACH DELETE c
                RETURN count(c) AS deleted
            """, email=user_email)
            record = result.single()
            return record["deleted"] if record else 0


# ============================================================================
# GRAPH CONSTRUCTION PIPELINE
# ============================================================================

class EduKGPipeline:
    """
    End-to-end pipeline: Document → Concepts → Relations → Neo4j Graph
    """

    def __init__(self):
        self.extractor = ConceptExtractor()
        self.store = KnowledgeGraphStore()

    def process_text(self, text: str, user_email: str, source_doc: str = "", strategy: str = "llm") -> dict:
        """Process raw text into a Knowledge Graph."""
        if strategy == "llm":
            concepts, relations = self.extractor.extract_with_llm(text, source_doc)
        elif strategy == "embedding":
            concepts, relations = self.extractor.extract_with_embeddings(text, source_doc)
        else:
            concepts, relations = self.extractor.extract_with_nlp(text, source_doc)

        # Store in Neo4j
        concept_count = self.store.store_concepts(concepts, user_email)
        relation_count = self.store.store_relations(relations, concepts, user_email)

        return {
            "concepts_extracted": concept_count,
            "relations_extracted": relation_count,
            "concepts": [c.to_dict() for c in concepts],
            "relations": [r.to_dict() for r in relations],
            "strategy_used": strategy,
        }

    def process_pdf(self, file_path: str, user_email: str, strategy: str = "llm", original_filename: str = "") -> dict:
        """Extract text from PDF and build Knowledge Graph."""
        text = ""
        if HAS_PDFPLUMBER:
            try:
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
            except Exception as e:
                print(f"⚠ pdfplumber extraction failed: {e}")

        if not text:
            # Only attempt text-read if it's likely a text file (not .pdf)
            if not file_path.lower().endswith(".pdf"):
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read()
                except Exception:
                    return {"error": "Could not extract text from file"}
            else:
                return {"error": "pdfplumber not available to extract text from PDF"}

        source_name = original_filename or Path(file_path).name
        return self.process_text(text, user_email, source_doc=source_name, strategy=strategy)

    def enrich_with_llm(self, user_email: str) -> dict:
        """
        Use LLM to enrich the existing graph:
        - Fill missing descriptions
        - Suggest additional prerequisite relationships
        - Add difficulty/bloom level estimates
        """
        if not HAS_GEMINI or not _gemini_model:
            return {"error": "Gemini not available"}

        graph = self.store.get_full_graph(user_email)
        concept_names = [n["name"] for n in graph["nodes"]]

        if not concept_names:
            return {"error": "No concepts in graph to enrich"}

        prompt = f"""You are an educational expert. Given these concepts from a student's course:
{json.dumps(concept_names[:50])}

For each concept, suggest:
1. A brief description (if missing)
2. Any prerequisite relationships between these concepts
3. Difficulty level (easy/medium/hard)

Return JSON:
{{
  "enrichments": [
    {{"name": "...", "description": "...", "difficulty": "...", "prerequisites": ["concept_name_1"]}}
  ]
}}
"""
        try:
            response = _gemini_model.generate_content(prompt)
            raw = response.text.strip()
            raw = re.sub(r"```json\s*", "", raw)
            raw = re.sub(r"```\s*$", "", raw)
            data = json.loads(raw)

            updates = 0
            with self.driver.session() as session:
                for e in data.get("enrichments", []):
                    name = e.get("name", "")
                    if not name:
                        continue
                    # Update description and difficulty
                    session.run("""
                        MATCH (c:Concept {name: $name, userEmail: $email})
                        SET c.description = CASE WHEN c.description = '' OR c.description IS NULL
                                            THEN $description ELSE c.description END,
                            c.difficulty = $difficulty,
                            c.enrichedAt = datetime()
                    """, name=name, email=user_email,
                        description=e.get("description", ""),
                        difficulty=e.get("difficulty", "medium"),
                    )

                    # Add prerequisite relations
                    for prereq_name in e.get("prerequisites", []):
                        session.run("""
                            MATCH (prereq:Concept {name: $prereq, userEmail: $email})
                            MATCH (target:Concept {name: $target, userEmail: $email})
                            MERGE (prereq)-[:PREREQUISITE_OF {source: 'llm_enrichment', confidence: 0.75}]->(target)
                        """, prereq=prereq_name, target=name, email=user_email)

                    updates += 1

            return {"enriched_concepts": updates}

        except Exception as e:
            return {"error": str(e)}


# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

app = FastAPI(title="TrackEneer Knowledge Graph API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_USER_EMAIL = os.getenv("DEFAULT_USER_EMAIL", "demo@trackeneer.local")
pipeline = EduKGPipeline()


def _resolve_email(request: Request, provided: Optional[str] = None) -> str:
    if provided:
        return provided
    email = request.headers.get("x-user-email", "")
    return email or DEFAULT_USER_EMAIL


# ─── Health ───

@app.get("/")
async def root():
    return {"service": "knowledge-graph", "status": "ok"}


# ─── Build KG from text ───

@app.post("/api/knowledge-graph/build")
async def build_kg_from_text(
    request: Request,
    text: str = Form(...),
    source_document: str = Form(""),
    strategy: str = Form("llm"),  # llm, embedding, nlp
    email: Optional[str] = Form(None),
):
    """Build a Knowledge Graph from raw text input."""
    user_email = _resolve_email(request, email)
    result = pipeline.process_text(text, user_email, source_doc=source_document, strategy=strategy)
    return {"status": "ok", **result}


# ─── Build KG from uploaded file ───

@app.post("/api/knowledge-graph/upload")
async def build_kg_from_file(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    strategy: str = Form("llm"),
    email: Optional[str] = Form(None),
):
    """Upload a PDF/text file and build a Knowledge Graph from it."""
    user_email = _resolve_email(request, email)

    # Save file
    upload_dir = Path("uploads/kg")
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{uuid.uuid4()}_{file.filename}"

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # Process in background
    original_name = file.filename
    def _process():
        try:
            r = pipeline.process_pdf(str(file_path), user_email, strategy=strategy, original_filename=original_name)
            print(f"✓ KG built from {file.filename}: {r.get('concepts_extracted', 0)} concepts, {r.get('relations_extracted', 0)} relations")
        except Exception as e:
            print(f"✗ KG build failed for {file.filename}: {e}")

    background_tasks.add_task(_process)

    return {
        "status": "processing",
        "message": f"Building Knowledge Graph from '{file.filename}' in background",
        "file": file.filename,
    }


# ─── Get full graph ───

@app.get("/api/knowledge-graph/documents")
async def get_source_documents(request: Request, email: Optional[str] = None):
    """Get list of distinct source documents for a user."""
    user_email = _resolve_email(request, email)
    docs = pipeline.store.get_source_documents(user_email)
    return {"status": "ok", "documents": docs}


@app.get("/api/knowledge-graph")
async def get_knowledge_graph(request: Request, email: Optional[str] = None, source_document: Optional[str] = None):
    """Retrieve the Knowledge Graph for a user, optionally filtered by source document."""
    user_email = _resolve_email(request, email)
    if source_document:
        graph = pipeline.store.get_graph_by_document(user_email, source_document)
    else:
        graph = pipeline.store.get_full_graph(user_email)
    return {"status": "ok", **graph}


# ─── Get prerequisites ───

@app.get("/api/knowledge-graph/prerequisites/{concept_name}")
async def get_prerequisites(concept_name: str, request: Request, email: Optional[str] = None):
    """Get the prerequisite chain for a concept."""
    user_email = _resolve_email(request, email)
    prereqs = pipeline.store.get_prerequisites(concept_name, user_email)
    return {"status": "ok", "concept": concept_name, "prerequisites": prereqs}


# ─── Get subgraph ───

@app.get("/api/knowledge-graph/subgraph/{concept_name}")
async def get_subgraph(concept_name: str, request: Request, hops: int = 2, email: Optional[str] = None):
    """Get a local subgraph around a concept (for RAG context)."""
    user_email = _resolve_email(request, email)
    subgraph = pipeline.store.get_subgraph(concept_name, user_email, hops=hops)
    return {"status": "ok", "center": concept_name, **subgraph}


# ─── Root cause analysis ───

@app.get("/api/knowledge-graph/root-cause/{concept_name}")
async def root_cause_analysis(concept_name: str, request: Request, email: Optional[str] = None):
    """Perform root cause analysis for a struggling concept."""
    user_email = _resolve_email(request, email)
    result = pipeline.store.root_cause_analysis(concept_name, user_email)
    return {"status": "ok", **result}


# ─── Get weak concepts ───

@app.get("/api/knowledge-graph/weaknesses")
async def get_weaknesses(request: Request, threshold: float = 0.5, email: Optional[str] = None):
    """Get all concepts below mastery threshold."""
    user_email = _resolve_email(request, email)
    weaknesses = pipeline.store.get_weak_concepts(user_email, threshold)
    return {"status": "ok", "weaknesses": weaknesses, "count": len(weaknesses)}


# ─── Update mastery ───

@app.post("/api/knowledge-graph/mastery")
async def update_mastery(
    request: Request,
    concept_name: str = Form(...),
    mastery: float = Form(...),
    email: Optional[str] = Form(None),
):
    """Update mastery score for a concept (0.0 - 1.0)."""
    user_email = _resolve_email(request, email)
    if not 0 <= mastery <= 1:
        raise HTTPException(status_code=400, detail="Mastery must be between 0 and 1")
    success = pipeline.store.update_mastery(concept_name, user_email, mastery)
    if not success:
        raise HTTPException(status_code=404, detail="Concept not found")
    return {"status": "ok", "concept": concept_name, "mastery": mastery}


# ─── Enrich graph with LLM ───

@app.post("/api/knowledge-graph/enrich")
async def enrich_graph(request: Request, email: Optional[str] = Form(None)):
    """Use LLM to enrich existing graph with descriptions and relationships."""
    user_email = _resolve_email(request, email)
    result = pipeline.enrich_with_llm(user_email)
    return {"status": "ok", **result}


# ─── Delete graph ───

@app.delete("/api/knowledge-graph")
async def delete_knowledge_graph(request: Request, email: Optional[str] = None):
    """Delete the entire Knowledge Graph for a user."""
    user_email = _resolve_email(request, email)
    deleted = pipeline.store.delete_graph(user_email)
    return {"status": "ok", "deleted_concepts": deleted}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5005)
