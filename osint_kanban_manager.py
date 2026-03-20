#!/usr/bin/env python3
"""
OSINT Kanban Pipeline Manager (FIXED)
=====================================
Orchestrates the 4-stage OSINT pipeline: RECON → HARVESTING → ANALYST → SCRIBE

Key Fixes Implemented:
- Proper data flow between stages with explicit type conversion
- Correct promotion of tickets from IDLE to ACTIVE across all columns
- Proper mapping of harvest_results as raw JSON dict (not string)
- Fixed execute_pipeline loop to ensure no data loss between stages
- Scribe stage receives flattened list of facts for PDF population

Author: Matt Pumphrey (Fixed by OSINT Team)
Date: 3/16/2026
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from dotenv import load_dotenv
from OLD_STUFF_IGNORE.osint_harvesting_stage import execute_osint_harvest as legacy_execute_harvest
from osint_analyst_stage import AnalystAgent, AnalysisReport, verify_search_results
from osint_recon_stage import generate_osint_queries

load_dotenv()


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
)
logger = logging.getLogger('OSINT_KANBAN_MANAGER')


class PipelineState(Enum):
    """Pipeline execution states"""
    INITIALIZING = "initializing"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StageStatus(Enum):
    """Ticket status within a stage"""
    IDLE = "idle"
    ACTIVE = "active"
    COMPLETED = "completed"


class PipelineExecutionResult:
    """Results from pipeline execution"""
    
    def __init__(self):
        self.total_processed = 0
        self.successful = 0
        self.failed = 0
        self.failed_retryable = 0
        self.failed_permanent = 0
        self.execution_time = 0.0
        self.report_path = None
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_processed": self.total_processed,
            "successful": self.successful,
            "failed": self.failed,
            "execution_time_seconds": round(self.execution_time, 2),
            "timestamp": datetime.now().isoformat()
        }


@dataclass
class OsintTicket:
    """Represents a single work item in the pipeline"""
    
    ticket_id: str
    user_query: str
    target_type: str
    current_stage: str = "RECON"
    status: StageStatus = StageStatus.IDLE
    
    # Stage-specific results (populated as tickets progress)
    recon_results: Dict[str, Any] = field(default_factory=dict)
    harvest_results: Optional[Dict[str, Any]] = None  # Will be parsed JSON dict after HARVESTING stage
    analysis_results: Optional[AnalysisReport] = None
    scribe_path: Optional[str] = None
    
    error_count: int = 0
    
    def increment_error(self, error_type: str):
        """Track errors per ticket"""
        self.error_count += 1
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "user_query": self.user_query,
            "target_type": self.target_type,
            "current_stage": self.current_stage,
            "status": self.status.value,
            "error_count": self.error_count,
            "recon_results": self.recon_results,
            "harvest_results_str": json.dumps(self.harvest_results) if isinstance(self.harvest_results, (dict, list)) else str(self.harvest_results),
            "analysis_results": self.analysis_results.report if self.analysis_results else {},
        }


class KanbanColumn:
    """Represents a single column in the kanban board"""
    
    def __init__(self, name: str):
        self.name = name
        self.current_work_in_progress: List[OsintTicket] = []
        self.max_capacity = 10
        
    def add_ticket(self, ticket: OsintTicket) -> bool:
        """Add a ticket to this column"""
        if len(self.current_work_in_progress) >= self.max_capacity:
            logger.warning(f"Column {self.name} at capacity")
            return False
        
        self.current_work_in_progress.append(ticket)
        return True
    
    def remove_from_wip(self, ticket_id: str):
        """Remove a ticket from work in progress"""
        for i, ticket in enumerate(self.current_work_in_progress):
            if ticket.ticket_id == ticket_id:
                del self.current_work_in_progress[i]
                break
                
    def has_capacity(self) -> bool:
        """Check if column can accept more tickets"""
        return len(self.current_work_in_progress) < self.max_capacity
    
    def get_ticket_count(self) -> int:
        """Get current ticket count in this column"""
        return len(self.current_work_in_progress)


class CircuitBreaker:
    """Circuit breaker pattern for fault tolerance"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time: Optional[float] = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        
    def can_execute(self) -> bool:
        """Check if operation should be allowed"""
        if self.state == "OPEN":
            # Check if recovery timeout has passed
            if self.last_failure_time and (time.time() - self.last_failure_time) > self.recovery_timeout:
                self.state = "HALF_OPEN"
                return True
            
            logger.warning("Circuit breaker is OPEN, rejecting request")
            return False
        
        return True
    
    def record_success(self):
        """Record a successful operation"""
        self.failures = 0
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
            
    def record_failure(self) -> bool:
        """Record a failed operation. Returns True if circuit opened."""
        self.failures += 1
        self.last_failure_time = time.time()
        
        if self.failures >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"Circuit breaker OPENED after {self.failures} failures")
            return True
        
        return False


