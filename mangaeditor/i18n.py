"""Interface language support (Turkish and English).

Source strings in the code are Turkish. ``tr(text)`` returns the English
translation (from ``translations.EN``) when the active language is English,
and the text unchanged when it is Turkish. Missing translations fall back to
the Turkish source text, so a gap never breaks the UI.

Language selection:
  * On first start the language follows the Windows language (Turkish → "tr",
    anything else → "en").
  * The user can change it in Settings → Language. The change takes effect
    after restarting the application.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QLocale, QSettings

LANGUAGES: dict[str, str] = {"tr": "Türkçe", "en": "English"}
SETTINGS_KEY = "language"
DEFAULT_LANGUAGE = "tr"  # used when nothing is selected and no detection is done (tests)

_current = DEFAULT_LANGUAGE
_table: dict[str, str] | None = None


def detect_language() -> str:
    """Language from the operating system: Turkish → "tr", otherwise "en"."""
    try:
        name = QLocale.system().name()  # e.g. "tr_TR" or "en_US"
    except Exception:  # pragma: no cover - defensive
        return "en"
    return "tr" if name[:2].lower() == "tr" else "en"


def _load_table() -> dict[str, str]:
    global _table
    if _table is None:
        from .translations import EN

        _table = EN
    return _table


def init(settings: QSettings | None) -> str:
    """Pick the active language: saved choice first, otherwise system detection."""
    global _current
    saved = settings.value(SETTINGS_KEY, "", type=str) if settings is not None else ""
    _current = saved if saved in LANGUAGES else detect_language()
    return _current


def current() -> str:
    return _current


def set_language(code: str, settings: QSettings | None) -> None:
    """Store the choice. It is applied on the next start."""
    if code not in LANGUAGES:
        raise ValueError(f"Unknown language: {code}")
    if settings is not None:
        settings.setValue(SETTINGS_KEY, code)
        settings.sync()


def saved_language(settings: QSettings | None) -> str | None:
    if settings is None:
        return None
    value = settings.value(SETTINGS_KEY, "", type=str)
    return value if value in LANGUAGES else None


def force(code: str) -> None:
    """Set the language directly (used by tests and the language switch preview)."""
    global _current
    if code not in LANGUAGES:
        raise ValueError(f"Unknown language: {code}")
    _current = code


def tr_in(code: str, text: str) -> str:
    """Translate a source string into a given language (no placeholder filling)."""
    if code == "tr" or not text:
        return text
    return _load_table().get(text, text)


def tr(text: str, **values: Any) -> str:
    """Translate a source string for the active language and fill ``{placeholders}``."""
    out = tr_in(_current, text)
    return out.format(**values) if values else out
