"""
Insights Module Backend - FastAPI endpoints for student guidance using Cohere AI
"""
import os
from fastapi import FastAPI, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import json
from pathlib import Path
import cohere
from typing import Optional

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
COHERE_API_KEY = "rM2zziYqveYXde5i74mQjLRSVU2NE22klhea4Xu1"
co = cohere.Client(COHERE_API_KEY)

INSIGHTS_FILE = Path("insights.json")
CACHE_DURATION = 24 * 60 * 60  # 24 hours in seconds

# Year mappings
YEAR_INFO = {
    "FE": {"full_name": "First Year Engineering", "focus": "Foundation & Basics"},
    "SE": {"full_name": "Second Year Engineering", "focus": "Core Subjects & Skills"},
    "TE": {"full_name": "Third Year Engineering", "focus": "Specialization & Projects"},
    "BE": {"full_name": "Final Year Engineering", "focus": "Placement & Advanced Topics"}
}

# Branch mappings
BRANCHES = {
    "Computer": "Computer Engineering",
    "IT": "Information Technology",
    "Electronics": "Electronics Engineering",
    "Mechanical": "Mechanical Engineering",
    "Civil": "Civil Engineering",
    "Electrical": "Electrical Engineering"
}

# --- Data Models ---
def load_insights():
    """Load insights data from JSON file"""
    if INSIGHTS_FILE.exists():
        with open(INSIGHTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_insights(insights):
    """Save insights data to JSON file"""
    with open(INSIGHTS_FILE, "w", encoding="utf-8") as f:
        json.dump(insights, f, indent=2, ensure_ascii=False)

def is_cache_valid(timestamp: str) -> bool:
    """Check if cached data is still valid"""
    try:
        cached_time = datetime.fromisoformat(timestamp)
        current_time = datetime.now()
        return (current_time - cached_time).total_seconds() < CACHE_DURATION
    except:
        return False

# --- AI Generation Functions ---
def generate_year_insights(year: str, branch: str = None) -> dict:
    """Generate personalized insights for a student based on their year and branch"""
    
    year_info = YEAR_INFO.get(year, {})
    branch_name = BRANCHES.get(branch, branch) if branch else "Engineering"
    
    prompt = f"""
You are an experienced academic counselor for engineering students at Xavier Institute of Engineering.

Generate a comprehensive preparation guide for a {year_info.get('full_name', year)} student in {branch_name}.

Please provide the following sections:

1. KEY FOCUS AREAS:
   - List 5-6 main focus areas for this year
   - Be specific to the year level and branch
   - Include both technical and soft skills

2. STUDY STRATEGY:
   - Recommended study approach for this year
   - Time management tips
   - Resource recommendations (books, online courses, etc.)
   - How to balance academics with other activities

3. TECHNICAL SKILLS TO DEVELOP:
   - 4-5 essential technical skills for this year
   - Specific tools/technologies to learn
   - How these skills help in future

4. PROJECT IDEAS:
   - 3-4 project ideas suitable for this level
   - Difficulty level and time required
   - Skills gained from each project

5. PLACEMENT PREPARATION:
   - When to start preparing (if applicable)
   - Key areas to focus on for placements
   - Companies that typically recruit at this level
   - Internship opportunities

6. EXTRACURRICULAR ACTIVITIES:
   - Recommended clubs/activities
   - Competitions to participate in
   - Networking opportunities

7. CAREER GUIDANCE:
   - Career paths available
   - Skills needed for different career options
   - Higher education opportunities

8. COMMON MISTAKES TO AVOID:
   - 3-4 common mistakes students make in this year
   - How to avoid them

Keep the tone motivational and practical. Use bullet points for clarity.
Make it specific to Xavier Institute of Engineering context where relevant.
"""

    try:
        response = co.chat(
            model='command-r-08-2024',
            message=prompt,
            max_tokens=2000,
            temperature=0.7
        )
        
        content = response.text.strip()
        
        return {
            "success": True,
            "year": year,
            "year_full_name": year_info.get('full_name', year),
            "branch": branch_name,
            "content": content,
            "generated_at": datetime.now().isoformat()
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "year": year,
            "branch": branch_name
        }

def generate_quick_tips(year: str) -> dict:
    """Generate quick tips for a specific year"""
    
    year_info = YEAR_INFO.get(year, {})
    
    prompt = f"""
Provide 5 quick, actionable tips for {year_info.get('full_name', year)} engineering students.

Make them:
- Specific and practical
- Easy to implement immediately
- Relevant to Xavier Institute of Engineering students
- Motivational

Format as a numbered list (1-5).
"""

    try:
        response = co.chat(
            model='command-r7b-12-2024',
            message=prompt,
            max_tokens=300,
            temperature=0.7
        )
        
        tips = response.text.strip()
        
        return {
            "success": True,
            "year": year,
            "tips": tips
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

# --- API Endpoints ---

@app.get("/")
def root():
    """Health check endpoint"""
    return {"status": "Insights module is running", "timestamp": datetime.now().isoformat()}

@app.post("/api/insights/generate")
async def generate_insights(
    year: str = Form(...),
    branch: str = Form(None)
):
    """Generate personalized insights for a student"""
    
    # Validate year
    if year not in YEAR_INFO:
        raise HTTPException(status_code=400, detail=f"Invalid year. Must be one of: {', '.join(YEAR_INFO.keys())}")
    
    try:
        insights_data = load_insights()
        cache_key = f"{year}_{branch or 'general'}"
        
        # Check cache
        if cache_key in insights_data and is_cache_valid(insights_data[cache_key].get("generated_at", "")):
            return {
                "message": "Retrieved from cache",
                "cached": True,
                **insights_data[cache_key]
            }
        
        # Generate new insights
        print(f"Generating insights for {year} - {branch or 'General'}...")
        result = generate_year_insights(year, branch)
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to generate insights"))
        
        # Cache the result
        insights_data[cache_key] = result
        save_insights(insights_data)
        
        return {
            "message": "Insights generated successfully",
            "cached": False,
            **result
        }
    
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"EXCEPTION in generate_insights: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/insights/quick-tips/{year}")
def get_quick_tips(year: str):
    """Get quick tips for a specific year"""
    
    if year not in YEAR_INFO:
        raise HTTPException(status_code=400, detail=f"Invalid year. Must be one of: {', '.join(YEAR_INFO.keys())}")
    
    try:
        result = generate_quick_tips(year)
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to generate tips"))
        
        return result
    
    except Exception as e:
        print(f"ERROR in get_quick_tips: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/insights/years")
def list_years():
    """List all available years with their info"""
    return {
        "years": [
            {
                "code": code,
                "full_name": info["full_name"],
                "focus": info["focus"]
            }
            for code, info in YEAR_INFO.items()
        ]
    }

@app.get("/api/insights/branches")
def list_branches():
    """List all available branches"""
    return {
        "branches": [
            {
                "code": code,
                "full_name": name
            }
            for code, name in BRANCHES.items()
        ]
    }

@app.delete("/api/insights/cache/{year}")
def clear_cache(year: str, branch: str = None):
    """Clear cached insights for a specific year/branch combination"""
    insights_data = load_insights()
    cache_key = f"{year}_{branch or 'general'}"
    
    if cache_key in insights_data:
        del insights_data[cache_key]
        save_insights(insights_data)
        return {"message": "Cache cleared successfully"}
    
    raise HTTPException(status_code=404, detail="No cached data found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5004)
