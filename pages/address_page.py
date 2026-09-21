"""Address and contact page."""

from __future__ import annotations

from logging import Logger
from typing import Any

from errors import PageTransitionError
from mappings import resolve_mother_phone
from models import StudentRecord


class AddressPage:
    def __init__(self, page: Any, logger: Logger) -> None:
        self.page = page
        self.logger = logger

    async def _verify_target_student(self, student: StudentRecord) -> None:
        displayed_national_id = await self.page.locator("#studentId").input_value()
        if displayed_national_id != student.student_national_id:
            raise PageTransitionError(
                "The open SIDA record does not match the selected Excel row."
            )

    async def fill_and_continue(self, student: StudentRecord) -> None:
        await self._verify_target_student(student)
        if not student.postal_code:
            raise ValueError("Postal code is required for the address page")
        if not student.address:
            raise ValueError("Address is required for the address page")

        shad_mobile = resolve_mother_phone(student.phone)

        await self.page.locator("#studentMobileNumber").fill(shad_mobile)
        await self.page.locator("#homeUnit").fill(student.address)
        await self.page.locator("#homePostalCode").fill(student.postal_code)

        continue_buttons = self.page.locator(
            "button.action-btn.submit-success.action-button-enter:visible"
        )
        if await continue_buttons.count() != 1:
            raise PageTransitionError(
                "Expected exactly one visible 'ثبت و ادامه' button on the address page."
            )
        await continue_buttons.first.click()
        await self.page.wait_for_timeout(500)
        if await self.page.locator("input.warning-req:visible").count():
            raise PageTransitionError(
                "SIDA rejected the address page because required fields are still empty."
            )
        self.logger.info(
            "Address information submitted for Excel row %s",
            student.source_row,
        )
