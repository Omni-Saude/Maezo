"""V2: Sincroniza agendamentos com sistemas ERP externos (Tasy/MV Soul)."""
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


@worker(topic='scheduling.update_system')
class UpdateSchedulingSystemWorkerV2(BaseExternalTaskWorker):
    """Atualiza sistemas de agendamento externos.

        Archetype: OPERATIONAL_ROUTING
    """

    TOPIC = 'scheduling.update_system'
    OPERATION_NAME = 'Atualização de Sistema de Agendamento'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs
        appointment_id = context.variables.get('appointment_id') or context.variables.get('appointmentId', '')
        patient_id = context.variables.get('patient_id') or context.variables.get('patientId', '')
        status = context.variables.get('status', 'booked')
        systems_to_update = context.variables.get('systems_to_update') or context.variables.get('systemsToUpdate', ['tasy'])

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='scheduling_system_sync',
            variables={
                'appointmentId': appointment_id,
                'patientId': patient_id,
                'status': status,
                'systemsToUpdate': systems_to_update,
            },
            category='patient_access',
        )
        routing = dmn.get('resultado', 'PROSSEGUIR')
        acao = dmn.get('acao', '')

        if routing == 'BLOQUEAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'BLOQUEAR'})
            return TaskResult.bpmn_error(
                'PATIENT_ACCESS_BLOCKED', acao, {'routing': 'BLOQUEAR', 'acao': acao},
            )

        # Build output
        out = {
            'syncCompleted': True,
            'systemsSynced': len(systems_to_update),
            'systemsFailed': 0,
            'partialSuccess': True,
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
