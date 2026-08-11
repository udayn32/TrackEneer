"""Study module backed by Neo4j for subjects and notes management."""

import os
import shutil
import uuid
import glob
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from db import get_driver
from graph_helpers import ensure_user_and_day, normalize_day
from nsga2_scheduler import generate_study_schedule, clean_paper_name
from ai_client import build_text_model

try:
    from weaviate_service import get_weaviate_service
except ImportError:
    def get_weaviate_service():
        raise RuntimeError("Weaviate service not available")

# ══════════════════════════════════════════════════════════════
# EDUKГ ENGINE — inlined from knowledge_graph.py
# ══════════════════════════════════════════════════════════════
import sys, io as _io
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import json, re, time, logging
import numpy as np
from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

try:
    _gemini_model = build_text_model()
    if not _gemini_model:
        raise ValueError("No AI model configured")
    HAS_GEMINI = True
except Exception:
    HAS_GEMINI = False
    _gemini_model = None

try:
    from transformers import AutoTokenizer, AutoModel
    import torch
    HAS_TRANSFORMERS = True
    _minilm_tokenizer = None
    _minilm_model = None
except ImportError:
    HAS_TRANSFORMERS = False

try:
    import pdfplumber as _pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import fitz
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

_embed_model = None
def _get_embed_model():
    global _embed_model
    if _embed_model is None and HAS_SBERT:
        try:
            _embed_model = SentenceTransformer(os.getenv("EMBED_MODEL", "./all-MiniLM-L6-v2"))
        except Exception as e:
            print(f"[WARN] Could not load embed model: {e}")
    return _embed_model


@dataclass
class Concept:
    id: str = ""
    name: str = ""
    description: str = ""
    category: str = ""
    difficulty: str = "medium"
    bloom_level: str = "understand"
    source_document: str = ""
    source_page: int = 0
    layer: int = 2
    weight: float = 0.0
    wikipedia_url: str = ""
    embedding: Optional[List[float]] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id or str(uuid.uuid4()),
            "name": self.name, "description": self.description,
            "category": self.category, "difficulty": self.difficulty,
            "bloom_level": self.bloom_level, "source_document": self.source_document,
            "source_page": self.source_page, "layer": self.layer,
            "weight": round(self.weight, 4), "wikipedia_url": self.wikipedia_url,
        }

@dataclass
class Relation:
    source_id: str = ""
    target_id: str = ""
    relation_type: str = "related_to"
    confidence: float = 0.8
    source: str = "auto"

    def to_dict(self) -> dict:
        return {"source_id": self.source_id, "target_id": self.target_id,
                "relation_type": self.relation_type, "confidence": self.confidence,
                "source": self.source}


