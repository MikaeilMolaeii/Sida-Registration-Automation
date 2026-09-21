import asyncio
import logging
import unittest

from models import StudentRecord
from pages.search_page import SearchPage, SearchPageSelectors
from errors import InvalidStudentNationalIdError, StudentInfoIncompleteError


class FakeLocator:
    def __init__(
        self,
        *,
        text: str = "",
        block_hidden: bool = False,
        block_visible: bool = False,
    ) -> None:
        self.text = text
        self.block_hidden = block_hidden
        self.block_visible = block_visible
        self.filled_with = None
        self.clicked = False
        self.wait_states = []
        self.children = {}
        self.items = [self]

    @property
    def first(self):
        return self.items[0]

    @property
    def last(self):
        return self.items[-1]

    async def count(self) -> int:
        return len(self.items)

    def nth(self, index: int):
        return self.items[index]

    def locator(self, selector: str):
        return self.children[selector]

    async def wait_for(self, *, state: str, timeout=None) -> None:
        self.wait_states.append((state, timeout))
        if state == "hidden" and self.block_hidden:
            await asyncio.Future()
        if state == "visible" and self.block_visible:
            await asyncio.Future()

    async def fill(self, value: str) -> None:
        self.filled_with = value

    async def click(self) -> None:
        self.clicked = True

    async def inner_text(self) -> str:
        return self.text


class FakePage:
    def __init__(self, selectors: SearchPageSelectors) -> None:
        self.url = "https://sida.example/search"
        self.main_frame = object()
        self.event_waits = []
        self.waited_url = None
        self.waited_timeouts = []

        self.student_id = FakeLocator(block_hidden=True)
        self.birth_date = FakeLocator()
        self.student_id.children[selectors.birth_date_relative] = self.birth_date

        self.guardian = FakeLocator()
        self.guardian_container = FakeLocator()
        self.guardian_container.children[".k-select"] = self.guardian

        self.first_option = FakeLocator(text="سرپرست پدر")
        self.option_collection = FakeLocator()
        self.option_collection.items = [self.first_option]
        self.listbox = FakeLocator()
        self.listbox.children[selectors.listbox_option] = self.option_collection
        self.listbox_collection = FakeLocator()
        self.listbox_collection.items = [self.listbox]

        self.next_step_marker = FakeLocator(block_visible=True)
        self.incomplete_popup = FakeLocator(block_visible=True)
        self.invalid_national_id_popup = FakeLocator(block_visible=True)

        self.locators = {
            selectors.national_id_textbox: self.student_id,
            selectors.guardian_combobox.removesuffix(" .k-select"): (
                self.guardian_container
            ),
            selectors.visible_listbox: self.listbox_collection,
            selectors.next_step_marker: self.next_step_marker,
        }

    def locator(self, selector: str):
        return self.locators[selector]

    def get_by_text(self, text: str, *, exact: bool):
        assert exact is False
        if text == SearchPage.STUDENT_INCOMPLETE_TEXT:
            return self.incomplete_popup
        if text == SearchPage.INVALID_STUDENT_NATIONAL_ID_TEXT:
            return self.invalid_national_id_popup
        raise AssertionError(f"Unexpected popup text: {text}")

    async def wait_for_event(self, event, *, predicate, timeout):
        self.event_waits.append((event, timeout))
        self.url = "https://sida.example/student"
        assert predicate(self.main_frame)
        return self.main_frame

    async def wait_for_url(self, url: str, *, timeout: int) -> None:
        self.waited_url = (url, timeout)

    async def wait_for_timeout(self, timeout: int) -> None:
        self.waited_timeouts.append(timeout)


class AttemptAwareLocator(FakeLocator):
    def __init__(self, page, *, visible_on_attempt: int) -> None:
        super().__init__()
        self.page = page
        self.visible_on_attempt = visible_on_attempt

    async def count(self) -> int:
        return int(self.page.attempts == self.visible_on_attempt)

    async def wait_for(self, *, state: str, timeout=None) -> None:
        if state != "visible":
            return await super().wait_for(state=state, timeout=timeout)
        while self.page.attempts < self.visible_on_attempt:
            await asyncio.sleep(0)


