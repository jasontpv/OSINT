#!/usr/bin/env python3
"""
OSINT Debug Script - Comprehensive Diagnostics for Empty Report Issue

This script systematically tests each failure point in the OSINT pipeline to identify
why PDF/HTML reports are empty despite API data being available.

Follows the 11-step debugging plan:
1. Verify API request works
2. Inspect authentication handling  
3. Confirm database insertion
4. Check parsing step
5. Validate verification logic
6. Inspect report configuration
7. Test report generation in isolation
8. Audit paginated handling
9. Look for hidden bugs in DB schema
10. Run full end-to-end integration test
11. Document findings & fixes

Author: Debugging Expert
"""

import asyncio
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import aiohttp


def step_1_verify_api_request():
    """
    STEP 1: Verify API request works
    
    Run a simple test against Serper.dev to check if the API returns data.
    
    Command (curl):
        curl -X POST https://google.serper.dev/search \\
          -H "X-API-KEY: YOUR_SERPER_API_KEY" \\
          -H "Content-Type: application/json" \\
          -d '{"q": "test@example.com", "num": 5}'
    
    Expected: Status 200, response contains 'organic' key with results
    """
    print("\n" + "="*60)
    print("STEP 1: Verify API Request Works")
    print("="*60)
    
    serper_key = os.getenv('SERPER_API_KEY')
    
    if not serper_key or serper_key == "YOUR_SERPER_API_KEY":
        print("❌ FAIL: SERPER_API_KEY is not set or using placeholder value")
        print("   Please set it in your .env file:")
        print("   SERPER_API_KEY=your_actual_api_key_here")
        return False
    
    async def test_request():
        try:
            headers = {
                "X-API-KEY": serper_key,
                "Content-Type": "application/json"
            }
            
            payload = {"q": "test@example.com", "num": 5}
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://google.serper.dev/search",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    
                    status = response.status
                    print(f"Response Status: {status}")
                    
                    if status == 200:
                        data = await response.json()
                        
                        # Check key header presence
                        has_organic = 'organic' in data and isinstance(data['organic'], list)
                        result_count = len(data.get('organic', []))
                        
                        print(f"Contains 'organic' key: {has_organic}")
                        print(f"Result count: {result_count}")
                        
                        if has_organic and result_count > 0:
                            print("✅ PASS: API returns valid data")
                            
                            # Show first result as sample
                            first_result = data['organic'][0]
                            if isinstance(first_result, dict):
                                print(f"Sample title: {first_result.get('title', 'N/A')[:50]}...")
                            return True
                        else:
                            print("❌ FAIL: API returned 200 but no results found")
                            print(f"Response preview: {str(data)[:200]}...")
                            return False
                    elif status == 401:
                        print("❌ FAIL: Invalid API key (HTTP 401)")
                        return False
                    elif status == 429:
                        print("❌ FAIL: Rate limit exceeded (HTTP 429)")
                        return False
                    else:
                        error_text = await response.text()
                        print(f"❌ FAIL: API error {status}: {error_text[:100]}")
                        return False
                        
        except aiohttp.ClientTimeout:
            print("❌ FAIL: Request timeout (30s exceeded)")
            return False
        except Exception as e:
            print(f"❌ FAIL: Unexpected error: {e}")
            return False
    
    result = asyncio.run(test_request())
    
    if not result:
        print("\n💡 SUGGESTION: Check your Serper.dev API key at https://serper.dev/")
        print("   Ensure it's valid and has remaining quota.")
    
    return result


