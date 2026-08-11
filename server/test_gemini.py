"""Test Gemini AI extraction"""
import google.generativeai as genai
import json
import re

genai.configure(api_key='AIzaSyCjdJbU8lCtZUT00P_uzQSrUw33tf9Ij6A')
model = genai.GenerativeModel('gemini-2.5-flash')

# Test simple extraction
test_text = """
Subject Code: IoTCSBCC701
Subject Name: Machine Learning & Blockchain

Course Objectives:
1. To learn the basic terminologies used in machine learning
2. To learn Feature Selection and various algorithms
3. To learn concepts of Neural Network and Deep Learning

Module I: Machine Learning Introduction
Module II: Feature Selection
Module III: Neural Networks and Deep Learning
Module IV: Introduction to Blockchain
Module V: Consensus Mechanism & Smart Contracts
Module VI: Application of Blockchain

Total Hours: 45
"""

prompt = """Extract course information from this syllabus text.

Return ONLY a JSON array (no explanation, no markdown):
[{"code": "COURSE_CODE", "name": "Course Name", "modules": ["Module 1", "Module 2"], "topics": ["topic1"], "total_hours": 40, "difficulty": "medium"}]

Syllabus text:
""" + test_text + """

JSON array:"""

print("Sending to Gemini...")
response = model.generate_content(prompt)
print("\nRaw response:")
print(response.text)
print("\n" + "="*50)

# Try to parse
text = response.text.strip()
print("\nParsing JSON...")

# Remove markdown
if '```' in text:
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        text = match.group(1).strip()

# Find array
array_match = re.search(r'(\[[\s\S]*\])', text)
if array_match:
    text = array_match.group(1)

try:
    result = json.loads(text)
    print("\nParsed result:")
    print(json.dumps(result, indent=2))
except Exception as e:
    print(f"\nParse error: {e}")
    print(f"Text was: {repr(text[:500])}")
