"""Typed data exchanged between the Excel and browser layers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    row_number: int
    field: str
    message: str


@dataclass(frozen=True, slots=True)
class StudentRecord:
    source_row: int
    student_name: str | None
    student_national_id: str | None
    student_birth_date: str | None
    student_birthplace: str | None
    father_name: str | None
    father_national_id: str | None
    father_birth_date: str | None
    father_education: str | None
    father_job: str | None
    mother_name: str | None
    mother_national_id: str | None
    mother_birth_date: str | None
    mother_education: str | None
    mother_job: str | None
    address: str | None
    postal_code: str | None
    phone: str | None
    family_type: str | None = None
    physical_status: str | None = None
    housing_status: str | None = None
    father_phone: str | None = None
    manual_father_first_name: str | None = None
    manual_father_last_name: str | None = None
    manual_father_parent_name: str | None = None
    manual_mother_first_name: str | None = None
    manual_mother_last_name: str | None = None
    manual_mother_parent_name: str | None = None
    robot_status: str | None = None
    selected_grade: str | None = None
    last_error: str | None = None
    last_attempt: str | None = None
    source_values: dict[str, str | None] = field(default_factory=dict, repr=False)

    @property
    def manual_father_info_complete(self) -> bool:
        return all(
            (
                self.manual_father_first_name,
                self.manual_father_last_name,
                self.manual_father_parent_name,
            )
        )

    @property
    def manual_mother_info_complete(self) -> bool:
        return all(
            (
                self.manual_mother_first_name,
                self.manual_mother_last_name,
                self.manual_mother_parent_name,
            )
        )


@dataclass(frozen=True, slots=True)
class StudentLoadResult:
    records: tuple[StudentRecord, ...]
    issues: tuple[ValidationIssue, ...]

    @property
    def valid_row_numbers(self) -> set[int]:
        invalid = {issue.row_number for issue in self.issues}
        return {record.source_row for record in self.records if record.source_row not in invalid}
