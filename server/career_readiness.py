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
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

from dotenv import load_dotenv
load_dotenv()  # loads .env from cwd (server/)

from typing import Optional, List

import httpx
from fastapi import FastAPI, Form, HTTPException, Query, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from ai_client import build_text_model
# Import career center service for unified company logic
from career_center_service import (
    resolve_user_email,
    fetch_company,
    store_company,
    is_cache_valid,
    list_companies,
    delete_company,
    generate_company_info,
    generate_company_score,
    get_alumni_data,
    _company_key,
)

# ─── PDF Extraction ───
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    pdfplumber = None
    HAS_PDFPLUMBER = False

# ─── Gemini ───
try:
    _gemini = build_text_model()
    HAS_GEMINI = _gemini is not None
except Exception:
    HAS_GEMINI = False
    _gemini = None

# ─── Brave Search ───
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
BRAVE_NEWS_URL   = "https://api.search.brave.com/res/v1/news/search"
BRAVE_VIDEO_URL  = "https://api.search.brave.com/res/v1/videos/search"

# ─── Graph Helpers ───
from graph_helpers import normalize_day


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
        raise HTTPException(status_code=503, detail="AI model is not available for resume analysis.")

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

    prompt = _build_resume_analysis_prompt(role, resume_text)

    try:
        response = _gemini.generate_content(prompt)
        data = _parse_resume_analysis_json(getattr(response, "text", ""))
        return {"status": "ok", "analysis": data, "target_role": role["title"], "extracted_chars": len(resume_text)}
    except Exception:
        try:
            retry_prompt = _build_resume_analysis_prompt(role, resume_text, strict_json=True)
            retry_response = _gemini.generate_content(retry_prompt)
            data = _parse_resume_analysis_json(getattr(retry_response, "text", ""))
            return {"status": "ok", "analysis": data, "target_role": role["title"], "extracted_chars": len(resume_text)}
        except Exception:
            fallback = _build_fallback_resume_analysis(role, resume_text)
            return {"status": "ok", "analysis": fallback, "target_role": role["title"], "extracted_chars": len(resume_text), "fallback": True}


