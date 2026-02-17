"""Worker for grouping procedures by TISS guide type."""
from __future__ import annotations

from typing import Any, Dict, List

from healthcare_platform.revenue_cycle.billing.workers.base import BaseWorker, WorkerResult, worker
from healthcare_platform.shared.domain.enums import TISSGuideType
from healthcare_platform.shared.domain.exceptions import BillingException
from healthcare_platform.shared.domain.value_objects import CodedValue
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


@worker(topic="billing-group-by-guide", max_jobs=1, lock_duration=300000)
class GroupByGuideWorker(BaseWorker):
    """Groups encounter procedures by TISS guide type.

    This worker organizes procedures into appropriate TISS guide categories
    based on procedure type and characteristics. This grouping is essential
    for proper billing submission to Brazilian health insurance payers.

    Input Variables:
        encounter_id: str - Unique identifier for the encounter
        procedures: List[Dict] - List of procedures with:
            - code: str - TUSS procedure code
            - type: str - Procedure type (consultation, surgery, exam, etc.)
            - quantity: int - Number of times performed
            - description: Optional[str] - Procedure description

    Output Variables:
        grouped_guides: Dict[str, List[Dict]] - Procedures grouped by TISS guide type
        guide_count: int - Number of different guide types needed
        total_procedures: int - Total number of procedures
    """

    # Mapping of procedure types to TISS guide types
    PROCEDURE_TYPE_MAPPING = {
        "consultation": TISSGuideType.CONSULTATION,
        "consulta": TISSGuideType.CONSULTATION,
        "ambulatory": TISSGuideType.CONSULTATION,
        "ambulatorial": TISSGuideType.CONSULTATION,
        "exam": TISSGuideType.SP_SADT,
        "exame": TISSGuideType.SP_SADT,
        "diagnostic": TISSGuideType.SP_SADT,
        "diagnostico": TISSGuideType.SP_SADT,
        "lab": TISSGuideType.SP_SADT,
        "laboratorio": TISSGuideType.SP_SADT,
        "therapy": TISSGuideType.SP_SADT,
        "terapia": TISSGuideType.SP_SADT,
        "surgery": TISSGuideType.SP_SADT,
        "cirurgia": TISSGuideType.SP_SADT,
        "admission": TISSGuideType.ADMISSION,
        "internacao": TISSGuideType.ADMISSION,
        "inpatient": TISSGuideType.ADMISSION,
        "hospitalization": TISSGuideType.ADMISSION,
        "extension": TISSGuideType.EXTENSION,
        "extensao": TISSGuideType.EXTENSION,
        "prorrogacao": TISSGuideType.EXTENSION,
        "honorarios": TISSGuideType.HONORARIOS,
        "professional_fees": TISSGuideType.HONORARIOS,
        "summary": TISSGuideType.SUMMARY,
        "resumo": TISSGuideType.SUMMARY,
    }

    def __init__(self) -> None:
        super().__init__()
        self.dmn_service = FederatedDMNService()

    @property
    def operation_name(self) -> str:
        """Get operation name."""
        return _("Agrupar procedimentos por guia TISS")

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

    async def process_task(self, job: Any, variables: dict[str, Any]) -> WorkerResult:
        """Process grouping by guide type.

        Args:
            job: Job object from workflow engine
            variables: Process variables containing encounter_id and procedures

        Returns:
            WorkerResult with grouped procedures

        Raises:
            BillingException: If required variables are missing or invalid
        """
        # Validate required input variables
        encounter_id = variables.get("encounter_id")
        if not encounter_id:
            raise BillingException(
                message=_("ID do encontro é obrigatório"),
                bpmn_error_code="MISSING_ENCOUNTER_ID",
                retryable=False,
                details={"variables": list(variables.keys())}
            )

        procedures = variables.get("procedures")
        if not procedures:
            raise BillingException(
                message=_("Lista de procedimentos é obrigatória"),
                bpmn_error_code="MISSING_PROCEDURES",
                retryable=False,
                details={"encounter_id": encounter_id}
            )

        if not isinstance(procedures, list):
            raise BillingException(
                message=_("Procedimentos devem ser uma lista"),
                bpmn_error_code="INVALID_PROCEDURES_FORMAT",
                retryable=False,
                details={"type": type(procedures).__name__}
            )

        self._logger.info(
            "Grouping procedures by guide type",
            encounter_id=encounter_id,
            procedure_count=len(procedures)
        )

        try:
            # Group procedures by TISS guide type
            grouped_guides = await self._group_procedures(procedures)

            # Calculate statistics
            guide_count = len(grouped_guides)
            total_procedures = sum(len(procs) for procs in grouped_guides.values())

            self._logger.info(
                "Procedures grouped successfully",
                encounter_id=encounter_id,
                guide_count=guide_count,
                total_procedures=total_procedures,
                guide_types=list(grouped_guides.keys())
            )

            # Convert enum keys to strings for serialization
            serialized_guides = {
                guide_type.value: procedures_list
                for guide_type, procedures_list in grouped_guides.items()
            }

            return WorkerResult.ok({
                "grouped_guides": serialized_guides,
                "guide_count": guide_count,
                "total_procedures": total_procedures,
                "encounter_id": encounter_id
            })

        except Exception as e:
            self._logger.error(
                "Error grouping procedures",
                encounter_id=encounter_id,
                error=str(e),
                exc_info=True
            )
            raise

    async def _group_procedures(
        self,
        procedures: List[Dict[str, Any]]
    ) -> Dict[TISSGuideType, List[Dict[str, Any]]]:
        """Group procedures by TISS guide type.

        Args:
            procedures: List of procedure dictionaries

        Returns:
            Dictionary mapping TISSGuideType to list of procedures

        Raises:
            BillingException: If procedure data is invalid
        """
        grouped: Dict[TISSGuideType, List[Dict[str, Any]]] = {}

        for idx, proc in enumerate(procedures):
            # Validate procedure structure
            if not isinstance(proc, dict):
                raise BillingException(
                    message=_("Procedimento deve ser um dicionário"),
                    bpmn_error_code="INVALID_PROCEDURE_FORMAT",
                    retryable=False,
                    details={"index": idx, "type": type(proc).__name__}
                )

            # Extract procedure data
            proc_code = proc.get("code")
            proc_type = proc.get("type")
            quantity = proc.get("quantity", 1)

            # Validate required fields
            if not proc_code:
                raise BillingException(
                    message=_("Código do procedimento é obrigatório"),
                    bpmn_error_code="MISSING_PROCEDURE_CODE",
                    retryable=False,
                    details={"index": idx, "procedure": proc}
                )

            if not proc_type:
                raise BillingException(
                    message=_("Tipo do procedimento é obrigatório"),
                    bpmn_error_code="MISSING_PROCEDURE_TYPE",
                    retryable=False,
                    details={"index": idx, "code": proc_code}
                )

            # Validate and create TUSS coded value
            try:
                coded_value = CodedValue.tuss(proc_code)
            except Exception as e:
                raise BillingException(
                    message=_("Código TUSS inválido: {code}").format(code=proc_code),
                    bpmn_error_code="INVALID_TUSS_CODE",
                    retryable=False,
                    details={"code": proc_code, "error": str(e)}
                )

            # Determine TISS guide type
            guide_type = self._determine_guide_type(proc_type, proc_code)

            # Add procedure to appropriate group
            if guide_type not in grouped:
                grouped[guide_type] = []

            # Enrich procedure with coded value
            enriched_proc = {
                **proc,
                "coded_value": {
                    "system": coded_value.system,
                    "code": coded_value.code,
                    "display": coded_value.display
                },
                "quantity": quantity
            }

            grouped[guide_type].append(enriched_proc)

            self._logger.debug(
                "Procedure assigned to guide",
                code=proc_code,
                type=proc_type,
                guide=guide_type.value
            )

        return grouped

    def _determine_guide_type(self, proc_type: str, proc_code: str) -> TISSGuideType:
        """Determine TISS guide type for a procedure.

        Args:
            proc_type: Procedure type string
            proc_code: TUSS procedure code

        Returns:
            TISSGuideType enum value
        """
        # Normalize procedure type to lowercase for matching
        normalized_type = proc_type.lower().strip()

        # Check direct mapping first
        if normalized_type in self.PROCEDURE_TYPE_MAPPING:
            return self.PROCEDURE_TYPE_MAPPING[normalized_type]

        # Check for partial matches
        for key, guide_type in self.PROCEDURE_TYPE_MAPPING.items():
            if key in normalized_type or normalized_type in key:
                return guide_type

        # Check procedure code patterns (TUSS code-based heuristics)
        # These patterns are based on typical TUSS code ranges
        if proc_code.startswith("1"):  # Consultations typically start with 1
            return TISSGuideType.CONSULTATION
        elif proc_code.startswith("2"):  # Exams/diagnostics typically start with 2
            return TISSGuideType.SP_SADT
        elif proc_code.startswith("3"):  # Surgeries typically start with 3
            return TISSGuideType.SP_SADT
        elif proc_code.startswith("4"):  # Procedures typically start with 4
            return TISSGuideType.SP_SADT

        # Default to SP_SADT for unknown types
        self._logger.warning(
            "Unknown procedure type, defaulting to SP_SADT",
            type=proc_type,
            code=proc_code
        )
        return TISSGuideType.SP_SADT
