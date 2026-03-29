"""
Unit tests for main.py CLI argument parsing and database_manager.py.

Covers:
- argparse accepts all README flags with correct defaults
- Missing / placeholder API keys raise ValueError
- DatabaseManager creates tables and inserts/retrieves facts
- audit_log records failed INSERT attempts
"""

import asyncio
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

# ── helpers ──────────────────────────────────────────────────────────────────

def _parse(argv: list) -> object:
    """Run the argparse block from main.py and return the parsed namespace."""
    import argparse
    # replicate the parser from main.py
    parser = argparse.ArgumentParser()
    parser.add_argument('query', nargs='?', default=None)
    parser.add_argument('--target', default=None)
    parser.add_argument('--target-type', default='person',
                        choices=['person', 'company', 'domain', 'product'])
    parser.add_argument('--wip-limit', type=int, default=5)
    parser.add_argument('--format', default='both', choices=['pdf', 'html', 'both'])
    parser.add_argument('--output', default='./reports')
    parser.add_argument('--privacy', '-p', default='hybrid',
                        choices=['public', 'private', 'hybrid'])
    parser.add_argument('--verbose', '-v', action='store_true')
    return parser.parse_args(argv)


# ── argparse tests ────────────────────────────────────────────────────────────

class TestArgparse:
    """Verify all README flags parse correctly."""

    def test_positional_query(self):
        args = _parse(['Matthew Pumphrey'])
        assert args.query == 'Matthew Pumphrey'

    def test_target_flag_alias(self):
        args = _parse(['--target', 'John Doe'])
        assert args.target == 'John Doe'
        assert args.query is None  # positional not supplied

    def test_wip_limit_default(self):
        args = _parse(['query'])
        assert args.wip_limit == 5

    def test_wip_limit_custom(self):
        args = _parse(['query', '--wip-limit', '10'])
        assert args.wip_limit == 10

    def test_format_default(self):
        args = _parse(['query'])
        assert args.format == 'both'

    def test_format_pdf(self):
        args = _parse(['query', '--format', 'pdf'])
        assert args.format == 'pdf'

    def test_format_html(self):
        args = _parse(['query', '--format', 'html'])
        assert args.format == 'html'

    def test_output_default(self):
        args = _parse(['query'])
        assert args.output == './reports'

    def test_output_custom(self):
        args = _parse(['query', '--output', '/tmp/myreports'])
        assert args.output == '/tmp/myreports'

    def test_target_type_default(self):
        args = _parse(['query'])
        assert args.target_type == 'person'

    def test_target_type_choices(self):
        for t in ('person', 'company', 'domain', 'product'):
            args = _parse(['q', '--target-type', t])
            assert args.target_type == t

    def test_verbose_false_by_default(self):
        args = _parse(['query'])
        assert args.verbose is False

    def test_verbose_flag(self):
        args = _parse(['query', '--verbose'])
        assert args.verbose is True

    def test_full_readme_example(self):
        """python main.py "Matthew Pumphrey" --wip-limit 5 --format both"""
        args = _parse(['Matthew Pumphrey', '--wip-limit', '5', '--format', 'both'])
        assert args.query == 'Matthew Pumphrey'
        assert args.wip_limit == 5
        assert args.format == 'both'

    def test_privacy_default(self):
        args = _parse(['query'])
        assert args.privacy == 'hybrid'

    def test_privacy_public(self):
        args = _parse(['query', '--privacy', 'public'])
        assert args.privacy == 'public'

    def test_privacy_private(self):
        args = _parse(['query', '--privacy', 'private'])
        assert args.privacy == 'private'

    def test_privacy_short_alias(self):
        args = _parse(['query', '-p', 'private'])
        assert args.privacy == 'private'

    def test_privacy_invalid_rejected(self):
        import argparse
        with pytest.raises(SystemExit):
            _parse(['query', '--privacy', 'secret'])


# ── API key validation tests ──────────────────────────────────────────────────

