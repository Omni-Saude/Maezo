"""V2: Valida documentação do paciente (RG, CPF, CNS, carteirinha)."""
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


@worker(topic='patient.validate_documentation')
class ValidateDocumentationWorkerV2(BaseExternalTaskWorker):
    """Valida documentação necessária do paciente.

        Archetype: COMPLIANCE_VALIDATION
    """

    TOPIC = 'patient.validate_documentation'
    OPERATION_NAME = 'Validação de Documentação'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs
        patient_id = context.variables.get('patient_id') or context.variables.get('patientId', '')
        documents = context.variables.get('documents', {})

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='patient_documentation_validation',
            variables={
                'patientId': patient_id,
                'hasCPF': 'CPF' in documents,
                'hasRG': 'RG' in documents,
                'hasCNS': 'CNS' in documents,
                'hasInsurance': 'INSURANCE_CARD' in documents,
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
            'patientId': patient_id,
            'allValid': True,
            'missingDocuments': [],
            'expiredDocuments': [],
            'validationResults': [],
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
