"""Seed the local Neo4j database with a few sample nodes for UI visualization.

Run from the repository `server` folder with the project's venv active:
  & .venv\Scripts\python.exe seed_db.py
"""
from db import get_driver
import uuid
from datetime import datetime, timezone, timedelta


def iso_now():
    return datetime.now(timezone.utc).isoformat()


def main():
    driver = get_driver()
    sid = str(uuid.uuid4())
    nid = str(uuid.uuid4())
    tid = str(uuid.uuid4())

    now = iso_now()
    start = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    due = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    with driver.session() as session:
        # Create a Subject and a linked Note
        session.run(
            """
            CREATE (s:Subject {id:$sid, name:$name, description:$desc, createdAt: $now})
            CREATE (s)-[:HAS_NOTE]->(n:Note {id:$nid, subjectId:$sid, title:$ntitle, description:$ndesc, filename:$fname, storedFilename:$sf, fileType:'PDF', fileSize:12345, uploadedAt:$now})
            """,
            sid=sid,
            name="Sample Subject",
            desc="This is a seeded subject for UI testing",
            now=now,
            nid=nid,
            ntitle="Sample Note",
            ndesc="Seeded note",
            fname="sample.pdf",
            sf=f"{nid}.pdf",
        )

        # Create a Task node
        session.run(
            """
            CREATE (t:Task {id:$tid, title:$title, description:$desc, status:'pending', startTime: datetime($start), endTime: datetime($end), dueDate: datetime($due), createdAt: datetime(), priority:'high', category:'education', estimatedDuration:60})
            """,
            tid=tid,
            title="Seeded Task",
            desc="A sample task created by seed script",
            start=start,
            end=end,
            due=due,
        )

    print("Seeded: Subject id=", sid)
    print("Seeded: Note id=", nid)
    print("Seeded: Task id=", tid)


if __name__ == '__main__':
    main()
