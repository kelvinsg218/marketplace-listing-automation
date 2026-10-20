"""Retries of one automation step: timeouts and network failures are retried; other browser errors are not."""
import pytest
from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeout

from mla.automation.base import StepError
from mla.automation.executor import ExecutionManager
from mla.automation.queue import QueueManager


class _Logger:
    def __init__(self):
        self.warnings = []

    def warning(self, message):
        self.warnings.append(message)

    def info(self, message):
        pass

    def screenshot(self, *args, **kwargs):
        pass


class _Adapter:
    page = None

    def check_blockers(self):
        pass


@pytest.fixture
def executor(ctx):
    return ExecutionManager(ctx, QueueManager(ctx.automation_repo, ctx.products, ctx.accounts))


def _flaky(errors):
    calls = {"n": 0}

    def action():
        calls["n"] += 1
        if calls["n"] <= len(errors):
            raise errors[calls["n"] - 1]
    return action, calls


def test_network_drop_is_retried_and_recovers(executor):
    action, calls = _flaky([PlaywrightError("net::ERR_INTERNET_DISCONNECTED at https://exemplo"),
                            PlaywrightTimeout("Timeout 30000ms exceeded")])
    logger = _Logger()
    executor._attempt(None, logger, _Adapter(), action)
    assert calls["n"] == 3 and len(logger.warnings) == 2


def test_persistent_network_failure_is_reported_as_such(executor):
    action, calls = _flaky([PlaywrightError("net::ERR_NAME_NOT_RESOLVED")] * 5)
    with pytest.raises(StepError, match="falha de rede") as info:
        executor._attempt(None, _Logger(), _Adapter(), action)
    assert calls["n"] == 3 and not info.value.retryable  # 1 attempt + 2 retries (default setting)


def test_other_browser_errors_are_not_retried(executor):
    action, calls = _flaky([PlaywrightError("Target page, context or browser has been closed")])
    with pytest.raises(PlaywrightError):
        executor._attempt(None, _Logger(), _Adapter(), action)
    assert calls["n"] == 1


def test_non_retryable_step_error_stops_at_once(executor):
    action, calls = _flaky([StepError("Campo obrigatório ausente.", retryable=False)])
    with pytest.raises(StepError):
        executor._attempt(None, _Logger(), _Adapter(), action)
    assert calls["n"] == 1
