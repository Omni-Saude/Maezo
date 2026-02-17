"""Pre-submission validation of claim data."""
from __future__ import annotations

from decimal import Decimal

from healthcare_platform.revenue_cycle.billing.workers.base import BaseWorker, WorkerResult, worker
from healthcare_platform.shared.domain.exceptions import ClaimValidationError
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _


@worker(topic="billing.validate_claim", max_jobs=5, lock_duration=300000)
class ValidateClaimWorker(BaseWorker):
    """
    Validate claim data before submission to TISS.

    Input variables:
        - claim_id (str): Claim UUID
        - claim (dict): Claim data with items, total, payer_id, etc.

    Output variables:
        - validation_passed (bool): True if all validations pass
        - validation_errors (list[str]): List of error messages
        - claim_ready_for_submission (bool): True if ready to submit
    """

    def __init__(self) -> None:
        super().__init__()
        self.dmn_service = FederatedDMNService()

    @property
    def operation_name(self) -> str:
        return _("Validar conta")

    def _evaluate_billing_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate billing DMN decision table via federation service."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='billing',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    async def process_task(self, job, variables: dict) -> WorkerResult:
        """Process claim validation task."""
        try:
            claim_id = variables.get("claim_id")
            claim_data = variables.get("claim", {})

            if not claim_id:
                raise ClaimValidationError(_("ID da conta é obrigatório"))
            if not claim_data or not isinstance(claim_data, dict):
                raise ClaimValidationError(_("Dados da conta são obrigatórios"))

            # Collect all validation errors
            errors: list[str] = []

            # Validate required fields
            self._validate_required_fields(claim_data, errors)

            # Validate items
            self._validate_items(claim_data, errors)

            # Validate total consistency
            self._validate_total_consistency(claim_data, errors)

            # Validate duplicates
            self._validate_no_duplicates(claim_data, errors)

            # Validate authorizations
            self._validate_authorizations(claim_data, errors)

            # Determine if claim is ready
            validation_passed = len(errors) == 0
            claim_ready = validation_passed

            if not validation_passed:
                self._logger.warning(
                    "Claim validation failed",
                    claim_id=claim_id,
                    error_count=len(errors),
                    errors=errors[:5]  # Log first 5 errors
                )
            else:
                self._logger.info("Claim validation passed", claim_id=claim_id)

            return WorkerResult.ok({
                "validation_passed": validation_passed,
                "validation_errors": errors,
                "claim_ready_for_submission": claim_ready,
            })

        except ClaimValidationError as e:
            self._logger.error("Critical validation error", error=str(e))
            return WorkerResult.bpmn_error(
                error_code=e.bpmn_error_code,
                error_message=str(e)
            )
        except Exception as e:
            self._logger.error("Unexpected error in validation", error=str(e), exc_info=True)
            return WorkerResult.failure(
                error_message=_("Erro ao validar conta: {error}").format(error=str(e)),
                retry=True
            )

    def _validate_required_fields(self, claim: dict, errors: list[str]) -> None:
        """Validate that all required fields are present."""
        required_fields = ["patient_id", "payer_id", "items", "total"]

        for field in required_fields:
            if not claim.get(field):
                errors.append(_("Campo obrigatório ausente: {field}").format(field=field))

        # Validate TISS guide type if present
        if "tiss_guide_type" in claim and claim["tiss_guide_type"]:
            guide_type = claim["tiss_guide_type"]
            valid_types = ["sp_sadt", "consultation", "admission", "extension", "honorarios", "summary"]
            if guide_type not in valid_types:
                errors.append(_("Tipo de guia TISS inválido: {type}").format(type=guide_type))

    def _validate_items(self, claim: dict, errors: list[str]) -> None:
        """Validate claim items."""
        items = claim.get("items", [])

        if not isinstance(items, list):
            errors.append(_("Items deve ser uma lista"))
            return

        if len(items) == 0:
            errors.append(_("Pelo menos um item é obrigatório"))
            return

        for idx, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                errors.append(_("Item {seq} deve ser um dicionário").format(seq=idx))
                continue

            # Validate item structure
            if "sequence" not in item:
                errors.append(_("Item {seq}: campo 'sequence' ausente").format(seq=idx))

            if "procedure_code" not in item:
                errors.append(_("Item {seq}: código do procedimento ausente").format(seq=idx))

            if "quantity" not in item:
                errors.append(_("Item {seq}: quantidade ausente").format(seq=idx))
            elif not isinstance(item["quantity"], int) or item["quantity"] < 1:
                errors.append(_("Item {seq}: quantidade inválida").format(seq=idx))

            if "unit_price" not in item:
                errors.append(_("Item {seq}: preço unitário ausente").format(seq=idx))

            if "total_price" not in item:
                errors.append(_("Item {seq}: preço total ausente").format(seq=idx))

            # Validate price consistency
            if "unit_price" in item and "quantity" in item and "total_price" in item:
                try:
                    unit_price = Decimal(str(item["unit_price"]))
                    quantity = int(item["quantity"])
                    total_price = Decimal(str(item["total_price"]))
                    expected_total = unit_price * quantity

                    if abs(expected_total - total_price) > Decimal("0.01"):
                        errors.append(
                            _("Item {seq}: preço total inconsistente (esperado {exp}, encontrado {found})").format(
                                seq=idx,
                                exp=float(expected_total),
                                found=float(total_price)
                            )
                        )
                except (ValueError, TypeError, ArithmeticError):
                    errors.append(_("Item {seq}: erro ao validar preços").format(seq=idx))

    def _validate_total_consistency(self, claim: dict, errors: list[str]) -> None:
        """Validate that claim total matches sum of items."""
        items = claim.get("items", [])
        claim_total = claim.get("total", {})

        if not isinstance(claim_total, dict):
            errors.append(_("Total da conta deve ser um dicionário"))
            return

        try:
            total_amount = Decimal(str(claim_total.get("amount", 0)))

            # Calculate sum of items
            items_sum = Decimal("0")
            for item in items:
                if isinstance(item, dict) and "total_price" in item:
                    item_total = item["total_price"]
                    if isinstance(item_total, dict):
                        items_sum += Decimal(str(item_total.get("amount", 0)))
                    else:
                        items_sum += Decimal(str(item_total))

            # Allow small rounding difference
            if abs(total_amount - items_sum) > Decimal("0.01"):
                errors.append(
                    _("Total da conta ({total}) não corresponde à soma dos itens ({sum})").format(
                        total=float(total_amount),
                        sum=float(items_sum)
                    )
                )

        except (ValueError, TypeError, ArithmeticError) as e:
            errors.append(_("Erro ao validar total: {error}").format(error=str(e)))

    def _validate_no_duplicates(self, claim: dict, errors: list[str]) -> None:
        """Validate that there are no duplicate items."""
        items = claim.get("items", [])

        seen_codes: dict[tuple, int] = {}

        for idx, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue

            proc_code = item.get("procedure_code", {})
            if isinstance(proc_code, dict):
                code = proc_code.get("code", "")
                system = proc_code.get("system", "")
            else:
                code = str(proc_code)
                system = ""

            service_date = item.get("service_date", "")
            key = (code, system, service_date)

            if key in seen_codes:
                errors.append(
                    _("Item duplicado detectado: código {code} (itens {seq1} e {seq2})").format(
                        code=code,
                        seq1=seen_codes[key],
                        seq2=idx
                    )
                )
            else:
                seen_codes[key] = idx

    def _validate_authorizations(self, claim: dict, errors: list[str]) -> None:
        """Validate that required authorizations are present."""
        items = claim.get("items", [])
        tiss_guide_type = claim.get("tiss_guide_type", "")

        # For certain guide types, authorization is mandatory
        requires_auth = tiss_guide_type in ["admission", "extension"]

        for idx, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue

            auth_ref = item.get("authorization_reference")

            if requires_auth and not auth_ref:
                proc_code = item.get("procedure_code", {})
                code = proc_code.get("code", "") if isinstance(proc_code, dict) else str(proc_code)
                errors.append(
                    _("Item {seq} (código {code}): autorização obrigatória ausente").format(
                        seq=idx,
                        code=code
                    )
                )
