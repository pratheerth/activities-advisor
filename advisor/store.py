"""Local conversation storage; a separate interface so Clip 3 can replace SQLite."""

from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
import time
import uuid


class Missing(Exception):
    pass


class Busy(Exception):
    pass


class Store:
    def __init__(self, path):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS conversations (
              id TEXT PRIMARY KEY, owner TEXT NOT NULL, history TEXT NOT NULL,
              state TEXT NOT NULL, lease TEXT, until REAL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS runs (
              id TEXT PRIMARY KEY, conversation_id TEXT, owner TEXT,
              created REAL, result TEXT, events TEXT);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, owner):
        cid = str(uuid.uuid4())
        with self.connect() as db:
            db.execute(
                "INSERT INTO conversations(id,owner,history,state) VALUES(?,?,?,?)",
                (
                    cid,
                    owner,
                    "[]",
                    json.dumps(
                        {
                            "locations": {},
                            "sources": {},
                            "next_source": 1,
                            "weather": None,
                        }
                    ),
                ),
            )
        return cid

    def acquire(self, cid, owner):
        lease = str(uuid.uuid4())
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM conversations WHERE id=? AND owner=?", (cid, owner)
            ).fetchone()
            if not row:
                raise Missing("Conversation not found")
            n = db.execute(
                "UPDATE conversations SET lease=?,until=? WHERE id=? AND owner=? AND (lease IS NULL OR until<?)",
                (lease, time.time() + 210, cid, owner, time.time()),
            ).rowcount
            if n != 1:
                raise Busy("A reply is already running in this conversation.")
        return json.loads(row["history"]), json.loads(row["state"]), lease

    def finish(self, cid, owner, lease, history, state, result, events):
        with self.connect() as db:
            n = db.execute(
                "UPDATE conversations SET history=?,state=?,lease=NULL,until=0 WHERE id=? AND owner=? AND lease=?",
                (json.dumps(history), json.dumps(state), cid, owner, lease),
            ).rowcount
            if n != 1:
                raise Busy("Conversation lease expired. Please reload.")
            db.execute(
                "INSERT INTO runs VALUES(?,?,?,?,?,?)",
                (
                    result["run_id"],
                    cid,
                    owner,
                    time.time(),
                    json.dumps(result),
                    json.dumps(events),
                ),
            )

    def release(self, cid, lease):
        with self.connect() as db:
            db.execute(
                "UPDATE conversations SET lease=NULL,until=0 WHERE id=? AND lease=?",
                (cid, lease),
            )

    def run(self, rid, owner):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM runs WHERE id=? AND owner=?", (rid, owner)
            ).fetchone()
        if not row:
            raise Missing("Run not found")
        return {
            "result": json.loads(row["result"]),
            "events": json.loads(row["events"]),
        }
