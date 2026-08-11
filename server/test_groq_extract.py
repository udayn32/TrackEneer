"""Test Groq extraction directly"""
import json
from groq import Groq
import pdfplumber

GROQ_API_KEY = "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"

def test_groq():
    # Extract text from PDF
    pdf_path = r"C:\Users\himan\Downloads\Learning\Projects\TrackEneer Uday\TrackEneer\server\uploads\fa04c2fa-392a-4c37-9b91-5e6ca92ea3a9.pdf"
    
    with pdfplumber.open(pdf_path) as pdf:
        text = '\n'.join([p.extract_text() or '' for p in pdf.pages])
    
    print(f"Extracted {len(text)} chars from PDF")
    print(f"\nFirst 2000 chars:\n{text[:2000]}\n")
    
    client = Groq(api_key=GROQ_API_KEY)
    
    prompt = f"""Analyze this Mumbai University syllabus and extract ALL courses.

For EACH course found, return a JSON object with:
- code: course code (like CSC401, CSC402, CSL401 etc)
- name: full course name 
- modules: array of module names with hours like ["Linear Algebra (7 hrs)", "Complex Integration (7 hrs)"]
- topics: key topics from each module as array of strings
- total_hours: sum of all module hours (number)
- difficulty: "easy", "medium" or "hard"

Look for course codes like CSC401, CSC402, CSC403, CSC404, CSC405, CSL401, etc.
Look for Module/Unit sections with hours.

SYLLABUS TEXT:
{text[:15000]}

Return ONLY a valid JSON array of courses. Start with [ and end with ]."""

    print("Calling Groq API...")
    
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=4000
    )
    
    result = response.choices[0].message.content.strip()
    print(f"\n=== GROQ RESPONSE ({len(result)} chars) ===")
    print(result[:3000])
    print("..." if len(result) > 3000 else "")
    
    # Try to parse
    try:
        # Clean markdown
        if '```' in result:
            parts = result.split('```')
            for part in parts:
                if part.strip().startswith('json'):
                    result = part.strip()[4:]
                    break
                elif part.strip().startswith('['):
                    result = part.strip()
                    break
        
        # Find JSON array
        if '[' in result:
            start = result.index('[')
            bracket_count = 0
            end = start
            for i, c in enumerate(result[start:], start):
                if c == '[':
                    bracket_count += 1
                elif c == ']':
                    bracket_count -= 1
                    if bracket_count == 0:
                        end = i + 1
                        break
            result = result[start:end]
        
        courses = json.loads(result)
        print(f"\n✅ Successfully parsed {len(courses)} courses!")
        
        for i, c in enumerate(courses[:5], 1):
            print(f"\n{i}. {c.get('code', 'N/A')} - {c.get('name', 'Unknown')}")
            print(f"   Modules: {c.get('modules', [])[:3]}...")
            print(f"   Hours: {c.get('total_hours', 'N/A')}")
            
    except json.JSONDecodeError as e:
        print(f"\n❌ JSON parse error: {e}")
        print(f"Attempted to parse: {result[:500]}")

if __name__ == "__main__":
    test_groq()
