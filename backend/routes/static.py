"""
Static file serving routes for JARVIS frontend.
Serves dashboard HTML and assets.
"""
from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse
from pathlib import Path

router = APIRouter()

STATIC_DIR = Path(__file__).parent.parent / "static"


@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve main dashboard HTML."""
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return """
        <html>
            <head><title>JARVIS Dashboard</title></head>
            <body>
                <h1>Dashboard not configured</h1>
                <p>Please configure static files in backend/static/</p>
            </body>
        </html>
        """
    return FileResponse(index_path)


@router.get("/api/frontend/config")
async def get_frontend_config():
    """Return runtime configuration for frontend."""
    return {
        "ws_url": "ws://localhost:8000/ws/jarvis",
        "api_base": "http://localhost:8000",
        "version": "5.2",
        "features": {
            "chat": True,
            "voice": True,
            "autonomy": True,
            "memory": True
        }
    }


@router.get("/status")
async def frontend_status():
    """Frontend health/status endpoint."""
    return {
        "status": "ok",
        "message": "Dashboard service running"
    }