class ConceptExtractor:
    BLOOM_KEYWORDS = {
        "remember": ["define","list","recall","identify","name","state"],
        "understand": ["describe","explain","summarize","interpret","classify"],
        "apply": ["implement","solve","use","demonstrate","calculate"],
        "analyze": ["compare","contrast","examine","differentiate","analyse"],
        "evaluate": ["assess","evaluate","justify","critique","judge"],
        "create": ["design","construct","develop","formulate","compose"],
    }
    DIFFICULTY_SIGNALS = {
        "easy": ["basic","introduction","fundamental","overview","simple"],
        "medium": ["intermediate","standard","typical","common"],
        "hard": ["advanced","complex","optimization","proof","theorem"],
    }
    _STOPWORD_PHRASES = {
        "the","a","an","this","that","these","those","it","its","such","other",
        "various","following","several","many","some","also","use","using","used",
        "may","can","will","etc","e.g","i.e","fig","figure","table","page",
        "chapter","section","example","note","see","given","based","what","which",
        "who","whom","whose","where","when","why","how","he","she","they","we",
        "you","me","him","her","them","us","each","every","all","both","few",
        "more","most","any","no","not","only","very","just","even","well","back",
        "still","new","old","good","bad","first","last","next","same","time",
        "year","way","day","part","place","case","point","number","hand","end",
        "set","order","level","side","work","result","form","type","kind","area",
        "fact","need","name","thing","line","term","however","therefore",
    }
    _JUNK_PATTERNS = re.compile(
        r"^(the |a |an |this |that |these |those |its |their |our |his |her )",
        re.IGNORECASE,
    )

    def __init__(self):
        self.embed = _get_embed_model()
        self._init_minilm()

    def _init_minilm(self):
        global _minilm_tokenizer, _minilm_model
        if HAS_TRANSFORMERS and _minilm_model is None:
            try:
                model_path = os.getenv("EMBED_MODEL", "./all-MiniLM-L6-v2")
                mn = model_path if os.path.isdir(model_path) else "sentence-transformers/all-MiniLM-L6-v2"
                _minilm_tokenizer = AutoTokenizer.from_pretrained(mn)
                _minilm_model = AutoModel.from_pretrained(mn)
                logger.info("✓ MiniLM-L6-v2 initialized")
            except Exception as e:
                logger.error(f"✗ Failed to initialize MiniLM: {e}")

    def _generate_candidates_with_gemini(self, text: str, source_doc: str = "") -> List[str]:
        if not HAS_GEMINI or not _gemini_model:
            return []
        prompt = (
            "You are an expert educational-content analyst.\n"
            "Extract ALL key academic / technical concepts from the text below.\n\n"
            "Rules:\n"
            "- Return ONLY a JSON array of strings, e.g. [\"Machine Learning\", \"Neural Network\"]\n"
            "- Each string must be a SHORT concept name (1-4 words max).\n"
            "- Include: main topics, sub-topics, specific methods, algorithms,\n"
            "  technologies, named theories, types/categories mentioned.\n"
            "- Extract EVERY concept mentioned, even if only once.\n"
            "- Use standard names: \"Artificial Intelligence\" not \"AI systems\".\n"
            "- Do NOT include generic phrases or sentence fragments.\n"
            "- Aim for 20-50 concepts depending on document length.\n\n"
            f"--- TEXT ---\n{text[:6000]}\n--- END ---\n\nJSON array:"
        )
        try:
            raw = _gemini_model.generate_content(prompt).text.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"```\s*$", "", raw)
            raw = re.sub(r',\s*(\])', r'\1', raw)
            names = json.loads(raw)
            if isinstance(names, list):
                return [n.strip() for n in names if isinstance(n, str) and 2 < len(n.strip()) <= 80]
        except Exception as e:
            logger.warning(f"Gemini candidate generation failed: {e}")
        return []

    def _compute_word_frequencies(self, text: str) -> Dict[str, float]:
        words = re.findall(r'\b[a-z]+\b', text.lower())
        total = len(words) or 1
        freq: Dict[str, int] = {}
        for w in words:
            freq[w] = freq.get(w, 0) + 1
        return {w: c / total for w, c in freq.items()}

    def _sif_weight(self, word: str, word_freq: Dict[str, float], a: float = 1e-3) -> float:
        return a / (a + word_freq.get(word.lower(), 1e-5))

    def _embed_document_chunked(self, text: str, word_freq: Dict[str, float],
                                 chunk_size: int = 450, overlap: int = 100) -> np.ndarray:
        tokens = text.split()
        chunks, i = [], 0
        while i < len(tokens):
            chunks.append(" ".join(tokens[i:i + chunk_size]))
            i += chunk_size - overlap
        if not chunks:
            chunks = [text[:512]]
        chunk_embeddings = []
        for chunk in chunks:
            inputs = _minilm_tokenizer(chunk, return_tensors="pt", truncation=True, max_length=512, padding=True)
            with torch.no_grad():
                outputs = _minilm_model(**inputs)
                te = outputs.last_hidden_state[0]
            decoded = _minilm_tokenizer.convert_ids_to_tokens(inputs["input_ids"][0])
            weights = np.array([self._sif_weight(t.replace("##", "").lower(), word_freq)
                                 if t not in ("[PAD]","[CLS]","[SEP]","") else 0.0 for t in decoded], dtype=np.float32)
            ws = weights.sum() or 1.0
            chunk_embeddings.append((te.numpy().T * weights).T.sum(axis=0) / ws)
        return np.mean(chunk_embeddings, axis=0)

    def _embed_candidates_sif(self, candidates: List[str], word_freq: Dict[str, float]) -> np.ndarray:
        all_embs = []
        for batch_start in range(0, len(candidates), 32):
            batch = candidates[batch_start:batch_start + 32]
            inputs = _minilm_tokenizer(batch, return_tensors="pt", truncation=True, max_length=64, padding=True)
            with torch.no_grad():
                outputs = _minilm_model(**inputs)
            for idx in range(len(batch)):
                te = outputs.last_hidden_state[idx]
                decoded = _minilm_tokenizer.convert_ids_to_tokens(inputs["input_ids"][idx])
                weights = np.array([self._sif_weight(t.replace("##","").lower(), word_freq)
                                     if t not in ("[PAD]","[CLS]","[SEP]","") else 0.0 for t in decoded], dtype=np.float32)
                ws = weights.sum() or 1.0
                all_embs.append((te.numpy().T * weights).T.sum(axis=0) / ws)
        return np.array(all_embs)

    def _remove_principal_component(self, embeddings: np.ndarray) -> np.ndarray:
        if len(embeddings) < 2:
            return embeddings
        centered = embeddings - np.mean(embeddings, axis=0)
        try:
            _, _, Vt = np.linalg.svd(centered, full_matrices=False)
            pc = Vt[0]
            return embeddings - np.outer(centered @ pc, pc)
        except Exception:
            return embeddings

    def _fuzzy_dedup(self, items: List[Tuple[str, float, int]], threshold: float = 0.85) -> List[Tuple[str, float, int]]:
        items = sorted(items, key=lambda x: (-x[1], len(x[0])))
        deduped, seen_lower = [], []
        for name, score, idx in items:
            nl = name.lower().strip()
            is_dup = False
            for ex in seen_lower:
                shorter, longer = min(len(nl), len(ex)), max(len(nl), len(ex))
                if shorter == 0:
                    continue
                if nl in ex:
                    if len(nl) < len(ex) * 0.7:
                        continue
                    is_dup = True; break
                if ex in nl:
                    if len(ex.split()) == 1 and len(nl.split()) >= 2:
                        continue
                    is_dup = True; break
                if sum(1 for a, b in zip(nl, ex) if a == b) / longer > threshold:
                    is_dup = True; break
            if not is_dup:
                deduped.append((name, score, idx))
                seen_lower.append(nl)
        return deduped

    def _build_sentence_index(self, text: str) -> List[str]:
        return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text[:20000]) if len(s.strip()) > 10]

    def _find_context_sentence(self, concept_name: str, sentences: List[str], source_doc: str) -> str:
        nl = concept_name.lower()
        for sent in sentences:
            if nl in sent.lower():
                clean = sent.strip()[:200]
                if len(clean) > 20:
                    return clean
        return f"Concept extracted from {source_doc}" if source_doc else ""

    def _infer_category(self, name: str, score: float, text: str) -> str:
        nl, tl = name.lower(), text[:5000].lower()
        if re.search(rf"(?:module|unit|chapter)\s*\d*[:\-–]\s*{re.escape(nl)}", tl): return "topic"
        if re.search(rf"(?:theorem|lemma)[:\-–]?\s*{re.escape(nl)}", tl): return "theorem"
        if re.search(rf"(?:algorithm|procedure)[:\-–]?\s*{re.escape(nl)}", tl): return "algorithm"
        if re.search(rf"(?:definition|define)[:\-–]?\s*{re.escape(nl)}", tl): return "definition"
        if re.search(rf"(?:formula|equation)[:\-–]?\s*{re.escape(nl)}", tl): return "formula"
        if score > 0.5: return "topic"
        if score > 0.3: return "subtopic"
        return "skill"

    def _infer_layer(self, name: str, score: float, text: str, position_ratio: float = 0.5) -> int:
        tl = text[:3000].lower()
        if re.search(rf"(?:module|unit|chapter)\s*\d*[:\-–]\s*{re.escape(name.lower())}", tl): return 1
        if score > 0.6: return 1
        if score > 0.35 or position_ratio < 0.3: return 2
        return 3

    def _infer_difficulty(self, concept_name: str, context: str = "") -> str:
        tl = (concept_name + " " + context[:500]).lower()
        for diff, kws in self.DIFFICULTY_SIGNALS.items():
            if any(kw in tl for kw in kws): return diff
        return "medium"

    def _infer_bloom_level(self, text: str) -> str:
        tl = text[:1000].lower()
        for level, kws in self.BLOOM_KEYWORDS.items():
            if any(kw in tl for kw in kws): return level
        return "understand"

    def _infer_bloom_for_concept(self, name: str, context_sentence: str) -> str:
        combined = (name + " " + context_sentence).lower()
        for level in ["create","evaluate","analyze","apply","understand","remember"]:
            if any(kw in combined for kw in self.BLOOM_KEYWORDS[level]): return level
        return "understand"

    def _is_noise(self, phrase: str) -> bool:
        pl, words = phrase.lower().strip(), phrase.lower().strip().split()
        if not words or len(words) > 4: return True
        if '\n' in phrase or '–' in phrase or '—' in phrase: return True
        if set(words).issubset(self._STOPWORD_PHRASES): return True
        if len(words) == 1 and (pl in self._STOPWORD_PHRASES or len(pl) < 4): return True
        if re.match(r'^[\d\s.,%/+\-]+$', phrase): return True
        return False

    def _extract_candidate_phrases_refined(self, text: str) -> List[str]:
        candidates, seen_lower = [], set()
        def _add(name: str) -> bool:
            name = re.sub(r'\s+', ' ', name).strip()
            if len(name) < 3 or len(name) > 80: return False
            key = name.lower()
            if key in seen_lower or self._is_noise(name): return False
            seen_lower.add(key); candidates.append(name); return True
        if HAS_SPACY and _nlp:
            doc = _nlp(text[:50000])
            for h in re.findall(r"(?:Module|Unit|Chapter|Topic|Section)\s*[\d.:]*\s*[:\-–]?\s*(.+)", text, re.IGNORECASE):
                _add(h.strip().rstrip("."))
            for ent in doc.ents: _add(ent.text.strip())
            for chunk in doc.noun_chunks:
                phrase = self._JUNK_PATTERNS.sub("", chunk.text).strip()
                words = phrase.split()
                if len(words) >= 2 or (len(words) == 1 and phrase[0:1].isupper()): _add(phrase)
            for m in re.finditer(r'\b([A-Z][a-z]+(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,6})){1,3})\b|\b([A-Z]{2,6})\b', text):
                _add((m.group(1) or m.group(2)).strip())
        else:
            for w in re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', text): _add(w)
        return candidates[:200]

    def _discover_relations_refined(self, concepts: List[Concept], embeddings: np.ndarray, text: str) -> List[Relation]:
        relations, existing_pairs = [], set()
        if len(embeddings) < 2: return relations
        tl = text[:30000].lower()
        for i in range(len(embeddings)):
            for j in range(i + 1, len(embeddings)):
                n1, n2 = np.linalg.norm(embeddings[i]), np.linalg.norm(embeddings[j])
                if n1 == 0 or n2 == 0: continue
                sim = float(np.dot(embeddings[i], embeddings[j]) / (n1 * n2))
                if sim < 0.55: continue
                ci, cj = concepts[i], concepts[j]
                ni, nj = ci.name.lower(), cj.name.lower()
                p_ij = bool(re.search(rf"{re.escape(ni)}.{{0,80}}(?:requires?|prerequisite|before).{{0,40}}{re.escape(nj)}", tl))
                p_ji = bool(re.search(rf"{re.escape(nj)}.{{0,80}}(?:requires?|prerequisite|before).{{0,40}}{re.escape(ni)}", tl))
                if p_ij: rel, src, tgt, conf = "PREREQUISITE_OF", ci, cj, 0.88
                elif p_ji: rel, src, tgt, conf = "PREREQUISITE_OF", cj, ci, 0.88
                elif ci.layer < cj.layer and sim > 0.58: rel, src, tgt, conf = "PART_OF", cj, ci, round(sim,3)
                elif cj.layer < ci.layer and sim > 0.58: rel, src, tgt, conf = "PART_OF", ci, cj, round(sim,3)
                elif ci.layer == cj.layer and sim > 0.62: rel, src, tgt, conf = "LEADS_TO", ci, cj, round(sim,3)
                else: rel, src, tgt, conf = "RELATED_TO", ci, cj, round(sim,3)
                pair = (src.id, tgt.id)
                if pair not in existing_pairs:
                    existing_pairs.add(pair)
                    relations.append(Relation(source_id=src.id, target_id=tgt.id, relation_type=rel, confidence=conf, source="minilm_sif"))
        same_layer: Dict[int, List[Concept]] = {}
        for c in concepts: same_layer.setdefault(c.layer, []).append(c)
        for grp in same_layer.values():
            for i in range(len(grp) - 1):
                pair = (grp[i].id, grp[i+1].id)
                if pair not in existing_pairs:
                    existing_pairs.add(pair)
                    relations.append(Relation(source_id=grp[i].id, target_id=grp[i+1].id, relation_type="PREREQUISITE_OF", confidence=0.50, source="sequence"))
        return relations

    def extract_with_llm(self, text: str, source_doc: str = "") -> Tuple[List[Concept], List[Relation]]:
        start_time = time.time()
        if not HAS_TRANSFORMERS or _minilm_model is None:
            return self.extract_with_nlp(text, source_doc)
        try:
            gemini_candidates = self._generate_candidates_with_gemini(text, source_doc)
            if gemini_candidates:
                nlp_candidates = self._extract_candidate_phrases_refined(text)
                seen_lower = {c.lower().strip() for c in gemini_candidates}
                extras = [nc for nc in nlp_candidates if nc.lower().strip() not in seen_lower
                          and not self._is_noise(nc) and len(nc.split()) >= 2
                          and all(w[0].isupper() for w in nc.split() if w)]
                merged = gemini_candidates + extras
                return self._build_concepts_from_candidates(merged, text, source_doc, start_time)
            return self._build_concepts_with_ranking(self._extract_candidate_phrases_refined(text), text, source_doc, start_time)
        except Exception as e:
            logger.error(f"MiniLM extraction failed: {e}", exc_info=True)
            return self.extract_with_nlp(text, source_doc)

    def _build_concepts_from_candidates(self, candidates: List[str], text: str, source_doc: str, start_time: float) -> Tuple[List[Concept], List[Relation]]:
        word_freq = self._compute_word_frequencies(text)
        doc_embedding = self._embed_document_chunked(text, word_freq)
        cand_embeddings = self._embed_candidates_sif(candidates, word_freq)
        all_embs = self._remove_principal_component(np.vstack([doc_embedding.reshape(1,-1), cand_embeddings]))
        doc_embedding, cand_embeddings = all_embs[0], all_embs[1:]
        norm_doc = np.linalg.norm(doc_embedding)
        tl, total_len = text.lower(), len(text.lower()) or 1
        scored = []
        for i, name in enumerate(candidates):
            nc = np.linalg.norm(cand_embeddings[i])
            cos = max(0.0, float(np.dot(doc_embedding, cand_embeddings[i]) / (norm_doc * nc + 1e-8)))
            hits = tl.count(name.lower())
            ctx = max(0.05, min(1.0, min(1.0, (hits * len(name)) / total_len * 30) + 0.10))
            denom = ctx + cos
            scored.append((name, (2.0 * ctx * cos / denom) if denom > 0 else 0.0, i))
        scored = self._fuzzy_dedup(scored)
        _GENERIC = {'types','concept','related','learning','applications','techniques','methods',
                    'approach','process','system','model','data','result','based','using'}
        scored = [(n,s,i) for n,s,i in scored
                  if (len(n.split())>1 or n.lower().strip() not in _GENERIC)
                  and not re.match(r'^(\w+)\s+\1$', n, re.IGNORECASE)]
        sentence_map = self._build_sentence_index(text)
        concepts = []
        for name, score, emb_idx in scored:
            desc = self._find_context_sentence(name, sentence_map, source_doc)
            pos = tl.find(name.lower())
            pr = pos / len(text) if pos >= 0 and len(text) > 0 else 0.5
            dn = name.strip()
            if dn.islower(): dn = dn.title()
            concepts.append(Concept(
                id=str(uuid.uuid4()), name=dn, description=desc,
                category=self._infer_category(name, score, text),
                difficulty=self._infer_difficulty(name, text),
                bloom_level=self._infer_bloom_for_concept(name, desc),
                source_document=source_doc,
                layer=self._infer_layer(name, score, text, pr),
                weight=score,
            ))
        sel_embs = np.array([cand_embeddings[idx] for _, _, idx in scored]) if scored else np.array([])
        relations = self._discover_relations_refined(concepts, sel_embs, text) if len(sel_embs) >= 2 else []
        logger.info(f"Extracted {len(concepts)} concepts, {len(relations)} relations from '{source_doc}' in {time.time()-start_time:.2f}s")
        return concepts, relations

    def _build_concepts_with_ranking(self, candidates: List[str], text: str, source_doc: str, start_time: float) -> Tuple[List[Concept], List[Relation]]:
        if not candidates: return self.extract_with_nlp(text, source_doc)
        word_freq = self._compute_word_frequencies(text)
        doc_embedding = self._embed_document_chunked(text, word_freq)
        cand_embeddings = self._embed_candidates_sif(candidates, word_freq)
        all_embs = self._remove_principal_component(np.vstack([doc_embedding.reshape(1,-1), cand_embeddings]))
        doc_embedding, cand_embeddings = all_embs[0], all_embs[1:]
        norm_doc = np.linalg.norm(doc_embedding)
        tl = text.lower()
        scored = []
        for i, name in enumerate(candidates):
            nc = np.linalg.norm(cand_embeddings[i])
            cos = max(0.0, float(np.dot(doc_embedding, cand_embeddings[i]) / (norm_doc * nc + 1e-8))) if norm_doc and nc else 0.0
            scored.append((name, cos, i))
        scored.sort(key=lambda x: x[1], reverse=True)
        scored = self._fuzzy_dedup(scored[:30])
        scored = [(n,s,i) for n,s,i in scored if s >= 0.15]
        sentence_map = self._build_sentence_index(text)
        concepts = []
        for name, score, emb_idx in scored:
            desc = self._find_context_sentence(name, sentence_map, source_doc)
            pos = tl.find(name.lower())
            pr = pos / len(text) if pos >= 0 and len(text) > 0 else 0.5
            dn = name.strip()
            if dn.islower(): dn = dn.title()
            concepts.append(Concept(
                id=str(uuid.uuid4()), name=dn, description=desc,
                category=self._infer_category(name, score, text),
                difficulty=self._infer_difficulty(name, text),
                bloom_level=self._infer_bloom_for_concept(name, desc),
                source_document=source_doc,
                layer=self._infer_layer(name, score, text, pr),
                weight=score,
            ))
        sel_embs = np.array([cand_embeddings[idx] for _, _, idx in scored]) if scored else np.array([])
        relations = self._discover_relations_refined(concepts, sel_embs, text) if len(sel_embs) >= 2 else []
        return concepts, relations

    def extract_with_nlp(self, text: str, source_doc: str = "") -> Tuple[List[Concept], List[Relation]]:
        concepts, seen = [], set()
        if HAS_SPACY and _nlp:
            doc = _nlp(text[:50000])
            for ent in doc.ents:
                name = ent.text.strip()
                if len(name) > 2 and name.lower() not in seen:
                    seen.add(name.lower())
                    concepts.append(Concept(id=str(uuid.uuid4()), name=name,
                        description=f"Entity: {ent.label_}", category="topic",
                        difficulty=self._infer_difficulty(name, text),
                        bloom_level=self._infer_bloom_level(text), source_document=source_doc))
        for h in re.findall(r"(?:Module|Unit|Chapter|Topic|Section)\s*[\d.:]*\s*[:\-–]?\s*(.+)", text, re.IGNORECASE):
            name = h.strip().rstrip(".")
            if len(name) > 2 and name.lower() not in seen:
                seen.add(name.lower())
                concepts.append(Concept(id=str(uuid.uuid4()), name=name, category="topic",
                    difficulty=self._infer_difficulty(name, text), source_document=source_doc))
        concepts = concepts[:25]
        relations = [Relation(source_id=concepts[i].id, target_id=concepts[i+1].id,
                               relation_type="prerequisite_of", confidence=0.5, source="heuristic")
                     for i in range(len(concepts)-1)]
        return concepts, relations

    def extract_with_embeddings(self, text: str, source_doc: str = "", top_k: int = 25) -> Tuple[List[Concept], List[Relation]]:
        if not self.embed: return self.extract_with_nlp(text, source_doc)
        candidates = self._extract_candidate_phrases_refined(text)
        if not candidates: return self.extract_with_nlp(text, source_doc)
        doc_emb = self.embed.encode([text[:2000]])[0]
        cand_embs = self.embed.encode(candidates)
        sims = [(candidates[i], float(np.dot(doc_emb, e) / (np.linalg.norm(doc_emb)*np.linalg.norm(e)+1e-8)))
                for i, e in enumerate(cand_embs)]
        sims.sort(key=lambda x: x[1], reverse=True)
        top = [(n, s) for n, s in sims[:top_k] if s >= 0.25]
        sm = self._build_sentence_index(text)
        concepts = []
        for name, score in top:
            pos = text.lower().find(name.lower())
            pr = pos/len(text) if pos>=0 and len(text)>0 else 0.5
            concepts.append(Concept(id=str(uuid.uuid4()), name=name.title(),
                description=self._find_context_sentence(name, sm, source_doc),
                category="topic" if score>0.5 else "subtopic",
                difficulty=self._infer_difficulty(name, text),
                bloom_level=self._infer_bloom_for_concept(name,""),
                source_document=source_doc, layer=self._infer_layer(name,score,text,pr)))
        relations = []
        for i in range(len(concepts)-1):
            relations.append(Relation(source_id=concepts[i].id, target_id=concepts[i+1].id,
                                       relation_type="prerequisite_of", confidence=0.6, source="sequence"))
        return concepts, relations


