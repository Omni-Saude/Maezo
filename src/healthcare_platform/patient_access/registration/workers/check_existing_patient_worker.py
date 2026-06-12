"""V2: Verify if patient already exists in the system."""
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


@worker(topic='patient.check_existing')
class CheckExistingPatientWorkerV2(BaseExternalTaskWorker):
    """Verify if patient already exists in the system.

        Archetype: COMPLIANCE_VALIDATION
    """

    TOPIC = 'patient.check_existing'
    OPERATION_NAME = 'Verificar Paciente Existente'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs
        cpf_hash = context.variables.get('cpfHash', '')
        cns_hash = context.variables.get('cnsHash', '')

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='patient_duplicate_check',
            variables={'cpfHash': cpf_hash, 'cnsHash': cns_hash},
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

        out = {
            'patient_exists': dmn.get('patientExists', False),
            'patient_reference': dmn.get('patientReference'),
            'patient_id': dmn.get('patientId')
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
