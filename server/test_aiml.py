"""Test AIML syllabus extraction with HYBRID pipeline."""
from document_processor import UniversalDocumentExtractor, HybridPDFExtractor

# Test hybrid extractor directly first
print("=" * 60)
print("TESTING HYBRID EXTRACTOR")
print("=" * 60)

hybrid = HybridPDFExtractor()
result = hybrid.extract('uploads/documents/syllabus/20260121_130547_AIMLSyllabus.pdf')
print(f"Extraction Method: {result['method']}")
print(f"Quality Score: {result['quality_score']:.1f} chars/page")
print(f"Page Count: {result['page_count']}")
print(f"Tables Found: {len(result['tables'])}")
print(f"Text Length: {len(result['text'])} characters")
print()

# Now test full pipeline
print("=" * 60)
print("TESTING FULL EXTRACTION PIPELINE")
print("=" * 60)

dp = UniversalDocumentExtractor()
result = dp.extract_any_pdf('uploads/documents/syllabus/20260121_130547_AIMLSyllabus.pdf')

print(f"Document Type: {result.get('document_type')}")
print(f"Extraction Method: {result.get('extraction_method')}")
print(f"Quality Score: {result.get('quality_score', 0):.1f}")
print(f"Total Subjects: {len(result.get('subjects', []))}")
print()

for i, s in enumerate(result.get('subjects', [])[:5], 1):
    print(f"{i}. {s.get('name')}")
    print(f"   Code: {s.get('code')}")
    print(f"   Modules: {len(s.get('modules', []))}")
    print(f"   Topics: {len(s.get('topics', []))}")
    print(f"   Hours: {s.get('total_hours', 'N/A')}")
    print()
