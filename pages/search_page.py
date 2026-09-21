"""Step 1: prepare search fields, then wait for the user's Search action."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from logging import Logger
from typing import Any

from errors import (
    ConfigurationError,
    InvalidStudentNationalIdError,
    PageTransitionError,
    StudentInfoIncompleteError,
)
from mappings import normalize_text
from models import StudentRecord
from pages.kendo import select_exact_option


@dataclass(frozen=True, slots=True)
class SearchPageSelectors:
    """Selectors derived from the confirmed Step 1 page structure."""

    national_id_textbox: str = "#studentId"
    birth_date_relative: str = (
        'xpath=following::input[@type="tel" and @maxlength="8"][1]'
    )
    guardian_combobox: str = "#combo-box-type-supervisorStatusId .k-select"
    visible_listbox: str = '[role="listbox"]:visible'
    listbox_option: str = '[role="option"]'
    next_step_marker: str = "#name:visible"
    next_page_url: str | None = None

    def __post_init__(self) -> None:
        required = {
            "national_id_textbox": self.national_id_textbox,
            "birth_date_relative": self.birth_date_relative,
            "guardian_combobox": self.guardian_combobox,
            "visible_listbox": self.visible_listbox,
            "listbox_option": self.listbox_option,
            "next_step_marker": self.next_step_marker,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ConfigurationError(
                "Missing verified Step 1 selectors: " + ", ".join(missing)
            )


class SearchPage:
    """Fill Step 1 without locating CAPTCHA or the Search button."""

    GUARDIAN_FIRST_OPTION = "سرپرست پدر"
    STUDENT_INCOMPLETE_TEXT = (
        "اطلاعات برای این کد ملی از سمت ثبت احوال به صورت کامل ارسال نشده است"
    )
    INVALID_STUDENT_NATIONAL_ID_TEXT = "کد ملی دانش آموز معتبر نیست"

    def __init__(
        self,
        page: Any,
        selectors: SearchPageSelectors,
        logger: Logger,
        *,
        manual_transition_timeout_ms: int,
        post_navigation_timeout_ms: int = 15_000,
        captcha_retry_delay_ms: int = 5_000,
        registry_error_delay_ms: int = 4_000,
    ) -> None:
        self.page = page
        self.selectors = selectors
        self.logger = logger
        self.manual_transition_timeout_ms = manual_transition_timeout_ms
        self.post_navigation_timeout_ms = post_navigation_timeout_ms
        self.captcha_retry_delay_ms = captcha_retry_delay_ms
        self.registry_error_delay_ms = registry_error_delay_ms

    async def fill_search_fields(self, student: StudentRecord) -> None:
        """Fill the two text inputs and select the first guardian option."""
        if not student.student_national_id:
            raise ValueError("Student national ID is required for Step 1")
        if not student.student_birth_date:
            raise ValueError("Student birth date is required for Step 1")

        national_id = self.page.locator(self.selectors.national_id_textbox)
        await national_id.wait_for(state="visible")
        await national_id.fill(student.student_national_id)

        # The birth-date input has no stable id. Locate it structurally as the
        # first tel/maxlength=8 input following the confirmed #studentId field.
        birth_date = national_id.locator(self.selectors.birth_date_relative)
        await birth_date.wait_for(state="visible")
        await birth_date.fill(student.student_birth_date)

        await self._select_first_guardian_option()
        self.logger.info(
            "Step 1 fields prepared for Excel row %s; waiting for manual CAPTCHA and Search",
            student.source_row,
        )

    async def _select_first_guardian_option(self) -> None:
        # The selector already targets the Kendo arrow rather than its parent,
        # so pass the confirmed parent container to the shared popup helper.
        container_selector = self.selectors.guardian_combobox.removesuffix(
            " .k-select"
        )
        await select_exact_option(
            self.page,
            container_selector,
            self.GUARDIAN_FIRST_OPTION,
        )

    async def wait_for_manual_search_navigation(self, student: StudentRecord) -> str:
        """Wait for navigation or disappearance of the Step 1 page state.

        The user solves CAPTCHA and clicks Search. The bot does not create a
        Search-button locator, click Search, or inspect CAPTCHA. Progress is
        detected by either a main-frame navigation or ``#studentId`` becoming
        hidden/detached during a same-document application transition.
        """

        async def wait_for_main_frame_navigation() -> str:
            await self.page.wait_for_event(
                "framenavigated",
                predicate=lambda frame: frame == self.page.main_frame,
                timeout=0,
            )
            return "main-frame navigation"

        async def wait_for_search_state_to_leave() -> str:
            await self.page.locator(self.selectors.national_id_textbox).wait_for(
                state="hidden",
                timeout=0,
            )
            return "search-page state change"

        async def wait_for_student_details() -> str:
            await self.page.locator(self.selectors.next_step_marker).wait_for(
                state="visible",
                timeout=0,
            )
            return "student details visible"

        async def wait_for_incomplete_student_info() -> str:
            await self.page.get_by_text(
                self.STUDENT_INCOMPLETE_TEXT,
                exact=False,
            ).first.wait_for(state="visible", timeout=0)
            return "incomplete student registry data"

        async def wait_for_invalid_student_national_id() -> str:
            await self.page.get_by_text(
                self.INVALID_STUDENT_NATIONAL_ID_TEXT,
                exact=False,
            ).first.wait_for(state="visible", timeout=0)
            return "invalid student national ID"

        while True:
            tasks = {
                asyncio.create_task(wait_for_main_frame_navigation()),
                asyncio.create_task(wait_for_search_state_to_leave()),
                asyncio.create_task(wait_for_student_details()),
                asyncio.create_task(wait_for_incomplete_student_info()),
                asyncio.create_task(wait_for_invalid_student_national_id()),
            }
            try:
                completed, _ = await asyncio.wait(
                    tasks,
                    timeout=(
                        None
                        if self.manual_transition_timeout_ms <= 0
                        else self.manual_transition_timeout_ms / 1000
                    ),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not completed:
                    raise PageTransitionError(
                        "Timed out while waiting for the user to solve CAPTCHA, click "
                        "Search, and leave the Step 1 page."
                    )
                signals = {task.result() for task in completed}
                signal = next(iter(signals))
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

            if "incomplete student registry data" in signals:
                popup = self.page.get_by_text(
                    self.STUDENT_INCOMPLETE_TEXT,
                    exact=False,
                ).first
                message = normalize_text(await popup.inner_text()) or (
                    self.STUDENT_INCOMPLETE_TEXT
                )
                self.logger.warning(
                    "Student registry data is incomplete for Excel row %s; "
                    "waiting 4 seconds before moving to the next student",
                    student.source_row,
                )
                await self.page.wait_for_timeout(self.registry_error_delay_ms)
                raise StudentInfoIncompleteError(message)
            if "invalid student national ID" in signals:
                popup = self.page.get_by_text(
                    self.INVALID_STUDENT_NATIONAL_ID_TEXT,
                    exact=False,
                ).first
                message = normalize_text(await popup.inner_text()) or (
                    self.INVALID_STUDENT_NATIONAL_ID_TEXT
                )
                self.logger.warning(
                    "Student national ID was rejected for Excel row %s; waiting "
                    "4 seconds before moving to the next student",
                    student.source_row,
                )
                await self.page.wait_for_timeout(self.registry_error_delay_ms)
                raise InvalidStudentNationalIdError(message)

            # A wrong CAPTCHA can reload the main frame while leaving Step 1
            # open. Never treat that reload alone as successful progression.
            await self.page.wait_for_timeout(300)
            if await self.page.locator(self.selectors.next_step_marker).count():
                break
            step1_visible = self.page.locator(
                f"{self.selectors.national_id_textbox}:visible"
            )
            if await step1_visible.count():
                self.logger.warning(
                    "Search did not leave Step 1 for Excel row %s; waiting 5 seconds "
                    "for another manual CAPTCHA attempt",
                    student.source_row,
                )
                await self.page.wait_for_timeout(self.captcha_retry_delay_ms)
                await self.fill_search_fields(student)
                continue

            try:
                await self.page.locator(self.selectors.next_step_marker).wait_for(
                    state="visible",
                    timeout=self.post_navigation_timeout_ms,
                )
                break
            except Exception as exc:
                raise PageTransitionError(
                    "Search changed the page, but student details did not become ready."
                ) from exc

        if self.selectors.next_page_url:
            try:
                await self.page.wait_for_url(
                    self.selectors.next_page_url,
                    timeout=self.post_navigation_timeout_ms,
                )
            except Exception as exc:
                raise PageTransitionError(
                    "The page changed after manual Search, but the expected Step 2 "
                    "URL was not reached."
                ) from exc

        self.logger.info("Manual Search progression detected by %s", signal)
        return self.page.url

    async def prepare_and_wait(self, student: StudentRecord) -> str:
        await self.fill_search_fields(student)
        return await self.wait_for_manual_search_navigation(student)
