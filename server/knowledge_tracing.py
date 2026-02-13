"""
Knowledge Tracing Engine (PSI-KT)
==================================

Implements Predictive, Scalable, Interpretable Knowledge Tracing:

1. PSI-KT Core – Models learning rate, forgetting rate, prerequisite utilization
2. Mastery Estimation – Continuous probability scores for each concept
3. Forgetting Curve – Ebbinghaus-inspired memory decay modeling
4. Gap Analysis – Automated weakness identification via KG traversal
5. Quiz Engine – Adaptive assessment with Bloom's taxonomy alignment
6. Spaced Repetition – Optimal review scheduling

Mathematical Foundations:
- P(mastery) = P_prev + α * correct - β * time_decay
- Forgetting: P(t) = P * e^(-λt) where λ is the personal forgetting rate
- Learning rate α adapted per student based on interaction history
"""

from __future__ import annotations

import json
import math
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from db import get_driver
from graph_helpers import ensure_user_and_day, normalize_day

# ─── Gemini for quiz generation ───
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
# DATA MODELS
# ============================================================================

@dataclass
class LearnerState:
    """Per-concept learner state with PSI-KT parameters."""
    concept_name: str
    mastery: float = 0.0            # P(mastery) ∈ [0, 1]
    learning_rate: float = 0.15     # α – how quickly the student learns
    forgetting_rate: float = 0.05   # λ – how quickly mastery decays
    prereq_utilization: float = 0.5 # How well prerequisites support learning
    total_attempts: int = 0
    correct_attempts: int = 0
    last_interaction: Optional[datetime] = None
    streak: int = 0                 # Consecutive correct answers
    bloom_level_reached: str = "remember"  # Highest Bloom level demonstrated

    @property
    def accuracy(self) -> float:
        return self.correct_attempts / max(self.total_attempts, 1)

    def to_dict(self) -> dict:
        return {
            "concept_name": self.concept_name,
            "mastery": round(self.mastery, 4),
            "learning_rate": round(self.learning_rate, 4),
            "forgetting_rate": round(self.forgetting_rate, 4),
            "prereq_utilization": round(self.prereq_utilization, 4),
            "total_attempts": self.total_attempts,
            "correct_attempts": self.correct_attempts,
            "accuracy": round(self.accuracy, 4),
            "last_interaction": self.last_interaction.isoformat() if self.last_interaction else None,
            "streak": self.streak,
            "bloom_level_reached": self.bloom_level_reached,
        }


@dataclass
class QuizQuestion:
    """A single quiz question with metadata."""
    id: str = ""
    concept_name: str = ""
    question: str = ""
    options: List[str] = field(default_factory=list)
    correct_answer: str = ""
    explanation: str = ""
    bloom_level: str = "understand"
    difficulty: str = "medium"
    question_type: str = "multiple_choice"  # multiple_choice, short_answer, true_false

    def to_dict(self) -> dict:
        return {
            "id": self.id or str(uuid.uuid4()),
            "concept_name": self.concept_name,
            "question": self.question,
            "options": self.options,
            "bloom_level": self.bloom_level,
            "difficulty": self.difficulty,
            "question_type": self.question_type,
        }

    def to_dict_with_answer(self) -> dict:
        d = self.to_dict()
        d["correct_answer"] = self.correct_answer
        d["explanation"] = self.explanation
        return d


# ============================================================================
# PSI-KT ENGINE
# ============================================================================

