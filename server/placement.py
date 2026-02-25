"""Placement module backed by Neo4j for caching Gemini AI company insights."""

import json
import os
import re
from datetime import datetime
from typing import Optional

import google.generativeai as genai
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from db import get_driver
from graph_helpers import ensure_user_and_day, normalize_day

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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set. Add it to your .env file.")
genai.configure(api_key=GEMINI_API_KEY)
# Using Gemini 2.5 Flash - fast and efficient
model = genai.GenerativeModel('gemini-2.5-flash')

CACHE_DURATION = 24 * 60 * 60  # 24 hours in seconds


driver = get_driver()

DEFAULT_USER_EMAIL = os.getenv("DEFAULT_USER_EMAIL", "demo@trackeneer.local")


def _resolve_user_email(request: Request, provided: Optional[str] = None) -> str:
    email = provided or request.headers.get("x-user-email") or request.headers.get("X-User-Email")
    if not email:
        email = DEFAULT_USER_EMAIL
    if not email:
        raise HTTPException(status_code=400, detail="User email is required")
    return email.strip().lower()


def _company_key(name: str) -> str:
    return name.lower().strip()


def _serialize_company(node) -> dict:
    sections = json.loads(node.get("sections", "{}")) if node.get("sections") else {}
    score_info = json.loads(node.get("scoreInfo", "{}")) if node.get("scoreInfo") else {}
    return {
        "success": True,
        "company_name": node.get("companyName"),
        "website": node.get("website"),
        "sections": sections,
        "raw_content": node.get("rawContent"),
        "generated_at": node.get("generatedAt"),
        "score_info": score_info,
    }


def _fetch_company(company_key: str, email: str, day: str) -> Optional[dict]:
    with driver.session() as session:
        day_iso = ensure_user_and_day(session, email, day=day)
        record = session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(d:Day {date: date($day), email: $email})-[:HAS_COMPANY]->(c:Company {key: $key, ownerEmail: $email, dayDate: $day})
            RETURN c
            """,
            key=company_key,
            email=email,
            day=day_iso,
        ).single()
        if record:
            return _serialize_company(record["c"])
        return None


def _store_company(company_key: str, data: dict, email: str, day: str) -> None:
    sections_json = json.dumps(data.get("sections", {}), ensure_ascii=False)
    score_info_json = json.dumps(data.get("score_info", {}), ensure_ascii=False)
    with driver.session() as session:
        day_iso = ensure_user_and_day(session, email, day=day)
        session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(d:Day {date: date($day), email: $email})
            MERGE (d)-[:HAS_COMPANY]->(c:Company {key: $key, ownerEmail: $email, dayDate: $day})
            SET c += {
                companyName: $company_name,
                website: $website,
                sections: $sections,
                rawContent: $raw_content,
                generatedAt: $generated_at,
                scoreInfo: $score_info
            }
            """,
            key=company_key,
            company_name=data.get("company_name"),
            website=data.get("website"),
            sections=sections_json,
            raw_content=data.get("raw_content"),
            generated_at=data.get("generated_at"),
            score_info=score_info_json,
            email=email,
            day=day_iso,
        )

def is_cache_valid(timestamp: str) -> bool:
    """Check if cached data is still valid"""
    try:
        cached_time = datetime.fromisoformat(timestamp)
        current_time = datetime.now()
        return (current_time - cached_time).total_seconds() < CACHE_DURATION
    except:
        return False

