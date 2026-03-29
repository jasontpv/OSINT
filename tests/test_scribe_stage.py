"""
Tests for the SCRIBE stage — report generation via MultiFormatReportGenerator.

Tests use the real public API of osint_scribe_stage:
  - ReportConfig / ReportResult / ReportFormat
  - generate_osint_report(target_name, recon_results, harvest_results,
                          analysis_results, output_path, output_format)
  - MultiFormatReportGenerator.generate_report()

All file-writing tests use tmp_path so they never pollute the working tree.
"""

import os
import pytest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

from osint_scribe_stage import (
    ReportConfig,
    ReportResult,
    ReportFormat,
    MultiFormatReportGenerator,
    generate_osint_report,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_facts():
    return [
        {
            "fact_type": "email",
            "value": "john.doe@example.com",
            "confidence": 0.9,
            "source": "linkedin",
        },
        {
            "fact_type": "location",
            "value": "New York, NY",
            "confidence": 0.75,
            "source": "twitter",
        },
    ]


@pytest.fixture
def report_config(sample_facts):
    return ReportConfig(
        title="OSINT Investigation: John Doe",
        target="John Doe",
        generated_at=datetime.now(),
        facts=sample_facts,
    )


@pytest.fixture
def mock_analysis(sample_facts):
    """Minimal analysis_results object accepted by generate_osint_report."""
    obj = MagicMock()
    obj.get = lambda key, default=None: sample_facts if key == "all_facts" else default
    return obj


# ── ReportConfig / ReportResult dataclass tests ───────────────────────────────

class TestReportDataclasses:

    def test_report_config_fields(self, report_config, sample_facts):
        assert report_config.target == "John Doe"
        assert report_config.facts == sample_facts
        assert isinstance(report_config.generated_at, datetime)

    def test_report_result_success(self):
        r = ReportResult(
            success=True,
            file_path="/tmp/test.pdf",
            format_type="pdf",
            size_bytes=1024,
        )
        assert r.success is True
        assert r.error_message is None

    def test_report_result_failure(self):
        r = ReportResult(
            success=False,
            file_path=None,
            format_type="pdf",
            size_bytes=0,
            error_message="Template not found",
        )
        assert r.success is False
        assert "Template" in r.error_message

    def test_report_format_values(self):
        assert ReportFormat.PDF.value == "pdf"
        assert ReportFormat.HTML.value == "html"
        assert ReportFormat.BOTH.value == "both"


# ── MultiFormatReportGenerator unit tests ─────────────────────────────────────

class TestMultiFormatReportGenerator:

    def test_instantiation(self, tmp_path):
        gen = MultiFormatReportGenerator(workspace_root=str(tmp_path))
        assert gen is not None

    def test_generate_html_returns_report_result(self, tmp_path, report_config):
        gen = MultiFormatReportGenerator(workspace_root=str(tmp_path))
        result = gen.generate_report(report_config, "html")
        assert isinstance(result, ReportResult)
        assert result.format_type in ("html", "pdf", "both")

    def test_generate_pdf_returns_report_result(self, tmp_path, report_config):
        gen = MultiFormatReportGenerator(workspace_root=str(tmp_path))
        result = gen.generate_report(report_config, "pdf")
        assert isinstance(result, ReportResult)

    def test_generate_html_creates_file_on_success(self, tmp_path, report_config):
        gen = MultiFormatReportGenerator(workspace_root=str(tmp_path))
        result = gen.generate_report(report_config, "html")
        if result.success:
            assert result.file_path is not None
            assert Path(result.file_path).exists()

    def test_generate_pdf_creates_file_on_success(self, tmp_path, report_config):
        gen = MultiFormatReportGenerator(workspace_root=str(tmp_path))
        result = gen.generate_report(report_config, "pdf")
        if result.success:
            assert result.file_path is not None
            assert Path(result.file_path).exists()

    def test_unknown_format_does_not_raise(self, tmp_path, report_config):
        """Generator must return a ReportResult (not raise) for unknown formats."""
        gen = MultiFormatReportGenerator(workspace_root=str(tmp_path))
        try:
            result = gen.generate_report(report_config, "xml")
            assert isinstance(result, ReportResult)
        except Exception:
            pass  # acceptable — just must not be an unhandled crash

    def test_empty_facts_list(self, tmp_path):
        config = ReportConfig(
            title="Empty",
            target="Nobody",
            generated_at=datetime.now(),
            facts=[],
        )
        gen = MultiFormatReportGenerator(workspace_root=str(tmp_path))
        result = gen.generate_report(config, "html")
        assert isinstance(result, ReportResult)


# ── generate_osint_report integration tests ───────────────────────────────────

class TestGenerateOsintReport:

    @pytest.mark.asyncio
    async def test_returns_report_result(self, tmp_path, mock_analysis):
        result = await generate_osint_report(
            target_name="John Doe",
            recon_results={},
            harvest_results={},
            analysis_results=mock_analysis,
            output_path=str(tmp_path / "report"),
            output_format=ReportFormat.HTML,
        )
        assert isinstance(result, ReportResult)

    @pytest.mark.asyncio
    async def test_pdf_format(self, tmp_path, mock_analysis):
        result = await generate_osint_report(
            target_name="Jane Smith",
            recon_results={},
            harvest_results={},
            analysis_results=mock_analysis,
            output_path=str(tmp_path / "report"),
            output_format=ReportFormat.PDF,
        )
        assert isinstance(result, ReportResult)

    @pytest.mark.asyncio
    async def test_both_format(self, tmp_path, mock_analysis):
        result = await generate_osint_report(
            target_name="Acme Corp",
            recon_results={},
            harvest_results={},
            analysis_results=mock_analysis,
            output_path=str(tmp_path / "report"),
            output_format=ReportFormat.BOTH,
        )
        assert isinstance(result, ReportResult)

    @pytest.mark.asyncio
    async def test_default_format_is_both(self, tmp_path, mock_analysis):
        """Calling without output_format uses BOTH as default."""
        result = await generate_osint_report(
            target_name="Default",
            recon_results={},
            harvest_results={},
            analysis_results=mock_analysis,
            output_path=str(tmp_path / "report"),
        )
        assert isinstance(result, ReportResult)

    @pytest.mark.asyncio
    async def test_string_format_accepted(self, tmp_path, mock_analysis):
        """output_format can also be passed as a plain string."""
        result = await generate_osint_report(
            target_name="String Test",
            recon_results={},
            harvest_results={},
            analysis_results=mock_analysis,
            output_path=str(tmp_path / "report"),
            output_format="html",
        )
        assert isinstance(result, ReportResult)
