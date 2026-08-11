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

import sys, io as _io
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

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
import numpy as np          # always needed (scoring, embeddings, etc.)

try:
    from sentence_transformers import SentenceTransformer
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
    from ai_client import build_text_model

    _gemini_model = build_text_model()
    if not _gemini_model:
        raise ValueError("No AI model configured")
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

try:
    import fitz  # PyMuPDF — better for scanned/complex PDFs
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

# ─── Embedding model (lightweight) ───
_embed_model: Optional[SentenceTransformer] = None

def _get_embed_model() -> Optional[SentenceTransformer]:
    global _embed_model
    if _embed_model is None and HAS_SBERT:
        model_path = os.getenv("EMBED_MODEL", "./all-MiniLM-L6-v2")
        try:
            _embed_model = SentenceTransformer(model_path)
        except Exception as e:
            print(f"[WARN] Could not load embed model: {e}")
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
    layer: int = 2           # IEEE EduKG layer: 0=Domain, 1=Topic, 2=Sub-topic, 3=Concept
    weight: float = 0.0      # Paper §4.5 w_SBERT: harmonic mean of contextual-score × cosine-similarity
    wikipedia_url: str = ""  # Wikipedia page URL if linked via expansion (Paper §4.4)
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
            "layer": self.layer,
            "weight": round(self.weight, 4),
            "wikipedia_url": self.wikipedia_url,
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
                model_path = os.getenv("EMBED_MODEL", "./all-MiniLM-L6-v2")
                # Prefer local model; fall back to HuggingFace Hub
                if os.path.isdir(model_path):
                    model_name = model_path
                else:
                    model_name = "sentence-transformers/all-MiniLM-L6-v2"
                _minilm_tokenizer = AutoTokenizer.from_pretrained(model_name)
                _minilm_model = AutoModel.from_pretrained(model_name)
                logger.info("✓ MiniLM-L6-v2 initialized successfully from %s", model_name)
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

    # ─── Gemini-Assisted Candidate Generation ───

    def _generate_candidates_with_gemini(self, text: str, source_doc: str = "") -> List[str]:
        """
        Use Gemini Flash to identify key educational concepts from text.
        Returns a list of clean concept-name strings.
        The LLM only proposes *names*; scoring, ranking, layer assignment,
        and relation discovery still go through the MiniLM + SIF pipeline.
        """
        if not HAS_GEMINI or not _gemini_model:
            return []

        # Truncate to ~6000 chars to stay well within token limits
        excerpt = text[:6000]
        prompt = (
            "You are an expert educational-content analyst.\n"
            "Extract ALL key academic / technical concepts from the text below.\n\n"
            "Rules:\n"
            "- Return ONLY a JSON array of strings, e.g. [\"Machine Learning\", \"Neural Network\"]\n"
            "- Each string must be a SHORT concept name (1-4 words max).\n"
            "- Include: main topics, sub-topics, specific methods, algorithms,\n"
            "  technologies, named theories, types/categories mentioned,\n"
            "  and real-world applications/domains.\n"
            "- Extract EVERY concept mentioned, even if only once.\n"
            "- Use standard names: \"Artificial Intelligence\" not \"AI systems\".\n"
            "- Do NOT include generic phrases like \"various types\" or \"key areas\".\n"
            "- Do NOT include sentence fragments, descriptions, or headings.\n"
            "- Do NOT include the document title as a concept.\n"
            "- Aim for 20-50 concepts depending on document length.\n\n"
            f"--- TEXT ---\n{excerpt}\n--- END ---\n\n"
            "JSON array:"
        )

        try:
            response = _gemini_model.generate_content(prompt)
            raw = response.text.strip()
            # Strip markdown fences if present
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"```\s*$", "", raw)
            # Fix common LLM JSON issues: trailing commas, comments
            raw = re.sub(r',\s*(\])', r'\1', raw)   # trailing comma before ]
            raw = re.sub(r'//[^\n]*', '', raw)         # C-style line comments
            names = json.loads(raw)
            if isinstance(names, list):
                cleaned = []
                for n in names:
                    if isinstance(n, str):
                        n = n.strip()
                        if 2 < len(n) <= 80:
                            cleaned.append(n)
                logger.info(f"Gemini proposed {len(cleaned)} candidate concepts")
                return cleaned
        except Exception as e:
            logger.warning(f"Gemini candidate generation failed: {e}")
        return []

    # ─── Strategy 1: MiniLM + SIF Ranking (Local, Refined) ───

    def extract_with_llm(self, text: str, source_doc: str = "") -> Tuple[List[Concept], List[Relation]]:
        """
        Hybrid extraction pipeline (LightRAG / GraphRAG style):

        PATH A – Gemini available:
          1. Gemini Flash extracts concept names  (high quality)
          2. MiniLM computes SIF weights for each  (Paper §4.5)
          3. All Gemini concepts are kept — no cosine drop / MMR pruning
          4. Relation discovery via embedding similarity

        PATH B – Gemini unavailable (offline fallback):
          1. Local NLP (spaCy + regex) generates candidates
          2. MiniLM SIF scoring → cosine rank → MMR diversification
          3. Fuzzy dedup → concepts + relations
        """
        start_time = time.time()
        if not HAS_TRANSFORMERS or _minilm_model is None:
            logger.warning("MiniLM not available, falling back to NLP")
            return self.extract_with_nlp(text, source_doc)

        try:
            # ── Path A: Gemini-assisted (preferred) ──
            gemini_candidates = self._generate_candidates_with_gemini(text, source_doc)

            if gemini_candidates:
                # Supplement with clean NLP candidates as safety net
                nlp_candidates = self._extract_candidate_phrases_refined(text)
                seen_lower = {c.lower().strip() for c in gemini_candidates}
                extras = []
                for nc in nlp_candidates:
                    key = nc.lower().strip()
                    if key not in seen_lower and not self._is_noise(nc):
                        words = nc.split()
                        # Only add multi-word Title-Case NLP candidates (high confidence)
                        if len(words) >= 2 and all(w[0].isupper() for w in words if w):
                            seen_lower.add(key)
                            extras.append(nc)
                if extras:
                    logger.info(f"NLP supplement: +{len(extras)} clean candidates")
                merged = gemini_candidates + extras
                return self._build_concepts_from_trusted_candidates(
                    merged, text, source_doc, start_time, path="Gemini+NLP"
                )

            # ── Path B: Offline fallback (local NLP + cosine rank + MMR) ──
            logger.info("Gemini unavailable — using local NLP pipeline")
            nlp_candidates = self._extract_candidate_phrases_refined(text)
            if not nlp_candidates:
                return self.extract_with_nlp(text, source_doc)

            return self._build_concepts_with_ranking(
                nlp_candidates, text, source_doc, start_time
            )

        except Exception as e:
            logger.error(f"⚠ MiniLM extraction failed: {e}", exc_info=True)
            return self.extract_with_nlp(text, source_doc)

    # ── Path A helper: trust the LLM candidates, just compute SIF weights ──

    def _build_concepts_from_trusted_candidates(
        self, candidates: List[str], text: str, source_doc: str,
        start_time: float, path: str = "Gemini"
    ) -> Tuple[List[Concept], List[Relation]]:
        """Build concepts from a trusted candidate list (Gemini).
        SIF weights are computed for Paper §4.5 compliance but candidates
        are NOT re-ranked or dropped — the LLM already curated them."""

        word_freq = self._compute_word_frequencies(text)
        doc_embedding = self._embed_document_chunked(text, word_freq)
        cand_embeddings = self._embed_candidates_sif(candidates, word_freq)

        # PCA common-component removal (true SIF)
        all_embs = np.vstack([doc_embedding.reshape(1, -1), cand_embeddings])
        all_embs = self._remove_principal_component(all_embs)
        doc_embedding = all_embs[0]
        cand_embeddings = all_embs[1:]

        # Compute SIF weight per candidate (Paper §4.5 harmonic mean)
        scored: List[Tuple[str, float, int]] = []
        norm_doc = np.linalg.norm(doc_embedding)
        text_lower = text.lower()
        total_len = len(text_lower) or 1
        for i, name in enumerate(candidates):
            norm_c = np.linalg.norm(cand_embeddings[i])
            cos_sim = float(np.dot(doc_embedding, cand_embeddings[i]) / (norm_doc * norm_c + 1e-8))
            cos_sim = max(0.0, cos_sim)
            # Frequency-based contextual score
            hits = text_lower.count(name.lower())
            freq_s = min(1.0, (hits * len(name)) / total_len * 30)
            ctx = max(0.05, min(1.0, freq_s + 0.10))
            # Harmonic mean (Paper Eq. 1)
            denom = ctx + cos_sim
            weight = (2.0 * ctx * cos_sim / denom) if denom > 0 else 0.0
            scored.append((name, weight, i))

        # Light dedup (only exact substring, no aggressive MMR)
        scored = self._fuzzy_dedup(scored)

        # Filter out single generic words that aren't domain-specific concepts
        _GENERIC_SINGLES = {
            'types', 'concept', 'related', 'ensuring', 'learning', 'applications',
            'techniques', 'challenges', 'strategies', 'advantages', 'formula',
            'control', 'protects', 'mitigates', 'domain', 'standards', 'depth',
            'images', 'token', 'artificial', 'super', 'narrow', 'features',
            'methods', 'approach', 'process', 'system', 'model', 'data',
            'result', 'based', 'used', 'using', 'level', 'example', 'speech',
        }
        # Also filter obvious duplicated-word artifacts like "AI AI"
        scored = [(n, s, i) for n, s, i in scored
                  if (len(n.split()) > 1 or n.lower().strip() not in _GENERIC_SINGLES)
                  and not re.match(r'^(\w+)\s+\1$', n, re.IGNORECASE)]

        # Build Concept objects
        sentence_map = self._build_sentence_index(text)
        concepts = []
        sif_scores = []
        total_chars = len(text) or 1
        for name, score, emb_idx in scored:
            sif_scores.append(score)
            desc = self._find_context_sentence(name, sentence_map, source_doc)
            category = self._infer_category(name, score, text)
            pos = text_lower.find(name.lower())
            position_ratio = pos / total_chars if pos >= 0 else 0.5
            layer = self._infer_layer(name, score, text, position_ratio)
            bloom = self._infer_bloom_for_concept(name, desc)
            display_name = name.strip()
            if display_name.islower():
                display_name = display_name.title()
            concepts.append(Concept(
                id=str(uuid.uuid4()), name=display_name, description=desc,
                category=category, difficulty=self._infer_difficulty(name, text),
                bloom_level=bloom, source_document=source_doc,
                layer=layer, weight=score,
            ))

        # Relations from embedding similarity
        sel_embs = np.array([cand_embeddings[idx] for _, _, idx in scored])
        relations = self._discover_relations_refined(concepts, sel_embs, text)

        # Logging
        duration = time.time() - start_time
        avg_sif = sum(sif_scores) / len(sif_scores) if sif_scores else 0
        min_sif = min(sif_scores) if sif_scores else 0
        max_sif = max(sif_scores) if sif_scores else 0
        logger.info(f"╔══ {path} + SIF Extraction Metrics ══╗")
        logger.info(f"║ Source        : {source_doc}")
        logger.info(f"║ Time Taken    : {duration:.3f}s")
        logger.info(f"║ Candidates    : {len(candidates)} {path} → {len(scored)} after dedup")
        logger.info(f"║ Concepts      : {len(concepts)}")
        logger.info(f"║ Relations     : {len(relations)}")
        logger.info(f"║ SIF Scores    : avg={avg_sif:.4f}  min={min_sif:.4f}  max={max_sif:.4f}")
        logger.info(f"║ Text Length   : {len(text)} chars")
        logger.info(f"╚{'═' * 38}╝")
        return concepts, relations

    # ── Path B helper: full local ranking pipeline (no Gemini) ──

    def _build_concepts_with_ranking(
        self, candidates: List[str], text: str, source_doc: str,
        start_time: float,
    ) -> Tuple[List[Concept], List[Relation]]:
        """Full local pipeline: SIF → cosine rank → MMR → dedup → concepts."""

        word_freq = self._compute_word_frequencies(text)
        doc_embedding = self._embed_document_chunked(text, word_freq)
        cand_embeddings = self._embed_candidates_sif(candidates, word_freq)

        all_embs = np.vstack([doc_embedding.reshape(1, -1), cand_embeddings])
        all_embs = self._remove_principal_component(all_embs)
        doc_embedding = all_embs[0]
        cand_embeddings = all_embs[1:]

        similarities = self._cosine_rank(doc_embedding, cand_embeddings, candidates, text=text)
        selected = self._mmr_select(similarities, cand_embeddings, candidates, top_k=30, lambda_param=0.6)
        selected = self._fuzzy_dedup(selected)
        selected = [(n, s, i) for n, s, i in selected if s >= 0.15]

        sentence_map = self._build_sentence_index(text)
        concepts = []
        sif_scores = []
        total_chars = len(text) or 1
        for name, score, emb_idx in selected:
            sif_scores.append(score)
            desc = self._find_context_sentence(name, sentence_map, source_doc)
            category = self._infer_category(name, score, text)
            pos = text.lower().find(name.lower())
            position_ratio = pos / total_chars if pos >= 0 else 0.5
            layer = self._infer_layer(name, score, text, position_ratio)
            bloom = self._infer_bloom_for_concept(name, desc)
            display_name = name.strip()
            if display_name.islower():
                display_name = display_name.title()
            concepts.append(Concept(
                id=str(uuid.uuid4()), name=display_name, description=desc,
                category=category, difficulty=self._infer_difficulty(name, text),
                bloom_level=bloom, source_document=source_doc,
                layer=layer, weight=score,
            ))

        sel_embs = np.array([cand_embeddings[idx] for _, _, idx in selected])
        relations = self._discover_relations_refined(concepts, sel_embs, text)

        duration = time.time() - start_time
        avg_sif = sum(sif_scores) / len(sif_scores) if sif_scores else 0
        min_sif = min(sif_scores) if sif_scores else 0
        max_sif = max(sif_scores) if sif_scores else 0
        logger.info("╔══ MiniLM-L6 Local Extraction Metrics ══╗")
        logger.info(f"║ Source        : {source_doc}")
        logger.info(f"║ Time Taken    : {duration:.3f}s")
        logger.info(f"║ Candidates    : {len(candidates)} NLP → {len(selected)} selected")
        logger.info(f"║ Concepts      : {len(concepts)}")
        logger.info(f"║ Relations     : {len(relations)}")
        logger.info(f"║ SIF Scores    : avg={avg_sif:.4f}  min={min_sif:.4f}  max={max_sif:.4f}")
        logger.info(f"║ Text Length   : {len(text)} chars")
        logger.info("╚════════════════════════════════════════╝")
        return concepts, relations

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
                     candidates: List[str], text: str = "") -> List[Tuple[str, float, int]]:
        """Rank candidates by cosine similarity + frequency boost (Coreness)."""
        norm_doc = np.linalg.norm(doc_emb)
        results = []

        # Precompute frequencies for boost
        text_lower = text.lower() if text else ""
        total_len = len(text_lower) or 1
        freq_scores = {}
        if text:
            for c in candidates:
                count = text_lower.count(c.lower())
                freq_scores[c] = min(count / (total_len / 5000), 1.0)  # Normalize, cap at 1.0

        # Precompute header boost (Standard + Implicit)
        header_terms = set()
        if text:
            # 1. Explicit headers (Module X, Chapter Y)
            headers = re.findall(r"(?:Module|Unit|Chapter|Topic|Section)\s*[\d.:]*\s*(.+)", text, re.IGNORECASE)
            for h in headers:
                header_terms.add(h.strip().lower())
            
            # 2. Implicit headers (Short standalone lines, Title Cased or Uppercase)
            # Looks for lines < 80 chars that are distinctly headings
            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                if 5 < len(line) < 80 and (line.isupper() or line.istitle()):
                    # Avoid sentences ending in period
                    if not line.endswith('.'):
                        header_terms.add(line.lower())

        for i, emb in enumerate(cand_embs):
            norm_cand = np.linalg.norm(emb)
            if norm_doc == 0 or norm_cand == 0:
                sim = 0.0
            else:
                sim = float(np.dot(doc_emb, emb) / (norm_doc * norm_cand))
            
            # Use 'Coreness' boost:
            # 1. Frequency: Frequent terms are more likely core (+0.1 max)
            # 2. Structure: Terms in headers get a huge boost (+0.15)
            # 3. Position: Terms appearing early often introduce the topic (implicit in SIF via weighting)
            
            phrase = candidates[i]

            # ── Paper §4.5: Harmonic Mean Weighting (w_SBERT analogue) ──────────
            # Frequency score (0.0–1.0): approximates DBpedia contextual score
            freq_s = freq_scores.get(phrase, 0.0) if text else 0.0

            # Structural presence bonus (header location → stronger educational signal)
            struct_bonus = 0.0
            if phrase.lower() in header_terms:
                struct_bonus = 0.30
            elif any(h in phrase.lower() for h in header_terms):
                struct_bonus = 0.10

            # Contextual score ≈ Paper Eq.1 DBpedia Spotlight contextual score
            # Clamp to [0.05, 1.0]: min 0.05 avoids fully suppressing rare-but-valid concepts
            contextual_score = min(1.0, freq_s + struct_bonus)
            contextual_score = max(0.05, contextual_score)

            # Paper Eq.1 — w(lm, c) = 2·ctx·cos / (ctx + cos)
            sim_nn = max(0.0, sim)   # cosine can be slightly negative
            denom = contextual_score + sim_nn
            final_score = (2.0 * contextual_score * sim_nn / denom) if denom > 0.0 else 0.0

            results.append((phrase, final_score, i))

        # Sort by harmonic-mean score (descending)
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
        """Remove near-duplicate candidates.  Prefer SHORTER & higher-scoring names."""
        # Pre-sort: shorter names first (at equal score), so 'Artificial Intelligence'
        # is kept instead of 'Artificial Intelligence – Educational Notes …'
        items = sorted(items, key=lambda x: (-x[1], len(x[0])))

        deduped = []
        seen_lower: list[str] = []
        for name, score, idx in items:
            name_lower = name.lower().strip()
            is_dup = False
            for existing in seen_lower:
                shorter = min(len(name_lower), len(existing))
                longer = max(len(name_lower), len(existing))
                if shorter == 0:
                    continue
                # Exact containment: only suppress the LONGER variant
                if name_lower in existing:
                    # name_lower is substring of existing — name is *shorter*, keep it,
                    # but only if significantly shorter (avoids 'AI' swallowing 'Artificial Intelligence')
                    if len(name_lower) < len(existing) * 0.7:
                        continue  # keep the shorter one
                    is_dup = True
                    break
                if existing in name_lower:
                    # existing is substring of name_lower — name is *longer*
                    # BUT if existing is single-word and name is multi-word, the
                    # longer name is more specific ("Artificial Intelligence" > "Artificial")
                    existing_words = len(existing.split())
                    name_words = len(name_lower.split())
                    if existing_words == 1 and name_words >= 2:
                        continue  # keep the more specific multi-word name
                    is_dup = True
                    break
                # Character-overlap ratio
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
        """
        Discover relations with IEEE EduKG semantics:
          - PART_OF      : higher-layer concept contains lower-layer (ontology hierarchy)
          - PREREQUISITE_OF : explicit text signals or document-order between same-layer concepts
          - LEADS_TO     : concept A in sequence leads to concept B (same layer, adjacent)
          - RELATED_TO   : semantic similarity without clear hierarchy
        """
        relations = []
        if len(embeddings) < 2:
            return relations

        text_lower = text[:30000].lower()
        existing_pairs: set = set()

        for i in range(len(embeddings)):
            for j in range(i + 1, len(embeddings)):
                n1 = np.linalg.norm(embeddings[i])
                n2 = np.linalg.norm(embeddings[j])
                if n1 == 0 or n2 == 0:
                    continue
                sim = float(np.dot(embeddings[i], embeddings[j]) / (n1 * n2))
                if sim < 0.55:
                    continue

                ci, cj = concepts[i], concepts[j]
                name_i, name_j = ci.name.lower(), cj.name.lower()

                # ── 1. Explicit prerequisite text signals ──────────────────────
                prereq_i_j = bool(re.search(
                    rf"{re.escape(name_i)}.{{0,80}}(?:requires?|prerequisite|before|prior to|assumes?).{{0,40}}{re.escape(name_j)}",
                    text_lower))
                prereq_j_i = bool(re.search(
                    rf"{re.escape(name_j)}.{{0,80}}(?:requires?|prerequisite|before|prior to|assumes?).{{0,40}}{re.escape(name_i)}",
                    text_lower))

                if prereq_i_j:
                    rel_type, src, tgt, conf = "PREREQUISITE_OF", ci, cj, 0.88
                elif prereq_j_i:
                    rel_type, src, tgt, conf = "PREREQUISITE_OF", cj, ci, 0.88

                # ── 2. Layer-hierarchy: higher layer contains lower layer ──────
                elif ci.layer < cj.layer and sim > 0.58:
                    # A (higher layer) -[PART_OF]-> B means B is PART_OF A? No:
                    # In IEEE EduKG: Sub-topic is PART_OF Topic. So cj PART_OF ci.
                    rel_type, src, tgt, conf = "PART_OF", cj, ci, round(sim, 3)
                elif cj.layer < ci.layer and sim > 0.58:
                    rel_type, src, tgt, conf = "PART_OF", ci, cj, round(sim, 3)

                # ── 3. Part-of from text signals ────────────────────────────
                elif re.search(
                        rf"{re.escape(name_j)}.{{0,60}}(?:includes?|contains?|consists? of|comprises?).{{0,40}}{re.escape(name_i)}",
                        text_lower):
                    rel_type, src, tgt, conf = "PART_OF", ci, cj, 0.80
                elif re.search(
                        rf"{re.escape(name_i)}.{{0,60}}(?:is part of|belongs to|within|subfield of).{{0,40}}{re.escape(name_j)}",
                        text_lower):
                    rel_type, src, tgt, conf = "PART_OF", ci, cj, 0.80

                # ── 4. Leads-to: related concepts at the same layer ──────────
                elif ci.layer == cj.layer and sim > 0.62:
                    rel_type, src, tgt, conf = "LEADS_TO", ci, cj, round(sim, 3)

                # ── 5. General relatedness ────────────────────────────────
                else:
                    rel_type, src, tgt, conf = "RELATED_TO", ci, cj, round(sim, 3)

                pair = (src.id, tgt.id)
                if pair not in existing_pairs:
                    existing_pairs.add(pair)
                    relations.append(Relation(
                        source_id=src.id, target_id=tgt.id,
                        relation_type=rel_type, confidence=conf,
                        source="minilm_sif",
                    ))

        # ── Document-order PREREQUISITE chain for same-layer consecutive concepts ──
        # (covers concepts with weak embedding similarity — ensures the graph is connected)
        same_layer_groups: Dict[int, List[Concept]] = {}
        for c in concepts:
            same_layer_groups.setdefault(c.layer, []).append(c)

        for layer_group in same_layer_groups.values():
            for i in range(len(layer_group) - 1):
                pair = (layer_group[i].id, layer_group[i + 1].id)
                if pair not in existing_pairs:
                    existing_pairs.add(pair)
                    relations.append(Relation(
                        source_id=layer_group[i].id,
                        target_id=layer_group[i + 1].id,
                        relation_type="PREREQUISITE_OF",
                        confidence=0.50,
                        source="sequence",
                    ))

        return relations

    # ─── (Legacy Gemini Extraction - Removed/replaced above) ───

    # ─── Strategy 2: Embedding-based keyphrase extraction ───

    def extract_with_embeddings(self, text: str, source_doc: str = "", top_k: int = 25) -> Tuple[List[Concept], List[Relation]]:
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

        # Filter: only keep concepts with similarity above threshold
        min_score = 0.25
        top_concepts_raw = [(name, score) for name, score in similarities[:top_k] if score >= min_score]

        # Build sentence index for contextual descriptions
        sentence_map = self._build_sentence_index(text)

        concepts = []
        for name, score in top_concepts_raw:
            desc = self._find_context_sentence(name, sentence_map, source_doc)
            pos = text.lower().find(name.lower())
            position_ratio = pos / len(text) if pos >= 0 and len(text) > 0 else 0.5
            layer = self._infer_layer(name, score, text, position_ratio)
            bloom = self._infer_bloom_for_concept(name, desc)
            concepts.append(Concept(
                id=str(uuid.uuid4()),
                name=name.title(),
                description=desc,
                category="topic" if score > 0.5 else "subtopic",
                difficulty=self._infer_difficulty(name, text),
                bloom_level=bloom,
                source_document=source_doc,
                layer=layer,
            ))

        # Discover relations via embedding similarity between concepts
        top_embeddings = candidate_embeddings[:len(top_concepts_raw)]
        relations = self._discover_relations_by_embedding(concepts, top_embeddings)

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

        concepts = concepts[:25]  # Cap at 25

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

        def _add(name: str) -> bool:
            """Add a candidate if it passes basic quality + dedup checks."""
            name = re.sub(r'\s+', ' ', name).strip()  # normalise inner whitespace
            # Strip document-title prefix artefacts  ("Artificial Intelligence – Ed. Notes AI")
            if '–' in name:
                name = name.split('–')[-1].strip()
            if '—' in name:
                name = name.split('—')[-1].strip()
            if len(name) < 3 or len(name) > 80:
                return False
            key = name.lower()
            if key in seen_lower:
                return False
            if self._is_noise(name):
                return False
            seen_lower.add(key)
            candidates.append(name)
            return True

        if HAS_SPACY and _nlp:
            doc = _nlp(text[:50000])

            # Pass 1: Structural headers (highest priority)
            headers = re.findall(
                r"(?:Module|Unit|Chapter|Topic|Section|Lesson)\s*[\d.:]*\s*[:\-–]?\s*(.+)",
                text, re.IGNORECASE,
            )
            for h in headers:
                _add(h.strip().rstrip("."))

            # Pass 2: Named Entities (broadened label set)
            good_ent_labels = {"ORG", "PRODUCT", "WORK_OF_ART", "EVENT", "LAW",
                               "NORP", "FAC", "GPE", "LOC", "PERSON",
                               "MISC", "LANGUAGE"}
            for ent in doc.ents:
                _add(ent.text.strip())

            # Pass 3: Noun chunks – filtered
            for chunk in doc.noun_chunks:
                # Remove leading determiners/articles
                phrase = self._JUNK_PATTERNS.sub("", chunk.text).strip()
                words = phrase.split()
                if len(words) >= 2 or (len(words) == 1 and phrase[0:1].isupper()):
                    _add(phrase)

            # Pass 4 (NEW): Title-Case / Acronym bigrams & trigrams
            # Catches "Machine Learning", "Deep Learning", "Natural Language Processing"
            # Also handles "Narrow AI" where last word is all-caps.
            tc_pattern = re.compile(
                r'\b([A-Z][a-z]+(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,6})){1,3})\b'   # Title Case + optional acronym tail
                r'|\b([A-Z]{2,6})\b'                                            # Standalone acronyms (AI, NLP, ML)
            )
            for m in tc_pattern.finditer(text):
                phrase = (m.group(1) or m.group(2)).strip()
                _add(phrase)

            # Pass 5 (NEW): Single capitalised technical terms (≥ 4 chars)
            # e.g. "Cybersecurity", "Blockchain", "Malware"
            single_cap = re.compile(r'\b([A-Z][a-z]{3,})\b')
            for m in single_cap.finditer(text):
                word = m.group(1)
                if text.count(word) >= 2:
                    _add(word)

            # Pass 6 (NEW): Case-insensitive concept discovery from text body
            # Many key concepts appear only in lowercase inside sentences:
            # "reinforcement learning", "neural networks", "speech recognition"
            ci_patterns = re.compile(
                r'\b((?:supervised|unsupervised|reinforcement|deep|machine|transfer)\s+learning)\b'
                r'|\b(neural\s+networks?)\b'
                r'|\b(natural\s+language\s+processing)\b'
                r'|\b(computer\s+vision)\b'
                r'|\b(speech\s+recognition)\b'
                r'|\b(decision[\-\s]making)\b'
                r'|\b(expert\s+systems?)\b'
                r'|\b(knowledge\s+(?:graph|base|representation)s?)\b'
                r'|\b(autonomous\s+vehicles?)\b'
                r'|\b(smart\s+farming)\b'
                r'|\b(fraud\s+detection)\b'
                r'|\b(medical\s+diagnosis)\b'
                r'|\b(data\s+privacy)\b'
                r'|\b(problem[\-\s]solving)\b',
                re.IGNORECASE
            )
            for m in ci_patterns.finditer(text):
                phrase = next(g for g in m.groups() if g is not None)
                # Title-case the display name
                _add(phrase.strip().title())

            # Pass 7 (NEW): Parenthetical abbreviations → "Natural Language Processing (NLP)" → extract the full name
            paren_pat = re.compile(r'([A-Z][a-z]+(?:\s+[A-Za-z]+){1,4})\s*\([A-Z]{2,6}\)')
            for m in paren_pat.finditer(text):
                _add(m.group(1).strip())

        else:
            # Fallback: capitalized multi-word phrases
            words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', text)
            for w in words:
                _add(w)

        logger.info(f"Candidate extraction: {len(candidates)} phrases from {len(text)} chars")
        return candidates[:200]

    def _is_noise(self, phrase: str) -> bool:
        """Check if a candidate phrase is noise / non-educational."""
        phrase_lower = phrase.lower().strip()
        words = phrase_lower.split()
        if not words:
            return True
        word_set = set(words)

        # ── Hard max word-count (LightRAG / GraphRAG best practice) ──
        # Legitimate concept names are 1-4 words; anything longer is a heading or fragment.
        if len(words) > 4:
            return True

        # ── Structural / whitespace corruption ──
        if '\n' in phrase or '\t' in phrase:
            return True
        # Contains em-dash / en-dash separator → likely a title-concatenation artefact
        if '–' in phrase or '—' in phrase:
            return True
        # Has bullet characters at the start → list artefact
        if phrase_lower.startswith(('●', '•', '○', '■', '▪', '-')):
            return True

        # ── All words are stopwords ──
        if word_set.issubset(self._STOPWORD_PHRASES):
            return True
        # Single word that is a stopword or too generic
        if len(words) == 1 and phrase_lower in self._STOPWORD_PHRASES:
            return True
        # Single word that is too short (< 4 chars)
        if len(words) == 1 and len(phrase_lower) < 4:
            return True
        # Too short after cleaning
        cleaned = re.sub(r'[^a-zA-Z\s]', '', phrase).strip()
        if len(cleaned) < 3:
            return True
        # Pure numbers / mark-scheme artefacts
        if re.match(r'^[\d\s.,%/+\-]+$', phrase):
            return True

        # ── Sentence fragment detection ──
        # Phrases ≥ 5 words that look like a sentence (contain common verbs / articles) are noise
        if len(words) >= 5:
            sent_verbs = {'is', 'are', 'was', 'were', 'has', 'have', 'had',
                          'refers', 'can', 'will', 'shall', 'may', 'should',
                          'benefit', 'include', 'includes', 'enables'}
            if word_set & sent_verbs:
                return True
        # Starts with "other", "the", etc. + multi-word  → partial heading / noise phrase
        if len(words) >= 3 and words[0] in {'other', 'some', 'these', 'those', 'several', 'many'}:
            return True

        # ── Single common English word that is not a technical concept ──
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
                "including", "respectively", "however", "therefore",
                "specifically", "additionally", "furthermore",
            }
            if phrase_lower in common_words:
                return True

        # ── Ends with a vague generic word ──
        # Only block when the qualifier is itself generic ("various types", "other methods")
        vague_qualifiers = {
            "specific", "particular", "various", "other", "such", "general",
            "theoretical", "any", "predefined", "domain-specific",
            "important", "major", "key", "main", "certain", "some",
        }
        generic_tails = {
            "concept", "concepts", "task", "tasks",
            "factor", "factors", "issue", "issues",
            "advantage", "advantages", "challenge", "challenges",
            "goal", "goals", "aim", "aims",
            "feature", "features", "part", "parts",
            "example", "examples", "use", "uses",
            "result", "results", "solution", "solutions",
            "activity", "activities", "context",
            "difference", "differences", "basis", "term", "terms",
        }
        if len(words) >= 2 and words[-1] in generic_tails and words[0] in vague_qualifiers:
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
        """Document-level Bloom's level (fallback for non-concept-specific calls)."""
        text_lower = text[:1000].lower()
        for level, keywords in self.BLOOM_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                return level
        return "understand"

    def _infer_bloom_for_concept(self, name: str, context_sentence: str) -> str:
        """
        Infer Bloom's Taxonomy level per concept based on name + its context sentence.
        Searches from highest to lowest so 'create' beats 'remember'.
        """
        combined = (name + " " + context_sentence).lower()
        for level in ["create", "evaluate", "analyze", "apply", "understand", "remember"]:
            if any(kw in combined for kw in self.BLOOM_KEYWORDS[level]):
                return level
        # Heuristic fallbacks from concept name signals
        name_l = name.lower()
        if any(w in name_l for w in ["advanced", "complex", "proof", "optimization", "theorem"]):
            return "analyze"
        if any(w in name_l for w in ["implement", "design", "build", "construct", "develop"]):
            return "apply"
        if any(w in name_l for w in ["algorithm", "procedure", "technique", "method"]):
            return "apply"
        return "understand"

    def _infer_layer(self, name: str, score: float, text: str, position_ratio: float = 0.5) -> int:
        """
        Assign IEEE EduKG ontology layer:
          L0 Domain  – top-level subject area (very high SIF, early in doc, 1-3 words)
          L1 Topic   – Module/Chapter/Unit heading (high SIF or explicit heading)
          L2 Sub-topic – Section headings or medium SIF
          L3 Concept – Specific terms, theorems, algorithms, definitions (leaf nodes)

        Parameters
        ----------
        position_ratio : float
            Fraction of document where the concept first appears (0 = start, 1 = end).
        """
        name_lower = name.lower()
        text_lower = text[:8000].lower()
        word_count = len(name.split())

        # ── L3 first: specific leaf-level signals ──────────────────────────
        leaf_markers = ["theorem", "lemma", "corollary", "definition", "formula",
                        "algorithm", "equation", "proposition", "proof"]
        if any(m in name_lower for m in leaf_markers):
            return 3
        if re.search(rf"(?:theorem|lemma|definition|algorithm|formula)\s*[:\-–]?\s*{re.escape(name_lower)}",
                     text_lower):
            return 3

        # ── L1: explicit Module/Chapter/Unit heading ───────────────────────
        if re.search(rf"(?:module|unit|chapter)\s*\d*[:\-–]?\s*{re.escape(name_lower)}", text_lower):
            return 1

        # ── L2: Section/Sub-section heading ───────────────────────────────
        if re.search(rf"(?:section|subsection|sub-section|topic|subtopic)\s*[\d.]*[:\-–\s]?\s*{re.escape(name_lower)}",
                     text_lower):
            return 2

        # ── L0: Domain — very high SIF, appears very early, short ─────────
        if score > 0.58 and position_ratio < 0.08 and 1 <= word_count <= 3:
            return 0

        # ── Score + position heuristics ───────────────────────────────────
        if score > 0.48:
            # High-scoring concepts near the start are Topics
            return 1 if position_ratio < 0.25 else 2
        elif score > 0.32:
            return 2  # Sub-topic
        else:
            return 3  # Concept/Leaf

    # ─── Paper §4.4: Wikipedia-based Concept Expansion ───────────────────────

    def _expand_with_wikipedia(
        self,
        concepts: List[Concept],
        source_doc: str = "",
        max_categories: int = 3,
        max_related: int = 3,
        top_n_source: int = 8,
    ) -> Tuple[List[Concept], List[Relation]]:
        """
        Paper §4.4 — Concept Expansion (Category-based + Related-concept).

        For each of the top `top_n_source` highest-weighted concepts:
          (a) Category-based: Wikipedia categories → L1 Topic nodes  [BELONGS_TO]
          (b) Related-concept: Wikipedia page links → L3 Concept nodes [RELATED_TO]

        Mirrors the paper's use of DBpedia SPARQL / dct:subject & dbo:wikiPageWikiLink,
        implemented here via the free Wikipedia MediaWiki API (no auth needed).
        """
        try:
            import requests as _req
        except ImportError:
            logger.warning("⚠ requests not available — skipping Wikipedia expansion")
            return [], []

        new_concepts: List[Concept] = []
        new_relations: List[Relation] = []
        seen_names = {c.name.lower() for c in concepts}

        # Only expand the top-weighted source concepts (avoids noise from weak ones)
        sorted_src = sorted(concepts, key=lambda c: c.weight, reverse=True)[:top_n_source]

        WIKI_API = "https://en.wikipedia.org/w/api.php"
        HEADERS  = {"User-Agent": "TrackEneer-EduKG/1.0 (educational-research)"}

        for concept in sorted_src:
            wiki_title = concept.name.replace(" ", "_")

            # ── (a) Category-based expansion (Paper §4.4.1) ─────────────────
            try:
                resp = _req.get(WIKI_API, params={
                    "action": "query", "titles": wiki_title,
                    "prop": "categories", "cllimit": str(max_categories + 4),
                    "clshow": "!hidden", "format": "json",
                }, headers=HEADERS, timeout=6)
                if resp.status_code == 200:
                    pages = resp.json().get("query", {}).get("pages", {})
                    cat_count = 0
                    for page in pages.values():
                        for cat in page.get("categories", []):
                            if cat_count >= max_categories:
                                break
                            raw_name = cat.get("title", "")
                            cat_name = raw_name.replace("Category:", "").strip()
                            # Skip stub / date / maintenance categories
                            if (cat_name and 4 < len(cat_name) < 70
                                    and cat_name.lower() not in seen_names
                                    and not re.search(r'\d{4}|stub|article|wiki|cs1|good', cat_name, re.I)):
                                seen_names.add(cat_name.lower())
                                nc = Concept(
                                    id=str(uuid.uuid4()),
                                    name=cat_name,
                                    description=f"Wikipedia category of '{concept.name}'",
                                    category="topic",
                                    difficulty="medium",
                                    bloom_level="understand",
                                    source_document=source_doc,
                                    layer=1,          # Category → Topic tier (Paper §4.4.1)
                                    weight=0.45,
                                    wikipedia_url=f"https://en.wikipedia.org/wiki/Category:{cat_name.replace(' ', '_')}",
                                )
                                new_concepts.append(nc)
                                new_relations.append(Relation(
                                    source_id=concept.id, target_id=nc.id,
                                    relation_type="BELONGS_TO",
                                    confidence=0.80, source="wikipedia_expansion",
                                ))
                                cat_count += 1
            except Exception as e:
                logger.debug(f"Wikipedia category fetch failed for '{concept.name}': {e}")

            # ── (b) Related-concept expansion (Paper §4.4.2) ─────────────────
            try:
                resp = _req.get(WIKI_API, params={
                    "action": "query", "titles": wiki_title,
                    "prop": "links", "pllimit": str(max_related + 6),
                    "plnamespace": "0", "format": "json",
                }, headers=HEADERS, timeout=6)
                if resp.status_code == 200:
                    pages = resp.json().get("query", {}).get("pages", {})
                    lnk_count = 0
                    for page in pages.values():
                        for link in page.get("links", []):
                            if lnk_count >= max_related:
                                break
                            rel_name = link.get("title", "").strip()
                            # Skip special Wikipedia pages (contain colon)
                            if (rel_name and 4 < len(rel_name) < 70
                                    and rel_name.lower() not in seen_names
                                    and ":" not in rel_name):
                                seen_names.add(rel_name.lower())
                                nc = Concept(
                                    id=str(uuid.uuid4()),
                                    name=rel_name,
                                    description=f"Related concept linked from '{concept.name}' via Wikipedia",
                                    category="concept",
                                    difficulty="medium",
                                    bloom_level="understand",
                                    source_document=source_doc,
                                    layer=3,          # Related concept → leaf tier (Paper §4.4.2)
                                    weight=0.30,
                                    wikipedia_url=f"https://en.wikipedia.org/wiki/{rel_name.replace(' ', '_')}",
                                )
                                new_concepts.append(nc)
                                new_relations.append(Relation(
                                    source_id=concept.id, target_id=nc.id,
                                    relation_type="RELATED_TO",
                                    confidence=0.65, source="wikipedia_expansion",
                                ))
                                lnk_count += 1
            except Exception as e:
                logger.debug(f"Wikipedia links fetch failed for '{concept.name}': {e}")

        logger.info(f"✓ Wikipedia expansion: +{len(new_concepts)} concepts, +{len(new_relations)} relations")
        return new_concepts, new_relations