class KnowledgeGraphStore:
    def __init__(self):
        self.driver = get_driver()

    def store_concepts(self, concepts: List[Concept], user_email: str) -> int:
        if not concepts: return 0
        with self.driver.session() as s:
            for c in concepts:
                s.run("""
                    MERGE (u:User {email: $email})
                    MERGE (u)-[:HAS_CONCEPT]->(c:Concept {name: $name, userEmail: $email})
                    SET c.id = coalesce(c.id, $id),
                        c.description = $description,
                        c.category = $category,
                        c.difficulty = $difficulty,
                        c.bloom_level = $bloom_level,
                        c.source_document = $source_document,
                        c.layer = $layer,
                        c.weight = $weight,
                        c.mastery = coalesce(c.mastery, 0.0),
                        c.updatedAt = datetime()
                """, email=user_email, id=c.id or str(uuid.uuid4()),
                    name=c.name, description=c.description, category=c.category,
                    difficulty=c.difficulty, bloom_level=c.bloom_level,
                    source_document=c.source_document, layer=c.layer, weight=c.weight)
        return len(concepts)

    def store_relations(self, relations: List[Relation], concepts: List[Concept], user_email: str) -> int:
        if not relations: return 0
        concept_map = {c.id: c.name for c in concepts}
        count = 0
        with self.driver.session() as s:
            for r in relations:
                sn = concept_map.get(r.source_id)
                tn = concept_map.get(r.target_id)
                if not sn or not tn: continue
                rt = r.relation_type.upper()
                if rt not in ("PREREQUISITE_OF","PART_OF","RELATED_TO","LEADS_TO"): rt = "RELATED_TO"
                try:
                    s.run(f"""
                        MATCH (a:Concept {{name: $sn, userEmail: $email}})
                        MATCH (b:Concept {{name: $tn, userEmail: $email}})
                        MERGE (a)-[r:{rt}]->(b)
                        SET r.confidence = $conf, r.source = $source, r.updatedAt = datetime()
                    """, sn=sn, tn=tn, email=user_email, conf=r.confidence, source=r.source)
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to store relation {sn}→{tn}: {e}")
        return count

    def get_full_graph(self, user_email: str) -> dict:
        with self.driver.session() as s:
            nr = s.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
                RETURN c.id AS id, c.name AS name, c.description AS description,
                       c.category AS category, c.difficulty AS difficulty,
                       c.bloom_level AS bloom_level, c.source_document AS source_document,
                       coalesce(c.layer, 2) AS layer, coalesce(c.weight, 0.0) AS weight,
                       coalesce(c.mastery, 0.0) AS mastery
            """, email=user_email)
            nodes = [dict(r) for r in nr]
            er = s.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(a:Concept)
                MATCH (a)-[r]->(b:Concept {userEmail: $email})
                WHERE type(r) IN ['PREREQUISITE_OF','PART_OF','RELATED_TO','LEADS_TO']
                RETURN a.name AS source, b.name AS target, type(r) AS relation,
                       coalesce(r.confidence, 0.8) AS confidence
            """, email=user_email)
            edges = [dict(r) for r in er]
        return {"nodes": nodes, "edges": edges}

    def get_graph_by_document(self, user_email: str, source_document: str) -> dict:
        with self.driver.session() as s:
            nr = s.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
                WHERE c.source_document = $doc
                RETURN c.id AS id, c.name AS name, c.description AS description,
                       c.category AS category, c.difficulty AS difficulty,
                       c.bloom_level AS bloom_level, c.source_document AS source_document,
                       coalesce(c.layer, 2) AS layer, coalesce(c.weight, 0.0) AS weight,
                       coalesce(c.mastery, 0.0) AS mastery
            """, email=user_email, doc=source_document)
            nodes = [dict(r) for r in nr]
            node_names = {n["name"] for n in nodes}
            er = s.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(a:Concept)
                MATCH (a)-[r]->(b:Concept {userEmail: $email})
                WHERE a.source_document = $doc AND b.source_document = $doc
                  AND type(r) IN ['PREREQUISITE_OF','PART_OF','RELATED_TO','LEADS_TO']
                RETURN a.name AS source, b.name AS target, type(r) AS relation,
                       coalesce(r.confidence, 0.8) AS confidence
            """, email=user_email, doc=source_document)
            edges = [dict(r) for r in er]
        return {"nodes": nodes, "edges": edges}

    def get_source_documents(self, user_email: str) -> List[dict]:
        with self.driver.session() as s:
            res = s.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
                WHERE c.source_document IS NOT NULL AND c.source_document <> ''
                RETURN c.source_document AS document, count(c) AS concept_count
                ORDER BY concept_count DESC
            """, email=user_email)
            return [{"document": r["document"], "concept_count": r["concept_count"]} for r in res]

    def get_prerequisites(self, concept_name: str, user_email: str) -> List[dict]:
        with self.driver.session() as s:
            res = s.run("""
                MATCH (p:Concept {userEmail: $email})-[:PREREQUISITE_OF*1..5]->(c:Concept {name: $name, userEmail: $email})
                RETURN DISTINCT p.name AS name, p.category AS category,
                       p.difficulty AS difficulty, coalesce(p.mastery, 0) AS mastery
                ORDER BY p.name
            """, name=concept_name, email=user_email)
            return [dict(r) for r in res]

    def get_subgraph(self, concept_name: str, user_email: str, hops: int = 2) -> dict:
        with self.driver.session() as s:
            nr = s.run("""
                MATCH (center:Concept {name: $name, userEmail: $email})
                OPTIONAL MATCH (center)-[*1..2]-(neighbor:Concept {userEmail: $email})
                WITH collect(DISTINCT center) + collect(DISTINCT neighbor) AS all_nodes
                UNWIND all_nodes AS n
                RETURN DISTINCT n.id AS id, n.name AS name, n.category AS category,
                       n.difficulty AS difficulty, coalesce(n.mastery, 0) AS mastery,
                       coalesce(n.layer, 2) AS layer
            """, name=concept_name, email=user_email)
            nodes = [dict(r) for r in nr]
            node_names = {n["name"] for n in nodes}
            er = s.run("""
                MATCH (a:Concept {userEmail: $email})-[r]->(b:Concept {userEmail: $email})
                WHERE a.name IN $names AND b.name IN $names
                  AND type(r) IN ['PREREQUISITE_OF','PART_OF','RELATED_TO','LEADS_TO']
                RETURN a.name AS source, b.name AS target, type(r) AS relation
            """, email=user_email, names=list(node_names))
            edges = [dict(r) for r in er]
        return {"nodes": nodes, "edges": edges}

    def get_weak_concepts(self, user_email: str, threshold: float = 0.5) -> List[dict]:
        with self.driver.session() as s:
            res = s.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
                WHERE coalesce(c.mastery, 0) < $threshold
                RETURN c.name AS name, coalesce(c.mastery, 0) AS mastery,
                       c.category AS category, c.difficulty AS difficulty,
                       coalesce(c.layer, 2) AS layer
                ORDER BY mastery ASC
            """, email=user_email, threshold=threshold)
            return [dict(r) for r in res]

    def root_cause_analysis(self, concept_name: str, user_email: str) -> dict:
        with self.driver.session() as s:
            tr = s.run("MATCH (c:Concept {name: $name, userEmail: $email}) RETURN c",
                       name=concept_name, email=user_email).single()
            if not tr:
                return {"message": f"Concept '{concept_name}' not found.", "root_cause": None}
            target = dict(tr["c"])
            mastery = target.get("mastery", 0) or 0
            if mastery >= 0.7:
                return {"message": f"'{concept_name}' is already well-mastered ({mastery:.0%}). Keep it up!", "root_cause": None}
            pr = s.run("""
                MATCH (p:Concept {userEmail: $email})-[:PREREQUISITE_OF*1..5]->(c:Concept {name: $name, userEmail: $email})
                WHERE coalesce(p.mastery, 0) < 0.5
                RETURN p.name AS name, coalesce(p.mastery, 0) AS mastery, p.difficulty AS difficulty
                ORDER BY mastery ASC LIMIT 1
            """, name=concept_name, email=user_email).single()
            if pr:
                return {"message": f"Root cause: '{pr['name']}' is weak (mastery: {pr['mastery']:.0%}). Fix this first to unlock '{concept_name}'.",
                        "root_cause": dict(pr)}
            return {"message": f"'{concept_name}' has no unmastered prerequisites. Focus on practising this concept directly.", "root_cause": None}

    def update_mastery(self, concept_name: str, user_email: str, mastery: float) -> bool:
        with self.driver.session() as s:
            res = s.run("""
                MATCH (c:Concept {name: $name, userEmail: $email})
                SET c.mastery = $mastery, c.updatedAt = datetime()
                RETURN c
            """, name=concept_name, email=user_email, mastery=mastery)
            return res.single() is not None

    def delete_graph(self, user_email: str) -> int:
        with self.driver.session() as s:
            res = s.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
                DETACH DELETE c
                RETURN count(c) AS deleted
            """, email=user_email)
            row = res.single()
            return row["deleted"] if row else 0

    def get_gap_analysis(self, user_email: str, mastery_threshold: float = 0.7) -> dict:
        with self.driver.session() as s:
            lr = s.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
                WITH coalesce(c.layer,2) AS layer, count(c) AS total,
                     avg(coalesce(c.mastery,0)) AS avg_mastery,
                     count(CASE WHEN coalesce(c.mastery,0) >= $threshold THEN 1 END) AS mastered
                RETURN layer, total, round(avg_mastery*100,1) AS avg_mastery_pct, mastered,
                       round(toFloat(mastered)/total*100,1) AS coverage_pct ORDER BY layer
            """, email=user_email, threshold=mastery_threshold)
            layer_coverage = [dict(r) for r in lr]
            cr = s.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
                WHERE coalesce(c.mastery,0) < $threshold
                OPTIONAL MATCH (c)-[:PREREQUISITE_OF]->(dep:Concept {userEmail: $email})
                WITH c, count(dep) AS blocking_count WHERE blocking_count > 0
                RETURN c.name AS name, round(coalesce(c.mastery,0)*100,1) AS mastery_pct,
                       c.difficulty AS difficulty, c.bloom_level AS bloom_level,
                       coalesce(c.layer,2) AS layer, blocking_count
                ORDER BY blocking_count DESC, mastery_pct ASC LIMIT 10
            """, email=user_email, threshold=mastery_threshold)
            critical_gaps = [dict(r) for r in cr]
            tr = s.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
                RETURN count(c) AS total, count(CASE WHEN coalesce(c.mastery,0) >= $threshold THEN 1 END) AS mastered
            """, email=user_email, threshold=mastery_threshold).single() or {}
            tc, tm = tr.get("total", 0), tr.get("mastered", 0)
        return {"summary": {"total_concepts": tc, "mastered_concepts": tm, "gap_count": tc-tm,
                            "overall_coverage_pct": round(tm/tc*100,1) if tc else 0,
                            "mastery_threshold": mastery_threshold},
                "layer_coverage": layer_coverage, "critical_gaps": critical_gaps}

    def get_learning_path(self, concept_name: str, user_email: str) -> dict:
        with self.driver.session() as s:
            tr = s.run("MATCH (c:Concept {name: $name, userEmail: $email}) RETURN c",
                       name=concept_name, email=user_email).single()
            if not tr:
                return {"error": f"Concept '{concept_name}' not found", "target": concept_name, "learning_path": []}
            target_row = dict(tr["c"])
            pr = s.run("""
                MATCH path = (prereq:Concept)-[:PREREQUISITE_OF|PART_OF*1..8]->(target:Concept {name: $name, userEmail: $email})
                WHERE prereq.userEmail = $email
                UNWIND nodes(path) AS n WITH DISTINCT n
                RETURN n.name AS name, coalesce(n.mastery,0) AS mastery, n.difficulty AS difficulty,
                       n.bloom_level AS bloom_level, coalesce(n.layer,2) AS layer, n.description AS description
                ORDER BY coalesce(n.layer,2) ASC, coalesce(n.mastery,0) DESC
            """, name=concept_name, email=user_email)
            steps = [dict(r) for r in pr]
            if not any(s["name"] == concept_name for s in steps):
                steps.append(target_row)
            bloom_order = ["remember","understand","apply","analyze","evaluate","create"]
            steps_sorted = sorted(steps, key=lambda s: (s.get("layer",2),
                bloom_order.index(s.get("bloom_level","understand")) if s.get("bloom_level") in bloom_order else 1))
            unmastered = [s for s in steps_sorted if s["mastery"] < 0.7]
            mastered = [s for s in steps_sorted if s["mastery"] >= 0.7]
            return {"target": concept_name, "total_steps": len(steps_sorted),
                    "mastered_count": len(mastered), "unmastered_count": len(unmastered),
                    "completion_pct": round(len(mastered)/len(steps_sorted)*100,1) if steps_sorted else 0,
                    "learning_path": steps_sorted, "next_recommended": unmastered[0] if unmastered else None}


