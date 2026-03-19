#!/usr/bin/env python3
"""
OSINT Kanban Pipeline Manager
=============================
Orchestrates the 4-stage OSINT pipeline: RECON → HARVESTING → ANALYST → SCRIBE

Features:
- Kanban-style ticket management across stages
- Circuit breaker pattern for fault tolerance
- Performance monitoring and metrics
- Async execution with proper stage gating
Author: Matt Pumphrey
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
        self.execution_time = 0.0
        
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
    harvest_results: Any = None  # Will be JSON string or dict after HARVESTING stage
    analysis_results: Dict[str, Any] = field(default_factory=dict)
    
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
            "analysis_results": self.analysis_results,
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
            if self.last_failure_time and \
               (time.time() - self.last_failure_time) > self.recovery_timeout:
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
        
        # Use setattr for all incoming arguments to handle any extra parameters gracefully
        for key, value in kwargs.items():
            if key == 'target_name' or key == 'query':
                continue  # Already handled above
            
            # Map common parameter names to internal attribute names
            attr_name = {
                'target_type': 'target_type',
                'wip_limits': '_wip_limits',
                'api_keys': 'api_keys',
                'max_retries_per_ticket': 'max_retries_per_ticket',
                'enable_circuit_breaker': 'enable_circuit_breaker',
                'recovery_time_after_failure': 'recovery_time_after_failure'
            }.get(key, key)  # Use key as attr_name if not in mapping
            
            setattr(self, attr_name, value)
        
        # Set defaults for missing attributes
        self.target_type = getattr(self, 'target_type', "person")
        self.api_keys: Dict[str, str] = kwargs.get('api_keys') or {
            "SERPER_API_KEY": os.getenv("SERPER_API_KEY", ""),
            "SCRAPINGANT_API_KEY": os.getenv("SCRAPINGANT_API_KEY", "")
        }


class OSINTKanbanManager:
    """Main orchestrator for the 4-stage OSINT pipeline"""
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        
        # Create kanban columns
        self.columns: Dict[str, KanbanColumn] = {
            "RECON": KanbanColumn("RECON"),
            "HARVESTING": KanbanColumn("HARVESTING"),
            "ANALYST": KanbanColumn("ANALYST"),
            "SCRIBE": KanbanColumn("SCRIBE")
        }
        
        # Circuit breakers for each stage
        self.circuit_breakers: Dict[str, CircuitBreaker] = {
            name: CircuitBreaker() for name in ["RECON", "HARVESTING", "ANALYST", "SCRIBE"]
        }
        
        # Performance monitor
        self.monitor = PerformanceMonitor()
        
        # Execution results
        self.results = PipelineExecutionResult()
        
        # Pipeline state
        self.state = PipelineState.INITIALIZING
    
    def _can_pull_from_stage(self, stage_name: str) -> bool:
        """Check if we can start processing a ticket from this stage"""
        column = self.columns.get(stage_name)
        if not column or not column.has_capacity():
            return False
        
        # Check for completed tickets in upstream stages that need to be promoted
        upstream_stages = {
            "SCRIBE": ["ANALYST"],
            "ANALYST": ["HARVESTING"],
            "HARVESTING": ["RECON"]
        }
        
        upstream_names = upstream_stages.get(stage_name, [])
        for upstream in upstream_names:
            upstream_col = self.columns.get(upstream)
            if upstream_col and any(
                t.current_stage == upstream and t.status == StageStatus.COMPLETED
                for t in upstream_col.current_work_in_progress
            ):
                return True
        
        return False
    
    async def _process_recon_ticket(self):
        """Process RECON stage ticket"""
        
        # Find a completed ticket ready to move from RECON
        recon_col = self.columns["RECON"]
        for ticket in recon_col.current_work_in_progress:
            if (ticket.status == StageStatus.COMPLETED and 
                ticket.current_stage == "RECON"):
                
                # Move ticket to HARVESTING
                recon_col.remove_from_wip(ticket.ticket_id)
                ticket.current_stage = "HARVESTING"
                self.columns["HARVESTING"].add_ticket(ticket)
                
                logger.info(f"   Moving {ticket.ticket_id} from RECON → HARVESTING")
                break
    
    async def _process_harvesting_ticket(self):
        """Process HARVESTING stage ticket"""
        
        # Find a completed ticket ready to move from HARVESTING
        harvest_col = self.columns["HARVESTING"]
        for ticket in harvest_col.current_work_in_progress:
            if (ticket.status == StageStatus.COMPLETED and 
                ticket.current_stage == "HARVESTING"):
                
                # Move ticket to ANALYST
                harvest_col.remove_from_wip(ticket.ticket_id)
                ticket.current_stage = "ANALYST"
                self.columns["ANALYST"].add_ticket(ticket)
                
                logger.info(f"   Moving {ticket.ticket_id} from HARVESTING → ANALYST")
                break
    
    async def _process_analyst_ticket(self):
        """Process ANALYST stage ticket"""
        
        # Find a completed ticket ready to move from ANALYST
        analyst_col = self.columns["ANALYST"]
        for ticket in analyst_col.current_work_in_progress:
            if (ticket.status == StageStatus.COMPLETED and 
                ticket.current_stage == "ANALYST"):
                
                # Move ticket to SCRIBE
                analyst_col.remove_from_wip(ticket.ticket_id)
                ticket.current_stage = "SCRIBE"
                self.columns["SCRIBE"].add_ticket(ticket)
                
                logger.info(f"   Moving {ticket.ticket_id} from ANALYST → SCRIBE")
                break
    
    async def _process_recon(self, ticket: OsintTicket) -> bool:
        """Execute RECON and spawn individual HARVESTING tickets"""
        start_time = time.time()
        try:
            if not self.circuit_breakers["RECON"].can_execute():
                return False
            
            from osint_recon_stage import generate_osint_queries
            result = generate_osint_queries(ticket.user_query)
            
            # Use generated queries or fallback to the original target
            queries = result.queries if result.queries else [ticket.user_query]

            # --- THE CRITICAL FIX: Create tickets for the next stage ---
            for i, q in enumerate(queries):
                query_str = q['query'] if isinstance(q, dict) else str(q)
                
                # We create a brand new ticket for every search query
                harvest_ticket = OsintTicket(
                    ticket_id=f"harvest_{ticket.ticket_id}_{i}",
                    user_query=query_str,
                    target_type=ticket.target_type,
                    current_stage="HARVESTING",
                    status=StageStatus.IDLE
                )
                # This puts the actual work into the Harvesting column
                self.columns["HARVESTING"].add_ticket(harvest_ticket)

            # Mark the master Recon ticket as done
            ticket.status = StageStatus.COMPLETED
            self.circuit_breakers["RECON"].record_success()
            self.monitor.record_execution("RECON", time.time() - start_time, True)
            
            logger.info(f"   ✓ RECON: Generated {len(queries)} search tasks.")
            return True
            
        except Exception as e:
            logger.error(f"✗ RECON failed: {e}")
            self.circuit_breakers["RECON"].record_failure()
            return False

    
    async def _process_harvesting(self, ticket: OsintTicket) -> bool:
        """Execute HARVESTING stage for a ticket"""
        
        start_time = time.time()
        
        try:
            # Check circuit breaker
            if not self.circuit_breakers["HARVESTING"].can_execute():
                logger.warning("Circuit breaker open for HARVESTING, skipping")
                return False
            
            from osint_harvesting_stage import execute_osint_harvest
            
            result = await execute_osint_harvest(
                dorks=ticket.recon_results.get("queries", []),
                serper_api_key=self.config.api_keys["SERPER_API_KEY"],
                scrapingant_api_key=self.config.api_keys["SCRAPINGANT_API_KEY"],
                max_concurrent=5
            )
            
            ticket.harvest_results = [
                {
                    "dork": dork,
                    "status": r.get("status", 0),
                    "results_count": len(r.get("results", [])),
                    "has_errors": r.get("error") is not None,
                    "tool_name": r.get("tool_name", "unknown"),
                    "raw_data": r.get("results", [])[:10]  # Keep first 10 results for processing
                }
                for dork, r in zip(
                    ticket.recon_results.get("queries", []), 
                    result.search_results or []
                )
            ]
            
            self.circuit_breakers["HARVESTING"].record_success()
            ticket.status = StageStatus.COMPLETED
            
            duration = time.time() - start_time
            self.monitor.record_execution("HARVESTING", duration, True)
            
            logger.info(f"   ✓ HARVESTING completed for {ticket.ticket_id} in {duration:.1f}s")
            return True
            
        except Exception as e:
            logger.error(f"✗ HARVESTING failed for {ticket.ticket_id}: {e}")
            ticket.increment_error("HARVESTING_FAILURE")
            
            if self.circuit_breakers["HARVESTING"].record_failure():
                logger.warning("Circuit breaker opened for HARVESTING")
            
            duration = time.time() - start_time
            self.monitor.record_execution("HARVESTING", duration, False)
            
            return False
    
    async def _process_analyst(self, ticket: OsintTicket) -> bool:
        """Execute ANALYST stage for a ticket
        
        CRITICAL FIX: Properly parse harvest_results which can be:
        - A JSON string (serialized dictionary/list)
        - An actual list of dictionaries
        - Already parsed as a dictionary structure
        
        The Analyst stage expects to receive the raw search results in a format
        it can process, specifically looking for 'organic' key in Serper.dev responses.
        """
        try:
            import json
            from osint_analyst_stage import OSINTAnalystStage
            analyst = OSINTAnalystStage(privacy_mode='public')
            
            # --- THE FIX: Parse the harvest results correctly for Analyst consumption ---
            raw_results = ticket.harvest_results
            
            # Handle JSON string input - deserialize it first
            if isinstance(raw_results, str):
                try:
                    parsed = json.loads(raw_results)
                    # If the parsed result is a list of search outcome objects, 
                    # we need to extract just the results portion for the Analyst
                    if isinstance(parsed, list):
                        # Each item in the list has 'raw_data' which contains actual Serper.dev results
                        raw_results = []
                        for item in parsed:
                            if isinstance(item, dict) and 'raw_data' in item:
                                raw_results.append(item['raw_data'])
                    else:
                        raw_results = parsed
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse harvest_results JSON string: {e}")
                    # Keep original if parsing fails
            elif isinstance(raw_results, list):
                # If it's already a list (from HARVESTING stage), extract raw_data from each item
                extracted_raw = []
                for item in raw_results:
                    if isinstance(item, dict) and 'raw_data' in item:
                        extracted_raw.append(item['raw_data'])
                    elif isinstance(item, dict):
                        # If it's already in the right format (Serper.dev JSON with 'organic')
                        extracted_raw.append(item)
                raw_results = extracted_raw
            
            # The Analyst stage needs to receive data structured as:
            # { "serper": [list of Serper.dev result objects with 'organic' key], "_target": target_name }
            harvest_data = {
                "serper": raw_results,  # This is now a list of result dicts (each potentially having 'organic')
                "_target": self.config.target_name
            }
            
            logger.info(f"   Processing {len(raw_results)} search results in ANALYST stage")
            
            report = analyst.process_harvest_results(harvest_data)
            
            # Store results - ensure Fact objects are converted to .__dict__ for Scribe compatibility
            ticket.analysis_results = {
                "all_facts": [f.__dict__ for f in report.facts],  # Convert Facts to dicts for PDF table
                "target": report.target_name,
                "confidence_summary": report.confidence_summary
            }
            ticket.status = StageStatus.COMPLETED
            return True
        except Exception as e:
            logger.error(f"✗ ANALYST failed: {e}", exc_info=True)
            return False
    
    async def _process_scribe(self, ticket: OsintTicket) -> bool:
        """Execute SCRIBE stage for a ticket"""
        try:
            from osint_scribe_stage import generate_osint_report
            
            # Generate output file path
            output_file = f"reports/osint_{self.config.target_name.replace(' ', '_')}"
            
            await generate_osint_report(
                target_name=self.config.target_name,
                recon_results=ticket.recon_results,
                harvest_results=ticket.harvest_results,
                analysis_results=ticket.analysis_results,  # Now contains properly converted Fact dicts
                output_path=output_file,
                output_format="pdf"
            )
            
            ticket.status = StageStatus.COMPLETED
            return True
        except Exception as e:
            logger.error(f"✗ SCRIBE failed: {e}", exc_info=True)
            return False
    
    def has_critical_failures(self) -> bool:
        """Check if pipeline has critical failures"""
        return any(
            cb.state == "OPEN" 
            for cb in self.circuit_breakers.values()
        )
    
    async def cleanup(self):
        """Cleanup resources and close connections"""
        
        logger.info("Cleaning up pipeline resources")
        
        # Close any open database connections, API sessions, etc.
        
        self.state = PipelineState.INITIALIZING

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
        logger.info(f"   [!] Injected Master Ticket: {ticket_id}")

    # === START OF EXECUTION ENGINE ===
    async def execute_pipeline(self, query: str, report_format: Any, output_path: str) -> PipelineExecutionResult:
        """The Master Engine: Runs until ALL columns (RECON through SCRIBE) are empty.
        
        CRITICAL FIX: The pipeline now properly waits for all tickets to complete
        processing through all stages before marking as completed. This ensures
        no data is lost between stages and the PDF report is fully populated.
        """
        import uuid
        
        # 1. Inject the first ticket directly
        ticket_id = f"recon_{uuid.uuid4().hex[:6]}"
        new_ticket = OsintTicket(
            ticket_id=ticket_id, user_query=query, target_type=self.config.target_type,
            status=StageStatus.IDLE, current_stage="RECON"
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
                    # Run the dork generator
                    result = generate_osint_queries(t.user_query)
                    
                    # Create the Harvesting tasks
                    queries = result.queries if result.queries else [t.user_query]
                    for i, q in enumerate(queries):
                        query_str = q['query'] if isinstance(q, dict) else str(q)
                        h_ticket = OsintTicket(
                            ticket_id=f"h_{t.ticket_id}_{i}", user_query=query_str,
                            target_type=t.target_type, current_stage="HARVESTING", status=StageStatus.IDLE
                        )
                        self.columns["HARVESTING"].current_work_in_progress.append(h_ticket)

                    self.columns["RECON"].current_work_in_progress.remove(t)
                    logger.info(f"   ✓ RECON: Created {len(queries)} search tasks.")

            # --- SECTION 2: HARVESTING ---
            for t in list(self.columns["HARVESTING"].current_work_in_progress):
                if t.status == StageStatus.IDLE:
                    t.status = StageStatus.ACTIVE
                    await self._process_harvesting(t)
                    # Move to Analyst
                    t.status = StageStatus.IDLE
                    self.columns["ANALYST"].current_work_in_progress.append(t)
                    self.columns["HARVESTING"].current_work_in_progress.remove(t)

            # --- SECTION 3: ANALYST ---
            for t in list(self.columns["ANALYST"].current_work_in_progress):
                if t.status == StageStatus.IDLE:
                    t.status = StageStatus.ACTIVE
                    await self._process_analyst(t)
                    # Move to Scribe - Fact objects already converted to __dict__ in _process_analyst
                    t.status = StageStatus.IDLE
                    self.columns["SCRIBE"].current_work_in_progress.append(t)
                    self.columns["ANALYST"].current_work_in_progress.remove(t)

            # --- SECTION 4: SCRIBE ---
            for t in list(self.columns["SCRIBE"].current_work_in_progress):
                if t.status == StageStatus.IDLE:
                    t.status = StageStatus.ACTIVE
                    await self._process_scribe(t)
                    self.columns["SCRIBE"].current_work_in_progress.remove(t)
                    # Track successful completion
                    self.results.total_processed += 1 
                    self.results.successful += 1

            # --- EXIT CHECK: Wait until ALL columns are EMPTY (not just one stage) ---
            active_count = sum(len(c.current_work_in_progress) for c in self.columns.values())
            
            if active_count == 0:
                logger.info(f"   ✓ All pipeline stages complete. Total processed: {self.results.total_processed}")
                break
            
            await asyncio.sleep(0.5)

        self.state = PipelineState.COMPLETED
        
        # Record total execution time
        self.results.execution_time = time.time() - start_time
        
        return self.results
    # === END OF EXECUTION ENGINE ===