class PSIKTEngine:
    """
    Predictive, Scalable, Interpretable Knowledge Tracing.
    
    Key Innovation: Explicitly models psychological parameters
    (learning rate, forgetting rate, prerequisite utilization)
    to provide both accurate predictions AND explainable feedback.
    """

    # ─── Bloom's Taxonomy ordered levels ───
    BLOOM_LEVELS = ["remember", "understand", "apply", "analyze", "evaluate", "create"]

    # ─── PSI-KT hyperparameters ───
    BASE_LEARNING_RATE = 0.15
    BASE_FORGETTING_RATE = 0.05
    MIN_MASTERY = 0.0
    MAX_MASTERY = 1.0
    MASTERY_GAIN_CORRECT = 0.12
    MASTERY_LOSS_INCORRECT = 0.08
    STREAK_BONUS = 0.03
    PREREQ_BONUS = 0.05

    def __init__(self):
        self.driver = get_driver()

    def update_mastery(
        self,
        user_email: str,
        concept_name: str,
        is_correct: bool,
        bloom_level: str = "understand",
        time_spent_seconds: float = 0,
    ) -> LearnerState:
        """
        Update mastery after a student interaction (quiz answer, exercise, etc.).
        
        Implements the PSI-KT update rule:
        1. Apply forgetting curve since last interaction
        2. Update based on correctness
        3. Adjust learning rate based on performance history
        4. Account for prerequisite mastery
        """
        state = self._get_learner_state(user_email, concept_name)
        now = datetime.now(timezone.utc)

        # Step 1: Apply forgetting curve
        if state.last_interaction:
            hours_elapsed = (now - state.last_interaction).total_seconds() / 3600
            decay = math.exp(-state.forgetting_rate * hours_elapsed)
            state.mastery = state.mastery * decay

        # Step 2: Get prerequisite mastery for bonus
        prereq_mastery = self._get_prerequisite_mastery(user_email, concept_name)
        state.prereq_utilization = prereq_mastery

        # Step 3: Update mastery based on correctness
        state.total_attempts += 1
        if is_correct:
            state.correct_attempts += 1
            state.streak += 1

            # Base gain
            gain = self.MASTERY_GAIN_CORRECT * state.learning_rate / self.BASE_LEARNING_RATE

            # Streak bonus
            if state.streak >= 3:
                gain += self.STREAK_BONUS

            # Prerequisite bonus (higher prereq mastery → faster learning)
            gain += self.PREREQ_BONUS * prereq_mastery

            # Bloom level bonus (higher levels = more gain)
            bloom_idx = self.BLOOM_LEVELS.index(bloom_level) if bloom_level in self.BLOOM_LEVELS else 1
            gain *= (1 + bloom_idx * 0.1)

            state.mastery = min(self.MAX_MASTERY, state.mastery + gain)

            # Update highest Bloom level
            current_idx = self.BLOOM_LEVELS.index(state.bloom_level_reached) if state.bloom_level_reached in self.BLOOM_LEVELS else 0
            if bloom_idx > current_idx:
                state.bloom_level_reached = bloom_level

        else:
            state.streak = 0
            loss = self.MASTERY_LOSS_INCORRECT
            state.mastery = max(self.MIN_MASTERY, state.mastery - loss)

        # Step 4: Adapt learning rate
        state.learning_rate = self._adapt_learning_rate(state)

        # Step 5: Adapt forgetting rate
        state.forgetting_rate = self._adapt_forgetting_rate(state)

        state.last_interaction = now

        # Step 6: Persist to Neo4j
        self._save_learner_state(user_email, state)

        return state

    def get_knowledge_state(self, user_email: str) -> dict:
        """Get the complete knowledge state for a user."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
                RETURN c.name AS name,
                       coalesce(c.mastery, 0) AS mastery,
                       coalesce(c.learning_rate, 0.15) AS learning_rate,
                       coalesce(c.forgetting_rate, 0.05) AS forgetting_rate,
                       coalesce(c.prereq_utilization, 0.5) AS prereq_utilization,
                       coalesce(c.total_attempts, 0) AS total_attempts,
                       coalesce(c.correct_attempts, 0) AS correct_attempts,
                       c.last_interaction AS last_interaction,
                       coalesce(c.streak, 0) AS streak,
                       coalesce(c.bloom_level_reached, 'remember') AS bloom_level_reached,
                       c.difficulty AS difficulty,
                       c.category AS category
                ORDER BY c.mastery ASC
            """, email=user_email)

            states = []
            for r in result:
                state = {
                    "concept_name": r["name"],
                    "mastery": r["mastery"],
                    "learning_rate": r["learning_rate"],
                    "forgetting_rate": r["forgetting_rate"],
                    "prereq_utilization": r["prereq_utilization"],
                    "total_attempts": r["total_attempts"],
                    "correct_attempts": r["correct_attempts"],
                    "accuracy": r["correct_attempts"] / max(r["total_attempts"], 1),
                    "streak": r["streak"],
                    "bloom_level_reached": r["bloom_level_reached"],
                    "difficulty": r.get("difficulty", "medium"),
                    "category": r.get("category", "topic"),
                }
                states.append(state)

            # Calculate summary statistics
            masteries = [s["mastery"] for s in states]
            overall = sum(masteries) / max(len(masteries), 1)
            weak_count = sum(1 for m in masteries if m < 0.5)
            strong_count = sum(1 for m in masteries if m >= 0.8)

            return {
                "states": states,
                "summary": {
                    "total_concepts": len(states),
                    "overall_mastery": round(overall, 4),
                    "weak_concepts": weak_count,
                    "strong_concepts": strong_count,
                    "mastered_percentage": round(strong_count / max(len(states), 1) * 100, 1),
                },
            }

    def gap_analysis(self, user_email: str) -> dict:
        """
        Comprehensive gap analysis:
        1. Identify weak concepts
        2. For each, perform root cause analysis
        3. Generate prioritized remediation plan
        """
        knowledge_state = self.get_knowledge_state(user_email)
        weak_concepts = [s for s in knowledge_state["states"] if s["mastery"] < 0.5]

        if not weak_concepts:
            return {
                "gaps": [],
                "message": "Excellent! No significant knowledge gaps detected.",
                "overall_mastery": knowledge_state["summary"]["overall_mastery"],
            }

        gaps = []
        for concept in weak_concepts[:10]:
            # Root cause analysis via graph traversal
            root_cause = self._root_cause_for_concept(user_email, concept["concept_name"])
            
            # Estimate time to mastery
            time_estimate = self._estimate_time_to_mastery(concept)

            gaps.append({
                "concept": concept["concept_name"],
                "current_mastery": concept["mastery"],
                "difficulty": concept["difficulty"],
                "root_cause": root_cause,
                "estimated_hours": time_estimate,
                "priority": "high" if root_cause.get("is_foundation") else "medium",
                "recommended_action": self._recommend_action(concept, root_cause),
            })

        # Sort by priority
        gaps.sort(key=lambda g: (g["priority"] != "high", g["current_mastery"]))

        return {
            "gaps": gaps,
            "total_gaps": len(weak_concepts),
            "overall_mastery": knowledge_state["summary"]["overall_mastery"],
            "remediation_order": [g["concept"] for g in gaps],
            "message": f"Found {len(weak_concepts)} knowledge gaps. "
                       f"Start with the high-priority items (they are prerequisites for other topics).",
        }

    def predict_due_for_review(self, user_email: str) -> List[dict]:
        """
        Spaced Repetition: Identify concepts due for review based on forgetting curves.
        """
        now = datetime.now(timezone.utc)
        due_concepts = []

        with self.driver.session() as session:
            result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
                WHERE c.mastery > 0.3 AND c.last_interaction IS NOT NULL
                RETURN c.name AS name, c.mastery AS mastery,
                       c.forgetting_rate AS forgetting_rate,
                       c.last_interaction AS last_interaction,
                       c.difficulty AS difficulty
            """, email=user_email)

            for r in result:
                last = r["last_interaction"]
                if not last:
                    continue

                if isinstance(last, str):
                    try:
                        last = datetime.fromisoformat(last.replace("Z", "+00:00"))
                    except Exception:
                        continue

                # Make last timezone-aware if it isn't
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)

                hours_elapsed = (now - last).total_seconds() / 3600
                forgetting_rate = r.get("forgetting_rate") or 0.05
                current_mastery = r["mastery"]

                # Apply forgetting curve
                predicted_mastery = current_mastery * math.exp(-forgetting_rate * hours_elapsed)

                # If predicted mastery drops below threshold, it's due for review
                if predicted_mastery < 0.6 * current_mastery:
                    due_concepts.append({
                        "concept": r["name"],
                        "stored_mastery": round(current_mastery, 3),
                        "predicted_mastery": round(predicted_mastery, 3),
                        "decay_percent": round((1 - predicted_mastery / max(current_mastery, 0.01)) * 100, 1),
                        "hours_since_review": round(hours_elapsed, 1),
                        "difficulty": r.get("difficulty", "medium"),
                        "urgency": "high" if predicted_mastery < 0.3 else "medium",
                    })

        due_concepts.sort(key=lambda x: x["predicted_mastery"])
        return due_concepts

    # ─── Internal helpers ───

    def _get_learner_state(self, user_email: str, concept_name: str) -> LearnerState:
        """Retrieve or initialize learner state from Neo4j."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (c:Concept {name: $name, userEmail: $email})
                RETURN c
            """, name=concept_name, email=user_email)
            record = result.single()

            if record:
                c = record["c"]
                last = c.get("last_interaction")
                if isinstance(last, str):
                    try:
                        last = datetime.fromisoformat(last.replace("Z", "+00:00"))
                    except Exception:
                        last = None
                elif hasattr(last, 'to_native'):
                    last = last.to_native()

                return LearnerState(
                    concept_name=concept_name,
                    mastery=c.get("mastery") or 0.0,
                    learning_rate=c.get("learning_rate") or self.BASE_LEARNING_RATE,
                    forgetting_rate=c.get("forgetting_rate") or self.BASE_FORGETTING_RATE,
                    prereq_utilization=c.get("prereq_utilization") or 0.5,
                    total_attempts=c.get("total_attempts") or 0,
                    correct_attempts=c.get("correct_attempts") or 0,
                    last_interaction=last,
                    streak=c.get("streak") or 0,
                    bloom_level_reached=c.get("bloom_level_reached") or "remember",
                )
            else:
                return LearnerState(concept_name=concept_name)

    def _save_learner_state(self, user_email: str, state: LearnerState):
        """Persist learner state to Neo4j."""
        with self.driver.session() as session:
            session.run("""
                MATCH (c:Concept {name: $name, userEmail: $email})
                SET c.mastery = $mastery,
                    c.learning_rate = $learning_rate,
                    c.forgetting_rate = $forgetting_rate,
                    c.prereq_utilization = $prereq_utilization,
                    c.total_attempts = $total_attempts,
                    c.correct_attempts = $correct_attempts,
                    c.last_interaction = datetime($last_interaction),
                    c.streak = $streak,
                    c.bloom_level_reached = $bloom_level_reached
            """,
                name=state.concept_name,
                email=user_email,
                mastery=state.mastery,
                learning_rate=state.learning_rate,
                forgetting_rate=state.forgetting_rate,
                prereq_utilization=state.prereq_utilization,
                total_attempts=state.total_attempts,
                correct_attempts=state.correct_attempts,
                last_interaction=state.last_interaction.isoformat() if state.last_interaction else datetime.now(timezone.utc).isoformat(),
                streak=state.streak,
                bloom_level_reached=state.bloom_level_reached,
            )

    def _get_prerequisite_mastery(self, user_email: str, concept_name: str) -> float:
        """Get average mastery of prerequisites."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (prereq:Concept)-[:PREREQUISITE_OF]->(target:Concept {name: $name, userEmail: $email})
                WHERE prereq.userEmail = $email
                RETURN avg(coalesce(prereq.mastery, 0)) AS avg_mastery
            """, name=concept_name, email=user_email)
            record = result.single()
            if record and record["avg_mastery"] is not None:
                return float(record["avg_mastery"])
            return 0.5  # Default if no prerequisites

    def _adapt_learning_rate(self, state: LearnerState) -> float:
        """Adapt learning rate based on recent performance."""
        if state.total_attempts < 3:
            return self.BASE_LEARNING_RATE

        recent_accuracy = state.accuracy
        # Higher accuracy → slightly higher learning rate (student learns quickly)
        return max(0.05, min(0.3, self.BASE_LEARNING_RATE * (0.5 + recent_accuracy)))

    def _adapt_forgetting_rate(self, state: LearnerState) -> float:
        """Adapt forgetting rate based on mastery and streak."""
        # Higher mastery and longer streaks → lower forgetting rate (better retention)
        base = self.BASE_FORGETTING_RATE
        mastery_factor = 1 - state.mastery * 0.5  # High mastery → less forgetting
        streak_factor = max(0.5, 1 - state.streak * 0.05)  # Streaks → better retention
        return max(0.01, base * mastery_factor * streak_factor)

    def _root_cause_for_concept(self, user_email: str, concept_name: str) -> dict:
        """Find the root cause of weakness in a concept."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH path = (prereq:Concept)-[:PREREQUISITE_OF*1..5]->(target:Concept {name: $name, userEmail: $email})
                WHERE prereq.userEmail = $email
                UNWIND nodes(path) AS n
                WITH DISTINCT n
                RETURN n.name AS name, coalesce(n.mastery, 0) AS mastery, n.difficulty AS difficulty
                ORDER BY n.mastery ASC
            """, name=concept_name, email=user_email)

            prereqs = [dict(r) for r in result]

            if not prereqs:
                return {
                    "root_cause": concept_name,
                    "is_foundation": True,
                    "message": f"'{concept_name}' has no prerequisites — it may be a foundational concept that needs direct review.",
                }

            weakest = min(prereqs, key=lambda p: p["mastery"])

            # Check if this concept is a prerequisite for many others
            dep_result = session.run("""
                MATCH (c:Concept {name: $name, userEmail: $email})-[:PREREQUISITE_OF]->(dependent:Concept)
                RETURN count(dependent) AS dep_count
            """, name=concept_name, email=user_email)
            dep_record = dep_result.single()
            is_foundation = (dep_record["dep_count"] or 0) > 2 if dep_record else False

            return {
                "root_cause": weakest["name"],
                "root_cause_mastery": weakest["mastery"],
                "prerequisite_chain": [p["name"] for p in prereqs],
                "is_foundation": is_foundation,
                "message": f"Your weakness in '{concept_name}' likely stems from low mastery of "
                           f"'{weakest['name']}' ({int(weakest['mastery'] * 100)}%). "
                           f"Review '{weakest['name']}' first.",
            }

    def _estimate_time_to_mastery(self, concept: dict) -> float:
        """Estimate hours needed to reach mastery based on current state."""
        current = concept.get("mastery", 0)
        target = 0.8
        difficulty_multiplier = {"easy": 0.7, "medium": 1.0, "hard": 1.5}.get(
            concept.get("difficulty", "medium"), 1.0
        )
        learning_rate = concept.get("learning_rate", 0.15)

        if current >= target:
            return 0

        # Rough estimate: each hour of study gives `learning_rate` mastery gain
        gap = target - current
        base_hours = gap / max(learning_rate, 0.05)
        return round(base_hours * difficulty_multiplier, 1)

    def _recommend_action(self, concept: dict, root_cause: dict) -> str:
        mastery = concept["mastery"]
        if root_cause.get("root_cause") != concept["concept_name"]:
            return f"First review prerequisite: '{root_cause['root_cause']}', then return to '{concept['concept_name']}'"
        elif mastery < 0.2:
            return f"Start from scratch. Read through your notes on '{concept['concept_name']}' and try basic recall exercises."
        elif mastery < 0.5:
            return f"Practice with exercises. Focus on 'Apply' level tasks for '{concept['concept_name']}'."
        else:
            return f"Almost there! Try teaching '{concept['concept_name']}' to reinforce your understanding."


# ============================================================================
# QUIZ GENERATOR
# ============================================================================

class AdaptiveQuizGenerator:
    """
    Generates adaptive quiz questions based on:
    - Student's current knowledge state
    - Bloom's Taxonomy alignment
    - Concept difficulty
    - Knowledge graph relationships
    """

    def __init__(self):
        self.kt_engine = PSIKTEngine()

    def generate_quiz(
        self,
        user_email: str,
        concept_name: str = "",
        num_questions: int = 5,
        target_bloom_levels: List[str] = None,
    ) -> List[dict]:
        """Generate adaptive quiz questions."""
        if not HAS_GEMINI or not _gemini:
            return self._generate_fallback_quiz(concept_name, num_questions)

        # Get current mastery to adapt difficulty
        state = self.kt_engine._get_learner_state(user_email, concept_name) if concept_name else None

        if target_bloom_levels is None:
            if state and state.mastery > 0.7:
                target_bloom_levels = ["apply", "analyze", "evaluate"]
            elif state and state.mastery > 0.4:
                target_bloom_levels = ["understand", "apply", "analyze"]
            else:
                target_bloom_levels = ["remember", "understand", "apply"]

        prompt = f"""Generate {num_questions} quiz questions about "{concept_name or 'general topics'}".

