"""
Placement Module Backend - FastAPI endpoints for company research using Gemini AI
"""
import os
from fastapi import FastAPI, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import json
from pathlib import Path
import google.generativeai as genai
from typing import Optional
import re

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
# API Key from Google AI Studio - Placement module
GEMINI_API_KEY = "AIzaSyCjdJbU8lCtZUT00P_uzQSrUw33tf9Ij6A"
genai.configure(api_key=GEMINI_API_KEY)
# Using Gemini 2.5 Flash - fast and efficient
model = genai.GenerativeModel('gemini-2.5-flash')

COMPANIES_FILE = Path("companies.json")
CACHE_DURATION = 24 * 60 * 60  # 24 hours in seconds

# --- Data Models ---
def load_companies():
    """Load companies data from JSON file"""
    if COMPANIES_FILE.exists():
        with open(COMPANIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_companies(companies):
    """Save companies data to JSON file"""
    with open(COMPANIES_FILE, "w", encoding="utf-8") as f:
        json.dump(companies, f, indent=2, ensure_ascii=False)

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
    company_name: str = Form(...),
    website: str = Form(None)
):
    """Generate placement information for a company using Gemini AI"""
    
    try:
        companies = load_companies()
        company_key = company_name.lower().strip()
        
        # Check cache
        if company_key in companies and is_cache_valid(companies[company_key].get("generated_at", "")):
            return {
                "message": "Retrieved from cache",
                "cached": True,
                **companies[company_key]
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
        
        # Cache the result
        companies[company_key] = company_info
        save_companies(companies)
        
        return {
            "message": "Information generated successfully",
            "cached": False,
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
def get_company_info(company_name: str):
    """Get cached company information"""
    companies = load_companies()
    company_key = company_name.lower().strip()
    
    if company_key not in companies:
        raise HTTPException(status_code=404, detail="Company not found. Please generate information first.")
    
    company_info = companies[company_key]
    
    return {
        "cached": True,
        "cache_valid": is_cache_valid(company_info.get("generated_at", "")),
        **company_info
    }

@app.get("/api/placement/companies")
def list_companies():
    """List all cached companies"""
    companies = load_companies()
    
    company_list = []
    for key, info in companies.items():
        company_list.append({
            "company_name": info.get("company_name", key),
            "website": info.get("website"),
            "generated_at": info.get("generated_at"),
            "cache_valid": is_cache_valid(info.get("generated_at", "")),
            "score": info.get("score_info", {}).get("score", 0)
        })
    
    return {"companies": company_list, "total": len(company_list)}

@app.delete("/api/placement/company/{company_name}")
def delete_company_cache(company_name: str):
    """Delete cached company information"""
    companies = load_companies()
    company_key = company_name.lower().strip()
    
    if company_key in companies:
        del companies[company_key]
        save_companies(companies)
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