class EduKGPipeline:
    def __init__(self):
        self.extractor = ConceptExtractor()
        self.store = KnowledgeGraphStore()

    def _preprocess_text(self, text: str) -> str:
        if not text: return ""
        text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text)
        lines = text.split('\n')
        merged = []
        for line in lines:
            stripped = line.strip()
            if not stripped: merged.append(''); continue
            if (merged and merged[-1]
                    and not merged[-1].endswith((':', '.', '!', '?'))
                    and not re.match(r'^(?:Module|Unit|Chapter|Section|Topic|\d+\.\s)', stripped, re.IGNORECASE)
                    and not re.match(r'^[●•\-\*]', stripped)):
                merged[-1] = merged[-1].rstrip() + ' ' + stripped
            else:
                merged.append(stripped)
        text = '\n'.join(merged)
        text = re.sub(r'http[s]?://\S+', '', text)
        text = re.sub(r'\S+@\S+', '', text)
        text = re.sub(r'^\d+\s*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = ''.join(c for c in text if c.isprintable() or c in '\n\t')
        return text.strip()

    def process_text(self, text: str, user_email: str, source_doc: str = "", strategy: str = "llm") -> dict:
        orig_len = len(text)
        text = self._preprocess_text(text)
        if strategy == "llm":
            concepts, relations = self.extractor.extract_with_llm(text, source_doc)
        elif strategy == "embedding":
            concepts, relations = self.extractor.extract_with_embeddings(text, source_doc)
        else:
            concepts, relations = self.extractor.extract_with_nlp(text, source_doc)
            
        # Hard limit of 15 concepts per document to prevent cluttered graphs
        MAX_CONCEPTS_PER_DOC = 15
        if len(concepts) > MAX_CONCEPTS_PER_DOC:
            concepts = sorted(concepts, key=lambda c: getattr(c, 'weight', 0) or 0, reverse=True)[:MAX_CONCEPTS_PER_DOC]
            
        allowed_names = {c.name for c in concepts}
        relations = [r for r in relations if r.source in allowed_names and r.target in allowed_names]

        cc = self.store.store_concepts(concepts, user_email)
        rc = self.store.store_relations(relations, concepts, user_email)
        return {"concepts_extracted": cc, "relations_extracted": rc,
                "concepts": [c.to_dict() for c in concepts],
                "relations": [r.to_dict() for r in relations],
                "strategy_used": strategy,
                "preprocessing_stats": {"input_chars": orig_len, "output_chars": len(text)}}

    def process_pdf(self, file_path: str, user_email: str, strategy: str = "llm", original_filename: str = "") -> dict:
        text = ""
        if HAS_PDFPLUMBER:
            try:
                with _pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        pt = page.extract_text()
                        if pt: text += pt + "\n"
            except Exception as e:
                logger.warning(f"pdfplumber failed: {e}"); text = ""
        if not text.strip() and HAS_PYMUPDF:
            try:
                doc = fitz.open(file_path)
                for page in doc: text += (page.get_text("text") or "") + "\n"
                doc.close()
            except Exception as e:
                logger.warning(f"PyMuPDF failed: {e}"); text = ""
        if not text.strip():
            if not file_path.lower().endswith(".pdf"):
                try:
                    text = open(file_path, "r", encoding="utf-8", errors="ignore").read()
                except Exception:
                    return {"error": "Could not extract text"}
            else:
                return {"error": "Could not extract text from PDF"}
        source_name = original_filename or Path(file_path).name
        return self.process_text(text, user_email, source_doc=source_name, strategy=strategy)

    def enrich_with_llm(self, user_email: str) -> dict:
        if not HAS_GEMINI or not _gemini_model: return {"error": "Gemini not available"}
        graph = self.store.get_full_graph(user_email)
        names = [n["name"] for n in graph["nodes"]]
        if not names: return {"error": "No concepts to enrich"}
        prompt = f"""Given these concepts: {json.dumps(names[:50])}
For each, return JSON: {{"enrichments": [{{"name":"...","description":"...","difficulty":"...","prerequisites":[]}}]}}"""
        try:
            raw = _gemini_model.generate_content(prompt).text.strip()
            raw = re.sub(r"```json\s*", "", raw); raw = re.sub(r"```\s*$", "", raw)
            data = json.loads(raw)
            updates = 0
            with self.store.driver.session() as s:
                for e in data.get("enrichments", []):
                    name = e.get("name","")
                    if not name: continue
                    s.run("""MATCH (c:Concept {name:$name, userEmail:$email})
                              SET c.description=CASE WHEN c.description='' OR c.description IS NULL THEN $desc ELSE c.description END,
                                  c.difficulty=$diff, c.enrichedAt=datetime()""",
                           name=name, email=user_email, desc=e.get("description",""), diff=e.get("difficulty","medium"))
                    for prereq in e.get("prerequisites",[]):
                        s.run("""MATCH (p:Concept {name:$p, userEmail:$email}) MATCH (t:Concept {name:$t, userEmail:$email})
                                  MERGE (p)-[:PREREQUISITE_OF {source:'llm'}]->(t)""",
                               p=prereq, t=name, email=user_email)
                    updates += 1
            return {"enriched_concepts": updates}
        except Exception as e:
            return {"error": str(e)}


# ── Inline EduKG pipeline instance ──
_ekg_pipeline = EduKGPipeline()
HAS_EKG = True


# ══════════════════════════════════════════════════════════════
# KNOWLEDGE GRAPH API ROUTES (mounted on the same study app)
# ══════════════════════════════════════════════════════════════

def _kg_email(request: Request, provided: Optional[str] = None) -> str:
    if provided: return provided
    return request.headers.get("x-user-email", "") or DEFAULT_USER_EMAIL

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
# Use absolute path for upload folder based on server location
_SERVER_DIR = Path(__file__).parent.absolute()
UPLOAD_FOLDER = (_SERVER_DIR.parent / "uploads").absolute()
UPLOAD_FOLDER.mkdir(exist_ok=True, parents=True)

DEFAULT_USER_EMAIL = os.getenv("DEFAULT_USER_EMAIL", "demo@trackeneer.local")

# Shared AI text model for study module
model = _gemini_model

driver = get_driver()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_user_email(request: Request, provided: Optional[str] = None) -> str:
    email = provided or request.headers.get("x-user-email") or request.headers.get("X-User-Email")
    if not email:
        email = DEFAULT_USER_EMAIL
    if not email:
        raise HTTPException(status_code=400, detail="User email is required")
    return email.strip().lower()


def _serialize_subject(node, notes_count: int) -> dict:
    return {
        "id": node["id"],
        "name": node.get("name", ""),
        "description": node.get("description", ""),
        "createdAt": node.get("createdAt"),
        "dayDate": node.get("dayDate"),
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
        "dayDate": node.get("dayDate"),
        "ownerEmail": node.get("ownerEmail"),
    }


def _get_note_node(note_id: str, email: Optional[str] = None):
    with driver.session() as session:
        if email:
            record = session.run(
                """
                MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_SUBJECT]->(:Subject)-[:HAS_NOTE]->(n:Note {id: $note_id})
                RETURN n
                """,
                note_id=note_id,
                email=email,
            ).single()
        else:
            record = session.run(
                """
                MATCH (n:Note {id: $note_id})
                RETURN n
                """,
                note_id=note_id,
            ).single()
        return record["n"] if record else None


def weaviate_health_check() -> dict:
    """Check if Weaviate service is available and healthy."""
    try:
        weaviate_svc = get_weaviate_service()
        if weaviate_svc:
            return {"status": "available", "service": "weaviate"}
        else:
            return {"status": "unavailable", "service": "weaviate", "reason": "Service not initialized"}
    except Exception as e:
        return {"status": "error", "service": "weaviate", "error": str(e)}


@app.get("/")
def root():
    weaviate_status = weaviate_health_check()
    return {
        "status": "Study module is running",
        "timestamp": _now_iso(),
        "weaviate": weaviate_status
    }

@app.get("/api/subjects")
def get_subjects(request: Request, day: Optional[str] = None, email: Optional[str] = None):
    user_email = _resolve_user_email(request, email)
    day_iso = normalize_day(day)
    with driver.session() as session:
        day_iso = ensure_user_and_day(session, user_email, day=day_iso)
        results = session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(d:Day {date: date($day), email: $email})-[:HAS_SUBJECT]->(s:Subject)
            OPTIONAL MATCH (s)-[:HAS_NOTE]->(n:Note)
            RETURN s AS subject, count(n) AS notesCount
            ORDER BY subject.createdAt DESC
            """,
            email=user_email,
            day=day_iso,
        )
        subjects = [
            _serialize_subject(record["subject"], record["notesCount"])
            for record in results
        ]
    return {"subjects": subjects}


@app.post("/api/subjects")
async def create_subject(
    request: Request,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    day: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
):
    user_email = _resolve_user_email(request, email)
    subject_id = str(uuid.uuid4())
    created_at = _now_iso()
    day_iso = normalize_day(day)
    with driver.session() as session:
        day_iso = ensure_user_and_day(session, user_email, day=day_iso)
        session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(d:Day {date: date($day), email: $email})
            CREATE (d)-[:HAS_SUBJECT]->(s:Subject {
                id: $id,
                name: $name,
                description: $description,
                createdAt: $created_at,
                ownerEmail: $email,
                dayDate: $day
            })
            """,
            id=subject_id,
            name=name,
            description=description or "",
            created_at=created_at,
            email=user_email,
            day=day_iso,
        )

    subject = {
        "id": subject_id,
        "name": name,
        "description": description or "",
        "createdAt": created_at,
        "dayDate": day_iso,
        "notesCount": 0,
    }
    
    # Index in Weaviate
    try:
        weaviate_svc = get_weaviate_service()
        weaviate_svc.index_subject(
            subject_id=subject_id,
            name=name,
            description=description or "",
            owner_email=user_email,
            created_at=created_at,
        )
    except Exception as e:
        print(f"Warning: Failed to index subject in Weaviate: {e}")

    # Index in BM25
    try:
        from app import bm25_subjects
        text = f"{name} {description or ''}".strip()
        if text:
            bm25_subjects.index(subject_id, text)
    except Exception as e:
        print(f"Warning: Failed to index subject in BM25: {e}")

    return {"message": "Subject created successfully", "subject": subject}


