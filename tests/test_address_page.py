import logging

import pytest

from models import StudentRecord
from pages.address_page import AddressPage


class FakeInput:
    def __init__(self, value: str = "") -> None:
        self.value = value
        self.filled_with = None

    async def input_value(self) -> str:
        return self.value

    async def fill(self, value: str) -> None:
        self.value = value
        self.filled_with = value


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
        self.inputs = {
            "#studentId": FakeInput("0123456789"),
            "#studentMobileNumber": FakeInput(),
            "#homeUnit": FakeInput(),
            "#homePostalCode": FakeInput(),
            "#homeTelephone": FakeInput(),
        }
        self.button = FakeButton()
        self.warnings = FakeWarnings()

    def locator(self, selector: str):
        if selector in self.inputs:
            return self.inputs[selector]
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
        address="نشانی آزمایشی",
        postal_code="7464143583",
        phone="09123456789",
    )


@pytest.mark.asyncio
async def test_fills_only_mobile_address_and_postal_code() -> None:
    page = FakePage()
    address_page = AddressPage(page, logging.getLogger("test"))

    await address_page.fill_and_continue(sample_student())

    assert page.inputs["#studentMobileNumber"].filled_with == "9123456789"
    assert page.inputs["#homeUnit"].filled_with == "نشانی آزمایشی"
    assert page.inputs["#homePostalCode"].filled_with == "7464143583"
    assert page.inputs["#homeTelephone"].filled_with is None
    assert page.button.clicked
