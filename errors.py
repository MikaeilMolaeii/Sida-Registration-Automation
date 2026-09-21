"""Domain exceptions for the SIDA automation project."""


class SidaAutomationError(Exception):
    """Base exception for expected automation failures."""


class ConfigurationError(SidaAutomationError):
    """Raised when required application configuration is missing or invalid."""


class BrowserConnectionError(SidaAutomationError):
    """Raised when the already-running Chrome session cannot be reached."""


class WorkbookSchemaError(SidaAutomationError):
    """Raised when the input workbook does not contain the required structure."""


class PageTransitionError(SidaAutomationError):
    """Raised when a required user-triggered page transition is not detected."""


class InquiryFailedError(SidaAutomationError):
    """Raised when a civil-registry inquiry exhausts its retry limit."""


class FatherInfoIncompleteError(InquiryFailedError):
    """Raised when father inquiry fails and manual identity data is incomplete."""


class MotherInfoIncompleteError(InquiryFailedError):
    """Raised when mother inquiry fails and manual identity data is incomplete."""


class StudentInfoIncompleteError(SidaAutomationError):
    """Raised when SIDA reports incomplete civil-registry data for the student."""


class InvalidStudentNationalIdError(SidaAutomationError):
    """Raised when SIDA reports that the student's national ID is invalid."""


class GradeSubmissionError(SidaAutomationError):
    """Raised when no confirmed final grade submission succeeds."""


class UnknownMappingError(SidaAutomationError):
    """Raised when an Excel value has no safe website mapping."""
