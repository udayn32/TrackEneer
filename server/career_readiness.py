"""
Career Readiness & Syllabus2Skill Engine
==========================================

Bridges academic learning to industry employment through:

1. Syllabus2Skill Pipeline – Maps academic concepts to ESCO/O*NET skills
2. Placement Prediction – Rule-based readiness scoring with explanations
3. Skill Gap Analysis – Delta between student profile and target role
4. XAI Feedback – Natural language explanations of scoring
5. Resume Analysis – AI-powered resume vs job description comparison

Architecture:
  Academic Concepts (KG) → SBERT Encoding → Cosine Alignment → ESCO/O*NET Skills
  Student Profile (Features) → Rule-Based Scorer → Placement Probability → NL Feedback
"""

from __future__ import annotations

import json
import os
import re

from dotenv import load_dotenv
load_dotenv()  # loads .env from cwd (server/)

from typing import Optional, List

import httpx
from fastapi import FastAPI, Form, HTTPException, Query, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

# ─── PDF Extraction ───
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    pdfplumber = None
    HAS_PDFPLUMBER = False

# ─── Gemini ───
try:
    import google.generativeai as genai
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        _gemini = genai.GenerativeModel("gemini-2.5-flash")
        HAS_GEMINI = True
    else:
        HAS_GEMINI = False
        _gemini = None
except ImportError:
    HAS_GEMINI = False
    _gemini = None

# ─── Brave Search ───
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
BRAVE_NEWS_URL   = "https://api.search.brave.com/res/v1/news/search"
BRAVE_VIDEO_URL  = "https://api.search.brave.com/res/v1/videos/search"


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


# ─── Health ───

@app.get("/")
async def root():
    return {"service": "career-readiness", "status": "ok"}


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


# ─── Resume PDF upload ───

@app.post("/api/career/analyze-resume-pdf")
async def analyze_resume_pdf(
    request: Request,
    file: UploadFile = File(...),
    target_role: str = Form("software_engineer"),
    email: Optional[str] = Form(None),
):
    """Extract text from an uploaded PDF and analyze it against a target role."""
    if not HAS_PDFPLUMBER:
        raise HTTPException(status_code=501, detail="pdfplumber is not installed. Run: pip install pdfplumber")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    if not HAS_GEMINI or not _gemini:
        raise HTTPException(status_code=503, detail="Gemini is not available for resume analysis.")

    # Read and extract text from PDF
    contents = await file.read()
    import io
    resume_text = ""
    try:
        with pdfplumber.open(io.BytesIO(contents)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    resume_text += page_text + "\n"
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to extract text from PDF: {e}")

    if not resume_text.strip():
        raise HTTPException(status_code=422, detail="No readable text found in the PDF. Try a text-based PDF (not a scanned image).")

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
        raw = re.sub(r"```json\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"```\s*", "", raw, flags=re.MULTILINE)
        data = json.loads(raw.strip())
        return {"status": "ok", "analysis": data, "target_role": role["title"], "extracted_chars": len(resume_text)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Brave Search helpers ───

async def _brave_fetch(url: str, query: str, count: int = 8) -> list[dict]:
    """Call a Brave Search endpoint and return normalised results."""
    if not BRAVE_API_KEY:
        return []
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": BRAVE_API_KEY,
    }
    params = {"q": query, "count": count, "text_decorations": False, "safesearch": "moderate"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []

    items: list[dict] = []
    # Web results
    if "web" in data and "results" in data["web"]:
        for r in data["web"]["results"]:
            items.append({
                "type": "web",
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "description": r.get("description", ""),
                "age": r.get("age", ""),
                "thumbnail": (r.get("thumbnail") or {}).get("src", ""),
            })
    # News results
    if "results" in data and url == BRAVE_NEWS_URL:
        for r in data["results"]:
            items.append({
                "type": "news",
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "description": r.get("description", ""),
                "age": r.get("age", ""),
                "source": (r.get("meta_url") or {}).get("hostname", ""),
                "thumbnail": (r.get("thumbnail") or {}).get("src", ""),
            })
    # Video results
    if "results" in data and url == BRAVE_VIDEO_URL:
        for r in data["results"]:
            items.append({
                "type": "video",
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "description": r.get("description", ""),
                "age": r.get("age", ""),
                "thumbnail": (r.get("thumbnail") or {}).get("src", ""),
            })
    return items


@app.post("/api/career/trends")
async def get_trends(
    skills: List[str] = Form([]),
    role: str = Form("software_engineer"),
):
    """
    Fetch latest trends from Brave Search based on user skills / role.
    Searches for:
      1. Skill-specific news & articles
      2. Interview tips & career advice videos/blogs
    """
    if not BRAVE_API_KEY:
        raise HTTPException(status_code=503, detail="Brave Search API key is not configured. Add BRAVE_API_KEY to your .env file.")

    role_title = JOB_ROLE_REQUIREMENTS.get(role, {}).get("title", role.replace("_", " ").title())

    # Build search queries from skills
    top_skills = skills[:6] if skills else []
    skill_query = " OR ".join(top_skills) if top_skills else role_title
    career_query = f"{role_title} latest trends technology 2025 2026"
    interview_query = f"{role_title} interview tips preparation guide"
    video_query = f"{role_title} interview tips career advice"

    # Fire all searches in parallel
    import asyncio
    skill_news_task = _brave_fetch(BRAVE_NEWS_URL, f"{skill_query} technology trends", 6)
    career_web_task = _brave_fetch(BRAVE_SEARCH_URL, career_query, 6)
    interview_web_task = _brave_fetch(BRAVE_SEARCH_URL, interview_query, 6)
    video_task = _brave_fetch(BRAVE_VIDEO_URL, video_query, 6)

    skill_news, career_web, interview_web, videos = await asyncio.gather(
        skill_news_task, career_web_task, interview_web_task, video_task
    )

    return {
        "status": "ok",
        "role": role_title,
        "skills_searched": top_skills,
        "sections": {
            "skill_news": skill_news,
            "career_articles": career_web,
            "interview_tips": interview_web,
            "videos": videos,
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
