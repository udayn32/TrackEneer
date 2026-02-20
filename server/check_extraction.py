"""Quick script to check the AI Notes knowledge graph extraction."""
from knowledge_graph import KnowledgeGraphStore
from db import get_driver

store = KnowledgeGraphStore()

doc_name = "3d43e1f9-e93e-48f5-b9a0-c1df05323624_Artificial_Intelligence_Notes.pdf"
graph = store.get_graph_by_document("test@trackeneer.com", doc_name)

nodes = graph["nodes"]
edges = graph["edges"]

print("=" * 70)
print(f"EXTRACTION REPORT  —  {doc_name}")
print("=" * 70)

print(f"\nTotal nodes: {len(nodes)}")
print(f"Total edges: {len(edges)}")

# Layer breakdown
from collections import Counter
layer_counts = Counter(n.get("layer", "?") for n in nodes)
for layer in sorted(layer_counts):
    print(f"  Layer {layer}: {layer_counts[layer]} nodes")

print("\n--- ALL NODES (sorted by layer, then weight) ---")
for n in sorted(nodes, key=lambda x: (x.get("layer", 99), -x.get("weight", 0))):
    layer = n.get("layer", "?")
    name = n.get("name", "?")
    bloom = n.get("bloom_level", "?")
    diff = n.get("difficulty", "?")
    weight = n.get("weight", 0)
    wiki = n.get("wikipedia_url", "")
    w_tag = f"  wiki={wiki}" if wiki else ""
    print(f"  L{layer} | w={weight:.3f} | {name:45s} | bloom={bloom:12s} | diff={diff}{w_tag}")

print("\n--- ALL EDGES ---")
# Edge type breakdown
edge_types = Counter(e.get("type", "?") for e in edges)
for etype, cnt in edge_types.most_common():
    print(f"  {etype}: {cnt}")

print()
for e in edges:
    src = e.get("source", "?")
    tgt = e.get("target", "?")
    typ = e.get("type", "?")
    print(f"  {src:40s} --[{typ:20s}]--> {tgt}")

print("\n--- QUALITY CHECKS ---")
# Check: do key AI concepts appear?
expected_concepts = [
    "Artificial Intelligence", "Machine Learning", "Deep Learning",
    "Natural Language Processing", "Computer Vision", "Narrow AI",
    "General AI", "Super AI", "Neural Network", "Expert System",
    "Fraud Detection", "Reinforcement Learning", "Supervised Learning"
]
node_names = {n.get("name", "").lower() for n in nodes}
found = []
missing = []
for c in expected_concepts:
    if any(c.lower() in nn for nn in node_names):
        found.append(c)
    else:
        missing.append(c)

print(f"  Expected concepts found: {len(found)}/{len(expected_concepts)}")
for c in found:
    print(f"    ✓ {c}")
if missing:
    print(f"  Missing concepts ({len(missing)}):")
    for c in missing:
        print(f"    ✗ {c}")

# Check: any duplicate names?
from collections import defaultdict
name_count = defaultdict(int)
for n in nodes:
    name_count[n.get("name", "")] += 1
dupes = {k: v for k, v in name_count.items() if v > 1}
if dupes:
    print(f"\n  WARNING: Duplicate node names:")
    for name, cnt in dupes.items():
        print(f"    '{name}' appears {cnt} times")
else:
    print("  No duplicate node names ✓")

# Check: orphan nodes (no edges)?
edge_nodes = set()
for e in edges:
    edge_nodes.add(e.get("source", ""))
    edge_nodes.add(e.get("target", ""))
orphans = [n.get("name") for n in nodes if n.get("name") not in edge_nodes]
if orphans:
    print(f"\n  Orphan nodes (no edges): {len(orphans)}")
    for o in orphans:
        print(f"    - {o}")
else:
    print("  No orphan nodes ✓")

print("\n" + "=" * 70)
print("Done.")
