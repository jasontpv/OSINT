#!/usr/bin/env python3
"""
OSINT Scribe Stage - Generates reports in multiple formats using Jinja2 templates and ReportLab.
Supports HTML, PDF, Markdown, JSON outputs with MythWorx branding.
Author: Matt Pumphrey
Date: 3/16/2026
"""

import os
import sys
import json
import io
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from jinja2 import Environment, FileSystemLoader, select_autoescape
import reportlab.lib.pagesizes as pagesizes
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, ListFlowable  
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import base64


@dataclass
class ReportConfig:
    
    """Configuration for report generation"""
    title: str
    target: str
    generated_at: datetime
    facts: List[Dict]
    include_evidence: bool = True
    taglines: str = "Intelligence Report"
    confidentiality_level: str = 'INTERNAL'  # PUBLIC, INTERNAL, CONFIDENTIAL


@dataclass
class ReportResult:
    """Result of report generation"""
    success: bool
    file_path: Optional[str]
    format_type: str
    size_bytes: int
    error_message: Optional[str] = None


class BrandingSystem:
    """MythWorx branding for all reports"""

    CONFIG = {
        'company_name': 'MythWorx, LLC',
        'founder': 'Matt Pumphrey',
        'colors': {
            'primary_cyan': '#0693e3',
            'primary_purple': '#9b51e0',
            'accent_orange': '#ff6900'
        },
        'taglines': [
            'Lean Compute. Massive Intelligence.',
            'Where human reasoning and machine intelligence finally converge.'
        ]
    }


class Jinja2ReportGenerator:
    """Generates HTML reports using Jinja2 templates"""

    def __init__(self, template_dir: str = './templates'):
        if not os.path.exists(template_dir):
            os.makedirs(template_dir, exist_ok=True)
            
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True
        )

    def load_template(self, template_name: str):
        """Load Jinja2 template with proper error handling"""
        try:
            return self.env.get_template(template_name)
        except Exception as e:
            print(f"❌ Template loading failed: {e}")
            return self._create_inline_template()

    def _create_inline_template(self):
        """Create inline Jinja2 template (fallback for missing files)"""
        source = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{{ title }}</title>
</head>
<body>
    <h1>{{ title }}</h1>
    <p>Generated: {{ generated_at }}</p>
    {% for fact in facts %}
    <div class="fact-card">
        <strong>{{ fact.type }}:</strong> {{ fact.value }}
        <br><em>Confidence: {{ "%.1f"|format(fact.confidence*100) }}%</em>
        <br>Sources: {{ fact.sources|join(', ') }}
    </div>
    {% endfor %}
</body>
</html>'''
        return self.env.from_string(source)

    def generate_html_report(self, config: ReportConfig) -> str:
        """Generate HTML report with MythWorx branding"""
        template_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{{ config.title }} - {{ config.company_name }}</title>
    <style>
        :root { --mw-cyan: #0693e3; --mw-purple: #9b51e0; }
        body { font-family: Arial, sans-serif; margin: 40px; background: #f8f9fa; }
        .container { max-width: 1000px; margin: auto; background: white; padding: 30px; border-radius: 8px; }
        .header-gradient {
            background: linear-gradient(135deg, var(--mw-cyan), var(--mw-purple));
            color: white; padding: 40px 20px; text-align: center; border-radius: 8px 8px 0 0;
        }
        .header-gradient h1 { margin: 0; font-size: 2.5em; }
        .tagline { font-size: 1.2em; opacity: 0.95; margin-top: 10px; }
        .fact-table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        .fact-table th, .fact-table td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        .fact-table th { background-color: var(--mw-cyan); color: white; }
        .confidence-high { color: #059669; font-weight: bold; }
        .confidence-medium { color: #d97706; }
        .confidence-low { color: #dc2626; }
        footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; text-align: center; color: #6b7280; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header-gradient">
            <h1>{{ config.title }}</h1>
            <p class="tagline">{{ config.taglines[0] }}</p>
            <small>Developed by {{ config.founder }} • {{ config.company_name }}</small>
        </div>
        <table class="fact-table">
            <tr><th>Type</th><th>Value</th><th>Confidence</th><th>Sources</th></tr>
            {% for fact in facts %}
            <tr>
                <td>{{ fact.type }}</td>
                <td>{{ fact.value }}</td>
                <td class="{% if fact.confidence >= 0.8 %}confidence-high{% elif fact.confidence >= 0.5 %}confidence-medium{% else %}confidence-low{% endif %}">
                    {{ "%.1f"|format(fact.confidence*100) }}%
                </td>
                <td>{{ fact.sources|join(', ') }}</td>
            </tr>
            {% endfor %}
        </table>
        <footer>
            <p>&copy; {{ config.company_name }}. All rights reserved.</p>
            <p>Generated: {{ generated_at.strftime('%Y-%m-%d %H:%M:%S') }}</p>
        </footer>
    </div>
</body>
</html>'''
        template = self.env.from_string(template_content)

        for fact in config.facts:
            if isinstance(fact, dict) and 'confidence' not in fact:
                fact['confidence'] = 0.5  # Default to 50% if missing
  
        return template.render(     
            config=config,
            facts=config.facts,
            generated_at=config.generated_at,
            taglines=BrandingSystem.CONFIG['taglines'],
            founder=BrandingSystem.CONFIG['founder']
        )


