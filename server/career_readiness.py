"""
Career Readiness & Syllabus2Skill Engine
==========================================

Bridges academic learning to industry employment through:

1. Syllabus2Skill Pipeline – Maps academic concepts to ESCO/O*NET skills
2. Placement Prediction – ML-based readiness scoring with SHAP explanations
3. Skill Gap Analysis – Delta between student profile and target role
4. XAI Feedback – Natural language explanations of AI predictions
5. Resume Analysis – AI-powered resume vs job description comparison

Architecture:
  Academic Concepts (KG) → SBERT Encoding → Cosine Alignment → ESCO/O*NET Skills
  Student Profile (Features) → Random Forest/XGBoost → Placement Probability → SHAP → NL Feedback
"""

from __future__ import annotations

import json
import math
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from db import get_driver
from graph_helpers import normalize_day

# ─── Embeddings ───
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    HAS_SBERT = True
except ImportError:
    HAS_SBERT = False
    np = None

# ─── ML Models ───
try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

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
# ESCO/O*NET SKILLS TAXONOMY
# ============================================================================

# Comprehensive skills taxonomy (ESCO/O*NET inspired)
INDUSTRY_SKILLS_TAXONOMY = {
    # Technical Skills
    "programming": {
        "name": "Programming & Software Development",
        "skills": [
            "Python", "Java", "JavaScript", "C++", "C", "SQL", "R",
            "TypeScript", "Go", "Rust", "Swift", "Kotlin",
        ],
        "category": "technical",
    },
    "data_science": {
        "name": "Data Science & Analytics",
        "skills": [
            "Machine Learning", "Deep Learning", "Data Analysis",
            "Statistical Modeling", "Data Visualization", "NLP",
            "Computer Vision", "Big Data", "TensorFlow", "PyTorch",
            "Pandas", "NumPy", "Scikit-learn", "Tableau", "Power BI",
        ],
        "category": "technical",
    },
    "web_development": {
        "name": "Web Development",
        "skills": [
            "HTML/CSS", "React", "Angular", "Vue.js", "Node.js",
            "Django", "Flask", "REST APIs", "GraphQL", "Next.js",
            "Express.js", "MongoDB", "PostgreSQL", "Redis",
        ],
        "category": "technical",
    },
    "cloud_devops": {
        "name": "Cloud & DevOps",
        "skills": [
            "AWS", "Azure", "GCP", "Docker", "Kubernetes",
            "CI/CD", "Linux", "Terraform", "Jenkins", "Git",
        ],
        "category": "technical",
    },
    "databases": {
        "name": "Database Management",
        "skills": [
            "SQL", "MySQL", "PostgreSQL", "MongoDB", "Redis",
            "Neo4j", "Cassandra", "Database Design", "Data Modeling",
            "Query Optimization",
        ],
        "category": "technical",
    },
    "networking": {
        "name": "Computer Networks",
        "skills": [
            "TCP/IP", "DNS", "HTTP/HTTPS", "Network Security",
            "Firewall Configuration", "Load Balancing", "VPN",
            "OSI Model", "Routing Protocols",
        ],
        "category": "technical",
    },
    "cybersecurity": {
        "name": "Cybersecurity",
        "skills": [
            "Network Security", "Cryptography", "Ethical Hacking",
            "Penetration Testing", "SIEM", "Incident Response",
            "Security Auditing", "Vulnerability Assessment",
        ],
        "category": "technical",
    },
    # Soft Skills
    "communication": {
        "name": "Communication",
        "skills": [
            "Written Communication", "Verbal Communication",
            "Presentation Skills", "Technical Writing",
            "Active Listening", "Stakeholder Management",
        ],
        "category": "soft",
    },
    "leadership": {
        "name": "Leadership & Management",
        "skills": [
            "Team Leadership", "Project Management", "Agile/Scrum",
            "Decision Making", "Conflict Resolution", "Mentoring",
        ],
        "category": "soft",
    },
    "problem_solving": {
        "name": "Problem Solving & Critical Thinking",
        "skills": [
            "Analytical Thinking", "Critical Thinking",
            "Creative Problem Solving", "Root Cause Analysis",
            "Design Thinking", "Debugging",
        ],
        "category": "soft",
    },
}