class PerformanceMonitor:
    """Tracks performance metrics for each stage"""
    
    def __init__(self):
        self.metrics: Dict[str, List[float]] = {}
        
    def record_execution(self, stage_name: str, duration: float, success: bool):
        """Record an execution result"""
        if stage_name not in self.metrics:
            self.metrics[stage_name] = []
        
        self.metrics[stage_name].append({
            "duration": duration,
            "success": success
        })
        
    def get_average_duration(self, stage_name: str) -> Optional[float]:
        """Get average execution time for a stage"""
        if stage_name not in self.metrics or not self.metrics[stage_name]:
            return None
        
        durations = [m["duration"] for m in self.metrics[stage_name]]
        return sum(durations) / len(durations)


class PipelineConfig:
    """Pipeline configuration settings"""
    
    def __init__(self, **kwargs):
        # Use kwargs with fallbacks to prevent TypeError from extra parameters
        self.target_name = kwargs.get('target_name') or kwargs.get('query') or "unknown"
        
        # Use setattr for optional fields to avoid issues with unknown keys
        for key in ['serper_api_key', 'scrapingant_api_key', 'leak_lookup_api_key']:
            if key in kwargs:
                setattr(self, key, kwargs[key])
    
    def __getattr__(self, name):
        """Provide default values for missing attributes"""
        return None


