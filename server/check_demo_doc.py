"""Check and re-extract the Demo edugraph doc.pdf"""
import sys

USER = "udaynaik057@gmail.com"
PDF_PATH = "uploads/kg/6a930cc4-98ec-41fc-97bc-7fc8fe85a840_Demo edugraph doc.pdf"
DOC_NAME = "Demo edugraph doc.pdf"

# ── Step 1: Delete old concepts ──
from db import get_driver
driver = get_driver()
with driver.session() as s:
    for doc in [DOC_NAME, PDF_PATH.split("/")[-1]]:
        result = s.run("""
            MATCH (u:User {email: $email})-[:HAS_CONCEPT]->(c:Concept)
            WHERE c.source_document = $doc
            DETACH DELETE c
            RETURN count(c) AS deleted
        """, email=USER, doc=doc)
        rec = result.single()
        print(f"Deleted {rec['deleted'] if rec else 0} old concepts for doc='{doc}'")
driver.close()

# ── Step 2: Extract ──
from knowledge_graph import EduKGPipeline
pipeline = EduKGPipeline()

result = pipeline.process_pdf(
    PDF_PATH, USER,
    strategy="llm",
    original_filename=DOC_NAME
)

print("\n" + "=" * 70)
print("DEMO EDUGRAPH DOC — EXTRACTION RESULTS")
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

# ── Step 4: Show relations (first 30) ──
relations = result.get("relations", [])
print(f"\n--- {len(relations)} RELATIONS (first 30) ---")
for r in relations[:30]:
    src = r.get("source_id", "?")[:8]
    tgt = r.get("target_id", "?")[:8]
    print(f"  {src}... --[{r.get('relation_type', '?'):20s}]--> {tgt}...")

# ── Step 5: Garbage check ──
print(f"\n--- GARBAGE CHECK ---")
garbage = [c for c in concepts if '\n' in c.get("name", "") or len(c.get("name", "").split()) > 6]
if garbage:
    print(f"  WARNING: {len(garbage)} garbage concepts:")
    for g in garbage:
        print(f"    ✗ {g.get('name', '?')}")
else:
    print("  No garbage concepts found ✓")

# ── Step 6: Weight check ──
weights = [c.get("weight", 0) for c in concepts]
if weights:
    avg_w = sum(weights) / len(weights)
    print(f"\n--- WEIGHT CHECK ---")
    print(f"  avg={avg_w:.4f}  min={min(weights):.4f}  max={max(weights):.4f}")
    zero_w = [c for c in concepts if c.get("weight", 0) == 0]
    if zero_w:
        print(f"  WARNING: {len(zero_w)} concepts with weight=0")
    else:
        print("  All weights > 0 ✓")

print("\n" + "=" * 70)
print("Done.")
