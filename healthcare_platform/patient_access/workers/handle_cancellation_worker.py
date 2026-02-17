"""V2: Handle appointment cancellation with resource release."""
from __future__ import annotations

import time

from healthcare_platform.revenue_cycle.billing.workers.base import worker
from healthcare_platform.shared.observability.correlation import (
    extract_correlation,
    log_worker_start,
    log_worker_end,
)
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


@worker(topic='scheduling.handle_cancellation')
class HandleCancellationWorkerV2(BaseExternalTaskWorker):
    """Process appointment cancellation and release resources.

        Archetype: OPERATIONAL_ROUTING
    """

    TOPIC = 'scheduling.handle_cancellation'
    OPERATION_NAME = 'Processar Cancelamento'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs
        appointment_id = context.variables.get('appointment_id', '')
        patient_id = context.variables.get('patient_id', '')
        cancellation_reason = context.variables.get('cancellation_reason', '')
        cancelled_by = context.variables.get('cancelled_by', '')

        self.logger.info(
            f"Processing cancellation for appointment {appointment_id}, "
            f"patient {patient_id}, reason: {cancellation_reason}, by: {cancelled_by}"
        )

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='scheduling_cancellation_rules',
            variables={
                'appointmentId': appointment_id,
                'cancellationReason': cancellation_reason,
                'cancelledBy': cancelled_by
            },
            category='patient_access'
        )
        routing = dmn.get('resultado', 'PROSSEGUIR')
        acao = dmn.get('acao', '')

        if routing == 'BLOQUEAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'BLOQUEAR'})
            return TaskResult.bpmn_error('PATIENT_ACCESS_BLOCKED', acao, {'routing': 'BLOQUEAR', 'acao': acao})

        out = {
            'cancellation_processed': True,
            'appointment_id': appointment_id,
            'cancelled_by': cancelled_by,
            'resources_released': dmn.get('resourcesReleased', [])
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
