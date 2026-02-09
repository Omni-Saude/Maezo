"""
Patient ID validation for CPF and CNJ formats.

Implements strict validation for Brazilian patient identifiers:
- CPF (Cadastro de Pessoas Físicas): XXX.XXX.XXX-XX with check digits
- CNJ (Conselho Nacional de Justiça): 14-digit format

Security: Validates format and check digits to prevent malformed IDs from reaching
downstream systems (TASY, LIS, PACS).
"""

import re
from typing import Optional
from pydantic import ValidationError, field_validator


class PatientIdValidationError(ValueError):
    """Raised when patient ID validation fails."""

    pass


class PatientIdValidator:
    """
    Validator for Brazilian patient identification formats.

    Supports:
    - CPF (Cadastro de Pessoas Físicas): 11 digits with check digits
    - CNJ (Conselho Nacional de Justiça): 14-digit unique identifier
    """

    # CPF pattern: XXX.XXX.XXX-XX or XXXXXXXXXXX (11 digits)
    CPF_PATTERN = re.compile(r"^\d{3}\.\d{3}\.\d{3}-\d{2}$|^\d{11}$")

    # CNJ pattern: 14 digits
    CNJ_PATTERN = re.compile(r"^\d{14}$")

    @classmethod
    def validate_cpf(cls, value: str) -> str:
        """
        Validate CPF format and check digits.

        Args:
            value: CPF string in format XXX.XXX.XXX-XX or XXXXXXXXXXX

        Returns:
            Normalized CPF (XXX.XXX.XXX-XX format)

        Raises:
            PatientIdValidationError: If CPF is invalid
        """
        if not isinstance(value, str):
            raise PatientIdValidationError(
                f"CPF must be string, got {type(value).__name__}"
            )

        value = value.strip()

        # Check format
        if not cls.CPF_PATTERN.match(value):
            raise PatientIdValidationError(
                f"Invalid CPF format: {value}. Expected XXX.XXX.XXX-XX or XXXXXXXXXXX"
            )

        # Remove formatting
        cpf_digits = value.replace(".", "").replace("-", "")

        # Reject known invalid CPFs
        if cpf_digits == "00000000000" or all(d == cpf_digits[0] for d in cpf_digits):
            raise PatientIdValidationError(
                f"Invalid CPF: {value}. All digits are the same or zero"
            )

        # Validate first check digit (position 9)
        sum_first = 0
        for i in range(9):
            sum_first += int(cpf_digits[i]) * (10 - i)

        remainder_first = sum_first % 11
        check_digit_1 = 0 if remainder_first < 2 else 11 - remainder_first

        if int(cpf_digits[9]) != check_digit_1:
            raise PatientIdValidationError(
                f"Invalid CPF check digit (position 10): {value}"
            )

        # Validate second check digit (position 10)
        sum_second = 0
        for i in range(10):
            sum_second += int(cpf_digits[i]) * (11 - i)

        remainder_second = sum_second % 11
        check_digit_2 = 0 if remainder_second < 2 else 11 - remainder_second

        if int(cpf_digits[10]) != check_digit_2:
            raise PatientIdValidationError(
                f"Invalid CPF check digit (position 11): {value}"
            )

        # Return normalized format
        return f"{cpf_digits[0:3]}.{cpf_digits[3:6]}.{cpf_digits[6:9]}-{cpf_digits[9:11]}"

    @classmethod
    def validate_cnj(cls, value: str) -> str:
        """
        Validate CNJ format (14-digit identifier).

        Args:
            value: 14-digit CNJ identifier

        Returns:
            Normalized CNJ (14 digits)

        Raises:
            PatientIdValidationError: If CNJ is invalid
        """
        if not isinstance(value, str):
            raise PatientIdValidationError(
                f"CNJ must be string, got {type(value).__name__}"
            )

        value = value.strip()

        # Check format
        if not cls.CNJ_PATTERN.match(value):
            raise PatientIdValidationError(
                f"Invalid CNJ format: {value}. Expected 14 digits"
            )

        # Reject all zeros
        if value == "00000000000000":
            raise PatientIdValidationError(f"Invalid CNJ: {value}. All digits are zero")

        # CNJ format validation (basic structural validation)
        # CNJ number format: NNNNNNNNNNNNNNN (14 digits)
        # The format is flexible and primarily relies on length
        return value

    @classmethod
    def validate(cls, value: str) -> str:
        """
        Auto-detect and validate patient ID format.

        Attempts to validate as CPF first, then CNJ.

        Args:
            value: Patient ID string

        Returns:
            Normalized patient ID

        Raises:
            PatientIdValidationError: If neither format is valid
        """
        if not isinstance(value, str):
            raise PatientIdValidationError(
                f"Patient ID must be string, got {type(value).__name__}"
            )

        value = value.strip()

        if not value:
            raise PatientIdValidationError("Patient ID cannot be empty")

        # Try CPF format first (11 or 14 chars with formatting)
        if len(value.replace(".", "").replace("-", "")) == 11:
            try:
                return cls.validate_cpf(value)
            except PatientIdValidationError as cpf_error:
                raise PatientIdValidationError(
                    f"Invalid patient ID format: {value}. "
                    f"CPF validation failed: {str(cpf_error)}"
                ) from cpf_error

        # Try CNJ format (14 digits)
        if len(value) == 14 and value.isdigit():
            try:
                return cls.validate_cnj(value)
            except PatientIdValidationError as cnj_error:
                raise PatientIdValidationError(
                    f"Invalid patient ID format: {value}. "
                    f"CNJ validation failed: {str(cnj_error)}"
                ) from cnj_error

        # Neither format matched
        raise PatientIdValidationError(
            f"Invalid patient ID format: {value}. "
            f"Expected CPF (XXX.XXX.XXX-XX or 11 digits) or CNJ (14 digits)"
        )


def validate_cpf(value: str) -> str:
    """
    Standalone CPF validator for Pydantic field_validator.

    Usage:
        @field_validator('patient_id')
        @classmethod
        def validate_cpf_field(cls, v):
            return validate_cpf(v)

    Args:
        value: CPF string

    Returns:
        Normalized CPF

    Raises:
        ValueError: If CPF is invalid (compatible with Pydantic)
    """
    try:
        return PatientIdValidator.validate_cpf(value)
    except PatientIdValidationError as e:
        raise ValueError(str(e)) from e


def validate_cnj(value: str) -> str:
    """
    Standalone CNJ validator for Pydantic field_validator.

    Usage:
        @field_validator('patient_id')
        @classmethod
        def validate_cnj_field(cls, v):
            return validate_cnj(v)

    Args:
        value: CNJ string

    Returns:
        Normalized CNJ

    Raises:
        ValueError: If CNJ is invalid (compatible with Pydantic)
    """
    try:
        return PatientIdValidator.validate_cnj(value)
    except PatientIdValidationError as e:
        raise ValueError(str(e)) from e


def validate_patient_id(value: str) -> str:
    """
    Standalone patient ID validator for Pydantic field_validator.

    Auto-detects CPF or CNJ format and validates accordingly.

    Usage:
        @field_validator('patient_id')
        @classmethod
        def validate_patient_id_field(cls, v):
            return validate_patient_id(v)

    Args:
        value: Patient ID string

    Returns:
        Normalized patient ID

    Raises:
        ValueError: If patient ID is invalid (compatible with Pydantic)
    """
    try:
        return PatientIdValidator.validate(value)
    except PatientIdValidationError as e:
        raise ValueError(str(e)) from e