class ReportLabPDFGenerator:
    """Generates PDF reports using ReportLab"""

    def __init__(self):
        self.styles = getSampleStyleSheet()

    def _create_custom_styles(self):
        """Create custom paragraph styles with MythWorx branding colors"""
        cyan = colors.HexColor(BrandingSystem.CONFIG['colors']['primary_cyan'])
        purple = colors.HexColor(BrandingSystem.CONFIG['colors']['primary_purple'])

        if 'CustomHeader' not in self.styles:
            self.styles.add(ParagraphStyle(
                'CustomHeader',
                parent=self.styles['Heading1'],
                fontSize=24,
                textColor=cyan,
                spaceAfter=30,
                alignment=1
            ))

        if 'Subtitle' not in self.styles:
            self.styles.add(ParagraphStyle(
                'Subtitle',
                parent=self.styles['Normal'],
                fontSize=14,
                textColor=purple,
                spaceBefore=10,
                spaceAfter=20,
                alignment=1
            ))

    def generate_pdf_report(self, config: ReportConfig) -> bytes:
        """Generate PDF report with MythWorx branding"""
        self._create_custom_styles()
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesizes=pagesizes.A4,
            leftMargin=1*inch,
            rightMargin=1*inch,
            topMargin=1*inch,
            bottomMargin=0.5*inch
        )

        story = []
        header_text = f"OSINT Investigation Report"
        story.append(Paragraph(header_text, self.styles['CustomHeader']))
        
        subtitle = f"{config.title}<br/>MythWorx • Developed by {BrandingSystem.CONFIG['founder']}"
        story.append(Paragraph(subtitle, self.styles['Subtitle']))
        story.append(Spacer(1, 0.25*inch))

        facts_data = [['Type', 'Value', 'Confidence', 'Sources']]
        for fact in config.facts[:30]:
            facts_data.append([
                str(fact.get('type', '')),
                str(fact.get('value', ''))[:50],
                f"{fact.get('confidence', 0.5)*100:.1f}%"
                ', '.join(str(s) for s in fact.get('sources', []))[:30]
            ])

        table = Table(facts_data, colWidths=[1.5*inch, 2.5*inch, 1*inch, 2.5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(BrandingSystem.CONFIG['colors']['primary_cyan'])),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ]))
        story.append(table)

        if config.confidentiality_level != 'PUBLIC':
            conf_style = ParagraphStyle('Conf', parent=self.styles['Normal'], textColor=colors.red, alignment=1)
            story.append(Spacer(1, 0.5*inch))
            story.append(Paragraph(f"CONFIDENTIAL - {config.confidentiality_level}", conf_style))

        doc.build(story)
        return buffer.getvalue()