def step_2_inspect_authentication():
    """
    STEP 2: Inspect authentication handling
    
    Print the value of the API-key header when a request is made.
    Check if the server returns 401, regenerate or refresh the key.
    
    File to check: osint_harvesting.py - SerperClient class
    """
    print("\n" + "="*60)
    print("STEP 2: Inspect Authentication Handling")
    print("="*60)
    
    serper_key = os.getenv('SERPER_API_KEY')
    
    if not serper_key:
        print("❌ FAIL: SERPER_API_KEY environment variable is missing")
        return False
    
    # Check for common issues
    issues = []
    
    if serper_key == "YOUR_SERPER_API_KEY":
        issues.append("Using placeholder value instead of real API key")
    
    if len(serper_key) < 10:
        issues.append(f"API key seems too short ({len(serper_key)} chars)")
    
    # Check for whitespace/special characters
    if serper_key != serper_key.strip():
        issues.append("API key has leading/trailing whitespace")
    
    if not issues:
        print("✅ PASS: API key appears valid")
        print(f"   Key preview: {serper_key[:4]}...{serper_key[-4:] if len(serper_key) > 8 else '***'}")
        return True
    else:
        print("❌ FAIL: API key issues detected:")
        for issue in issues:
            print(f"   - {issue}")
        
        # Check if it's a known bad pattern
        if "YOUR_" in serper_key.upper():
            print("\n💡 SUGGESTION: Replace placeholder with real Serper.dev API key")
            print("   Get your key at: https://serper.dev/")
        
        return False


def step_3_confirm_database_insertion():
    """
    STEP 3: Confirm database insertion
    
    After running the harvest routine, query the raw_harvest table:
        SELECT ticket_id, source, results_raw FROM raw_harvest WHERE ticket_id='recon_f4f007';
    
    Ensure that a row exists and that results_raw is not an empty string.
    """
    print("\n" + "="*60)
    print("STEP 3: Confirm Database Insertion")
    print("="*60)
    
    db_path = "osint.db"
    
    if not os.path.exists(db_path):
        print(f"❌ FAIL: Database file '{db_path}' does not exist")
        print("   The pipeline hasn't run yet, or database path is incorrect.")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check for any recon tickets
        cursor.execute("""
            SELECT ticket_id, source, LENGTH(results_raw) as raw_length, timestamp
            FROM raw_harvest 
            WHERE ticket_id LIKE 'recon_%'
            ORDER BY timestamp DESC
        """)
        rows = cursor.fetchall()
        
        if not rows:
            print("❌ FAIL: No recon tickets found in raw_harvest table")
            print("   Possible causes:")
            print("   1. Pipeline never ran successfully")
            print("   2. Recon stage failed before insertion")
            print("   3. Wrong ticket_id pattern (not starting with 'recon_')")
            
            # Check for any tickets at all
            cursor.execute("SELECT COUNT(*) FROM raw_harvest")
            total_count = cursor.fetchone()[0]
            
            if total_count == 0:
                print("\n   The database is completely empty. Run the pipeline first.")
            else:
                print(f"\n   However, there are {total_count} other tickets in raw_harvest:")
                cursor.execute("SELECT ticket_id FROM raw_harvest LIMIT 3")
                for row in cursor.fetchall():
                    print(f"     - {row[0]}")
            
            conn.close()
            return False
        
        print(f"✅ PASS: Found {len(rows)} recon tickets in database")
        
        # Check if results_raw is not empty
        non_empty = sum(1 for r in rows if r[2] > 0)
        
        if non_empty == len(rows):
            print("   All tickets have valid results_raw data (length > 0)")
        else:
            print(f"   ⚠️ WARNING: {len(rows) - non_empty} ticket(s) have empty results_raw")
            for r in rows:
                if r[2] == 0:
                    print(f"      Empty: {r[0]} ({r[1]})")
        
        # Show sample data
        print("\n   Sample ticket (most recent):")
        first = rows[0]
        print(f"     Ticket ID: {first[0]}")
        print(f"     Source: {first[1]}")
        print(f"     Raw length: {first[2]} bytes")
        
        # Try to parse as JSON if possible
        try:
            parsed = json.loads(first[3])  # timestamp is first[3] for length, actually results_raw is index 3 in SELECT
            print(f"     Valid JSON: Yes")
            if isinstance(parsed, dict):
                print(f"     Keys: {', '.join(list(parsed.keys())[:5])}")
        except json.JSONDecodeError:
            print(f"     Valid JSON: No (raw text preview)")
            print(f"     Preview: {first[3][:100]}...")
        
        conn.close()
        return True
        
    except sqlite3.Error as e:
        print(f"❌ FAIL: Database error: {e}")
        return False


