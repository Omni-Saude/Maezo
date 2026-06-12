"""V2: Alocar recursos necessários para agendamento."""
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


@worker(topic='scheduling.assign_resources')
class AssignResourcesWorkerV2(BaseExternalTaskWorker):
    """Aloca recursos (salas, equipamentos, profissionais) para agendamento.

        Archetype: OPERATIONAL_ROUTING
    """

    TOPIC = 'scheduling.assign_resources'
    OPERATION_NAME = 'Alocar Recursos'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs from context.variables
        appointment_reference = context.variables.get('appointment_reference') or context.variables.get('appointmentReference', '')
        service_type = context.variables.get('service_type') or context.variables.get('serviceType', '')
        start_datetime = context.variables.get('start_datetime') or context.variables.get('startDatetime', '')
        end_datetime = context.variables.get('end_datetime') or context.variables.get('endDatetime', '')

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='scheduling_resource_assignment',
            variables={
                'appointmentReference': appointment_reference,
                'serviceType': service_type,
                'startDatetime': start_datetime,
                'endDatetime': end_datetime,
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

        # Build output variables
        assigned_resources = dmn.get('assigned_resources', [])
        all_resources_assigned = len(assigned_resources) > 0

        out = {
            'appointment_reference': appointment_reference,
            'assigned_resources': assigned_resources,
            'all_resources_assigned': all_resources_assigned,
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
