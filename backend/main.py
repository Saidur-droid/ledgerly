"""Render compatibility entry point.

The canonical application lives at ``app.main:app``. Re-exporting it here keeps
manually created Render services that still invoke ``main:app`` operational
while the Blueprint uses the canonical import path.
"""

from app.main import app

__all__ = ["app"]
