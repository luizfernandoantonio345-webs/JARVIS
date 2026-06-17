
"""
Sentinel regression tests.
Protects scanner behavior against accidental pattern regressions.
"""
from __future__ import annotations
import pytest
pytestmark = pytest.mark.integration


import sys
from pathlib import Path

# Ensure backend is on path
_BACKEND = Path(__file__).parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def test_sentinel_detects_real_secret_and_ignores_comments(monkeypatch, tmp_path) -> None:
    from autonomy_v2 import event_detector as sentinel

    monkeypatch.setattr(sentinel, "WATCH_PATH", tmp_path)

    code_file = tmp_path / "sample.py"
    code_file.write_text(
        "# password = 'fake_comment_secret'\n"
        "password = None\n"
        "api_key = 'real-secret-12345'\n",
        encoding="utf-8",
    )

    findings = sentinel.scan_file(code_file)

    # Must detect the real api_key assignment
    assert any(f["pattern"] == "hardcoded_secret" for f in findings)

    # Must not detect commented or benign placeholder values
    assert not any("fake_comment_secret" in f["snippet"] for f in findings)
    assert not any("password = None" in f["snippet"] for f in findings)


def test_sentinel_skips_test_files(monkeypatch, tmp_path) -> None:
    from autonomy_v2 import event_detector as sentinel

    monkeypatch.setattr(sentinel, "WATCH_PATH", tmp_path)

    test_file = tmp_path / "auth_test.py"
    test_file.write_text("token = 'secret-in-test-file'\n", encoding="utf-8")

    findings = sentinel.scan_file(test_file)
    assert findings == []
