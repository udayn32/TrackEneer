#!/usr/bin/env python3
from neo4j import GraphDatabase
import os

URI = os.getenv('NEO4J_URI', 'neo4j://127.0.0.1:7687')
AUTH = (os.getenv('NEO4J_USER', 'neo4j'), os.getenv('NEO4J_PASSWORD', '12345678'))

try:
    with GraphDatabase.driver(URI, auth=AUTH) as driver:
        with driver.session() as session:
            result = session.run('MATCH (n:Note) RETURN n.filename as filename, n.storedFilename as stored LIMIT 10')
            records = list(result)
            if records:
                print('Notes in Neo4j:')
                for record in records:
                    print(f'  Filename: {record["filename"]}')
                    print(f'  StoredFilename: {record["stored"]}')
                    print()
            else:
                print('No notes found in Neo4j')
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
