"""V2: Validate appointment against business rules and constraints."""
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


@worker(topic='scheduling.validate_rules')
class ValidateAppointmentRulesWorkerV2(BaseExternalTaskWorker):
    """Validate appointment against scheduling business rules.

        Archetype: COMPLIANCE_VALIDATION
    """

    TOPIC = 'scheduling.validate_rules'
    OPERATION_NAME = 'Validar Regras de Agendamento'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs
        patient_id = context.variables.get('patient_id', '')
        practitioner_id = context.variables.get('practitioner_id', '')
        specialty_code = context.variables.get('specialty_code', '')
        proposed_datetime = context.variables.get('proposed_datetime', '')
        service_type = context.variables.get('service_type', '')
        duration_minutes = context.variables.get('duration_minutes', 30)

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='scheduling_appointment_rules',
            variables={
                'patientId': patient_id,
                'practitionerId': practitioner_id,
                'specialtyCode': specialty_code,
                'proposedDatetime': proposed_datetime,
                'serviceType': service_type,
                'durationMinutes': duration_minutes
            },
            category='patient_access'
        )
        routing = dmn.get('resultado', 'PROSSEGUIR')
        acao = dmn.get('acao', '')

        if routing == 'BLOQUEAR':
            violations = dmn.get('violations', [])
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'BLOQUEAR', 'violations': violations})
            return TaskResult.bpmn_error(
                'PATIENT_ACCESS_BLOCKED',
                acao,
                {'routing': 'BLOQUEAR', 'acao': acao, 'violations': violations}
            )

        out = {
            'is_valid': routing == 'PROSSEGUIR',
            'violations': dmn.get('violations', []),
            'warnings': dmn.get('warnings', [])
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
