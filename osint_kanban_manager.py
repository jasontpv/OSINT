#!/usr/bin/env python3
"""
OSINT Kanban Pipeline Manager - Orchestration Layer
====================================================
Manages the flow of work through RECON -> HARVESTING -> ANALYST -> SCRIBE stages
with WIP limits, error handling, and pull-based workflow control.

Features:
- Pull-based Kanban flow (downstream pulls when capacity available)
- WIP limits per stage to prevent overload
- Error recovery with circuit breakers
- Real-time monitoring and bottleneck detection
Author: Matt Pumphrey
Date: 3/16/2026
"""

import asyncio
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StageStatus(Enum):
    """Status of each pipeline stage"""
    IDLE = "idle"
    ACTIVE = "active"
    BLOCKED = "blocked"
    FAILED = "failed"
    COMPLETED = "completed"


class PipelineState(Enum):
    """Overall pipeline state"""
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass
class PipelineConfig:
    """Configuration for the OSINT pipeline"""
    target_name: str
    target_type: str  # person, group, company
    wip_limits: Dict[str, int]
    api_keys: Dict[str, str]
    max_retries_per_ticket: int = 3
    enable_circuit_breaker: bool = True
    recovery_time_after_failure: int = 60
    verbose: bool = False


@dataclass
class OsintTicket:
    """Kanban ticket representing work item"""
    ticket_id: str
    user_query: str
    target_type: str
    status: StageStatus = StageStatus.IDLE
    current_stage: Optional[str] = None
    
    # Results and data accumulation
    recon_results: Dict[str, Any] = field(default_factory=dict)
    harvest_results: List[Dict] = field(default_factory=list)
    analysis_results: Dict[str, Any] = field(default_factory=dict)
    
    # Error tracking
    error_count: int = 0
    last_error_time: Optional[float] = None
    errors_by_type: Dict[str, int] = field(default_factory=dict)
    
    # Timing metrics
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    def increment_error(self, error_type: str):
        """Track error for this ticket"""
        self.error_count += 1
        if self.last_error_time is None:
            self.last_error_time = time.time()
        
        self.errors_by_type[error_type] = self.errors_by_type.get(error_type, 0) + 1
        
    def get_max_errors(self) -> int:
        """Get maximum allowed errors for this ticket type"""
        return 5 if self.target_type == "person" else 3


@dataclass
class PipelineExecutionResult:
    """Results of pipeline execution"""
    total_processed: int = 0
    successful: int = 0
    failed_retryable: int = 0
    failed_permanent: int = 0
    bottlenecks_detected: List[str] = field(default_factory=list)
    total_execution_time_seconds: float = 0.0
    average_throughput_per_minute: float = 0.0
    error_summary: Dict[str, int] = field(default_factory=dict)
    report_path: Optional[str] = None


