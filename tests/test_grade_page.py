import logging

import pytest

from errors import GradeSubmissionError
from models import StudentRecord
from pages.grade_page import GradePage


class FakeStudentId:
    async def input_value(self) -> str:
        return "0123456789"


class FakePage:
    def __init__(self) -> None:
        self.waits: list[int] = []

    def locator(self, selector: str):
        assert selector == "#studentId"
        return FakeStudentId()

    async def wait_for_timeout(self, timeout: int) -> None:
        self.waits.append(timeout)


class StubGradePage(GradePage):
    def __init__(self, outcomes: list[tuple[str, str]]) -> None:
        super().__init__(
            FakePage(),
            logging.getLogger("test"),
            grade_preferences=("پیش دبستانی یک", "پیش دبستانی دو", "نوباوه"),
        )
        self.outcomes = iter(outcomes)
        self.selected: list[str] = []
        self.clicks = 0
        self.dismissals = 0

    async def _select_grade(self, expected: str) -> None:
        self.selected.append(expected)

    async def _click_final(self) -> None:
        self.clicks += 1

    async def _wait_submission_result(self) -> tuple[str, str]:
        return next(self.outcomes)

    async def _dismiss_feedback(self) -> None:
        self.dismissals += 1


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
async def test_tries_grades_in_order_until_one_succeeds() -> None:
    page = StubGradePage(
        [("error", "ظرفیت ندارد"), ("success", "ثبت با موفقیت انجام شد")]
    )

    selected = await page.submit_with_fallback(sample_student())

    assert selected == "پیش دبستانی دو"
    assert page.selected == ["پیش دبستانی یک", "پیش دبستانی دو"]
    assert page.clicks == 2
    assert page.dismissals == 2
    assert page.page.waits == [6_000]


@pytest.mark.asyncio
async def test_fails_after_all_three_grades_are_rejected() -> None:
    page = StubGradePage(
        [("error", "خطا 1"), ("error", "خطا 2"), ("error", "خطا 3")]
    )

    with pytest.raises(GradeSubmissionError):
        await page.submit_with_fallback(sample_student())

    assert page.selected == ["پیش دبستانی یک", "پیش دبستانی دو", "نوباوه"]
    assert page.clicks == 3
    assert page.dismissals == 3
    assert page.page.waits == [6_000, 6_000]


@pytest.mark.asyncio
async def test_uncertain_response_stops_without_trying_another_grade() -> None:
    page = StubGradePage([("timeout", "no response")])

    with pytest.raises(GradeSubmissionError):
        await page.submit_with_fallback(sample_student())

    assert page.selected == ["پیش دبستانی یک"]
    assert page.clicks == 1
    assert page.page.waits == []
