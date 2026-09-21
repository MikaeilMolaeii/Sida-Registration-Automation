"""Student personal-information step after the civil-registry inquiry."""

from __future__ import annotations

import re
from logging import Logger
from typing import Any

from errors import PageTransitionError
from models import StudentRecord


class StudentPage:
    """Preserve inquiry results, fill Excel-backed fields, and continue."""

    RETURNED_IDENTITY_LABELS = (
        "نام",
        "نام خانوادگی",
        "کد ملی",
        "نام پدر",
        "جنسیت",
    )

    def __init__(self, page: Any, logger: Logger) -> None:
        self.page = page
        self.logger = logger

    def _control_for_label(self, label_text: str):  # type: ignore[no-untyped-def]
        label = self.page.locator("label").filter(
            has_text=re.compile(rf"^\s*{re.escape(label_text)}\s*$")
        )
        return label.first.locator("xpath=..").locator("input:visible").first

    async def _verify_inquiry_results(self) -> None:
        for label_text in self.RETURNED_IDENTITY_LABELS:
            control = self._control_for_label(label_text)
            await control.wait_for(state="visible")
            if not await control.input_value():
                raise PageTransitionError(
                    f"Civil-registry result field {label_text!r} is empty."
                )

    async def _verify_target_student(self, student: StudentRecord) -> None:
        displayed_national_id = await self.page.locator("#studentId").input_value()
        if displayed_national_id != student.student_national_id:
            raise PageTransitionError(
                "The open SIDA inquiry result does not match the selected Excel row."
            )

    async def fill_and_continue(self, student: StudentRecord) -> None:
        if not student.student_national_id:
            raise ValueError("Student national ID is required for the student page")
        if not student.student_birthplace:
            raise ValueError("Student birthplace is required for the student page")

        await self._verify_target_student(student)
        await self._verify_inquiry_results()

        fields = {
            "شماره شناسنامه": student.student_national_id,
            "محل صدور": student.student_birthplace,
            "محل تولد": student.student_birthplace,
        }
        for label_text, value in fields.items():
            control = self._control_for_label(label_text)
            await control.wait_for(state="visible")
            await control.fill(value)

        continue_buttons = self.page.locator(
            "button.action-btn.submit-success.action-button-enter:visible"
        )
        if await continue_buttons.count() != 1:
            raise PageTransitionError(
                "Expected exactly one visible 'ثبت و ادامه' button on the student page."
            )

        await continue_buttons.first.click()
        await self.page.wait_for_timeout(500)
        if await self.page.locator("input.warning-req:visible").count():
            raise PageTransitionError(
                "SIDA rejected the student page because required fields are still empty."
            )
        self.logger.info(
            "Student information submitted for Excel row %s; waiting for the next step",
            student.source_row,
        )
