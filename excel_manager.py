"""Read student input and persist resumable processing results."""

from __future__ import annotations

import math
import json
import os
import re
from copy import copy
from datetime import date, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from errors import WorkbookSchemaError
from mappings import map_education, normalize_text
from models import StudentLoadResult, StudentRecord, ValidationIssue


COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "student_name": ("نام و نام خانوادگی نوآموز", "نام نوآموز"),
    "student_national_id": ("کد ملی نوآموز", "کدملی نوآموز"),
    "student_birth_date": ("تاریخ تولد نوآموز",),
    "student_birthplace": ("محل تولد نوآموز",),
    "father_name": ("نام پدر", "نام و نام خانوادگی پدر"),
    "father_national_id": ("کد ملی پدر", "کدملی پدر"),
    "father_birth_date": ("تاریخ تولد پدر",),
    "father_education": ("مدرک تحصیلی پدر",),
    "father_job": ("شغل پدر",),
    "mother_name": ("نام و نام خانوادگی مادر", "نام مادر"),
    "mother_national_id": ("کد ملی مادر", "کدملی مادر"),
    "mother_birth_date": ("تاریخ تولد مادر",),
    "mother_education": ("مدرک تحصیلی مادر",),
    "mother_job": ("شغل مادر",),
    "address": ("آدرس منزل", "آدرس"),
    "postal_code": ("کدپستی", "کد پستی"),
    "phone": ("تلفن مادر",),
    "family_type": ("نوع ایثارگری پدر", "نوع خانواده"),
    "physical_status": ("وضعیت جسمانی",),
    "housing_status": ("وضعیت مسکن",),
    "father_phone": ("تلفن پدر", "شماره تلفن پدر"),
    "manual_father_first_name": ("نام کوچک پدر",),
    "manual_father_last_name": ("نام خانوادگی پدر",),
    "manual_father_parent_name": ("نام پدر پدر", "نام پدرِ پدر"),
    "manual_mother_first_name": ("نام کوچک مادر",),
    "manual_mother_last_name": ("نام خانوادگی مادر",),
    "manual_mother_parent_name": ("نام پدر مادر", "نام پدرِ مادر"),
    "robot_status": ("وضعیت ربات",),
    "selected_grade": ("پایه ثبت‌شده",),
    "last_error": ("آخرین خطا",),
    "last_attempt": ("زمان آخرین تلاش",),
}

ROBOT_STATUS_HEADER = "وضعیت ربات"
SELECTED_GRADE_HEADER = "پایه ثبت‌شده"
LAST_ERROR_HEADER = "آخرین خطا"
LAST_ATTEMPT_HEADER = "زمان آخرین تلاش"
RETRY_REQUEST_STATUS = "در انتظار تلاش مجدد"
RESULT_STATUS_LABELS = {
    "SUCCESS": "ثبت شد",
    "PENDING": RETRY_REQUEST_STATUS,
    "INCOMPLETE_STUDENT_INFO": "بررسی: اطلاعات نوآموز ناقص است",
    "INVALID_STUDENT_NATIONAL_ID": "بررسی: کد ملی نامعتبر است",
    "INVALID_EXCEL_DATA": "بررسی: اطلاعات اکسل ناقص است",
    "INCOMPLETE_FATHER_INFO": "بررسی: اطلاعات پدر ناقص است",
    "INCOMPLETE_MOTHER_INFO": "بررسی: اطلاعات مادر ناقص است",
    "INCOMPLETE_PARENT_INFO": "بررسی: اطلاعات والدین ناقص است",
    "FAILED": "بررسی: خطای ثبت",
}
LABEL_RESULT_STATUSES = {label: status for status, label in RESULT_STATUS_LABELS.items()}

REQUIRED_FIELDS = (
    "student_name",
    "student_national_id",
    "student_birth_date",
    "student_birthplace",
    "address",
    "father_national_id",
    "father_birth_date",
    "father_phone",
    "mother_national_id",
    "mother_birth_date",
    "phone",
    "postal_code",
)

_DIGITS_ONLY = re.compile(r"^\d+$")


def _normalize_cell(value: object) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y%m%d")
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return normalize_text(value)


def _normalize_identifier(value: object, length: int) -> str | None:
    text = _normalize_cell(value)
    if text is None:
        return None
    if _DIGITS_ONLY.fullmatch(text) and len(text) < length:
        return text.zfill(length)
    return text


