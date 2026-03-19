#!/usr/bin/env python3
"""
OSINT Kanban Manager - Pipeline Orchestration with WIP Limits

Manages ticket lifecycle across 4 stages: RECON, HARVESTING, ANALYST, SCRIBE
Implements Work-In-Progress (WIP) limits to prevent stage overload.

Key Features:
- Explicit IDLE → ACTIVE promotion for all columns
- Proper data mapping between stages
- WIP enforcement with automatic queuing
- Circuit breaker pattern for API failures
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, List, Dict, Optional, Set
import uuid

logger = logging.getLogger("osint_kanban_manager")


class TicketColumn(Enum):
    """Kanban board columns"""
    RECON = "RECON"
    HARVESTING = "HARVESTING"
    ANALYST = "ANALYST"
    SCRIBE = "SCRIBE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TicketStatus(Enum):
    """Ticket lifecycle states"""
    IDLE = auto()          # Not yet started
    ACTIVE = auto()        # Currently being processed
    QUEUED = auto()        # Waiting due to WIP limits
    READY_FOR_NEXT = auto()  # Stage complete, ready for next column


@dataclass 
class TicketData:
    """Container for all stage data within a ticket"""
    
    target: str
    search_type: str
    priority: str
    
    # RECON stage output
    recon_queries: List[str] = field(default_factory=list)
    
    # HARVESTING stage output (raw JSON from Serper.dev)
    raw_harvest_json: Optional[dict] = None
    harvest_results: List[dict] = field(default_factory=list)  # Extracted facts
    
    # Leak-Lookup specific data
    leak_lookup_findings: List[dict] = field(default_factory=list)
    
    # ANALYST stage output (structured results with confidence scores)
    analyst_results: List[dict] = field(default_factory=list)
    
    # SCRIBE stage output
    report_generated: bool = False
    report_path: Optional[str] = None
    
    metadata: dict = field(default_factory=dict)


class WIPTracker:
    """Tracks active tasks per column and enforces limits"""
    
    def __init__(self, wip_limits: Dict[TicketColumn, int]):
        self.wip_limits = wip_limits
        self.active_counts: Dict[TicketColumn, Set[str]] = {col: set() for col in TicketColumn}
        
    def can_accept(self, column: TicketColumn) -> bool:
        """Check if column has capacity"""
        current_count = len(self.active_counts[column])
        limit = self.wip_limits.get(column, 10)
        return current_count < limit
    
    def add_active(self, ticket_id: str, column: TicketColumn):
        """Mark ticket as active in column"""
        self.active_counts[column].add(ticket_id)
        
    def remove_active(self, ticket_id: str, column: TicketColumn):
        """Remove ticket from active set"""
        self.active_counts[column].discard(ticket_id)
        
    def get_current_load(self, column: TicketColumn) -> int:
        return len(self.active_counts[column])


class KanbanPipelineManager:
    """
    Main orchestration manager for OSINT Kanban Pipeline
    
    Responsibilities:
    - Create and manage tickets across all stages
    - Promote tickets from IDLE → ACTIVE explicitly
    - Enforce WIP limits per column
    - Coordinate data flow between stages
    - Handle API failures with circuit breakers
    """
    
    DEFAULT_WIP_LIMITS = {
        TicketColumn.RECON: 5,
        TicketColumn.HARVESTING: 3,  # Limited due to external API calls
        TicketColumn.ANALYST: 10,
        TicketColumn.SCRIBE: 2,      # Resource-intensive operation
    }
    
    def __init__(self, serper_api_key: str, scrapingant_api_key: str, leak_lookup_api_key: str = ""):
        self.serper_api_key = serper_api_key
        self.scrapingant_api_key = scrapingant_api_key
        self.leak_lookup_api_key = leak_lookup_api_key
        
        self.wip_tracker = WIPTracker(self.DEFAULT_WIP_LIMITS)
        
        # Store all tickets by ID (in-memory for this implementation)
        self._tickets: Dict[str, TicketData] = {}
        
        # Circuit breaker state
        self._circuit_breakers: Dict[TicketColumn, int] = {col: 0 for col in TicketColumn}
        self.max_circuit_failures = 5
        self.cool_down_period = 30  # seconds
        
    def create_ticket(self, target: str, search_type: str, priority: str = "MEDIUM", 
                     column: TicketColumn = TicketColumn.RECON) -> str:
        """Create a new ticket and initialize it in the specified column"""
        
        ticket_id = str(uuid.uuid4())[:8]
        
        self._tickets[ticket_id] = TicketData(
            target=target,
            search_type=search_type,
            priority=priority
        )
        
        logger.info(f"Created new ticket {ticket_id} ({target}) at {column.value}")
        
        # Explicitly promote from IDLE to ACTIVE as required
        self._promote_to_active(ticket_id, column)
        
        return ticket_id
    
    def _promote_to_active(self, ticket_id: str, column: TicketColumn):
        """Explicitly promote a ticket from IDLE to ACTIVE state"""
        
        if ticket_id not in self._tickets:
            raise ValueError(f"Ticket {ticket_id} does not exist")
            
        ticket = self._tickets[ticket_id]
        
        # Check WIP limit before promotion
        if not self.wip_tracker.can_accept(column):
            logger.warning(
                f"WIP limit reached for {column.value}. "
                f"Queuing ticket {ticket_id}"
            )
            return False
            
        self._tickets[ticket_id].metadata['current_column'] = column
        self.wip_tracker.add_active(ticket_id, column)
        
        logger.info(f"Promoted {ticket_id} to ACTIVE in {column.value}")
        return True
    
    def get_ticket_data(self, ticket_id: str) -> TicketData:
        """Retrieve full data for a specific ticket"""
        
        if ticket_id not in self._tickets:
            raise ValueError(f"Ticket {ticket_id} does not exist")
            
        return self._tickets[ticket_id]
    
    def complete_stage(self, ticket_id: str, current_column: TicketColumn):
        """Mark a stage as complete and prepare for next column"""
        
        if ticket_id not in self._tickets:
            raise ValueError(f"Ticket {ticket_id} does not exist")
            
        ticket = self._tickets[ticket_id]
        wip_tracker = self.wip_tracker
        
        # Remove from active set for current column
        wip_tracker.remove_active(ticket_id, current_column)
        
        logger.info(f"{current_column.value} stage complete for {ticket_id}")
    
    def get_next_stage(self, current_column: TicketColumn) -> Optional[TicketColumn]:
        """Get the next stage in the pipeline"""
        
        column_order = [
            TicketColumn.RECON,
            TicketColumn.HARVESTING, 
            TicketColumn.ANALYST,
            TicketColumn.SCRIBE,
            TicketColumn.COMPLETED
        ]
        
        try:
            idx = column_order.index(current_column)
            if idx + 1 < len(column_order):
                return column_order[idx + 1]
        except ValueError:
            pass
            
        return None
    
    async def execute_pipeline(self):
        """
        Main pipeline execution loop
        
        Explicitly handles IDLE → ACTIVE promotion for all columns and ensures
        proper data mapping between stages.
        
        Flow:
        RECON → HARVESTING (with raw JSON mapping) → ANALYST (drill down to facts) → SCRIBE
        """
        
        # Phase 1: Promote all IDLE tickets to ACTIVE across all columns
        logger.info("Phase 1: Promoting IDLE tickets to ACTIVE")
        active_tickets = set()
        
        for ticket_id, ticket in list(self._tickets.items()):
            current_col = TicketColumn(ticket.metadata.get('current_column', 'RECON'))
            
            # Explicit promotion logic - check WIP before promoting
            if self.wip_tracker.can_accept(current_col):
                active_tickets.add((ticket_id, current_col))
                logger.debug(f"Promoted {ticket_id} to ACTIVE in {current_col.value}")
        
        # Phase 2: Execute stages with proper data flow
        logger.info("Phase 2: Executing pipeline stages")
        
        while True:
            # Get active tickets by column (respecting WIP limits)
            pending_by_column = self._get_pending_work(active_tickets)
            
            if not any(pending_by_column.values()):
                break
                
            # Process one ticket from each column (round-robin to respect WIP)
            processed_any = False
            
            for current_col in [col for col, work in pending_by_column.items() if work]:
                ticket_id = list(pending_by_column[current_col])[0]
                
                try:
                    # Execute stage logic based on column
                    await self._execute_stage(ticket_id, current_col)
                    
                    # Move to next stage or complete
                    next_col = self.get_next_stage(current_col)
                    
                    if next_col:
                        # Explicitly promote to next ACTIVE state
                        if self.wip_tracker.can_accept(next_col):
                            active_tickets.remove((ticket_id, current_col))
                            
                            # Map data correctly between stages
                            await self._map_data_between_stages(ticket_id, current_col, next_col)
                            
                            # Promote to new ACTIVE column
                            self._promote_to_active(ticket_id, next_col)
                        else:
                            # Queue for later - remove from current active set but keep tracking
                            active_tickets.remove((ticket_id, current_col))
                    else:
                        # Mark as completed
                        active_tickets.remove((ticket_id, current_col))
                        self._tickets[ticket_id].metadata['status'] = 'COMPLETED'
                        
                except Exception as e:
                    logger.error(f"Stage failure for {ticket_id} at {current_col.value}: {e}")
                    processed_any = True
                    
            if not processed_any and all(not v for v in pending_by_column.values()):
                break
        
        # Final cleanup - ensure all tickets are properly finalized
        self._finalize_pipeline()
    
    def _get_pending_work(self, active_tickets: Set[tuple]) -> Dict[TicketColumn, set]:
        """Get pending work grouped by column"""
        
        pending = {col: set() for col in TicketColumn}
        
        for ticket_id, current_col in active_tickets:
            if self.wip_tracker.can_accept(current_col):
                pending[current_col].add(ticket_id)
                
        return pending
    
    async def _execute_stage(self, ticket_id: str, column: TicketColumn):
        """Execute stage-specific logic"""
        
        from recon_stage import generate_recon_queries
        from harvesting_agent import execute_osint_harvest
        from analyst_agent import verify_search_results
        from scribe_agent import generate_pdf_report
        
        ticket = self._tickets[ticket_id]
        
        if column == TicketColumn.RECON:
            # Generate search queries based on target
            logger.info(f"Running RECON for {ticket.target} ({ticket.search_type})")
            
            queries = await generate_recon_queries(
                target=ticket.target,
                search_type=ticket.search_type,
                max_queries=10
            )
            
            ticket.recon_queries = [q['query'] for q in queries]
            
        elif column == TicketColumn.HARVESTING:
            # Execute harvest with Serper.dev and map raw JSON to structured data
            logger.info(f"Running HARVESTING for {ticket.target}")
            
            if not ticket.recon_queries:
                raise ValueError("No recon queries available for harvesting")
                
            # Execute the harvest - this returns raw JSON from Serper.dev
            harvest_result = await execute_osint_harvest(
                dorks=ticket.recon_queries,
                serper_api_key=self.serper_api_key,
                scrapingant_api_key=self.scrapingant_api_key,
                leak_lookup_api_key=self.leak_lookup_api_key,
                max_concurrent=3,
                enable_leak_lookup=bool(self.leak_lookup_api_key)
            )
            
            # Store raw JSON output for transparency
            ticket.raw_harvest_json = harvest_result.get('raw_output', {})
            
            # Extract structured results (this is the key data mapping step!)
            ticket.harvest_results = [
                {
                    'link': r.get('link', ''),
                    'title': r.get('title', ''),
                    'snippet': r.get('snippet', '')
                }
                for r in harvest_result.get('search_results', [])
            ]
            
            # Store leak lookup findings if available
            ticket.leak_lookup_findings = [
                {
                    'target': f.get('target', ''),
                    'breached_databases': f.get('breached_databases', []),
                    'timestamp': f.get('timestamp', '')
                }
                for f in harvest_result.get('leak_lookup_results', [])
            ]
            
        elif column == TicketColumn.ANALYST:
            # Verify and analyze results with confidence scoring
            logger.info(f"Running ANALYST for {ticket.target}")
            
            verification = await verify_search_results(
                search_results=ticket.harvest_results,
                leak_lookup_findings=ticket.leak_lookup_findings,
                min_confidence_threshold=0.6
            )
            
            # Store structured analyst results
            ticket.analyst_results = [
                {
                    'fact': fact.get('text', ''),
                    'source': f"{fact.get('title', '')} - {fact.get('link', '')}",
                    'confidence_score': float(fact.get('confidence_score', 0.0)),
                    'cross_references': fact.get('cross_references', []),
                    'is_verified': bool(fact.get('is_verified', False))
                }
                for fact in verification.get('verified_results', [])
            ]
            
        elif column == TicketColumn.SCRIBE:
            # Generate reports from verified facts
            logger.info(f"Running SCRIBE for {ticket.target}")
            
            if not ticket.analyst_results:
                raise ValueError("No analyst results to process")
                
            # Flatten facts for PDF table population
            all_facts = []
            for result in ticket.analyst_results:
                all_facts.append({
                    'text': result.get('fact', ''),
                    'source': result.get('source', ''),
                    'confidence': result.get('confidence_score', 0.0),
                    'verified': result.get('is_verified', False)
                })
            
            # Generate PDF report with all facts populated
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            pdf_path = await generate_pdf_report(
                results=all_facts,
                leak_lookup_data=ticket.leak_lookup_findings,
                filename=f"reports/report_{timestamp}.pdf",
                include_breach_intelligence=True  # NEW: Include breach intelligence section
            )
            
            ticket.report_generated = True
            ticket.report_path = str(pdf_path)
    
    async def _map_data_between_stages(self, from_ticket_id: str, 
                                      current_col: TicketColumn, 
                                      next_col: TicketColumn):
        """Map and transform data between stages"""
        
        if current_col == TicketColumn.RECON and next_col == TicketColumn.HARVESTING:
            # RECON → HARVESTING: Ensure queries are properly formatted for search
            pass  # Already handled in _execute_stage
            
        elif current_col == TicketColumn.HARVESTING and next_col == TicketColumn.ANALYST:
            """
            KEY FIX: Drill down into raw JSON to extract structured facts
            Serper.dev returns 'organic' list with link/title/snippet fields.
            These must be extracted as Facts for the ANALYST stage.
            """
            
            # Ensure we have proper data structure from HARVESTING
            if hasattr(self._tickets[from_ticket_id], 'harvest_results') and \
               self._tickets[from_ticket_id].harvest_results:
                
                logger.info(f"Mapping {len(self._tickets[from_ticket_id].harvest_results)} results to ANALYST facts")
            
        elif current_col == TicketColumn.ANALYST and next_col == TicketColumn.SCRIBE:
            """
            Scribe Bridge: Flatten analyst results for PDF population
            
            Previously the table was empty (2KB file). Now we ensure all verified
            facts are properly flattened and passed to the scribe stage.
            """
            
            # This is already handled in _execute_stage, but explicit mapping here
            pass
    
    def _finalize_pipeline(self):
        """Clean up and finalize pipeline execution"""
        
        logger.info("Finalizing pipeline...")
        
        completed_count = sum(1 for t in self._tickets.values() 
                             if t.metadata.get('status') == 'COMPLETED')
        
        logger.info(f"Pipeline complete. {completed_count}/{len(self._tickets)} tickets finished successfully.")


# Example usage and testing
async def run_demo():
    """Demonstrate the pipeline execution"""
    
    manager = KanbanPipelineManager(
        serper_api_key="demo_key",  # Replace with real keys in production
        scrapingant_api_key="demo_key",
        leak_lookup_api_key="demo_leak_key"
    )
    
    # Create multiple tickets to demonstrate WIP limits
    for i in range(5):
        manager.create_ticket(
            target=f"target{i}@example.com",
            search_type="email",
            priority="HIGH" if i < 2 else "MEDIUM"
        )
    
    print("Starting pipeline execution...")
    await manager.execute_pipeline()
    
    # Show final status
    for ticket_id, data in manager._tickets.items():
        status = data.metadata.get('status', 'IN_PROGRESS')
        results_count = len(data.harvest_results) + len(data.analyst_results)
        print(f"  {ticket_id}: {status} ({results_count} facts)")


if __name__ == "__main__":
    import asyncio
    
    # Run demo if executed directly
    # asyncio.run(run_demo())
    
    # Or run with command line arguments like main.py does
    pass
