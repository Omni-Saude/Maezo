"""V2: Verificar disponibilidade de horários para agendamento."""
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


@worker(topic='scheduling.check_availability')
class CheckAvailabilityWorkerV2(BaseExternalTaskWorker):
    """Verifica disponibilidade de horários para profissional e serviço.

        Archetype: COMPLIANCE_VALIDATION
    """

    TOPIC = 'scheduling.check_availability'
    OPERATION_NAME = 'Verificar Disponibilidade'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs from context.variables
        practitioner_id = context.variables.get('practitioner_id') or context.variables.get('practitionerId', '')
        service_type = context.variables.get('service_type') or context.variables.get('serviceType', '')
        start_date = context.variables.get('start_date') or context.variables.get('startDate', '')
        end_date = context.variables.get('end_date') or context.variables.get('endDate', '')
        location_id = context.variables.get('location_id') or context.variables.get('locationId', '')

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='scheduling_availability_check',
            variables={
                'practitionerId': practitioner_id,
                'serviceType': service_type,
                'startDate': start_date,
                'endDate': end_date,
                'locationId': location_id or '',
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
        available_slots = dmn.get('available_slots', [])
        total_slots_found = len(available_slots)

        out = {
            'available_slots': available_slots,
            'total_slots_found': total_slots_found,
            'search_completed': True,
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
