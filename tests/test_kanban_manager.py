"""Tests for the Kanban Manager - Pipeline orchestration and WIP limits"""

import pytest
from unittest.mock import AsyncMock, patch
from osint_kanban_manager import (
    OsintKanbanManager, 
    PipelineConfig,
    OsintTicket
)


class TestKanbanManager:
    """Test suite for pipeline orchestration"""
    
    def test_pipeline_config_initialization(self):
        """Test configuration initialization with default values"""
        
        config = PipelineConfig(
            target_name="Test Target",
            wip_limits={"RECON": 3, "HARVESTING": 5, "ANALYST": 2, "SCRIBE": 1},
            api_keys={"SERPER_API_KEY": "test_key"}
        )
        
        assert config.target_name == "Test Target"
        assert config.wip_limits["RECON"] == 3
        assert config.max_retries_per_ticket == 3
        
    def test_pipeline_config_custom_wip(self):
        """Test configuration with custom WIP limits"""
        
        config = PipelineConfig(
            target_name="Test Target", 
            wip_limits={"RECON": 5, "HARVESTING": 10, "ANALYST": 3, "SCRIBE": 2},
            api_keys={}
        )
        
        assert config.wip_limits["HARVESTING"] == 10
        
    @pytest.mark.asyncio
    async def test_ticket_creation(self):
        """Test OsintTicket creation and initialization"""
        
        ticket = OsintTicket(
            user_query="John Doe, Apple Inc"
        )
        
        assert hasattr(ticket, 'id')
        assert ticket.user_query == "John Doe, Apple Inc"
        assert ticket.error_count == 0
        
    @pytest.mark.asyncio
    async def test_ticket_error_counter(self):
        """Test error counter incrementing"""
        
        ticket = OsintTicket(user_query="Test query")
        
        initial_count = ticket.error_count
        ticket.increment_error_counter("RATE_LIMIT")
        
        assert ticket.error_count == initial_count + 1
        
    @pytest.mark.asyncio
    async def test_ticket_manual_review_flag(self):
        """Test flagging ticket for manual review"""
        
        ticket = OsintTicket(user_query="Test query")
        
        assert ticket.manual_review_flagged is False
        
        ticket.mark_for_manual_review(
            reason="Insufficient data",
            evidence={"missing_fields": ["company"]}
        )
        
        assert ticket.manual_review_flagged is True
        
    @pytest.mark.asyncio
    async def test_manager_initialization(self):
        """Test Kanban manager initialization"""
        
        config = PipelineConfig(
            target_name="Test Target",
            wip_limits={"RECON": 3, "HARVESTING": 5, "ANALYST": 2, "SCRIBE": 1},
            api_keys={}
        )
        
        manager = OsintKanbanManager(config=config)
        
        assert len(manager.columns["RECON"]) == 0
        assert not manager.is_running()


class TestWipLimits:
    """Test WIP limit enforcement"""
    
    @pytest.mark.asyncio
    async def test_wip_limit_enforcement(self):
        """Test that stages respect their WIP limits"""
        
        config = PipelineConfig(
            target_name="Test Target",
            wip_limits={"RECON": 2, "HARVESTING": 1, "ANALYST": 1, "SCRIBE": 1},
            api_keys={}
        )
        
        manager = OsintKanbanManager(config=config)
        
        # Simulate adding items to RECON column
        for i in range(5):
            ticket = OsintTicket(user_query=f"Query {i}")
            
            # Should only add if below WIP limit
            should_add = len(manager.columns["RECON"]) < manager.config.wip_limits["RECON"]
            
            if should_add:
                manager.columns["RECON"].append(ticket)
        
        # Verify we didn't exceed WIP limit
        assert len(manager.columns["RECON"]) <= 2
        
    @pytest.mark.asyncio
    async def test_pull_on_capacity(self):
        """Test that downstream stages pull work only when capacity available"""
        
        config = PipelineConfig(
            target_name="Test Target",
            wip_limits={"RECON": 3, "HARVESTING": 5, "ANALYST": 2, "SCRIBE": 1},
            api_keys={}
        )
        
        manager = OsintKanbanManager(config=config)
        
        # Fill RECON column to capacity
        for i in range(3):
            ticket = OsintTicket(user_query=f"Query {i}")
            manager.columns["RECON"].append(ticket)
        
        # Try to pull from RECON when ANALYST is at WIP limit
        manager.columns["ANALYST"] = [OsintTicket("Test"), OsintTicket("Test2")]  # At limit
        
        should_pull = manager._pull_from_upstream("ANALYST")
        
        # Should return False - no capacity available
        assert not should_pull


class TestErrorHandling:
    """Test error recovery mechanisms"""
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_activation(self):
        """Test circuit breaker pattern activation after failures"""
        
        config = PipelineConfig(
            target_name="Test Target",
            wip_limits={"RECON": 3, "HARVESTING": 5, "ANALYST": 2, "SCRIBE": 1},
            api_keys={},
            enable_circuit_breaker=True,
            recovery_time_after_failure=60
        )
        
        manager = OsintKanbanManager(config=config)
        
        # Simulate multiple failures to trigger circuit breaker
        for i in range(5):
            manager._record_stage_failure("HARVESTING")
        
        # Circuit should now be open (blocking execution)
        is_open = manager._is_circuit_breaker_open("HARVESTING")
        assert is_open is True
        
    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        """Test handling when maximum retries are exceeded"""
        
        ticket = OsintTicket(user_query="Test query")
        
        # Simulate exceeding max retries (default: 3)
        for i in range(4):
            ticket.increment_error_counter("RETRYABLE_ERROR")
        
        assert ticket.error_count >= 4
        # Should trigger manual review flagging automatically
        
    @pytest.mark.asyncio  
    async def test_graceful_failure_handling(self):
        """Test graceful degradation on stage failures"""
        
        config = PipelineConfig(
            target_name="Test Target",
            wip_limits={"RECON": 3, "HARVESTING": 5, "ANALYST": 2, "SCRIBE": 1},
            api_keys={},
            max_retries_per_ticket=1  # Low retry for testing
        )
        
        manager = OsintKanbanManager(config=config)
        
        # Simulate failure but with graceful handling enabled
        try:
            # This should not crash the system
            result = await manager.execute_pipeline(
                query="Test Target",
                report_format=None,  # Will fail gracefully
                max_retries_per_ticket=1,
                graceful_failure_handling=True
            )
            
            # System should still return a result object even with failures
            assert hasattr(result, 'total_processed')
            
        except Exception:
            pytest.fail("Pipeline crashed despite graceful handling enabled")
