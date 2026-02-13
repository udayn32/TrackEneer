
import os
import sys
import logging

# Ensure we can import from server directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Mock db module BEFORE importing knowledge_graph
from unittest.mock import MagicMock
sys.modules["db"] = MagicMock()
sys.modules["db"].get_driver = MagicMock()

# Mock env vars if needed
os.environ["GEMINI_API_KEY"] = "dummy"

try:
    # Now import knowledge_graph
    from knowledge_graph import ConceptExtractor
    print("✓ Imported ConceptExtractor")
except ImportError as e:
    print(f"✗ Import failed: {e}")
    # Print full traceback if import fails
    import traceback
    traceback.print_exc()
    sys.exit(1)

def test_extraction():
    print("Initializing Extractor...")
    extractor = ConceptExtractor()
    
    text = """
    Machine Learning is a field of study in artificial intelligence concerned with the development and study of statistical algorithms that can learn from data and generalize to unseen data, and thus perform tasks without explicit instructions.
    Recently, artificial neural networks have been able to surpass many previous approaches in performance.
    Deep learning is a subset of machine learning based on artificial neural networks with representation learning.
    """
    
    print("Running extraction...")
    concepts, relationships = extractor.extract_with_llm(text, source_doc="test_doc.txt")
    
    print(f"\nExtracted {len(concepts)} concepts and {len(relationships)} relations.")
    
    print("\nConcepts:")
    for c in concepts:
        print(f"- {c.name} ({c.category}) - Score/Conf: {c.description}")
        
    print("\nRelations:")
    for r in relationships:
        print(f"- {r.source_id} -> {r.target_id} ({r.relation_type})")

if __name__ == "__main__":
    test_extraction()
