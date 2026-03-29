#!/usr/bin/env python3
"""
Database Manager for SQLite persistence layer.
Implements connection pooling, upsert logic, and test connectivity.
Stateful pipeline foundation for OSINT analysis.

Features:
- Thread-safe singleton pattern prevents "Database is locked" errors during concurrent operations
- Connection pooling with max 5 connections to prevent resource exhaustion
- Upsert (INSERT OR REPLACE) logic handles duplicate prevention at database level
- Context manager ensures proper connection cleanup and error handling
- audit_log table records every failed INSERT for post-mortem diagnostics
"""

import sqlite3
import os
from typing import Dict, List, Optional, Any, Generator
from datetime import datetime
import logging
import threading
from contextlib import contextmanager
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# BUGFIX: always resolve the DB path relative to this file so the pipeline
# finds the same database regardless of the working directory.
_DEFAULT_DB_PATH = str(Path(__file__).parent / "osint.db")


class DatabaseManager:
    """SQLite database manager with connection pooling and upsert logic.

    Thread-safe singleton pattern prevents "Database is locked" errors
    during concurrent operations across multiple pipeline stages.

    Tables managed:
    - raw_harvest:     Stores all tool output from OSINT scanners
    - verified_facts:  Stores LLM-extracted facts with confidence scores
    - audit_log:       Records every failed DB operation for diagnostics
    """

    _instance: Optional['DatabaseManager'] = None
    _init_lock = threading.Lock()  # Separate lock for thread-safe singleton initialization

    def __init__(self, db_path: str = _DEFAULT_DB_PATH):
        """Initialize the database manager with connection pool setup.

        Args:
            db_path: Absolute path to SQLite database file.
                     Defaults to <script_dir>/osint.db.
                     Override via OSINT_DB_PATH environment variable.
        """
        # BUGFIX: prefer env-var override, then supplied arg, then script-dir default —
        # but always convert to an absolute path so SQLite never creates a stale
        # relative-path file in a different working directory.
        resolved = os.environ.get("OSINT_DB_PATH") or db_path or _DEFAULT_DB_PATH
        self.db_path = str(Path(resolved).resolve())

        # BUGFIX: ensure the parent directory exists before trying to open the file.
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._connection_pool: List[sqlite3.Connection] = []
        self._lock = threading.Lock()  # Protects connection pool operations
        self._initialized = False

    @classmethod
    def get_instance(cls, db_path: Optional[str] = None) -> 'DatabaseManager':
        """Thread-safe singleton instance retrieval.

        Ensures only one DatabaseManager exists per process, preventing
        duplicate connections and resource leaks across pipeline stages.

        Args:
            db_path: Optional override for default database path

        Returns:
            Singleton DatabaseManager instance (creates if doesn't exist)
        """
        with cls._init_lock:
            if cls._instance is None or (db_path and cls._instance.db_path != str(Path(db_path).resolve())):
                cls._instance = cls(db_path or _DEFAULT_DB_PATH)
            return cls._instance

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for database connections with pooling.

        Yields a connection from the pool (or creates new one if needed).
        Ensures proper cleanup and prevents "Database is locked" errors.

        Yields:
            sqlite3.Connection object with row_factory set

        Raises:
            sqlite3.OperationalError: If database becomes unavailable
            Exception: For unexpected connection failures
        """
        conn = None
        try:
            with self._lock:
                if self._connection_pool:
                    conn = self._connection_pool.pop()
                else:
                    logger.debug(f"Creating new connection to {self.db_path}")
                    conn = sqlite3.connect(
                        self.db_path,
                        timeout=30.0,
                        isolation_level=None,   # Autocommit mode for better concurrency
                        check_same_thread=False  # Allow cross-thread usage with proper locking
                    )
                    conn.row_factory = sqlite3.Row

            yield conn

            with self._lock:
                if len(self._connection_pool) < 5:
                    self._connection_pool.append(conn)

        except sqlite3.OperationalError as e:
            logger.error(f"Database operational error during connection: {e}")
            if conn:
                try:
                    conn.close()
                except Exception as close_error:
                    logger.warning(f"Failed to close connection after error: {close_error}")
            raise
        except Exception as e:
            logger.error(f"Unexpected database error during connection: {e}")
            if conn:
                try:
                    conn.close()
                except Exception as close_error:
                    logger.warning(f"Failed to close connection after error: {close_error}")
            raise

    def initialize_tables(self) -> bool:
        """Initialize the database tables with required schema.

        Creates all tables if they don't exist, including indexes for
        efficient ticket_id lookups and the audit_log table for diagnostics.

        Returns:
            True if initialization successful or already initialized, False otherwise.
        """
        if self._initialized:
            return True

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # raw_harvest: stores all tool output from OSINT scanners
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS raw_harvest (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticket_id TEXT NOT NULL,
                        source TEXT NOT NULL,
                        results_raw TEXT NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(ticket_id, source, results_raw)
                    )
                ''')

                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_raw_harvest_ticket
                    ON raw_harvest (ticket_id)
                ''')

                # verified_facts: stores LLM-extracted facts with confidence scores
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS verified_facts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticket_id TEXT NOT NULL,
                        type TEXT NOT NULL,
                        value TEXT NOT NULL,
                        confidence REAL DEFAULT 0.0,
                        sources TEXT,
                        description TEXT,
                        fact_json TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(ticket_id, type, value)
                    )
                ''')

                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_verified_facts_ticket
                    ON verified_facts (ticket_id)
                ''')

                # BUGFIX: audit_log table records every failed INSERT so operators
                # can diagnose "disk image is malformed" and other DB errors offline.
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS audit_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_type TEXT NOT NULL,
                        details TEXT,
                        error_msg TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                conn.commit()
                self._initialized = True
                logger.info(f"Database tables initialized successfully: {self.db_path}")
                return True

        except sqlite3.Error as e:
            logger.error(f"Failed to initialize database tables: {e}")
            return False

    def _log_audit(self, event_type: str, details: str, error_msg: str) -> None:
        """Write a row to audit_log without raising on failure (best-effort)."""
        try:
            with self.get_connection() as conn:
                conn.execute(
                    "INSERT INTO audit_log (event_type, details, error_msg) VALUES (?, ?, ?)",
                    (event_type, details, error_msg)
                )
                conn.commit()
        except Exception as audit_err:
            # audit_log write failed — just log; never raise from here
            logger.warning(f"audit_log write failed: {audit_err}")

    def test_connection(self) -> bool:
        """Test if the database is reachable and writable.

        Returns:
            True if connection successful and query executed, False otherwise.
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                return result[0] == 1

        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False

    def insert_raw_harvest(self, ticket_id: str, source: str, results_raw: str) -> bool:
        """Insert or update a raw harvest record (upsert logic).

        Args:
            ticket_id: The ticket/recon identifier
            source: Source tool name
            results_raw: The harvested content as string/JSON

        Returns:
            True if insertion successful, False otherwise.
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO raw_harvest (ticket_id, source, results_raw)
                    VALUES (?, ?, ?)
                ''', (ticket_id, source, results_raw))
                conn.commit()
                logger.debug(f"Inserted/updated raw harvest: ticket={ticket_id}, source={source}")
                return True

        except sqlite3.Error as e:
            logger.error(f"Failed to insert raw harvest data for {ticket_id}: {e}")
            return False

    def get_raw_harvest(self, ticket_id: str) -> List[Dict[str, Any]]:
        """Get all raw harvest records for a specific ticket."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, ticket_id, source, results_raw, timestamp
                    FROM raw_harvest
                    WHERE ticket_id = ?
                    ORDER BY timestamp DESC
                ''', (ticket_id,))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]

        except sqlite3.Error as e:
            logger.error(f"Failed to retrieve raw harvest data for ticket {ticket_id}: {e}")
            return []

    def insert_verified_fact(self, ticket_id: str, fact_type: str, value: str,
                             confidence: float = 0.0, sources: Optional[str] = None,
                             description: Optional[str] = None) -> bool:
        """Insert or update a verified fact record with audit logging on failure.

        BUGFIX: wrapped in try/except; on sqlite3.Error the failure is written
        to audit_log with event_type='DB_INSERT' so it can be diagnosed later.

        Args:
            ticket_id: The ticket/recon identifier
            fact_type: Type of the fact (e.g., "email", "ip_address")
            value: The actual fact value
            confidence: Confidence score between 0.0 and 1.0
            sources: Optional source information
            description: Optional description or context

        Returns:
            True if insertion successful, False otherwise.
        """
        import json as _json
        fact_json_str = _json.dumps({
            "ticket_id": ticket_id,
            "type": fact_type,
            "value": value,
            "confidence": confidence,
            "sources": sources,
            "description": description,
        })

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO verified_facts
                        (ticket_id, type, value, confidence, sources, description, fact_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (ticket_id, fact_type, value, confidence, sources, description, fact_json_str))
                conn.commit()
                logger.debug(f"Inserted/updated verified fact: ticket={ticket_id}, type={fact_type}")
                return True

        except sqlite3.Error as e:
            # BUGFIX: log failure to audit_log instead of silently returning False.
            err_msg = str(e)
            logger.error(f"Failed to insert verified fact for {ticket_id}: {err_msg}")
            self._log_audit(
                event_type="DB_INSERT",
                details=f"ticket_id={ticket_id} type={fact_type} value={value[:80]}",
                error_msg=err_msg
            )
            return False

    def get_verified_facts(self, ticket_id: str) -> List[Dict[str, Any]]:
        """Get all verified facts for a specific ticket, ordered by confidence."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, ticket_id, type, value, confidence, sources, description, timestamp
                    FROM verified_facts
                    WHERE ticket_id = ?
                    ORDER BY confidence DESC, timestamp DESC
                ''', (ticket_id,))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]

        except sqlite3.Error as e:
            logger.error(f"Failed to retrieve verified facts for ticket {ticket_id}: {e}")
            return []

    def get_verified_facts_summary(self, ticket_id: str) -> Dict[str, int]:
        """Get a summary count of verified facts by type."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT type, COUNT(*) as count
                    FROM verified_facts
                    WHERE ticket_id = ?
                    GROUP BY type
                ''', (ticket_id,))
                rows = cursor.fetchall()
                return {row['type']: row['count'] for row in rows}

        except sqlite3.Error as e:
            logger.error(f"Failed to get facts summary for ticket {ticket_id}: {e}")
            return {}

    def clear_ticket_data(self, ticket_id: str) -> bool:
        """Clear all data for a specific ticket."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM raw_harvest WHERE ticket_id = ?', (ticket_id,))
                cursor.execute('DELETE FROM verified_facts WHERE ticket_id = ?', (ticket_id,))
                conn.commit()
                logger.info(f"Cleared all data for ticket {ticket_id}")
                return True

        except sqlite3.Error as e:
            logger.error(f"Failed to clear data for ticket {ticket_id}: {e}")
            return False

    def close_all_connections(self):
        """Close all connections in the pool. Call on application shutdown."""
        with self._lock:
            while self._connection_pool:
                try:
                    conn = self._connection_pool.pop()
                    conn.close()
                except Exception as e:
                    logger.error(f"Error closing connection from pool: {e}")


