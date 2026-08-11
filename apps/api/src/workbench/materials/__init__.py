"""Versioned material collections for flexible document and presentation input."""

from .models import MaterialCollection, MaterialPageRef, MaterialSection
from .service import MaterialCollectionError, MaterialCollectionService

__all__ = [
    "MaterialCollection",
    "MaterialCollectionError",
    "MaterialCollectionService",
    "MaterialPageRef",
    "MaterialSection",
]
