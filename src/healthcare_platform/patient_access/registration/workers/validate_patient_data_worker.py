"""V2: Valida dados demográficos do paciente (CPF, CNS, nome, nascimento)."""
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


@worker(topic='patient.validate_data')
class ValidatePatientDataWorkerV2(BaseExternalTaskWorker):
    """Valida dados do paciente com hash de PII.

        Archetype: COMPLIANCE_VALIDATION
    """

    TOPIC = 'patient.validate_data'
    OPERATION_NAME = 'Validação de Dados do Paciente'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs
        cpf = context.variables.get('cpf', '')
        cns = context.variables.get('cns')
        name = context.variables.get('name', '')
        birth_date = context.variables.get('birth_date') or context.variables.get('birthDate', '')
        gender = context.variables.get('gender', '')

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='patient_data_validation',
            variables={
                'cpf': cpf,
                'cns': cns,
                'name': name,
                'birthDate': birth_date,
                'gender': gender,
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

        # Build output (simplified hash for V2)
        import hashlib
        cpf_hash = hashlib.sha256(cpf.encode()).hexdigest() if cpf else ''
        cns_hash = hashlib.sha256(cns.encode()).hexdigest() if cns else None

        out = {
            'isValid': True,
            'cpfHash': cpf_hash,
            'cnsHash': cns_hash,
            'validationErrors': [],
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
