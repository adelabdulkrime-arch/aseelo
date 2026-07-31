"""Font discovery and resolution.

Arabic is a first-class language in ASEELO, so every resolved family must be
able to render Arabic. Families are addressed by stable slugs (stored on the
brand profile) and mapped to concrete TTF/OTF files found on the system.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.logging_config import get_logger

logger = get_logger(__name__)

SEARCH_DIRS = (
    Path(__file__).resolve().parents[2] / "assets" / "fonts",  # vendored (optional)
    Path("/usr/share/fonts"),
    Path("/usr/local/share/fonts"),
    Path("C:/Windows/Fonts"),
)

FONT_EXTENSIONS = {".ttf", ".otf", ".ttc"}


@dataclass(frozen=True)
class FontFamily:
    slug: str
    label: str
    label_ar: str
    regular: str
    bold: str
    supports_arabic: bool = True


# Ordered by preference: the first family whose files exist becomes the default.
FAMILIES: tuple[FontFamily, ...] = (
    FontFamily(
        slug="noto-sans-arabic",
        label="Noto Sans Arabic",
        label_ar="نوتو سانس عربي",
        regular="NotoSansArabic-Regular",
        bold="NotoSansArabic-Bold",
    ),
    FontFamily(
        slug="noto-kufi-arabic",
        label="Noto Kufi Arabic",
        label_ar="نوتو كوفي عربي",
        regular="NotoKufiArabic-Regular",
        bold="NotoKufiArabic-Bold",
    ),
    FontFamily(
        slug="amiri",
        label="Amiri",
        label_ar="أميري",
        regular="Amiri-Regular",
        bold="Amiri-Bold",
    ),
    FontFamily(
        slug="dejavu-sans",
        label="DejaVu Sans",
        label_ar="ديجافو سانس",
        regular="DejaVuSans",
        bold="DejaVuSans-Bold",
        supports_arabic=False,
    ),
)

FAMILY_BY_SLUG = {family.slug: family for family in FAMILIES}


@lru_cache
def _font_index() -> dict[str, Path]:
    """Map lowercase font file stems to their paths (built once per process)."""
    index: dict[str, Path] = {}
    for directory in SEARCH_DIRS:
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if path.suffix.lower() in FONT_EXTENSIONS and path.is_file():
                index.setdefault(path.stem.lower(), path)
    logger.info("font_index_built", extra={"font_files": len(index)})
    return index


def _find(stem: str) -> Path | None:
    index = _font_index()
    if hit := index.get(stem.lower()):
        return hit
    # Tolerate naming variants such as "NotoSansArabic-Regular[wdth,wght]".
    needle = stem.lower().replace("-", "")
    for key, path in index.items():
        if key.replace("-", "").replace("_", "").startswith(needle):
            return path
    return None


def _fc_match(pattern: str) -> Path | None:
    """Ask fontconfig for a file as a last resort."""
    try:
        out = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["fc-match", "-f", "%{file}", pattern],  # noqa: S607 - resolved via PATH
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    candidate = out.stdout.decode("utf-8", "replace").strip()
    if candidate and Path(candidate).is_file():
        return Path(candidate)
    return None


@lru_cache
def _codepoints(path: str) -> frozenset[int]:
    """Every codepoint the font file can actually render."""
    from fontTools.ttLib import TTFont

    try:
        font = TTFont(path, fontNumber=0, lazy=True)
    except Exception as exc:  # noqa: BLE001 - an unreadable font is simply unusable
        logger.warning("font_cmap_unreadable", extra={"font_path": path, "error": str(exc)})
        return frozenset()
    try:
        return frozenset(font.getBestCmap())
    except Exception:  # noqa: BLE001
        return frozenset()
    finally:
        font.close()


def covers(path: Path, text: str) -> bool:
    """True when ``path`` has a glyph for every non-space character in ``text``."""
    cmap = _codepoints(str(path))
    if not cmap:
        return False
    return all(ord(ch) in cmap for ch in text if not ch.isspace())


@lru_cache
def _candidate_paths(slug: str | None, bold: bool) -> tuple[Path, ...]:
    """Concrete font files to try for a family slug, best match first."""
    ordered: list[FontFamily] = []
    if slug and slug in FAMILY_BY_SLUG:
        ordered.append(FAMILY_BY_SLUG[slug])
    ordered.extend(f for f in FAMILIES if f not in ordered)

    paths: list[Path] = []
    for family in ordered:
        for stem in ((family.bold, family.regular) if bold else (family.regular, family.bold)):
            if (found := _find(stem)) and found not in paths:
                paths.append(found)

    for pattern in ("Noto Sans Arabic", "Arabic", "sans-serif"):
        if (found := _fc_match(pattern)) and found not in paths:
            paths.append(found)
    return tuple(paths)


def resolve_font(slug: str | None, *, bold: bool = False, text: str | None = None) -> Path:
    """Resolve a family slug to a concrete font file.

    Pillow does no font fallback: a glyph the chosen file lacks renders as tofu.
    The Arabic-only Noto families have no Latin coverage, so when ``text`` is
    given we pick the first candidate that covers the whole string - which is
    what keeps mixed Arabic/English headlines readable.
    """
    candidates = _candidate_paths(slug, bold)
    if not candidates:
        raise RuntimeError(f"No usable font found for slug {slug!r}")

    if text:
        for path in candidates:
            if covers(path, text):
                return path
        logger.warning(
            "no_font_covers_text", extra={"font_slug": slug, "candidates": len(candidates)}
        )
    return candidates[0]


@lru_cache
def default_family_slug() -> str:
    for family in FAMILIES:
        if _find(family.regular):
            return family.slug
    return FAMILIES[0].slug


def available_families() -> list[dict[str, object]]:
    """Families installed in this environment, for the brand-profile picker."""
    result = []
    for family in FAMILIES:
        if _find(family.regular) or _find(family.bold):
            result.append(
                {
                    "slug": family.slug,
                    "label": family.label,
                    "label_ar": family.label_ar,
                    "supports_arabic": family.supports_arabic,
                }
            )
    return result
