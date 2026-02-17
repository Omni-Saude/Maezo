"""V2: Generate pre-admission checklist for appointments."""
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


@worker(topic='scheduling.generate_checklist')
class GeneratePreAdmissionChecklistWorkerV2(BaseExternalTaskWorker):
    """Generate pre-admission checklist for appointments.

        Archetype: COMPLIANCE_VALIDATION
    """

    TOPIC = 'scheduling.generate_checklist'
    OPERATION_NAME = 'Gerar Checklist Pré-Admissão'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs
        appointment_id = context.variables.get('appointmentId', '')
        appointment_type = context.variables.get('appointmentType', '')
        specialty = context.variables.get('specialty', '')
        patient_age = context.variables.get('patientAge', 0)
        has_insurance = context.variables.get('hasInsurance', False)

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='scheduling_pre_admission_checklist',
            variables={
                'appointmentType': appointment_type,
                'specialty': specialty,
                'patientAge': patient_age,
                'hasInsurance': has_insurance
            },
            category='patient_access'
        )
        routing = dmn.get('resultado', 'PROSSEGUIR')
        acao = dmn.get('acao', '')

        if routing == 'BLOQUEAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'BLOQUEAR'})
            return TaskResult.bpmn_error(
                'PATIENT_ACCESS_BLOCKED',
                acao,
                {'routing': 'BLOQUEAR', 'acao': acao}
            )

        checklist_items = dmn.get('checklistItems', [])
        out = {
            'appointment_id': appointment_id,
            'checklist_items': checklist_items,
            'total_items': len(checklist_items),
            'appointment_type': appointment_type
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