class MultiFormatReportGenerator:
    def __init__(self, workspace_root: str = "./OSINT_WORKSPACE"):
        self.workspace_root = os.path.abspath(workspace_root)
        self.html_generator = Jinja2ReportGenerator('./templates')
        self.pdf_generator = ReportLabPDFGenerator()

    def generate_report(self, config: ReportConfig, output_format: str = 'html') -> ReportResult:
        """Generate report in specified format with comprehensive error handling"""
        try:
            # Create output directory
            reports_dir = os.path.join(self.workspace_root, 'data', 'reports')
            os.makedirs(reports_dir, exist_ok=True)

            # Generate timestamped filename
            safe_title = config.title.replace(' ', '_').replace('/', '_')[:50]
            filename = f"{safe_title}_{config.generated_at.strftime('%Y%m%d_%H%M%S')}.{output_format}"
            filepath = os.path.join(reports_dir, filename)

            # Generate based on format
            if output_format.lower() == 'html':
                content = self.html_generator.generate_html_report(config)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                size_bytes = len(content.encode('utf-8'))

            elif output_format.lower() == 'pdf':
                content = self.pdf_generator.generate_pdf_report(config)
                with open(filepath, 'wb') as f:
                    f.write(content)
                size_bytes = len(content)

            elif output_format.lower() in ['markdown', 'md']:
                content = self._generate_markdown_report(config)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                size_bytes = len(content.encode('utf-8'))

            elif output_format.lower() == 'json':
                data_to_save = {
                    'title': config.title,
                    'target': config.target,
                    'generated_at': config.generated_at.isoformat(),
                    'facts': config.facts,
                    'confidentiality_level': config.confidentiality_level
                }
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(data_to_save, f, indent=2)
                size_bytes = len(json.dumps(data_to_save).encode('utf-8'))

            else:
                return ReportResult(
                    success=False,
                    file_path=None,
                    format_type=output_format,
                    size_bytes=0,
                    error_message=f"Unsupported output format: {output_format}"
                )

            print(f"✅ {output_format.upper()} report generated successfully")
            print(f" File: {filepath}")
            print(f" Size: {size_bytes:,} bytes ({size_bytes/1024:.2f} KB)")

            return ReportResult(
                success=True,
                file_path=filepath,
                format_type=output_format,
                size_bytes=size_bytes
            )

        except Exception as e:
            print(f"❌ Report generation failed: {e}")
            import traceback
            traceback.print_exc()

            return ReportResult(
                success=False,
                file_path=None,
                format_type=output_format,
                size_bytes=0,
                error_message=str(e)
            )

    def _generate_markdown_report(self, config: ReportConfig) -> str:
        """Generate Markdown report with MythWorx branding"""
        markdown = f'''# {config.title}

**Developed by {BrandingSystem.CONFIG['founder']} • {BrandingSystem.CONFIG['company_name']}**

*{BrandingSystem.CONFIG['taglines'][0]}*

---

## Investigation Details

- **Target:** {config.target}
- **Generated:** {config.generated_at.strftime('%Y-%m-%d %H:%M:%S')}
- **Confidentiality:** {config.confidentiality_level}

---

## Key Findings


| Type | Value | Confidence | Sources |
|------|-------|------------|---------|
'''
        for fact in config.facts[:30]:
            markdown += f"| {fact['type']} | {fact['value'][:50]} | {fact['confidence']*100:.1f}% | {', '.join(fact.get('sources', []))} |\n"

        markdown += '''
---

## Evidence Trail

All facts are traceable to their original source tools with full attribution.

---

*© 2025 MythWorx, LLC. All rights reserved.*
'''
        return markdown

from enum import Enum

class ReportFormat(Enum):
    """Enumeration of supported report formats for main.py integration."""
    PDF = "pdf"
    HTML = "html"
    BOTH = "both"

async def generate_osint_report(target_name, recon_results, harvest_results, analysis_results, output_path, output_format=ReportFormat.BOTH):
    """
    Main entry point for the SCRIBE stage. 
    Coordinates report generation across multiple formats for main.py.
    """
    # Initialize the generator we built in the previous step
    gen = MultiFormatReportGenerator(workspace_root=os.path.dirname(output_path))
    
    # Create the config object
    config = ReportConfig(
        title=f"OSINT Investigation: {target_name}",
        target=target_name,
        generated_at=datetime.now(),
        facts=analysis_results.report.facts if hasattr(analysis_results, 'report') else analysis_results.get('all_facts', [])
    )
    
    # Map the format to the specific generator calls
    format_str = output_format.value if isinstance(output_format, ReportFormat) else output_format
    
    if format_str == 'both':
        res_html = gen.generate_report(config, 'html')
        res_pdf = gen.generate_report(config, 'pdf')
        return res_pdf if res_pdf.success else res_html
    else:
        return gen.generate_report(config, format_str)

def ask_user_report_format():
    """Helper function for CLI interaction if main.py requires it."""
    return ReportFormat.BOTH

# Main execution entry point
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Generate OSINT reports')
    parser.add_argument('format', choices=['html', 'pdf', 'markdown', 'json'],
                        help='Output report format')
    parser.add_argument('--workspace-root', default='./OSINT_WORKSPACE',
                        help='Workspace root directory')

    args = parser.parse_args()

    # Create sample config for testing
    sample_config = ReportConfig(
        title="OSINT Investigation: Example Company",
        target="example.com",
        generated_at=datetime.now(),
        facts=[
            {'type': 'EMAIL', 'value': 'john.doe@example.com',
             'confidence': 0.95, 'sources': ['shodan', 'spiderfoot']},
            {'type': 'IP_ADDRESS', 'value': '192.168.1.1',
             'confidence': 0.75, 'sources': ['nmap']},
        ],
        include_evidence=True,
        confidentiality_level='INTERNAL'
    )

    # Generate report
    generator = MultiFormatReportGenerator(workspace_root=args.workspace_root)
    res = generator.generate_report(sample_config, output_format=args.format)

    if not res.success:
        print(f"❌ Report generation failed: {res.error_message}")
        sys.exit(1)

    sys.exit(0)