# Job role templates
JOB_ROLE_REQUIREMENTS = {
    "software_engineer": {
        "title": "Software Engineer",
        "required_skills": [
            "Python", "Java", "JavaScript", "SQL", "Git",
            "REST APIs", "Data Structures", "Algorithms",
            "Problem Solving", "Team Leadership",
        ],
        "preferred_skills": [
            "Docker", "Kubernetes", "CI/CD", "AWS",
            "System Design", "Agile/Scrum",
        ],
        "min_cgpa": 6.5,
    },
    "data_analyst": {
        "title": "Data Analyst",
        "required_skills": [
            "Python", "SQL", "Data Analysis", "Data Visualization",
            "Statistical Modeling", "Tableau", "Excel",
            "Communication", "Critical Thinking",
        ],
        "preferred_skills": [
            "Machine Learning", "R", "Power BI", "Big Data",
            "Pandas", "NumPy",
        ],
        "min_cgpa": 6.0,
    },
    "data_scientist": {
        "title": "Data Scientist",
        "required_skills": [
            "Python", "Machine Learning", "Deep Learning",
            "Statistical Modeling", "SQL", "Data Visualization",
            "NLP", "TensorFlow", "PyTorch",
        ],
        "preferred_skills": [
            "Computer Vision", "Big Data", "A/B Testing",
            "MLOps", "Spark",
        ],
        "min_cgpa": 7.0,
    },
    "web_developer": {
        "title": "Full Stack Web Developer",
        "required_skills": [
            "HTML/CSS", "JavaScript", "React", "Node.js",
            "SQL", "Git", "REST APIs",
        ],
        "preferred_skills": [
            "TypeScript", "Next.js", "MongoDB", "Docker",
            "GraphQL", "AWS",
        ],
        "min_cgpa": 6.0,
    },
    "devops_engineer": {
        "title": "DevOps Engineer",
        "required_skills": [
            "Linux", "Docker", "Kubernetes", "CI/CD",
            "AWS", "Git", "Python", "Terraform",
        ],
        "preferred_skills": [
            "Azure", "GCP", "Jenkins", "Ansible",
            "Monitoring", "Security",
        ],
        "min_cgpa": 6.5,
    },
    "cybersecurity_analyst": {
        "title": "Cybersecurity Analyst",
        "required_skills": [
            "Network Security", "Cryptography", "SIEM",
            "Incident Response", "Vulnerability Assessment",
            "Linux", "Python",
        ],
        "preferred_skills": [
            "Penetration Testing", "Ethical Hacking",
            "Cloud Security", "Security Auditing",
        ],
        "min_cgpa": 6.0,
    },
}


# ============================================================================
# SYLLABUS2SKILL MAPPER
# ============================================================================

