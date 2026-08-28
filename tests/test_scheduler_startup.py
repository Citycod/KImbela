import signal
import threading
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock


class FakeApp:
    def __init__(self):
        self.context_entries = 0

    @contextmanager
    def app_context(self):
        self.context_entries += 1
        yield


def test_scheduler_process_starts_once_and_shuts_down_cleanly():
    from scheduler import run_scheduler_process

    app = FakeApp()
    stop_event = threading.Event()
    stop_event.set()
    scheduler_instance = SimpleNamespace(running=True, shutdown=Mock())
    initializer = Mock(return_value=scheduler_instance)

    run_scheduler_process(
        app,
        stop_event=stop_event,
        scheduler_initializer=initializer,
    )

    initializer.assert_called_once_with(app)
    assert app.context_entries == 1
    scheduler_instance.shutdown.assert_called_once_with(wait=True)


def test_sigterm_and_sigint_request_clean_shutdown():
    from scheduler import _install_shutdown_signal_handlers, _restore_signal_handlers

    stop_event = threading.Event()
    previous_handlers = _install_shutdown_signal_handlers(stop_event)
    try:
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        assert stop_event.is_set()

        stop_event.clear()
        signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
        assert stop_event.is_set()
    finally:
        _restore_signal_handlers(previous_handlers)


def test_init_scheduler_prevents_duplicate_startup(app, monkeypatch):
    import scheduler as scheduler_module

    running_scheduler = SimpleNamespace(running=True)
    monkeypatch.setattr(scheduler_module, "scheduler", running_scheduler)
    constructor = Mock(side_effect=AssertionError("must not create a second scheduler"))
    monkeypatch.setattr(scheduler_module, "BackgroundScheduler", constructor)

    assert scheduler_module.init_scheduler(app) is running_scheduler
    constructor.assert_not_called()


def test_dedicated_scheduler_registers_both_birthday_jobs(app, monkeypatch):
    import scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module, "scheduler", None)
    scheduler_instance = scheduler_module.init_scheduler(app)
    try:
        job_ids = {job.id for job in scheduler_instance.get_jobs()}
        assert "birthday_web_pushes" in job_ids
        assert "birthday_in_app_notifications" in job_ids
        assert scheduler_module.init_scheduler(app) is scheduler_instance
    finally:
        scheduler_instance.shutdown(wait=True)
        scheduler_module.scheduler = None


def test_web_app_factory_does_not_start_scheduler(monkeypatch):
    import app_config
    import scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module, "scheduler", None)

    app_config.create_app()

    assert scheduler_module.scheduler is None


def test_main_uses_factory_created_app_once(monkeypatch):
    import app_config
    import scheduler as scheduler_module

    runner = Mock()
    monkeypatch.setattr(scheduler_module, "run_scheduler_process", runner)

    assert scheduler_module.main() == 0
    runner.assert_called_once_with(app_config.app)
