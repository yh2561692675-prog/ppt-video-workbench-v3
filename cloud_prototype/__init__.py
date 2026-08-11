"""Isolated cloud collaboration control-plane prototype.

This package is intentionally not imported by the desktop application.  It is
an executable contract prototype for the future cloud service boundary.
"""

from .app import create_cloud_app

__all__ = ["create_cloud_app"]
