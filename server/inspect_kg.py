"""Inspect all KG data in Neo4j."""
from db import get_driver

driver = get_driver()

with driver.session() as s:
    # All distinct users
    result = s.run("MATCH (u:User)-[:HAS_CONCEPT]->(c:Concept) RETURN DISTINCT u.email AS email, count(c) AS concepts ORDER BY concepts DESC")
    print("=== USERS WITH CONCEPTS ===")
    users = []
    for r in result:
        print(f"  {r['email']}: {r['concepts']} concepts")
        users.append(r['email'])
    
    # All distinct source documents
    result = s.run("MATCH (c:Concept) RETURN DISTINCT c.source_document AS doc, c.userEmail AS email, count(*) AS cnt ORDER BY cnt DESC")
    print("\n=== SOURCE DOCUMENTS ===")
    for r in result:
        print(f"  [{r['email']}] {r['doc']}: {r['cnt']} concepts")
    
    # For each user, show all concepts
    for email in users[:3]:  # top 3 users
        result = s.run(
            "MATCH (c:Concept {userEmail: $email}) RETURN c.name AS name, c.layer AS layer, c.weight AS weight, c.bloom_level AS bloom, c.difficulty AS diff, c.source_document AS doc ORDER BY c.layer, c.name",
            email=email
        )
        print(f"\n=== CONCEPTS for {email} ===")
        for r in result:
            w = r['weight'] or 0
            print(f"  L{r['layer']} | w={w:.3f} | {r['name']:45s} | {r['bloom'] or '':12s} | {r['diff'] or ''} | doc={r['doc']}")
    
    # Edges
    result = s.run("""
        MATCH (a:Concept)-[r]->(b:Concept)
        RETURN DISTINCT type(r) AS rel_type, count(*) AS cnt
        ORDER BY cnt DESC
    """)
    print("\n=== EDGE TYPE SUMMARY ===")
    for r in result:
        print(f"  {r['rel_type']}: {r['cnt']}")

driver.close()
