"""PPT semantic fidelity and deterministic animation mapping."""

from .models import FidelityPolicy, SlideFidelityManifest
from .scanner import PptxFidelityScanner

__all__ = ["FidelityPolicy", "PptxFidelityScanner", "SlideFidelityManifest"]
