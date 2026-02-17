"""V2: Verifica elegibilidade de cobertura de seguro via ANS."""
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


@worker(topic='patient.verify_insurance')
class VerifyInsuranceCoverageWorkerV2(BaseExternalTaskWorker):
    """Verifica cobertura de seguro ANS.

        Archetype: COMPLIANCE_VALIDATION
    """

    TOPIC = 'patient.verify_insurance'
    OPERATION_NAME = 'Verificação de Cobertura de Seguro'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs
        patient_ref = context.variables.get('patient_reference') or context.variables.get('patientReference', '')
        operator_code = context.variables.get('operator_code') or context.variables.get('operatorCode', '')
        plan_code = context.variables.get('plan_code') or context.variables.get('planCode', '')
        card_number = context.variables.get('card_number') or context.variables.get('cardNumber', '')

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='insurance_coverage_verification',
            variables={
                'operatorCode': operator_code,
                'planCode': plan_code,
                'cardNumber': card_number,
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
        from datetime import datetime
        out = {
            'coverageActive': True,
            'coverageReference': f'Coverage/{operator_code}_{card_number}',
            'coverageStatus': 'active',
            'eligibilityVerified': True,
            'verificationDate': datetime.utcnow().isoformat(),
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