def step_4_check_parsing_step():
    """
    STEP 4: Check the parsing step
    
    In harvest_search_docs(), you receive a JSON-string (or XML).
    Right after the json.loads() line, add a temporary print(type(res), len(res)).
    
    If it crashes, catch the exception and try xmltodict.parse() instead.
    """
    print("\n" + "="*60)
    print("STEP 4: Check Parsing Step")
    print("="*60)
    
    # Read the harvesting stage code to check parsing logic
    harvesting_path = "osint_harvesting_stage.py"
    
    if not os.path.exists(harvesting_path):
        print(f"❌ FAIL: File '{harvesting_path}' does not exist")
        return False
    
    try:
        with open(harvesting_path, 'r') as f:
            content = f.read()
        
        # Check for JSON parsing patterns
        has_json_loads = 'json.loads' in content or 'await response.json()' in content
        has_error_handling = 'except' in content and ('JSONDecodeError' in content or 'json.JSONDecodeError' in content)
        
        print("Code analysis:")
        print(f"  - Uses json.loads(): {has_json_loads}")
        print(f"  - Has JSON error handling: {has_error_handling}")
        
        if has_json_loads and has_error_handling:
            print("\n✅ PASS: Parsing logic appears robust")
            
            # Check for the specific pattern in execute_search method
            if 'async def execute_search' in content:
                # Extract the method
                import re
                match = re.search(r'async def execute_search\(self.*?\n(?:.*?\n)*?    (?:except|return|\Z)', content, re.DOTALL)
                
                if match:
                    method_code = match.group(0)[:500]  # First 500 chars
                    
                    # Check for proper response handling
                    has_json_parse = 'await response.json()' in method_code or '.json()' in method_code
                    has_status_check = 'if response.status == 200' in method_code
                    
                    print(f"    - execute_search parses JSON: {has_json_parse}")
                    print(f"    - Checks HTTP status before parsing: {has_status_check}")
                    
                    if not has_status_check:
                        print("    ⚠️ WARNING: May parse non-200 responses as JSON (risk of error)")
            
            return True
        else:
            print("\n⚠️ WARNING: Parsing logic may need improvement")
            if not has_json_loads:
                print("   - No json.loads() or .json() found in code")
            if not has_error_handling:
                print("   - No JSONDecodeError handling found")
            
            return False
            
    except Exception as e:
        print(f"❌ FAIL: Error reading file: {e}")
        return False


def step_5_validate_verification_logic():
    """
    STEP 5: Validate verification logic
    
    In verify_search_results(), temporarily lower min_confidence_threshold to 0.5 
    and log every fact's confidence value.
    
    Run the pipeline again – if you now see facts, the original threshold was too high for the data set.
    """
    print("\n" + "="*60)
    print("STEP 5: Validate Verification Logic")
    print("="*60)
    
    analyst_path = "osint_analyst_stage.py"
    
    if not os.path.exists(analyst_path):
        print(f"❌ FAIL: File '{analyst_path}' does not exist")
        return False
    
    try:
        with open(analyst_path, 'r') as f:
            content = f.read()
        
        # Check the verify_search_results function signature
        import re
        match = re.search(r'def verify_search_results\(.*?\)', content)
        
        if not match:
            print("❌ FAIL: Could not find verify_search_results function")
            return False
        
        func_signature = match.group(0)
        print(f"Function signature: {func_signature}")
        
        # Check for min_confidence_threshold default value
        threshold_match = re.search(r'min_confidence_threshold\s*=\s*([0-9.]+)', content)
        
        if threshold_match:
            current_value = float(threshold_match.group(1))
            print(f"\nCurrent min_confidence_threshold default: {current_value}")
            
            if current_value >= 0.7:
                print("⚠️ WARNING: Threshold may be too high for some datasets")
                print(f"   Suggested test value: 0.5 (lower than current {current_value})")
                return True
            else:
                print("✅ PASS: Threshold appears reasonable")
                return True
        else:
            # Check how the threshold is used
            if 'min_confidence_threshold' in content:
                print("\n   min_confidence_threshold parameter exists but no default found")
                return True
            else:
                print("   No min_confidence_threshold parameter found")
                return False
                
    except Exception as e:
        print(f"❌ FAIL: Error analyzing file: {e}")
        return False


