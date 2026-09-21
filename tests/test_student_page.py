import logging

import pytest

from models import StudentRecord
from pages.student_page import StudentPage


class FakeControl:
    def __init__(self, value: str = "") -> None:
        self.value = value
        self.filled_with = None

    @property
    def first(self):
        return self

    async def wait_for(self, *, state: str) -> None:
        assert state == "visible"

    async def input_value(self) -> str:
        return self.value

    async def fill(self, value: str) -> None:
        self.value = value
        self.filled_with = value


class FakeParent:
    def __init__(self, control: FakeControl) -> None:
        self.control = control

    def locator(self, selector: str):
        assert selector == "input:visible"
        return self.control


class FakeLabel:
    def __init__(self, control: FakeControl) -> None:
        self.control = control

    @property
    def first(self):
        return self

    def locator(self, selector: str):
        assert selector == "xpath=.."
        return FakeParent(self.control)


class FakeLabels:
    def __init__(self, controls: dict[str, FakeControl]) -> None:
        self.controls = controls

    def filter(self, *, has_text):
        matches = [
            control
            for label, control in self.controls.items()
            if has_text.search(label)
        ]
        assert len(matches) == 1
        return FakeLabel(matches[0])


class FakeButton:
    def __init__(self) -> None:
        self.clicked = False

    @property
    def first(self):
        return self

    async def count(self) -> int:
        return 1

    async def click(self) -> None:
        self.clicked = True


class FakeWarnings:
    async def count(self) -> int:
        return 0


class FakePage:
    def __init__(self) -> None:
        self.national_id = FakeControl("0123456789")
        self.controls = {
            "نام": FakeControl("نام"),
            "نام خانوادگی": FakeControl("خانوادگی"),
            "کد ملی": FakeControl("0123456789"),
            "نام پدر": FakeControl("پدر"),
            "جنسیت": FakeControl("مرد"),
            "شماره شناسنامه": FakeControl(),
            "محل صدور": FakeControl(),
            "محل تولد": FakeControl(),
        }
        self.button = FakeButton()
        self.warnings = FakeWarnings()

    def locator(self, selector: str):
        if selector == "#studentId":
            return self.national_id
        if selector == "label":
            return FakeLabels(self.controls)
        if selector == "button.action-btn.submit-success.action-button-enter:visible":
            return self.button
        if selector == "input.warning-req:visible":
            return self.warnings
        raise AssertionError(f"Unexpected selector: {selector}")

    async def wait_for_timeout(self, timeout: int) -> None:
        assert timeout == 500


def sample_student() -> StudentRecord:
    return StudentRecord(
        source_row=3,
        student_name="نمونه آزمایشی",
        student_national_id="0123456789",
        student_birth_date="14000102",
        student_birthplace="بندرعباس",
        father_name=None,
        father_national_id=None,
        father_birth_date=None,
        father_education=None,
        father_job=None,
        mother_name=None,
        mother_national_id=None,
        mother_birth_date=None,
        mother_education=None,
        mother_job=None,
        address=None,
        postal_code=None,
        phone=None,
    )


@pytest.mark.asyncio
async def test_fills_required_student_fields_and_continues() -> None:
    page = FakePage()
    student_page = StudentPage(page, logging.getLogger("test"))

    await student_page.fill_and_continue(sample_student())

    assert page.controls["شماره شناسنامه"].filled_with == "0123456789"
    assert page.controls["محل صدور"].filled_with == "بندرعباس"
    assert page.controls["محل تولد"].filled_with == "بندرعباس"
    assert page.button.clicked
