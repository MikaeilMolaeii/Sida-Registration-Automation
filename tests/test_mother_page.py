import logging
from dataclasses import replace

import pytest

from errors import InquiryFailedError
from models import StudentRecord
from pages.mother_page import MotherPage


class FakeInquiry:
    def __init__(self, page) -> None:
        self.page = page

    async def count(self) -> int:
        return 1

    async def click(self) -> None:
        self.page.attempts += 1


class FakePopup:
    @property
    def first(self):
        return self

    async def count(self) -> int:
        return 0

    async def is_visible(self) -> bool:
        return False


class FakeResult:
    def __init__(self, page, field: str) -> None:
        self.page = page
        self.field = field

    def locator(self, selector: str):
        if 'maxlength="30"' in selector:
            return FakeResult(self.page, "last")
        if 'maxlength="20"' in selector:
            return FakeResult(self.page, "father")
        raise AssertionError(f"Unexpected selector: {selector}")

    async def input_value(self) -> str:
        if self.field in self.page.manual_values:
            return self.page.manual_values[self.field]
        if self.page.succeed_on and self.page.attempts >= self.page.succeed_on:
            return self.field
        return ""

    async def evaluate(self, script: str, value: str) -> None:
        assert "element.disabled = false" in script
        self.page.manual_values[self.field] = value


class FakePage:
    def __init__(self, *, succeed_on: int | None) -> None:
        self.succeed_on = succeed_on
        self.attempts = 0
        self.waits = []
        self.inquiry = FakeInquiry(self)
        self.manual_values = {}
        self.popup = FakePopup()

    def locator(self, selector: str):
        if selector == MotherPage.INQUIRY_BUTTON:
            return self.inquiry
        if selector == "#name:visible":
            return FakeResult(self, "first")
        raise AssertionError(f"Unexpected selector: {selector}")

    def get_by_text(self, text: str, *, exact: bool):
        assert text == MotherPage.INCOMPLETE_REGISTRY_TEXT
        assert exact is False
        return self.popup

    async def wait_for_timeout(self, timeout: int) -> None:
        self.waits.append(timeout)


def sample_student() -> StudentRecord:
    return StudentRecord(
        source_row=3,
        student_name="نمونه آزمایشی",
        student_national_id="0123456789",
        student_birth_date="14000102",
        student_birthplace="بندرعباس",
        father_name=None,
        father_national_id="1111111111",
        father_birth_date="13600102",
        father_education="لیسانس",
        father_job="آزاد تجاری",
        mother_name=None,
        mother_national_id="2222222222",
        mother_birth_date="13650102",
        mother_education="لیسانس",
        mother_job=None,
        address=None,
        postal_code="7464143583",
        phone="9123456789",
        father_phone="9234567890",
    )


@pytest.mark.asyncio
async def test_mother_inquiry_retries_until_results_are_populated() -> None:
    page = FakePage(succeed_on=2)
    mother_page = MotherPage(
        page,
        logging.getLogger("test"),
        retry_delay_ms=3_000,
        max_attempts=5,
    )

    await mother_page._run_inquiry(sample_student())

    assert page.attempts == 2
    assert page.waits == [3_000, 3_000]


@pytest.mark.asyncio
async def test_mother_inquiry_fails_after_five_attempts() -> None:
    page = FakePage(succeed_on=None)
    mother_page = MotherPage(
        page,
        logging.getLogger("test"),
        retry_delay_ms=3_000,
        max_attempts=5,
    )

    with pytest.raises(InquiryFailedError):
        await mother_page._run_inquiry(sample_student())

    assert page.attempts == 5
    assert page.waits == [3_000] * 5


@pytest.mark.asyncio
async def test_mother_inquiry_uses_complete_manual_identity_after_five_attempts() -> None:
    page = FakePage(succeed_on=None)
    mother_page = MotherPage(
        page,
        logging.getLogger("test"),
        retry_delay_ms=3_000,
        max_attempts=5,
    )
    student = replace(
        sample_student(),
        manual_mother_first_name="مریم",
        manual_mother_last_name="نمونه",
        manual_mother_parent_name="رضا",
    )

    await mother_page._run_inquiry(student)

    assert page.attempts == 5
    assert page.manual_values == {
        "first": "مریم",
        "last": "نمونه",
        "father": "رضا",
    }
