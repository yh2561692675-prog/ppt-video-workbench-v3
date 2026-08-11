"""Launcher shim; the importable implementation lives in ``cloud_prototype``."""

from cloud_prototype.app import CloudRepository, create_cloud_app

__all__ = ["CloudRepository", "create_cloud_app"]