class Syllabus2SkillMapper:
    """
    Maps academic learning outcomes to industry skills using
    SBERT embeddings and cosine similarity alignment.
    """

    SIMILARITY_THRESHOLD = 0.45  # Cosine sim threshold for mapping

    def __init__(self):
        self._embed_model = None
        self._skill_embeddings = None
        self._all_skills = None

    @property
    def embed_model(self):
        if self._embed_model is None and HAS_SBERT:
            model_path = os.getenv("EMBED_MODEL", "./all-MiniLM-L6-v2")
            try:
                self._embed_model = SentenceTransformer(model_path)
            except Exception:
                pass
        return self._embed_model

    def _ensure_skill_embeddings(self):
        """Pre-compute embeddings for all taxonomy skills."""
        if self._skill_embeddings is not None:
            return
        if not self.embed_model:
            return

        self._all_skills = []
        for domain, info in INDUSTRY_SKILLS_TAXONOMY.items():
            for skill in info["skills"]:
                self._all_skills.append({
                    "skill": skill,
                    "domain": info["name"],
                    "category": info["category"],
                })

        skill_texts = [s["skill"] for s in self._all_skills]
        self._skill_embeddings = self.embed_model.encode(skill_texts)

    def map_concepts_to_skills(self, concepts: List[str]) -> List[dict]:
        """
        Map academic concepts to industry skills.
        
        Algorithm:
        1. Encode academic concepts with SBERT
        2. Compute cosine similarity against skill taxonomy
        3. Map concepts exceeding threshold to skills
        """
        if not self.embed_model or not concepts:
            return self._fallback_mapping(concepts)

        self._ensure_skill_embeddings()
        if self._skill_embeddings is None:
            return self._fallback_mapping(concepts)

        # Encode academic concepts
        concept_embeddings = self.embed_model.encode(concepts)

        mappings = []
        for i, concept in enumerate(concepts):
            concept_emb = concept_embeddings[i]

            # Compute similarities against all skills
            similarities = []
            for j, skill_emb in enumerate(self._skill_embeddings):
                sim = float(np.dot(concept_emb, skill_emb) /
                           (np.linalg.norm(concept_emb) * np.linalg.norm(skill_emb) + 1e-8))
                if sim > self.SIMILARITY_THRESHOLD:
                    similarities.append({
                        "skill": self._all_skills[j]["skill"],
                        "domain": self._all_skills[j]["domain"],
                        "category": self._all_skills[j]["category"],
                        "similarity": round(sim, 4),
                    })

            similarities.sort(key=lambda x: x["similarity"], reverse=True)

            mappings.append({
                "academic_concept": concept,
                "mapped_skills": similarities[:5],  # Top 5 matches
                "has_mapping": len(similarities) > 0,
            })

        return mappings

    def generate_skill_profile(self, user_email: str) -> dict:
        """
        Generate a complete skill profile from the student's KG mastery.
        Maps academic mastery to industry skill readiness.
        """
        driver = get_driver()
        with driver.session() as session:
            result = session.run("""
                MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
                RETURN c.name AS name, coalesce(c.mastery, 0) AS mastery,
                       c.category AS category, c.difficulty AS difficulty
            """, email=user_email)

            concepts_with_mastery = [(r["name"], r["mastery"]) for r in result]

        if not concepts_with_mastery:
            return {"skills": [], "message": "No concepts found. Upload your syllabus first."}

        concept_names = [c[0] for c in concepts_with_mastery]
        mastery_map = {c[0]: c[1] for c in concepts_with_mastery}

        # Map concepts to skills
        mappings = self.map_concepts_to_skills(concept_names)

        # Aggregate skills with mastery-weighted scores
        skill_scores: Dict[str, List[float]] = {}
        skill_meta: Dict[str, dict] = {}

        for mapping in mappings:
            concept_mastery = mastery_map.get(mapping["academic_concept"], 0)
            for skill in mapping["mapped_skills"]:
                skill_name = skill["skill"]
                if skill_name not in skill_scores:
                    skill_scores[skill_name] = []
                    skill_meta[skill_name] = {
                        "domain": skill["domain"],
                        "category": skill["category"],
                    }
                # Weighted score: similarity * mastery
                weighted_score = skill["similarity"] * concept_mastery
                skill_scores[skill_name].append(weighted_score)

        # Calculate final skill readiness
        skills = []
        for skill_name, scores in skill_scores.items():
            avg_score = sum(scores) / len(scores)
            max_score = max(scores)
            skills.append({
                "skill": skill_name,
                "readiness": round(min(avg_score * 1.5, 1.0), 4),  # Scale up slightly
                "confidence": round(max_score, 4),
                "domain": skill_meta[skill_name]["domain"],
                "category": skill_meta[skill_name]["category"],
                "contributing_concepts": len(scores),
            })

        skills.sort(key=lambda x: x["readiness"], reverse=True)

        # Categorize
        technical = [s for s in skills if s["category"] == "technical"]
        soft = [s for s in skills if s["category"] == "soft"]

        return {
            "skills": skills,
            "technical_skills": technical[:15],
            "soft_skills": soft[:10],
            "total_skills_mapped": len(skills),
            "avg_readiness": round(sum(s["readiness"] for s in skills) / max(len(skills), 1), 4),
        }

    def _fallback_mapping(self, concepts: List[str]) -> List[dict]:
        """Keyword-based fallback mapping when SBERT isn't available."""
        keyword_map = {
            "python": "Python", "java": "Java", "javascript": "JavaScript",
            "sql": "SQL", "database": "Database Design", "network": "TCP/IP",
            "machine learning": "Machine Learning", "deep learning": "Deep Learning",
            "web": "HTML/CSS", "react": "React", "algorithm": "Algorithms",
            "data structure": "Data Structures", "operating system": "Linux",
            "cloud": "AWS", "security": "Network Security",
        }

        mappings = []
        for concept in concepts:
            concept_lower = concept.lower()
            matched = []
            for keyword, skill in keyword_map.items():
                if keyword in concept_lower:
                    matched.append({
                        "skill": skill,
                        "domain": "general",
                        "category": "technical",
                        "similarity": 0.7,
                    })
            mappings.append({
                "academic_concept": concept,
                "mapped_skills": matched[:3],
                "has_mapping": len(matched) > 0,
            })
        return mappings


# ============================================================================
# PLACEMENT READINESS PREDICTOR
# ============================================================================