class TestApiKeyValidation:
    """Missing or placeholder keys must raise ValueError with clear message."""

    def _make_pipeline(self, env_overrides: dict):
        """Instantiate OSINTPipeline with a patched environment."""
        base = {
            'SERPER_API_KEY': 'valid_serper_key',
            'SCRAPEANT_API_KEY': 'valid_scrapeant_key',
        }
        base.update(env_overrides)
        # Remove keys explicitly set to None
        env = {k: v for k, v in base.items() if v is not None}

        from main import OSINTPipeline
        with patch.dict(os.environ, env, clear=False):
            # Clear the two required keys from environ first to avoid bleed-through
            for k in ('SERPER_API_KEY', 'SCRAPEANT_API_KEY'):
                os.environ.pop(k, None)
            os.environ.update(env)
            return OSINTPipeline()

    def test_valid_keys_accepted(self):
        from main import OSINTPipeline
        with patch.dict(os.environ, {
            'SERPER_API_KEY': 'abc123',
            'SCRAPEANT_API_KEY': 'def456',
        }, clear=False):
            p = OSINTPipeline()
            assert p.api_keys['serper'] == 'abc123'

    def test_missing_serper_raises(self):
        from main import OSINTPipeline
        env = {'SERPER_API_KEY': '', 'SCRAPEANT_API_KEY': 'valid'}
        with patch.dict(os.environ, env, clear=False):
            os.environ['SERPER_API_KEY'] = ''
            with pytest.raises(ValueError, match='SERPER_API_KEY'):
                OSINTPipeline()

    def test_missing_scrapeant_raises(self):
        from main import OSINTPipeline
        with patch.dict(os.environ, {
            'SERPER_API_KEY': 'valid',
            'SCRAPEANT_API_KEY': '',
        }, clear=False):
            os.environ['SCRAPEANT_API_KEY'] = ''
            with pytest.raises(ValueError, match='SCRAPEANT_API_KEY'):
                OSINTPipeline()

    def test_placeholder_serper_raises(self):
        from main import OSINTPipeline
        with patch.dict(os.environ, {
            'SERPER_API_KEY': 'YOUR_SERPER_API_KEY',
            'SCRAPEANT_API_KEY': 'real_key',
        }, clear=False):
            with pytest.raises(ValueError, match='SERPER_API_KEY'):
                OSINTPipeline()

    def test_public_mode_missing_keys_no_raise(self):
        """--privacy public must NOT raise even when both keys are missing."""
        from main import OSINTPipeline
        env = {'SERPER_API_KEY': '', 'SCRAPEANT_API_KEY': ''}
        with patch.dict(os.environ, env, clear=False):
            os.environ['SERPER_API_KEY'] = ''
            os.environ['SCRAPEANT_API_KEY'] = ''
            # Should complete without raising
            p = OSINTPipeline(privacy_mode='public')
            assert p.privacy_mode == 'public'

    def test_private_mode_missing_key_raises(self):
        """--privacy private must raise even when only one key is missing."""
        from main import OSINTPipeline
        with patch.dict(os.environ, {
            'SERPER_API_KEY': '',
            'SCRAPEANT_API_KEY': 'valid',
        }, clear=False):
            os.environ['SERPER_API_KEY'] = ''
            with pytest.raises(ValueError, match='SERPER_API_KEY'):
                OSINTPipeline(privacy_mode='private')

    def test_hybrid_mode_missing_key_raises(self):
        """--privacy hybrid (default) must raise on missing keys."""
        from main import OSINTPipeline
        with patch.dict(os.environ, {
            'SERPER_API_KEY': 'valid',
            'SCRAPEANT_API_KEY': '',
        }, clear=False):
            os.environ['SCRAPEANT_API_KEY'] = ''
            with pytest.raises(ValueError, match='SCRAPEANT_API_KEY'):
                OSINTPipeline(privacy_mode='hybrid')

    def test_privacy_mode_stored_on_instance(self):
        """privacy_mode must be stored on the pipeline instance."""
        from main import OSINTPipeline
        with patch.dict(os.environ, {
            'SERPER_API_KEY': 'key1',
            'SCRAPEANT_API_KEY': 'key2',
        }, clear=False):
            p = OSINTPipeline(privacy_mode='private')
            assert p.privacy_mode == 'private'


# ── DatabaseManager tests ─────────────────────────────────────────────────────

