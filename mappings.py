"""Deterministic normalization and SIDA option-label mappings."""

from __future__ import annotations

import re
import unicodedata

from errors import UnknownMappingError


_DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"
)
_SPACE_RE = re.compile(r"\s+")


def normalize_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value)).translate(_DIGIT_TRANSLATION)
    text = text.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")
    text = _SPACE_RE.sub(" ", text).strip()
    return text or None


EDUCATION_MAP = {
    "بیسواد": "بیسواد",
    "تحصیلات قدیم": "تحصیلات قدیم",
    "مقدماتی نهضت": "مقدماتی نهضت",
    "لیسانس": "لیسانس",
    "دیپلم": "دیپلم متوسطه",
    "دیپلم متوسطه": "دیپلم متوسطه",
    "ابتدایی": "ابتدایی",
    "سیکل": "راهنمایی سیکل",
    "راهنمایی سیکل": "راهنمایی سیکل",
    "فوق دیپلم": "فوق دیپلم",
    "فوق لیسانس": "فوق لیسانس",
    "دکتری": "دکتری",
    "تحصیلات حوزوی": "تحصیلات حوزوی",
    "هنوز دانش آموز است": "هنوز دانش آموز است",
}


def map_education(value: object | None) -> str | None:
    normalized = normalize_text(value)
    if normalized is None:
        return None
    try:
        return EDUCATION_MAP[normalized]
    except KeyError as exc:
        raise UnknownMappingError(
            f"No approved education mapping for value: {normalized!r}"
        ) from exc


def map_job(value: object | None) -> str:
    normalized = normalize_text(value)
    if normalized in (None, "آزاد"):
        return "آزاد تجاری"
    return normalized


FIXED_OPTIONS = {
    "guardian": "پدر",
    "religion": "مسلمان",
    "madhab": "اهل تسنن - شافعی",
    "family_type": "فاقد عناوین ایثارگری",
    "physical_status": "سالم",
    "housing_status": "شخصی - با خانواده",
    "parent_life_status": "در قید حیات",
}

DEFAULT_FATHER_EDUCATION = "دیپلم"
DEFAULT_MOTHER_EDUCATION = "لیسانس"


def resolve_mother_phone(value: object | None) -> str:
    """Return a required 10-digit mobile number without its leading zero."""
    normalized = normalize_text(value)
    if normalized is None:
        raise ValueError("Mother mobile is required")
    if normalized.startswith("0") and len(normalized) == 11:
        normalized = normalized[1:]
    if len(normalized) != 10 or not normalized.isdigit():
        raise ValueError("Mother mobile must be 10 digits without the leading zero")
    return normalized


def map_family_type(value: object | None) -> str:
    normalized = normalize_text(value)
    if normalized in (None, "فاقد", "فاقد عناوین ایثارگری"):
        return "فاقد عناوین ایثارگری"
    return normalized


def map_housing(value: object | None) -> str:
    normalized = normalize_text(value)
    mapping = {
        "شخصی": "شخصی - با خانواده",
        "شخصی - با خانواده": "شخصی - با خانواده",
        "اجاره ای": "اجاره ای - با خانواده",
        "اجاره ای - با خانواده": "اجاره ای - با خانواده",
        "سازمانی": "سازمانی - با خانواده",
        "سازمانی - با خانواده": "سازمانی - با خانواده",
    }
    if normalized is None:
        return FIXED_OPTIONS["housing_status"]
    return mapping.get(normalized, normalized)
