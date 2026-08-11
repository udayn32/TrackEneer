"""Test exam timetable extraction with Gemini AI."""
from document_processor import UniversalDocumentExtractor
import os

dp = UniversalDocumentExtractor()

# Find an exam timetable PDF
exam_folder = 'uploads/documents/exam_timetable'
if os.path.exists(exam_folder):
    pdfs = [f for f in os.listdir(exam_folder) if f.endswith('.pdf')]
    if pdfs:
        pdf_path = os.path.join(exam_folder, pdfs[0])
        print(f"Testing: {pdfs[0]}")
        
        result = dp.extract_any_pdf(pdf_path)
        
        print('=' * 60)
        print('EXAM TIMETABLE EXTRACTION RESULTS')
        print('=' * 60)
        print(f"Document Type: {result.get('document_type')}")
        print(f"Total Exams: {len(result.get('exams', []))}")
        print()
        
        for i, exam in enumerate(result.get('exams', [])[:10], 1):
            print(f"{i}. {exam.get('subject', 'Unknown Subject')}")
            print(f"   Code: {exam.get('subject_code', 'N/A')}")
            print(f"   Date: {exam.get('date', 'N/A')}")
            print(f"   Time: {exam.get('start_time', 'N/A')} - {exam.get('end_time', 'N/A')}")
            print()
    else:
        print("No exam PDFs found")
else:
    print(f"Folder not found: {exam_folder}")