def _header_key(value: object) -> str:
    return normalize_text(value) or ""


class ExcelManager:
    def __init__(self, input_file: Path, sheet_name: str) -> None:
        self.input_file = Path(input_file)
        self.sheet_name = sheet_name

    def load_students(self) -> StudentLoadResult:
        if not self.input_file.exists():
            raise WorkbookSchemaError(f"Input workbook not found: {self.input_file}")

        try:
            frame = pd.read_excel(
                self.input_file,
                sheet_name=self.sheet_name,
                dtype=object,
                engine="openpyxl",
            )
        except ValueError as exc:
            raise WorkbookSchemaError(
                f"Worksheet {self.sheet_name!r} was not found in {self.input_file.name}."
            ) from exc

        frame.columns = [_header_key(column) for column in frame.columns]
        source_columns = self._resolve_columns(frame.columns)
        records: list[StudentRecord] = []
        issues: list[ValidationIssue] = []

        for zero_based_index, row in frame.iterrows():
            excel_row = int(zero_based_index) + 2
            values = {
                field: self._first_value(row, aliases)
                for field, aliases in source_columns.items()
            }
            record = StudentRecord(
                source_row=excel_row,
                student_name=_normalize_cell(values["student_name"]),
                student_national_id=_normalize_identifier(
                    values["student_national_id"], 10
                ),
                student_birth_date=_normalize_identifier(
                    values["student_birth_date"], 8
                ),
                student_birthplace=_normalize_cell(values["student_birthplace"]),
                father_name=_normalize_cell(values["father_name"]),
                father_national_id=_normalize_identifier(
                    values["father_national_id"], 10
                ),
                father_birth_date=_normalize_identifier(values["father_birth_date"], 8),
                father_education=_normalize_cell(values["father_education"]),
                father_job=_normalize_cell(values["father_job"]),
                mother_name=_normalize_cell(values["mother_name"]),
                mother_national_id=_normalize_identifier(
                    values["mother_national_id"], 10
                ),
                mother_birth_date=_normalize_identifier(values["mother_birth_date"], 8),
                mother_education=_normalize_cell(values["mother_education"]),
                mother_job=_normalize_cell(values["mother_job"]),
                address=_normalize_cell(values["address"]),
                postal_code=_normalize_identifier(values["postal_code"], 10),
                phone=_normalize_identifier(values["phone"], 11),
                family_type=_normalize_cell(values["family_type"]),
                physical_status=_normalize_cell(values["physical_status"]),
                housing_status=_normalize_cell(values["housing_status"]),
                father_phone=_normalize_identifier(values["father_phone"], 11),
                manual_father_first_name=_normalize_cell(
                    values["manual_father_first_name"]
                ),
                manual_father_last_name=_normalize_cell(
                    values["manual_father_last_name"]
                ),
                manual_father_parent_name=_normalize_cell(
                    values["manual_father_parent_name"]
                ),
                manual_mother_first_name=_normalize_cell(
                    values["manual_mother_first_name"]
                ),
                manual_mother_last_name=_normalize_cell(
                    values["manual_mother_last_name"]
                ),
                manual_mother_parent_name=_normalize_cell(
                    values["manual_mother_parent_name"]
                ),
                robot_status=_normalize_cell(values["robot_status"]),
                selected_grade=_normalize_cell(values["selected_grade"]),
                last_error=_normalize_cell(values["last_error"]),
                last_attempt=_normalize_cell(values["last_attempt"]),
                source_values={
                    field: _normalize_cell(raw_value)
                    for field, raw_value in values.items()
                },
            )
            records.append(record)
            issues.extend(self._validate_record(record))

        return StudentLoadResult(tuple(records), tuple(issues))

    @staticmethod
    def _resolve_columns(columns: pd.Index) -> dict[str, tuple[str, ...]]:
        available = set(columns)
        resolved: dict[str, tuple[str, ...]] = {}
        missing: list[str] = []
        for field, aliases in COLUMN_ALIASES.items():
            matches = tuple(alias for alias in aliases if _header_key(alias) in available)
            if not matches:
                if field in REQUIRED_FIELDS:
                    missing.append(f"{field} ({' / '.join(aliases)})")
                resolved[field] = ()
            else:
                resolved[field] = matches
        if missing:
            raise WorkbookSchemaError(
                "Required Excel columns are missing: " + ", ".join(missing)
            )
        return resolved

    @staticmethod
    def _first_value(row: pd.Series, aliases: tuple[str, ...]) -> object | None:
        for alias in aliases:
            value = row.get(_header_key(alias))
            if _normalize_cell(value) is not None:
                return value
        return None

    @staticmethod
    def _validate_record(record: StudentRecord) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for field in REQUIRED_FIELDS:
            if getattr(record, field) is None:
                issues.append(
                    ValidationIssue(record.source_row, field, "Required value is missing")
                )

        for field in ("student_national_id", "father_national_id", "mother_national_id"):
            value = getattr(record, field)
            if value is not None and not re.fullmatch(r"\d{10}", value):
                issues.append(
                    ValidationIssue(record.source_row, field, "Expected exactly 10 digits")
                )

        for field in ("student_birth_date", "father_birth_date", "mother_birth_date"):
            value = getattr(record, field)
            if value is not None and not re.fullmatch(r"\d{8}", value):
                issues.append(
                    ValidationIssue(record.source_row, field, "Expected YYYYMMDD as 8 digits")
                )

        if record.postal_code is not None and not re.fullmatch(r"\d{10}", record.postal_code):
            issues.append(
                ValidationIssue(record.source_row, "postal_code", "Expected exactly 10 digits")
            )

        for field in ("father_education", "mother_education"):
            value = getattr(record, field)
            if value is not None:
                try:
                    map_education(value)
                except Exception as exc:
                    issues.append(ValidationIssue(record.source_row, field, str(exc)))
        return issues