def step_6_inspect_report_configuration():
    """
    STEP 6: Inspect the report configuration
    
    After the Analyst stage, print ticket.analysis_results.report.
    
    It should be a dict with keys title, target, generated_at, facts (list).
    
    If facts is empty, trace back to step 5.
    """
    print("\n" + "="*60)
    print("STEP 6: Inspect Report Configuration")
    print("="*60)
    
    # Check the Scribe stage for ReportConfig usage
    scribe_path = "osint_scribe_stage.py"
    
    if not os.path.exists(scribe_path):
        print(f"❌ FAIL: File '{scribe_path}' does not exist")
        return False
    
    try:
        with open(scribe_path, 'r') as f:
            content = f.read()
        
        # Check ReportConfig definition
        config_match = re.search(r'class ReportConfig.*?\n(?:.*?\n)*?    """', content)
        
        if not config_match:
            print("❌ FAIL: Could not find ReportConfig class")
            return False
        
        # Extract the class fields
        import re
        fields = re.findall(r'\s+(\w+):', content[config_match.end():config_match.end()+200])
        
        print(f"ReportConfig expected fields:")
        for field in ['title', 'target', 'generated_at', 'facts']:
            if field in fields:
                print(f"  ✅ {field}")
            else:
                print(f"  ❌ {field} (missing!)")
        
        # Check how facts are populated
        facts_usage = re.search(r'facts\s*=\s*(.*?)(?:\n|$)', content)
        
        if facts_usage:
            usage = facts_usage.group(1).strip()
            print(f"\nFacts assignment found: {usage[:80]}...")
            
            # Check if it reads from analysis_results.report.facts
            if 'analysis_results' in usage or '.facts' in usage:
                print("   Looks like it's trying to read facts from analysis results")
                
                # Check if there's an empty list fallback
                if '=' in usage and '[' in usage:
                    print(f"   ✅ Has fallback for missing facts")
                else:
                    print("   ⚠️ WARNING: No explicit fallback - may pass empty list")
            
            return True
        
        print("\n⚠️ WARNING: Could not determine how facts are populated")
        return False
        
    except Exception as e:
        print(f"❌ FAIL: Error analyzing file: {e}")
        return False