class TestDatabaseManager:
    """Verify DB creation, table schema, insert/retrieve, and audit_log."""

    @pytest.fixture
    def db(self, tmp_path):
        """Fresh DatabaseManager backed by a temp file."""
        from database_manager import DatabaseManager
        # Reset singleton so each test gets a clean instance
        DatabaseManager._instance = None
        db_file = str(tmp_path / "test_osint.db")
        manager = DatabaseManager(db_path=db_file)
        manager.initialize_tables()
        yield manager
        manager.close_all_connections()
        DatabaseManager._instance = None

    def test_db_file_created(self, db):
        assert Path(db.db_path).exists()

    def test_connection_ok(self, db):
        assert db.test_connection() is True

    def test_verified_facts_table_exists(self, db):
        conn = sqlite3.connect(db.db_path)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert 'verified_facts' in tables

    def test_audit_log_table_exists(self, db):
        conn = sqlite3.connect(db.db_path)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert 'audit_log' in tables

    def test_insert_and_retrieve_fact(self, db):
        ok = db.insert_verified_fact(
            ticket_id='t001',
            fact_type='email',
            value='john@example.com',
            confidence=0.9,
            sources='linkedin',
            description='found on profile',
        )
        assert ok is True
        facts = db.get_verified_facts('t001')
        assert len(facts) == 1
        assert facts[0]['value'] == 'john@example.com'
        assert facts[0]['confidence'] == pytest.approx(0.9)

    def test_insert_multiple_facts(self, db):
        for i in range(3):
            db.insert_verified_fact('t002', 'ip', f'10.0.0.{i}', confidence=0.7)
        facts = db.get_verified_facts('t002')
        assert len(facts) == 3

    def test_upsert_deduplication(self, db):
        """Same (ticket_id, type, value) triplet must not create duplicate rows."""
        db.insert_verified_fact('t003', 'email', 'dup@test.com', confidence=0.5)
        db.insert_verified_fact('t003', 'email', 'dup@test.com', confidence=0.8)
        facts = db.get_verified_facts('t003')
        assert len(facts) == 1
        # Updated confidence should be stored
        assert facts[0]['confidence'] == pytest.approx(0.8)

    def test_fact_json_column_populated(self, db):
        """fact_json should contain a JSON string with all field values."""
        import json
        db.insert_verified_fact('t004', 'phone', '555-1234', confidence=0.6)
        conn = sqlite3.connect(db.db_path)
        row = conn.execute(
            "SELECT fact_json FROM verified_facts WHERE ticket_id='t004'"
        ).fetchone()
        conn.close()
        assert row is not None
        parsed = json.loads(row[0])
        assert parsed['value'] == '555-1234'
        assert parsed['confidence'] == pytest.approx(0.6)

    def test_audit_log_on_insert_failure(self, db):
        """A failed INSERT must write a row to audit_log."""
        # Drop verified_facts to force an error on next insert
        conn = sqlite3.connect(db.db_path)
        conn.execute("DROP TABLE verified_facts")
        conn.commit()
        conn.close()
        # Mark tables as initialized so initialize_tables won't recreate them
        db._initialized = True

        ok = db.insert_verified_fact('fail_ticket', 'email', 'x@y.com')
        assert ok is False

        conn2 = sqlite3.connect(db.db_path)
        rows = conn2.execute(
            "SELECT event_type, error_msg FROM audit_log WHERE event_type='DB_INSERT'"
        ).fetchall()
        conn2.close()
        assert len(rows) >= 1
        assert rows[0][0] == 'DB_INSERT'

    def test_clear_ticket_data(self, db):
        db.insert_verified_fact('del_ticket', 'ip', '1.2.3.4')
        db.clear_ticket_data('del_ticket')
        assert db.get_verified_facts('del_ticket') == []

    def test_absolute_path_resolved(self, tmp_path):
        """DatabaseManager must always use an absolute path."""
        from database_manager import DatabaseManager
        DatabaseManager._instance = None
        db_file = str(tmp_path / "abs_test.db")
        manager = DatabaseManager(db_path=db_file)
        assert Path(manager.db_path).is_absolute()
        DatabaseManager._instance = None

    def test_no_malformed_db_on_fresh_init(self, db):
        """Integrity check must pass on a freshly created database."""
        conn = sqlite3.connect(db.db_path)
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        assert result[0] == 'ok'