class ResultManager:
    """Persist results in students.xlsx with a JSON success safety journal."""

    RESULT_COLUMNS = (
        (ROBOT_STATUS_HEADER, 34),
        (SELECTED_GRADE_HEADER, 20),
        (LAST_ERROR_HEADER, 70),
        (LAST_ATTEMPT_HEADER, 28),
    )

    def __init__(
        self,
        input_file: Path,
        sheet_name: str,
        completion_file: Path,
    ) -> None:
        self.input_file = Path(input_file)
        self.sheet_name = sheet_name
        self.completion_file = Path(completion_file)

    def _load_completion_records(self) -> dict[str, dict[str, object]]:
        if not self.completion_file.exists():
            return {}
        try:
            payload = json.loads(self.completion_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkbookSchemaError(
                f"Cannot read completion recovery file: {self.completion_file}"
            ) from exc
        if not isinstance(payload, dict):
            raise WorkbookSchemaError(
                f"Invalid completion recovery file: {self.completion_file}"
            )
        return payload

    def _record_completion(
        self,
        *,
        row_number: int,
        student_national_id: str,
        selected_grade: str,
    ) -> None:
        """Persist a success marker before touching the lockable Excel workbook."""
        self.completion_file.parent.mkdir(parents=True, exist_ok=True)
        records = self._load_completion_records()
        records[student_national_id] = {
            "row_number": row_number,
            "selected_grade": selected_grade,
            "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        with NamedTemporaryFile(
            prefix=f".{self.completion_file.stem}-",
            suffix=".json",
            dir=self.completion_file.parent,
            delete=False,
            mode="w",
            encoding="utf-8",
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(records, temporary, ensure_ascii=False, indent=2)
        try:
            os.replace(temporary_path, self.completion_file)
        finally:
            temporary_path.unlink(missing_ok=True)

    def _save_completion_records(
        self,
        records: dict[str, dict[str, object]],
    ) -> None:
        self.completion_file.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            prefix=f".{self.completion_file.stem}-",
            suffix=".json",
            dir=self.completion_file.parent,
            delete=False,
            mode="w",
            encoding="utf-8",
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(records, temporary, ensure_ascii=False, indent=2)
        try:
            os.replace(temporary_path, self.completion_file)
        finally:
            temporary_path.unlink(missing_ok=True)

    def _worksheet(self, workbook: object) -> object:
        if self.sheet_name not in workbook.sheetnames:
            raise WorkbookSchemaError(
                f"Worksheet {self.sheet_name!r} was not found in "
                f"{self.input_file.name}."
            )
        return workbook[self.sheet_name]

    @staticmethod
    def _header_columns(worksheet: object) -> dict[str, int]:
        return {
            _header_key(worksheet.cell(1, column).value): column
            for column in range(1, worksheet.max_column + 1)
            if _header_key(worksheet.cell(1, column).value)
        }

    def _ensure_result_columns(self, worksheet: object) -> dict[str, int]:
        columns = self._header_columns(worksheet)
        created = False
        for header_text, width in self.RESULT_COLUMNS:
            header_key = _header_key(header_text)
            if header_key in columns:
                columns[header_text] = columns[header_key]
                continue
            column = worksheet.max_column + 1
            previous = worksheet.cell(1, column - 1)
            header = worksheet.cell(1, column, header_text)
            if previous.has_style:
                header._style = copy(previous._style)
            header.alignment = copy(previous.alignment)
            header.font = copy(previous.font)
            header.fill = copy(previous.fill)
            header.border = copy(previous.border)
            worksheet.column_dimensions[get_column_letter(column)].width = width
            columns[header_key] = column
            columns[header_text] = column
            created = True
        columns["__created__"] = int(created)
        return columns

    @staticmethod
    def _status_code(value: object) -> str | None:
        text = _normalize_cell(value)
        if text in RESULT_STATUS_LABELS:
            return text
        return LABEL_RESULT_STATUSES.get(text or "")

    def _result_rows(self) -> list[tuple[int, str, str | None]]:
        workbook = load_workbook(self.input_file, read_only=True, data_only=True)
        try:
            worksheet = self._worksheet(workbook)
            columns = self._header_columns(worksheet)
            national_id_column = next(
                (
                    columns[_header_key(alias)]
                    for alias in COLUMN_ALIASES["student_national_id"]
                    if _header_key(alias) in columns
                ),
                None,
            )
            status_column = columns.get(_header_key(ROBOT_STATUS_HEADER))
            if national_id_column is None:
                raise WorkbookSchemaError("Student national-ID column is missing.")
            rows: list[tuple[int, str, str | None]] = []
            for row_number in range(2, worksheet.max_row + 1):
                national_id = _normalize_identifier(
                    worksheet.cell(row_number, national_id_column).value,
                    10,
                ) or ""
                status = (
                    self._status_code(worksheet.cell(row_number, status_column).value)
                    if status_column is not None
                    else None
                )
                rows.append((row_number, national_id, status))
            return rows
        finally:
            workbook.close()

    def successful_national_ids(self) -> set[str]:
        completion_records = self._load_completion_records()
        ids = set(completion_records)
        workbook_ids = {
            national_id
            for _, national_id, status in self._result_rows()
            if status == "SUCCESS" and national_id
        }
        ids.update(workbook_ids)

        # Best-effort synchronization: a locked students.xlsx must never cause a
        # student whose final registration succeeded to be submitted again.
        for national_id, record in completion_records.items():
            if national_id in workbook_ids:
                continue
            try:
                self.upsert(
                    row_number=int(record["row_number"]),
                    student_national_id=national_id,
                    status="SUCCESS",
                    selected_grade=str(record["selected_grade"]),
                )
            except (OSError, KeyError, TypeError, ValueError):
                break
        return ids

    def sync_completion_journal_from_workbook(self) -> None:
        """Backfill the JSON safety journal from successful workbook rows."""
        workbook = load_workbook(self.input_file, read_only=True, data_only=True)
        try:
            worksheet = self._worksheet(workbook)
            columns = self._header_columns(worksheet)
            national_id_column = next(
                (
                    columns[_header_key(alias)]
                    for alias in COLUMN_ALIASES["student_national_id"]
                    if _header_key(alias) in columns
                ),
                None,
            )
            status_column = columns.get(_header_key(ROBOT_STATUS_HEADER))
            grade_column = columns.get(_header_key(SELECTED_GRADE_HEADER))
            attempt_column = columns.get(_header_key(LAST_ATTEMPT_HEADER))
            if national_id_column is None or status_column is None:
                return

            completion_records = self._load_completion_records()
            changed = False
            for row_number in range(2, worksheet.max_row + 1):
                if self._status_code(
                    worksheet.cell(row_number, status_column).value
                ) != "SUCCESS":
                    continue
                national_id = _normalize_identifier(
                    worksheet.cell(row_number, national_id_column).value,
                    10,
                )
                if not national_id or national_id in completion_records:
                    continue
                grade = (
                    _normalize_cell(worksheet.cell(row_number, grade_column).value)
                    if grade_column is not None
                    else ""
                )
                attempted = (
                    worksheet.cell(row_number, attempt_column).value
                    if attempt_column is not None
                    else None
                )
                if isinstance(attempted, datetime):
                    completed_at = attempted.astimezone().isoformat(timespec="seconds")
                else:
                    completed_at = str(attempted or "")
                completion_records[national_id] = {
                    "row_number": row_number,
                    "selected_grade": grade or "",
                    "completed_at": completed_at,
                }
                changed = True
        finally:
            workbook.close()

        if changed:
            self._save_completion_records(completion_records)

    def successful_keys(self) -> set[tuple[int, str]]:
        return {
            (row_number, national_id)
            for row_number, national_id, status in self._result_rows()
            if status == "SUCCESS" and national_id
        }

    def latest_statuses(self) -> dict[str, str]:
        """Return the most recently written result status for each national ID."""
        return {
            national_id: status
            for _, national_id, status in self._result_rows()
            if national_id and status is not None
        }

    def latest_statuses_by_row(self) -> dict[int, str]:
        """Return the most recently written result status for each source row."""
        return {
            row_number: status
            for row_number, _, status in self._result_rows()
            if status is not None
        }

    def mark_pending_for_retry(
        self,
        *,
        row_number: int,
        student_national_id: str,
    ) -> None:
        """Honor a retry request, including a previously recorded success."""
        self.upsert(
            row_number=row_number,
            student_national_id=student_national_id,
            status="PENDING",
            preserve_details=True,
        )
        completion_records = self._load_completion_records()
        if student_national_id not in completion_records:
            return
        completion_records.pop(student_national_id, None)
        self._save_completion_records(completion_records)

    def record_success(
        self,
        *,
        row_number: int,
        student_national_id: str,
        selected_grade: str,
    ) -> bool:
        """Record success durably; return whether students.xlsx was updated."""
        self._record_completion(
            row_number=row_number,
            student_national_id=student_national_id,
            selected_grade=selected_grade,
        )
        try:
            self.upsert(
                row_number=row_number,
                student_national_id=student_national_id,
                status="SUCCESS",
                selected_grade=selected_grade,
            )
        except OSError:
            return False
        return True

    def upsert(
        self,
        *,
        row_number: int,
        student_national_id: str,
        status: str,
        selected_grade: str = "",
        error_message: str = "",
        preserve_details: bool = False,
    ) -> None:
        if status not in {
            "SUCCESS",
            "FAILED",
            "PENDING",
            "INCOMPLETE_PARENT_INFO",
            "INCOMPLETE_STUDENT_INFO",
            "INVALID_STUDENT_NATIONAL_ID",
            "INVALID_EXCEL_DATA",
            "INCOMPLETE_FATHER_INFO",
            "INCOMPLETE_MOTHER_INFO",
        }:
            raise ValueError(f"Unsupported result status: {status}")

        workbook = load_workbook(self.input_file)
        try:
            worksheet = self._worksheet(workbook)
            columns = self._ensure_result_columns(worksheet)
            worksheet.cell(
                row_number,
                columns[ROBOT_STATUS_HEADER],
                RESULT_STATUS_LABELS[status],
            )
            if not preserve_details:
                worksheet.cell(
                    row_number,
                    columns[SELECTED_GRADE_HEADER],
                    selected_grade or None,
                )
                worksheet.cell(
                    row_number,
                    columns[LAST_ERROR_HEADER],
                    error_message or None,
                )
                worksheet.cell(
                    row_number,
                    columns[LAST_ATTEMPT_HEADER],
                    datetime.now().astimezone().isoformat(timespec="seconds"),
                )
            self._atomic_save(workbook)
        except Exception:
            workbook.close()
            raise

    def ensure_columns(self) -> None:
        workbook = load_workbook(self.input_file)
        try:
            worksheet = self._worksheet(workbook)
            columns = self._ensure_result_columns(worksheet)
            if columns["__created__"]:
                self._atomic_save(workbook)
            else:
                workbook.close()
        except Exception:
            workbook.close()
            raise

    def _atomic_save(self, workbook: object) -> None:
        with NamedTemporaryFile(
            prefix=f".{self.input_file.stem}-",
            suffix=".xlsx",
            dir=self.input_file.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
        try:
            workbook.save(temporary_path)
            workbook.close()
            os.replace(temporary_path, self.input_file)
        finally:
            temporary_path.unlink(missing_ok=True)