def _build_resume_analysis_prompt(role: dict, resume_text: str, strict_json: bool = False) -> str:
    json_clause = (
        "Return only valid JSON. Do not use markdown fences. Do not add explanations before or after the JSON."
        if strict_json
        else "Return JSON:"
    )
    return f"""Analyze this resume against the requirements for a {role['title']} position.

Required Skills: {', '.join(role['required_skills'])}
Preferred Skills: {', '.join(role['preferred_skills'])}

Resume:
{resume_text[:3000]}

{json_clause}
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


def _build_fallback_resume_analysis(role: dict, resume_text: str) -> dict:
    """Produce a basic but stable resume analysis without relying on model JSON output."""
    normalized_resume = f" {resume_text.lower()} "

    def _present(skill: str) -> bool:
        variants = {skill.lower()}
        lowered = skill.lower()
        if lowered == "javascript":
            variants.update({"js", "node.js", "nodejs"})
        elif lowered == "html/css":
            variants.update({"html", "css"})
        elif lowered == "rest apis":
            variants.update({"rest api", "apis", "api development"})
        elif lowered == "ci/cd":
            variants.update({"ci", "cd", "github actions", "jenkins"})
        elif lowered == "aws":
            variants.update({"amazon web services"})
        elif lowered == "data structures":
            variants.update({"dsa", "data structure"})
        elif lowered == "algorithms":
            variants.update({"algorithm"})
        return any(f" {variant} " in normalized_resume for variant in variants)

    matched_required = [skill for skill in role["required_skills"] if _present(skill)]
    matched_preferred = [skill for skill in role["preferred_skills"] if _present(skill)]
    missing_required = [skill for skill in role["required_skills"] if skill not in matched_required]
    missing_preferred = [skill for skill in role["preferred_skills"] if skill not in matched_preferred]

    required_weight = 0.75
    preferred_weight = 0.25
    required_score = (len(matched_required) / max(1, len(role["required_skills"]))) * required_weight
    preferred_score = (len(matched_preferred) / max(1, len(role["preferred_skills"]))) * preferred_weight
    overall_match_percentage = int(round((required_score + preferred_score) * 100))

    strengths = []
    if matched_required:
        strengths.append(f"Your resume already shows core role skills such as {', '.join(matched_required[:4])}.")
    if re.search(r"\b(project|internship|experience|developer|engineer)\b", normalized_resume):
        strengths.append("Your resume appears to include project or experience signals that help in screening.")
    if re.search(r"\b(github|portfolio|hackathon|certification|certified)\b", normalized_resume):
        strengths.append("Portfolio, certifications, or public work can strengthen your profile.")

    improvements = []
    if missing_required:
        improvements.append(f"Add stronger evidence for key required skills like {', '.join(missing_required[:4])}.")
    if not re.search(r"\b(achievement|improved|reduced|increased|built|developed)\b", normalized_resume):
        improvements.append("Rewrite bullets to include actions and measurable outcomes.")
    if not re.search(r"\b(sql|database|api|cloud|docker|aws|react|python|java)\b", normalized_resume):
        improvements.append("Add more role-relevant technical detail to your projects and experience sections.")

    interview_tips = []
    if matched_required:
        interview_tips.append(f"Be ready to explain where you used {matched_required[0]} in a project or internship.")
    if missing_required:
        interview_tips.append(f"Prepare concise answers around {missing_required[0]} and how you are learning it.")
    interview_tips.append("Practice a 60-second walkthrough of your resume focusing on impact, tools, and problem-solving.")

    return {
        "matched_skills": matched_required + matched_preferred[:2],
        "missing_required": missing_required,
        "missing_preferred": missing_preferred,
        "strengths": strengths[:3] or ["Your resume contains some role-relevant technical signals."],
        "improvements": improvements[:3] or ["Add clearer evidence for role-specific skills and quantified impact."],
        "overall_match_percentage": max(0, min(overall_match_percentage, 100)),
        "interview_tips": interview_tips[:3],
    }


def _parse_resume_analysis_json(raw_text: str) -> dict:
    """Extract the first JSON object from a model response and normalize it."""
    raw = (raw_text or "").strip()
    if not raw:
        raise ValueError("The AI model returned an empty response.")

    raw = re.sub(r"```json\s*", "", raw, flags=re.IGNORECASE | re.MULTILINE)
    raw = re.sub(r"```+\s*", "", raw, flags=re.MULTILINE)
    raw = raw.strip()

    candidates = [raw]

    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.insert(0, raw[start : end + 1])

    decoder = json.JSONDecoder()
    parsed = None
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            parsed, _ = decoder.raw_decode(candidate)
            break
        except json.JSONDecodeError:
            continue

    if not isinstance(parsed, dict):
        raise ValueError("The AI response was not valid JSON for resume analysis.")

    def _list_of_strings(value):
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [line.strip("- ").strip() for line in value.splitlines() if line.strip()]
        return []

    try:
        match_pct = int(float(parsed.get("overall_match_percentage", 0)))
    except (TypeError, ValueError):
        match_pct = 0

    return {
        "matched_skills": _list_of_strings(parsed.get("matched_skills")),
        "missing_required": _list_of_strings(parsed.get("missing_required")),
        "missing_preferred": _list_of_strings(parsed.get("missing_preferred")),
        "strengths": _list_of_strings(parsed.get("strengths")),
        "improvements": _list_of_strings(parsed.get("improvements")),
        "overall_match_percentage": max(0, min(match_pct, 100)),
        "interview_tips": _list_of_strings(parsed.get("interview_tips")),
    }


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


async def _google_news_search(query: str, count: int = 6, item_type: str = "news") -> list[dict]:
    """Fetch lightweight live results from Google News RSS without an API key."""
    rss_url = (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    )
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            resp = await client.get(rss_url)
            resp.raise_for_status()
    except Exception:
        return []

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        return []

    items: list[dict] = []
    for entry in root.findall("./channel/item")[:count]:
        source_el = entry.find("source")
        items.append({
            "type": item_type,
            "title": (entry.findtext("title") or "").strip(),
            "url": (entry.findtext("link") or "").strip(),
            "description": (entry.findtext("description") or "").strip(),
            "age": (entry.findtext("pubDate") or "").strip(),
            "source": (source_el.text or "").strip() if source_el is not None else "Google News",
            "thumbnail": "",
        })
    return items


def _video_search_links(role_title: str, top_skills: list[str]) -> list[dict]:
    """Provide direct search links for video-style resources when no video API is configured."""
    queries = [
        f"{role_title} interview tips",
        f"{role_title} roadmap 2026",
    ]
    if top_skills:
        queries.insert(0, f"{' '.join(top_skills[:3])} tutorial")

    links: list[dict] = []
    for query in queries[:3]:
        links.append({
            "type": "video",
            "title": query,
            "url": f"https://www.youtube.com/results?search_query={quote_plus(query)}",
            "description": "Open this search to find recent walkthroughs, mock interviews, and explainers related to your target role.",
            "age": "Live search",
            "source": "YouTube Search",
            "thumbnail": "",
        })
    return links


async def _public_trends_search(role_title: str, top_skills: list[str]) -> dict:
    """Use public no-key search sources when Brave Search is unavailable."""
    skill_query = " OR ".join(top_skills) if top_skills else role_title
    career_query = f"{role_title} technology hiring trends 2026"
    interview_query = f"{role_title} interview preparation tips"

    import asyncio

    skill_news_task = _google_news_search(f"{skill_query} technology trends", 6, "news")
    career_web_task = _google_news_search(career_query, 6, "article")
    interview_web_task = _google_news_search(interview_query, 6, "tip")

    skill_news, career_web, interview_web = await asyncio.gather(
        skill_news_task,
        career_web_task,
        interview_web_task,
    )
    videos = _video_search_links(role_title, top_skills)

    results = {
        "status": "ok",
        "role": role_title,
        "skills_searched": top_skills,
        "fallback": False,
        "source": "public-search",
        "message": "Showing live results from public search sources because Brave Search is not configured.",
        "sections": {
            "skill_news": skill_news,
            "career_articles": career_web,
            "interview_tips": interview_web,
            "videos": videos,
        },
    }

    if any(results["sections"].values()):
        return results
    return _fallback_trends(role_title, top_skills)


def _fallback_trends(role_title: str, top_skills: list[str]) -> dict:
    """Return a UI-compatible fallback when live Brave Search is unavailable."""
    focus_skills = top_skills[:4]
    skill_label = ", ".join(focus_skills) if focus_skills else role_title

    return {
        "status": "ok",
        "role": role_title,
        "skills_searched": top_skills,
        "fallback": True,
        "message": "Live trend search is unavailable right now, so showing built-in guidance instead.",
        "sections": {
            "skill_news": [
                {
                    "type": "note",
                    "title": f"Focus your weekly practice on {skill_label}",
                    "url": "",
                    "description": "Spend this week strengthening the skills most closely tied to your target role through projects, revision, and interview-style problem solving.",
                    "age": "TrackEneer guidance",
                    "source": "TrackEneer",
                    "thumbnail": "",
                },
                {
                    "type": "note",
                    "title": f"Build one proof-of-work item for {role_title}",
                    "url": "",
                    "description": "Create or improve a small portfolio project, GitHub repo, case study, or resume bullet that demonstrates measurable progress for this role.",
                    "age": "TrackEneer guidance",
                    "source": "TrackEneer",
                    "thumbnail": "",
                },
            ],
            "career_articles": [
                {
                    "type": "article",
                    "title": f"What recruiters usually expect from an entry-level {role_title}",
                    "url": "",
                    "description": "Review core fundamentals, communication clarity, and project evidence. Employers usually value clear basics plus one or two standout strengths over broad but shallow coverage.",
                    "age": "Evergreen",
                    "source": "TrackEneer",
                    "thumbnail": "",
                },
                {
                    "type": "article",
                    "title": "Turn resume gaps into a 2-week improvement plan",
                    "url": "",
                    "description": "Choose the top missing skills from your analysis, study them in short focused blocks, and convert each improvement into a visible project or quantified resume point.",
                    "age": "Evergreen",
                    "source": "TrackEneer",
                    "thumbnail": "",
                },
            ],
            "interview_tips": [
                {
                    "type": "tip",
                    "title": f"Prepare concise stories for {role_title} interviews",
                    "url": "",
                    "description": "Practice 3 to 5 examples covering problem solving, teamwork, learning speed, and ownership. Keep each answer short, structured, and outcome-focused.",
                    "age": "Practice now",
                    "source": "TrackEneer",
                    "thumbnail": "",
                },
                {
                    "type": "tip",
                    "title": "Revise fundamentals before advanced topics",
                    "url": "",
                    "description": "Interviewers usually notice weak fundamentals first. Revisit concepts, common mistakes, and applied examples before spending time on edge-case topics.",
                    "age": "Practice now",
                    "source": "TrackEneer",
                    "thumbnail": "",
                },
            ],
            "videos": [
                {
                    "type": "video",
                    "title": f"Record a mock explanation for a key {role_title} concept",
                    "url": "",
                    "description": "Use your phone or laptop to explain one core concept in under 3 minutes. Replay it and tighten clarity, confidence, and structure.",
                    "age": "Try today",
                    "source": "TrackEneer",
                    "thumbnail": "",
                },
            ],
        },
    }


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
    role_title = JOB_ROLE_REQUIREMENTS.get(role, {}).get("title", role.replace("_", " ").title())
    top_skills = skills[:6] if skills else []

    if not BRAVE_API_KEY:
        return await _public_trends_search(role_title, top_skills)

    # Build search queries from skills
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


# ─── Company Research & Alumni (Unified Career Center) ───

@app.post("/api/career/companies/generate")
async def generate_company_profile(
    request: Request,
    company_name: str = Form(...),
    website: str = Form(None),
    day: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
):
    """Generate company profile using Gemini AI with caching."""
    try:
        user_email = resolve_user_email(request, email)
        day_iso = normalize_day(day) if day else None
        company_key = _company_key(company_name)

        # Check cache first
        cached = fetch_company(company_key, user_email, day_iso)
        if cached and is_cache_valid(cached.get("generated_at", "")):
            return {
                "message": "Retrieved from cache",
                "cached": True,
                **cached
            }
        
        # Generate new information
        print(f"Generating information for {company_name}...")
        company_info = generate_company_info(company_name, website)
        
        if not company_info["success"]:
            error_msg = company_info.get("error", "Failed to generate information")
            print(f"ERROR: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)
        
        # Generate score
        print(f"Generating score for {company_name}...")
        score_info = generate_company_score(company_name, company_info)
        company_info["score_info"] = score_info
        
        # Store in cache
        store_company(company_key, company_info, user_email, day_iso)

        return {
            "message": "Information generated successfully",
            "cached": False,
            "ownerEmail": user_email,
            "dayDate": day_iso,
            **company_info
        }
    
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"EXCEPTION in generate_company_profile: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/career/companies/{company_name}")
def get_company_profile(
    company_name: str,
    request: Request,
    day: Optional[str] = None,
    email: Optional[str] = None,
):
    """Get cached company profile."""
    company_key = _company_key(company_name)
    user_email = resolve_user_email(request, email)
    day_iso = normalize_day(day) if day else None
    company_info = fetch_company(company_key, user_email, day_iso)

    if not company_info:
        raise HTTPException(status_code=404, detail="Company not found. Please generate information first.")

    return {
        "cached": True,
        "cache_valid": is_cache_valid(company_info.get("generated_at", "")),
        **company_info
    }


@app.get("/api/career/companies")
def list_cached_companies(request: Request, day: Optional[str] = None, email: Optional[str] = None):
    """List all cached companies for the user."""
    user_email = resolve_user_email(request, email)
    day_iso = normalize_day(day) if day else None
    
    companies_data = list_companies(user_email, day_iso)
    
    return {"companies": companies_data, "total": len(companies_data)}


@app.delete("/api/career/companies/{company_name}")
def delete_cached_company(
    company_name: str,
    request: Request,
    day: Optional[str] = None,
    email: Optional[str] = None,
):
    """Delete a cached company profile."""
    company_key = _company_key(company_name)
    user_email = resolve_user_email(request, email)
    day_iso = normalize_day(day) if day else None
    
    deleted = delete_company(company_key, user_email, day_iso)
    
    if deleted:
        return {"message": "Company cache deleted successfully"}

    raise HTTPException(status_code=404, detail="Company not found")


@app.get("/api/career/alumni")
def get_alumni_list():
    """Get alumni placement data."""
    alumni = get_alumni_data()
    return {"alumni": alumni}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
