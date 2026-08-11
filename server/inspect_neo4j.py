from db import get_driver

if __name__ == '__main__':
    driver = get_driver()
    with driver.session() as session:
        try:
            # Database info (if supported)
            try:
                dbs = session.run("SHOW DATABASES").data()
                print("Databases:")
                for d in dbs:
                    print(" ", d)
            except Exception:
                print("Could not run SHOW DATABASES (maybe older Neo4j or insufficient privileges).")

            # Labels present
            try:
                labels = session.run("CALL db.labels()").data()
                print("Labels:")
                for l in labels:
                    print(" ", l)
            except Exception:
                print("Could not run CALL db.labels().")

            # Count Users and Profiles
            ucount = session.run("MATCH (u:User) RETURN count(u) AS c").single().get('c')
            pcount = session.run("MATCH (p:Profile) RETURN count(p) AS c").single().get('c')
            relcount = session.run("MATCH (u:User)-[r:HAS_PROFILE]->(p:Profile) RETURN count(r) AS c").single().get('c')
            print(f"User nodes: {ucount}, Profile nodes: {pcount}, HAS_PROFILE rels: {relcount}")

            # List a few User nodes
            print("Sample Users (up to 10):")
            res = session.run("MATCH (u:User) RETURN u LIMIT 10")
            for r in res:
                node = r['u']
                try:
                    props = dict(node.items())
                except Exception:
                    props = {k: node.get(k) for k in node.keys()} if hasattr(node, 'keys') else str(node)
                print(props)

            # List a few Profile nodes
            print("Sample Profiles (up to 10):")
            res = session.run("MATCH (p:Profile) RETURN p LIMIT 10")
            for r in res:
                node = r['p']
                try:
                    props = dict(node.items())
                except Exception:
                    props = {k: node.get(k) for k in node.keys()} if hasattr(node, 'keys') else str(node)
                print(props)

        except Exception as e:
            print("Error querying Neo4j:", e)