# Singleton instance accessor (separate function for easy import)
def get_db_manager(db_path: Optional[str] = None) -> DatabaseManager:
    """Get the database manager singleton instance.

    Args:
        db_path: Optional override for default database path

    Returns:
        Singleton DatabaseManager instance (shared across all pipeline stages)
    """
    return DatabaseManager.get_instance(db_path)


# Standalone test runner when executed directly
if __name__ == "__main__":
    logger.info("Testing DatabaseManager...")

    db = get_db_manager()

    if not db.test_connection():
        logger.error("Connection test failed!")
        exit(1)
    logger.info("✓ Connection test passed")

    if not db.initialize_tables():
        logger.error("Table initialization failed!")
        exit(1)
    logger.info("✓ Tables initialized successfully")

    test_ticket = "test_001"
    success = db.insert_raw_harvest(test_ticket, "shodan", '{"ip": "1.2.3.4"}')
    if not success:
        logger.error("Failed to insert test data!")
        exit(1)
    logger.info("✓ Raw harvest insertion successful")

    raw_data = db.get_raw_harvest(test_ticket)
    if len(raw_data) == 0:
        logger.error("Failed to retrieve inserted data!")
        exit(1)
    logger.info(f"✓ Retrieved {len(raw_data)} raw harvest record(s)")

    success = db.insert_verified_fact(test_ticket, "ip_address", "1.2.3.4", 0.95)
    if not success:
        logger.error("Failed to insert test fact!")
        exit(1)
    logger.info("✓ Verified fact insertion successful")

    facts = db.get_verified_facts(test_ticket)
    if len(facts) == 0:
        logger.error("Failed to retrieve verified facts!")
        exit(1)
    logger.info(f"✓ Retrieved {len(facts)} verified fact(s)")

    summary = db.get_verified_facts_summary(test_ticket)
    logger.info(f"✓ Facts summary: {summary}")

    print("\n[OK] All DatabaseManager tests passed!")