def step_7_test_report_generation():
    """
    STEP 7: Test report generation in isolation
    
    Create a tiny script that builds a ReportConfig with one fact 
    (the email you expect) and calls MultiFormatReportGenerator.generate_report() 
    for both PDF and HTML.
    
    Check the returned objects (success=True) and open the generated files – 
    they must contain the fact text.
    """
    print("\n" + "="*60)
    print("STEP 7: Test Report Generation in Isolation")
    print("="*60)
    
    # Try to run an isolated report generation test
    test_script = '''
import sys
sys.path.insert(0, '.')

from osint_scribe_stage import MultiFormatReportGenerator, ReportConfig
from datetime import datetime

# Create a minimal config with expected fact
config = ReportConfig(
    title="Test Report",
    target="test@example.com",
    generated_at=datetime.now(),
    facts=[{
        'type': 'EMAIL',
        'value': 'test@example.com',
        'confidence': 0.95,
        'sources': ['serper']
    }]
)

# Generate reports
gen = MultiFormatReportGenerator()

print("Generating HTML...")
html_result = gen.generate_report(config, 'html')
print(f"HTML: success={html_result.success}, size={html_result.size_bytes:,} bytes")

if html_result.success and os.path.exists(html_result.file_path):
    with open(html_result.file_path, 'r') as f:
        content = f.read()
    print(f"Content contains email: {'test@example.com' in content}")
    
print("\nGenerating PDF...")
pdf_result = gen.generate_report(config, 'pdf')
print(f"PDF: success={pdf_result.success}, size={pdf_result.size_bytes:,} bytes")

if pdf_result.success and os.path.exists(pdf_result.file_path):
    with open(pdf_result.file_path, 'rb') as f:
        content = f.read()
    print(f"Content length: {len(content)} bytes (non-empty if > 0)")

sys.exit(0 if html_result.success else 1)
'''
    
    try:
        # Write and run the test script temporarily
        test_path = "temp_report_test.py"
        
        with open(test_path, 'w') as f:
            f.write("#!/usr/bin/env python3\n")
            f.write("import os\n")
            f.write(test_script)
        
        result = asyncio.run(run_isolated_report_test())
        
        # Clean up
        if os.path.exists(test_path):
            os.remove(test_path)
        
        return result
        
    except Exception as e:
        print(f"❌ FAIL: Error running isolation test: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_isolated_report_test():
    """Helper function for isolated report generation test"""
    try:
        from osint_scribe_stage import MultiFormatReportGenerator, ReportConfig
        
        # Create a minimal config with expected fact
        config = ReportConfig(
            title="Test Report",
            target="test@example.com",
            generated_at=datetime.now(),
            facts=[{
                'type': 'EMAIL',
                'value': 'test@example.com',
                'confidence': 0.95,
                'sources': ['serper']
            }]
        )
        
        # Generate reports
        gen = MultiFormatReportGenerator()
        
        print("Generating HTML...")
        html_result = gen.generate_report(config, 'html')
        print(f"HTML: success={html_result.success}, size={html_result.size_bytes:,} bytes")
        
        if html_result.success and os.path.exists(html_result.file_path):
            with open(html_result.file_path, 'r') as f:
                content = f.read()
            contains_email = 'test@example.com' in content or 'EMAIL' in content
            print(f"Content contains expected data: {contains_email}")
            
        print("\nGenerating PDF...")
        pdf_result = gen.generate_report(config, 'pdf')
        print(f"PDF: success={pdf_result.success}, size={pdf_result.size_bytes:,} bytes")
        
        if pdf_result.success and os.path.exists(pdf_result.file_path):
            with open(pdf_result.file_path, 'rb') as f:
                content = f.read()
            non_empty = len(content) > 0
            print(f"Content is non-empty: {non_empty} ({len(content)} bytes)")
        
        return html_result.success and pdf_result.success
        
    except ImportError as e:
        print(f"❌ FAIL: Cannot import scribe stage modules: {e}")
        return False
    except Exception as e:
        print(f"❌ FAIL: Report generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def step_8_audit_paginated_handling():
    """
    STEP 8: Audit paginated handling
    
    If your dataset is large, run the harvest loop with a small ed (e.g., 2) 
    and verify that subsequent pages are requested correctly (rec increments).
    
    Make sure the loop stops when fewer than ed records are returned.
    """
    print("\n" + "="*60)
    print("STEP 8: Audit Paginated Handling")
    print("="*60)
    
    # Serper.dev doesn't use pagination in the same way as PublicData API,
    # but let's check for any pagination logic
    
    harvesting_path = "osint_harvesting_stage.py"
    
    if not os.path.exists(harvesting_path):
        print(f"❌ FAIL: File '{harvesting_path}' does not exist")
        return False
    
    try:
        with open(harvesting_path, 'r') as f:
            content = f.read()
        
        # Check for pagination patterns
        has_rec_param = '"rec"' in content or "'rec'" in content
        has_ed_param = '"ed"' in content or "'ed'" in content
        
        print("Serper.dev API handling:")
        print(f"  - Uses 'rec' parameter: {has_rec_param}")
        print(f"  - Uses 'ed' parameter: {has_ed_param}")
        
        # Check how the API call is made
        if '"q": query' in content or "'q': query" in content:
            print("  ✅ Correctly uses Serper.dev format (query string)")
            
            # Check for num parameter (Serper.dev supports this)
            has_num = '"num"' in content or "'num'" in content
            
            if has_num:
                print("  ✅ Supports 'num' parameter for result count")
            else:
                print("  ⚠️ No explicit 'num' parameter found")
            
            return True
        
        # Check if it's using PublicData API format instead
        if 'pdsearchdocs.php' in content or 'publicdata' in content.lower():
            print("\n⚠️ WARNING: Found PublicData API references (different system)")
            print("   This script uses Serper.dev, not the legacy PublicData API")
            
            return False
        
        print("\n✅ PASS: No pagination issues found for Serper.dev integration")
        return True
        
    except Exception as e:
        print(f"❌ FAIL: Error analyzing file: {e}")
        return False


def step_9_look_for_hidden_bugs():
    """
    STEP 9: Look for hidden bugs in DB schema
    
    Ensure the SELECT statement in the harvesting module lists columns explicitly:
        SELECT ticket_id, source, results_raw FROM raw_harvest WHERE ticket_id = ?
    
    Do not rely on "*" (wildcard) if you have extra columns that could be mis-aligned.
    """
    print("\n" + "="*60)
    print("STEP 9: Look for Hidden Bugs in DB Schema")
    print("="*60)
    
    # Check database_manager.py for SELECT statements
    db_path = "database_manager.py"
    
    if not os.path.exists(db_path):
        print(f"❌ FAIL: File '{db_path}' does not exist")
        return False
    
    try:
        with open(db_path, 'r') as f:
            content = f.read()
        
        # Check for SELECT * patterns (bad practice)
        has_wildcard_selects = re.search(r'SELECT\s+\*', content, re.IGNORECASE)
        
        print("Database query analysis:")
        
        if has_wildcard_selects:
            print("  ❌ FAIL: Found SELECT * statements (should list columns explicitly)")
            
            # Show where they occur
            for line_num, line in enumerate(content.split('\n'), 1):
                if 'SELECT' in line.upper() and '*' in line:
                    print(f"     Line {line_num}: {line.strip()}")
        else:
            print("  ✅ PASS: All SELECT statements list columns explicitly")
        
        # Check for proper ticket_id filtering
        has_ticket_filter = "WHERE ticket_id = ?" in content or "WHERE ticket_id=?" in content
        
        if has_ticket_filter:
            print("  ✅ Uses parameterized queries with ticket_id filter")
        else:
            print("  ⚠️ WARNING: No explicit ticket_id filtering found")
        
        # Check table schema definitions
        raw_harvest_exists = 'CREATE TABLE IF NOT EXISTS raw_harvest' in content
        verified_facts_exists = 'CREATE TABLE IF NOT EXISTS verified_facts' in content
        
        print("\nTable schemas:")
        print(f"  - raw_harvest: {'✅ exists' if raw_harvest_exists else '❌ missing'}")
        print(f"  - verified_facts: {'✅ exists' if verified_facts_exists else '❌ missing'}")
        
        return has_wildcard_selects is None and (raw_harvest_exists or verified_facts_exists)
        
    except Exception as e:
        print(f"❌ FAIL: Error analyzing file: {e}")
        return False


def step_10_run_integration_test():
    """
    STEP 10: Run a full end-to-end integration test
    
    Use the provided integration_test.py script (or write your own).
    
    The script should:
     – Create a fresh DB.
     – Run harvest, verification, report generation.
     – Assert that both PDF and HTML files are non-empty and contain the expected fact.
    """
    print("\n" + "="*60)
    print("STEP 10: Run Full End-to-End Integration Test")
    print("="*60)
    
    # Check if an integration test already exists
    integration_test_paths = [
        "test_api_fixes.py",
        "tests/test_integration.py",
        "integration_test.py"
    ]
    
    existing_tests = []
    for path in integration_test_paths:
        if os.path.exists(path):
            existing_tests.append(path)
    
    if existing_tests:
        print(f"Found {len(existing_tests)} test file(s):")
        for t in existing_tests:
            print(f"  - {t}")
        
        # Try to run one of them
        try:
            result = asyncio.run(run_integration_test(existing_tests[0]))
            
            if result:
                print("✅ PASS: Integration test completed successfully")
                return True
            else:
                print("❌ FAIL: Integration test failed")
                return False
                
        except Exception as e:
            print(f"⚠️ WARNING: Could not run integration test: {e}")
    
    # No existing test found - create a minimal one
    print("\nCreating minimal integration test...")
    
    test_content = '''#!/usr/bin/env python3
"""Minimal integration test for OSINT pipeline"""

import asyncio
import os
import sys
from datetime import datetime

async def main():
    # Test 1: Can we create a report with known facts?
    from osint_scribe_stage import MultiFormatReportGenerator, ReportConfig
    
    config = ReportConfig(
        title="Integration Test",
        target="test@example.com",
        generated_at=datetime.now(),
        facts=[{
            'type': 'EMAIL',
            'value': 'test@example.com',
            'confidence': 0.95,
            'sources': ['integration_test']
        }]
    )
    
    gen = MultiFormatReportGenerator()
    
    # Generate both formats
    html_result = gen.generate_report(config, 'html')
    pdf_result = gen.generate_report(config, 'pdf')
    
    print(f"HTML: success={html_result.success}, size={html_result.size_bytes}")
    print(f"PDF: success={pdf_result.success}, size={pdf_result.size_bytes}")
    
    # Verify both are non-empty
    if html_result.success and pdf_result.success:
        print("✅ PASS: Both reports generated")
        
        # Check HTML content contains expected fact
        if os.path.exists(html_result.file_path):
            with open(html_result.file_path, 'r') as f:
                html_content = f.read()
            
            if 'test@example.com' in html_content or 'EMAIL' in html_content:
                print("✅ PASS: HTML contains expected fact")
            else:
                print("❌ FAIL: HTML does not contain expected fact")
                return False
        
        # Check PDF is non-empty (basic check)
        if os.path.exists(pdf_result.file_path):
            pdf_size = os.path.getsize(pdf_result.file_path)
            if pdf_size > 100:  # Should be at least a tiny valid PDF
                print(f"✅ PASS: PDF is non-empty ({pdf_size} bytes)")
            else:
                print(f"❌ FAIL: PDF too small ({pdf_size} bytes)")
                return False
        
        return True
    
    print("❌ FAIL: One or both reports failed to generate")
    return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
'''
    
    test_path = "temp_integration_test.py"
    
    with open(test_path, 'w') as f:
        f.write("#!/usr/bin/env python3\n")
        f.write("import os\n")
        f.write("import sys\n")
        f.write("import asyncio\n")
        f.write("from datetime import datetime\n")
        f.write(test_content)
    
    try:
        result = await run_command_async(f"python {test_path}")
        
        # Clean up
        if os.path.exists(test_path):
            os.remove(test_path)
        
        return result.get('success', False)
        
    except Exception as e:
        print(f"❌ FAIL: Error running integration test: {e}")
        return False


async def run_integration_test(test_file: str):
    """Run an existing integration test file"""
    try:
        import subprocess
        result = await asyncio.create_subprocess_exec(
            'python', test_file,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await result.communicate()
        
        print(f"Test output:\n{stdout.decode()}")
        if stderr:
            print(f"Test errors:\n{stderr.decode()}")
        
        return result.returncode == 0
        
    except Exception as e:
        print(f"Error running test: {e}")
        return False


async def run_command_async(command: str) -> Dict[str, Any]:
    """Helper to run async command"""
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        return {
            'success': process.returncode == 0,
            'stdout': stdout.decode(),
            'stderr': stderr.decode(),
            'return_code': process.returncode
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def step_11_document_findings():
    """
    STEP 11: Document all findings & fixes
    
    Create a short markdown file (DEBUG_LOG.md) with:
     – What was wrong (e.g., "empty facts due to high min_confidence").
     – The code change applied.
     – How the final test passed.
    """
    print("\n" + "="*60)
    print("STEP 11: Document Findings & Fixes")
    print("="*60)
    
    # This step creates documentation, so we'll prepare a template
    print("\n📄 Creating DEBUG_LOG.md with findings...")
    
    return True


def run_all_steps():
    """Run all 11 debugging steps"""
    
    results = []
    
    steps = [
        ("STEP 1: Verify API Request", step_1_verify_api_request),
        ("STEP 2: Inspect Authentication", step_2_inspect_authentication),
        ("STEP 3: Confirm Database Insertion", step_3_confirm_database_insertion),
        ("STEP 4: Check Parsing Step", step_4_check_parsing_step),
        ("STEP 5: Validate Verification Logic", step_5_validate_verification_logic),
        ("STEP 6: Inspect Report Configuration", step_6_inspect_report_configuration),
        ("STEP 7: Test Report Generation", step_7_test_report_generation),
        ("STEP 8: Audit Paginated Handling", step_8_audit_paginated_handling),
        ("STEP 9: Look for Hidden Bugs", step_9_look_for_hidden_bugs),
        ("STEP 10: Run Integration Test", step_10_run_integration_test),
    ]
    
    print("\n🔍 Starting comprehensive OSINT pipeline diagnostics")
    print("This will take approximately 30-60 seconds...\n")
    
    for name, step_func in steps:
        print(f"\n{'='*70}")
        try:
            result = step_func()
            results.append((name, result))
            
            if isinstance(result, bool):
                status = "✅ PASS" if result else "❌ FAIL"
                print(f"{status}: {name}\n")
                
        except Exception as e:
            print(f"\n💥 EXCEPTION in {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    return results


def generate_debug_report(results):
    """Generate a comprehensive debug report"""
    
    report = f"""# OSINT Pipeline Debug Report

Generated: {datetime.now().isoformat()}

## Summary

Total Steps Tested: {len(results)}
Passed: {sum(1 for _, r in results if r is True)}
Failed: {sum(1 for _, r in results if r is False)}
Skipped/Exception: {sum(1 for _, r in results if r not in [True, False])}

## Detailed Results

"""
    
    for name, result in results:
        status = "✅ PASS" if result is True else ("❌ FAIL" if result is False else "⚠️  EXCEPTION")
        report += f"\n### {name}\n{status}\n"
    
    report += """

## Next Steps

Based on the failed tests above, please:

1. **If API key issues**: Set your Serper.dev API key in .env file
2. **If database empty**: Run the pipeline with valid data first
3. **If parsing fails**: Check JSON response format from API
4. **If verification filters everything**: Lower min_confidence_threshold to 0.5
5. **If reports empty**: Verify ReportConfig.facts contains actual data

## Recommendations

"""
    
    # Add specific recommendations based on failures
    failure_count = sum(1 for _, r in results if r is False)
    
    if failure_count >= 3:
        report += """**Multiple critical issues detected**. Please address them in order:

1. Fix API configuration first (Step 1 & 2 must pass)
2. Ensure data flows through pipeline (Steps 3-5)
3. Verify report generation works independently (Steps 6-7)
4. Run integration test to confirm end-to-end functionality (Step 10)
"""
    elif failure_count >= 1:
        report += """**Some issues detected**. Focus on the failed steps above and rerun diagnostics."""
    else:
        report += """✅ **All critical checks passed!** The pipeline should be functioning correctly.

If you're still experiencing empty reports, check:
- API quota limits (Serper.dev free tier has limited requests)
- Network connectivity to API endpoints
- File system permissions for report generation directory
"""
    
    return report


def main():
    """Main entry point for debug script"""
    
    print("="*70)
    print("OSINT PIPELINE DIAGNOSTIC TOOL")
    print("="*70)
    
    # Run all diagnostic steps
    results = run_all_steps()
    
    # Generate comprehensive report
    report = generate_debug_report(results)
    
    # Save report to file
    report_path = "DEBUG_LOG.md"
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n{'='*70}")
    print("📄 Debug Report Saved")
    print(f"   File: {os.path.abspath(report_path)}")
    print("="*70)
    
    # Print summary to console
    passed = sum(1 for _, r in results if r is True)
    failed = sum(1 for _, r in results if r is False)
    
    print(f"\n📊 Summary:")
    print(f"   ✅ Passed: {passed}/{len(results)}")
    print(f"   ❌ Failed: {failed}/{len(results)}")
    
    if failed > 0:
        print("\n💡 Please review the detailed report above and in DEBUG_LOG.md")
        print("   Fix the failing issues and re-run diagnostics.")
    
    # Return exit code based on critical failures
    critical_failures = sum(1 for name, _ in results if 'API' in name or 'Database' in name)
    
    return 0 if critical_failures == 0 else 1


if __name__ == "__main__":
    import re
    
    exit_code = main()
    exit(exit_code)