class RetryFakePage(FakePage):
    def __init__(self, selectors: SearchPageSelectors) -> None:
        super().__init__(selectors)
        self.attempts = 0
        self.next_step_marker = AttemptAwareLocator(self, visible_on_attempt=2)
        self.locators[selectors.next_step_marker] = self.next_step_marker
        self.locators[f"{selectors.national_id_textbox}:visible"] = (
            AttemptAwareLocator(self, visible_on_attempt=1)
        )

    async def wait_for_event(self, event, *, predicate, timeout):
        self.event_waits.append((event, timeout))
        self.attempts += 1
        self.url = (
            "https://sida.example/search"
            if self.attempts == 1
            else "https://sida.example/student"
        )
        assert predicate(self.main_frame)
        await asyncio.sleep(0)
        return self.main_frame


class IncompleteStudentFakePage(FakePage):
    def __init__(self, selectors: SearchPageSelectors) -> None:
        super().__init__(selectors)
        self.incomplete_popup = FakeLocator(
            text=(
                "اطلاعات برای این کد ملی از سمت ثبت احوال به صورت کامل "
                "ارسال نشده است (از ثبت احوال پیگیری نمایید)"
            )
        )

    async def wait_for_event(self, event, *, predicate, timeout):
        await asyncio.Future()


class InvalidNationalIdFakePage(FakePage):
    def __init__(self, selectors: SearchPageSelectors) -> None:
        super().__init__(selectors)
        self.invalid_national_id_popup = FakeLocator(
            text="کد ملی دانش آموز معتبر نیست"
        )

    async def wait_for_event(self, event, *, predicate, timeout):
        await asyncio.Future()


def sample_student() -> StudentRecord:
    return StudentRecord(
        source_row=2,
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


class SearchPageTests(unittest.IsolatedAsyncioTestCase):
    async def test_fills_text_inputs_and_clicks_first_guardian_option(self) -> None:
        selectors = SearchPageSelectors(next_page_url="**/student")
        page = FakePage(selectors)
        search_page = SearchPage(
            page,
            selectors,
            logging.getLogger("test"),
            manual_transition_timeout_ms=300_000,
        )

        resulting_url = await search_page.prepare_and_wait(sample_student())

        self.assertEqual(selectors.national_id_textbox, "#studentId")
        self.assertEqual(page.student_id.filled_with, "0123456789")
        self.assertEqual(page.birth_date.filled_with, "14000102")
        self.assertTrue(page.guardian.clicked)
        self.assertTrue(page.first_option.clicked)
        self.assertEqual(page.first_option.text, "سرپرست پدر")
        self.assertEqual(page.event_waits, [("framenavigated", 0)])
        self.assertEqual(page.waited_timeouts, [100, 300])
        self.assertEqual(page.waited_url, ("**/student", 15_000))
        self.assertEqual(resulting_url, "https://sida.example/student")
        self.assertFalse(hasattr(page, "click"))

    async def test_waits_five_seconds_and_retries_after_failed_search(self) -> None:
        selectors = SearchPageSelectors()
        page = RetryFakePage(selectors)
        search_page = SearchPage(
            page,
            selectors,
            logging.getLogger("test"),
            manual_transition_timeout_ms=300_000,
            captcha_retry_delay_ms=5_000,
        )

        resulting_url = await search_page.prepare_and_wait(sample_student())

        self.assertEqual(resulting_url, "https://sida.example/student")
        self.assertEqual(page.event_waits, [("framenavigated", 0)] * 2)
        self.assertEqual(page.waited_timeouts, [100, 300, 5_000, 100, 300])

    async def test_reports_incomplete_student_registry_popup(self) -> None:
        selectors = SearchPageSelectors()
        page = IncompleteStudentFakePage(selectors)
        search_page = SearchPage(
            page,
            selectors,
            logging.getLogger("test"),
            manual_transition_timeout_ms=300_000,
        )

        with self.assertRaises(StudentInfoIncompleteError) as captured:
            await search_page.prepare_and_wait(sample_student())

        self.assertIn("ثبت احوال", str(captured.exception))
        self.assertEqual(page.waited_timeouts, [100, 4_000])

    async def test_reports_invalid_student_national_id_popup(self) -> None:
        selectors = SearchPageSelectors()
        page = InvalidNationalIdFakePage(selectors)
        search_page = SearchPage(
            page,
            selectors,
            logging.getLogger("test"),
            manual_transition_timeout_ms=300_000,
        )

        with self.assertRaises(InvalidStudentNationalIdError) as captured:
            await search_page.prepare_and_wait(sample_student())

        self.assertIn("معتبر نیست", str(captured.exception))
        self.assertEqual(page.waited_timeouts, [100, 4_000])


if __name__ == "__main__":
    unittest.main()
