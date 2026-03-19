#!/usr/bin/env python3
"""
OSINT Scribe Agent - Report Generation (PDF and HTML)

This module handles:
1. PDF report generation with structured tables
2. HTML report generation for web viewing
3. Breach Intelligence section highlighting Leak-Lookup findings
4. Proper data formatting for table population

Key Fix Implemented:
- Now properly populates the PDF table from flattened facts list
- Includes dedicated 'Breach Intelligence' section with clear table format
- Previously had empty 2KB file - now fully populated with verified results
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

# Try to import reportlab for PDF generation (fallback if not available)
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    REPORTLAB_AVAILABLE = True
except ImportError:
    logger = logging.getLogger("osint_scribe")
    logger.warning("ReportLab not available. PDF generation will use fallback.")
    REPORTLAB_AVAILABLE = False


class ReportGenerator:
    """Generates both PDF and HTML reports from OSINT analysis results"""
    
    def __init__(self, include_breach_intelligence: bool = True):
        self.include_breach_intelligence = include_breach_intelligence
    
    async def generate_pdf_report(self, 
                                 results: List[dict],
                                 leak_lookup_data: List[dict],
                                 filename: str,
                                 title: str = "OSINT Analysis Report") -> Path:
        """
        Generate PDF report with structured tables
        
        This method now properly populates the table from flattened facts list.
        Previously had empty 2KB file - this ensures all verified results are included.
        
        Args:
            results: List of verified analysis results (flattened for table)
            leak_lookup_data: Leak-Lookup breach findings
            filename: Output file path
            title: Report title
            
        Returns:
            Path to generated PDF file
        """
        
        # Ensure output directory exists
        output_path = Path(filename)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if not REPORTLAB_AVAILABLE:
            logger.warning("ReportLab not available. Generating HTML only.")
            return await self.generate_html_report(
                results=results,
                leak_lookup_data=leak_lookup_data,
                filename=str(output_path.with_suffix('.html')),
                title=title
            )
        
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
        )
        
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            alignment=TA_CENTER
        )
        
        subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=styles['Heading2'],
            fontSize=14,
            spaceBefore=10,
            spaceAfter=20,
            alignment=TA_CENTER
        )
        
        normal_style = styles['Normal']
        bold_style = ParagraphStyle(
            'CustomBold',
            parent=styles['Normal'],
            fontName='Helvetica-Bold'
        )
        
        elements = []
        
        # Title and metadata
        elements.append(Paragraph(title, title_style))
        elements.append(Spacer(1, 0.25*inch))
        
        report_metadata = f"""
        <para>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</para>
        """
        elements.append(Paragraph(report_metadata, normal_style))
        elements.append(Spacer(1, 0.5*inch))
        
        # Section 1: Analysis Summary Table (Populated with verified facts)
        elements.append(Paragraph("Analysis Results", bold_style))
        elements.append(Spacer(1, 0.25*inch))
        
        summary_table_data = self._create_analysis_summary_table(results)
        
        if summary_table_data and len(summary_table_data) > 1:
            analysis_table = Table(
                summary_table_data,
                colWidths=[3*inch, 1.5*inch, 1*inch]
            )
            
            # Style the table to ensure proper population
            style = [
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkgrey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ]
            
            analysis_table.setStyle(TableStyle(style))
            elements.append(analysis_table)
        else:
            elements.append(Paragraph("No verified results found.", normal_style))
        
        elements.append(Spacer(1, 0.5*inch))
        elements.append(PageBreak())
        
        # Section 2: Breach Intelligence (NEW SECTION - Clear table format)
        if self.include_breach_intelligence and leak_lookup_data:
            elements.append(Paragraph("Breach Intelligence", bold_style))
            elements.append(Spacer(1, 0.25*inch))
            
            breach_table_data = self._create_breach_intelligence_table(leak_lookup_data)
            
            if breach_table_data and len(breach_table_data) > 1:
                breach_table = Table(
                    breach_table_data,
                    colWidths=[2.5*inch, 3*inch]
                )
                
                style = [
                    ('BACKGROUND', (0, 0), (-1, 0), colors.darkred),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                    ('TOPPADDING', (0, 0), (-1, 0), 8),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.lightpink),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ]
                
                breach_table.setStyle(TableStyle(style))
                elements.append(breach_table)
            else:
                elements.append(Paragraph("No breach intelligence data available.", normal_style))
            
            elements.append(Spacer(1, 0.5*inch))
        elif leak_lookup_data and not self.include_breach_intelligence:
            logger.debug("Breach Intelligence section disabled")
        
        # Section 3: Detailed Findings (if results exist)
        if results:
            elements.append(PageBreak())
            elements.append(Paragraph("Detailed Findings", bold_style))
            elements.append(Spacer(1, 0.25*inch))
            
            for i, result in enumerate(results, 1):
                element = self._create_result_paragraph(result, i)
                if element:
                    elements.append(element)
        
        # Build PDF
        doc.build(elements)
        
        logger.info(f"PDF report generated successfully: {output_path}")
        return output_path
    
    def _create_analysis_summary_table(self, results: List[dict]) -> List[List]:
        """Create table data for analysis summary section
        
        This method ensures the table is properly populated from flattened facts.
        Previously had empty 2KB file - now guarantees content population.
        
        Returns:
            Table data structure [[header1, header2], [row1_col1, row1_col2], ...]
        """
        
        if not results or len(results) == 0:
            return [["No verified results found."]]
        
        table_data = [
            ["Fact / Finding", "Source", "Confidence"]
        ]
        
        for result in results[:50]:  # Limit to first 50 for readability
            if isinstance(result, dict):
                text = str(result.get("text", ""))[:80] + ("..." if len(str(result.get("text", ""))) > 80 else "")
                source = str(result.get("source", "Unknown"))[:40] + ("..." if len(str(result.get("source", ""))) > 40 else "")
                
                # Confidence color coding
                confidence = result.get("confidence_score", 0.0)
                if isinstance(confidence, (int, float)):
                    conf_str = f"{confidence:.2f}"
                else:
                    conf_str = "N/A"
                
                table_data.append([text, source, conf_str])
        
        return table_data
    
    def _create_breach_intelligence_table(self, leak_lookup_data: List[dict]) -> List[List]:
        """Create table for Breach Intelligence section
        
        NEW FEATURE: Clear table format listing Leak-Lookup results.
        
        Returns:
            Table data structure with breach database information
        """
        
        if not leak_lookup_data or len(leak_lookup_data) == 0:
            return [["No breach intelligence available."]]
        
        table_data = [
            ["Target", "Breach Databases Found"],
        ]
        
        for entry in leak_lookup_data[:25]:  # Limit to first 25 for readability
            if isinstance(entry, dict):
                target = str(entry.get("target", "Unknown"))
                
                databases = entry.get("breached_databases", [])
                if not isinstance(databases, list):
                    databases = [str(databases)] if databases else []
                
                # Format database names for display
                db_names = ", ".join([str(db)[:30] + ("..." if len(str(db)) > 30 else "") 
                                    for db in databases[:5]])
                if len(databases) > 5:
                    db_names += f" (+{len(databases)-5} more)"
                
                table_data.append([target, db_names])
        
        return table_data
    
    def _create_result_paragraph(self, result: dict, index: int) -> Optional[Paragraph]:
        """Create formatted paragraph for detailed findings"""
        
        if not isinstance(result, dict):
            return None
        
        text = str(result.get("text", "No description"))
        source = str(result.get("source", "Unknown source"))
        confidence = result.get("confidence_score", 0.0)
        
        # Color coding for confidence levels
        color = colors.black
        if isinstance(confidence, (int, float)):
            if confidence >= 0.8:
                color = colors.green
            elif confidence >= 0.6:
                color = colors.orange
            else:
                color = colors.red
        
        content = f"""
        <para><b>{index}. {text}</b></para>
        """
        
        if source and source != "Unknown":
            content += f"<para style='font-style:italic; font-size:10'>Source: {source}</para>"
        
        if isinstance(confidence, (int, float)):
            color_str = colors._colorsMapping.get(color.name, "#000000")
            content += f"<para style='color:{color_str}; font-size:9'>Confidence: {confidence:.2f}</para>"
        
        return Paragraph(content, getSampleStyleSheet()['Normal'])


async def generate_pdf_report(results: List[dict], 
                             leak_lookup_data: List[dict] = [],
                             filename: str = "reports/osint_report.pdf",
                             title: str = "OSINT Analysis Report",
                             include_breach_intelligence: bool = True) -> Path:
    """
    High-level function to generate PDF report
    
    Args:
        results: List of verified analysis results (flattened list for table population)
        leak_lookup_data: Leak-Lookup breach database findings
        filename: Output file path
        title: Report title
        include_breach_intelligence: Whether to include Breach Intelligence section
        
    Returns:
        Path to generated PDF file
    """
    
    generator = ReportGenerator(include_breach_intelligence=include_breach_intelligence)
    return await generator.generate_pdf_report(
        results=results,
        leak_lookup_data=leak_lookup_data,
        filename=filename,
        title=title
    )


async def generate_html_report(results: List[dict], 
                              leak_lookup_data: List[dict] = [],
                              filename: str = "reports/osint_report.html",
                              title: str = "OSINT Analysis Report") -> Path:
    """
    Generate HTML report for web viewing
    
    Args:
        results: List of verified analysis results
        leak_lookup_data: Leak-Lookup breach findings
        filename: Output file path
        title: Report title
        
    Returns:
        Path to generated HTML file
    """
    
    output_path = Path(filename)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }}
        h2 {{ color: #666; margin-top: 30px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #4CAF50; color: white; font-weight: bold; }}
        tr:hover {{ background-color: #f5f5f5; }}
        .confidence-high {{ color: green; font-weight: bold; }}
        .confidence-medium {{ color: orange; font-weight: bold; }}
        .confidence-low {{ color: red; font-weight: bold; }}
        .breach-section {{ background-color: #fff3f3; border-left: 4px solid #ff4444; padding: 15px; margin: 20px 0; }}
        .timestamp {{ color: #888; font-size: 0.9em; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
        <p class="timestamp">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <!-- Analysis Results Section -->
        <h2>Analysis Results</h2>
        {'<table>' if results else '<p>No verified results found.</p>'}
        {''.join(f'''
            <tr>
                <td>{result.get('text', 'N/A')[:100]}</td>
                <td>{result.get('source', 'Unknown')}</td>
                <td class="{self._get_confidence_class(result.get('confidence_score', 0.0))}">{result.get('confidence_score', 'N/A')}</td>
            </tr>
        ''' if isinstance(result, dict) else '') for result in results[:50]}
        {'</table>' if results else ''}
        
        <!-- Breach Intelligence Section -->
        {f"""
        <div class="breach-section">
            <h2>Breach Intelligence</h2>
            <p><strong>This section contains findings from Leak-Lookup breach database searches.</strong></p>
            <table>
                <tr>
                    <th>Target</th>
                    <th>Breach Databases Found</th>
                </tr>
                {''.join(f'''
                    <tr>
                        <td>{entry.get('target', 'N/A')}</td>
                        <td>{', '.join(entry.get('breached_databases', []))}</td>
                    </tr>
                ''' if isinstance(entry, dict) else '') for entry in leak_lookup_data[:25]}
            </table>
        </div>
        """ if leak_lookup_data else ""}
        
        <!-- Detailed Findings Section -->
        {f"""
        <h2>Detailed Findings</h2>
        """ if results else ""}
        {''.join(f'''
            <div style="margin: 15px 0; padding: 15px; border-left: 3px solid #4CAF50;">
                <strong>{result.get('text', 'N/A')}</strong><br>
                <em>Source: {result.get('source', 'Unknown')}</em>
            </div>
        ''' if isinstance(result, dict) else '') for result in results}
    </div>
</body>
</html>"""
    
    with open(output_path, 'w') as f:
        f.write(html_content)
    
    logger.info(f"HTML report generated successfully: {output_path}")
    return output_path


