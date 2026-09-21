"""End-to-end human-in-the-loop registration workflow."""

from __future__ import annotations

from logging import Logger
from typing import Any, Iterable

from config import AppConfig
from errors import (
    FatherInfoIncompleteError,
    GradeSubmissionError,
    InvalidStudentNationalIdError,
    InquiryFailedError,
    MotherInfoIncompleteError,
    SidaAutomationError,
    StudentInfoIncompleteError,
)
from excel_manager import ResultManager
from models import StudentRecord
from pages.address_page import AddressPage
from pages.extra_page import ExtraPage
from pages.father_page import FatherPage
from pages.grade_page import GradePage
from pages.mother_page import MotherPage
from pages.search_page import SearchPage, SearchPageSelectors
from pages.start_navigation import StartPageNavigator
from pages.student_page import StudentPage


class RegistrationWorkflow:
    """Process records while leaving CAPTCHA entry to the user."""

    def __init__(
        self,
        page: Any,
        config: AppConfig,
        logger: Logger,
        results: ResultManager,
    ) -> None:
        self.page = page
        self.config = config
        self.logger = logger
        self.results = results
        self.navigator = StartPageNavigator(
            page,
            logger,
            timeout_ms=config.action_timeout_ms,
        )

    def _search_page(self) -> SearchPage:
        return SearchPage(
            self.page,
            SearchPageSelectors(),
            self.logger,
            manual_transition_timeout_ms=self.config.page_transition_timeout_ms,
            captcha_retry_delay_ms=self.config.captcha_retry_delay_ms,
            registry_error_delay_ms=self.config.student_registry_error_delay_ms,
        )

    def _grade_page(self) -> GradePage:
        return GradePage(
            self.page,
            self.logger,
            grade_preferences=self.config.grade_preferences,
            response_timeout_ms=self.config.grade_response_timeout_ms,
            retry_delay_ms=self.config.grade_retry_delay_ms,
        )

    def _record_failure(self, student: StudentRecord, error: Exception) -> None:
        if isinstance(error, StudentInfoIncompleteError):
            status = "INCOMPLETE_STUDENT_INFO"
        elif isinstance(error, InvalidStudentNationalIdError):
            status = "INVALID_STUDENT_NATIONAL_ID"
        elif isinstance(error, FatherInfoIncompleteError):
            status = "INCOMPLETE_FATHER_INFO"
        elif isinstance(error, MotherInfoIncompleteError):
            status = "INCOMPLETE_MOTHER_INFO"
        elif isinstance(error, InquiryFailedError):
            status = "INCOMPLETE_PARENT_INFO"
        else:
            status = "FAILED"
        self.results.upsert(
            row_number=student.source_row,
            student_national_id=student.student_national_id or "",
            status=status,
            error_message=str(error),
        )
        self.logger.error(
            "Registration failed for Excel row %s, student ID %s: %s",
            student.source_row,
            student.student_national_id or "missing",
            error,
        )

    def _record_success(self, student: StudentRecord, selected_grade: str) -> None:
        excel_synced = self.results.record_success(
            row_number=student.source_row,
            student_national_id=student.student_national_id or "",
            selected_grade=selected_grade,
        )
        if not excel_synced:
            self.logger.warning(
                "Registration success for Excel row %s was saved to the recovery "
                "file, but students.xlsx is locked. Close students.xlsx before "
                "the next run to sync it.",
                student.source_row,
            )

    async def _detect_stage(self) -> str:
        markers = (
            ("grade", "#combo-box-gradeTypeId:visible"),
            ("mother", "#combo-box-type-hayat:visible"),
            ("father", "#combo-box-type-hayat1:visible"),
            ("address", "#studentMobileNumber:visible"),
            ("extra", "#combo-box-din-type:visible"),
            ("student", "#name:visible"),
            ("search", "#combo-box-type-supervisorStatusId .k-select:visible"),
        )
        for name, selector in markers:
            if await self.page.locator(selector).count():
                return name
        return "unknown"

    async def _open_record_matches(self, student: StudentRecord) -> bool:
        student_id = self.page.locator("#studentId:visible")
        if await student_id.count() != 1:
            return False
        return await student_id.input_value() == student.student_national_id

    async def _complete_from_stage(
        self,
        student: StudentRecord,
        stage: str,
    ) -> str:
        stages = ("student", "extra", "address", "father", "mother", "grade")
        if stage not in stages:
            raise ValueError(f"Unsupported continuation stage: {stage}")
        start = stages.index(stage)

        if start <= stages.index("student"):
            await StudentPage(self.page, self.logger).fill_and_continue(student)
        if start <= stages.index("extra"):
            await ExtraPage(self.page, self.logger).fill_and_continue(student)
        if start <= stages.index("address"):
            await AddressPage(self.page, self.logger).fill_and_continue(student)
        if start <= stages.index("father"):
            await FatherPage(
                self.page,
                self.logger,
                retry_delay_ms=self.config.inquiry_retry_delay_ms,
                max_attempts=self.config.inquiry_max_attempts,
            ).fill_and_continue(student)
        if start <= stages.index("mother"):
            await MotherPage(
                self.page,
                self.logger,
                retry_delay_ms=self.config.inquiry_retry_delay_ms,
                max_attempts=self.config.inquiry_max_attempts,
            ).fill_and_continue(student)
        return await self._grade_page().submit_with_fallback(student)

    async def run_students(self, students: Iterable[StudentRecord]) -> None:
        """Run every supplied record, pausing at CAPTCHA for each one."""
        for student in students:
            try:
                stage = await self._detect_stage()
                if stage in {
                    "student",
                    "extra",
                    "address",
                    "father",
                    "mother",
                    "grade",
                } and await self._open_record_matches(student):
                    self.logger.info(
                        "Resuming Excel row %s from the current %s stage",
                        student.source_row,
                        stage,
                    )
                    selected_grade = await self._complete_from_stage(
                        student,
                        stage,
                    )
                else:
                    await self.navigator.open_preschool_preregistration()
                    await self._search_page().prepare_and_wait(student)
                    selected_grade = await self._complete_from_stage(
                        student,
                        "student",
                    )
            except (SidaAutomationError, ValueError) as exc:
                self._record_failure(student, exc)
                continue

            self._record_success(student, selected_grade)
            # SIDA can leave a stale search form visible after final success.
            # Always traverse the confirmed right-menu path before the next row.
            await self.navigator.open_preschool_preregistration(force_menu=True)

        # Leave SIDA at the safe starting page after the final record too.
        await self.navigator.open_preschool_preregistration()

    async def finalize_current_and_prepare_next(
        self,
        current: StudentRecord,
        remaining: Iterable[StudentRecord],
    ) -> StudentRecord | None:
        """Finish the open final page, then prefill one next record before CAPTCHA."""
        try:
            selected_grade = await self._grade_page().submit_with_fallback(current)
        except GradeSubmissionError as exc:
            self._record_failure(current, exc)
        else:
            self._record_success(current, selected_grade)

        await self.navigator.open_preschool_preregistration(force_menu=True)
        next_student = next(iter(remaining), None)
        if next_student is not None:
            await self._search_page().fill_search_fields(next_student)
        return next_student
