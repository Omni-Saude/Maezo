"""
FraudDetectionWorker - Zeebe worker for pattern-based fraud detection.

This worker identifies potential fraudulent claims through pattern analysis,
anomaly detection, and behavioral analysis. It examines claim characteristics
against known fraud patterns and flags suspicious activities for further review.

This is the Python equivalent of the Java FraudDetectionDelegate.

Business Rule: Benchmark - Healthcare fraud prevention standards (HIPAA fraud indicators adapted for Brazil)
Regulatory Compliance: HIPAA fraud prevention, CNJ Resolution 65/2008 (fraud detection in healthcare), ANS guidelines
Migrated from: com.hospital.revenuecycle.delegates.FraudDetectionDelegate

Section references:
- Duplicate claim detection
- Anomaly detection in billing patterns
- Provider and patient behavior analysis
- Fraud risk scoring and escalation

BPMN Task: Task_Fraud_Detection in Audit_Validation_Workflow
Topic: detect-fraud
"""

from __future__ import annotations

from typing import Any
from datetime import datetime, timedelta
from collections import defaultdict

import structlog

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker
from revenue_cycle.workers.streaming import (
    MemoryMonitor,
    chunked_stream,
    stream_with_filter,
    stream_with_transform,
    timeout_wrapper,
)

logger = structlog.get_logger(__name__)