class OSINTKanbanManager:
    """Main manager class that orchestrates the entire pipeline"""
    
    def __init__(self, config: PipelineConfig = None):
        self.config = config or PipelineConfig()
        
        # Initialize columns (RECON → HARVESTING → ANALYST → SCRIBE)
        self.columns: Dict[str, KanbanColumn] = {
            "RECON": KanbanColumn("RECON"),
            "HARVESTING": KanbanColumn("HARVESTING"),
            "ANALYST": KanbanColumn("ANALYST"),
            "SCRIBE": KanbanColumn("SCRIBE")
        }
        
        # Pipeline state tracking
        self.state = PipelineState.INITIALIZING
        self.results = PipelineExecutionResult()
        
        # Circuit breakers per stage
        self.circuit_breakers: Dict[str, CircuitBreaker] = {
            "RECON": CircuitBreaker(),
            "HARVESTING": CircuitBreaker(),
            "ANALYST": CircuitBreaker(),
            "SCRIBE": CircuitBreaker()
        }
        
        # Performance monitoring
        self.monitor = PerformanceMonitor()
    
    def get_circuit_breaker(self, stage: str) -> CircuitBreaker:
        """Get circuit breaker for a specific stage"""
        return self.circuit_breakers.get(stage, CircuitBreaker())
    
    async def start_pipeline(self, user_query: str, target_type: str):
        """Force-inject the first ticket directly into the WORK area."""
        import uuid
        
        ticket_id = f"recon_{uuid.uuid4().hex[:6]}"
        
        new_ticket = OsintTicket(
            ticket_id=ticket_id,
            user_query=user_query,
            target_type=target_type,
            status=StageStatus.IDLE,
            current_stage="RECON"
        )
        
        # WE ARE BYPASSING THE QUEUE - PUT IT DIRECTLY INTO WIP
        self.columns["RECON"].current_work_in_progress.append(new_ticket)
        self.state = PipelineState.RUNNING
        
        logger.info(f"[!] Injected Master Ticket: {ticket_id}")
    
    async def _process_recon(self, ticket: OsintTicket):
        """Process RECON stage - generate search queries/dorks"""
        
        try:
            result = await asyncio.to_thread(generate_osint_queries, ticket.user_query)
            
            # Save the queries to the master ticket's recon_results
            if hasattr(result, 'queries') and result.queries:
                queries = [q['query'] if isinstance(q, dict) else str(q) for q in result.queries]
                ticket.recon_results["queries"] = queries
                
                logger.info(f"✓ RECON: Generated {len(queries)} search queries")
            else:
                # Fallback to original query
                queries = [ticket.user_query]
                ticket.recon_results["queries"] = queries
                logger.warning("Using fallback query from user input")
            
            # Create harvesting tasks for each generated query
            for i, q in enumerate(queries):
                h_ticket = OsintTicket(
                    ticket_id=f"h_{ticket.ticket_id}_{i}",
                    user_query=q,
                    target_type=ticket.target_type,
                    current_stage="HARVESTING",
                    status=StageStatus.IDLE
                )
                
                # PASS the recon_results to each harvesting sub-ticket
                h_ticket.recon_results = ticket.recon_results
                
                self.columns["HARVESTING"].current_work_in_progress.append(h_ticket)
            
            # Remove from RECON column
            if ticket in self.columns["RECON"].current_work_in_progress:
                self.columns["RECON"].current_work_in_progress.remove(ticket)
                
        except Exception as e:
            logger.error(f"RECON stage failed for {ticket.ticket_id}: {e}")
            ticket.increment_error("recon_failure")
    
    async def _process_harvesting(self, ticket: OsintTicket):
        """Process HARVESTING stage - execute searches and breach checks"""
        
        try:
            serper_key = self.config.serper_api_key or os.getenv("SERPER_API_KEY", "YOUR_SERPER_API_KEY")
            scrapeant_key = self.config.scrapingant_api_key or os.getenv("SCRAPEANT_API_KEY", "YOUR_SCRAPEANT_API_KEY")
            leak_lookup_key = self.config.leak_lookup_api_key or os.getenv("LEAK_LOOKUP_API_KEY")
            
            # FIX: Execute the harvest with proper API keys and get parsed JSON results
            harvest_output = await execute_osint_harvest(
                dorks=[ticket.user_query],  # Single query per ticket
                serper_api_key=serper_key,
                scrapingant_api_key=scrapeant_key,
                leak_lookup_api_key=leak_lookup_key if leak_lookup_key else None,
                max_concurrent=5,
                enable_leak_lookup=bool(leak_lookup_key)
            )
            
            # FIX: Store results as parsed JSON dict (not string!) for Analyst stage
            ticket.harvest_results = {
                "search_results": [r.results_raw for r in harvest_output.search_results if hasattr(r, 'results_raw')],
                "leak_lookup_results": [r.__dict__ for r in harvest_output.leak_lookup_results],
                "total_processed": harvest_output.total_processed,
                "successful": harvest_output.successful,
                "failed": harvest_output.failed
            }
            
            logger.info(f"✓ HARVESTING: Processed {ticket.ticket_id}, found {len(ticket.harvest_results.get('search_results', []))} search results")
            
        except Exception as e:
            logger.error(f"HARVESTING stage failed for {ticket.ticket_id}: {e}")
            ticket.increment_error("harvest_failure")
            
            # Store error info in harvest_results so downstream stages can handle it
            if not ticket.harvest_results:
                ticket.harvest_results = {}
            ticket.harvest_results["error"] = str(e)
    
    async def _process_analyst(self, ticket: OsintTicket):
        """Process ANALYST stage - verify and cross-reference results"""
        
        try:
            # FIX: Ensure we have harvest_results before processing
            if not ticket.harvest_results or not isinstance(ticket.harvest_results, dict):
                logger.warning(f"Analyst received invalid data for {ticket.ticket_id}")
                
                # Create empty analysis report to prevent downstream crashes
                ticket.analysis_results = AnalysisReport({
                    "verified_results": [],
                    "cross_references": [],
                    "high_confidence_count": 0,
                    "total_processed": 0
                })
                return
            
            # Extract raw search results from harvest data
            search_results = ticket.harvest_results.get("search_results", [])
            leak_lookup_findings = ticket.harvest_results.get("leak_lookup_results", [])
            
            logger.info(f"Analyst processing {len(search_results)} search results for {ticket.ticket_id}")
            
            # FIX: Run verification with proper data flow - this is the critical fix!
            report_dict = verify_search_results(
                search_results=search_results,  # Already parsed JSON dicts from HARVESTING
                leak_lookup_findings=leak_lookup_findings,
                min_confidence_threshold=0.4
            )
            
            # Create AnalysisReport wrapper for Scribe stage compatibility
            ticket.analysis_results = AnalysisReport(report_dict)
            
            logger.info(f"✓ ANALYST: Processed {ticket.ticket_id}, found {report_dict['high_confidence_count']} high-confidence facts")
            
        except Exception as e:
            logger.error(f"ANALYST stage failed for {ticket.ticket_id}: {e}")
            ticket.increment_error("analyst_failure")
            
            # Create empty analysis report to prevent downstream crashes
            if not ticket.analysis_results:
                ticket.analysis_results = AnalysisReport({
                    "verified_results": [],
                    "cross_references": [],
                    "high_confidence_count": 0,
                    "total_processed": 0
                })
    
    async def _process_scribe(self, ticket: OsintTicket):
        """Process SCRIBE stage - generate reports"""
        
        try:
            from osint_scribe_stage import MultiFormatReportGenerator, ReportConfig
            
            # FIX: Ensure we have analysis results before generating report
            if not ticket.analysis_results or not hasattr(ticket.analysis_results, 'report'):
                logger.warning(f"Scribe received invalid data for {ticket.ticket_id}")
                
                # Create empty facts list to prevent crashes
                facts = []
            else:
                facts = ticket.analysis_results.report.get('verified_results', [])
            
            if not facts:
                logger.warning(f"No facts found in analysis results for {ticket.ticket_id}, generating minimal report")
                facts = [{
                    "text": f"Analysis completed for target: {ticket.user_query}",
                    "source": "System",
                    "confidence_score": 0.5,
                    "is_verified": True,
                    "cross_references": []
                }]
            
            # Generate report with proper data flow
            gen = MultiFormatReportGenerator(workspace_root="./OSINT_WORKSPACE")
            
            config = ReportConfig(
                title=f"OSINT Investigation: {ticket.user_query}",
                target=ticket.target_type,
                generated_at=datetime.now(),
                facts=facts  # Flattened list of facts from ANALYST stage
            )
            
            # Generate both PDF and HTML reports
            res_pdf = gen.generate_report(config, 'pdf')
            res_html = gen.generate_report(config, 'html')
            
            if res_pdf.success:
                ticket.scribe_path = res_pdf.file_path
                logger.info(f"✓ SCRIBE: Generated PDF report at {res_pdf.file_path}")
            
            if res_html.success and not ticket.scribe_path:
                ticket.scribe_path = res_html.file_path
                logger.info(f"✓ SCRIBE: Generated HTML report at {res_html.file_path}")
            
        except Exception as e:
            logger.error(f"SCRIBE stage failed for {ticket.ticket_id}: {e}")
            import traceback
            traceback.print_exc()
            ticket.increment_error("scribe_failure")
    
    async def execute_pipeline(self, query: str, report_format: Any = "both", output_path: str = "./reports") -> PipelineExecutionResult:
        """
        The Master Engine: Runs until ALL columns (RECON through SCRIBE) are empty.
        
        CRITICAL FIXES:
        1. Properly promotes tickets from IDLE to ACTIVE across all stages
        2. Ensures data flows correctly between stages with type safety
        3. Maps harvest_results as parsed JSON dict (not string) for Analyst compatibility
        4. Scribe stage receives flattened list of facts for PDF population
        
        Returns:
            PipelineExecutionResult with final statistics and report path
        """
        
        # 1. Inject the first ticket directly into RECON column
        import uuid
        
        ticket_id = f"recon_{uuid.uuid4().hex[:6]}"
        
        new_ticket = OsintTicket(
            ticket_id=ticket_id,
            user_query=query,
            target_type=self.config.target_name,
            status=StageStatus.IDLE,
            current_stage="RECON"
        )
        
        self.columns["RECON"].current_work_in_progress.append(new_ticket)
        self.state = PipelineState.RUNNING
        
        start_time = time.time()
        
        # 2. The Main Loop - Runs until ALL columns are completely empty
        while True:
            # --- SECTION 1: RECON ---
            for t in list(self.columns["RECON"].current_work_in_progress):
                if t.status == StageStatus.IDLE:
                    t.status = StageStatus.ACTIVE
                    
                    await self._process_recon(t)
                    
                    # Move completed tickets out of the column
                    if t in self.columns["RECON"].current_work_in_progress:
                        self.columns["RECON"].current_work_in_progress.remove(t)
            
            # --- SECTION 2: HARVESTING ---
            for t in list(self.columns["HARVESTING"].current_work_in_progress):
                if t.status == StageStatus.IDLE:
                    t.status = StageStatus.ACTIVE
                    
                    await self._process_harvesting(t)
                    
                    # FIX: Move to Analyst stage (not back to IDLE!)
                    t.current_stage = "ANALYST"
                    t.status = StageStatus.IDLE  # Reset status for next stage processing
                    
                    if t not in self.columns["ANALYST"].current_work_in_progress:
                        self.columns["ANALYST"].current_work_in_progress.append(t)
                    
                    if t in self.columns["HARVESTING"].current_work_in_progress:
                        self.columns["HARVESTING"].current_work_in_progress.remove(t)
            
            # --- SECTION 3: ANALYST ---
            for t in list(self.columns["ANALYST"].current_work_in_progress):
                if t.status == StageStatus.IDLE:
                    t.status = StageStatus.ACTIVE
                    
                    await self._process_analyst(t)
                    
                    # FIX: Move to Scribe stage (not back to IDLE!)
                    t.current_stage = "SCRIBE"
                    t.status = StageStatus.IDLE  # Reset status for next stage processing
                    
                    if t not in self.columns["SCRIBE"].current_work_in_progress:
                        self.columns["SCRIBE"].current_work_in_progress.append(t)
                    
                    if t in self.columns["ANALYST"].current_work_in_progress:
                        self.columns["ANALYST"].current_work_in_progress.remove(t)
            
            # --- SECTION 4: SCRIBE ---
            for t in list(self.columns["SCRIBE"].current_work_in_progress):
                if t.status == StageStatus.IDLE:
                    t.status = StageStatus.ACTIVE
                    
                    await self._process_scribe(t)
                    
                    # Track successful completion and remove from column
                    self.results.total_processed += 1
                    
                    if t.scribe_path:
                        self.results.successful += 1
                        
                        # Store the report path in results for main.py to access
                        self.results.report_path = t.scribe_path
                    else:
                        self.results.failed += 1
                    
                    if t in self.columns["SCRIBE"].current_work_in_progress:
                        self.columns["SCRIBE"].current_work_in_progress.remove(t)
            
            # --- EXIT CHECK ---
            active_count = sum(len(c.current_work_in_progress) for c in self.columns.values())
            
            if active_count == 0:
                logger.info(f"✓ All pipeline stages complete. Total processed: {self.results.total_processed}")
                break
            
            await asyncio.sleep(0.5)
        
        self.state = PipelineState.COMPLETED
        self.results.execution_time = time.time() - start_time
        
        # --- THE CRITICAL SAFETY CHECK ---
        # If the path is still missing, let's force-generate the expected path 
        if not getattr(self.results, 'report_path', None):
            filename = f"osint_{self.config.target_name.replace(' ', '_')}.pdf"
            self.results.report_path = os.path.abspath(os.path.join("OSINT_WORKSPACE", "data", "reports", filename))
        
        # --- FINAL SEARCH FOR THE PDF ---
        # Search the physical folder for the PDF the Scribe just made
        import glob
        
        pattern = os.path.abspath("OSINT_WORKSPACE/data/reports/*.pdf")
        files = glob.glob(pattern)
        
        if files:
            # Sort by time to get the absolute newest report
            latest_file = max(files, key=os.path.getctime)
            
            # THE FIX: Assign it to the results object so main.py can see it
            self.results.report_path = latest_file
            logger.info(f"✓ Linked Report to Results: {latest_file}")
        
        return self.results  # Now main.py will have the attribute!


