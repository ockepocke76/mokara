"""
Tests for performance instrumentation.

TimingContext, the tracker context managers and the checkpoint tracker log
locally; the Cloud Monitoring export layer was removed in R4 (the module it
imported never existed in this repo, so it was permanently self-disabled).
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from utils.performance import (
    TimingContext,
    PageLoadTracker,
    DatabaseQueryTracker,
    ComponentRenderTracker,
    PerformanceTracker,
    _config_value,
)


def test_timing_context_basic():
    with TimingContext("test_operation"):
        time.sleep(0.01)
    # Should complete without errors


def test_trackers_complete_without_errors():
    with PageLoadTracker("TestPage"):
        time.sleep(0.01)
    with DatabaseQueryTracker("get_user_simulations", "SELECT"):
        time.sleep(0.01)
    with ComponentRenderTracker("test_component"):
        time.sleep(0.01)


def test_trackers_survive_body_exceptions():
    with pytest.raises(ValueError):
        with PageLoadTracker("FailingPage"):
            raise ValueError("boom")


def test_performance_tracker_checkpoints():
    tracker = PerformanceTracker("test_operation")

    time.sleep(0.01)
    tracker.checkpoint("step1")

    time.sleep(0.01)
    tracker.checkpoint("step2")

    tracker.log_summary()

    assert len(tracker.checkpoints) == 2
    assert tracker.checkpoints[0]['name'] == 'step1'
    assert tracker.checkpoints[1]['name'] == 'step2'


def test_config_value_reads_nested_value_keys():
    # config.yml stores flags as {description, value} nodes
    assert _config_value('monitoring.slow_query_threshold', -1) == 1.0
    assert _config_value('monitoring.enable_memory_tracking', True) is False
    # Unknown path falls back to the default
    assert _config_value('nope.not_here', 'fallback') == 'fallback'


def test_database_logging_decorator():
    from db.logging_utils import log_db_call

    @log_db_call
    def mock_db_method(self):
        time.sleep(0.01)
        return "result"

    mock_self = MagicMock()
    with patch('db.logging_utils.DB_LOGGING_ENABLED', True):
        assert mock_db_method(mock_self) == "result"


def test_no_performance_overhead_when_disabled():
    iterations = 100
    sleep_time = 0.001

    start = time.time()
    for _ in range(iterations):
        time.sleep(sleep_time)
    baseline = time.time() - start

    with patch('utils.performance._is_perf_enabled', return_value=False):
        start = time.time()
        for _ in range(iterations):
            with TimingContext("test"):
                time.sleep(sleep_time)
        instrumented = time.time() - start

    overhead_pct = ((instrumented - baseline) / baseline) * 100
    assert overhead_pct < 20.0, f"Overhead: {overhead_pct:.2f}%"
