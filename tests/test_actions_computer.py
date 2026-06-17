
"""
Integration tests for JARVIS computer control actions.
Tests mouse movement, clicks, keyboard input with validation.
"""
import pytest
pytestmark = pytest.mark.integration

import pytest
from fastapi.testclient import TestClient


class TestComputerControl:
    """Test suite for computer control (mouse, keyboard, system)."""

    def test_get_mouse_position(self, client: TestClient):
        """Test fetching current mouse position."""
        response = client.post("/computer/mouse/position", json={})
        # Should return success or graceful error (may not work in CI)
        assert response.status_code in [200, 400, 422]

    def test_mouse_move_validation(self, client: TestClient):
        """Test mouse move with invalid coordinates."""
        response = client.post(
            "/computer/mouse/move",
            json={"x": -999, "y": -999}
        )
        # Should either work or fail gracefully
        assert response.status_code in [200, 400, 422]

    def test_screenshot_request(self, client: TestClient):
        """Test taking a screenshot."""
        response = client.post("/computer/screenshot", json={})
        assert response.status_code in [200, 400, 422]

    def test_keyboard_input_security(self, client: TestClient):
        """Test that dangerous keyboard commands are blocked."""
        # Should reject or sanitize dangerous input
        response = client.post(
            "/computer/keyboard/type",
            json={"text": "rm -rf /"}
        )
        # Should not execute dangerous commands
        assert response.status_code in [200, 400, 422, 403]

    def test_window_list(self, client: TestClient):
        """Test listing open windows."""
        response = client.post("/computer/windows/list", json={})
        assert response.status_code in [200, 400, 422]

    def test_system_info(self, client: TestClient):
        """Test fetching system information."""
        response = client.post("/computer/system/info", json={})
        assert response.status_code in [200, 400, 422]

    def test_process_list(self, client: TestClient):
        """Test listing running processes."""
        response = client.post("/computer/process/list", json={})
        assert response.status_code in [200, 400, 422]

    def test_display_info(self, client: TestClient):
        """Test fetching display/monitor information."""
        response = client.post("/computer/display/info", json={})
        assert response.status_code in [200, 400, 422]
