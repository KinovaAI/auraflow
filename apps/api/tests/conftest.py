"""
AuraFlow — Shared Test Configuration

Common settings applied to all tests (unit and integration).
"""
import os
import sys
from pathlib import Path

# Ensure the project root (parent of tests/) is on sys.path so 'app' package is importable
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Set test environment before any app imports (preserve existing env vars for Docker)
os.environ.setdefault("DATABASE_URL", "postgresql://auraflow:1d50a904518d74c94260bc57c66a7ca5dffc58359c4b4b6653605241bf043fed@localhost:5432/auraflow")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("APP_SECRET", "test-secret-not-for-production-use-only")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("SENDGRID_API_KEY", "")


def auth_header(token: str) -> dict:
    """Helper to build Authorization header."""
    return {"Authorization": f"Bearer {token}"}