class StageCircuitBreaker:
    """Circuit breaker pattern for stage failure prevention"""
    
    def __init__(self, failure_threshold: int = 5, recovery_time: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.state: str = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.failure_count: int = 0
        self.last_failure_time: Optional[float] = None
    
    def record_success(self):
        """Record a successful execution"""
        self.failure_count = 0
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
    
    def record_failure(self) -> bool:
        """Record a failure and check if circuit should open
        
        Returns True if circuit is now OPEN (execution should be blocked)"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            return True
        
        # Check if enough time has passed to try HALF_OPEN state
        if self.state == "OPEN":
            elapsed = time.time() - self.last_failure_time
            if elapsed > self.recovery_time:
                self.state = "HALF_OPEN"
        
        return False
    
    def can_execute(self) -> bool:
        """Check if execution is allowed"""
        if self.state == "CLOSED":
            return True
        
        if self.state == "OPEN":
            # Check recovery time
            if self.last_failure_time and (time.time() - self.last_failure_time) < self.recovery_time:
                return False
            
            # Transition to HALF_OPEN for testing
            self.state = "HALF_OPEN"
        
        return True


class KanbanColumnState:
    """State management for a single Kanban column"""
    
    def __init__(self, name: str, wip_limit: int):
        self.name = name
        self.wip_limit = wip_limit
        self.current_work_in_progress: List[OsintTicket] = []
        self.queue: List[OsintTicket] = []
        
    def has_capacity(self) -> bool:
        """Check if column can accept more work"""
        return len(self.current_work_in_progress) < self.wip_limit
    
    @property
    def current_wip_count(self) -> int:
        """Current number of items in progress"""
        return len(self.current_work_in_progress)
    
    @property
    def total_queue_size(self) -> int:
        """Total items waiting (queue + WIP)"""
        return len(self.queue) + len(self.current_work_in_progress)
    
    def add_ticket(self, ticket: OsintTicket):
        """Add ticket to appropriate list based on state"""
        if self.has_capacity():
            self.current_work_in_progress.append(ticket)
        else:
            self.queue.append(ticket)
    
    def remove_from_wip(self, ticket_id: str) -> bool:
        """Remove ticket from WIP list"""
        for i, ticket in enumerate(self.current_work_in_progress):
            if ticket.ticket_id == ticket_id:
                del self.current_work_in_progress[i]
                return True
        return False
    
    def promote_from_queue(self) -> Optional[OsintTicket]:
        """Promote next item from queue to WIP if capacity available"""
        if not self.queue or not self.has_capacity():
            return None
        
        ticket = self.queue.pop(0)
        self.current_work_in_progress.append(ticket)
        return ticket


class PipelineHealthMonitor:
    """Monitors pipeline health and detects bottlenecks"""
    
    def __init__(self, columns: Dict[str, KanbanColumnState]):
        self.columns = columns
        self.execution_history: List[Dict] = []
        
    def get_bottleneck_stage(self) -> Optional[str]:
        """Identify which stage is causing slowdown
        
        Returns the name of the bottleneck stage or None if no bottleneck"""
        # Calculate average processing time and queue size for each stage
        metrics = {}
        
        for stage_name, column in self.columns.items():
            avg_queue_size = column.total_queue_size / max(1, len(self.execution_history))
            total_processing_time = sum(
                ex['duration'] 
                for ex in self.execution_history 
                if ex.get('stage') == stage_name and ex.get('success', False)
            )
            execution_count = sum(
                1 for ex in self.execution_history 
                if ex.get('stage') == stage_name
            )
            
            avg_processing_time = total_processing_time / max(1, execution_count)
            
            metrics[stage_name] = {
                'queue_size': avg_queue_size,
                'avg_processing_time': avg_processing_time,
                'total_executions': execution_count
            }
        
        # Find bottleneck: stage with highest queue size AND longest processing time
        bottlenecks = []
        for stage, m in metrics.items():
            if m['queue_size'] > 2 and m['avg_processing_time'] > 10:
                bottlenecks.append(stage)
        
        return bottlenecks[0] if bottlenecks else None
    
    def record_execution(self, stage: str, duration: float, success: bool):
        """Record execution metrics"""
        self.execution_history.append({
            'stage': stage,
            'duration': duration,
            'success': success,
            'timestamp': time.time()
        })
        
        # Keep only last 100 entries for performance
        if len(self.execution_history) > 100:
            self.execution_history = self.execution_history[-100:]


class OsintPipelineManager:
    """Main orchestrator for the OSINT pipeline"""
    
    def __init__(self, config: PipelineConfig):
        self.config = config
        
        # Initialize circuit breakers for each stage
        self.circuit_breakers: Dict[str, StageCircuitBreaker] = {
            "RECON": StageCircuitBreaker(3, 120),
            "HARVESTING": StageCircuitBreaker(5, 60),
            "ANALYST": StageCircuitBreaker(4, 90),
            "SCRIBE": StageCircuitBreaker(2, 30)
        }
        
        # Initialize Kanban columns with WIP limits
        self.columns: Dict[str, KanbanColumnState] = {}
        for stage_name, wip_limit in config.wip_limits.items():
            self.columns[stage_name] = KanbanColumnState(stage_name, wip_limit)
        
        # Health monitoring
        self.monitor = PipelineHealthMonitor(self.columns)
        
        # Pipeline state tracking
        self.state: PipelineState = PipelineState.INITIALIZING
        
        # Results tracking
        self.results: PipelineExecutionResult = PipelineExecutionResult()
    
    async def start_pipeline(self, user_query: str, target_type: str):
        """Initialize and start the pipeline with a new investigation"""
        
        if self.state != PipelineState.INITIALIZING:
            logger.warning(f"Pipeline already in {self.state.value} state")
            return
        
        # Create new ticket for this investigation
        import uuid
        ticket_id = f"{target_type.lower()}_{uuid.uuid4().hex[:8]}"
        
        self.config.target_name = user_query.split('"')[1] if '"' in user_query else user_query[:30]
        self.config.target_type = target_type
        
        new_ticket = OsintTicket(
            ticket_id=ticket_id,
            user_query=user_query,
            target_type=target_type
        )
        
        # Add to RECON column (initial stage)
        self.columns["RECON"].add_ticket(new_ticket)
        
        logger.info(f"🚀 Starting new investigation: {user_query}")
        logger.info(f"   Ticket ID: {ticket_id}, Target Type: {target_type}")
        
        # Start the pull-based processing loop
        await self._process_pull_loop()
    
    async def _process_pull_loop(self):
        """Main pull-based processing loop"""
        
        self.state = PipelineState.RUNNING
        
        while not self.columns["SCRIBE"].has_capacity():  # Keep running until SCRIBE has capacity
            # Check for pipeline completion
            if all(
                len(col.current_work_in_progress) == 0 and 
                len(col.queue) == 0 
                for col in self.columns.values()
            ):
                logger.info("✅ All work completed")
                break
            
            # Check for critical failures
            if self.has_critical_failures():
                logger.error("🚨 Critical failure detected - pipeline halted")
                self.state = PipelineState.FAILED
                return
            
            # Try to pull from downstream stages first (pull-based)
            pulled_any = False
            
            # Priority 1: SCRIBE stage (final output)
            if not self.columns["SCRIBE"].current_work_in_progress and \
               self._can_pull_from_stage("SCRIBE"):
                await self._process_analyst_ticket()
                pulled_any = True
            
            # Priority 2: ANALYST stage (if not already being processed)
            elif not self.columns["ANALYST"].current_work_in_progress and \
                 self._can_pull_from_stage("ANALYST"):
                await self._process_harvesting_ticket()
                pulled_any = True
            
            # Priority 3: HARVESTING stage (if RECON completed)
            elif not self.columns["HARVESTING"].current_work_in_progress and \
                 self._can_pull_from_stage("HARVESTING"):
                await self._process_recon_ticket()
                pulled_any = True
            
            # If nothing was pulled, wait briefly before retrying
            if not pulled_any:
                await asyncio.sleep(0.5)
        
        self.state = PipelineState.COMPLETED
    
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
        """Execute RECON stage for a ticket"""
        
        start_time = time.time()
        
        try:
            # Check circuit breaker
            if not self.circuit_breakers["RECON"].can_execute():
                logger.warning("Circuit breaker open for RECON, skipping")
                return False
            
            from osint_recon_stage import generate_osint_queries
            
            result = await generate_osint_queries(
                user_input=ticket.user_query,
                target_type=ticket.target_type
            )
            
            ticket.recon_results = {
                "queries": [q['query'] for q in result.queries],
                "api_queries": result.api_queries,
                "confidence_scores": [q.get('confidence', 0.5) for q in result.queries]
            }
            
            # Record success and update ticket status
            self.circuit_breakers["RECON"].record_success()
            ticket.status = StageStatus.COMPLETED
            
            duration = time.time() - start_time
            self.monitor.record_execution("RECON", duration, True)
            
            logger.info(f"   ✓ RECON completed for {ticket.ticket_id} in {duration:.1f}s")
            return True
            
        except Exception as e:
            logger.error(f"✗ RECON failed for {ticket.ticket_id}: {e}")
            ticket.increment_error("RECON_FAILURE")
            
            if self.circuit_breakers["RECON"].record_failure():
                logger.warning("Circuit breaker opened for RECON")
            
            duration = time.time() - start_time
            self.monitor.record_execution("RECON", duration, False)
            
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
        """Execute ANALYST stage for a ticket"""
        
        start_time = time.time()
        
        try:
            # Check circuit breaker
            if not self.circuit_breakers["ANALYST"].can_execute():
                logger.warning("Circuit breaker open for ANALYST, skipping")
                return False
            
            from osint_analyst_stage import OSINTAnalystStage
            
            # Initialize analyst with privacy mode (default: local)
            privacy_mode = self.config.api_keys.get('PRIVACY_MODE', 'local')
            analyst = OSINTAnalystStage(privacy_mode=privacy_mode)
            
            # Prepare raw data for processing (convert harvest results to expected format)
            raw_harvest_data = {}
            for result in ticket.harvest_results:
                tool_name = result.get("tool_name", "unknown")
                raw_harvest_data[tool_name] = result.get("raw_data", [])
            
            # Add target metadata
            raw_harvest_data['_target'] = self.config.target_name
            
            # Process through analyst stage
            report = analyst.process_harvest_results(raw_harvest_data)
            
            # Save the analysis report
            output_path = analyst.save_report(report, f"analyst_{ticket.ticket_id}.json")
            
            # Store results in ticket for downstream stages
            ticket.analysis_results = {
                "verified_entities": [f.__dict__ for f in report.facts if f.confidence_score >= 70],
                "all_facts": [f.__dict__ for f in report.facts],
                "confidence_summary": report.confidence_summary,
                "analysis_timestamp": report.analysis_timestamp.isoformat(),
                "report_path": output_path
            }
            
            self.circuit_breakers["ANALYST"].record_success()
            ticket.status = StageStatus.COMPLETED
            
            duration = time.time() - start_time
            self.monitor.record_execution("ANALYST", duration, True)
            
            logger.info(f"   ✓ ANALYST completed for {ticket.ticket_id} in {duration:.1f}s")
            logger.info(f"      Processed {len(report.facts)} facts with privacy mode: {privacy_mode}")
            return True
            
        except Exception as e:
            logger.error(f"✗ ANALYST failed for {ticket.ticket_id}: {e}")
            ticket.increment_error("ANALYST_FAILURE")
            
            if self.circuit_breakers["ANALYST"].record_failure():
                logger.warning("Circuit breaker opened for ANALYST")
            
            duration = time.time() - start_time
            self.monitor.record_execution("ANALYST", duration, False)
            
            return False
    
    async def _process_scribe(self, ticket: OsintTicket) -> bool:
        """Execute SCRIBE stage for a ticket"""
        
        start_time = time.time()
        
        try:
            # Check circuit breaker
            if not self.circuit_breakers["SCRIBE"].can_execute():
                logger.warning("Circuit breaker open for SCRIBE, skipping")
                return False
            
            from osint_scribe_stage import generate_osint_report
            
            # Generate final report using analysis results
            report = await generate_osint_report(
                target_name=self.config.target_name,
                recon_results=ticket.recon_results,
                harvest_results=ticket.harvest_results,
                analysis_results=ticket.analysis_results,
                output_format="json"  # or "html", "pdf" when implemented
            )
            
            ticket.scribe_results = {
                "report": report,
                "status": "generated"
            }
            
            self.circuit_breakers["SCRIBE"].record_success()
            ticket.status = StageStatus.COMPLETED
            
            duration = time.time() - start_time
            self.monitor.record_execution("SCRIBE", duration, True)
            
            logger.info(f"   ✓ SCRIBE completed for {ticket.ticket_id} in {duration:.1f}s")
            return True
            
        except Exception as e:
            logger.error(f"✗ SCRIBE failed for {ticket.ticket_id}: {e}")
            ticket.increment_error("SCRIBE_FAILURE")
            
            if self.circuit_breakers["SCRIBE"].record_failure():
                logger.warning("Circuit breaker opened for SCRIBE")
            
            duration = time.time() - start_time
            self.monitor.record_execution("SCRIBE", duration, False)
            
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
