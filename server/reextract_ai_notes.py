"""Re-extract the AI Notes PDF with the fixed pipeline and compare results."""
import sys, json

# ── Step 1: Delete OLD concepts for BOTH docs for this user ──
from db import get_driver
driver = get_driver()

USER = "udaynaik057@gmail.com"
DOCS = [
    "Artificial_Intelligence_Notes.pdf",
    "3d43e1f9-e93e-48f5-b9a0-c1df05323624_Artificial_Intelligence_Notes.pdf",
]

with driver.session() as s:
    for doc in DOCS:
        result = s.run("""
            MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
            WHERE c.source_document = $doc
            DETACH DELETE c
            RETURN count(c) AS deleted
        """, email=USER, doc=doc)
        rec = result.single()
        deleted = rec["deleted"] if rec else 0
        print(f"Deleted {deleted} old concepts for doc='{doc}'")

driver.close()

# ── Step 2: Re-extract ──
from knowledge_graph import EduKGPipeline

pipeline = EduKGPipeline()

pdf_path = "uploads/kg/3d43e1f9-e93e-48f5-b9a0-c1df05323624_Artificial_Intelligence_Notes.pdf"
result = pipeline.process_pdf(
    pdf_path, USER,
    strategy="llm",
    original_filename="Artificial_Intelligence_Notes.pdf"
)

print("\n" + "=" * 70)
print("RE-EXTRACTION RESULTS")
print("=" * 70)
print(f"Concepts extracted: {result['concepts_extracted']}")
print(f"Relations extracted: {result['relations_extracted']}")
print(f"Strategy used: {result['strategy_used']}")

# ── Step 3: Show all concepts ──
concepts = result.get("concepts", [])
print(f"\n--- {len(concepts)} CONCEPTS ---")
for c in sorted(concepts, key=lambda x: (x.get("layer", 99), -x.get("weight", 0))):
    layer = c.get("layer", "?")
    name = c.get("name", "?")
    bloom = c.get("bloom_level", "?")
    diff = c.get("difficulty", "?")
    weight = c.get("weight", 0)
    cat = c.get("category", "?")
    print(f"  L{layer} | w={weight:.4f} | {name:45s} | bloom={bloom:12s} | {diff:8s} | {cat}")

# ── Step 4: Show relations (first 40) ──
relations = result.get("relations", [])
print(f"\n--- {len(relations)} RELATIONS (first 40) ---")
for r in relations[:40]:
    src = r.get("source_id", "?")[:8]
    tgt = r.get("target_id", "?")[:8]
    print(f"  {src}... --[{r.get('relation_type', '?'):20s}]--> {tgt}...")

# ── Step 5: Quality checks ──
expected = [
    "Artificial Intelligence", "Machine Learning", "Deep Learning",
    "Natural Language Processing", "Computer Vision", "Narrow AI",
    "General AI", "Super AI", "Neural Network", "Expert System",
    "Fraud Detection", "Reinforcement Learning", "Supervised Learning",
    "Unsupervised Learning", "Speech Recognition", "Decision-Making",
    "Smart Farming", "Autonomous Vehicles", "Medical Diagnosis"
]

node_names = {c.get("name", "").lower() for c in concepts}

print(f"\n--- QUALITY CHECK: Expected Concepts ---")
found, missing = [], []
for c in expected:
    if any(c.lower() in nn for nn in node_names):
        found.append(c)
    else:
        missing.append(c)

print(f"  Found: {len(found)}/{len(expected)}")
for c in found:
    print(f"    ✓ {c}")
if missing:
    print(f"  Missing ({len(missing)}):")
    for c in missing:
        print(f"    ✗ {c}")

# Check for garbage
print(f"\n--- GARBAGE CHECK ---")
garbage = [c for c in concepts if '\n' in c.get("name", "") or len(c.get("name", "").split()) > 6]
if garbage:
    print(f"  WARNING: {len(garbage)} garbage concepts:")
    for g in garbage:
        print(f"    - '{g['name']}'")
else:
    print("  No garbage concepts found ✓")

# Weight check
weights = [c.get("weight", 0) for c in concepts]
if weights:
    avg_w = sum(weights) / len(weights)
    print(f"\n--- WEIGHT CHECK ---")
    print(f"  avg={avg_w:.4f}  min={min(weights):.4f}  max={max(weights):.4f}")
    zero_count = sum(1 for w in weights if w == 0)
    if zero_count:
        print(f"  WARNING: {zero_count} concepts with weight=0")
    else:
        print("  All weights > 0 ✓")

print("\n" + "=" * 70)
print("Done.")