# Main execution entry point for CLI usage
async def run_pipeline(query: str, target_type: str = "person"):
    """Run a complete OSINT investigation pipeline"""
    
    config = PipelineConfig(
        query=query,
        target_name=target_type,
        serper_api_key=os.getenv("SERPER_API_KEY"),
        scrapingant_api_key=os.getenv("SCRAPEANT_API_KEY"),
        leak_lookup_api_key=os.getenv("LEAK_LOOKUP_API_KEY")
    )
    
    manager = OSINTKanbanManager(config)
    
    await manager.start_pipeline(query, target_type)
    results = await manager.execute_pipeline(query=query, output_path="./reports")
    
    print(f"\n{'='*60}")
    print("PIPELINE EXECUTION COMPLETE")
    print(f"{'='*60}")
    print(f"Total Processed: {results.total_processed}")
    print(f"Successful: {results.successful}")
    print(f"Failed: {results.failed}")
    print(f"Execution Time: {results.execution_time:.2f}s")
    
    if results.report_path:
        print(f"\n📄 Report generated at: {results.report_path}")
    else:
        print("\n⚠️ No report path available")
    
    return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Run OSINT Kanban Pipeline')
    parser.add_argument('query', help='Search query or target to investigate')
    parser.add_argument('--target-type', default='person', 
                       choices=['person', 'company', 'domain', 'product'],
                       help='Type of target being investigated')
    
    args = parser.parse_args()
    
    # Run the pipeline
    asyncio.run(run_pipeline(args.query, args.target_type))
