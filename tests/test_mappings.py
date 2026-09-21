import pytest

from errors import UnknownMappingError
from mappings import (
    DEFAULT_FATHER_EDUCATION,
    DEFAULT_MOTHER_EDUCATION,
    FIXED_OPTIONS,
    map_education,
    map_housing,
    map_job,
    normalize_text,
    resolve_mother_phone,
)


def test_normalize_persian_digits_and_spacing() -> None:
    assert normalize_text("  ۱۲۳  ") == "123"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("لیسانس", "لیسانس"),
        ("دیپلم", "دیپلم متوسطه"),
        ("دیپلم متوسطه", "دیپلم متوسطه"),
        ("ابتدایی", "ابتدایی"),
        ("سیکل", "راهنمایی سیکل"),
        ("فوق دیپلم", "فوق دیپلم"),
        ("فوق لیسانس", "فوق لیسانس"),
        ("دکتری", "دکتری"),
    ],
)
def test_education_mapping(source: str, expected: str) -> None:
    assert map_education(source) == expected


def test_unknown_education_is_not_guessed() -> None:
    with pytest.raises(UnknownMappingError):
        map_education("نامشخص")


def test_blank_and_free_job_mapping() -> None:
    assert map_job(None) == "آزاد تجاری"
    assert map_job("آزاد") == "آزاد تجاری"


def test_blank_housing_uses_confirmed_first_option() -> None:
    assert map_housing(None) == "شخصی - با خانواده"
    assert FIXED_OPTIONS["family_type"] == "فاقد عناوین ایثارگری"
    assert FIXED_OPTIONS["physical_status"] == "سالم"


def test_education_defaults_and_required_mother_phone() -> None:
    assert map_education(DEFAULT_FATHER_EDUCATION) == "دیپلم متوسطه"
    assert map_education(DEFAULT_MOTHER_EDUCATION) == "لیسانس"
    assert resolve_mother_phone("09123456789") == "9123456789"
    with pytest.raises(ValueError, match="Mother mobile is required"):
        resolve_mother_phone(None)
