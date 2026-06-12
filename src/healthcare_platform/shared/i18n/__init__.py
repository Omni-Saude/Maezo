"""Internationalization framework with gettext/babel integration.

Provides _() translation function for all user-facing messages.
Default locale: pt_BR (Brazilian Portuguese).
"""
from __future__ import annotations

import gettext
import os
from pathlib import Path
from typing import Any

# Locale directory relative to project root
_LOCALE_DIR = Path(__file__).resolve().parents[3] / "locale"
_DEFAULT_DOMAIN = "messages"
_DEFAULT_LOCALE = "pt_BR"

_translations: dict[str, gettext.GNUTranslations | gettext.NullTranslations] = {}
_current_locale: str = _DEFAULT_LOCALE


def _load_translations(locale: str) -> gettext.GNUTranslations | gettext.NullTranslations:
    """Load translations for the given locale."""
    if locale in _translations:
        return _translations[locale]
    try:
        trans = gettext.translation(
            _DEFAULT_DOMAIN,
            localedir=str(_LOCALE_DIR),
            languages=[locale],
        )
    except FileNotFoundError:
        trans = gettext.NullTranslations()
    _translations[locale] = trans
    return trans


def set_locale(locale: str) -> None:
    """Set the active locale for translations."""
    global _current_locale
    _current_locale = locale
    _load_translations(locale)


def get_locale() -> str:
    """Get the current active locale."""
    return _current_locale


def _(message: str) -> str:
    """Translate a message using the current locale.

    Usage:
        from healthcare_platform.shared.i18n import _
        raise ValueError(_("Código de procedimento inválido"))
    """
    trans = _load_translations(_current_locale)
    return trans.gettext(message)


def ngettext(singular: str, plural: str, n: int) -> str:
    """Translate with plural forms."""
    trans = _load_translations(_current_locale)
    return trans.ngettext(singular, plural, n)


# Initialize default locale on import
set_locale(_DEFAULT_LOCALE)
