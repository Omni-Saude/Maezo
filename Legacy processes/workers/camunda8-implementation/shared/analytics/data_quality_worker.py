"""
DataQualityWorker - Zeebe worker for data quality validation and cleansing.

This worker implements data quality management for the Brazilian healthcare revenue cycle:
- Missing required field detection
- Data format validation
- Duplicate record identification
- Data completeness metrics
- Data quality trend analysis
- Automatic data cleansing recommendations

Business Rule: HIMSS Data Quality Standards & ANS Operational Requirements
Industry Standard: HIMSS Data Quality Capabilities Model, Healthcare Data Standards (HL7, FHIR)
KPI Reference:
  - Data Completeness: Target 100% for required fields
  - Duplicate Detection Rate: Industry standard <0.5%
  - Data Quality Score: Target 95%+
  - Format Compliance: Target 99%+
  - Record Validation Pass Rate: Target 98%+

Migrated from Java DataQualityDelegate.

Topic: data-quality
BPMN Task: Task_Data_Quality
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from collections import defaultdict
import re

import structlog
from pydantic import BaseModel, Field, ConfigDict, ValidationError

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


class DataIssue(BaseModel):
    """Model for a data quality issue."""
    model_config = ConfigDict(populate_by_name=True)

    issue_id: str = Field(..., alias="issueId")
    issue_type: str = Field(..., alias="issueType")  # MISSING, FORMAT, DUPLICATE, etc.
    field_name: str = Field(..., alias="fieldName")
    record_id: str = Field(..., alias="recordId")
    description: str
    severity: str = Field(..., )  # LOW, MEDIUM, HIGH, CRITICAL
    detected_at: datetime = Field(..., alias="detectedAt")


class DataQualityInput(BaseModel):
    """Input model for data quality validation."""
    model_config = ConfigDict(populate_by_name=True)

    data_source: str = Field(..., alias="dataSource")  # CLAIMS, PATIENTS, CONTRACTS
    facility_id: str = Field(..., alias="facilityId")
    batch_size: int = Field(default=100, alias="batchSize")
    records: list[dict[str, Any]] = Field(default_factory=list)
    required_fields: list[str] = Field(default_factory=list, alias="requiredFields")


class DataQualityOutput(BaseModel):
    """Output model for data quality assessment."""
    model_config = ConfigDict(populate_by_name=True)

    validation_complete: bool = Field(..., alias="validationComplete")
    data_source: str = Field(..., alias="dataSource")
    records_checked: int = Field(..., alias="recordsChecked")
    quality_score: Decimal = Field(..., alias="qualityScore")  # 0-100
    missing_fields_count: int = Field(..., alias="missingFieldsCount")
    duplicate_count: int = Field(..., alias="duplicateCount")
    format_errors_count: int = Field(..., alias="formatErrorsCount")
    completeness_rate: Decimal = Field(..., alias="completenessRate")  # 0-100
    quality_status: str = Field(..., alias="qualityStatus")  # PASS, WARN, FAIL
    issues: list[DataIssue] = Field(default_factory=list)
    issues_summary: dict[str, int] = Field(..., alias="issuesSummary")
    validation_timestamp: datetime = Field(..., alias="validationTimestamp")


class DataQualityError(BpmnErrorException):
    """Raised when data quality validation fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="DATA_QUALITY_ERROR",
            message=message,
            details=details,
        )


