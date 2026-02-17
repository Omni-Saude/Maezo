"""V2: Generate patient identification card."""
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


@worker(topic='patient.generate_card')
class GeneratePatientCardWorkerV2(BaseExternalTaskWorker):
    """Generate patient identification card.

        Archetype: OPERATIONAL_ROUTING
    """

    TOPIC = 'patient.generate_card'
    OPERATION_NAME = 'Gerar Cartão do Paciente'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs
        patient_id = context.variables.get('patientId', '')
        mrn = context.variables.get('mrn', '')
        patient_name = context.variables.get('patientName', '')
        facility_name = context.variables.get('facilityName', '')
        facility_cnes_code = context.variables.get('facilityCnesCode', '')

        # Hash PII before DMN
        patient_id_hash = self.hash_pii(patient_id, 'patient_id')

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='patient_card_generation',
            variables={
                'patientId': patient_id,
                'mrn': mrn,
                'facilityCnesCode': facility_cnes_code
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

        out = {
            'patient_id': patient_id,
            'card_number': dmn.get('cardNumber', f"{facility_cnes_code}-{mrn}"),
            'patient_id_hash': patient_id_hash,
            'mrn': mrn,
            'facility_name': facility_name,
            'facility_cnes_code': facility_cnes_code
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
