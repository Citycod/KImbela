import signal
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo


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


def test_ai_activity_startup_time_is_aware_and_one_minute_from_now():
    from scheduler import ai_activity_startup_time

    scheduler_timezone = ZoneInfo("UTC")
    before = datetime.now(timezone.utc)
    scheduled = ai_activity_startup_time(scheduler_timezone)
    after = datetime.now(timezone.utc)

    assert scheduled.tzinfo is not None
    assert scheduled.utcoffset() is not None
    assert before + timedelta(seconds=59) <= scheduled
    assert scheduled <= after + timedelta(seconds=61)


def test_ai_activity_startup_time_preserves_absolute_time_across_dst_offsets():
    from scheduler import ai_activity_startup_time

    scheduler_timezone = ZoneInfo("Europe/Zurich")
    utc = ZoneInfo("UTC")
    summer_now = datetime(2026, 7, 1, 9, 45, tzinfo=utc)
    winter_now = datetime(2026, 12, 1, 9, 45, tzinfo=utc)

    summer_run = ai_activity_startup_time(scheduler_timezone, now=summer_now)
    winter_run = ai_activity_startup_time(scheduler_timezone, now=winter_now)

    assert summer_run.utcoffset() == timedelta(hours=2)
    assert winter_run.utcoffset() == timedelta(hours=1)
    assert summer_run.astimezone(utc) == summer_now + timedelta(minutes=1)
    assert winter_run.astimezone(utc) == winter_now + timedelta(minutes=1)


def test_production_ai_job_uses_aware_scheduler_local_start_time(
    app, monkeypatch
):
    import scheduler as scheduler_module

    scheduler_timezone = ZoneInfo("Europe/Zurich")
    monkeypatch.setattr(scheduler_module, "scheduler", None)
    monkeypatch.setattr(scheduler_module, "get_localzone", lambda: scheduler_timezone)
    monkeypatch.setattr(
        "utils.ai_group_membership.sync_ai_group_memberships", lambda: 0
    )
    previous_testing = app.config["TESTING"]
    app.config["TESTING"] = False
    before = datetime.now(timezone.utc)
    scheduler_instance = scheduler_module.init_scheduler(app)
    try:
        job = scheduler_instance.get_job("ai_persona_activity")
        scheduled = job.next_run_time
        after = datetime.now(timezone.utc)

        assert scheduler_instance.timezone == scheduler_timezone
        assert scheduled.tzinfo is not None
        assert scheduled.utcoffset() is not None
        assert before + timedelta(seconds=59) <= scheduled.astimezone(timezone.utc)
        assert scheduled.astimezone(timezone.utc) <= after + timedelta(seconds=61)
        assert job.trigger.interval == timedelta(hours=24)
        assert job.max_instances == 1
        assert job.coalesce is True
    finally:
        scheduler_instance.shutdown(wait=True)
        scheduler_module.scheduler = None
        app.config["TESTING"] = previous_testing


def test_testing_mode_does_not_force_production_startup_time(app, monkeypatch):
    import scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module, "scheduler", None)
    startup_time = Mock(side_effect=AssertionError("must not run in testing mode"))
    monkeypatch.setattr(scheduler_module, "ai_activity_startup_time", startup_time)
    monkeypatch.setattr(
        "utils.ai_group_membership.sync_ai_group_memberships", lambda: 0
    )

    scheduler_instance = scheduler_module.init_scheduler(app)
    try:
        job = scheduler_instance.get_job("ai_persona_activity")
        assert job.trigger.interval == timedelta(hours=24)
        startup_time.assert_not_called()
    finally:
        scheduler_instance.shutdown(wait=True)
        scheduler_module.scheduler = None


def test_registered_ai_job_calls_the_bounded_activity_pass(app, monkeypatch):
    import scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module, "scheduler", None)
    monkeypatch.setattr(
        "utils.ai_group_membership.sync_ai_group_memberships", lambda: 0
    )
    activity_pass = Mock(return_value={"group_slots_completed": 1})
    monkeypatch.setattr(scheduler_module, "run_ai_persona_activity_once", activity_pass)

    scheduler_instance = scheduler_module.init_scheduler(app)
    try:
        result = scheduler_instance.get_job("ai_persona_activity").func()
        assert result == {"group_slots_completed": 1}
        activity_pass.assert_called_once_with(app)
    finally:
        scheduler_instance.shutdown(wait=True)
        scheduler_module.scheduler = None


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
