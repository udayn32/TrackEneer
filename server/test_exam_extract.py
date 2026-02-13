"""Test exam timetable extraction with OCR + Groq AI"""
from document_processor import ExamTimetableParser

# Test with the uploaded exam timetable
parser = ExamTimetableParser()
pdf_path = 'uploads/documents/exam_timetable/20260118_234216_389155Exam_Time_Table-NOV_2025_CSE__IOT-CSBC___Regular__Sem._III__V___VII.pdf'

print(f"\n{'='*70}")
print(f"Testing Exam Timetable Extraction")
print(f"{'='*70}")
print(f"File: {pdf_path}\n")

exams = parser.parse(pdf_path)

print(f"\n{'='*70}")
print(f"RESULTS: Extracted {len(exams)} exams")
print(f"{'='*70}\n")

if exams:
    for i, exam in enumerate(exams[:15], 1):
        print(f"{i}. {exam.subject}")
        print(f"   📅 Date: {exam.date}")
        print(f"   🕐 Time: {exam.start_time or 'TBA'} - {exam.end_time or 'TBA'}")
        if exam.venue:
            print(f"   📍 Venue: {exam.venue}")
        print(f"   📝 Type: {exam.exam_type}")
        print()
    
    if len(exams) > 15:
        print(f"... and {len(exams) - 15} more exams")
else:
    print("❌ No exams extracted")
