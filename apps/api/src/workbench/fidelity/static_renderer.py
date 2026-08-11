from __future__ import annotations

from pathlib import Path

from workbench.renderers.office_renderer import OfficeRendererError, build_pptx_previews


def build_static_previews(source: Path, output: Path) -> list[Path]:
    """Use the existing isolated Office renderer when available.

    Missing LibreOffice/fonts are a capability downgrade, not a reason to
    discard the semantic scene extracted by the fidelity scanner.
    """

    try:
        result = build_pptx_previews(source, output)
    except OfficeRendererError:
        return []
    return [page.preview_path for page in result.pages if page.preview_path is not None]
