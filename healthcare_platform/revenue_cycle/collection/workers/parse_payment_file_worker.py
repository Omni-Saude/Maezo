"""Worker: Parse CNAB 240/400 bank return files."""
from __future__ import annotations

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.revenue_cycle.collection.lib.cnab_parser import (
    parse_cnab,
    CNABFileResult,
)
from healthcare_platform.revenue_cycle.collection.exceptions import CNABParsingError

logger = get_logger(__name__)


class ParsePaymentFileWorker:
    """Parses CNAB 240/400 bank return files."""

    WORKER_TYPE = "parse_payment_file"

    def __init__(self) -> None:
        self.dmn_service = FederatedDMNService()
        self._logger = get_logger(__name__)

    def _evaluate_cash_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate cash_operations DMN decision table via federation service."""
        try:
            return self.dmn_service.evaluate(
                tenant_id='default',
                category='cash_operations',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    @track_task_execution(metric_name="parse_payment_file")
    async def execute(self, task_variables: dict) -> dict:
        """Execute CNAB file parsing.

        Args:
            task_variables: Contains 'file_content' (CNAB raw string).

        Returns:
            Dict with parsed payment records list.

        Raises:
            CNABParsingError: If file parsing fails.
        """
        file_content = task_variables.get("file_content", "")
        if not file_content:
            raise CNABParsingError(_("Conteúdo do arquivo CNAB vazio"))

        logger.info("cnab_parsing_started", size=len(file_content))

        try:
            result: CNABFileResult = parse_cnab(file_content)
        except CNABParsingError:
            raise
        except Exception as exc:
            logger.error("cnab_parsing_unexpected_error", error=str(exc))
            raise CNABParsingError(
                _("Erro inesperado ao parsear CNAB: {err}").format(err=str(exc))
            ) from exc

        # Convert to serializable format
        payment_records = []
        for record in result.payments:
            payment_records.append({
                "nosso_numero": record.nosso_numero,
                "seu_numero": record.seu_numero,
                "payment_date": record.payment_date.isoformat() if record.payment_date else None,
                "credit_date": record.credit_date.isoformat() if record.credit_date else None,
                "gross_amount": str(record.gross_amount),
                "discount_amount": str(record.discount_amount),
                "interest_amount": str(record.interest_amount),
                "penalty_amount": str(record.penalty_amount),
                "net_amount": str(record.net_amount),
                "occurrence_code": record.occurrence_code,
                "occurrence_description": record.occurrence_description,
                "payer_name": record.payer_name,
                "payer_document": record.payer_document,
                "bank_code": record.bank_code,
                "agency": record.agency,
                "account": record.account,
                "line_number": record.line_number,
            })

        logger.info(
            "cnab_parsing_completed",
            bank_code=result.header.bank_code,
            payment_count=len(payment_records),
            total_amount=str(result.total_amount),
            error_count=len(result.errors),
        )

        return {
            "payment_records": payment_records,
            "header": {
                "bank_code": result.header.bank_code,
                "bank_name": result.header.bank_name,
                "company_name": result.header.company_name,
                "company_cnpj": result.header.company_cnpj,
                "file_date": result.header.file_date.isoformat(),
                "cnab_format": result.header.cnab_format.value,
            },
            "total_records": result.total_records,
            "total_amount": str(result.total_amount),
            "errors": result.errors,
        }