@app.delete("/api/subjects/{subject_id}")
def delete_subject(subject_id: str, request: Request, email: Optional[str] = None):
    user_email = _resolve_user_email(request, email)
    stored_files = []
    with driver.session() as session:
        records = session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_SUBJECT]->(s:Subject {id: $id})
            OPTIONAL MATCH (s)-[:HAS_NOTE]->(n:Note)
            RETURN n.storedFilename AS storedFilename
            """,
            id=subject_id,
            email=user_email,
        )
        stored_files = [record["storedFilename"] for record in records if record["storedFilename"]]

        result = session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_SUBJECT]->(s:Subject {id: $id})
            RETURN s
            """,
            id=subject_id,
            email=user_email,
        ).single()
        if not result:
            raise HTTPException(status_code=404, detail="Subject not found")

        session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_SUBJECT]->(s:Subject {id: $id})
            DETACH DELETE s
            """,
            id=subject_id,
            email=user_email,
        )

    for filename in stored_files:
        file_path = UPLOAD_FOLDER / filename
        if file_path.exists():
            file_path.unlink()
    
    # Delete from Weaviate
    try:
        weaviate_svc = get_weaviate_service()
        weaviate_svc.delete_subject(subject_id)
    except Exception as e:
        print(f"Warning: Failed to delete subject from Weaviate: {e}")

    return {"message": "Subject deleted successfully"}

@app.get("/api/notes")
def get_notes(
    request: Request,
    subject_id: Optional[str] = None,
    day: Optional[str] = None,
    email: Optional[str] = None,
):
    user_email = _resolve_user_email(request, email)
    with driver.session() as session:
        if subject_id:
            results = session.run(
                """
                MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_SUBJECT]->(s:Subject {id: $subject_id})-[:HAS_NOTE]->(n:Note)
                RETURN n
                ORDER BY n.uploadedAt DESC
                """,
                email=user_email,
                subject_id=subject_id,
            )
        else:
            day_iso = ensure_user_and_day(session, user_email, day=normalize_day(day))
            results = session.run(
                """
                MATCH (u:User {email: $email})-[:HAS_DAY]->(d:Day {date: date($day), email: $email})-[:HAS_SUBJECT]->(:Subject)-[:HAS_NOTE]->(n:Note)
                RETURN n
                ORDER BY n.uploadedAt DESC
                """,
                email=user_email,
                day=day_iso,
            )
        notes = [_serialize_note(record["n"]) for record in results]
    return {"notes": notes}


@app.post("/api/notes/upload")
async def upload_note(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    subject_id: str = Form(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
):
    user_email = _resolve_user_email(request, email)
    with driver.session() as session:
        subject_exists = session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(d:Day)-[:HAS_SUBJECT]->(s:Subject {id: $id})
            RETURN s, d
            """,
            id=subject_id,
            email=user_email,
        ).single()
        if not subject_exists:
            raise HTTPException(status_code=404, detail="Subject not found")

        day_node = subject_exists["d"]
        day_iso = normalize_day(None)
        if day_node:
            try:
                day_value = day_node["date"]
                if hasattr(day_value, "to_native"):
                    day_iso = day_value.to_native().isoformat()
                elif hasattr(day_value, "isoformat"):
                    day_iso = day_value.isoformat()
                else:
                    day_iso = normalize_day(str(day_value))
            except (KeyError, TypeError):
                pass
        ensure_user_and_day(session, user_email, day=day_iso)

    file_ext = os.path.splitext(file.filename)[1]
    note_id = str(uuid.uuid4())
    stored_filename = f"{note_id}{file_ext}"
    file_path = UPLOAD_FOLDER / stored_filename

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        print(f"[UPLOAD] File saved successfully: {file_path}")
        print(f"[UPLOAD] File exists: {file_path.exists()}")
        print(f"[UPLOAD] UPLOAD_FOLDER: {UPLOAD_FOLDER}")
    except Exception as e:
        print(f"[UPLOAD ERROR] Failed to save file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    finally:
        file.file.close()

    file_size = file_path.stat().st_size if file_path.exists() else 0
    uploaded_at = _now_iso()

    with driver.session() as session:
        session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_SUBJECT]->(s:Subject {id: $subject_id})
            CREATE (s)-[:HAS_NOTE]->(n:Note {
                id: $id,
                subjectId: $subject_id,
                title: $title,
                description: $description,
                filename: $filename,
                storedFilename: $stored_filename,
                fileType: $file_type,
                fileSize: $file_size,
                uploadedAt: $uploaded_at,
                ownerEmail: $email,
                dayDate: $day
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
            email=user_email,
            day=day_iso,
        )

    # schedule background processing: topic extraction + EduKG pipeline
    try:
        original_fname = file.filename or ""
        background_tasks.add_task(process_file_background, file_path, user_email, original_fname)
    except Exception as e:
        print(f"Warning: failed to schedule background processing for {file_path}: {e}")

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
        "dayDate": day_iso,
        "ownerEmail": user_email,
    }
    
    # Index in Weaviate
    try:
        weaviate_svc = get_weaviate_service()
        weaviate_svc.index_note(
            note_id=note_id,
            subject_id=subject_id,
            title=title or file.filename,
            description=description or "",
            file_path=file_path,
            file_type=file_ext.replace(".", "").upper(),
            filename=file.filename,
            owner_email=user_email,
            uploaded_at=uploaded_at,
        )
    except Exception as e:
        print(f"Warning: Failed to index note in Weaviate: {e}")

    # Index in BM25
    try:
        from app import bm25_notes
        text = f"{title or file.filename} {description or ''}".strip()
        if text:
            bm25_notes.index(note_id, text)
    except Exception as e:
        print(f"Warning: Failed to index note in BM25: {e}")

    return {"message": "File uploaded successfully", "note": note}


