"""Phase-one CLI: validate Excel input and test the Chrome CDP connection."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from logging import Logger
from pathlib import Path

from config import AppConfig
from errors import (
    ConfigurationError,
    FatherInfoIncompleteError,
    InquiryFailedError,
    MotherInfoIncompleteError,
    SidaAutomationError,
)
from excel_manager import (
    RETRY_REQUEST_STATUS,
    ExcelManager,
    ResultManager,
)
from logger import setup_logging
from models import StudentLoadResult, StudentRecord


def _record_invalid_excel_rows(
    loaded: StudentLoadResult,
    results: ResultManager,
    logger: Logger,
) -> None:
    issues_by_row: dict[int, list[str]] = defaultdict(list)
    for issue in loaded.issues:
        issues_by_row[issue.row_number].append(f"{issue.field}: {issue.message}")

    successful = results.successful_national_ids()
    records_by_row = {record.source_row: record for record in loaded.records}
    for row_number, messages in issues_by_row.items():
        record = records_by_row[row_number]
        national_id = record.student_national_id or ""
        if national_id in successful:
            continue
        results.upsert(
            row_number=row_number,
            student_national_id=national_id,
            status="INVALID_EXCEL_DATA",
            error_message=" | ".join(messages),
        )
        logger.warning(
            "Excel row %s was marked INVALID_EXCEL_DATA: %s",
            row_number,
            " | ".join(messages),
        )


def _apply_retry_requests(
    loaded: StudentLoadResult,
    results: ResultManager,
    logger: Logger,
) -> None:
    for record in loaded.records:
        if record.robot_status != RETRY_REQUEST_STATUS:
            continue
        results.mark_pending_for_retry(
            row_number=record.source_row,
            student_national_id=record.student_national_id or "",
        )
        logger.info(
            "Retry requested from students.xlsx for Excel row %s, student ID %s",
            record.source_row,
            record.student_national_id or "missing",
        )


def _is_pending_record(
    record: StudentRecord,
    successful_ids: set[str],
    statuses: dict[str, str],
) -> bool:
    national_id = record.student_national_id or ""
    if national_id in successful_ids:
        return False
    status = statuses.get(national_id)
    if status in {
        "INCOMPLETE_STUDENT_INFO",
        "INVALID_STUDENT_NATIONAL_ID",
        "INVALID_EXCEL_DATA",
    }:
        return False
    if status == "INCOMPLETE_FATHER_INFO":
        return record.manual_father_info_complete
    if status == "INCOMPLETE_MOTHER_INFO":
        return record.manual_mother_info_complete
    if status == "INCOMPLETE_PARENT_INFO":
        return (
            record.manual_father_info_complete
            or record.manual_mother_info_complete
        )
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Path to the source .xlsx workbook")
    parser.add_argument("--sheet", help="Input worksheet name")
    parser.add_argument(
        "--check-browser",
        action="store_true",
        help="Also verify the already-running Chrome CDP session",
    )
    parser.add_argument(
        "--prepare-step1",
        action="store_true",
        help=(
            "Fill Step 1 for one valid Excel row, then stop before CAPTCHA/Search"
        ),
    )
    parser.add_argument(
        "--row",
        type=int,
        help="Excel row to prepare; defaults to the first valid data row",
    )
    parser.add_argument(
        "--continue-student",
        action="store_true",
        help=(
            "Fill the post-inquiry student page and click 'ثبت و ادامه' for one "
            "valid Excel row"
        ),
    )
    parser.add_argument(
        "--run-through-student",
        action="store_true",
        help=(
            "Run Step 1, wait for manual CAPTCHA/Search, then automatically "
            "complete and continue the student-information step"
        ),
    )
    parser.add_argument(
        "--continue-extra",
        action="store_true",
        help="Fill the current additional-information page and click 'ثبت و ادامه'",
    )
    parser.add_argument(
        "--continue-address",
        action="store_true",
        help="Fill the current address/contact page and click 'ثبت و ادامه'",
    )
    parser.add_argument(
        "--continue-father",
        action="store_true",
        help="Complete the current father page, including retried registry inquiry",
    )
    parser.add_argument(
        "--continue-mother",
        action="store_true",
        help="Complete the current mother page, including retried registry inquiry",
    )
    parser.add_argument(
        "--continue-final",
        action="store_true",
        help=(
            "Try all confirmed final grades for the current row, return to the "
            "preschool preregistration page, and prepare the next pending row"
        ),
    )
    parser.add_argument(
        "--run-batch",
        action="store_true",
        help=(
            "Run the complete workflow for pending rows; CAPTCHA/Search remains "
            "manual for every student"
        ),
    )
    return parser


async def run() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = build_parser().parse_args()
    config = AppConfig.from_env()
    if args.input:
        config.input_file = args.input
    if args.sheet:
        config.input_sheet = args.sheet
    config.ensure_runtime_directories()
    logger = setup_logging(config.log_dir)

    try:
        loaded = ExcelManager(config.input_file, config.input_sheet).load_students()
        invalid_rows = {issue.row_number for issue in loaded.issues}
        print(f"Workbook: {config.input_file}")
        print(f"Rows: {len(loaded.records)}")
        print(f"Valid rows: {len(loaded.records) - len(invalid_rows)}")
        print(f"Rows requiring review: {len(invalid_rows)}")
        for issue in loaded.issues:
            print(f"  row {issue.row_number}: {issue.field} - {issue.message}")

        results = ResultManager(
            config.input_file,
            config.input_sheet,
            config.completion_file,
        )
        results.ensure_columns()
        _apply_retry_requests(loaded, results, logger)
        results.sync_completion_journal_from_workbook()
        _record_invalid_excel_rows(loaded, results, logger)

        if (
            args.check_browser
            or args.prepare_step1
            or args.continue_student
            or args.run_through_student
            or args.continue_extra
            or args.continue_address
            or args.continue_father
            or args.continue_mother
            or args.continue_final
            or args.run_batch
        ):
            # Playwright is optional for Excel-only validation.
            try:
                from browser import BrowserSession
            except ModuleNotFoundError as exc:
                if exc.name == "playwright":
                    raise ConfigurationError(
                        "Playwright is not installed. Run: pip install -r requirements.txt"
                    ) from exc
                raise

            async with BrowserSession(config, logger) as connected:
                print(f"Chrome CDP connection: OK ({connected.page.url})")
                if args.prepare_step1:
                    from pages.search_page import SearchPage, SearchPageSelectors

                    valid_rows = loaded.valid_row_numbers
                    candidates = [
                        record
                        for record in loaded.records
                        if record.source_row in valid_rows
                        and (args.row is None or record.source_row == args.row)
                    ]
                    if not candidates:
                        requested = (
                            f"Excel row {args.row}" if args.row is not None else "any row"
                        )
                        raise ConfigurationError(
                            f"No valid student record is available for {requested}."
                        )

                    student = candidates[0]
                    search_page = SearchPage(
                        connected.page,
                        SearchPageSelectors(),
                        logger,
                        manual_transition_timeout_ms=(
                            config.page_transition_timeout_ms
                        ),
                    )
                    await search_page.fill_search_fields(student)
                    print(
                        f"Step 1 prepared for Excel row {student.source_row}. "
                        "CAPTCHA and Search were not touched."
                    )
                elif args.continue_student:
                    from pages.student_page import StudentPage

                    valid_rows = loaded.valid_row_numbers
                    candidates = [
                        record
                        for record in loaded.records
                        if record.source_row in valid_rows
                        and (args.row is None or record.source_row == args.row)
                    ]
                    if not candidates:
                        requested = (
                            f"Excel row {args.row}" if args.row is not None else "any row"
                        )
                        raise ConfigurationError(
                            f"No valid student record is available for {requested}."
                        )

                    student = candidates[0]
                    await StudentPage(connected.page, logger).fill_and_continue(student)
                    print(
                        f"Student page submitted for Excel row {student.source_row}."
                    )
                elif args.run_through_student:
                    from pages.search_page import SearchPage, SearchPageSelectors
                    from pages.student_page import StudentPage

                    valid_rows = loaded.valid_row_numbers
                    candidates = [
                        record
                        for record in loaded.records
                        if record.source_row in valid_rows
                        and (args.row is None or record.source_row == args.row)
                    ]
                    if not candidates:
                        requested = (
                            f"Excel row {args.row}" if args.row is not None else "any row"
                        )
                        raise ConfigurationError(
                            f"No valid student record is available for {requested}."
                        )

                    student = candidates[0]
                    search_page = SearchPage(
                        connected.page,
                        SearchPageSelectors(),
                        logger,
                        manual_transition_timeout_ms=(
                            config.page_transition_timeout_ms
                        ),
                    )
                    await search_page.prepare_and_wait(student)
                    await StudentPage(connected.page, logger).fill_and_continue(student)
                    print(
                        f"Steps 1 and 2 completed for Excel row {student.source_row}."
                    )
                elif args.continue_extra:
                    from pages.extra_page import ExtraPage

                    valid_rows = loaded.valid_row_numbers
                    candidates = [
                        record
                        for record in loaded.records
                        if record.source_row in valid_rows
                        and (args.row is None or record.source_row == args.row)
                    ]
                    if not candidates:
                        requested = (
                            f"Excel row {args.row}" if args.row is not None else "any row"
                        )
                        raise ConfigurationError(
                            f"No valid student record is available for {requested}."
                        )
                    student = candidates[0]
                    await ExtraPage(connected.page, logger).fill_and_continue(student)
                    print(
                        f"Additional-information page submitted for Excel row "
                        f"{student.source_row}."
                    )
                elif args.continue_address:
                    from pages.address_page import AddressPage

                    valid_rows = loaded.valid_row_numbers
                    candidates = [
                        record
                        for record in loaded.records
                        if record.source_row in valid_rows
                        and (args.row is None or record.source_row == args.row)
                    ]
                    if not candidates:
                        requested = (
                            f"Excel row {args.row}" if args.row is not None else "any row"
                        )
                        raise ConfigurationError(
                            f"No valid student record is available for {requested}."
                        )
                    student = candidates[0]
                    await AddressPage(connected.page, logger).fill_and_continue(student)
                    print(
                        f"Address page submitted for Excel row {student.source_row}."
                    )
                elif args.continue_father:
                    from pages.father_page import FatherPage

                    valid_rows = loaded.valid_row_numbers
                    candidates = [
                        record
                        for record in loaded.records
                        if record.source_row in valid_rows
                        and (args.row is None or record.source_row == args.row)
                    ]
                    if not candidates:
                        requested = (
                            f"Excel row {args.row}" if args.row is not None else "any row"
                        )
                        raise ConfigurationError(
                            f"No valid student record is available for {requested}."
                        )
                    student = candidates[0]
                    try:
                        await FatherPage(
                            connected.page,
                            logger,
                            retry_delay_ms=config.inquiry_retry_delay_ms,
                            max_attempts=config.inquiry_max_attempts,
                        ).fill_and_continue(student)
                    except InquiryFailedError as exc:
                        status = (
                            "INCOMPLETE_FATHER_INFO"
                            if isinstance(exc, FatherInfoIncompleteError)
                            else "INCOMPLETE_PARENT_INFO"
                        )
                        results.upsert(
                            row_number=student.source_row,
                            student_national_id=student.student_national_id or "",
                            status=status,
                            error_message=str(exc),
                        )
                        raise
                    print(
                        f"Father page submitted for Excel row {student.source_row}."
                    )
                elif args.continue_mother:
                    from pages.mother_page import MotherPage

                    valid_rows = loaded.valid_row_numbers
                    candidates = [
                        record
                        for record in loaded.records
                        if record.source_row in valid_rows
                        and (args.row is None or record.source_row == args.row)
                    ]
                    if not candidates:
                        requested = (
                            f"Excel row {args.row}" if args.row is not None else "any row"
                        )
                        raise ConfigurationError(
                            f"No valid student record is available for {requested}."
                        )
                    student = candidates[0]
                    try:
                        await MotherPage(
                            connected.page,
                            logger,
                            retry_delay_ms=config.inquiry_retry_delay_ms,
                            max_attempts=config.inquiry_max_attempts,
                        ).fill_and_continue(student)
                    except InquiryFailedError as exc:
                        status = (
                            "INCOMPLETE_MOTHER_INFO"
                            if isinstance(exc, MotherInfoIncompleteError)
                            else "INCOMPLETE_PARENT_INFO"
                        )
                        results.upsert(
                            row_number=student.source_row,
                            student_national_id=student.student_national_id or "",
                            status=status,
                            error_message=str(exc),
                        )
                        raise
                    print(
                        f"Mother page submitted for Excel row {student.source_row}."
                    )
                elif args.continue_final:
                    from registration_workflow import RegistrationWorkflow

                    valid_rows = loaded.valid_row_numbers
                    candidates = [
                        record
                        for record in loaded.records
                        if record.source_row in valid_rows
                    ]
                    current = next(
                        (
                            record
                            for record in candidates
                            if args.row is None or record.source_row == args.row
                        ),
                        None,
                    )
                    if current is None:
                        requested = (
                            f"Excel row {args.row}" if args.row is not None else "any row"
                        )
                        raise ConfigurationError(
                            f"No valid student record is available for {requested}."
                        )

                    successful = results.successful_national_ids()
                    statuses = results.latest_statuses()
                    remaining = [
                        record
                        for record in candidates
                        if record.source_row != current.source_row
                        and _is_pending_record(record, successful, statuses)
                    ]
                    next_student = await RegistrationWorkflow(
                        connected.page,
                        config,
                        logger,
                        results,
                    ).finalize_current_and_prepare_next(current, remaining)
                    if next_student is None:
                        print(
                            "Final page processed. No pending valid student remains; "
                            "SIDA is at the preregistration start page."
                        )
                    else:
                        print(
                            f"Final page processed. Step 1 is prepared for Excel row "
                            f"{next_student.source_row}; waiting for manual CAPTCHA/Search."
                        )
                elif args.run_batch:
                    from registration_workflow import RegistrationWorkflow

                    successful = results.successful_national_ids()
                    statuses = results.latest_statuses()
                    candidates = [
                        record
                        for record in loaded.records
                        if record.source_row in loaded.valid_row_numbers
                        and _is_pending_record(record, successful, statuses)
                    ]
                    if args.row is not None:
                        start = next(
                            (
                                index
                                for index, record in enumerate(candidates)
                                if record.source_row == args.row
                            ),
                            None,
                        )
                        if start is None:
                            raise ConfigurationError(
                                f"Excel row {args.row} is not a pending valid record."
                            )
                        candidates = candidates[start:] + candidates[:start]
                    if not candidates:
                        print("No pending valid student remains.")
                    else:
                        await RegistrationWorkflow(
                            connected.page,
                            config,
                            logger,
                            results,
                        ).run_students(candidates)
                        print("Batch workflow finished; SIDA returned to the start page.")
        return 0 if not loaded.issues else 2
    except SidaAutomationError as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