# ============================================================================
# KNOWLEDGE GRAPH STORE (Neo4j)
# ============================================================================

class KnowledgeGraphStore:
    """Manages CRUD operations for the EduKG in Neo4j."""

    def __init__(self):
        self.driver = get_driver()

    def store_concepts(self, concepts: List[Concept], user_email: str, day: Optional[str] = None) -> int:
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
                        concept.layer = $layer,
                        concept.weight = $weight,
                        concept.wikipedia_url = $wikipedia_url,
                        concept.createdAt = datetime()
                    ON MATCH SET
                        concept.description = CASE WHEN $description <> '' THEN $description ELSE concept.description END,
                        concept.category = $category,
                        concept.difficulty = $difficulty,
                        concept.bloom_level = $bloom_level,
                        concept.layer = $layer,
                        concept.weight = $weight,
                        concept.wikipedia_url = CASE WHEN $wikipedia_url <> '' THEN $wikipedia_url ELSE concept.wikipedia_url END,
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
                    layer=c_dict.get("layer", 2),
                    weight=c_dict.get("weight", 0.0),
                    wikipedia_url=c_dict.get("wikipedia_url", ""),
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
                    "layer": c.get("layer", 2),
                    "weight": c.get("weight", 0.0),
                    "wikipedia_url": c.get("wikipedia_url", ""),
                })

            # Edges
            edges_result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(src:Concept)-[r]->(tgt:Concept)<-[:HAS_CONCEPT]-(u)
                WHERE type(r) IN ['PREREQUISITE_OF', 'PART_OF', 'RELATED_TO', 'LEADS_TO', 'BELONGS_TO']
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

    def search_concepts(self, user_email: str, query: str, limit: int = 20) -> List[dict]:
        """Find concept candidates without loading the full graph."""
        tokens = [t.lower() for t in re.findall(r"[a-zA-Z0-9_+#.-]+", query or "") if len(t) > 2][:8]
        query_lower = (query or "").strip().lower()
        if not tokens and not query_lower:
            return []

        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
                WHERE
                    ($query = '' OR toLower(c.name) CONTAINS $query OR toLower(coalesce(c.description, '')) CONTAINS $query)
                    OR ANY(token IN $tokens WHERE toLower(c.name) CONTAINS token OR toLower(coalesce(c.description, '')) CONTAINS token)
                RETURN c
                ORDER BY coalesce(c.mastery, 0) ASC, c.createdAt DESC
                LIMIT $limit
                """,
                email=user_email,
                query=query_lower,
                tokens=tokens,
                limit=limit,
            )
            concepts = []
            for record in result:
                c = record["c"]
                concepts.append({
                    "id": c.get("id", ""),
                    "name": c.get("name", ""),
                    "description": c.get("description", ""),
                    "category": c.get("category", ""),
                    "difficulty": c.get("difficulty", ""),
                    "bloom_level": c.get("bloom_level", ""),
                    "mastery": c.get("mastery", 0.0),
                    "source_document": c.get("source_document", ""),
                    "layer": c.get("layer", 2),
                    "weight": c.get("weight", 0.0),
                })
            return concepts

    def get_recent_concepts(self, user_email: str, limit: int = 120) -> List[dict]:
        """Return a bounded concept set for fast mentor ranking."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
                RETURN c
                ORDER BY c.createdAt DESC
                LIMIT $limit
                """,
                email=user_email,
                limit=limit,
            )
            concepts = []
            for record in result:
                c = record["c"]
                concepts.append({
                    "id": c.get("id", ""),
                    "name": c.get("name", ""),
                    "description": c.get("description", ""),
                    "category": c.get("category", ""),
                    "difficulty": c.get("difficulty", ""),
                    "bloom_level": c.get("bloom_level", ""),
                    "mastery": c.get("mastery", 0.0),
                    "source_document": c.get("source_document", ""),
                    "layer": c.get("layer", 2),
                    "weight": c.get("weight", 0.0),
                })
            return concepts

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
                    "layer": c.get("layer", 2),
                    "weight": c.get("weight", 0.0),
                    "wikipedia_url": c.get("wikipedia_url", ""),
                })

            # Only edges where both endpoints belong to this document
            edges_result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(src:Concept)-[r]->(tgt:Concept)<-[:HAS_CONCEPT]-(u)
                WHERE src.source_document = $doc AND tgt.source_document = $doc
                  AND type(r) IN ['PREREQUISITE_OF', 'PART_OF', 'RELATED_TO', 'LEADS_TO', 'BELONGS_TO']
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
    # GAP ANALYSIS & LEARNING PATH  (IEEE EduKG §4 — Knowledge Tracing + Gap Analysis)
    # ============================================================================

    def get_learning_path(self, concept_name: str, user_email: str) -> dict:
        """
        Generate optimal learning path to a target concept.
        Traverses PREREQUISITE_OF and PART_OF edges backwards, returns topo-sorted
        steps ordered by IEEE ontology layer (Domain first → Concept last).
        Unmastered steps are flagged so the frontend can highlight what’s missing.
        """
        with self.driver.session() as session:
            # Collect the target node
            target_res = session.run("""
                MATCH (c:Concept {name: $name, userEmail: $email})
                RETURN c.name AS name, coalesce(c.mastery, 0) AS mastery,
                       c.difficulty AS difficulty, c.bloom_level AS bloom_level,
                       coalesce(c.layer, 2) AS layer, c.description AS description
            """, name=concept_name, email=user_email)
            target_row = target_res.single()
            if not target_row:
                return {"error": f"Concept '{concept_name}' not found in your graph"}

            # Walk the prerequisite graph (up to 8 hops) to collect all ancestors
            prereq_res = session.run("""
                MATCH path = (prereq:Concept)-[:PREREQUISITE_OF|PART_OF*1..8]->(target:Concept {name: $name, userEmail: $email})
                WHERE prereq.userEmail = $email
                UNWIND nodes(path) AS n
                WITH DISTINCT n
                RETURN n.name AS name, coalesce(n.mastery, 0) AS mastery,
                       n.difficulty AS difficulty, n.bloom_level AS bloom_level,
                       coalesce(n.layer, 2) AS layer, n.description AS description
                ORDER BY coalesce(n.layer, 2) ASC, coalesce(n.mastery, 0) DESC
            """, name=concept_name, email=user_email)

            steps = [dict(r) for r in prereq_res]
            # Ensure the target itself is in the list
            target_dict = dict(target_row)
            if not any(s["name"] == concept_name for s in steps):
                steps.append(target_dict)

            unmastered = [s for s in steps if s["mastery"] < 0.7]
            mastered   = [s for s in steps if s["mastery"] >= 0.7]

            # Bloom progression: steps sorted by Bloom level depth
            bloom_order = ["remember", "understand", "apply", "analyze", "evaluate", "create"]
            steps_sorted = sorted(
                steps,
                key=lambda s: (s.get("layer", 2), bloom_order.index(s.get("bloom_level", "understand"))
                               if s.get("bloom_level") in bloom_order else 1)
            )

            return {
                "target": concept_name,
                "total_steps": len(steps_sorted),
                "mastered_count": len(mastered),
                "unmastered_count": len(unmastered),
                "completion_pct": round(len(mastered) / len(steps_sorted) * 100, 1) if steps_sorted else 0,
                "learning_path": steps_sorted,
                "next_recommended": unmastered[0] if unmastered else None,
                "all_mastered": len(unmastered) == 0,
            }

    def get_gap_analysis(self, user_email: str, mastery_threshold: float = 0.7) -> dict:
        """
        IEEE EduKG Gap Analysis (Section 4.2):
        - Layer coverage: how many concepts are mastered at each ontology layer
        - Bloom's distribution: cognitive depth across the graph
        - Critical gaps: unmastered concepts that BLOCK other concepts downstream
        - Root-cause candidates: leaf-level weaknesses causing upper-level failures
        """
        with self.driver.session() as session:
            # Layer coverage
            layer_res = session.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
                WITH coalesce(c.layer, 2) AS layer,
                     count(c) AS total,
                     avg(coalesce(c.mastery, 0)) AS avg_mastery,
                     count(CASE WHEN coalesce(c.mastery, 0) >= $threshold THEN 1 END) AS mastered
                RETURN layer, total, round(avg_mastery * 100, 1) AS avg_mastery_pct,
                       mastered,
                       round(toFloat(mastered) / total * 100, 1) AS coverage_pct
                ORDER BY layer
            """, email=user_email, threshold=mastery_threshold)
            layer_coverage = [dict(r) for r in layer_res]

            # Bloom distribution with mastery averages
            bloom_res = session.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
                RETURN c.bloom_level AS bloom_level,
                       count(c) AS concept_count,
                       round(avg(coalesce(c.mastery, 0)) * 100, 1) AS avg_mastery_pct
                ORDER BY bloom_level
            """, email=user_email)
            bloom_dist = [dict(r) for r in bloom_res]

            # Critical blocking gaps: unmastered concepts that are prerequisites for others
            critical_res = session.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
                WHERE coalesce(c.mastery, 0) < $threshold
                OPTIONAL MATCH (c)-[:PREREQUISITE_OF]->(dep:Concept {userEmail: $email})
                WITH c, count(dep) AS blocking_count
                WHERE blocking_count > 0
                RETURN c.name AS name,
                       round(coalesce(c.mastery, 0) * 100, 1) AS mastery_pct,
                       c.difficulty AS difficulty,
                       c.bloom_level AS bloom_level,
                       coalesce(c.layer, 2) AS layer,
                       blocking_count
                ORDER BY blocking_count DESC, mastery_pct ASC
                LIMIT 10
            """, email=user_email, threshold=mastery_threshold)
            critical_gaps = [dict(r) for r in critical_res]

            # Total unmastered
            total_res = session.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
                RETURN count(c) AS total,
                       count(CASE WHEN coalesce(c.mastery, 0) >= $threshold THEN 1 END) AS mastered
            """, email=user_email, threshold=mastery_threshold)
            totals = total_res.single() or {}

            total_concepts = totals.get("total", 0)
            total_mastered = totals.get("mastered", 0)

            return {
                "summary": {
                    "total_concepts":   total_concepts,
                    "mastered_concepts": total_mastered,
                    "gap_count":        total_concepts - total_mastered,
                    "overall_coverage_pct": round(total_mastered / total_concepts * 100, 1) if total_concepts else 0,
                    "mastery_threshold": mastery_threshold,
                },
                "layer_coverage":     layer_coverage,
                "bloom_distribution": bloom_dist,
                "critical_gaps":      critical_gaps,
            }

    def get_bloom_summary(self, user_email: str) -> dict:
        """
        Return Bloom's Taxonomy distribution with mastery stats —
        used to show cognitive depth and suggest next learning objectives.
        """
        bloom_order = ["remember", "understand", "apply", "analyze", "evaluate", "create"]
        with self.driver.session() as session:
            result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
                RETURN c.bloom_level AS level,
                       count(c) AS count,
                       round(avg(coalesce(c.mastery, 0)) * 100, 1) AS avg_mastery_pct,
                       collect(c.name)[0..5] AS sample_concepts
                ORDER BY level
            """, email=user_email)
            rows = [dict(r) for r in result]
            # Ensure all 6 levels are represented (even if empty)
            row_map = {r["level"]: r for r in rows}
            bloom_data = []
            for level in bloom_order:
                if level in row_map:
                    bloom_data.append(row_map[level])
                else:
                    bloom_data.append({"level": level, "count": 0, "avg_mastery_pct": 0.0, "sample_concepts": []})

            # Highest achieved level
            achieved = [b for b in bloom_data if b["count"] > 0]
            highest = achieved[-1]["level"] if achieved else "none"
            next_level_map = {b: bloom_order[i + 1] for i, b in enumerate(bloom_order[:-1])}

            return {
                "bloom_levels": bloom_data,
                "highest_level_covered": highest,
                "recommended_next_level": next_level_map.get(highest),
            }


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

    def _preprocess_text(self, text: str) -> str:
        """
        Clean and normalize text before extraction.
        1. Fix hyphenation (word-\nbreak -> wordbreak)
        2. Remove noise: URLs, emails, standalone page numbers
        3. Normalize whitespace (spaces, tabs, excessive newlines)
        4. Remove non-printable characters
        """
        if not text:
            logger.info("⚠ _preprocess_text: received empty text, skipping.")
            return ""

        original_len   = len(text)
        original_lines = text.count('\n')
        logger.info("╔══ Preprocessing Pipeline ══════════════════════════╗")
        logger.info(f"║ INPUT   : {original_len} chars, {original_lines} lines")

        # ── Stage 1: Fix hyphenation at line endings ───────────────────────
        hyphen_matches = len(re.findall(r'(\w+)-\n(\w+)', text))
        text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text)
        logger.info(f"║ Stage 1 │ Fix hyphenation    : {hyphen_matches} joins, text now {len(text)} chars")

        # ── Stage 1b: Normalize PDF line-breaks (core fix) ────────────────
        # PDFs inject \n in the middle of sentences.  Join lines that don't
        # look like paragraph boundaries, headings, or list items.
        before = len(text)
        lines = text.split('\n')
        merged: list[str] = []
        for line in lines:
            stripped = line.strip()
            # Keep blank lines (paragraph separators)
            if not stripped:
                merged.append('')
                continue
            # If previous line exists and ends with lower-alpha / comma /
            # semicolon, the current line is a continuation
            if (merged and merged[-1]
                    and not merged[-1].endswith((':', '.', '!', '?'))
                    and not re.match(r'^(?:Module|Unit|Chapter|Section|Topic|Lesson|\d+\.\s)', stripped, re.IGNORECASE)
                    and not re.match(r'^[●•\-\*]', stripped)):
                merged[-1] = merged[-1].rstrip() + ' ' + stripped
            else:
                merged.append(stripped)
        text = '\n'.join(merged)
        logger.info(f"║ Stage 1b│ Rejoin PDF lines   : merged {before - len(text):+d} chars")

        # ── Stage 2a: Remove URLs ──────────────────────────────────────────
        urls_removed = len(re.findall(r'http[s]?://\S+', text))
        before = len(text)
        text = re.sub(r'http[s]?://\S+', '', text)
        logger.info(f"║ Stage 2a│ Remove URLs        : {urls_removed} removed, -{before - len(text)} chars")

        # ── Stage 2b: Remove Emails ────────────────────────────────────────
        emails_removed = len(re.findall(r'\S+@\S+', text))
        before = len(text)
        text = re.sub(r'\S+@\S+', '', text)
        logger.info(f"║ Stage 2b│ Remove emails      : {emails_removed} removed, -{before - len(text)} chars")

        # ── Stage 3: Remove standalone page numbers ────────────────────────
        page_nums = len(re.findall(r'^\d+\s*$', text, flags=re.MULTILINE))
        before = len(text)
        text = re.sub(r'^\d+\s*$', '', text, flags=re.MULTILINE)
        logger.info(f"║ Stage 3 │ Remove page nums   : {page_nums} removed, -{before - len(text)} chars")

        # ── Stage 4a: Collapse multiple spaces/tabs ────────────────────────
        before = len(text)
        text = re.sub(r'[ \t]+', ' ', text)
        logger.info(f"║ Stage 4a│ Collapse spaces    : -{before - len(text)} chars")

        # ── Stage 4b: Collapse excessive newlines ─────────────────────────
        excess_nl = len(re.findall(r'\n{3,}', text))
        before = len(text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        logger.info(f"║ Stage 4b│ Collapse newlines  : {excess_nl} blocks collapsed, -{before - len(text)} chars")

        # ── Stage 5: Strip non-printable characters ────────────────────────
        before = len(text)
        text = ''.join(c for c in text if c.isprintable() or c in '\n\t')
        logger.info(f"║ Stage 5 │ Remove non-print   : {before - len(text)} chars removed")

        text = text.strip()
        final_len   = len(text)
        final_lines = text.count('\n')
        total_reduction = original_len - final_len
        pct = (total_reduction / original_len * 100) if original_len else 0
        logger.info(f"║ OUTPUT  : {final_len} chars, {final_lines} lines")
        logger.info(f"║ TOTAL   : -{total_reduction} chars ({pct:.1f}% reduction)")
        logger.info("╚════════════════════════════════════════════════════╝")

        return text

    def process_text(self, text: str, user_email: str, source_doc: str = "", strategy: str = "llm") -> dict:
        """Process raw text into a Knowledge Graph."""

        # ── Capture preprocessing stats for API response ──
        original_len   = len(text)
        original_lines = text.count('\n')

        # Preprocess text to clean artifacts (logs each stage via logger)
        text = self._preprocess_text(text)

        final_len   = len(text)
        final_lines = text.count('\n')
        total_removed = original_len - final_len
        pct = round((total_removed / original_len * 100), 1) if original_len else 0

        preprocessing_stats = {
            "input_chars":    original_len,
            "input_lines":    original_lines,
            "output_chars":   final_len,
            "output_lines":   final_lines,
            "total_removed":  total_removed,
            "reduction_pct":  pct,
            "stages": [
                {"label": "Stage 1  Fix hyphenation ", "detail": "word-\\n joins merged"},
                {"label": "Stage 2a Remove URLs     ", "detail": "http/https links stripped"},
                {"label": "Stage 2b Remove emails   ", "detail": "address tokens stripped"},
                {"label": "Stage 3  Remove page nums", "detail": "standalone digit lines removed"},
                {"label": "Stage 4a Collapse spaces ", "detail": "multiple spaces/tabs → single space"},
                {"label": "Stage 4b Collapse newlines", "detail": "3+ newlines → 2 newlines"},
                {"label": "Stage 5  Non-printable   ", "detail": "control characters stripped"},
            ]
        }

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
            "concepts_extracted":  concept_count,
            "relations_extracted": relation_count,
            "concepts":            [c.to_dict() for c in concepts],
            "relations":           [r.to_dict() for r in relations],
            "strategy_used":       strategy,
            "preprocessing_stats": preprocessing_stats,
        }

    def process_pdf(self, file_path: str, user_email: str, strategy: str = "llm", original_filename: str = "") -> dict:
        """Extract text from PDF and build Knowledge Graph."""
        text = ""
        # ── Strategy 1: pdfplumber (best for digital/text PDFs) ──
        if HAS_PDFPLUMBER:
            try:
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                if text.strip():
                    logger.info(f"✓ pdfplumber extracted {len(text)} chars from {Path(file_path).name}")
            except Exception as e:
                logger.warning(f"⚠ pdfplumber extraction failed: {e}")
                text = ""

        # ── Strategy 2: PyMuPDF (handles complex layouts, rotated/scanned text) ──
        if not text.strip() and HAS_PYMUPDF:
            try:
                doc = fitz.open(file_path)
                for page in doc:
                    page_text = page.get_text("text")
                    if page_text:
                        text += page_text + "\n"
                doc.close()
                if text.strip():
                    logger.info(f"✓ PyMuPDF extracted {len(text)} chars from {Path(file_path).name}")
            except Exception as e:
                logger.warning(f"⚠ PyMuPDF extraction failed: {e}")
                text = ""

        if not text.strip():
            # Only attempt text-read if it's likely a text file (not .pdf)
            if not file_path.lower().endswith(".pdf"):
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read()
                except Exception:
                    return {"error": "Could not extract text from file"}
            else:
                return {"error": "Could not extract text from PDF — install pdfplumber or pymupdf"}

        source_name = original_filename or Path(file_path).name
        result = self.process_text(text, user_email, source_doc=source_name, strategy=strategy)
        return result

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
            with self.store.driver.session() as session:
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

    def expand_with_wikipedia(
        self,
        user_email: str,
        source_document: str = "",
        max_categories: int = 3,
        max_related: int = 3,
        top_n_source: int = 8,
    ) -> dict:
        """
        Paper §4.4 — Concept Expansion applied to an already-built graph.

        1. Retrieve existing concepts for the user (optionally filtered by doc)
        2. Call ConceptExtractor._expand_with_wikipedia()
        3. Store the new concepts + relations in Neo4j
        Returns a summary dict.
        """
        # Fetch existing concepts so we know what's already there
        if source_document:
            graph = self.store.get_graph_by_document(user_email, source_document)
        else:
            graph = self.store.get_full_graph(user_email)

        if not graph["nodes"]:
            return {"error": "No concepts found. Upload a document first."}

        # Re-hydrate as Concept objects (only need id, name, weight, layer)
        existing: List[Concept] = []
        for n in graph["nodes"]:
            existing.append(Concept(
                id=n.get("id", str(uuid.uuid4())),
                name=n.get("name", ""),
                layer=n.get("layer", 2),
                weight=float(n.get("weight", 0.0)),
                source_document=source_document or n.get("source_document", ""),
            ))

        new_concepts, new_relations = self.extractor._expand_with_wikipedia(
            existing,
            source_doc=source_document,
            max_categories=max_categories,
            max_related=max_related,
            top_n_source=top_n_source,
        )

        if not new_concepts:
            return {
                "message": "No new concepts found via Wikipedia expansion.",
                "new_concepts": 0,
                "new_relations": 0,
            }

        concept_count  = self.store.store_concepts(new_concepts, user_email)
        relation_count = self.store.store_relations(new_relations, new_concepts + existing, user_email)

        return {
            "message": f"Wikipedia expansion complete: +{concept_count} concepts, +{relation_count} relations",
            "new_concepts":  concept_count,
            "new_relations": relation_count,
            "concepts": [c.to_dict() for c in new_concepts],
        }


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

    # Process inline so preprocessing_stats can be returned in the response
    original_name = file.filename
    try:
        result = pipeline.process_pdf(str(file_path), user_email, strategy=strategy, original_filename=original_name)
        print(f"[OK] KG built from {file.filename}: {result.get('concepts_extracted', 0)} concepts, {result.get('relations_extracted', 0)} relations")
    except Exception as e:
        print(f"[ERROR] KG build failed for {file.filename}: {e}")
        return {"status": "error", "message": str(e), "file": file.filename}

    return {
        "status": "ok",
        "message": f"Knowledge Graph built from '{file.filename}'",
        "file": file.filename,
        **result,
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


# ─── Gap Analysis (IEEE EduKG §4.2) ───

@app.get("/api/knowledge-graph/gap-analysis")
async def gap_analysis(
    request: Request,
    email: Optional[str] = None,
    mastery_threshold: float = 0.7,
):
    """
    Comprehensive IEEE EduKG gap analysis:
    - Layer coverage (Domain → Concept)
    - Bloom's Taxonomy distribution
    - Critical blocking gaps (unmastered concepts that block others)
    """
    user_email = _resolve_email(request, email)
    result = pipeline.store.get_gap_analysis(user_email, mastery_threshold)
    return {"status": "ok", **result}


# ─── Learning Path (topological prerequisite traversal) ───

@app.get("/api/knowledge-graph/learning-path/{concept_name}")
async def get_learning_path(
    concept_name: str,
    request: Request,
    email: Optional[str] = None,
):
    """
    Generate an optimal learning path to reach a target concept.
    Returns steps sorted by IEEE ontology layer + Bloom level,
    with mastery status on each step.
    """
    user_email = _resolve_email(request, email)
    result = pipeline.store.get_learning_path(concept_name, user_email)
    return {"status": "ok", **result}


# ─── Bloom's Taxonomy summary ───

@app.get("/api/knowledge-graph/bloom-summary")
async def bloom_summary(request: Request, email: Optional[str] = None):
    """
    Return Bloom's Taxonomy distribution for the user's knowledge graph.
    Indicates cognitive depth coverage (Remember → Create) and recommends
    the next Bloom level to target.
    """
    user_email = _resolve_email(request, email)
    result = pipeline.store.get_bloom_summary(user_email)
    return {"status": "ok", **result}


# ─── Bulk mastery update ───

@app.post("/api/knowledge-graph/mastery/bulk")
async def bulk_update_mastery(
    request: Request,
    email: Optional[str] = Form(None),
):
    """
    Bulk-update mastery scores.  POST body (form or JSON) must include:
      email       : user email
      updates     : JSON array of {"name": "...", "mastery": 0.0–1.0}
    """
    user_email = _resolve_email(request, email)
    body = await request.json()
    updates = body.get("updates", [])
    if not isinstance(updates, list):
        raise HTTPException(status_code=400, detail="'updates' must be a JSON array")

    results = []
    for item in updates:
        name    = item.get("name", "")
        mastery = item.get("mastery")
        if not name or mastery is None:
            continue
        mastery = max(0.0, min(1.0, float(mastery)))
        ok = pipeline.store.update_mastery(name, user_email, mastery)
        results.append({"name": name, "mastery": mastery, "updated": ok})

    return {"status": "ok", "results": results, "updated_count": sum(1 for r in results if r["updated"])}


# ─── Wikipedia Concept Expansion (Paper §4.4) ───

@app.post("/api/knowledge-graph/expand/wikipedia")
async def expand_wikipedia(
    request: Request,
    email: Optional[str] = Form(None),
    source_document: Optional[str] = Form(""),
    max_categories: int = Form(3),
    max_related: int = Form(3),
    top_n_source: int = Form(8),
):
    """
    Paper §4.4 — Expand the existing Knowledge Graph with Wikipedia-sourced concepts.

    For each of the top-weighted concepts already in the graph:
      • Category-based expansion: adds Wikipedia parent categories as L1 Topic nodes
        connected with BELONGS_TO edges.
      • Related-concept expansion: adds Wikipedia-linked pages as L3 Concept nodes
        connected with RELATED_TO edges.

    Parameters
    ----------
    source_document : optional — restrict to one document's concepts (default = all)
    max_categories  : max Wikipedia categories to add per concept (default 3)
    max_related     : max related Wikipedia articles to add per concept (default 3)
    top_n_source    : how many of the highest-weighted concepts to expand (default 8)
    """
    user_email = _resolve_email(request, email)
    result = pipeline.expand_with_wikipedia(
        user_email,
        source_document=source_document or "",
        max_categories=max_categories,
        max_related=max_related,
        top_n_source=top_n_source,
    )
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