@worker(topic="data-quality", max_jobs=16, lock_duration=45000)
class DataQualityWorker(BaseWorker):
    """
    Zeebe worker for data quality validation and monitoring.

    This worker:
    1. Validates required fields presence
    2. Checks data format consistency
    3. Identifies duplicate records
    4. Calculates completeness metrics
    5. Detects data anomalies
    6. Generates quality scores

    Input Variables:
        - dataSource: Data source (CLAIMS, PATIENTS, CONTRACTS)
        - facilityId: Hospital facility identifier
        - batchSize: Number of records to validate
        - records: List of data records to validate
        - requiredFields: List of required field names

    Output Variables:
        - validationComplete: Whether validation completed
        - dataSource: Source being validated
        - recordsChecked: Number of records checked
        - qualityScore: Quality percentage (0-100)
        - missingFieldsCount: Count of missing required fields
        - duplicateCount: Count of duplicate records
        - formatErrorsCount: Count of format validation errors
        - completenessRate: Data completeness percentage
        - qualityStatus: PASS/WARN/FAIL
        - issues: List of detected quality issues
        - issuesSummary: Summary of issues by type
        - validationTimestamp: When validation was performed
    """

    # Required fields by data source
    REQUIRED_FIELDS = {
        "CLAIMS": ["claimId", "patientId", "facilityId", "serviceDate", "amount"],
        "PATIENTS": ["patientId", "name", "dateOfBirth", "cpf"],
        "CONTRACTS": ["contractId", "payerId", "facilityId", "startDate"],
    }

    def __init__(self, settings=None, service=None, **kwargs):
        """
        Initialize the worker.

        Args:
            settings: Optional worker settings
            service: Optional service (for testing)
        """
        super().__init__(settings=settings)
        self._service = service

    @property
    def operation_name(self) -> str:
        """Operation name for logging."""
        return "data_quality_validation"

    @property
    def requires_idempotency(self) -> bool:
        """Data quality checks are read-only, no idempotency needed."""
        return False

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the data quality validation task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with quality assessment
        """
        self._logger.info(
            "Starting data quality validation",
            data_source=variables.get("dataSource"),
            facility_id=variables.get("facilityId"),
        )

        try:
            # Parse and validate input
            input_data = DataQualityInput.model_validate(variables)

            # Get required fields for data source
            required_fields = input_data.required_fields or self.REQUIRED_FIELDS.get(
                input_data.data_source, []
            )

            # Validate records
            issues = []
            missing_fields_count = 0
            duplicate_count = 0
            format_errors_count = 0

            # Check for duplicates
            duplicate_ids = self._find_duplicates(input_data.records)
            duplicate_count = len(duplicate_ids)

            # Check each record
            seen_ids = set()
            for record in input_data.records:
                record_id = record.get("id") or record.get("recordId", "unknown")

                # Check for duplicate
                if record_id in seen_ids:
                    issues.append(
                        DataIssue(
                            issueId=f"DUP-{record_id}",
                            issueType="DUPLICATE",
                            fieldName="id",
                            recordId=record_id,
                            description=f"Duplicate record ID: {record_id}",
                            severity="MEDIUM",
                            detectedAt=datetime.utcnow(),
                        )
                    )
                seen_ids.add(record_id)

                # Check required fields
                for field in required_fields:
                    if field not in record or record[field] is None or record[field] == "":
                        missing_fields_count += 1
                        issues.append(
                            DataIssue(
                                issueId=f"MISS-{record_id}-{field}",
                                issueType="MISSING",
                                fieldName=field,
                                recordId=record_id,
                                description=f"Required field '{field}' is missing",
                                severity="HIGH",
                                detectedAt=datetime.utcnow(),
                            )
                        )

                # Check format for specific fields
                format_issues = self._validate_formats(record)
                format_errors_count += len(format_issues)
                issues.extend(format_issues)

            # Calculate metrics
            record_count = len(input_data.records)
            completeness_rate = (
                Decimal(record_count - missing_fields_count)
                / max(1, record_count * len(required_fields))
                * 100
            )
            quality_score = Decimal(100) - (
                Decimal(len(issues)) / max(1, record_count) * 10
            )
            quality_score = max(Decimal("0"), min(Decimal("100"), quality_score))

            # Determine status
            if quality_score >= 95:
                quality_status = "PASS"
            elif quality_score >= 80:
                quality_status = "WARN"
            else:
                quality_status = "FAIL"

            # Build issues summary
            issues_summary = defaultdict(int)
            for issue in issues:
                issues_summary[issue.issue_type] += 1

            # Create output
            output = DataQualityOutput(
                validationComplete=True,
                dataSource=input_data.data_source,
                recordsChecked=record_count,
                qualityScore=quality_score,
                missingFieldsCount=missing_fields_count,
                duplicateCount=duplicate_count,
                formatErrorsCount=format_errors_count,
                completenessRate=completeness_rate,
                qualityStatus=quality_status,
                issues=issues[:100],  # Limit to first 100 issues
                issuesSummary=dict(issues_summary),
                validationTimestamp=datetime.utcnow(),
            )

            self._logger.info(
                "Data quality validation completed",
                data_source=input_data.data_source,
                quality_score=str(quality_score),
                status=quality_status,
            )

            return WorkerResult.ok(output.model_dump(by_alias=True))

        except ValidationError as e:
            self._logger.error("Data quality validation error", errors=e.errors())
            return WorkerResult.bpmn_error(
                error_code="INVALID_DQ_DATA",
                error_message=f"Validation failed: {e}",
            )

        except DataQualityError as e:
            self._logger.error("Data quality error", error=str(e))
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.message,
            )

        except Exception as e:
            self._logger.error("Unexpected error in data quality validation", error=str(e), exc_info=True)
            return WorkerResult.failure(
                error_message=f"Data quality validation failed: {e}",
                retry=True,
            )

    def _find_duplicates(self, records: list[dict[str, Any]]) -> set[str]:
        """
        Find duplicate records.

        Args:
            records: List of records

        Returns:
            Set of duplicate record IDs
        """
        seen = {}
        duplicates = set()

        for record in records:
            record_id = record.get("id") or record.get("recordId")
            if record_id:
                if record_id in seen:
                    duplicates.add(record_id)
                seen[record_id] = True

        return duplicates

    def _validate_formats(self, record: dict[str, Any]) -> list[DataIssue]:
        """
        Validate data formats for a record.

        Args:
            record: Record to validate

        Returns:
            List of format validation issues
        """
        issues = []
        record_id = record.get("id") or record.get("recordId", "unknown")

        # Validate email format if present
        if "email" in record and record["email"]:
            email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
            if not re.match(email_pattern, str(record["email"])):
                issues.append(
                    DataIssue(
                        issueId=f"FMT-{record_id}-email",
                        issueType="FORMAT",
                        fieldName="email",
                        recordId=record_id,
                        description=f"Invalid email format: {record['email']}",
                        severity="MEDIUM",
                        detectedAt=datetime.utcnow(),
                    )
                )

        # Validate amount fields
        for field in ["amount", "paymentAmount", "claimAmount"]:
            if field in record and record[field] is not None:
                try:
                    amount = Decimal(str(record[field]))
                    if amount < 0:
                        issues.append(
                            DataIssue(
                                issueId=f"FMT-{record_id}-{field}",
                                issueType="FORMAT",
                                fieldName=field,
                                recordId=record_id,
                                description=f"Amount cannot be negative: {amount}",
                                severity="HIGH",
                                detectedAt=datetime.utcnow(),
                            )
                        )
                except (ValueError, TypeError):
                    issues.append(
                        DataIssue(
                            issueId=f"FMT-{record_id}-{field}",
                            issueType="FORMAT",
                            fieldName=field,
                            recordId=record_id,
                            description=f"Invalid amount format: {record[field]}",
                            severity="HIGH",
                            detectedAt=datetime.utcnow(),
                        )
                    )

        return issues
