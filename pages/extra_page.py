"""Additional student and parent information page."""

from __future__ import annotations

from logging import Logger
from typing import Any

from errors import PageTransitionError
from pages.kendo import select_exact_option
from mappings import (
    DEFAULT_FATHER_EDUCATION,
    DEFAULT_MOTHER_EDUCATION,
    FIXED_OPTIONS,
    map_education,
    map_job,
)
from models import StudentRecord


class ExtraPage:
    COMBOBOXES = {
        "religion": "#combo-box-din-type",
        "madhab": "#combo-box-mazhab-type",
        "family_type": "#combo-box-fam-type",
        "father_education": "#combo-box-fmadrak-type",
        "father_job": "#combo-box-fjob-type",
        "mother_education": "#combo-box-mmadrak-type",
        "physical_status": "#combo-box-body-type",
        "housing_status": "#combo-box-hos-type",
    }

    def __init__(self, page: Any, logger: Logger) -> None:
        self.page = page
        self.logger = logger

    async def _verify_target_student(self, student: StudentRecord) -> None:
        displayed_national_id = await self.page.locator("#studentId").input_value()
        if displayed_national_id != student.student_national_id:
            raise PageTransitionError(
                "The open SIDA record does not match the selected Excel row."
            )

    async def _select_option(self, container_selector: str, expected: str) -> None:
        await select_exact_option(self.page, container_selector, expected)

    async def fill_and_continue(self, student: StudentRecord) -> None:
        await self._verify_target_student(student)
        selections = {
            "religion": FIXED_OPTIONS["religion"],
            "madhab": FIXED_OPTIONS["madhab"],
            "family_type": FIXED_OPTIONS["family_type"],
            "father_education": map_education(
                student.father_education or DEFAULT_FATHER_EDUCATION
            ),
            "father_job": map_job(student.father_job),
            "mother_education": map_education(
                student.mother_education or DEFAULT_MOTHER_EDUCATION
            ),
            "physical_status": FIXED_OPTIONS["physical_status"],
            "housing_status": FIXED_OPTIONS["housing_status"],
        }
        missing = [name for name, value in selections.items() if value is None]
        if missing:
            raise ValueError(
                "Missing additional-information values: " + ", ".join(missing)
            )

        for name, value in selections.items():
            await self._select_option(self.COMBOBOXES[name], value)

        continue_buttons = self.page.locator(
            "button.action-btn.submit-success.action-button-enter:visible"
        )
        if await continue_buttons.count() != 1:
            raise PageTransitionError(
                "Expected exactly one visible 'ثبت و ادامه' button on the extra page."
            )
        await continue_buttons.first.click()
        await self.page.wait_for_timeout(500)
        if await self.page.locator("input.warning-req:visible").count():
            raise PageTransitionError(
                "SIDA rejected the additional-information page because required "
                "fields are still empty."
            )
        self.logger.info(
            "Additional information submitted for Excel row %s",
            student.source_row,
        )