Requirements:
1. Mix question types: multiple choice, true/false, and short answer.
2. Target these Bloom's Taxonomy levels: {', '.join(target_bloom_levels)}
3. Include clear explanations for correct answers.
4. Progress from easier to harder.

Return ONLY valid JSON in this format:
{{
  "questions": [
    {{
      "question": "...",
      "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
      "correct_answer": "A",
      "explanation": "...",
      "bloom_level": "understand",
      "difficulty": "medium",
      "question_type": "multiple_choice"
    }}
  ]
}}
"""
        try:
            response = _gemini.generate_content(prompt)
            raw = response.text.strip()
            raw = re.sub(r"```json\s*", "", raw)
            raw = re.sub(r"```\s*$", "", raw)
            data = json.loads(raw)

            questions = []
            for q in data.get("questions", []):
                questions.append({
                    "id": str(uuid.uuid4()),
                    "concept_name": concept_name,
                    "question": q.get("question", ""),
                    "options": q.get("options", []),
                    "correct_answer": q.get("correct_answer", ""),
                    "explanation": q.get("explanation", ""),
                    "bloom_level": q.get("bloom_level", "understand"),
                    "difficulty": q.get("difficulty", "medium"),
                    "question_type": q.get("question_type", "multiple_choice"),
                })

            return questions

        except Exception as e:
            print(f"⚠ Quiz generation failed: {e}")
            return self._generate_fallback_quiz(concept_name, num_questions)

    def evaluate_answer(
        self,
        user_email: str,
        question_id: str,
        concept_name: str,
        student_answer: str,
        correct_answer: str,
        bloom_level: str = "understand",
    ) -> dict:
        """Evaluate a student's answer and update knowledge tracing."""
        # Simple correctness check
        is_correct = student_answer.strip().lower() == correct_answer.strip().lower()

        # If it's a longer answer, use LLM for evaluation
        if len(student_answer) > 20 and HAS_GEMINI and _gemini:
            try:
                eval_prompt = f"""Evaluate this student answer:
Question answer should be: {correct_answer}
Student answered: {student_answer}

Is the student's answer correct or substantially correct? Reply with ONLY "correct" or "incorrect"."""
                response = _gemini.generate_content(eval_prompt)
                is_correct = "correct" in response.text.strip().lower() and "incorrect" not in response.text.strip().lower()
            except Exception:
                pass

        # Update knowledge tracing
        new_state = self.kt_engine.update_mastery(
            user_email=user_email,
            concept_name=concept_name,
            is_correct=is_correct,
            bloom_level=bloom_level,
        )

        # Generate feedback
        if is_correct:
            feedback = f"✅ Correct! Great job. Your mastery of '{concept_name}' is now {int(new_state.mastery * 100)}%."
            if new_state.streak >= 3:
                feedback += f" 🔥 {new_state.streak}-answer streak!"
        else:
            feedback = f"❌ Not quite. The correct answer is: {correct_answer}. "
            feedback += f"Your mastery is now {int(new_state.mastery * 100)}%."
            if new_state.mastery < 0.3:
                feedback += f" 💡 Consider reviewing the basics of '{concept_name}' before trying again."

        return {
            "is_correct": is_correct,
            "feedback": feedback,
            "new_mastery": new_state.mastery,
            "streak": new_state.streak,
            "learner_state": new_state.to_dict(),
        }

    def _generate_fallback_quiz(self, concept_name: str, num_questions: int) -> List[dict]:
        """Fallback quiz when Gemini is unavailable."""
        return [{
            "id": str(uuid.uuid4()),
            "concept_name": concept_name,
            "question": f"Explain the key ideas behind '{concept_name}' in your own words.",
            "options": [],
            "bloom_level": "understand",
            "difficulty": "medium",
            "question_type": "short_answer",
        }]


