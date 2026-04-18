"""
Async SQLite database layer for persisting investigations, reports, and facts.
"""

import aiosqlite
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "osint.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS investigations (
    id TEXT PRIMARY KEY,
    target TEXT NOT NULL,
    target_type TEXT NOT NULL DEFAULT 'person',
    status TEXT NOT NULL DEFAULT 'pending',
    tools_json TEXT DEFAULT '[]',
    formats_json TEXT DEFAULT '["json"]',
    config_json TEXT DEFAULT '{}',
    fact_count INTEGER DEFAULT 0,
    avg_confidence REAL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    investigation_id TEXT NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    format TEXT NOT NULL,
    file_path TEXT NOT NULL,
    size_bytes INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    investigation_id TEXT NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    fact_type TEXT NOT NULL,
    value TEXT NOT NULL,
    confidence REAL DEFAULT 0.0,
    sources_json TEXT DEFAULT '[]',
    context_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS identity_clusters (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cluster_facts (
    cluster_id TEXT NOT NULL REFERENCES identity_clusters(id) ON DELETE CASCADE,
    fact_id INTEGER NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
    PRIMARY KEY (cluster_id, fact_id)
);
"""

MIGRATION_ADD_PARENT_CLUSTER = """
ALTER TABLE investigations ADD COLUMN parent_cluster_id TEXT DEFAULT NULL;
"""

LOGIN_LOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS login_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip TEXT NOT NULL,
    user_agent TEXT DEFAULT '',
    success INTEGER NOT NULL DEFAULT 0,
    logged_in_at TEXT NOT NULL,
    logged_out_at TEXT,
    session_token TEXT DEFAULT ''
);
"""


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    db = await get_db()
    try:
        await db.executescript(SCHEMA)
        await db.executescript(LOGIN_LOG_SCHEMA)
        cur = await db.execute("PRAGMA table_info(investigations)")
        cols = {row[1] for row in await cur.fetchall()}
        if "parent_cluster_id" not in cols:
            await db.execute(MIGRATION_ADD_PARENT_CLUSTER)
        await db.commit()
    finally:
        await db.close()


# ── Investigation CRUD ──────────────────────────────────────────────

async def create_investigation(
    inv_id: str,
    target: str,
    target_type: str,
    tools: List[str],
    formats: List[str],
    config: Dict[str, Any],
) -> Dict:
    db = await get_db()
    now = datetime.utcnow().isoformat()
    try:
        await db.execute(
            """INSERT INTO investigations
               (id, target, target_type, status, tools_json, formats_json, config_json, created_at)
               VALUES (?, ?, ?, 'running', ?, ?, ?, ?)""",
            (inv_id, target, target_type, json.dumps(tools), json.dumps(formats), json.dumps(config), now),
        )
        await db.commit()
        return {"id": inv_id, "target": target, "status": "running", "created_at": now}
    finally:
        await db.close()


async def update_investigation(inv_id: str, **fields):
    db = await get_db()
    try:
        sets = ", ".join(f"{k} = ?" for k in fields)
        vals = list(fields.values()) + [inv_id]
        await db.execute(f"UPDATE investigations SET {sets} WHERE id = ?", vals)
        await db.commit()
    finally:
        await db.close()


async def get_investigation(inv_id: str) -> Optional[Dict]:
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM investigations WHERE id = ?", (inv_id,))
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def list_investigations(limit: int = 50, offset: int = 0, search: str = "") -> List[Dict]:
    db = await get_db()
    try:
        if search:
            cur = await db.execute(
                "SELECT * FROM investigations WHERE target LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (f"%{search}%", limit, offset),
            )
        else:
            cur = await db.execute(
                "SELECT * FROM investigations ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def delete_investigation(inv_id: str):
    db = await get_db()
    try:
        await db.execute("DELETE FROM facts WHERE investigation_id = ?", (inv_id,))
        await db.execute("DELETE FROM reports WHERE investigation_id = ?", (inv_id,))
        await db.execute("DELETE FROM investigations WHERE id = ?", (inv_id,))
        await db.commit()
    finally:
        await db.close()


async def get_dashboard_stats() -> Dict:
    db = await get_db()
    try:
        cur = await db.execute("SELECT COUNT(*) FROM investigations")
        total = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM facts")
        total_facts = (await cur.fetchone())[0]
        cur = await db.execute("SELECT AVG(confidence) FROM facts")
        avg_conf = (await cur.fetchone())[0] or 0.0
        cur = await db.execute("SELECT COUNT(*) FROM investigations WHERE status = 'completed'")
        completed = (await cur.fetchone())[0]
        return {
            "total_investigations": total,
            "completed_investigations": completed,
            "total_facts": total_facts,
            "avg_confidence": round(avg_conf, 1),
        }
    finally:
        await db.close()


# ── Facts CRUD ──────────────────────────────────────────────────────

async def insert_facts(inv_id: str, facts: List[Dict]):
    if not facts:
        return
    db = await get_db()
    try:
        await db.executemany(
            """INSERT INTO facts (investigation_id, fact_type, value, confidence, sources_json, context_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (
                    inv_id,
                    f.get("fact_type", "unknown"),
                    f.get("value", ""),
                    f.get("confidence_score", f.get("confidence", 0)),
                    json.dumps(f.get("sources", [])),
                    json.dumps(f.get("context", {})),
                )
                for f in facts
            ],
        )
        await db.commit()
    finally:
        await db.close()


async def get_facts(inv_id: str, fact_type: str = "", sort_by: str = "confidence", order: str = "desc") -> List[Dict]:
    db = await get_db()
    try:
        allowed_sorts = {"confidence", "fact_type", "value"}
        col = sort_by if sort_by in allowed_sorts else "confidence"
        direction = "DESC" if order == "desc" else "ASC"

        if fact_type:
            cur = await db.execute(
                f"SELECT * FROM facts WHERE investigation_id = ? AND fact_type = ? ORDER BY {col} {direction}",
                (inv_id, fact_type),
            )
        else:
            cur = await db.execute(
                f"SELECT * FROM facts WHERE investigation_id = ? ORDER BY {col} {direction}",
                (inv_id,),
            )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_fact_types(inv_id: str) -> List[str]:
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT DISTINCT fact_type FROM facts WHERE investigation_id = ? ORDER BY fact_type",
            (inv_id,),
        )
        rows = await cur.fetchall()
        return [r[0] for r in rows]
    finally:
        await db.close()


async def get_fact(fact_id: int) -> Optional[Dict]:
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM facts WHERE id = ?", (fact_id,))
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def delete_fact(fact_id: int) -> None:
    db = await get_db()
    try:
        await db.execute("DELETE FROM cluster_facts WHERE fact_id = ?", (fact_id,))
        await db.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
        await db.commit()
    finally:
        await db.close()


async def update_fact(fact_id: int, **fields) -> None:
    db = await get_db()
    try:
        sets = ", ".join(f"{k} = ?" for k in fields)
        vals = list(fields.values()) + [fact_id]
        await db.execute(f"UPDATE facts SET {sets} WHERE id = ?", vals)
        await db.commit()
    finally:
        await db.close()


# ── Reports CRUD ────────────────────────────────────────────────────

async def insert_report(inv_id: str, fmt: str, file_path: str, size_bytes: int):
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO reports (investigation_id, format, file_path, size_bytes, created_at) VALUES (?, ?, ?, ?, ?)",
            (inv_id, fmt, file_path, size_bytes, datetime.utcnow().isoformat()),
        )
        await db.commit()
    finally:
        await db.close()


async def get_reports(inv_id: str) -> List[Dict]:
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT * FROM reports WHERE investigation_id = ? ORDER BY created_at DESC", (inv_id,)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


# ── Identity Cluster CRUD ──────────────────────────────────────────

async def create_cluster(cluster_id: str, investigation_id: str, label: str, notes: str = "") -> Dict:
    db = await get_db()
    now = datetime.utcnow().isoformat()
    try:
        await db.execute(
            "INSERT INTO identity_clusters (id, investigation_id, label, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (cluster_id, investigation_id, label, notes, now, now),
        )
        await db.commit()
        return {"id": cluster_id, "investigation_id": investigation_id, "label": label, "notes": notes, "created_at": now, "updated_at": now}
    finally:
        await db.close()


async def update_cluster(cluster_id: str, **fields) -> None:
    db = await get_db()
    try:
        fields["updated_at"] = datetime.utcnow().isoformat()
        sets = ", ".join(f"{k} = ?" for k in fields)
        vals = list(fields.values()) + [cluster_id]
        await db.execute(f"UPDATE identity_clusters SET {sets} WHERE id = ?", vals)
        await db.commit()
    finally:
        await db.close()


async def delete_cluster(cluster_id: str) -> None:
    db = await get_db()
    try:
        await db.execute("DELETE FROM cluster_facts WHERE cluster_id = ?", (cluster_id,))
        await db.execute("DELETE FROM identity_clusters WHERE id = ?", (cluster_id,))
        await db.commit()
    finally:
        await db.close()


async def get_clusters(investigation_id: str) -> List[Dict]:
    db = await get_db()
    try:
        cur = await db.execute(
            """SELECT c.*, COUNT(cf.fact_id) AS fact_count,
                      COALESCE(AVG(f.confidence), 0) AS avg_confidence
               FROM identity_clusters c
               LEFT JOIN cluster_facts cf ON cf.cluster_id = c.id
               LEFT JOIN facts f ON f.id = cf.fact_id
               WHERE c.investigation_id = ?
               GROUP BY c.id
               ORDER BY c.created_at""",
            (investigation_id,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_cluster_facts(cluster_id: str) -> List[Dict]:
    db = await get_db()
    try:
        cur = await db.execute(
            """SELECT f.* FROM facts f
               JOIN cluster_facts cf ON cf.fact_id = f.id
               WHERE cf.cluster_id = ?
               ORDER BY f.confidence DESC""",
            (cluster_id,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_unclustered_facts(investigation_id: str) -> List[Dict]:
    db = await get_db()
    try:
        cur = await db.execute(
            """SELECT f.* FROM facts f
               WHERE f.investigation_id = ?
                 AND f.id NOT IN (SELECT fact_id FROM cluster_facts)
               ORDER BY f.confidence DESC""",
            (investigation_id,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def add_facts_to_cluster(cluster_id: str, fact_ids: List[int]) -> int:
    if not fact_ids:
        return 0
    db = await get_db()
    try:
        added = 0
        for fid in fact_ids:
            try:
                await db.execute(
                    "INSERT OR IGNORE INTO cluster_facts (cluster_id, fact_id) VALUES (?, ?)",
                    (cluster_id, fid),
                )
                added += 1
            except Exception:
                pass
        await db.commit()
        return added
    finally:
        await db.close()


async def remove_fact_from_cluster(cluster_id: str, fact_id: int) -> None:
    db = await get_db()
    try:
        await db.execute("DELETE FROM cluster_facts WHERE cluster_id = ? AND fact_id = ?", (cluster_id, fact_id))
        await db.commit()
    finally:
        await db.close()


async def get_cluster_count(investigation_id: str) -> int:
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT COUNT(*) FROM identity_clusters WHERE investigation_id = ?",
            (investigation_id,),
        )
        return (await cur.fetchone())[0]
    finally:
        await db.close()


async def get_cluster(cluster_id: str) -> Optional[Dict]:
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM identity_clusters WHERE id = ?", (cluster_id,))
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


# ── Login logs ──────────────────────────────────────────────────────

async def log_login(ip: str, user_agent: str, success: bool, session_token: str = "") -> int:
    db = await get_db()
    try:
        cur = await db.execute(
            "INSERT INTO login_logs (ip, user_agent, success, logged_in_at, session_token) VALUES (?, ?, ?, ?, ?)",
            (ip, user_agent[:256], 1 if success else 0, datetime.utcnow().isoformat(), session_token),
        )
        await db.commit()
        return cur.lastrowid
    finally:
        await db.close()


async def log_logout(session_token: str):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE login_logs SET logged_out_at = ? WHERE session_token = ? AND logged_out_at IS NULL",
            (datetime.utcnow().isoformat(), session_token),
        )
        await db.commit()
    finally:
        await db.close()


async def get_login_logs(limit: int = 100) -> List[Dict]:
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT * FROM login_logs ORDER BY logged_in_at DESC LIMIT ?", (limit,)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()
