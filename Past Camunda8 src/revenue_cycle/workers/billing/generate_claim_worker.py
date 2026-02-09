"""
GenerateClaimWorker - Zeebe worker for generating TISS claims.

This worker implements the claim generation logic for the Brazilian
healthcare revenue cycle, including:
- TUSS/CBHPM procedure code validation
- Procedure pricing via PricingService
- DMN billing calculation rules
- TISS 4.0 XML generation

Business Rule: RN-BIL-006-SubmitClaim.md (TISS claim format and generation)
Regulatory Compliance: TISS 4.01.00, ANS RN 439/2015, CBHPM 2024, TUSS
Migrated from: com.hospital.revenuecycle.delegates.GenerateClaimDelegate

Section references:
- TISS 4.0 XML structure generation
- CBHPM/TUSS code validation and mapping
- Pricing calculation and validation
- Service guide (guia de cobranca) generation

Topic: generate-claim
BPMN Task: Task_Generate_Claim (Gerar Guia de Cobranca)
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

import structlog
from pydantic import ValidationError

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.services.dmn import DMNService, FallbackDMNService, DMNEvaluationError
from revenue_cycle.services.pricing import PricingService, MockPricingService
from revenue_cycle.services.pricing.pricing_service import PricingError
from revenue_cycle.services.tiss import TissXmlGenerator, TissXmlGenerationError
from revenue_cycle.services.tiss.tiss_xml_generator import ClaimData
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker
from revenue_cycle.workers.billing.models import (
    GenerateClaimInput,
    GenerateClaimOutput,
    ClaimLineItem,
    ClaimType,
    ProcedureType,
)

logger = structlog.get_logger(__name__)

# Maximum claim amount allowed (R$ 1,000,000.00)
MAX_CLAIM_AMOUNT = Decimal("1000000.00")


class InvalidProcedureCodesError(BpmnErrorException):
    """Raised when procedure codes are invalid."""

    def __init__(self, message: str, codes: Optional[List[str]] = None):
        super().__init__(
            error_code="INVALID_PROCEDURE_CODES",
            message=message,
            details={"invalid_codes": codes} if codes else None,
        )


class CalculationError(BpmnErrorException):
    """Raised when calculation fails or exceeds limits."""

    def __init__(self, message: str):
        super().__init__(
            error_code="CALCULATION_ERROR",
            message=message,
        )


class SubmissionDeadlineExceededError(BpmnErrorException):
    """Raised when ANS RN 395/2016 60-day submission deadline is exceeded."""

    def __init__(self, encounter_date: datetime, deadline: datetime):
        super().__init__(
            error_code="SUBMISSION_DEADLINE_EXCEEDED",
            message=(
                f"Claim submission deadline exceeded per ANS RN 395/2016. "
                f"Encounter date: {encounter_date.isoformat()}, "
                f"Deadline: {deadline.isoformat()}"
            ),
            details={
                "encounter_date": encounter_date.isoformat(),
                "deadline": deadline.isoformat(),
            }
        )


@worker(topic="generate-claim", max_jobs=32, lock_duration=30000)
class GenerateClaimWorker(BaseWorker):
    """
    Zeebe worker for generating TISS claims from encounter data.

    This worker:
    1. Validates procedure codes (TUSS/CBHPM formats)
    2. Retrieves pricing from PricingService
    3. Generates unique claim ID
    4. Evaluates DMN billing-calculation rules
    5. Generates TISS 4.0 compliant XML
    6. Validates generated XML

    Input Variables:
        - encounterId: Encounter identifier (required)
        - patientId: Patient identifier (required)
        - procedureCodes: List of TUSS/CBHPM codes (required)
        - insuranceId: Insurance identifier (optional)
        - claimType: Claim type SP_SADT/INTERNACAO/CONSULTA (optional)
        - hasGlosa: Whether there is a glosa (optional)
        - glosaPercentage: Glosa percentage (optional)
        - serviceDate: Date of service (ISO format, for ANS RN 395/2016 validation)

    Output Variables:
        - claimId: Generated claim identifier
        - claimAmount: Total claim amount
        - claimItems: List of claim line items
        - billableAmount: DMN-calculated billable amount
        - finalClaimAmount: Final amount after DMN rules
        - tissXml: Base64-encoded TISS XML
        - needsAudit: Whether claim needs audit review

    Regulatory Compliance:
        - ANS RN 395/2016: Validates 60-day submission deadline
    """

    def __init__(
        self,
        pricing_service: Optional[PricingService] = None,
        dmn_service: Optional[DMNService] = None,
        tiss_generator: Optional[TissXmlGenerator] = None,
        settings: Optional[Any] = None,
    ):
        """
        Initialize GenerateClaimWorker.

        Args:
            pricing_service: Service for procedure pricing lookup
            dmn_service: Service for DMN decision evaluation
            tiss_generator: TISS XML generator
            settings: Application settings
        """
        super().__init__(settings)
        self.pricing_service = pricing_service or MockPricingService()
        self.dmn_service = dmn_service or FallbackDMNService()
        self.tiss_generator = tiss_generator or TissXmlGenerator()
        self._logger = logger.bind(worker="GenerateClaimWorker")

    @property
    def operation_name(self) -> str:
        """Get operation name for idempotency."""
        return "generate_claim"

    @property
    def requires_idempotency(self) -> bool:
        """Claim generation must be idempotent."""
        return True

    def _validate_submission_deadline(self, encounter_date: datetime) -> None:
        """
        Validate ANS RN 395/2016 60-day submission deadline.

        Per ANS Normativa 395/2016, healthcare providers must submit claims
        to health insurers within 60 days of the service date.

        Args:
            encounter_date: Date when service was provided

        Raises:
            SubmissionDeadlineExceededError: If submission deadline exceeded
        """
        deadline = encounter_date + timedelta(days=60)
        if datetime.now() > deadline:
            raise SubmissionDeadlineExceededError(encounter_date, deadline)

    def extract_idempotency_params(self, variables: Dict[str, Any]) -> str:
        """
        Extract parameters for idempotency key generation.

        Uses encounter_id, patient_id, and procedure_codes for deterministic key.
        """
        encounter_id = variables.get("encounterId", "")
        patient_id = variables.get("patientId", "")
        procedure_codes = variables.get("procedureCodes", [])

        # Sort codes for consistent key
        sorted_codes = sorted(procedure_codes) if procedure_codes else []
        codes_str = ":".join(sorted_codes)

        return f"{encounter_id}:{patient_id}:{codes_str}"

    async def process_task(
        self,
        job: Any,
        variables: Dict[str, Any],
    ) -> WorkerResult:
        """
        Process the claim generation task.

        Args:
            job: Camunda external task
            variables: Job variables

        Returns:
            WorkerResult with claim data
        """
        self._logger.info(
            "Processing claim generation",
            job_key=getattr(job, "key", "unknown"),
        )

        try:
            # Parse and validate input
            input_data = self._parse_input(variables)

            self._logger.info(
                "Generating claim",
                encounter_id=input_data.encounter_id,
                patient_id=input_data.patient_id,
                procedure_count=len(input_data.procedure_codes),
                claim_type=input_data.claim_type.value,
            )

            # Validate ANS RN 395/2016 60-day submission deadline
            if input_data.service_date:
                self._validate_submission_deadline(input_data.service_date)

            # Generate unique claim ID
            claim_id = self._generate_claim_id(input_data.encounter_id)

            # Build claim items with pricing
            claim_items = await self._build_claim_items(
                input_data.procedure_codes,
                input_data.insurance_id,
            )

            # Calculate total amount
            claim_amount = self._calculate_total_amount(claim_items)
            self._validate_amount_positive(claim_amount)

            # Evaluate DMN for billing calculation
            dmn_result = await self._evaluate_billing_dmn(
                claim_items=claim_items,
                claim_amount=claim_amount,
                insurance_id=input_data.insurance_id,
                has_glosa=input_data.has_glosa,
                glosa_percentage=input_data.glosa_percentage,
            )

            # Validate DMN results
            self._validate_dmn_result(dmn_result)

            # Generate TISS XML
            tiss_xml, validation_status, validation_messages = await self._generate_tiss_xml(
                claim_id=claim_id,
                input_data=input_data,
                claim_items=claim_items,
                total_amount=claim_amount,
            )

            # Build output
            output = GenerateClaimOutput(
                claim_id=claim_id,
                claim_amount=claim_amount,
                claim_items_count=len(claim_items),
                claim_items=claim_items,
                claim_generated_date=datetime.now(),
                billable_amount=Decimal(str(dmn_result["billableAmount"])),
                discount_applied=Decimal(str(dmn_result["discountApplied"])),
                final_claim_amount=Decimal(str(dmn_result["finalAmount"])),
                calculation_rule=dmn_result["calculationRule"],
                needs_audit=dmn_result["needsAudit"],
                tiss_xml=tiss_xml,
                validation_status=validation_status,
                validation_messages=validation_messages,
            )

            self._logger.info(
                "Claim generated successfully",
                claim_id=claim_id,
                amount=float(claim_amount),
                final_amount=dmn_result["finalAmount"],
                rule=dmn_result["calculationRule"],
                needs_audit=dmn_result["needsAudit"],
            )

            return WorkerResult.ok(output.model_dump(by_alias=True))

        except InvalidProcedureCodesError as e:
            self._logger.warning(
                "Invalid procedure codes",
                error=str(e),
            )
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.message,
            )

        except CalculationError as e:
            self._logger.warning(
                "Calculation error",
                error=str(e),
            )
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.message,
            )

        except SubmissionDeadlineExceededError as e:
            self._logger.warning(
                "Submission deadline exceeded",
                error=str(e),
                details=e.details,
            )
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.message,
                variables=e.details,
            )

        except PricingError as e:
            self._logger.error(
                "Pricing error",
                error=str(e),
                procedure_code=e.procedure_code,
            )
            return WorkerResult.bpmn_error(
                error_code="PRICING_ERROR",
                error_message=f"Pricing lookup failed: {e.message}",
            )

        except DMNEvaluationError as e:
            self._logger.error(
                "DMN evaluation error",
                error=str(e),
                decision_key=e.decision_key,
            )
            return WorkerResult.bpmn_error(
                error_code="CALCULATION_ERROR",
                error_message=f"DMN evaluation failed: {e.message}",
            )

        except TissXmlGenerationError as e:
            self._logger.error(
                "TISS XML generation error",
                error=str(e),
                claim_id=e.claim_id,
            )
            return WorkerResult.bpmn_error(
                error_code="TISS_ERROR",
                error_message=f"TISS XML generation failed: {e.message}",
            )

        except ValidationError as e:
            self._logger.warning(
                "Input validation error",
                errors=e.errors(),
            )
            # Extract first error message
            first_error = e.errors()[0] if e.errors() else {"msg": "Validation failed"}
            return WorkerResult.bpmn_error(
                error_code="INVALID_PROCEDURE_CODES",
                error_message=f"Input validation failed: {first_error.get('msg', str(e))}",
            )

        except Exception as e:
            self._logger.exception(
                "Unexpected error during claim generation",
                error=str(e),
            )
            # Return failure with retry
            return WorkerResult.failure(
                error_message=f"Claim generation failed: {e}",
                retry=True,
            )

    def _parse_input(self, variables: Dict[str, Any]) -> GenerateClaimInput:
        """
        Parse and validate input variables.

        Args:
            variables: Raw job variables

        Returns:
            Validated GenerateClaimInput

        Raises:
            ValidationError: If input is invalid
        """
        return GenerateClaimInput(**variables)

    def _generate_claim_id(self, encounter_id: str) -> str:
        """
        Generate unique claim ID.

        Format: CLM-{encounterId}-{timestamp}

        Args:
            encounter_id: Encounter identifier

        Returns:
            Unique claim identifier
        """
        timestamp = int(datetime.now().timestamp() * 1000)
        return f"CLM-{encounter_id}-{timestamp}"

    async def _build_claim_items(
        self,
        procedure_codes: List[str],
        insurance_id: Optional[str],
    ) -> List[ClaimLineItem]:
        """
        Build claim line items with pricing from PricingService.

        Args:
            procedure_codes: List of TUSS/CBHPM codes
            insurance_id: Insurance for pricing lookup

        Returns:
            List of ClaimLineItem objects

        Raises:
            PricingError: If pricing lookup fails
        """
        claim_items = []

        for idx, code in enumerate(procedure_codes, start=1):
            # Get pricing information
            price = await self.pricing_service.get_procedure_price(
                code, insurance_id
            )
            description = await self.pricing_service.get_procedure_description(code)
            procedure_type = await self.pricing_service.determine_procedure_type(code)

            item = ClaimLineItem(
                line_number=idx,
                procedure_code=code,
                description=description,
                procedure_type=procedure_type,
                quantity=1,
                unit_price=price,
                total_price=price,
            )

            claim_items.append(item)

            self._logger.debug(
                "Built claim item",
                line_number=idx,
                procedure_code=code,
                price=float(price),
                procedure_type=procedure_type,
            )

        return claim_items

    def _calculate_total_amount(
        self,
        claim_items: List[ClaimLineItem],
    ) -> Decimal:
        """
        Calculate total claim amount from line items.

        Args:
            claim_items: List of claim items

        Returns:
            Total amount as Decimal
        """
        total = sum(item.total_price for item in claim_items)
        return Decimal(str(total)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    def _validate_amount_positive(self, amount: Decimal) -> None:
        """
        Validate claim amount is greater than zero.

        Args:
            amount: Amount to validate

        Raises:
            CalculationError: If amount is not positive
        """
        if amount <= 0:
            raise CalculationError(
                "Calculated claim amount must be greater than zero"
            )

    async def _evaluate_billing_dmn(
        self,
        claim_items: List[ClaimLineItem],
        claim_amount: Decimal,
        insurance_id: Optional[str],
        has_glosa: bool,
        glosa_percentage: float,
    ) -> Dict[str, Any]:
        """
        Evaluate billing-calculation DMN decision table.

        Args:
            claim_items: List of claim items
            claim_amount: Total claim amount
            insurance_id: Insurance for table lookup
            has_glosa: Whether there is a denial
            glosa_percentage: Denial percentage

        Returns:
            DMN evaluation result
        """
        # Determine procedure type from first item
        procedure_type = (
            claim_items[0].procedure_type if claim_items else "CLINICAL"
        )

        # Get insurance pricing table
        insurance_table = "CUSTOM"
        if insurance_id:
            insurance_table = await self.pricing_service.get_insurance_table(
                insurance_id
            )

        dmn_input = {
            "procedureType": procedure_type,
            "insuranceTable": insurance_table,
            "baseValue": float(claim_amount),
            "hasGlosa": has_glosa,
            "glosaPercentage": glosa_percentage,
        }

        self._logger.debug(
            "Evaluating billing-calculation DMN",
            dmn_input=dmn_input,
        )

        result = await self.dmn_service.evaluate(
            decision_key="billing-calculation",
            variables=dmn_input,
        )

        self._logger.debug(
            "DMN evaluation result",
            result=result,
        )

        return result

    def _validate_dmn_result(self, result: Dict[str, Any]) -> None:
        """
        Validate DMN evaluation results.

        Args:
            result: DMN evaluation result

        Raises:
            CalculationError: If validation fails
        """
        final_amount = result.get("finalAmount", 0)

        if final_amount <= 0:
            raise CalculationError(
                f"Final claim amount must be greater than zero: {final_amount}"
            )

        if final_amount > float(MAX_CLAIM_AMOUNT):
            raise CalculationError(
                f"Final claim amount exceeds maximum allowed value "
                f"(R$ {MAX_CLAIM_AMOUNT:,.2f}): R$ {final_amount:,.2f}"
            )

    async def _generate_tiss_xml(
        self,
        claim_id: str,
        input_data: GenerateClaimInput,
        claim_items: List[ClaimLineItem],
        total_amount: Decimal,
    ) -> tuple[str, str, List[str]]:
        """
        Generate and validate TISS XML.

        Args:
            claim_id: Claim identifier
            input_data: Input data with patient/provider info
            claim_items: Claim line items
            total_amount: Total claim amount

        Returns:
            Tuple of (base64_xml, validation_status, validation_messages)
        """
        # Build claim data for TISS generator
        claim_data = ClaimData(
            claim_id=claim_id,
            encounter_id=input_data.encounter_id,
            patient_id=input_data.patient_id,
            patient_name=input_data.patient_name,
            patient_cpf=input_data.patient_cpf,
            patient_card_number=input_data.patient_card_number,
            payer_id=input_data.payer_id or input_data.insurance_id,
            provider_cnes=input_data.provider_cnes,
            provider_name=input_data.provider_name,
            claim_type=input_data.claim_type,
            items=claim_items,
            total_amount=total_amount,
            authorization_number=input_data.authorization_number,
            service_date=input_data.service_date or datetime.now(),
        )

        # Generate XML
        xml = self.tiss_generator.generate(claim_data)

        # Validate XML
        validation_result = self.tiss_generator.validate_xml(xml)

        # Encode to base64
        xml_base64 = self.tiss_generator.encode_base64(xml)

        # Build validation messages
        messages = []
        if validation_result.errors:
            messages.extend([f"ERROR: {e}" for e in validation_result.errors])
        if validation_result.warnings:
            messages.extend([f"WARNING: {w}" for w in validation_result.warnings])

        return xml_base64, validation_result.status, messages


def generate_idempotency_key(
    encounter_id: str,
    patient_id: str,
    procedure_codes: List[str],
) -> str:
    """
    Generate deterministic idempotency key.

    This function matches the Java @IdempotencyParams annotation behavior.

    Args:
        encounter_id: Encounter identifier
        patient_id: Patient identifier
        procedure_codes: List of procedure codes

    Returns:
        32-character hash key
    """
    sorted_codes = sorted(procedure_codes)
    data = f"{encounter_id}:{patient_id}:{':'.join(sorted_codes)}"
    return hashlib.sha256(data.encode()).hexdigest()[:32]