@app.post("/api/notes/upload-simple")
async def upload_note_simple(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
):
    """Simple note upload without requiring subject_id. Creates/uses 'General' subject."""
    user_email = _resolve_user_email(request, email)
    
    with driver.session() as session:
        # Ensure user exists
        ensure_user_and_day(session, user_email, day=normalize_day(None))
        
        # Find or create 'General' subject
        result = session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(d:Day)-[:HAS_SUBJECT]->(s:Subject {name: 'General'})
            RETURN s.id as id
            """,
            email=user_email,
        ).single()
        
        if result:
            subject_id = result["id"]
        else:
            # Create General subject
            subject_id = str(uuid.uuid4())
            day_result = session.run(
                """
                MATCH (u:User {email: $email})-[:HAS_DAY]->(d:Day)
                RETURN d
                LIMIT 1
                """,
                email=user_email,
            ).single()
            
            if day_result:
                day_node = day_result["d"]
                session.run(
                    """
                    MATCH (d:Day) WHERE elementId(d) = $day_elem_id
                    CREATE (d)-[:HAS_SUBJECT]->(s:Subject {
                        id: $id,
                        name: 'General',
                        description: 'General study notes'
                    })
                    """,
                    day_elem_id=day_node.element_id,
                    id=subject_id,
                )

    # Process file upload
    file_ext = os.path.splitext(file.filename)[1]
    note_id = str(uuid.uuid4())
    stored_filename = f"{note_id}{file_ext}"
    file_path = UPLOAD_FOLDER / stored_filename

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        print(f"[UPLOAD] File saved successfully: {file_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File save failed: {str(e)}")

    # Get file info
    file_size = file_path.stat().st_size if file_path.exists() else 0
    uploaded_at = datetime.now().isoformat()
    day_iso = normalize_day(None)

    # Create Note node in Neo4j
    with driver.session() as session:
        session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(d:Day)-[:HAS_SUBJECT]->(s:Subject {id: $subject_id})
            CREATE (s)-[:HAS_NOTE]->(n:Note {
                id: $id,
                title: $title,
                description: $description,
                filename: $filename,
                storedFilename: $stored_filename,
                fileType: $file_type,
                fileSize: $file_size,
                uploadedAt: $uploaded_at,
                ownerEmail: $email,
                dayDate: $day
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
            email=user_email,
            day=day_iso,
        )

    # Schedule background processing
    try:
        original_fname = file.filename or ""
        background_tasks.add_task(process_file_background, file_path, user_email, original_fname)
    except Exception as e:
        print(f"Warning: failed to schedule background processing for {file_path}: {e}")

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
        "dayDate": day_iso,
        "ownerEmail": user_email,
    }

    # Index in Weaviate
    try:
        weaviate_svc = get_weaviate_service()
        weaviate_svc.index_note(
            note_id=note_id,
            subject_id=subject_id,
            title=title or file.filename,
            description=description or "",
            file_path=file_path,
            file_type=file_ext.replace(".", "").upper(),
            filename=file.filename,
            owner_email=user_email,
            uploaded_at=uploaded_at,
        )
    except Exception as e:
        print(f"Warning: Failed to index note in Weaviate: {e}")

    # Index in BM25
    try:
        from app import bm25_notes
        text = f"{title or file.filename} {description or ''}".strip()
        if text:
            bm25_notes.index(note_id, text)
    except Exception as e:
        print(f"Warning: Failed to index note in BM25: {e}")

    return {"message": "File uploaded successfully", "note": note}


@app.get("/api/notes/{note_id}/download")
async def download_note(note_id: str, request: Request, email: Optional[str] = None):
    user_email = _resolve_user_email(request, email)
    note = _get_note_node(note_id, user_email)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found in database")

    print(f"\n[DOWNLOAD] note_id={note_id}")
    print(f"[DOWNLOAD] Note data: id={note.get('id')}, storedFilename={note.get('storedFilename')}, filename={note.get('filename')}")
    
    file_path = UPLOAD_FOLDER / note["storedFilename"]
    print(f"[DOWNLOAD] Checking path: {file_path}")
    print(f"[DOWNLOAD] Path exists: {file_path.exists()}")
    
    # If exact path doesn't exist, search for any file matching the note ID
    if not file_path.exists():
        print(f"[DOWNLOAD] Exact path not found, searching for {note_id}*")
        # Search for files that might be this note
        search_pattern = str(UPLOAD_FOLDER / f"{note_id}*")
        print(f"[DOWNLOAD] Search pattern: {search_pattern}")
        matching_files = glob.glob(search_pattern, recursive=False)
        print(f"[DOWNLOAD] Found {len(matching_files)} files in main folder")
        
        if matching_files:
            file_path = Path(matching_files[0])
            print(f"[DOWNLOAD] Using file: {file_path}")
        else:
            # Also search in subdirectories
            search_pattern_recursive = str(UPLOAD_FOLDER / f"**/{note_id}*")
            print(f"[DOWNLOAD] Recursive search pattern: {search_pattern_recursive}")
            matching_files = glob.glob(search_pattern_recursive, recursive=True)
            print(f"[DOWNLOAD] Found {len(matching_files)} files in subdirectories")
            
            if matching_files:
                file_path = Path(matching_files[0])
                print(f"[DOWNLOAD] Using file: {file_path}")
            else:
                print(f"[DOWNLOAD] NO FILES FOUND for note {note_id}")
                print(f"[DOWNLOAD] Files in UPLOAD_FOLDER: {list(UPLOAD_FOLDER.glob('*')) if UPLOAD_FOLDER.exists() else 'folder does not exist'}")
                raise HTTPException(status_code=404, detail=f"File not found. The file '{note['filename']}' may no longer exist or was removed. Use cleanup endpoint to remove broken notes.")

    print(f"[DOWNLOAD] Returning file: {file_path}")
    return FileResponse(
        path=file_path,
        filename=note["filename"],
        media_type="application/octet-stream",
    )


@app.get("/api/notes/{note_id}/preview")
async def preview_note(note_id: str, request: Request, email: Optional[str] = None):
    user_email = _resolve_user_email(request, email)
    note = _get_note_node(note_id, user_email)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found in database")

    print(f"\n[PREVIEW] note_id={note_id}")
    print(f"[PREVIEW] Note data: id={note.get('id')}, storedFilename={note.get('storedFilename')}, filename={note.get('filename')}")
    
    file_path = UPLOAD_FOLDER / note["storedFilename"]
    print(f"[PREVIEW] Checking path: {file_path}")
    print(f"[PREVIEW] Path exists: {file_path.exists()}")
    
    # If exact path doesn't exist, search for any file matching the note ID
    if not file_path.exists():
        print(f"[PREVIEW] Exact path not found, searching for {note_id}*")
        # Search for files that might be this note
        search_pattern = str(UPLOAD_FOLDER / f"{note_id}*")
        print(f"[PREVIEW] Search pattern: {search_pattern}")
        matching_files = glob.glob(search_pattern, recursive=False)
        print(f"[PREVIEW] Found {len(matching_files)} files in main folder")
        
        if matching_files:
            file_path = Path(matching_files[0])
            print(f"[PREVIEW] Using file: {file_path}")
        else:
            # Also search in subdirectories
            search_pattern_recursive = str(UPLOAD_FOLDER / f"**/{note_id}*")
            print(f"[PREVIEW] Recursive search pattern: {search_pattern_recursive}")
            matching_files = glob.glob(search_pattern_recursive, recursive=True)
            print(f"[PREVIEW] Found {len(matching_files)} files in subdirectories")
            
            if matching_files:
                file_path = Path(matching_files[0])
                print(f"[PREVIEW] Using file: {file_path}")
            else:
                print(f"[PREVIEW] NO FILES FOUND for note {note_id}")
                print(f"[PREVIEW] Files in UPLOAD_FOLDER: {list(UPLOAD_FOLDER.glob('*')) if UPLOAD_FOLDER.exists() else 'folder does not exist'}")
                raise HTTPException(status_code=404, detail=f"File not found: {note['filename']}")

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

    print(f"[PREVIEW] Returning file: {file_path} with media_type: {media_type}")
    return FileResponse(
        path=file_path,
        media_type=media_type,
        headers={"Content-Disposition": f"inline; filename={note['filename']}"},
    )


@app.delete("/api/notes/{note_id}")
def delete_note(note_id: str, request: Request, email: Optional[str] = None):
    user_email = _resolve_user_email(request, email)
    note = _get_note_node(note_id, user_email)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    with driver.session() as session:
        session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_SUBJECT]->(:Subject)-[:HAS_NOTE]->(n:Note {id: $id})
            DETACH DELETE n
            """,
            id=note_id,
            email=user_email,
        )

    file_path = UPLOAD_FOLDER / note["storedFilename"]
    if file_path.exists():
        file_path.unlink()
    
    # Delete from Weaviate
    try:
        weaviate_svc = get_weaviate_service()
        weaviate_svc.delete_note(note_id)
    except Exception as e:
        print(f"Warning: Failed to delete note from Weaviate: {e}")

    return {"message": "Note deleted successfully"}

@app.get("/api/notes/recent")
def get_recent_notes(request: Request, limit: int = 5, email: Optional[str] = None):
    user_email = _resolve_user_email(request, email)
    with driver.session() as session:
        results = session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_SUBJECT]->(:Subject)-[:HAS_NOTE]->(n:Note)
            RETURN n
            ORDER BY n.uploadedAt DESC
            LIMIT $limit
            """,
            limit=limit,
            email=user_email,
        )
        notes = [_serialize_note(record["n"]) for record in results]
    return {"notes": notes}


@app.get("/api/study/stats")
def get_study_stats(request: Request, email: Optional[str] = None):
    user_email = _resolve_user_email(request, email)
    with driver.session() as session:
        subjects_count = (
            session.run(
                """
                MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_SUBJECT]->(s:Subject)
                RETURN count(s) AS count
                """,
                email=user_email,
            ).single()["count"]
        )
        note_records = list(
            session.run(
                """
                MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_SUBJECT]->(:Subject)-[:HAS_NOTE]->(n:Note)
                RETURN coalesce(n.fileType, 'OTHER') AS type, n.fileSize AS fileSize
                """,
                email=user_email,
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


@app.get("/api/debug/files")
def debug_files(request: Request, email: Optional[str] = None):
    """Debug endpoint: shows files on disk vs notes in database"""
    user_email = _resolve_user_email(request, email)
    
    # Get files on disk
    files_on_disk = []
    if UPLOAD_FOLDER.exists():
        for file_path in UPLOAD_FOLDER.glob("**/*"):
            if file_path.is_file():
                files_on_disk.append({
                    "name": file_path.name,
                    "path": str(file_path),
                    "relative": str(file_path.relative_to(UPLOAD_FOLDER)),
                    "size": file_path.stat().st_size if file_path.exists() else 0,
                })
    
    # Get notes in database
    with driver.session() as session:
        note_results = list(session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_SUBJECT]->(:Subject)-[:HAS_NOTE]->(n:Note)
            RETURN n.id as id, n.filename as filename, n.storedFilename as storedFilename, n.fileSize as fileSize
            ORDER BY n.uploadedAt DESC
            """,
            email=user_email,
        ))
    
    notes_in_db = [dict(record) for record in note_results]
    
    return {
        "upload_folder": str(UPLOAD_FOLDER),
        "files_on_disk": files_on_disk,
        "notes_in_database": notes_in_db,
        "total_files": len(files_on_disk),
        "total_notes": len(notes_in_db),
    }


