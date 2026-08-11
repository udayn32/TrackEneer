"""Test the Local NLP Extractor with real PDFs"""
import pdfplumber
from document_processor import ai_extractor, HAS_LAYOUTLM

print(f"LayoutLMv3 available: {HAS_LAYOUTLM}")

# Test with AIML Syllabus
print("=" * 60)
print("Testing with AIMLSyllabus.pdf")
print("=" * 60)

# Method 1: Direct PDF extraction (uses LayoutLMv3 if available)
print("\n--- Method 1: Direct PDF extraction ---")
results = ai_extractor.extract_syllabus_from_pdf(r'uploads/documents/syllabus/20260118_233902_AIMLSyllabus.pdf')

print(f"\nExtracted {len(results)} courses:")
for i, course in enumerate(results[:5]):
    print(f"\n{i+1}. {course['name']}")
    print(f"   Code: {course['code']}")
    print(f"   Hours: {course['total_hours']}, Difficulty: {course['difficulty']}")
    print(f"   Modules ({len(course['modules'])}): {course['modules'][:3]}")
    print(f"   Topics ({len(course['topics'])}): {course['topics'][:3]}")

# Test with MLBC Syllabus
print("\n" + "=" * 60)
print("Testing with MLBC.pdf")
print("=" * 60)

results2 = ai_extractor.extract_syllabus_from_pdf(r'uploads/documents/syllabus/20260120_155526_MLBC.pdf')

print(f"\nExtracted {len(results2)} courses:")
for i, course in enumerate(results2[:3]):
    print(f"\n{i+1}. {course['name']}")
    print(f"   Code: {course['code']}")
    print(f"   Hours: {course['total_hours']}, Difficulty: {course['difficulty']}")
    print(f"   Modules ({len(course['modules'])}): {course['modules'][:3]}")
    print(f"   Topics ({len(course['topics'])}): {course['topics'][:3]}")
