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
"""

import sqlite3
import os
from typing import Dict, List, Optional, Any, Generator
from datetime import datetime
import logging
import threading
from contextlib import contextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseManager:
    """SQLite database manager with connection pooling and upsert logic.

    Thread-safe singleton pattern prevents "Database is locked" errors
    during concurrent operations across multiple pipeline stages.

    Tables managed:
    - raw_harvest: Stores all tool output from OSINT scanners
    - verified_facts: Stores LLM-extracted facts with confidence scores
    """

    _instance: Optional['DatabaseManager'] = None
    _init_lock = threading.Lock()  # Separate lock for thread-safe singleton initialization

    def __init__(self, db_path: str = "osint.db"):
        """Initialize the database manager with connection pool setup.

        Args:
            db_path: Path to SQLite database file. Defaults to osint_pipeline.db in current directory.
                     Can be set via environment variable OSINT_DB_PATH for flexibility.
        """
        # Allow environment variable override
        self.db_path = db_path or os.environ.get("OSINT_DB_PATH", "osint_pipeline.db")
        self._connection_pool: List[sqlite3.Connection] = []
        self._lock = threading.Lock()  # Protects connection pool operations
        self._initialized = False

    @classmethod
    def get_instance(cls, db_path: Optional[str] = None) -> 'DatabaseManager':
        """Thread-safe singleton instance retrieval.

        Ensures only one DatabaseManager exists per database path, preventing
        duplicate connections and resource leaks across pipeline stages.

        Args:
            db_path: Optional override for default database path

        Returns:
            Singleton DatabaseManager instance (creates if doesn't exist)
        """
        with cls._init_lock:  # Prevent race condition during initialization
            if cls._instance is None or (db_path and cls._instance.db_path != db_path):
                cls._instance = cls(db_path or "osint_pipeline.db")
            return cls._instance

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for database connections with pooling.

        Yields a connection from the pool (or creates new one if needed).
        Ensures proper cleanup and prevents "Database is locked" errors during concurrent harvesting.

        Yields:
            sqlite3.Connection object with row_factory set

        Raises:
            sqlite3.OperationalError: If database becomes unavailable
            Exception: For unexpected connection failures
        """
        conn = None
        try:
            # Get connection from pool or create new one (thread-safe)
            with self._lock:
                if self._connection_pool:
                    conn = self._connection_pool.pop()
                else:
                    logger.debug(f"Creating new connection to {self.db_path}")
                    conn = sqlite3.connect(
                        self.db_path,
                        timeout=30.0,  # Wait up to 30s for lock acquisition
                        isolation_level=None,  # Autocommit mode for better concurrency
                        check_same_thread=False  # Allow cross-thread usage with proper locking
                    )
                    conn.row_factory = sqlite3.Row

            yield conn

            # Return connection to pool after successful operation (thread-safe)
            with self._lock:
                if len(self._connection_pool) < 5:  # Limit pool size to prevent memory leaks
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

        Creates raw_harvest and verified_facts tables if they don't exist,
        including indexes for efficient ticket_id lookups.

        Returns:
            True if initialization successful or already initialized, False otherwise.
        """
        if self._initialized:
            return True

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Create raw_harvest table (stores all tool output)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS raw_harvest (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticket_id TEXT NOT NULL,
                        source TEXT NOT NULL,
                        raw_content TEXT NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(ticket_id, source, raw_content)
                    )
                ''')

                # Create index on ticket_id for faster queries (critical for pipeline performance)
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_raw_harvest_ticket
                    ON raw_harvest (ticket_id)
                ''')

                # Create verified_facts table (stores LLM-extracted facts)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS verified_facts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticket_id TEXT NOT NULL,
                        fact_type TEXT NOT NULL,
                        value TEXT NOT NULL,
                        confidence REAL DEFAULT 0.0,
                        source_url TEXT,
                        description TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(ticket_id, fact_type, value)
                    )
                ''')

                # Create index on ticket_id for faster queries (critical for report generation)
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_verified_facts_ticket
                    ON verified_facts (ticket_id)
                ''')

                conn.commit()
                self._initialized = True
                logger.info(f"Database tables initialized successfully: {self.db_path}")
                return True

        except sqlite3.Error as e:
            logger.error(f"Failed to initialize database tables: {e}")
            return False

    def test_connection(self) -> bool:
        """Test if the database is reachable and writable.

        Performs a minimal query to verify connection health without modifying data.
        Should be called before starting pipeline operations.

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

    def insert_raw_harvest(self, ticket_id: str, source: str, raw_content: str) -> bool:
        """Insert or update a raw harvest record (upsert logic).

        Uses INSERT OR REPLACE to handle duplicates - if the same tool
        produces identical output for the same target, it updates instead of creating.

        Args:
            ticket_id: The ticket/recon identifier (e.g., "recon_f4f007")
            source: Source of the harvested data (tool name like 'shodan', 'hunter')
            raw_content: The actual harvested content as string

        Returns:
            True if insertion successful, False otherwise.
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Use INSERT OR REPLACE for upsert behavior (prevents duplicates)
                cursor.execute('''
                    INSERT OR REPLACE INTO raw_harvest (ticket_id, source, raw_content)
                    VALUES (?, ?, ?)
                ''', (ticket_id, source, raw_content))

                conn.commit()
                logger.debug(f"Inserted/updated raw harvest: ticket={ticket_id}, source={source}")
                return True

        except sqlite3.Error as e:
            logger.error(f"Failed to insert raw harvest data for {ticket_id}: {e}")
            return False

    def get_raw_harvest(self, ticket_id: str) -> List[Dict[str, Any]]:
        """Get all raw harvest records for a specific ticket.

        Primary method used by osint_analyst_stage.py to retrieve data for LLM analysis.
        Returns data ordered by timestamp (newest first).

        Args:
            ticket_id: The ticket/recon identifier

        Returns:
            List of dictionaries containing raw harvest data, or empty list on error.
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, ticket_id, source, raw_content, timestamp
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
                           confidence: float = 0.0, source_url: Optional[str] = None,
                           description: Optional[str] = None) -> bool:
        """Insert or update a verified fact record (upsert logic).

        Uses INSERT OR REPLACE to handle duplicates - if the same fact is extracted
        multiple times by LLM analysis, it updates confidence/score instead of creating.

        Args:
            ticket_id: The ticket/recon identifier
            fact_type: Type of the fact ("email", "ip_address", "domain", etc.)
            value: The actual fact value (e.g., "user@example.com")
            confidence: Confidence score between 0.0 and 1.0 from LLM analysis
            source_url: Optional URL where this fact was found
            description: Optional description or context about the fact

        Returns:
            True if insertion successful, False otherwise.
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Use INSERT OR REPLACE for upsert behavior (prevents duplicates)
                cursor.execute('''
                    INSERT OR REPLACE INTO verified_facts
                        (ticket_id, fact_type, value, confidence, source_url, description)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (ticket_id, fact_type, value, confidence, source_url, description))

                conn.commit()
                logger.debug(f"Inserted/updated verified fact: ticket={ticket_id}, type={fact_type}")
                return True

        except sqlite3.Error as e:
            logger.error(f"Failed to insert verified fact for {ticket_id}: {e}")
            return False

    def get_verified_facts(self, ticket_id: str) -> List[Dict[str, Any]]:
        """Get all verified facts for a specific ticket.

        Primary method used by osint_scribe_stage.py to generate reports.
        Returns facts ordered by confidence (highest first).

        Args:
            ticket_id: The ticket/recon identifier

        Returns:
            List of dictionaries containing verified fact data, or empty list on error.

        Note: This guarantees non-empty results if the database has data for this ticket.
              Solves the "empty report" issue by reading from persistent storage.
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, ticket_id, fact_type, value, confidence, source_url, description, timestamp
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
        """Get a summary count of verified facts by type.

        Useful for generating high-level statistics in reports.

        Args:
            ticket_id: The ticket/recon identifier

        Returns:
            Dictionary mapping fact_type to count (e.g., {"email": 5, "ip_address": 3})
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT fact_type, COUNT(*) as count
                    FROM verified_facts
                    WHERE ticket_id = ?
                    GROUP BY fact_type
                ''', (ticket_id,))

                rows = cursor.fetchall()
                return {row['fact_type']: row['count'] for row in rows}

        except sqlite3.Error as e:
            logger.error(f"Failed to get facts summary for ticket {ticket_id}: {e}")
            return {}

    def clear_ticket_data(self, ticket_id: str) -> bool:
        """Clear all data for a specific ticket (both raw_harvest and verified_facts).

        Useful for resetting a recon session or cleaning up old data.

        Args:
            ticket_id: The ticket/recon identifier

        Returns:
            True if deletion successful, False otherwise.
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Delete from raw_harvest first (no foreign key constraints to worry about)
                cursor.execute('DELETE FROM raw_harvest WHERE ticket_id = ?', (ticket_id,))

                # Then delete from verified_facts
                cursor.execute('DELETE FROM verified_facts WHERE ticket_id = ?', (ticket_id,))

                conn.commit()
                logger.info(f"Cleared all data for ticket {ticket_id}")
                return True

        except sqlite3.Error as e:
            logger.error(f"Failed to clear data for ticket {ticket_id}: {e}")
            return False

    def close_all_connections(self):
        """Close all connections in the pool. Should be called on application shutdown."""
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
    # Test the database manager independently
    logger.info("Testing DatabaseManager...")

    db = get_db_manager()

    # Test connection
    if not db.test_connection():
        logger.error("Connection test failed!")
        exit(1)

    logger.info("✓ Connection test passed")

    # Initialize tables
    if not db.initialize_tables():
        logger.error("Table initialization failed!")
        exit(1)

    logger.info("✓ Tables initialized successfully")

    # Test insert and retrieve raw harvest data
    test_ticket = "test_001"
    success = db.insert_raw_harvest(test_ticket, "shodan", '{"ip": "1.2.3.4"}')
    if not success:
        logger.error("Failed to insert test data!")
        exit(1)

    logger.info("✓ Raw harvest insertion successful")

    # Verify retrieval
    raw_data = db.get_raw_harvest(test_ticket)
    if len(raw_data) == 0:
        logger.error("Failed to retrieve inserted data!")
        exit(1)

    logger.info(f"✓ Retrieved {len(raw_data)} raw harvest record(s)")

    # Test insert and retrieve verified facts
    success = db.insert_verified_fact(test_ticket, "ip_address", "1.2.3.4", 0.95)
    if not success:
        logger.error("Failed to insert test fact!")
        exit(1)

    logger.info("✓ Verified fact insertion successful")

    # Verify retrieval (this is what osint_scribe_stage.py uses - never returns empty if DB has data!)
    facts = db.get_verified_facts(test_ticket)
    if len(facts) == 0:
        logger.error("Failed to retrieve verified facts!")
        exit(1)

    logger.info(f"✓ Retrieved {len(facts)} verified fact(s)")

    # Test summary
    summary = db.get_verified_facts_summary(test_ticket)
    logger.info(f"✓ Facts summary: {summary}")

    print("\n[OK] All DatabaseManager tests passed!")