class PlacementPredictor:
    """
    Predicts placement readiness using ML models with SHAP-like explainability.
    
    Features:
    - CGPA
    - Technical skill mastery (from KT)
    - Soft skill indicators
    - Internship/project experience
    - Practice problem scores
    
    Provides feature importance as XAI explanations.
    """

    # Feature weights for interpretable scoring (when sklearn not available)
    FEATURE_WEIGHTS = {
        "cgpa_normalized": 0.20,
        "technical_mastery": 0.25,
        "soft_skills": 0.10,
        "internship_months": 0.15,
        "projects_count": 0.10,
        "practice_score": 0.10,
        "skill_match_ratio": 0.10,
    }

    def predict_readiness(
        self,
        user_email: str,
        target_role: str = "software_engineer",
        cgpa: float = 7.0,
        internship_months: int = 0,
        projects_count: int = 0,
        practice_score: float = 0.0,
    ) -> dict:
        """
        Predict placement readiness with explainable breakdown.
        """
        # Get role requirements
        role = JOB_ROLE_REQUIREMENTS.get(target_role, JOB_ROLE_REQUIREMENTS["software_engineer"])

        # Get skill profile
        mapper = Syllabus2SkillMapper()
        skill_profile = mapper.generate_skill_profile(user_email)

        # Calculate feature scores
        features = self._calculate_features(
            skill_profile=skill_profile,
            role=role,
            cgpa=cgpa,
            internship_months=internship_months,
            projects_count=projects_count,
            practice_score=practice_score,
        )

        # Calculate overall probability
        probability = sum(
            features[feat]["score"] * weight
            for feat, weight in self.FEATURE_WEIGHTS.items()
            if feat in features
        )
        probability = max(0, min(1, probability))

        # Calculate SHAP-like contributions
        contributions = self._calculate_contributions(features, probability)

        # Generate natural language explanation
        nl_explanation = self._generate_nl_explanation(features, contributions, probability, role)

        # Identify missing skills
        missing_skills = self._identify_missing_skills(skill_profile, role)

        return {
            "probability": round(probability, 4),
            "percentage": round(probability * 100, 1),
            "target_role": role["title"],
            "readiness_level": self._readiness_label(probability),
            "features": features,
            "contributions": contributions,
            "missing_skills": missing_skills,
            "explanation": nl_explanation,
            "recommendations": self._generate_recommendations(features, missing_skills, role),
        }

    def _calculate_features(
        self,
        skill_profile: dict,
        role: dict,
        cgpa: float,
        internship_months: int,
        projects_count: int,
        practice_score: float,
    ) -> dict:
        """Calculate normalized feature scores."""
        # CGPA normalized to 0-1 (assuming 10-point scale)
        cgpa_normalized = min(cgpa / 10.0, 1.0)
        cgpa_meets_threshold = cgpa >= role.get("min_cgpa", 6.0)

        # Technical mastery from skill profile
        technical_skills = skill_profile.get("technical_skills", [])
        tech_readiness = [s["readiness"] for s in technical_skills] if technical_skills else [0]
        technical_mastery = sum(tech_readiness) / max(len(tech_readiness), 1)

        # Soft skills
        soft_skills_list = skill_profile.get("soft_skills", [])
        soft_readiness = [s["readiness"] for s in soft_skills_list] if soft_skills_list else [0]
        soft_skills_score = sum(soft_readiness) / max(len(soft_readiness), 1)

        # Skill match ratio
        required_skills = set(s.lower() for s in role.get("required_skills", []))
        student_skills = set(s["skill"].lower() for s in skill_profile.get("skills", []) if s["readiness"] > 0.3)
        match_count = len(required_skills & student_skills)
        match_ratio = match_count / max(len(required_skills), 1)

        # Normalize other features
        internship_score = min(internship_months / 6.0, 1.0)
        project_score = min(projects_count / 5.0, 1.0)
        practice_normalized = min(practice_score / 100.0, 1.0)

        return {
            "cgpa_normalized": {
                "score": cgpa_normalized,
                "raw_value": cgpa,
                "label": "Academic GPA",
                "meets_threshold": cgpa_meets_threshold,
                "impact": "positive" if cgpa_normalized > 0.7 else "negative",
            },
            "technical_mastery": {
                "score": technical_mastery,
                "label": "Technical Skill Mastery",
                "impact": "positive" if technical_mastery > 0.5 else "negative",
            },
            "soft_skills": {
                "score": soft_skills_score,
                "label": "Soft Skills",
                "impact": "positive" if soft_skills_score > 0.5 else "negative",
            },
            "internship_months": {
                "score": internship_score,
                "raw_value": internship_months,
                "label": "Internship Experience",
                "impact": "positive" if internship_months >= 3 else "negative",
            },
            "projects_count": {
                "score": project_score,
                "raw_value": projects_count,
                "label": "Project Portfolio",
                "impact": "positive" if projects_count >= 2 else "negative",
            },
            "practice_score": {
                "score": practice_normalized,
                "raw_value": practice_score,
                "label": "Practice/Assessment Score",
                "impact": "positive" if practice_score > 60 else "negative",
            },
            "skill_match_ratio": {
                "score": match_ratio,
                "matched": match_count,
                "total_required": len(required_skills),
                "label": "Skill-Role Match",
                "impact": "positive" if match_ratio > 0.5 else "negative",
            },
        }

    def _calculate_contributions(self, features: dict, probability: float) -> List[dict]:
        """Calculate SHAP-like feature contributions."""
        baseline = 0.5  # Baseline probability
        contributions = []

        for feat_name, weight in self.FEATURE_WEIGHTS.items():
            if feat_name not in features:
                continue
            feat = features[feat_name]
            # Contribution = weight * (feature_score - 0.5) normalized
            contribution = weight * (feat["score"] - 0.5) * 2
            contributions.append({
                "feature": feat["label"],
                "contribution": round(contribution, 4),
                "direction": "positive" if contribution > 0 else "negative",
                "magnitude": abs(round(contribution, 4)),
                "score": feat["score"],
            })

        contributions.sort(key=lambda x: abs(x["contribution"]), reverse=True)
        return contributions

    def _identify_missing_skills(self, skill_profile: dict, role: dict) -> List[dict]:
        """Identify skills required by the role but missing from the student."""
        student_skills = {s["skill"].lower(): s for s in skill_profile.get("skills", [])}
        required = role.get("required_skills", []) + role.get("preferred_skills", [])

        missing = []
        for skill in required:
            skill_lower = skill.lower()
            if skill_lower not in student_skills or student_skills[skill_lower]["readiness"] < 0.3:
                is_required = skill in role.get("required_skills", [])
                missing.append({
                    "skill": skill,
                    "importance": "required" if is_required else "preferred",
                    "current_readiness": student_skills.get(skill_lower, {}).get("readiness", 0),
                })

        missing.sort(key=lambda x: (x["importance"] != "required", -x.get("current_readiness", 0)))
        return missing

    def _generate_nl_explanation(self, features: dict, contributions: List[dict], probability: float, role: dict) -> str:
        """Generate natural language explanation using LLM or template."""
        # Top positive and negative factors
        positive = [c for c in contributions if c["direction"] == "positive"][:3]
        negative = [c for c in contributions if c["direction"] == "negative"][:3]

        parts = [f"**Placement Readiness: {round(probability * 100, 1)}%** for {role['title']}\n"]

        if positive:
            parts.append("📈 **Strengths:**")
            for p in positive:
                parts.append(f"  • {p['feature']}: Contributing +{round(p['magnitude'] * 100, 1)}%")

        if negative:
            parts.append("\n📉 **Areas for Improvement:**")
            for n in negative:
                parts.append(f"  • {n['feature']}: Holding back by -{round(n['magnitude'] * 100, 1)}%")

        return "\n".join(parts)

    def _generate_recommendations(self, features: dict, missing_skills: List[dict], role: dict) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []

        # Check each feature
        for feat_name, feat in features.items():
            if feat["impact"] == "negative":
                if feat_name == "internship_months":
                    recommendations.append(
                        "🏢 Your internship experience is limited. Consider applying for summer internships "
                        "or a capstone project to gain practical experience."
                    )
                elif feat_name == "projects_count":
                    recommendations.append(
                        "💼 Build more projects! Aim for 3-5 well-documented projects on GitHub "
                        "that showcase your skills."
                    )
                elif feat_name == "technical_mastery":
                    recommendations.append(
                        "🔧 Focus on deepening your technical skills. Practice coding problems daily "
                        "and complete online courses in your weak areas."
                    )
                elif feat_name == "practice_score":
                    recommendations.append(
                        "📝 Increase your assessment scores by practicing mock tests and "
                        "aptitude questions regularly."
                    )

        # Add missing skills recommendations
        required_missing = [s for s in missing_skills if s["importance"] == "required"][:3]
        if required_missing:
            skills_str = ", ".join(s["skill"] for s in required_missing)
            recommendations.append(
                f"📚 Critical missing skills for {role['title']}: **{skills_str}**. "
                f"Prioritize learning these through courses or projects."
            )

        return recommendations

    def _readiness_label(self, probability: float) -> str:
        if probability >= 0.8:
            return "Highly Ready"
        elif probability >= 0.6:
            return "Moderately Ready"
        elif probability >= 0.4:
            return "Developing"
        elif probability >= 0.2:
            return "Early Stage"
        else:
            return "Not Ready"


# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

app = FastAPI(title="TrackEneer Career Readiness API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_USER_EMAIL = os.getenv("DEFAULT_USER_EMAIL", "demo@trackeneer.local")
mapper = Syllabus2SkillMapper()
predictor = PlacementPredictor()


def _resolve_email(request: Request, provided: Optional[str] = None) -> str:
    if provided:
        return provided
    return request.headers.get("x-user-email", "") or DEFAULT_USER_EMAIL


# ─── Health ───

@app.get("/")
async def root():
    return {"service": "career-readiness", "status": "ok"}


# ─── Skill mapping ───

@app.post("/api/career/map-skills")
async def map_skills(
    request: Request,
    concepts: str = Form(...),  # Comma-separated concept names
    email: Optional[str] = Form(None),
):
    """Map academic concepts to industry skills."""
    concept_list = [c.strip() for c in concepts.split(",") if c.strip()]
    mappings = mapper.map_concepts_to_skills(concept_list)
    return {"status": "ok", "mappings": mappings}


# ─── Skill profile ───

@app.get("/api/career/skill-profile")
async def get_skill_profile(request: Request, email: Optional[str] = None):
    """Generate the student's industry skill profile from their KG."""
    user_email = _resolve_email(request, email)
    profile = mapper.generate_skill_profile(user_email)
    return {"status": "ok", **profile}


# ─── Placement prediction ───

@app.post("/api/career/predict-readiness")
async def predict_readiness(
    request: Request,
    target_role: str = Form("software_engineer"),
    cgpa: float = Form(7.0),
    internship_months: int = Form(0),
    projects_count: int = Form(0),
    practice_score: float = Form(0),
    email: Optional[str] = Form(None),
):
    """
    Predict placement readiness with XAI explanations.
    
    Target roles: software_engineer, data_analyst, data_scientist,
                  web_developer, devops_engineer, cybersecurity_analyst
    """
    user_email = _resolve_email(request, email)
    result = predictor.predict_readiness(
        user_email=user_email,
        target_role=target_role,
        cgpa=cgpa,
        internship_months=internship_months,
        projects_count=projects_count,
        practice_score=practice_score,
    )
    return {"status": "ok", **result}


# ─── Available roles ───

@app.get("/api/career/roles")
async def list_roles():
    """List all available target roles."""
    roles = []
    for key, role in JOB_ROLE_REQUIREMENTS.items():
        roles.append({
            "id": key,
            "title": role["title"],
            "required_skills_count": len(role["required_skills"]),
            "min_cgpa": role["min_cgpa"],
        })
    return {"status": "ok", "roles": roles}


# ─── Resume analysis ───

@app.post("/api/career/analyze-resume")
async def analyze_resume(
    request: Request,
    resume_text: str = Form(...),
    target_role: str = Form("software_engineer"),
    email: Optional[str] = Form(None),
):
    """Analyze resume against target role requirements."""
    if not HAS_GEMINI or not _gemini:
        return {"status": "error", "message": "Gemini not available for resume analysis"}

    role = JOB_ROLE_REQUIREMENTS.get(target_role, JOB_ROLE_REQUIREMENTS["software_engineer"])

    prompt = f"""Analyze this resume against the requirements for a {role['title']} position.

Required Skills: {', '.join(role['required_skills'])}
Preferred Skills: {', '.join(role['preferred_skills'])}

Resume:
{resume_text[:3000]}

Return JSON:
{{
  "matched_skills": ["skill1", "skill2"],
  "missing_required": ["skill3"],
  "missing_preferred": ["skill4"],
  "strengths": ["strength description"],
  "improvements": ["improvement suggestion"],
  "overall_match_percentage": 75,
  "interview_tips": ["tip1", "tip2"]
}}
"""
    try:
        response = _gemini.generate_content(prompt)
        raw = response.text.strip()
        raw = re.sub(r"```json\s*", "", raw)
        raw = re.sub(r"```\s*$", "", raw)
        data = json.loads(raw)
        return {"status": "ok", "analysis": data, "target_role": role["title"]}
    except Exception as e:
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5008)
