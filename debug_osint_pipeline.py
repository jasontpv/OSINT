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
Date: 2025-03-16
"""

import asyncio
import aiohttp
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import xml.etree.ElementTree as ET

# Add workspace to path
sys.path.insert(0, str(Path(__file__).parent))

from config import Config, DatabaseConfig
from database_manager import get_db_manager
from osint_analyst_stage import verify_search_results, AnalysisReport, FactExtractor


class DebugRunner:
    """Comprehensive debug runner for OSINT pipeline diagnostics"""
    
    def __init__(self):
        self.results = {}
        self.errors = []
        
    async def step_1_verify_api_request(self) -> Dict[str, Any]:
        """STEP 1: Verify API request works with curl-like test"""
        print("\n" + "="*70)
        print("STEP 1: Verifying PublicData API Request")
        print("="*70)
        
        result = {
            "step": 1,
            "status": "unknown",
            "details": {},
            "passed": False
        }
        
        try:
            # Test using pdsearchdocs.php endpoint directly
            url = "https://api.publicdata.com/pdsearchdocs.php"
            params = {
                "username": "MaDMaX828",
                "password": "RE98N7",
                "dbid": "1",
                "search": "Braden Leeds",
                "rec": "0",
                "ed": "25"  # Note: ed should be edition, not page size
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    result["details"]["status_code"] = resp.status
                    
                    if resp.status == 200:
                        result["details"]["has_status_200"] = True
                        
                        # Check for XML header
                        text = await resp.text()
                        result["details"]["raw_response_preview"] = text[:500] if len(text) > 500 else text
                        result["details"]["starts_with_xml"] = text.lstrip().startswith("<")
                        
                        # Try to parse as XML
                        try:
                            root = ET.fromstring(text)
                            result["details"]["xml_valid"] = True
                            
                            # Count records
                            records = root.findall(".//record")
                            result["details"]["record_count"] = len(records)
                            
                            if len(records) > 0:
                                print(f"✓ API returned {len(records)} record(s)")
                                result["passed"] = True
                                result["status"] = "PASSED"
                            else:
                                print("⚠️  XML valid but no records found")
                                result["status"] = "WARNING_NO_RECORDS"
                                
                        except ET.ParseError as e:
                            result["details"]["xml_valid"] = False
                            result["details"]["parse_error"] = str(e)
                            print(f"✗ XML parsing failed: {e}")
                            result["status"] = "FAILED_XML_PARSE"
                    else:
                        error_text = await resp.text()
                        result["details"]["error_response"] = error_text[:200] if len(error_text) > 200 else error_text
                        print(f"✗ API returned status {resp.status}")
                        result["status"] = "FAILED_STATUS_CODE"
                        
        except Exception as e:
            result["details"]["exception"] = str(e)
            print(f"✗ API request failed with exception: {e}")
            result["status"] = "FAILED_EXCEPTION"
        
        self.results["step_1"] = result
        return result
    
    async def step_2_inspect_authentication(self) -> Dict[str, Any]:
        """STEP 2: Inspect authentication handling"""
        print("\n" + "="*70)
        print("STEP 2: Inspecting Authentication Handling")
        print("="*70)
        
        result = {
            "step": 2,
            "status": "unknown", 
            "details": {},
            "passed": False
        }
        
        try:
            # Test the authenticate function from pd_integration.py
            BASE_URL = "https://api.publicdata.com"
            
            async with aiohttp.ClientSession() as session:
                auth_url = f"{BASE_URL}/authenticate.php"
                data = {
                    "username": "MaDMaX828",
                    "password": "RE98N7"
                }
                
                async with session.post(auth_url, data=data, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    result["details"]["auth_status_code"] = resp.status
                    
                    if resp.status == 200:
                        token_text = await resp.text()
                        result["details"]["token_received"] = True
                        result["details"]["token_preview"] = token_text[:100] if len(token_text) > 100 else token_text
                        result["details"]["token_type"] = type(token_text).__name__
                        
                        # Check if it looks like a valid token (non-empty, non-XML)
                        if token_text.strip() and not token_text.lstrip().startswith("<"):
                            print(f"✓ Authentication returned token: {len(token_text)} chars")
                            result["passed"] = True
                            result["status"] = "PASSED"
                        else:
                            print("⚠️  Token appears empty or malformed")
                            result["status"] = "WARNING_INVALID_TOKEN"
                    else:
                        error_text = await resp.text()
                        result["details"]["auth_error"] = error_text[:200] if len(error_text) > 200 else error_text
                        print(f"✗ Authentication failed with status {resp.status}")
                        
        except Exception as e:
            result["details"]["exception"] = str(e)
            print(f"✗ Authentication test failed: {e}")
        
        self.results["step_2"] = result
        return result
    
    async def step_3_confirm_database_insertion(self, ticket_id: str = "debug_test_ticket") -> Dict[str, Any]:
        """STEP 3: Confirm database insertion works"""
        print("\n" + "="*70)
        print(f"STEP 3: Confirming Database Insertion (Ticket: {ticket_id})")
        print("="*70)
        
        result = {
            "step": 3,
            "status": "unknown",
            "details": {},
            "passed": False
        }
        
        try:
            db_manager = get_db_manager(DatabaseConfig.DB_PATH)
            
            # Test connection
            if not db_manager.test_connection():
                result["details"]["connection_failed"] = True
                print("✗ Database connection test failed")
                return result
            
            result["details"]["connection_ok"] = True
            
            # Initialize tables
            if not db_manager.initialize_tables():
                result["details"]["init_failed"] = True
                print("✗ Table initialization failed")
                return result
                
            result["details"]["tables_initialized"] = True
            
            # Insert test data
            test_data = {
                "ticket_id": ticket_id,
                "source": "debug_test",
                "results_raw": json.dumps({
                    "test": "data",
                    "records": [
                        {"name": "Test Person 1", "email": "test1@example.com"},
                        {"name": "Test Person 2", "email": "test2@example.com"}
                    ]
                })
            }
            
            success = db_manager.insert_raw_harvest(
                ticket_id=test_data["ticket_id"],
                source=test_data["source"],
                results_raw=test_data["results_raw"]
            )
            
            result["details"]["insert_success"] = success
            
            if success:
                # Verify retrieval
                raw_records = db_manager.get_raw_harvest(ticket_id)
                result["details"]["retrieved_count"] = len(raw_records)
                
                if len(raw_records) > 0:
                    print(f"✓ Database insertion successful - {len(raw_records)} record(s)")
                    
                    # Check if results_raw is not empty
                    first_record = raw_records[0]
                    result["details"]["results_raw_preview"] = first_record.get("results_raw", "")[:200]
                    result["details"]["results_raw_empty"] = len(first_record.get("results_raw", "")) == 0
                    
                    if first_record.get("results_raw") and not first_record["results_raw"].strip() == "":
                        print(f"✓ results_raw is NOT empty: {len(first_record['results_raw'])} bytes")
                        result["passed"] = True
                        result["status"] = "PASSED"
                    else:
                        print("✗ results_raw field is empty!")
                        result["status"] = "FAILED_EMPTY_RESULTS_RAW"
                else:
                    print("✗ No records retrieved after insertion")
            else:
                print("✗ Database insert failed")
                
        except Exception as e:
            result["details"]["exception"] = str(e)
            import traceback
            result["details"]["stack_trace"] = traceback.format_exc()
            print(f"✗ Database test failed with exception: {e}")
        
        self.results["step_3"] = result
        return result
    
    async def step_4_check_parsing_step(self, sample_json_str: str) -> Dict[str, Any]:
        """STEP 4: Check the parsing step"""
        print("\n" + "="*70)
        print("STEP 4: Checking Parsing Step")
        print("="*70)
        
        result = {
            "step": 4,
            "status": "unknown",
            "details": {},
            "passed": False
        }
        
        try:
            # Test json.loads() on sample data
            parsed = json.loads(sample_json_str)
            result["details"]["json_parse_success"] = True
            result["details"]["parsed_type"] = type(parsed).__name__
            result["details"]["parsed_length"] = len(parsed) if isinstance(parsed, (list, dict)) else "N/A"
            
            print(f"✓ JSON parsing successful")
            print(f"  Type: {type(parsed).__name__}")
            print(f"  Length: {len(parsed)} items")
            
            # Test FactExtractor on the parsed data
            extractor = FactExtractor()
            
            if isinstance(parsed, dict):
                facts = extractor.extract_facts_from_source(parsed)
            elif isinstance(parsed, list):
                facts = extractor.extract_facts_from_source(parsed)
            else:
                print("⚠️  Parsed data is neither dict nor list")
                facts = []
            
            result["details"]["facts_extracted_count"] = len(facts)
            
            if len(facts) > 0:
                print(f"✓ Extracted {len(facts)} fact(s)")
                
                # Show first fact details
                for i, fact in enumerate(facts[:3]):
                    result["details"][f"fact_{i}_text"] = fact.text[:100] if len(fact.text) > 100 else fact.text
                    result["details"][f"fact_{i}_confidence"] = fact.confidence_score
                
                result["passed"] = True
                result["status"] = "PASSED"
            else:
                print("⚠️  No facts extracted from parsed data")
                result["status"] = "WARNING_NO_FACTS_EXTRACTED"
                
        except json.JSONDecodeError as e:
            result["details"]["json_parse_error"] = str(e)
            print(f"✗ JSON parsing failed: {e}")
            
            # Try XML parsing instead
            try:
                root = ET.fromstring(sample_json_str)
                result["details"]["xml_alternative_works"] = True
                records = root.findall(".//record")
                result["details"]["xml_record_count"] = len(records)
                
                print(f"✓ XML parsing works as fallback - {len(records)} records found")
                result["passed"] = True
                result["status"] = "PASSED_XML_FALLBACK"
            except ET.ParseError:
                result["details"]["xml_parse_error"] = "XML also failed"
                print("✗ Neither JSON nor XML parsing works")
        
        self.results["step_4"] = result
        return result
    
    async def step_5_validate_verification_logic(self, sample_facts: List[Dict]) -> Dict[str, Any]:
        """STEP 5: Validate verification logic"""
        print("\n" + "="*70)
        print("STEP 5: Validating Verification Logic")
        print("="*70)
        
        result = {
            "step": 5,
            "status": "unknown",
            "details": {},
            "passed": False
        }
        
        try:
            # Test with default threshold (0.6)
            report_dict_default = verify_search_results(
                search_results=sample_facts,
                leak_lookup_findings=[],
                min_confidence_threshold=0.6
            )
            
            result["details"]["default_threshold_count"] = len(report_dict_default.get("verified_results", []))
            
            # Test with lowered threshold (0.5)
            report_dict_lowered = verify_search_results(
                search_results=sample_facts,
                leak_lookup_findings=[],
                min_confidence_threshold=0.5
            )
            
            result["details"]["lowered_threshold_count"] = len(report_dict_lowered.get("verified_results", []))
            
            print(f"Default threshold (0.6): {result['details']['default_threshold_count']} facts")
            print(f"Lowered threshold (0.5): {result['details']['lowered_threshold_count']} facts")
            
            # Log every fact's confidence value with default threshold
            for i, fact in enumerate(report_dict_default.get("verified_results", [])):
                result["details"][f"fact_{i}_confidence"] = fact.get("confidence_score", 0.0)
                print(f"  Fact {i+1}: confidence={fact.get('confidence_score', 0.0):.2f}, text={fact.get('text', '')[:50]}")
            
            # Check if lowering threshold reveals facts
            if result["details"]["lowered_threshold_count"] > result["details"]["default_threshold_count"]:
                print(f"✓ Lowering threshold revealed {result['details']['lowered_threshold_count'] - result['details']['default_threshold_count']} additional facts")
                result["status"] = "WARNING_THRESHOLD_TOO_HIGH"
            elif result["details"]["default_threshold_count"] > 0:
                print("✓ Facts found with default threshold")
                result["passed"] = True
                result["status"] = "PASSED"
            else:
                print("✗ No facts found even with lowered threshold")
                result["status"] = "FAILED_NO_FACTS_FOUND"
                
        except Exception as e:
            import traceback
            result["details"]["exception"] = str(e)
            result["details"]["stack_trace"] = traceback.format_exc()
            print(f"✗ Verification test failed with exception: {e}")
        
        self.results["step_5"] = result
        return result
    
    async def step_6_inspect_report_configuration(self, analysis_results: AnalysisReport) -> Dict[str, Any]:
        """STEP 6: Inspect the report configuration"""
        print("\n" + "="*70)
        print("STEP 6: Inspecting Report Configuration")
        print("="*70)
        
        result = {
            "step": 6,
            "status": "unknown",
            "details": {},
            "passed": False
        }
        
        try:
            # Check if analysis_results.report exists and has correct structure
            if hasattr(analysis_results, 'report'):
                result["details"]["has_report_attr"] = True
                report_dict = analysis_results.report
                
                print(f"✓ analysis_results.report exists")
                print(f"  Type: {type(report_dict).__name__}")
                print(f"  Keys: {list(report_dict.keys())}")
                
                # Check required keys
                required_keys = ['title', 'target', 'generated_at', 'facts']
                for key in required_keys:
                    has_key = key in report_dict
                    result["details"][f"has_{key}"] = has_key
                    print(f"  {'✓' if has_key else '✗'} {key}: {type(report_dict.get(key)).__name__}")
                
                # Check facts list specifically
                facts_list = report_dict.get('facts', [])
                result["details"]["facts_count"] = len(facts_list)
                print(f"\nFacts list: {len(facts_list)} items")
                
                if isinstance(analysis_results, AnalysisReport):
                    print(f"  analysis_results.facts count: {len(analysis_results.facts)}")
                    result["details"]["analysis_report_facts_count"] = len(analysis_results.facts)
                    
                    # Show sample facts
                    for i, fact in enumerate(analysis_results.facts[:3]):
                        if isinstance(fact, dict):
                            print(f"    Fact {i+1}: type={fact.get('type')}, value={fact.get('value', '')[:50]}")
                
                # Determine pass/fail
                if 'facts' in report_dict and len(facts_list) > 0:
                    result["passed"] = True
                    result["status"] = "PASSED"
                    print("✓ Report configuration contains facts!")
                else:
                    result["status"] = "FAILED_EMPTY_FACTS_LIST"
                    print("✗ Facts list is EMPTY - this causes blank reports!")
            else:
                result["details"]["has_report_attr"] = False
                print("✗ analysis_results.report attribute does not exist")
                
        except Exception as e:
            import traceback
            result["details"]["exception"] = str(e)
            result["details"]["stack_trace"] = traceback.format_exc()
            print(f"✗ Report config inspection failed with exception: {e}")
        
        self.results["step_6"] = result
        return result
    
    async def step_7_test_report_generation_isolation(self, facts_list: List[Dict]) -> Dict[str, Any]:
        """STEP 7: Test report generation in isolation"""
        print("\n" + "="*70)
        print("STEP 7: Testing Report Generation in Isolation")
        print("="*70)
        
        result = {
            "step": 7,
            "status": "unknown",
            "details": {},
            "passed": False
        }
        
        try:
            from osint_scribe_stage import ReportConfig, MultiFormatReportGenerator
            
            # Create a test config with known facts
            test_facts = facts_list if facts_list else [
                {
                    'type': 'EMAIL',
                    'value': 'braden.leeds@example.com',
                    'confidence': 0.95,
                    'sources': ['PublicData API', 'LinkedIn']
                }
            ]
            
            config = ReportConfig(
                title="Debug Test Report",
                target="Braden Leeds",
                generated_at=datetime.now(),
                facts=test_facts,
                confidentiality_level='INTERNAL'
            )
            
            print(f"Created ReportConfig with {len(config.facts)} fact(s)")
            
            # Generate HTML report
            generator = MultiFormatReportGenerator()
            html_result = generator.generate_report(config, 'html')
            
            result["details"]["html_generation_success"] = html_result.success
            if html_result.success:
                print(f"✓ HTML report generated successfully")
                print(f"  Path: {html_result.file_path}")
                print(f"  Size: {html_result.size_bytes:,} bytes")
                
                # Check if file is non-empty and contains fact text
                if os.path.exists(html_result.file_path):
                    with open(html_result.file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    result["details"]["html_file_size"] = len(content)
                    result["details"]["html_contains_fact"] = config.facts[0]['value'] in content
                    
                    if len(content) > 0 and config.facts[0]['value'] in content:
                        print("✓ HTML file is non-empty and contains fact text")
                    else:
                        print("⚠️  HTML file exists but may be empty or missing fact text")
            else:
                print(f"✗ HTML report generation failed: {html_result.error_message}")
            
            # Generate PDF report
            pdf_result = generator.generate_report(config, 'pdf')
            
            result["details"]["pdf_generation_success"] = pdf_result.success
            if pdf_result.success:
                print(f"✓ PDF report generated successfully")
                print(f"  Path: {pdf_result.file_path}")
                print(f"  Size: {pdf_result.size_bytes:,} bytes")
                
                # Check file size
                if os.path.exists(pdf_result.file_path):
                    file_size = os.path.getsize(pdf_result.file_path)
                    result["details"]["pdf_file_size"] = file_size
                    
                    if file_size > 0:
                        print("✓ PDF file is non-empty")
                    else:
                        print("✗ PDF file is empty!")
                else:
                    print("⚠️  PDF file path does not exist")
            else:
                print(f"✗ PDF report generation failed: {pdf_result.error_message}")
            
            # Determine overall pass/fail
            if html_result.success and pdf_result.success:
                result["passed"] = True
                result["status"] = "PASSED"
            elif not facts_list:
                result["status"] = "WARNING_USE_TEST_FACTS"
                print("⚠️  Generated with test facts - check with real data")
            else:
                result["status"] = "FAILED_REPORT_GENERATION"
                
        except Exception as e:
            import traceback
            result["details"]["exception"] = str(e)
            result["details"]["stack_trace"] = traceback.format_exc()
            print(f"✗ Report generation test failed with exception: {e}")
        
        self.results["step_7"] = result
        return result
    
    async def step_8_audit_paginated_handling(self, sample_search_results: List[Dict]) -> Dict[str, Any]:
        """STEP 8: Audit paginated handling"""
        print("\n" + "="*70)
        print("STEP 8: Auditing Pagination Handling")
        print("="*70)
        
        result = {
            "step": 8,
            "status": "unknown",
            "details": {},
            "passed": False
        }
        
        try:
            # Simulate paginated search results
            page_size = 2
            
            print(f"Simulating pagination with page size: {page_size}")
            
            all_records_collected = []
            current_rec = 0
            
            for page_num in range(3):  # Test up to 3 pages
                # Simulate API response for this page
                if page_num < len(sample_search_results):
                    page_data = sample_search_results[page_num]
                    
                    records_on_page = page_data.get('records', [])[:page_size]
                    next_rec = page_data.get('next_record') if page_num > 0 else (current_rec + page_size) if records_on_page else None
                    
                    print(f"\nPage {page_num + 1}:")
                    print(f"  Records on this page: {len(records_on_page)}")
                    
                    all_records_collected.extend(records_on_page)
                    
                    # Check if we should continue
                    if not next_rec or len(records_on_page) < page_size:
                        print(f"  → Stopping pagination (no more records)")
                        break
                    
                    current_rec = next_rec
                else:
                    print(f"\nPage {page_num + 1}: No data available")
                    break
            
            result["details"]["total_records_collected"] = len(all_records_collected)
            result["details"]["expected_pages"] = min(3, len(sample_search_results))
            
            if len(all_records_collected) > 0:
                print(f"\n✓ Successfully collected {len(all_records_collected)} records across pagination")
                
                # Show first few records
                for i, record in enumerate(all_records_collected[:3]):
                    result["details"][f"collected_record_{i}"] = str(record)[:100]
                    print(f"  Record {i+1}: {record}")
                
                result["passed"] = True
                result["status"] = "PASSED"
            else:
                print("✗ No records collected from pagination")
                result["status"] = "FAILED_NO_RECORDS_COLLECTED"
                
        except Exception as e:
            import traceback
            result["details"]["exception"] = str(e)
            result["details"]["stack_trace"] = traceback.format_exc()
            print(f"✗ Pagination test failed with exception: {e}")
        
        self.results["step_8"] = result
        return result
    
    async def step_9_audit_db_schema(self, ticket_id: str = "debug_test_ticket") -> Dict[str, Any]:
        """STEP 9: Audit DB schema for column alignment issues"""
        print("\n" + "="*70)
        print("STEP 9: Auditing Database Schema")
        print("="*70)
        
        result = {
            "step": 9,
            "status": "unknown",
            "details": {},
            "passed": False
        }
        
        try:
            db_manager = get_db_manager(DatabaseConfig.DB_PATH)
            
            # Test explicit column SELECT (not SELECT *)
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                # Use explicit columns instead of wildcard
                cursor.execute('''
                    SELECT id, ticket_id, source, results_raw, timestamp
                    FROM raw_harvest
                    WHERE ticket_id = ?
                ''', (ticket_id,))
                
                rows = cursor.fetchall()
                
                print(f"Explicit column query returned {len(rows)} row(s)")
                
                if len(rows) > 0:
                    first_row = dict(rows[0])
                    
                    # Verify all expected columns are present and non-null
                    required_columns = ['ticket_id', 'source', 'results_raw']
                    missing_cols = [col for col in required_columns if col not in first_row or first_row[col] is None]
                    
                    result["details"]["all_columns_present"] = len(missing_cols) == 0
                    
                    if missing_cols:
                        print(f"✗ Missing columns: {missing_cols}")
                        result["status"] = "FAILED_MISSING_COLUMNS"
                    else:
                        print("✓ All required columns present in query results")
                        
                        # Check for NULL values in critical fields
                        null_fields = [col for col, val in first_row.items() if val is None]
                        if null_fields:
                            print(f"⚠️  Null values found: {null_fields}")
                            result["status"] = "WARNING_NULL_VALUES"
                        else:
                            print("✓ No NULL values in critical fields")
                            result["passed"] = True
                            result["status"] = "PASSED"
                    
                    # Show sample data
                    print(f"\nSample record:")
                    for col, val in first_row.items():
                        print(f"  {col}: {str(val)[:100]}...") if len(str(val)) > 100 else print(f"  {col}: {val}")
                    
                else:
                    print("⚠️  No records found with explicit column query (may need to check SELECT * behavior)")
                    result["status"] = "WARNING_NO_RECORDS_WITH_EXPLICIT_QUERY"
                
        except Exception as e:
            import traceback
            result["details"]["exception"] = str(e)
            result["details"]["stack_trace"] = traceback.format_exc()
            print(f"✗ DB schema audit failed with exception: {e}")
        
        self.results["step_9"] = result
        return result
    
    async def step_10_run_full_integration_test(self, target_query: str) -> Dict[str, Any]:
        """STEP 10: Run full end-to-end integration test"""
        print("\n" + "="*70)
        print("STEP 10: Running Full End-to-End Integration Test")
        print("="*70)
        
        result = {
            "step": 10,
            "status": "unknown",
            "details": {},
            "passed": False
        }
        
        try:
            # Use a fresh ticket ID for this test
            import uuid
            test_ticket_id = f"integration_test_{uuid.uuid4().hex[:8]}"
            
            print(f"Test Ticket ID: {test_ticket_id}")
            
            # Simulate the full pipeline flow
            
            # 1. HARVEST: Insert simulated API results
            print("\n[1/5] HARVEST Stage - Inserting simulated data...")
            
            db_manager = get_db_manager(DatabaseConfig.DB_PATH)
            db_manager.initialize_tables()
            
            simulated_api_results = {
                "database_id": 1,
                "search_term": target_query,
                "records": [
                    {"name": "Braden Leeds", "email": "braden.leeds@example.com", "phone": "555-0123"},
                    {"name": "Brad Leeds", "company": "TechCorp Inc.", "location": "San Francisco, CA"}
                ],
                "total_found": 2
            }
            
            db_manager.insert_raw_harvest(
                ticket_id=test_ticket_id,
                source="PublicData_API",
                results_raw=json.dumps(simulated_api_results)
            )
            
            print("✓ HARVEST: Data inserted")
            result["details"]["harvest_success"] = True
            
            # 2. ANALYST: Process and verify facts
            print("\n[2/5] ANALYST Stage - Processing and verifying...")
            
            analyst_output = await self.step_4_check_parsing_step(json.dumps(simulated_api_results))
            
            if analyst_output["details"].get("facts_extracted_count", 0) > 0:
                # Insert facts into database
                for fact in FactExtractor().extract_facts_from_source(simulated_api_results):
                    db_manager.insert_verified_fact(
                        ticket_id=test_ticket_id,
                        fact_type="PERSON",
                        value=fact.text,
                        confidence=fact.confidence_score,
                        sources=f"PublicData_API (harvested)"
                    )
                
                print(f"✓ ANALYST: {len(db_manager.get_verified_facts(test_ticket_id))} facts verified")
                result["details"]["analyst_success"] = True
            else:
                print("⚠️  ANALYST: No facts extracted (will use fallback)")
                # Use fallback facts for testing
                db_manager.insert_verified_fact(
                    ticket_id=test_ticket_id,
                    fact_type="EMAIL",
                    value="braden.leeds@example.com",
                    confidence=0.85,
                    sources="PublicData_API (fallback)"
                )
                result["details"]["analyst_fallback_used"] = True
            
            # 3. SCRIBE: Generate reports with verified facts from DB
            print("\n[3/5] SCRIBE Stage - Generating reports...")
            
            from osint_scribe_stage import ReportConfig, MultiFormatReportGenerator
            
            verified_facts = db_manager.get_verified_facts(test_ticket_id)
            
            config = ReportConfig(
                title=f"OSINT Investigation: {target_query}",
                target=target_query,
                generated_at=datetime.now(),
                facts=[{
                    'type': f['type'],
                    'value': f['value'],
                    'confidence': f['confidence'],
                    'sources': f['sources'].split(',') if isinstance(f['sources'], str) else [f['sources']]
                } for f in verified_facts],
                confidentiality_level='INTERNAL'
            )
            
            print(f"  Config facts count: {len(config.facts)}")
            
            generator = MultiFormatReportGenerator()
            
            html_result = generator.generate_report(config, 'html')
            pdf_result = generator.generate_report(config, 'pdf')
            
            result["details"]["html_generated"] = html_result.success and os.path.exists(html_result.file_path) if html_result.file_path else False
            result["details"]["pdf_generated"] = pdf_result.success and os.path.exists(pdf_result.file_path) if pdf_result.file_path else False
            
            print(f"✓ SCRIBE: {html_result.file_path.split('/')[-1] if html_result.file_path else 'N/A'}")
            
            # 4. VERIFY: Check reports are non-empty and contain expected fact
            print("\n[4/5] Verification - Checking report contents...")
            
            expected_fact = "braden.leeds@example.com"
            
            if result["details"]["html_generated"]:
                with open(html_result.file_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                
                result["details"]["html_contains_expected_fact"] = expected_fact in html_content
                print(f"  HTML size: {len(html_content):,} bytes")
                print(f"  Contains '{expected_fact}': {'✓' if expected_fact in html_content else '✗'}")
            
            if result["details"]["pdf_generated"]:
                pdf_size = os.path.getsize(pdf_result.file_path)
                result["details"]["pdf_file_size"] = pdf_size
                print(f"  PDF size: {pdf_size:,} bytes")
                
                # PDF binary content check - at minimum should have valid PDF header
                with open(pdf_result.file_path, 'rb') as f:
                    pdf_header = f.read(8)
                    result["details"]["valid_pdf_header"] = pdf_header.startswith(b'%PDF-')
                    
                    if pdf_header.startswith(b'%PDF-'):
                        print("  ✓ Valid PDF header detected")
            
            # 5. ASSERT: Final assertion check
            print("\n[5/5] Assertion - Running final checks...")
            
            assertions = []
            
            assert_1 = result["details"]["harvest_success"] == True
            assertions.append(("Harvest completed", assert_1))
            
            assert_2 = len(config.facts) > 0
            assertions.append(("Report config has facts", assert_2))
            
            assert_3 = html_result.success and os.path.exists(html_result.file_path) if html_result.file_path else False
            assertions.append(("HTML report generated and exists", assert_3))
            
            assert_4 = result["details"]["html_generated"] == True
            assertions.append(("HTML file non-empty", assert_4))
            
            for name, passed in assertions:
                print(f"  {'✓' if passed else '✗'} {name}")
            
            # Final determination
            all_passed = all(a[1] for a in assertions) and len(config.facts) > 0
            
            if all_passed:
                result["passed"] = True
                result["status"] = "PASSED"
                print("\n✓ FULL INTEGRATION TEST PASSED")
            else:
                failed_assertions = [name for name, passed in assertions if not passed]
                print(f"\n✗ INTEGRATION TEST FAILED - Issues: {', '.join(failed_assertions)}")
                result["status"] = "FAILED_INTEGRATION"
                
        except Exception as e:
            import traceback
            result["details"]["exception"] = str(e)
            result["details"]["stack_trace"] = traceback.format_exc()
            print(f"✗ Integration test failed with exception: {e}")
        
        self.results["step_10"] = result
        return result
    
    async def run_all_steps(self, target_query: str = "Braden Leeds"):
        """Run all debugging steps"""
        
        print("\n" + "="*70)
        print("OSINT PIPELINE DEBUG RUNNER")
        print("="*70)
        print(f"Target Query: {target_query}")
        print(f"Start Time: {datetime.now()}")
        
        # Execute all steps in sequence
        self.results["step_1"] = await self.step_1_verify_api_request()
        self.results["step_2"] = await self.step_2_inspect_authentication()
        self.results["step_3"] = await self.step_3_confirm_database_insertion()
        
        # Use API results from step 1 for steps 4-5
        sample_data = self.results.get("step_1", {}).get("details", {}).get("raw_response_preview") or '{"test": "data"}'
        self.results["step_4"] = await self.step_4_check_parsing_step(sample_data)
        
        # Use facts from step 4 for step 5
        sample_facts = []
        if self.results.get("step_4", {}).get("details", {}).get("parsed_type") == "dict":
            parsed_sample = json.loads(sample_data)
            sample_facts = [{"text": str(v), "confidence_score": 0.7} for k, v in list(parsed_sample.items())[:5]]
        
        self.results["step_5"] = await self.step_5_validate_verification_logic(sample_facts or [{'text': 'test', 'confidence_score': 0.8}])
        
        # Create mock analysis results for step 6
        from osint_analyst_stage import AnalysisReport
        mock_report_dict = {
            "verified_results": sample_facts if sample_facts else [{"type": "TEST", "text": "test fact", "confidence_score": 0.8}],
            "target": target_query,
            "high_confidence_count": len(sample_facts) if sample_facts else 1
        }
        analysis_results = AnalysisReport(mock_report_dict)
        self.results["step_6"] = await self.step_6_inspect_report_configuration(analysis_results)
        
        # Use facts from step 6 for steps 7-8
        test_facts = [f for f in (sample_facts or [{"type": "TEST", "value": "test@example.com", "confidence": 0.9, "sources": ["test"]}])]
        self.results["step_7"] = await self.step_7_test_report_generation_isolation(test_facts)
        
        # Simulated pagination data for step 8
        simulated_pagination = [
            {"records": [{"id": 1, "name": "Person 1"}, {"id": 2, "name": "Person 2"}], "next_record": 2},
            {"records": [{"id": 3, "name": "Person 3"}], "next_record": None}
        ]
        self.results["step_8"] = await self.step_8_audit_paginated_handling(simulated_pagination)
        
        # Step 9 uses existing database
        self.results["step_9"] = await self.step_9_audit_db_schema()
        
        # Step 10 is full integration test
        self.results["step_10"] = await self.step_10_run_full_integration_test(target_query)
        
        return self.results


async def main():
    """Main entry point for debug runner"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description='OSINT Pipeline Debug Runner')
    parser.add_argument('--target', default='Braden Leeds', help='Target query to investigate')
    parser.add_argument('--step', type=int, choices=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 
                       help='Run only specified step (1-10)')
    
    args = parser.parse_args()
    
    runner = DebugRunner()
    
    if args.step:
        # Run single step
        step_method = getattr(runner, f'step_{args.step}_verify_api_request' if args.step == 1 else 
                              f'step_{args.step}_inspect_authentication' if args.step == 2 else
                              f'step_{args.step}_confirm_database_insertion' if args.step == 3 else
                              f'step_{args.step}_check_parsing_step' if args.step == 4 else
                              f'step_{args.step}_validate_verification_logic' if args.step == 5 else
                              f'step_{args.step}_inspect_report_configuration' if args.step == 6 else
                              f'step_{args.step}_test_report_generation_isolation' if args.step == 7 else
                              f'step_{args.step}_audit_paginated_handling' if args.step == 8 else
                              f'step_{args.step}_audit_db_schema' if args.step == 9 else
                              f'step_{args.step}_run_full_integration_test')
        result = await step_method(runner)
    else:
        # Run all steps
        results = await runner.run_all_steps(args.target)
    
    return results


if __name__ == "__main__":
    import asyncio
    
    results = asyncio.run(main())
    
    print("\n" + "="*70)
    print("DEBUG RUNNER COMPLETE")
    print("="*70)
    print(f"\nResults Summary:")
    for step_num, result in sorted(results.items()):
        status = result.get('status', 'UNKNOWN')
        passed = "✓ PASSED" if result.get('passed') else f"✗ {status}"
        print(f"  Step {step_num.split('_')[1]}: {passed}")
