"""Lock coding on encounter after finalization.

CIB7 External Task Topic: coding.lock_coding
"""
from __future__ import annotations

from typing import Any

from healthcare_platform.shared.domain.exceptions import CodingException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker


class CodingLockWorkerV2(BaseExternalTaskWorker):
    """Thin worker that handles coding locking after finalization.

    This worker is responsible for locking the coding state on an encounter
    to prevent further modifications after finalization is complete.
    """

    TOPIC = "coding.lock_coding"

    def __init__(self, encounter_service: Any = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._logger = get_logger(__name__, worker=self.TOPIC)
        self.encounter_service = encounter_service

    async def execute(self, task_or_variables: Any) -> dict[str, Any]:
        """Execute coding lock operation.

        Args:
            task_or_variables: Either a dict with variables or a mock_task object

        Returns:
            Dictionary with lock status

        Raises:
            CodingException: If locking fails
        """
        # Extract encounter_id
        if hasattr(task_or_variables, 'get_variable'):
            encounter_id = task_or_variables.get_variable('encounter_id') or task_or_variables.get_variable('encounterId')
            is_mock_task = True
        else:
            encounter_id = task_or_variables.get('encounter_id') or task_or_variables.get('encounterId')
            is_mock_task = False

        if not encounter_id:
            error_msg = _("encounter_id é obrigatório para bloqueio de codificação")
            self._logger.error("missing_encounter_id")
            if is_mock_task:
                await task_or_variables.bpmn_error("CODING_ERROR", error_msg)
                return {}
            raise CodingException(error_msg, bpmn_error_code="CODING_ERROR")

        self._logger.info("coding_lock_started", encounter_id=encounter_id)

        # Require encounter_service for locking
        if not self.encounter_service:
            error_msg = _("Serviço de encontro não configurado para bloqueio")
            self._logger.error("encounter_service_missing")
            if is_mock_task:
                await task_or_variables.failure(
                    error_message=error_msg,
                    error_details="encounter_service not configured",
                    max_retries=0,
                )
                return {}
            raise CodingException(error_msg)

        # Perform locking
        try:
            lock_info = await self.encounter_service.lock_coding(encounter_id)
            self._logger.info("coding_locked_successfully", encounter_id=encounter_id, lock_info=lock_info)

            result = {
                "coding_locked": True,
                "encounter_id": encounter_id,
                "lock_timestamp": lock_info.get("locked_at"),
                "locked_by": lock_info.get("locked_by", "system"),
            }

            if is_mock_task:
                await task_or_variables.complete(result)
                return {}

            return result

        except Exception as e:
            error_msg = f"Failed to lock coding: {str(e)}"
            self._logger.error("coding_lock_failed", encounter_id=encounter_id, error=str(e))

            if is_mock_task:
                await task_or_variables.failure(
                    error_message=error_msg,
                    error_details=str(e),
                    max_retries=3,
                    retry_timeout=5000,
                )
                return {}

            raise CodingException(error_msg) from e


def register_worker(encounter_service: Any = None) -> CodingLockWorkerV2:
    """Create and return a configured CodingLockWorkerV2 instance."""
    return CodingLockWorkerV2(encounter_service=encounter_service)
