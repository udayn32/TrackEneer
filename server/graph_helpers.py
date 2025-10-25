"""Utility helpers for maintaining user/day hierarchy in Neo4j."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from neo4j import Session


def normalize_day(value: Optional[str], *, now: Optional[datetime] = None) -> str:
    """Return a YYYY-MM-DD string, falling back to *now* in UTC when not provided."""
    if value:
        value = value.strip()
        if value:
            # Try datetime with time component first.
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed.date().isoformat()
            except ValueError:
                pass
            # Try plain date component.
            try:
                parsed_date = date.fromisoformat(value)
                return parsed_date.isoformat()
            except ValueError:
                pass
    current = now or datetime.now(timezone.utc)
    return current.date().isoformat()


def ensure_user_and_day(
    session: Session,
    email: str,
    *,
    day: Optional[str] = None,
    name: Optional[str] = None,
    now: Optional[datetime] = None,
) -> str:
    """Ensure a user node and its day node exist, returning the normalized day string."""
    if not email:
        raise ValueError("email is required to ensure user/day nodes")

    current = now or datetime.now(timezone.utc)
    day_iso = normalize_day(day, now=current)
    session.run(
        """
        MERGE (u:User {email: $email})
          ON CREATE SET u.id = randomUUID(),
                        u.name = coalesce($name, $email),
                        u.createdAt = datetime($now)
          SET u.lastActiveAt = datetime($now)
        MERGE (u)-[:HAS_DAY]->(d:Day {date: date($day), email: $email})
          ON CREATE SET d.id = randomUUID(),
                        d.createdAt = datetime($now)
          SET d.lastActiveAt = datetime($now)
        RETURN u, d
        """,
        email=email,
        name=name,
        now=current.isoformat(),
        day=day_iso,
    ).single()
    return day_iso


def touch_user_login(session: Session, email: str, *, name: Optional[str] = None) -> None:
    """Update login metadata without creating duplicate user nodes."""
    if not email:
        raise ValueError("email is required to record login")

    now = datetime.now(timezone.utc).isoformat()
    session.run(
        """
        MERGE (u:User {email: $email})
          ON CREATE SET u.id = randomUUID(),
                        u.name = coalesce($name, $email),
                        u.createdAt = datetime($now)
        SET u.lastLoginAt = datetime($now),
            u.lastActiveAt = datetime($now)
        """,
        email=email,
        name=name,
        now=now,
    )
