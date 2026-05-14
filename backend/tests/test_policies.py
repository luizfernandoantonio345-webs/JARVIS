from autonomy.policy_engine import Event, PolicyDecision, PolicyEngine


def test_idle_detected_allows_daily_briefing():
    engine = PolicyEngine()
    assert engine.evaluate(Event("idle_detected", {"idle_seconds": 301, "safe_mode": True})) == PolicyDecision.ALLOW


def test_file_changed_allows_linter_for_source_files():
    engine = PolicyEngine()
    assert engine.evaluate(Event("file_changed", {"file": "backend/main.py"})) == PolicyDecision.ALLOW


def test_repeated_error_notifies_owner():
    engine = PolicyEngine()
    assert engine.evaluate(Event("error_in_log", {"severity": "ERROR", "repeated": 4})) == PolicyDecision.ALLOW


def test_disk_above_90_notifies_owner():
    engine = PolicyEngine()
    assert engine.evaluate(Event("disk_above_90pct", {"disk_usage": 91})) == PolicyDecision.ALLOW


def test_auto_commit_requires_confirmation():
    engine = PolicyEngine()
    assert engine.evaluate(Event("auto_commit", {})) == PolicyDecision.REQUIRE_CONFIRMATION


def test_delete_files_is_denied():
    engine = PolicyEngine()
    assert engine.evaluate(Event("delete_files", {})) == PolicyDecision.DENY
