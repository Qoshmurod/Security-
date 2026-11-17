"""Translations for everything Qorovul says to people.

Translated: Telegram messages, check results, and the output of
``qorovul test`` and ``qorovul status``.  Journal logs and configuration
errors stay in English on purpose - they are searched for and pasted into
bug reports, where one shared wording helps.

Each language lives in ``qorovul/locales/<code>.py`` and defines:

    NAME            the language's own name
    MESSAGES        message id -> template using {named} placeholders
    DECIMAL         decimal mark (default ".")
    PERCENT         percent pattern (default "{n}%")
    SIZE_UNITS      byte units, B..TB (default B KB MB GB TB)
    DURATION_UNITS  suffixes for days/hours/minutes/seconds
    DURATION_JOIN   separator between duration parts (default " ")
    LIST_SEP        separator when joining details (default ", ")

Any message a locale does not define falls back to English, so a partly
translated language still works.  Messages are written so that no plural
forms are needed ("days left: 3"), which keeps every language correct.
"""

import importlib
import os
import unicodedata
from typing import Dict, List, Mapping, Optional, Sequence

# English first; the rest roughly by number of speakers in the region the
# project started in, then world-wide.
LANGUAGES = ("en", "uz", "ru", "tr", "ko", "zh", "ja", "es", "pt", "fr", "de", "ar", "hi", "id")
DEFAULT_LANGUAGE = "en"
AUTO = "auto"


class Translator:
    """Formats messages, numbers, sizes and durations for one language."""

    def __init__(self, language: str = DEFAULT_LANGUAGE) -> None:
        if language not in LANGUAGES:
            raise ValueError("unsupported language %r (supported: %s)"
                             % (language, ", ".join(LANGUAGES)))
        base = importlib.import_module("qorovul.locales.en")
        loc = importlib.import_module("qorovul.locales." + language)
        self.language = language
        self.name: str = loc.NAME
        self.messages: Dict[str, str] = dict(base.MESSAGES)
        self.messages.update(loc.MESSAGES)
        self.decimal: str = getattr(loc, "DECIMAL", ".")
        self.percent_pattern: str = getattr(loc, "PERCENT", "{n}%")
        self.size_units: List[str] = list(getattr(loc, "SIZE_UNITS", base.SIZE_UNITS))
        self.duration_units: Dict[str, str] = dict(
            getattr(loc, "DURATION_UNITS", base.DURATION_UNITS))
        self.duration_join: str = getattr(loc, "DURATION_JOIN", " ")
        self.list_sep: str = getattr(loc, "LIST_SEP", ", ")

    def __call__(self, key: str, **params: object) -> str:
        return self.messages[key].format(**params)

    def __repr__(self) -> str:
        return "Translator(%r)" % self.language

    # ------------------------------------------------------------ formatting

    def number(self, value: float, digits: int = 1) -> str:
        text = "%.*f" % (digits, value)
        return text.replace(".", self.decimal) if self.decimal != "." else text

    def percent(self, value: float) -> str:
        return self.percent_pattern.format(n=self.number(value))

    def size(self, nbytes: float) -> str:
        n = float(nbytes)
        units = self.size_units
        for i, unit in enumerate(units):
            if abs(n) < 1024 or i == len(units) - 1:
                if i == 0:
                    return "%d %s" % (n, unit)
                return "%s %s" % (self.number(n), unit)
            n /= 1024.0
        raise AssertionError("unreachable")  # pragma: no cover

    def duration(self, seconds: Optional[float]) -> str:
        if seconds is None:
            return "?"
        seconds = int(max(0, seconds))
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, secs = divmod(rem, 60)
        u = self.duration_units
        if days:
            parts = [(days, "d"), (hours, "h")]
        elif hours:
            parts = [(hours, "h"), (minutes, "m")]
        elif minutes:
            parts = [(minutes, "m")]
        else:
            parts = [(secs, "s")]
        return self.duration_join.join("%d%s" % (n, u[k]) for n, k in parts)

    def severity(self, severity: str) -> str:
        return self("severity." + severity)

    def join(self, parts: Sequence[str]) -> str:
        return self.list_sep.join(parts)


_CACHE: Dict[str, Translator] = {}


def get_translator(language: str = DEFAULT_LANGUAGE) -> Translator:
    """Shared, cached translator for a language code."""
    tr = _CACHE.get(language)
    if tr is None:
        tr = _CACHE[language] = Translator(language)
    return tr


def detect_language(env: Optional[Mapping[str, str]] = None) -> str:
    """Language from the POSIX locale variables, or English.

    The first of LC_ALL, LC_MESSAGES, LANG that is set decides, as in libc;
    "ru_RU.UTF-8" gives "ru", "C" or an unsupported language gives "en".
    """
    env = os.environ if env is None else env
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = (env.get(var) or "").strip()
        if value:
            code = value.split(".")[0].split("@")[0].split("_")[0].lower()
            return code if code in LANGUAGES else DEFAULT_LANGUAGE
    return DEFAULT_LANGUAGE


def resolve_language(value: str, env: Optional[Mapping[str, str]] = None) -> str:
    return detect_language(env) if value == AUTO else value


# --------------------------------------------------------------- text layout

def display_width(text: str) -> int:
    """Terminal columns used by text (CJK characters take two)."""
    width = 0
    for ch in text:
        if unicodedata.combining(ch):
            continue
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def ljust(text: str, width: int) -> str:
    """str.ljust that counts display columns instead of characters."""
    return text + " " * max(0, width - display_width(text))


EN = get_translator(DEFAULT_LANGUAGE)
