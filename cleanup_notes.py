#!/usr/bin/env python3
"""Clean up orphaned notes from the database"""

import os
import glob
from pathlib import Path
from neo4j import GraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "12345678")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

_SERVER_DIR = Path(__file__).parent.absolute()
UPLOAD_FOLDER = (_SERVER_DIR / "uploads").absolute()

print("Cleaning up orphaned notes...")
print()

with driver.session() as session:
    # Get all notes
    note_results = list(session.run("""
        MATCH (n:Note)
        RETURN n.id as id, n.storedFilename as storedFilename
        ORDER BY n.uploadedAt DESC
    """))

print(f"Total notes in database: {len(note_results)}")

# Find orphaned notes
orphaned = []
for record in note_results:
    note_id = record["id"]
    stored_filename = record["storedFilename"]
    file_path = UPLOAD_FOLDER / stored_filename
    
    # Check if file exists
    if not file_path.exists():
        # Also check with glob
        search_pattern = str(UPLOAD_FOLDER / f"{note_id}*")
        matching = glob.glob(search_pattern, recursive=False)
        if not matching:
            matching = glob.glob(str(UPLOAD_FOLDER / f"**/{note_id}*"), recursive=True)
        
        if not matching:
            orphaned.append(note_id)
            print(f"  Orphaned: {note_id} (file: {stored_filename})")

print()
print(f"Found {len(orphaned)} orphaned notes")

# Delete orphaned notes
if orphaned:
    print()
    print("Deleting orphaned notes...")
    
    with driver.session() as session:
        for note_id in orphaned:
            # Delete the note
            session.run("""
                MATCH (n:Note {id: $id})
                DETACH DELETE n
            """, id=note_id)
            print(f"  Deleted: {note_id}")
    
    print()
    print(f"Successfully deleted {len(orphaned)} orphaned notes")
else:
    print("No orphaned notes to delete")

driver.close()
print()
print("Cleanup complete!")
