"""Father-information page with resilient civil-registry inquiry."""

from __future__ import annotations

from logging import Logger
from typing import Any

from errors import FatherInfoIncompleteError, PageTransitionError
from mappings import normalize_text
from models import StudentRecord
from pages.kendo import select_exact_option


class FatherPage:
    LIFE_STATUS_CONTAINER = "#combo-box-type-hayat1"
    INQUIRY_BUTTON = "button.col-md-12.action-btn.submit-success.m-0:visible"
    CONTINUE_BUTTON = (
        "button.action-btn.submit-success.action-button-enter:visible"
    )
    INCOMPLETE_REGISTRY_TEXT = (
        "اطلاعات برای این کد ملی از سمت ثبت احوال به صورت کامل ارسال نشده است"
    )

    def __init__(
        self,
        page: Any,
        logger: Logger,
        *,
        retry_delay_ms: int = 3_000,
        max_attempts: int = 5,
    ) -> None:
        self.page = page
        self.logger = logger
        self.retry_delay_ms = retry_delay_ms
        self.max_attempts = max_attempts

    async def _verify_target_student(self, student: StudentRecord) -> None:
        displayed_national_id = await self.page.locator("#studentId").input_value()
        if displayed_national_id != student.student_national_id:
            raise PageTransitionError(
                "The open SIDA record does not match the selected Excel row."
            )

    async def _select_alive(self) -> None:
        await select_exact_option(
            self.page,
            self.LIFE_STATUS_CONTAINER,
            "در قید حیات",
        )

    def _national_id_input(self):  # type: ignore[no-untyped-def]
        return self.page.locator(self.LIFE_STATUS_CONTAINER).locator(
            'xpath=following::input[@type="tel" and @maxlength="10"][1]'
        )

    def _birth_date_input(self):  # type: ignore[no-untyped-def]
        return self.page.locator(self.LIFE_STATUS_CONTAINER).locator(
            'xpath=following::input[@type="tel" and @maxlength="8"][1]'
        )

    def _result_inputs(self):  # type: ignore[no-untyped-def]
        first_name = self.page.locator("#name:visible")
        last_name = first_name.locator(
            'xpath=following::input[@type="text" and @maxlength="30"][1]'
        )
        father_name = first_name.locator(
            'xpath=following::input[@type="text" and @maxlength="20"][1]'
        )
        return first_name, last_name, father_name

    async def _results_complete(self) -> bool:
        for control in self._result_inputs():
            if not normalize_text(await control.input_value()):
                return False
        return True

    async def _incomplete_registry_popup_visible(self) -> bool:
        popup = self.page.get_by_text(
            self.INCOMPLETE_REGISTRY_TEXT,
            exact=False,
        )
        return bool(await popup.count()) and await popup.first.is_visible()

    async def _fill_manual_identity(self, student: StudentRecord) -> bool:
        values = (
            student.manual_father_first_name,
            student.manual_father_last_name,
            student.manual_father_parent_name,
        )
        if not all(values):
            return False
        script = """
            (element, value) => {
                element.disabled = false;
                element.readOnly = false;
                element.removeAttribute('disabled');
                element.removeAttribute('readonly');
                const setter = Object.getOwnPropertyDescriptor(
                    HTMLInputElement.prototype, 'value'
                ).set;
                setter.call(element, value);
                element.dispatchEvent(new Event('input', { bubbles: true }));
                element.dispatchEvent(new Event('change', { bubbles: true }));
            }
        """
        for control, value in zip(self._result_inputs(), values, strict=True):
            await control.evaluate(script, value)
        if not await self._results_complete():
            raise PageTransitionError(
                "Father manual identity fields could not be populated."
            )
        self.logger.warning(
            "Father identity was entered manually after five failed inquiries "
            "for Excel row %s",
            student.source_row,
        )
        return True

    async def _run_inquiry(self, student: StudentRecord) -> None:
        inquiry = self.page.locator(self.INQUIRY_BUTTON)
        if await inquiry.count() != 1:
            raise PageTransitionError("Father civil-registry inquiry button was not found.")

        for attempt in range(1, self.max_attempts + 1):
            await inquiry.click()
            await self.page.wait_for_timeout(self.retry_delay_ms)
            if await self._results_complete():
                self.logger.info(
                    "Father inquiry succeeded on attempt %s for Excel row %s",
                    attempt,
                    student.source_row,
                )
                return
            if await self._incomplete_registry_popup_visible():
                self.logger.warning(
                    "SIDA reported incomplete civil-registry data for the father "
                    "on inquiry attempt %s/%s for Excel row %s",
                    attempt,
                    self.max_attempts,
                    student.source_row,
                )
            self.logger.warning(
                "Father inquiry attempt %s/%s did not populate results for Excel row %s",
                attempt,
                self.max_attempts,
                student.source_row,
            )

        if await self._fill_manual_identity(student):
            return

        message = (
            "اطلاعات پدر ناقص است: استعلام ثبت احوال پس از "
            f"{self.max_attempts} تلاش نتیجه نداد و سه ستون ورود دستی پدر کامل نیست"
        )
        self.logger.error(message)
        raise FatherInfoIncompleteError(message)

    async def fill_and_continue(self, student: StudentRecord) -> None:
        await self._verify_target_student(student)
        if not student.father_national_id or not student.father_birth_date:
            raise ValueError("Father national ID and birth date are required")
        if not student.father_phone:
            raise ValueError("Father mobile is required")

        father_mobile = (
            student.father_phone[1:]
            if student.father_phone.startswith("0")
            else student.father_phone
        )
        if len(father_mobile) != 10 or not father_mobile.isdigit():
            raise ValueError("Father mobile must be 10 digits without the leading zero")

        await self._select_alive()
        await self._national_id_input().fill(student.father_national_id)
        await self._birth_date_input().fill(student.father_birth_date)
        await self._run_inquiry(student)
        await self.page.locator("#fatherMobileNumber").fill(father_mobile)

        continue_buttons = self.page.locator(self.CONTINUE_BUTTON)
        if await continue_buttons.count() != 1:
            raise PageTransitionError(
                "Expected exactly one visible 'ثبت و ادامه' button on the father page."
            )
        await continue_buttons.first.click()
        await self.page.wait_for_timeout(500)
        if await self.page.locator("input.warning-req:visible").count():
            raise PageTransitionError(
                "SIDA rejected the father page because required fields are still empty."
            )
        self.logger.info(
            "Father information submitted for Excel row %s",
            student.source_row,
        )
