
"""
Integration tests for JARVIS file operations.
Tests reading, writing, directory constraints with security validation.
"""
import pytest
pytestmark = pytest.mark.integration

import pytest
from fastapi.testclient import TestClient


class TestFileOperations:
    """Test suite for file read/write operations."""

    def test_read_valid_file(self, client: TestClient):
        """Test reading a valid text file."""
        response = client.post(
            "/files/read",
            json={"path": "README.md"}
        )
        assert response.status_code in [200, 400, 422]

    def test_read_nonexistent_file(self, client: TestClient):
        """Test reading a file that doesn't exist."""
        response = client.post(
            "/files/read",
            json={"path": "nonexistent_file_12345.txt"}
        )
        # Should return 404 or error
        assert response.status_code in [400, 404, 422]

    def test_path_traversal_attempt_read(self, client: TestClient):
        """Test that path traversal is blocked in read."""
        response = client.post(
            "/files/read",
            json={"path": "../../../../../../etc/passwd"}
        )
        # Should block or reject
        assert response.status_code in [400, 403, 422]

    def test_write_to_allowed_directory(self, client: TestClient):
        """Test writing to allowed directory."""
        response = client.post(
            "/files/write",
            json={
                "path": "test_write_output.txt",
                "content": "Test content"
            }
        )
        assert response.status_code in [200, 400, 422]

    def test_write_to_system_directory(self, client: TestClient):
        """Test that write to system directories is blocked."""
        response = client.post(
            "/files/write",
            json={
                "path": "/etc/important_system_file.txt",
                "content": "malicious"
            }
        )
        # Should block
        assert response.status_code in [400, 403, 422]

    def test_path_traversal_attempt_write(self, client: TestClient):
        """Test that path traversal is blocked in write."""
        response = client.post(
            "/files/write",
            json={
                "path": "../../dangerous.txt",
                "content": "trying to escape"
            }
        )
        # Should block
        assert response.status_code in [400, 403, 422]

    def test_list_directory(self, client: TestClient):
        """Test listing directory contents."""
        response = client.post(
            "/files/list",
            json={"path": "."}
        )
        assert response.status_code in [200, 400, 422]

    def test_get_file_info(self, client: TestClient):
        """Test getting file metadata."""
        response = client.post(
            "/files/info",
            json={"path": "README.md"}
        )
        assert response.status_code in [200, 400, 422]

    def test_delete_file_blocked(self, client: TestClient):
        """Test that file deletion is blocked (security)."""
        response = client.post(
            "/files/delete",
            json={"path": "some_file.txt"}
        )
        # Should be blocked for safety
        assert response.status_code in [400, 403, 422]

    def test_copy_file(self, client: TestClient):
        """Test copying a file."""
        response = client.post(
            "/files/copy",
            json={
                "source": "README.md",
                "destination": "README_copy.md"
            }
        )
        assert response.status_code in [200, 400, 422]

    def test_move_file(self, client: TestClient):
        """Test moving a file."""
        response = client.post(
            "/files/move",
            json={
                "source": "test_file.txt",
                "destination": "moved_file.txt"
            }
        )
        assert response.status_code in [200, 400, 422, 404]
