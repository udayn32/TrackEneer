"""Debug: show exactly what candidates are extracted and why some are filtered."""
from knowledge_graph import EduKGPipeline, ConceptExtractor
import pdfplumber, re

pdf_path = "uploads/kg/3d43e1f9-e93e-48f5-b9a0-c1df05323624_Artificial_Intelligence_Notes.pdf"
with pdfplumber.open(pdf_path) as pdf:
    text = ""
    for p in pdf.pages:
        t = p.extract_text()
        if t: text += t + "\n"

# Preprocess
pipeline = EduKGPipeline()
text = pipeline._preprocess_text(text)

print("="*70)
print("PREPROCESSED TEXT (first 1000 chars):")
print("="*70)
print(text[:1000])
print("="*70)

# Now manually run candidate extraction with debug
extractor = pipeline.extractor
import spacy
nlp = spacy.load("en_core_web_sm")
doc = nlp(text[:50000])

print("\n--- Named Entities from spaCy ---")
for ent in doc.ents:
    print(f"  [{ent.label_:10s}] '{ent.text}'")

print("\n--- Noun Chunks from spaCy ---")
for chunk in doc.noun_chunks:
    print(f"  '{chunk.text}'")

# Title Case extraction
print("\n--- Title Case matches (Pass 4) ---")
tc_pattern = re.compile(
    r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b'
    r'|\b([A-Z]{2,6})\b'
)
seen = set()
for m in tc_pattern.finditer(text):
    phrase = (m.group(1) or m.group(2)).strip()
    if phrase.lower() not in seen:
        seen.add(phrase.lower())
        is_noise = extractor._is_noise(phrase)
        print(f"  '{phrase}' -> noise={is_noise}")

# Check specific expected concepts
print("\n--- Expected Concept Traces ---")
expected = [
    "Artificial Intelligence", "Machine Learning", "Deep Learning",
    "Natural Language Processing", "Computer Vision", "Narrow AI",
    "General AI", "Reinforcement Learning", "Neural Network",
    "Speech Recognition", "Decision-Making"
]
for exp in expected:
    in_text = exp.lower() in text.lower()
    is_noise = extractor._is_noise(exp)
    # Check if TC regex would match
    tc_match = bool(re.search(r'\b' + re.escape(exp) + r'\b', text))
    print(f"  '{exp}': in_text={in_text}, noise={is_noise}, regex_match={tc_match}")
