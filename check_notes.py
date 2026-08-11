#!/usr/bin/env python3
"""Check what notes are in the database vs files on disk"""

import os
from pathlib import Path
from neo4j import GraphDatabase

# Use the same configuration as study.py
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "12345678")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

_SERVER_DIR = Path(__file__).parent.absolute()
UPLOAD_FOLDER = (_SERVER_DIR / "uploads").absolute()

print(f"Upload folder: {UPLOAD_FOLDER}")
print(f"Upload folder exists: {UPLOAD_FOLDER.exists()}")
print()

# Get files on disk
files_on_disk = {}
if UPLOAD_FOLDER.exists():
    for file_path in UPLOAD_FOLDER.glob("**/*"):
        if file_path.is_file():
            rel_path = str(file_path.relative_to(UPLOAD_FOLDER))
            files_on_disk[rel_path] = file_path.stat().st_size

print(f"Files on disk ({len(files_on_disk)}):")
for name, size in files_on_disk.items():
    print(f"  {name}: {size:,} bytes")
print()

# Get notes from database
with driver.session() as session:
    results = list(session.run("""
        MATCH (n:Note)
        RETURN n.id as id, n.filename as filename, n.storedFilename as storedFilename, n.fileSize as fileSize
        ORDER BY n.uploadedAt DESC
    """))

print(f"Notes in database ({len(results)}):")
for record in results:
    stored = record["storedFilename"]
    print(f"  ID: {record['id'][:8]}...")
    print(f"    Filename: {record['filename']}")
    print(f"    StoredFilename: {stored}")
    print(f"    File exists: {(UPLOAD_FOLDER / stored).exists()}")
    print()

driver.close()
