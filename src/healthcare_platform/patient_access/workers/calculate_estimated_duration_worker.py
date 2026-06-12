"""V2: Calcular duração estimada do atendimento."""
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


@worker(topic='scheduling.calculate_duration')
class CalculateEstimatedDurationWorkerV2(BaseExternalTaskWorker):
    """Calcula duração estimada baseada em tipo de serviço e complexidade.

        Archetype: CLINICAL_SCORE
    """

    TOPIC = 'scheduling.calculate_duration'
    OPERATION_NAME = 'Calcular Duração Estimada'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs from context.variables
        service_type = context.variables.get('service_type') or context.variables.get('serviceType', '')
        specialty_code = context.variables.get('specialty_code') or context.variables.get('specialtyCode', '')
        complexity_level = context.variables.get('complexity_level') or context.variables.get('complexityLevel', 'medium')
        is_first_visit = context.variables.get('is_first_visit') or context.variables.get('isFirstVisit', False)

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='scheduling_duration_estimation',
            variables={
                'serviceType': service_type,
                'specialtyCode': specialty_code,
                'complexityLevel': complexity_level,
                'isFirstVisit': is_first_visit,
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
        estimated_duration_minutes = dmn.get('estimated_duration_minutes', 30)
        confidence_level = dmn.get('confidence_level', 'medium')

        out = {
            'estimated_duration_minutes': estimated_duration_minutes,
            'confidence_level': confidence_level,
            'service_type': service_type,
            'specialty_code': specialty_code,
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