# Need re import for quiz generation
import re


# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

app = FastAPI(title="TrackEneer Knowledge Tracing API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_USER_EMAIL = os.getenv("DEFAULT_USER_EMAIL", "demo@trackeneer.local")
kt_engine = PSIKTEngine()
quiz_generator = AdaptiveQuizGenerator()


def _resolve_email(request: Request, provided: Optional[str] = None) -> str:
    if provided:
        return provided
    return request.headers.get("x-user-email", "") or DEFAULT_USER_EMAIL


# ─── Health ───

@app.get("/")
async def root():
    return {"service": "knowledge-tracing", "status": "ok"}


# ─── Get knowledge state ───

@app.get("/api/knowledge-tracing/state")
async def get_knowledge_state(request: Request, email: Optional[str] = None):
    """Get the complete knowledge state (mastery heatmap data)."""
    user_email = _resolve_email(request, email)
    state = kt_engine.get_knowledge_state(user_email)
    return {"status": "ok", **state}


# ─── Update mastery ───

@app.post("/api/knowledge-tracing/update")
async def update_mastery(
    request: Request,
    concept_name: str = Form(...),
    is_correct: bool = Form(...),
    bloom_level: str = Form("understand"),
    time_spent: float = Form(0),
    email: Optional[str] = Form(None),
):
    """Update mastery after a learning interaction."""
    user_email = _resolve_email(request, email)
    state = kt_engine.update_mastery(
        user_email=user_email,
        concept_name=concept_name,
        is_correct=is_correct,
        bloom_level=bloom_level,
        time_spent_seconds=time_spent,
    )
    return {"status": "ok", "learner_state": state.to_dict()}


# ─── Gap analysis ───

@app.get("/api/knowledge-tracing/gaps")
async def gap_analysis(request: Request, email: Optional[str] = None):
    """Perform comprehensive gap analysis with root cause detection."""
    user_email = _resolve_email(request, email)
    result = kt_engine.gap_analysis(user_email)
    return {"status": "ok", **result}


# ─── Spaced repetition ───

@app.get("/api/knowledge-tracing/due-review")
async def due_for_review(request: Request, email: Optional[str] = None):
    """Get concepts due for review (spaced repetition)."""
    user_email = _resolve_email(request, email)
    due = kt_engine.predict_due_for_review(user_email)
    return {"status": "ok", "due_concepts": due, "count": len(due)}


# ─── Generate quiz ───

@app.post("/api/quiz/generate")
async def generate_quiz(
    request: Request,
    concept_name: str = Form(""),
    num_questions: int = Form(5),
    email: Optional[str] = Form(None),
):
    """Generate adaptive quiz questions for a concept."""
    user_email = _resolve_email(request, email)
    questions = quiz_generator.generate_quiz(
        user_email=user_email,
        concept_name=concept_name,
        num_questions=num_questions,
    )
    return {"status": "ok", "questions": questions, "count": len(questions)}


# ─── Evaluate answer ───

@app.post("/api/quiz/evaluate")
async def evaluate_answer(
    request: Request,
    question_id: str = Form(...),
    concept_name: str = Form(...),
    student_answer: str = Form(...),
    correct_answer: str = Form(...),
    bloom_level: str = Form("understand"),
    email: Optional[str] = Form(None),
):
    """Evaluate a quiz answer and update knowledge tracing."""
    user_email = _resolve_email(request, email)
    result = quiz_generator.evaluate_answer(
        user_email=user_email,
        question_id=question_id,
        concept_name=concept_name,
        student_answer=student_answer,
        correct_answer=correct_answer,
        bloom_level=bloom_level,
    )
    return {"status": "ok", **result}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5007)