# --- AI Generation Functions ---
def generate_company_info(company_name: str, website: str = None) -> dict:
    """Generate company information using Gemini AI"""
    
    website_info = f" (Website: {website})" if website else ""
    
    prompt = f"""
You are a career counselor and placement expert. Provide detailed, accurate information about {company_name}{website_info} for engineering students preparing for placements.

Please provide the following in a well-structured format:

1. VISION AND MISSION:
   - Company Vision (2-3 sentences)
   - Company Mission (2-3 sentences)
   - Core Values (3-5 points)

2. PLACEMENT PROCESS:
   - Eligibility Criteria (CGPA, branches, etc.)
   - Number of Rounds (specify each round)
   - Round 1: [Type] - Description
   - Round 2: [Type] - Description
   - Round 3: [Type] - Description (if applicable)
   - Round 4: [Type] - Description (if applicable)
   - Selection Timeline (how long the process takes)
   - Tips for Preparation (3-5 specific tips)

3. COMPANY REVIEW:
   - Work Culture (2-3 sentences)
   - Career Growth Opportunities (2-3 sentences)
   - Average Salary Package (for freshers)
   - Learning & Development Programs
   - Work-Life Balance Rating (out of 5)
   - Employee Benefits (list key benefits)
   - Alumni Testimonials/Reviews (2-3 positive aspects)
   - Areas for Improvement (1-2 honest points)

Format your response clearly with proper sections and bullet points. Be specific and practical.
"""

    try:
        response = model.generate_content(prompt)
        content = response.text
        
        # Parse the response into structured sections
        sections = {
            "vision_mission": "",
            "placement_process": "",
            "company_review": ""
        }
        
        # Extract sections using regex
        vision_match = re.search(r'1\.\s*VISION AND MISSION:(.*?)(?=2\.\s*PLACEMENT PROCESS:|\Z)', content, re.DOTALL)
        process_match = re.search(r'2\.\s*PLACEMENT PROCESS:(.*?)(?=3\.\s*COMPANY REVIEW:|\Z)', content, re.DOTALL)
        review_match = re.search(r'3\.\s*COMPANY REVIEW:(.*?)$', content, re.DOTALL)
        
        if vision_match:
            sections["vision_mission"] = vision_match.group(1).strip()
        if process_match:
            sections["placement_process"] = process_match.group(1).strip()
        if review_match:
            sections["company_review"] = review_match.group(1).strip()
        
        # If sections couldn't be parsed, use the full content
        if not any(sections.values()):
            sections = {
                "vision_mission": content,
                "placement_process": "Please refer to the vision and mission section above.",
                "company_review": "Please refer to the vision and mission section above."
            }
        
        return {
            "success": True,
            "company_name": company_name,
            "website": website,
            "sections": sections,
            "raw_content": content,
            "generated_at": datetime.now().isoformat()
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "company_name": company_name
        }

def generate_company_score(company_name: str, company_info: dict) -> dict:
    """Generate an overall company score and rating using Gemini AI"""
    
    prompt = f"""
Based on the following information about {company_name}, provide:
1. An overall placement score out of 10
2. Key strengths (3 points)
3. Key considerations (2 points)
4. A one-line recommendation

Company Information:
{company_info.get('raw_content', '')}

Provide your response in this exact format:
SCORE: [number]/10
STRENGTHS:
- [strength 1]
- [strength 2]
- [strength 3]
CONSIDERATIONS:
- [consideration 1]
- [consideration 2]
RECOMMENDATION: [one line recommendation for students]
"""

    try:
        response = model.generate_content(prompt)
        content = response.text
        
        # Parse score
        score_match = re.search(r'SCORE:\s*(\d+(?:\.\d+)?)\s*/\s*10', content)
        score = float(score_match.group(1)) if score_match else 7.5
        
        # Parse strengths
        strengths_match = re.search(r'STRENGTHS:(.*?)(?=CONSIDERATIONS:|$)', content, re.DOTALL)
        strengths = []
        if strengths_match:
            strengths_text = strengths_match.group(1).strip()
            strengths = [s.strip('- ').strip() for s in strengths_text.split('\n') if s.strip().startswith('-')]
        
        # Parse considerations
        considerations_match = re.search(r'CONSIDERATIONS:(.*?)(?=RECOMMENDATION:|$)', content, re.DOTALL)
        considerations = []
        if considerations_match:
            considerations_text = considerations_match.group(1).strip()
            considerations = [c.strip('- ').strip() for c in considerations_text.split('\n') if c.strip().startswith('-')]
        
        # Parse recommendation
        recommendation_match = re.search(r'RECOMMENDATION:\s*(.+?)(?:\n|$)', content)
        recommendation = recommendation_match.group(1).strip() if recommendation_match else "Consider applying based on your career goals."
        
        return {
            "score": score,
            "strengths": strengths[:3],
            "considerations": considerations[:2],
            "recommendation": recommendation
        }
    
    except Exception as e:
        return {
            "score": 7.5,
            "strengths": ["Reputed company", "Good learning opportunities", "Career growth potential"],
            "considerations": ["Research specific role requirements", "Prepare thoroughly for interviews"],
            "recommendation": "A good opportunity worth exploring."
        }

# --- API Endpoints ---

@app.get("/")
def root():
    """Health check endpoint"""
    return {"status": "Placement module is running", "timestamp": datetime.now().isoformat()}