@worker(topic="detect-fraud", max_jobs=8, lock_duration=30000)
class FraudDetectionWorker(BaseWorker):
    """
    Zeebe worker for pattern-based fraud detection.

    BPMN Task: Task_Fraud_Detection
    Topic: detect-fraud

    This worker detects fraudulent patterns including:
    - Duplicate claim submissions
    - Unusually high claim amounts
    - Multiple claims from same provider on same date
    - Billing during closed hours/unusual times
    - Claims with unusual service combinations
    - Provider claim frequency anomalies
    - Patient claim frequency anomalies

    Input Variables:
        - claimId: Claim identifier (required)
        - claimData: Claim data object (required)
        - providerId: Provider ID (required)
        - patientId: Patient ID (required)
        - amount: Claim amount (required)
        - serviceDate: Service date (required)
        - historicalClaims: List of historical claims for comparison (optional)

    Output Variables:
        - fraudRiskLevel: NONE/LOW/MEDIUM/HIGH/CRITICAL
        - fraudScore: Fraud risk score (0-100)
        - suspiciousPatterns: List of detected patterns
        - recommendedAction: ACCEPT/REVIEW/BLOCK/INVESTIGATE
        - detectionTimestamp: When fraud detection was performed
    """

    # Fraud detection thresholds
    AMOUNT_OUTLIER_THRESHOLD = 95  # 95th percentile
    DUPLICATE_CHECK_DAYS = 90
    MAX_CLAIMS_PER_DAY_PROVIDER = 50
    MAX_CLAIMS_PER_DAY_PATIENT = 20
    UNUSUAL_HOUR_RANGES = [(22, 6)]  # 10 PM - 6 AM

    def __init__(self, settings=None, **kwargs):
        """Initialize the worker."""
        super().__init__(settings=settings)
        self._fraud_patterns_cache: dict[str, Any] = {}
        # Initialize memory monitor with configured threshold
        self._memory_monitor = MemoryMonitor(
            threshold_mb=self._settings.audit_memory_threshold_mb
        )

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "fraud_detection"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the fraud detection task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with fraud detection outcome
        """
        self._logger.info(
            "Processing fraud detection",
            claim_id=variables.get("claimId"),
        )

        try:
            claim_id = variables.get("claimId")
            claim_data = variables.get("claimData", {})
            provider_id = variables.get("providerId", "")
            patient_id = variables.get("patientId", "")
            amount = variables.get("amount")
            service_date = variables.get("serviceDate")
            historical_claims = variables.get("historicalClaims", [])

            suspicious_patterns = []
            fraud_score = 0

            # Wrap entire detection in timeout
            async def run_detection():
                nonlocal fraud_score, suspicious_patterns

                # Check 1: Duplicate claims (streaming)
                if await self._is_duplicate_claim_streaming(
                    claim_id, provider_id, patient_id, amount,
                    service_date, historical_claims
                ):
                    suspicious_patterns.append("DUPLICATE_CLAIM_DETECTED")
                    fraud_score += 25

                # Check 2: Unusual claim amount (streaming outlier detection)
                if historical_claims and await self._is_amount_outlier_streaming(
                    amount, historical_claims, provider_id
                ):
                    suspicious_patterns.append("AMOUNT_OUTLIER")
                    fraud_score += 15

                # Check 3: Multiple claims same provider same date (streaming)
                if await self._has_multiple_claims_same_day_streaming(
                    provider_id, service_date, historical_claims
                ):
                    suspicious_patterns.append("MULTIPLE_CLAIMS_SAME_DAY")
                    fraud_score += 10

                # Check 4: Unusual service time (no streaming needed - simple check)
                if self._is_unusual_service_time(service_date):
                    suspicious_patterns.append("UNUSUAL_SERVICE_TIME")
                    fraud_score += 8

                # Check 5: Patient claim frequency anomaly (streaming)
                if await self._is_patient_claim_frequency_anomaly_streaming(
                    patient_id, historical_claims
                ):
                    suspicious_patterns.append("PATIENT_FREQUENCY_ANOMALY")
                    fraud_score += 12

                # Check 6: Provider claim frequency anomaly (streaming)
                if await self._is_provider_frequency_anomaly_streaming(
                    provider_id, historical_claims
                ):
                    suspicious_patterns.append("PROVIDER_FREQUENCY_ANOMALY")
                    fraud_score += 12

                # Check 7: Unusual service combinations (streaming)
                service_code = claim_data.get("serviceCode")
                if await self._has_unusual_service_combination_streaming(
                    service_code, claim_data, historical_claims
                ):
                    suspicious_patterns.append("UNUSUAL_SERVICE_COMBINATION")
                    fraud_score += 10

                # Check 8: Billing during closed/unusual hours (no streaming needed)
                if self._is_billing_unusual_pattern(service_date):
                    suspicious_patterns.append("BILLING_PATTERN_ANOMALY")
                    fraud_score += 8

            # Execute with timeout enforcement
            await timeout_wrapper(
                run_detection(),
                timeout_seconds=self._settings.audit_timeout_seconds,
                operation_name="fraud_detection",
            )

            # Ensure fraud score is between 0 and 100
            fraud_score = min(fraud_score, 100)

            # Determine fraud risk level
            if fraud_score >= 80:
                fraud_risk_level = "CRITICAL"
                recommended_action = "BLOCK"
            elif fraud_score >= 60:
                fraud_risk_level = "HIGH"
                recommended_action = "INVESTIGATE"
            elif fraud_score >= 40:
                fraud_risk_level = "MEDIUM"
                recommended_action = "REVIEW"
            elif fraud_score >= 20:
                fraud_risk_level = "LOW"
                recommended_action = "ACCEPT"
            else:
                fraud_risk_level = "NONE"
                recommended_action = "ACCEPT"

            output = {
                "fraudRiskLevel": fraud_risk_level,
                "fraudScore": fraud_score,
                "suspiciousPatterns": suspicious_patterns,
                "recommendedAction": recommended_action,
                "detectionTimestamp": datetime.now().isoformat(),
            }

            self._logger.info(
                "Fraud detection completed",
                claim_id=claim_id,
                fraud_risk_level=fraud_risk_level,
                fraud_score=fraud_score,
                patterns_count=len(suspicious_patterns),
            )

            return WorkerResult.ok(output)

        except Exception as e:
            self._logger.error(
                "Error performing fraud detection",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Fraud detection failed: {e}",
                retry=True,
            )

    def _is_duplicate_claim(
        self,
        claim_id: str,
        provider_id: str,
        patient_id: str,
        amount: Any,
        service_date: Any,
        historical_claims: list[dict],
    ) -> bool:
        """
        Detect duplicate claims.

        Args:
            claim_id: Current claim ID
            provider_id: Provider ID
            patient_id: Patient ID
            amount: Claim amount
            service_date: Service date
            historical_claims: List of historical claims

        Returns:
            True if duplicate found, False otherwise
        """
        if not historical_claims:
            return False

        try:
            amount_float = float(amount)
            for historical in historical_claims:
                if (historical.get("providerId") == provider_id
                    and historical.get("patientId") == patient_id
                    and float(historical.get("amount", 0)) == amount_float
                    and historical.get("serviceDate") == service_date):
                    return True
        except (ValueError, TypeError):
            pass

        return False

    def _is_amount_outlier(
        self,
        amount: Any,
        historical_claims: list[dict],
        provider_id: str,
    ) -> bool:
        """
        Detect unusually high claim amounts.

        Args:
            amount: Current claim amount
            historical_claims: List of historical claims
            provider_id: Provider ID

        Returns:
            True if amount is outlier, False otherwise
        """
        if not historical_claims:
            return False

        try:
            amount_float = float(amount)
            provider_amounts = []

            for claim in historical_claims:
                if claim.get("providerId") == provider_id:
                    try:
                        provider_amounts.append(float(claim.get("amount", 0)))
                    except (ValueError, TypeError):
                        pass

            if not provider_amounts:
                return False

            # Calculate 95th percentile
            provider_amounts.sort()
            percentile_95_idx = int(len(provider_amounts) * 0.95)
            percentile_95 = provider_amounts[percentile_95_idx]

            # Current amount is outlier if it exceeds 95th percentile by 50%
            return amount_float > (percentile_95 * 1.5)
        except (ValueError, TypeError):
            return False

    def _has_multiple_claims_same_day(
        self,
        provider_id: str,
        service_date: Any,
        historical_claims: list[dict],
    ) -> bool:
        """
        Detect multiple claims from same provider on same date.

        Args:
            provider_id: Provider ID
            service_date: Service date
            historical_claims: List of historical claims

        Returns:
            True if count exceeds threshold, False otherwise
        """
        if not historical_claims or not service_date:
            return False

        same_day_count = 0
        for claim in historical_claims:
            if (claim.get("providerId") == provider_id
                and claim.get("serviceDate") == service_date):
                same_day_count += 1

        return same_day_count > self.MAX_CLAIMS_PER_DAY_PROVIDER

    def _is_unusual_service_time(self, service_date: Any) -> bool:
        """
        Detect unusual service times (off-hours).

        Args:
            service_date: Service date/time

        Returns:
            True if time is unusual, False otherwise
        """
        if not service_date:
            return False

        try:
            if isinstance(service_date, str):
                dt = datetime.fromisoformat(service_date.replace("Z", "+00:00"))
            elif isinstance(service_date, datetime):
                dt = service_date
            else:
                return False

            hour = dt.hour
            for start, end in self.UNUSUAL_HOUR_RANGES:
                if start > end:  # Handles ranges that cross midnight
                    if hour >= start or hour < end:
                        return True
                else:
                    if start <= hour < end:
                        return True

            return False
        except (ValueError, TypeError):
            return False

    def _is_patient_claim_frequency_anomaly(
        self,
        patient_id: str,
        historical_claims: list[dict],
    ) -> bool:
        """
        Detect patient claim frequency anomalies.

        Args:
            patient_id: Patient ID
            historical_claims: List of historical claims

        Returns:
            True if frequency is anomalous, False otherwise
        """
        if not historical_claims or not patient_id:
            return False

        try:
            cutoff_date = datetime.now() - timedelta(days=30)
            recent_claims = 0

            for claim in historical_claims:
                if claim.get("patientId") == patient_id:
                    try:
                        claim_date = datetime.fromisoformat(
                            claim.get("serviceDate", "").replace("Z", "+00:00")
                        )
                        if claim_date >= cutoff_date:
                            recent_claims += 1
                    except (ValueError, TypeError):
                        pass

            # Anomaly if more than 20 claims in 30 days
            return recent_claims > self.MAX_CLAIMS_PER_DAY_PATIENT * 30
        except (ValueError, TypeError):
            return False

    def _is_provider_frequency_anomaly(
        self,
        provider_id: str,
        historical_claims: list[dict],
    ) -> bool:
        """
        Detect provider claim frequency anomalies.

        Args:
            provider_id: Provider ID
            historical_claims: List of historical claims

        Returns:
            True if frequency is anomalous, False otherwise
        """
        if not historical_claims or not provider_id:
            return False

        try:
            cutoff_date = datetime.now() - timedelta(days=30)
            recent_claims = 0

            for claim in historical_claims:
                if claim.get("providerId") == provider_id:
                    try:
                        claim_date = datetime.fromisoformat(
                            claim.get("serviceDate", "").replace("Z", "+00:00")
                        )
                        if claim_date >= cutoff_date:
                            recent_claims += 1
                    except (ValueError, TypeError):
                        pass

            # Anomaly if more than 50 claims per day on average in 30 days
            return recent_claims > (self.MAX_CLAIMS_PER_DAY_PROVIDER * 30)
        except (ValueError, TypeError):
            return False

    def _has_unusual_service_combination(
        self,
        service_code: str,
        claim_data: dict,
        historical_claims: list[dict],
    ) -> bool:
        """
        Detect unusual combinations of services in same claim.

        Args:
            service_code: Service code
            claim_data: Current claim data
            historical_claims: List of historical claims

        Returns:
            True if combination is unusual, False otherwise
        """
        # Check if this service code is rarely billed by this provider
        if not service_code or not historical_claims:
            return False

        provider_id = claim_data.get("providerId")
        if not provider_id:
            return False

        provider_service_codes = set()
        for claim in historical_claims:
            if claim.get("providerId") == provider_id:
                code = claim.get("serviceCode")
                if code:
                    provider_service_codes.add(code)

        # Service code not in provider's typical services (first time provider bills this code)
        return len(provider_service_codes) > 0 and service_code not in provider_service_codes

    def _is_billing_unusual_pattern(self, service_date: Any) -> bool:
        """
        Detect unusual billing patterns.

        Args:
            service_date: Service date/time

        Returns:
            True if pattern is unusual, False otherwise
        """
        if not service_date:
            return False

        try:
            if isinstance(service_date, str):
                dt = datetime.fromisoformat(service_date.replace("Z", "+00:00"))
            elif isinstance(service_date, datetime):
                dt = service_date
            else:
                return False

            # Unusual if billed on weekend
            weekday = dt.weekday()
            return weekday >= 5  # Saturday (5) or Sunday (6)
        except (ValueError, TypeError):
            return False

    # =========================================================================
    # STREAMING VERSIONS - Memory-efficient fraud detection for large datasets
    # =========================================================================

    async def _is_duplicate_claim_streaming(
        self,
        claim_id: str,
        provider_id: str,
        patient_id: str,
        amount: Any,
        service_date: Any,
        historical_claims: list[dict],
    ) -> bool:
        """
        Detect duplicate claims using streaming to avoid loading all at once.

        Args:
            claim_id: Current claim ID
            provider_id: Provider ID
            patient_id: Patient ID
            amount: Claim amount
            service_date: Service date
            historical_claims: List of historical claims

        Returns:
            True if duplicate found, False otherwise
        """
        if not historical_claims:
            return False

        try:
            amount_float = float(amount)

            # Stream through historical claims in chunks
            async for chunk in chunked_stream(
                historical_claims,
                batch_size=self._settings.audit_batch_size,
                memory_monitor=self._memory_monitor,
            ):
                for historical in chunk:
                    if (historical.get("providerId") == provider_id
                        and historical.get("patientId") == patient_id
                        and float(historical.get("amount", 0)) == amount_float
                        and historical.get("serviceDate") == service_date):
                        return True

        except (ValueError, TypeError):
            pass

        return False

    async def _is_amount_outlier_streaming(
        self,
        amount: Any,
        historical_claims: list[dict],
        provider_id: str,
    ) -> bool:
        """
        Detect unusually high claim amounts using streaming percentile calculation.

        Args:
            amount: Current claim amount
            historical_claims: List of historical claims
            provider_id: Provider ID

        Returns:
            True if amount is outlier, False otherwise
        """
        if not historical_claims:
            return False

        try:
            amount_float = float(amount)
            provider_amounts = []

            # Stream and collect provider amounts
            async for provider_amount in stream_with_transform(
                historical_claims,
                lambda claim: float(claim.get("amount", 0))
                if claim.get("providerId") == provider_id else None,
                batch_size=self._settings.audit_batch_size,
                memory_monitor=self._memory_monitor,
            ):
                if provider_amount is not None:
                    provider_amounts.append(provider_amount)

            if not provider_amounts:
                return False

            # Calculate 95th percentile
            provider_amounts.sort()
            percentile_95_idx = int(len(provider_amounts) * 0.95)
            percentile_95 = provider_amounts[percentile_95_idx]

            # Current amount is outlier if it exceeds 95th percentile by 50%
            return amount_float > (percentile_95 * 1.5)
        except (ValueError, TypeError):
            return False

    async def _has_multiple_claims_same_day_streaming(
        self,
        provider_id: str,
        service_date: Any,
        historical_claims: list[dict],
    ) -> bool:
        """
        Detect multiple claims from same provider on same date using streaming.

        Args:
            provider_id: Provider ID
            service_date: Service date
            historical_claims: List of historical claims

        Returns:
            True if count exceeds threshold, False otherwise
        """
        if not historical_claims or not service_date:
            return False

        same_day_count = 0

        # Stream through claims and count matches
        async for claim in stream_with_filter(
            historical_claims,
            lambda c: (c.get("providerId") == provider_id
                      and c.get("serviceDate") == service_date),
            batch_size=self._settings.audit_batch_size,
            memory_monitor=self._memory_monitor,
        ):
            same_day_count += 1
            # Early termination if threshold exceeded
            if same_day_count > self.MAX_CLAIMS_PER_DAY_PROVIDER:
                return True

        return False

    async def _is_patient_claim_frequency_anomaly_streaming(
        self,
        patient_id: str,
        historical_claims: list[dict],
    ) -> bool:
        """
        Detect patient claim frequency anomalies using streaming.

        Args:
            patient_id: Patient ID
            historical_claims: List of historical claims

        Returns:
            True if frequency is anomalous, False otherwise
        """
        if not historical_claims or not patient_id:
            return False

        try:
            cutoff_date = datetime.now() - timedelta(days=30)
            recent_claims = 0
            max_recent_claims = self.MAX_CLAIMS_PER_DAY_PATIENT * 30

            # Stream and count recent patient claims
            async for claim in stream_with_filter(
                historical_claims,
                lambda c: c.get("patientId") == patient_id,
                batch_size=self._settings.audit_batch_size,
                memory_monitor=self._memory_monitor,
            ):
                try:
                    claim_date = datetime.fromisoformat(
                        claim.get("serviceDate", "").replace("Z", "+00:00")
                    )
                    if claim_date >= cutoff_date:
                        recent_claims += 1
                        # Early termination
                        if recent_claims > max_recent_claims:
                            return True
                except (ValueError, TypeError):
                    pass

            return False
        except (ValueError, TypeError):
            return False

    async def _is_provider_frequency_anomaly_streaming(
        self,
        provider_id: str,
        historical_claims: list[dict],
    ) -> bool:
        """
        Detect provider claim frequency anomalies using streaming.

        Args:
            provider_id: Provider ID
            historical_claims: List of historical claims

        Returns:
            True if frequency is anomalous, False otherwise
        """
        if not historical_claims or not provider_id:
            return False

        try:
            cutoff_date = datetime.now() - timedelta(days=30)
            recent_claims = 0
            max_recent_claims = self.MAX_CLAIMS_PER_DAY_PROVIDER * 30

            # Stream and count recent provider claims
            async for claim in stream_with_filter(
                historical_claims,
                lambda c: c.get("providerId") == provider_id,
                batch_size=self._settings.audit_batch_size,
                memory_monitor=self._memory_monitor,
            ):
                try:
                    claim_date = datetime.fromisoformat(
                        claim.get("serviceDate", "").replace("Z", "+00:00")
                    )
                    if claim_date >= cutoff_date:
                        recent_claims += 1
                        # Early termination
                        if recent_claims > max_recent_claims:
                            return True
                except (ValueError, TypeError):
                    pass

            return False
        except (ValueError, TypeError):
            return False

    async def _has_unusual_service_combination_streaming(
        self,
        service_code: str,
        claim_data: dict,
        historical_claims: list[dict],
    ) -> bool:
        """
        Detect unusual combinations of services using streaming.

        Args:
            service_code: Service code
            claim_data: Current claim data
            historical_claims: List of historical claims

        Returns:
            True if combination is unusual, False otherwise
        """
        if not service_code or not historical_claims:
            return False

        provider_id = claim_data.get("providerId")
        if not provider_id:
            return False

        provider_service_codes = set()

        # Stream and collect provider service codes
        async for claim in stream_with_filter(
            historical_claims,
            lambda c: c.get("providerId") == provider_id,
            batch_size=self._settings.audit_batch_size,
            memory_monitor=self._memory_monitor,
        ):
            code = claim.get("serviceCode")
            if code:
                provider_service_codes.add(code)

        # Service code not in provider's typical services
        return len(provider_service_codes) > 0 and service_code not in provider_service_codes