def _get_confidence_class(score):
    """Helper to get CSS class for confidence level"""
    if isinstance(score, (int, float)):
        if score >= 0.8:
            return "confidence-high"
        elif score >= 0.6:
            return "confidence-medium"
    return "confidence-low"


# Example usage and testing
async def run_demo():
    """Demonstrate report generation capabilities"""
    
    # Sample results for demonstration
    sample_results = [
        {
            "text": "John Doe - Software Engineer at TechCorp",
            "source": "LinkedIn Profile - https://linkedin.com/in/johndoe123",
            "confidence_score": 0.95,
            "is_verified": True
        },
        {
            "text": "Email found in breach database Collection1",
            "source": "Breach Database Entry - https://breachdb.example.com/entry/12345",
            "confidence_score": 0.87,
            "is_verified": True
        },
        {
            "text": "Possible match: John D. Doe @ example.com",
            "source": "Social Media Profile - https://twitter.com/johndoe",
            "confidence_score": 0.65,
            "is_verified": False
        }
    ]
    
    # Sample breach intelligence data
    sample_breach_data = [
        {
            "target": "test@example.com",
            "breached_databases": ["Collection1", "DataBreach2023", "LinkedInLeak"],
            "timestamp": datetime.now().isoformat()
        },
        {
            "target": "john.doe@example.com", 
            "breached_databases": ["YahooBreach2021"],
            "timestamp": datetime.now().isoformat()
        }
    ]
    
    # Generate both PDF and HTML reports
    pdf_path = await generate_pdf_report(
        results=sample_results,
        leak_lookup_data=sample_breach_data,
        filename="reports/demo_osint_report.pdf",
        title="OSINT Analysis Demo Report"
    )
    
    html_path = await generate_html_report(
        results=sample_results,
        leak_lookup_data=sample_breach_data,
        filename="reports/demo_osint_report.html",
        title="OSINT Analysis Demo Report"
    )
    
    print(f"PDF Report: {pdf_path}")
    print(f"HTML Report: {html_path}")


if __name__ == "__main__":
    import asyncio
    
    # Run demo if executed directly
    asyncio.run(run_demo())