@app.post("/api/placement/generate")
async def generate_placement_info(
    request: Request,
    company_name: str = Form(...),
    website: str = Form(None),
    day: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
):
    """Generate placement information for a company using Gemini AI"""
    
    try:
        user_email = _resolve_user_email(request, email)
        day_iso = normalize_day(day)
        company_key = _company_key(company_name)

        cached = _fetch_company(company_key, user_email, day_iso)
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
        
        _store_company(company_key, company_info, user_email, day_iso)

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
        print(f"EXCEPTION in generate_placement_info: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/placement/company/{company_name}")
def get_company_info(
    company_name: str,
    request: Request,
    day: Optional[str] = None,
    email: Optional[str] = None,
):
    """Get cached company information"""
    company_key = _company_key(company_name)
    user_email = _resolve_user_email(request, email)
    day_iso = normalize_day(day)
    company_info = _fetch_company(company_key, user_email, day_iso)

    if not company_info:
        raise HTTPException(status_code=404, detail="Company not found. Please generate information first.")

    return {
        "cached": True,
        "cache_valid": is_cache_valid(company_info.get("generated_at", "")),
        **company_info
    }

@app.get("/api/placement/companies")
def list_companies(request: Request, day: Optional[str] = None, email: Optional[str] = None):
    """List all cached companies"""
    user_email = _resolve_user_email(request, email)
    day_iso = normalize_day(day)
    with driver.session() as session:
        day_iso = ensure_user_and_day(session, user_email, day=day_iso)
        records = session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(d:Day {date: date($day), email: $email})-[:HAS_COMPANY]->(c:Company)
            RETURN c
            ORDER BY c.companyName
            """,
            email=user_email,
            day=day_iso,
        )
        companies = []
        for record in records:
            node = record["c"]
            info = _serialize_company(node)
            companies.append({
                "company_name": info.get("company_name") or node.get("key"),
                "website": info.get("website"),
                "generated_at": info.get("generated_at"),
                "cache_valid": is_cache_valid(info.get("generated_at", "")),
                "score": info.get("score_info", {}).get("score", 0),
            })

    return {"companies": companies, "total": len(companies)}

@app.delete("/api/placement/company/{company_name}")
def delete_company_cache(
    company_name: str,
    request: Request,
    day: Optional[str] = None,
    email: Optional[str] = None,
):
    """Delete cached company information"""
    company_key = _company_key(company_name)
    user_email = _resolve_user_email(request, email)
    day_iso = normalize_day(day)
    with driver.session() as session:
        day_iso = ensure_user_and_day(session, user_email, day=day_iso)
        deleted = session.run(
            """
            MATCH (u:User {email: $email})-[:HAS_DAY]->(d:Day {date: date($day), email: $email})-[:HAS_COMPANY]->(c:Company {key: $key, ownerEmail: $email, dayDate: $day})
            WITH c
            DETACH DELETE c
            RETURN count(c) AS removed
            """,
            key=company_key,
            email=user_email,
            day=day_iso,
        ).single()

    if deleted["removed"]:
        return {"message": "Company cache deleted successfully"}

    raise HTTPException(status_code=404, detail="Company not found")

@app.get("/api/placement/alumni")
def get_alumni_data():
    """Get alumni data for Xavier Institute of Engineering"""
    # Xavier Institute of Engineering Alumni Placements
    alumni = [
        {
            "name": "Arjun Deshmukh",
            "batch": "2024",
            "company": "TCS",
            "role": "Software Engineer",
            "package": "7.5 LPA",
            "avatar": "👨‍💻"
        },
        {
            "name": "Priya Kadam",
            "batch": "2024",
            "company": "Infosys",
            "role": "Systems Engineer",
            "package": "6.2 LPA",
            "avatar": "👩‍💼"
        },
        {
            "name": "Rohan Mehta",
            "batch": "2023",
            "company": "Wipro",
            "role": "Project Engineer",
            "package": "6.8 LPA",
            "avatar": "👨‍💼"
        },
        {
            "name": "Sneha Patil",
            "batch": "2024",
            "company": "Accenture",
            "role": "Associate Software Engineer",
            "package": "5.5 LPA",
            "avatar": "�‍�"
        },
        {
            "name": "Aditya Shah",
            "batch": "2023",
            "company": "L&T Infotech",
            "role": "Graduate Engineer Trainee",
            "package": "6 LPA",
            "avatar": "👨‍🔧"
        },
        {
            "name": "Neha Joshi",
            "batch": "2024",
            "company": "Cognizant",
            "role": "Programmer Analyst",
            "package": "5.8 LPA",
            "avatar": "👩‍💻"
        }
    ]
    
    return {"alumni": alumni}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5003)