@app.post("/api/notes/cleanup-orphaned")
def cleanup_orphaned_notes(request: Request, email: Optional[str] = None):
    """Remove notes that don't have corresponding files on disk"""
    user_email = _resolve_user_email(request, email)
    
    with driver.session() as session:
        # Get all notes for the user
        note_results = list(session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_SUBJECT]->(:Subject)-[:HAS_NOTE]->(n:Note)
            RETURN n.id as id, n.storedFilename as storedFilename
            """,
            email=user_email,
        ))
    
    # Find orphaned notes (where file doesn't exist)
    orphaned = []
    valid = []
    
    for record in note_results:
        note_id = record["id"]
        stored_filename = record["storedFilename"]
        file_path = UPLOAD_FOLDER / stored_filename
        
        # Also check with glob search
        if not file_path.exists():
            search_pattern = str(UPLOAD_FOLDER / f"{note_id}*")
            matching = glob.glob(search_pattern, recursive=False)
            if not matching:
                matching = glob.glob(str(UPLOAD_FOLDER / f"**/{note_id}*"), recursive=True)
            
            if not matching:
                orphaned.append(note_id)
            else:
                valid.append(note_id)
        else:
            valid.append(note_id)
    
    # Delete orphaned notes
    deleted_count = 0
    if orphaned:
        with driver.session() as session:
            for note_id in orphaned:
                result = session.run(
                    """
                    MATCH (u:User {email: $email})-[:HAS_DAY]->(:Day)-[:HAS_SUBJECT]->(:Subject)-[:HAS_NOTE]->(n:Note {id: $id})
                    DETACH DELETE n
                    """,
                    id=note_id,
                    email=user_email,
                )
                deleted_count += 1
    
    return {
        "status": "ok",
        "orphaned_notes_found": len(orphaned),
        "orphaned_notes_deleted": deleted_count,
        "valid_notes_kept": len(valid),
        "orphaned_note_ids": orphaned[:5],  # Show first 5
    }



# ---------------------------
# Notes extraction & graph
# ---------------------------
def extract_text_from_file(path: Path) -> str:
    """Try to extract text from common file types (PDF, DOCX, plain text).
    Falls back to reading bytes as latin-1 if parsing libraries aren't available.
    """
    text = ""
    try:
        if path.suffix.lower() == ".pdf":
            try:
                from PyPDF2 import PdfReader

                reader = PdfReader(str(path))
                for p in reader.pages:
                    page_text = p.extract_text()
                    if page_text:
                        text += page_text + "\n\n"
            except Exception:
                # Best-effort fallback
                with open(path, "rb") as f:
                    data = f.read()
                    try:
                        text = data.decode("utf-8")
                    except Exception:
                        text = data.decode("latin-1", errors="ignore")
        elif path.suffix.lower() in (".docx", ".doc"):
            try:
                import docx

                doc = docx.Document(str(path))
                for para in doc.paragraphs:
                    text += para.text + "\n"
            except Exception:
                with open(path, "rb") as f:
                    data = f.read()
                    try:
                        text = data.decode("utf-8")
                    except Exception:
                        text = data.decode("latin-1", errors="ignore")
        else:
            # plain text or unknown; try to read as text
            with open(path, "rb") as f:
                data = f.read()
                try:
                    text = data.decode("utf-8")
                except Exception:
                    text = data.decode("latin-1", errors="ignore")
    except Exception:
        # Last resort: return empty string
        text = ""
    return text


def call_gemini_extract(text: str) -> dict:
    """Call the configured AI text model to extract structured JSON from the notes text.
    If no AI model is configured, returns a
    very small heuristic extraction (topics/subtopics) as a fallback.
    """
    if not _gemini_model:
        # simple heuristic: split by double-newline into sections
        topics = []
        parts = [p.strip() for p in text.split("\n\n") if p.strip()]
        for i, p in enumerate(parts[:20]):
            lines = [l.strip() for l in p.splitlines() if l.strip()]
            title = lines[0][:120] if lines else f"Topic {i+1}"
            body = "\n".join(lines[1:]) if len(lines) > 1 else ""
            topics.append({"title": title, "content": body, "subtopics": []})
        return {"topics": topics}

    try:
        # Use a simple prompt asking the configured model to extract topics/subtopics/depends_on
        prompt = (
            "Extract a JSON object with keys: topics (array). Each topic should have title, "
            "subtopics (array of strings) and depends_on (array of topic titles). "
            "Return ONLY valid JSON.\n\nText:\n" + text[:60000]
        )

        response = _gemini_model.generate_content(prompt)
        # The response may contain text; try to parse JSON from it
        import re, json

        response_text = response.text or ""
        m = re.search(r"\{.*\}", response_text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return {"topics_text": response_text}
        return {"topics_text": response_text}
    except Exception:
        return {"topics": []}


def process_and_store_notes(extracted: dict, user_email: str):
    """Given the extracted JSON, store topics/subtopics and dependencies into Neo4j.
    This function is idempotent for repeated uploads of the same content.
    """
    topics = extracted.get("topics") or []
    if not topics:
        return

    with driver.session() as session:
        for t in topics:
            title = t.get("title") or t.get("name") or "Untitled"
            content = t.get("content") or ""
            # Create or merge topic node
            session.run(
                """
                MERGE (top:Topic {title: $title, ownerEmail: $email})
                SET top.content = coalesce(top.content, $content), top.updatedAt = datetime()
                """,
                title=title,
                content=content,
                email=user_email,
            )

            # handle subtopics
            for s in t.get("subtopics", []):
                session.run(
                    """
                    MATCH (top:Topic {title: $title, ownerEmail: $email})
                    MERGE (sub:Subtopic {title: $sub, ownerEmail: $email})
                    MERGE (top)-[:HAS_SUBTOPIC]->(sub)
                    """,
                    title=title,
                    sub=s,
                    email=user_email,
                )

            # handle dependencies
            for dep in t.get("depends_on", []):
                session.run(
                    """
                    MATCH (a:Topic {title: $title, ownerEmail: $email})
                    MATCH (b:Topic {title: $dep, ownerEmail: $email})
                    MERGE (a)-[:DEPENDS_ON]->(b)
                    """,
                    title=title,
                    dep=dep,
                    email=user_email,
                )


def process_file_background(path: Path, user_email: str, original_filename: str = ""):
    """Background worker: extract text from a file, call Gemini/heuristic, store topics into Neo4j.
    Also triggers the EduKG pipeline to build/update the Knowledge Graph for this document.
    This is a module-level helper so multiple endpoints can reuse the same logic.
    """
    # ── 1. Legacy topic/subtopic extraction (Neo4j Topics graph) ──
    try:
        txt = extract_text_from_file(path)
        extracted = call_gemini_extract(txt)
        process_and_store_notes(extracted, user_email)
    except Exception as e:
        import traceback
        print(f"Exception in background extraction for {path}: {e}")
        traceback.print_exc()

    # ── 2. EduKG concept extraction (Knowledge Graph) ──
    if HAS_EKG and _ekg_pipeline and str(path).lower().endswith(".pdf"):
        try:
            fname = original_filename or path.name
            print(f"[EduKG] Building knowledge graph for '{fname}' (user: {user_email})...")
            _ekg_pipeline.process_pdf(
                file_path=str(path),
                user_email=user_email,
                original_filename=fname,
            )
            print(f"[EduKG] Knowledge graph built for '{fname}'")
        except Exception as e:
            import traceback
            print(f"[EduKG] Exception building KG for {path}: {e}")
            traceback.print_exc()


@app.post("/api/notes/extract")
def notes_extract_endpoint(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    request: Request = None,
    email: Optional[str] = None,
):
    """Accept an uploaded file, store it, and enqueue background extraction + storage to Neo4j.
    Returns a job-like response (immediate)."""
    user_email = _resolve_user_email(request, email)
    uid = str(uuid.uuid4())
    stored_name = f"{uid}_{file.filename}"
    dest = UPLOAD_FOLDER / stored_name
    with open(dest, "wb") as f:
        f.write(file.file.read())

    # schedule background processing using shared helper
    try:
        background_tasks.add_task(process_file_background, dest, user_email)
    except Exception as e:
        print(f"Warning: failed to schedule background processing for {dest}: {e}")

    return {"message": "File received; extraction queued", "storedFilename": stored_name}


@app.get("/api/notes/graph")
def get_notes_graph(request: Request, email: Optional[str] = None):
    """Return a simple graph (nodes and edges) representing Topics and Subtopics for the user."""
    user_email = _resolve_user_email(request, email)
    nodes = []
    edges = []
    with driver.session() as session:
        res = session.run(
            """
            MATCH (t:Topic {ownerEmail: $email})
            OPTIONAL MATCH (t)-[:HAS_SUBTOPIC]->(s:Subtopic)
            OPTIONAL MATCH (t)-[:DEPENDS_ON]->(d:Topic)
            RETURN t, collect(DISTINCT s) AS subs, collect(DISTINCT d) AS deps
            """,
            email=user_email,
        )
        for record in res:
            t = record["t"]
            t_id = f"topic:{t['title']}"
            nodes.append({"data": {"id": t_id, "label": t["title"]}})
            for s in record["subs"]:
                if not s:
                    continue
                s_id = f"sub:{s['title']}"
                nodes.append({"data": {"id": s_id, "label": s["title"]}})
                edges.append({"data": {"source": t_id, "target": s_id, "label": "has_subtopic"}})
            for d in record["deps"]:
                if not d:
                    continue
                d_id = f"topic:{d['title']}"
                nodes.append({"data": {"id": d_id, "label": d["title"]}})
                edges.append({"data": {"source": t_id, "target": d_id, "label": "depends_on"}})

    # de-duplicate nodes
    seen = set()
    uniq_nodes = []
    for n in nodes:
        nid = n["data"]["id"]
        if nid in seen:
            continue
        seen.add(nid)
        uniq_nodes.append(n)

    return {"nodes": uniq_nodes, "edges": edges}


@app.post("/api/notes/seed")
def seed_notes_graph(request: Request, email: Optional[str] = None):
    """Create sample Topic/Subtopic nodes for the current user to verify the frontend graph UI."""
    user_email = _resolve_user_email(request, email)
    sample = [
        {"title": "Introduction to IoT", "subtopics": ["Sensors", "Actuators", "Protocols"], "depends_on": []},
        {"title": "Sensors", "subtopics": ["Temperature", "Humidity"], "depends_on": ["Introduction to IoT"]},
        {"title": "Communication Protocols", "subtopics": ["MQTT", "HTTP"], "depends_on": ["Introduction to IoT"]},
    ]

    with driver.session() as session:
        for t in sample:
            title = t["title"]
            session.run(
                """
                MERGE (top:Topic {title: $title, ownerEmail: $email})
                SET top.createdAt = coalesce(top.createdAt, datetime())
                """,
                title=title,
                email=user_email,
            )
            for s in t.get("subtopics", []):
                session.run(
                    """
                    MATCH (top:Topic {title: $title, ownerEmail: $email})
                    MERGE (sub:Subtopic {title: $sub, ownerEmail: $email})
                    MERGE (top)-[:HAS_SUBTOPIC]->(sub)
                    """,
                    title=title,
                    sub=s,
                    email=user_email,
                )
            for dep in t.get("depends_on", []):
                session.run(
                    """
                    MATCH (a:Topic {title: $title, ownerEmail: $email})
                    MERGE (b:Topic {title: $dep, ownerEmail: $email})
                    MERGE (a)-[:DEPENDS_ON]->(b)
                    """,
                    title=title,
                    dep=dep,
                    email=user_email,
                )

    return {"message": "Seeded sample topics", "sampleCount": len(sample)}


@app.post("/api/notes/process_stored")
def process_stored_file(request: Request, storedFilename: str = None, email: Optional[str] = None):
    """Debug endpoint: process a previously uploaded file (from uploads/) synchronously.
    Returns the extracted JSON and any errors. Use this to troubleshoot why a file didn't produce graph nodes.
    """
    user_email = _resolve_user_email(request, email)
    if not storedFilename:
        raise HTTPException(status_code=400, detail="storedFilename is required")

    file_path = UPLOAD_FOLDER / storedFilename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Stored file not found: {file_path}")

    try:
        txt = extract_text_from_file(file_path)
        extracted = call_gemini_extract(txt)
        # return the extracted result to the caller for inspection
        # and also attempt to store into Neo4j
        process_and_store_notes(extracted, user_email)
        return {"status": "processed", "extracted": extracted}
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"Error processing stored file {file_path}: {e}\n{tb}")
        raise HTTPException(status_code=500, detail={"error": str(e), "traceback": tb})


# ============== NSGA-II STUDY SCHEDULE ENDPOINTS ==============

class ExamInput(BaseModel):
    """Single exam input model"""
    paper: str = ""
    subject: str = ""
    date: str = ""
    start_time: str = ""
    end_time: str = ""


class ScheduleRequest(BaseModel):
    """Request model for schedule generation"""
    exams: List[Dict]


@app.post("/api/study/generate-schedule")
def api_generate_schedule(request_data: ScheduleRequest):
    """
    Generate an optimized study schedule using NSGA-II algorithm.
    
    The algorithm optimizes for three objectives:
    1. Even distribution of study sessions (minimize cramming)
    2. Reduced context switching between subjects
    3. Priority for subjects with upcoming exams
    
    Request body:
    {
        "exams": [
            {"paper": "Machine Learning", "subject": "ML", "date": "2025-11-10"},
            ...
        ]
    }
    
    Returns:
    {
        "schedule": [...],
        "num_days": 60,
        "num_subjects": 10,
        "start_date": "2025-01-25T...",
        "objectives": {"cramming": ..., "switching": ..., "revision": ...}
    }
    """
    try:
        exams = request_data.exams
        
        if not exams:
            raise HTTPException(status_code=400, detail="No exams provided")
        
        # Generate schedule using NSGA-II
        result = generate_study_schedule(exams)
        
        return result
    
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"Error generating schedule: {e}\n{tb}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/study/clean-paper-names")
def api_clean_paper_names(request_data: ScheduleRequest):
    """
    Clean paper names from exam data, removing OCR artifacts and course codes.
    
    Request body:
    {
        "exams": [
            {"paper": "Machine Learning & Blockchain - P IoTCSBCC701", "subject": "Machine"},
            ...
        ]
    }
    
    Returns cleaned exam data with paper_name field.
    """
    try:
        cleaned_exams = []
        
        for exam in request_data.exams:
            paper = exam.get('paper', '')
            subject = exam.get('subject', '')
            
            cleaned_name = clean_paper_name(paper, subject)
            
            cleaned_exam = dict(exam)
            cleaned_exam['paper_name'] = cleaned_name
            cleaned_exams.append(cleaned_exam)
        
        return {"exams": cleaned_exams}
    
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"Error cleaning paper names: {e}\n{tb}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/search/notes")
def semantic_search_notes(
    request: Request,
    query: str,
    limit: int = 10,
    subject_id: Optional[str] = None,
    email: Optional[str] = None,
):
    """Perform semantic search on notes using Weaviate."""
    user_email = _resolve_user_email(request, email)
    try:
        weaviate_svc = get_weaviate_service()
        results = weaviate_svc.semantic_search_notes(
            query=query,
            owner_email=user_email,
            limit=limit,
            subject_id=subject_id,
        )
        return {"query": query, "results": results, "count": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@app.get("/api/search/subjects")
def semantic_search_subjects(
    request: Request,
    query: str,
    limit: int = 10,
    email: Optional[str] = None,
):
    """Perform semantic search on subjects using Weaviate."""
    user_email = _resolve_user_email(request, email)
    try:
        weaviate_svc = get_weaviate_service()
        results = weaviate_svc.semantic_search_subjects(
            query=query,
            owner_email=user_email,
            limit=limit,
        )
        return {"query": query, "results": results, "count": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@app.get("/api/notes/{note_id}/similar")
def get_similar_notes(
    note_id: str,
    request: Request,
    limit: int = 5,
    email: Optional[str] = None,
):
    """Find notes similar to the given note using vector similarity."""
    user_email = _resolve_user_email(request, email)
    try:
        weaviate_svc = get_weaviate_service()
        results = weaviate_svc.get_similar_notes(
            note_id=note_id,
            owner_email=user_email,
            limit=limit,
        )
        return {"noteId": note_id, "similar": results, "count": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to find similar notes: {str(e)}")


# ══════════════════════════════════════════════════════════════
# /api/knowledge-graph/* ROUTES — inlined from knowledge_graph.py
# ══════════════════════════════════════════════════════════════

DEFAULT_USER_EMAIL = os.getenv("DEFAULT_USER_EMAIL", "demo@trackeneer.local")


@app.get("/api/knowledge-graph/documents")
async def kg_get_documents(request: Request, email: Optional[str] = None):
    """List distinct source documents for a user."""
    em = _kg_email(request, email)
    docs = _ekg_pipeline.store.get_source_documents(em)
    return {"status": "ok", "documents": docs}


@app.get("/api/knowledge-graph")
async def kg_get_graph(request: Request, email: Optional[str] = None, source_document: Optional[str] = None):
    """Return the full knowledge graph, optionally filtered by source document."""
    em = _kg_email(request, email)
    if source_document:
        graph = _ekg_pipeline.store.get_graph_by_document(em, source_document)
    else:
        graph = _ekg_pipeline.store.get_full_graph(em)
    return {"status": "ok", **graph}


@app.post("/api/knowledge-graph/build")
async def kg_build_from_text(
    request: Request,
    text: str = Form(...),
    source_document: str = Form(""),
    strategy: str = Form("llm"),
    email: Optional[str] = Form(None),
):
    """Build a Knowledge Graph from raw text input."""
    em = _kg_email(request, email)
    result = _ekg_pipeline.process_text(text, em, source_doc=source_document, strategy=strategy)
    return {"status": "ok", **result}


@app.post("/api/knowledge-graph/upload")
async def kg_build_from_file(
    request: Request,
    file: UploadFile = File(...),
    strategy: str = Form("llm"),
    email: Optional[str] = Form(None),
):
    """Upload a PDF/text file and build a Knowledge Graph from it."""
    em = _kg_email(request, email)
    upload_dir = Path("uploads/kg")
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{uuid.uuid4()}_{file.filename}"
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    try:
        result = _ekg_pipeline.process_pdf(str(file_path), em, strategy=strategy, original_filename=file.filename)
    except Exception as e:
        return {"status": "error", "message": str(e), "file": file.filename}
    return {"status": "ok", "message": f"Knowledge Graph built from '{file.filename}'", "file": file.filename, **result}


@app.get("/api/knowledge-graph/prerequisites/{concept_name}")
async def kg_get_prerequisites(concept_name: str, request: Request, email: Optional[str] = None):
    """Get the prerequisite chain for a concept."""
    em = _kg_email(request, email)
    prereqs = _ekg_pipeline.store.get_prerequisites(concept_name, em)
    return {"status": "ok", "concept": concept_name, "prerequisites": prereqs}


@app.get("/api/knowledge-graph/subgraph/{concept_name}")
async def kg_get_subgraph(concept_name: str, request: Request, hops: int = 2, email: Optional[str] = None):
    """Get a local subgraph around a concept."""
    em = _kg_email(request, email)
    subgraph = _ekg_pipeline.store.get_subgraph(concept_name, em, hops=hops)
    return {"status": "ok", "center": concept_name, **subgraph}


@app.get("/api/knowledge-graph/root-cause/{concept_name}")
async def kg_root_cause(concept_name: str, request: Request, email: Optional[str] = None):
    """Root cause analysis for a struggling concept."""
    em = _kg_email(request, email)
    result = _ekg_pipeline.store.root_cause_analysis(concept_name, em)
    return {"status": "ok", **result}


@app.get("/api/knowledge-graph/weaknesses")
async def kg_get_weaknesses(request: Request, threshold: float = 0.5, email: Optional[str] = None):
    """Get all concepts below mastery threshold."""
    em = _kg_email(request, email)
    weaknesses = _ekg_pipeline.store.get_weak_concepts(em, threshold)
    return {"status": "ok", "weaknesses": weaknesses, "count": len(weaknesses)}


@app.post("/api/knowledge-graph/mastery")
async def kg_update_mastery(
    request: Request,
    concept_name: str = Form(...),
    mastery: float = Form(...),
    email: Optional[str] = Form(None),
):
    """Update mastery score for a concept (0.0–1.0)."""
    em = _kg_email(request, email)
    if not 0 <= mastery <= 1:
        raise HTTPException(status_code=400, detail="Mastery must be between 0 and 1")
    ok = _ekg_pipeline.store.update_mastery(concept_name, em, mastery)
    if not ok:
        raise HTTPException(status_code=404, detail="Concept not found")
    return {"status": "ok", "concept": concept_name, "mastery": mastery}


@app.post("/api/knowledge-graph/enrich")
async def kg_enrich(request: Request, email: Optional[str] = Form(None)):
    """Use LLM to enrich the existing graph."""
    em = _kg_email(request, email)
    result = _ekg_pipeline.enrich_with_llm(em)
    return {"status": "ok", **result}


@app.get("/api/knowledge-graph/gap-analysis")
async def kg_gap_analysis(request: Request, email: Optional[str] = None, mastery_threshold: float = 0.7):
    """IEEE EduKG gap analysis: layer coverage + critical blocking gaps."""
    em = _kg_email(request, email)
    result = _ekg_pipeline.store.get_gap_analysis(em, mastery_threshold)
    return {"status": "ok", **result}


@app.get("/api/knowledge-graph/learning-path/{concept_name}")
async def kg_learning_path(concept_name: str, request: Request, email: Optional[str] = None):
    """Generate an optimal learning path to reach a target concept."""
    em = _kg_email(request, email)
    result = _ekg_pipeline.store.get_learning_path(concept_name, em)
    return {"status": "ok", **result}


@app.delete("/api/knowledge-graph")
async def kg_delete_graph(request: Request, email: Optional[str] = None):
    """Delete the entire Knowledge Graph for a user."""
    em = _kg_email(request, email)
    deleted = _ekg_pipeline.store.delete_graph(em)
    return {"status": "ok", "deleted_concepts": deleted}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5002)
