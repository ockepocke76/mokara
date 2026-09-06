#!/usr/bin/env python3
"""
Test suite for strategy evaluation worker.

This validates the worker implementation BEFORE migrating the admin UI,
following lessons learned from PDF generation.
"""

import sys
import pytest
from unittest.mock import Mock, patch

# Add project root to path
sys.path.insert(0, '/Users/oscarsverud/dev/btc_sim')


class TestStrategyEvaluationWorker:
    """Tests for worker strategy evaluation functionality."""
    
    def test_builtin_strategy_evaluation(self):
        """Test worker can evaluate a built-in strategy."""
        from services.background_worker import JobWorker
        
        worker = JobWorker("test_worker")
        
        payload = {
            'strategy_class': 'TrinityStrategy',
            'strategy_name': 'Trinity Test'
        }
        
        # This should work with current implementation
        result = worker._process_strategy_evaluation('test-job-1', payload)
        
        assert result is not None
        assert 'evaluation_id' in result or 'excellence_score' in result
        assert result.get('strategy_category') in ['CONTRIBUTION_ONLY', 'WITHDRAWAL_ONLY', 'HYBRID']
    
    def test_invalid_strategy_class(self):
        """Test worker handles invalid strategy class gracefully."""
        from services.background_worker import JobWorker
        
        worker = JobWorker("test_worker")
        
        payload = {
            'strategy_class': 'NonExistentStrategy',
            'strategy_name': 'Fake Strategy'
        }
        
        # Should raise error
        with pytest.raises((ValueError, KeyError)):
            worker._process_strategy_evaluation('test-job-2', payload)
    
    def test_custom_strategy_evaluation(self):
        """Test worker can evaluate a custom strategy (future)."""
        pytest.skip("Custom strategy support not yet implemented in worker")
        
        from services.background_worker import JobWorker
        
        worker = JobWorker("test_worker")
        
        # Simple test strategy
        code = '''
class SimpleTestStrategy:
    def __init__(self, params):
        self.params = params
    
    def reset(self):
        self.year = 0
    
    def execute(self, current_portfolio, asset_price, year, params):
        """Simple buy-and-hold strategy for testing."""
        return {
            'action': 'hold',
            'amount': 0
        }
    
    @property
    def parameters(self):
        return {}
'''
        
        payload = {
            'type': 'custom',
            'strategy_name': 'Simple Test',
            'user_id': 999,
            'custom_strategy_id': 1,
            'code': code,
            'class_name': 'SimpleTestStrategy',
            'params': {}
        }
        
        result = worker._process_strategy_evaluation('test-job-3', payload)
        
        assert result is not None
        assert 'excellence_score' in result


class TestWorkerIntegration:
    """Integration tests for full worker flow."""
    
    def test_job_queue_to_completion(self):
        """Test creating a job and worker processing it."""
        pytest.skip("Requires BackgroundManager.start_strategy_evaluation() implementation")
        
        from services.background_manager import BackgroundManager
        from db.database import db
        
        manager = BackgroundManager()
        
        # Start evaluation
        job_id = manager.start_strategy_evaluation(
            strategy_class='TrinityStrategy',
            strategy_name='Trinity Integration Test'
        )
        
        assert job_id is not None
        
        # Check job was created
        job = db.get_job_by_id(job_id)
        assert job is not None
        assert job['status'] == 'pending'
        assert job['job_type'] == 'strategy_evaluation'


def manual_worker_test():
    """
    Manual test function to validate worker on a real strategy.
    Run this directly to test before implementing admin UI changes.
    """
    print("=== Manual Worker Test ===\n")
    
    from services.background_worker import JobWorker
    from db.database import db
    
    worker = JobWorker("manual_test")
    
    # Test Trinity Strategy
    print("Testing Trinity Strategy evaluation...")
    payload = {
        'strategy_class': 'TrinityStrategy',
        'strategy_name': 'Trinity Manual Test'
    }
    
    try:
        result = worker._process_strategy_evaluation('manual-test-1', payload)
        print(f"✅ SUCCESS!")
        print(f"   Evaluation ID: {result.get('evaluation_id')}")
        print(f"   Excellence Score: {result.get('excellence_score'):.2f}")
        print(f"   Category: {result.get('strategy_category')}")
        
        # Verify it was saved to database
        evals = db.get_leaderboard(limit=1)
        if evals and evals[0]['strategy_name'] == 'Trinity Manual Test':
            print(f"✅ Found in leaderboard!")
        
        return 0
    
    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    # Run manual test
    sys.exit(manual_worker_test())
