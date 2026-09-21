"""Try the final SIDA grade options in the confirmed order."""

from __future__ import annotations

import time
from logging import Logger
from typing import Any, Iterable

from errors import GradeSubmissionError, PageTransitionError
from mappings import normalize_text
from models import StudentRecord
from pages.kendo import select_exact_option


class GradePage:
    GRADE_CONTAINER = "#combo-box-gradeTypeId"
    FINAL_BUTTON = (
        "button.action-btn.submit-success.action-button-enter:visible"
    )
    FINAL_PAGE_MARKER = "#combo-box-gradeTypeId:visible"
    FEEDBACK = (
        ".swal2-popup:visible, .toast:visible, .toast-message:visible, "
        ".k-notification:visible, .iziToast:visible, .alert-danger:visible, "
        ".alert-warning:visible, .validation-summary-errors:visible, "
        "#toast-container [class*=\"toast\"]:visible, "
        ".alertify-notifier .ajs-message:visible, .ajs-dialog:visible"
    )
    SUCCESS_WORDS = ("موفق", "ثبت شد", "انجام شد")
    ERROR_WORDS = (
        "خطا",
        "ناموفق",
        "امکان ثبت",
        "مجاز نیست",
        "ظرفیت",
        "تکراری",
    )

    def __init__(
        self,
        page: Any,
        logger: Logger,
        *,
        grade_preferences: Iterable[str],
        response_timeout_ms: int = 10_000,
        poll_interval_ms: int = 200,
        retry_delay_ms: int = 6_000,
    ) -> None:
        self.page = page
        self.logger = logger
        self.grade_preferences = tuple(grade_preferences)
        self.response_timeout_ms = response_timeout_ms
        self.poll_interval_ms = poll_interval_ms
        self.retry_delay_ms = retry_delay_ms

    async def _verify_target_student(self, student: StudentRecord) -> None:
        displayed = await self.page.locator("#studentId").input_value()
        if displayed != student.student_national_id:
            raise PageTransitionError(
                "The open SIDA record does not match the selected Excel row."
            )

    async def _select_grade(self, expected: str) -> None:
        await select_exact_option(self.page, self.GRADE_CONTAINER, expected)

    async def _click_final(self) -> None:
        buttons = self.page.locator(self.FINAL_BUTTON)
        if await buttons.count() != 1:
            raise PageTransitionError(
                "Expected exactly one visible final-registration button."
            )
        await buttons.first.click()

    async def _visible_feedback(self) -> tuple[str | None, str]:
        messages = self.page.locator(self.FEEDBACK)
        texts: list[str] = []
        for index in range(await messages.count()):
            text = normalize_text(await messages.nth(index).inner_text()) or ""
            if text:
                texts.append(text)
        combined = " ".join(texts)
        if any(word in combined for word in self.SUCCESS_WORDS):
            return "success", combined
        if any(word in combined for word in self.ERROR_WORDS):
            return "error", combined
        return None, combined

    async def _wait_submission_result(self) -> tuple[str, str]:
        deadline = time.monotonic() + self.response_timeout_ms / 1000
        while time.monotonic() < deadline:
            if await self.page.locator(self.FINAL_PAGE_MARKER).count() == 0:
                return "success", "final page closed"
            status, message = await self._visible_feedback()
            if status:
                return status, message
            await self.page.wait_for_timeout(self.poll_interval_ms)
        return "timeout", "No confirmed SIDA response was detected."

    async def _dismiss_feedback(self) -> None:
        dismiss = self.page.locator(
            ".swal2-confirm:visible, .toast button.close:visible, "
            ".iziToast-close:visible"
        )
        if await dismiss.count():
            await dismiss.first.click()
        else:
            await self.page.wait_for_timeout(300)

    async def submit_with_fallback(self, student: StudentRecord) -> str:
        """Submit grades in order and return the first confirmed successful one."""
        await self._verify_target_student(student)
        if not self.grade_preferences:
            raise GradeSubmissionError("No final grade options were configured.")

        errors: list[str] = []
        for attempt, grade in enumerate(self.grade_preferences, start=1):
            await self._select_grade(grade)
            await self._click_final()
            status, message = await self._wait_submission_result()
            if status == "success":
                await self._dismiss_feedback()
                self.logger.info(
                    "Final registration succeeded with grade %s for Excel row %s",
                    grade,
                    student.source_row,
                )
                return grade
            if status == "timeout":
                raise GradeSubmissionError(
                    "Final registration response was uncertain after selecting "
                    f"{grade!r}; no further grade was attempted."
                )

            errors.append(f"{grade}: {message or 'SIDA rejected the grade'}")
            self.logger.warning(
                "SIDA rejected final grade option %s/%s (%s) for Excel row %s",
                attempt,
                len(self.grade_preferences),
                grade,
                student.source_row,
            )
            await self._dismiss_feedback()
            if attempt < len(self.grade_preferences):
                self.logger.info(
                    "Waiting %s seconds before trying the next grade for Excel row %s",
                    self.retry_delay_ms / 1000,
                    student.source_row,
                )
                await self.page.wait_for_timeout(self.retry_delay_ms)

        raise GradeSubmissionError(
            "SIDA rejected every confirmed grade option: " + " | ".join(errors)
        )
