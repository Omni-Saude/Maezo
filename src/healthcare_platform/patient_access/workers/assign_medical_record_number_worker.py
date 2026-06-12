"""V2: Atribuir número de prontuário médico (MRN) ao paciente."""
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


@worker(topic='patient.assign_mrn')
class AssignMedicalRecordNumberWorkerV2(BaseExternalTaskWorker):
    """Atribui número único de prontuário médico ao paciente.

        Archetype: OPERATIONAL_ROUTING
    """

    TOPIC = 'patient.assign_mrn'
    OPERATION_NAME = 'Atribuir Número de Prontuário'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs from context.variables
        patient_id = context.variables.get('patient_id') or context.variables.get('patientId', '')
        facility_cnes_code = context.variables.get('facility_cnes_code') or context.variables.get('facilityCnesCode', '')
        patient_cpf_hash = context.variables.get('patient_cpf_hash') or context.variables.get('cpfHash', '')

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='patient_mrn_assignment',
            variables={
                'patientId': patient_id,
                'facilityCnesCode': facility_cnes_code,
                'cpfHash': patient_cpf_hash,
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
        sequence = dmn.get('sequence', 1)
        mrn = f"{facility_cnes_code}-{sequence:06d}"
        formatted_mrn = f"{facility_cnes_code[:2]}.{facility_cnes_code[2:5]}.{sequence:06d}"

        out = {
            'patient_id': patient_id,
            'mrn': mrn,
            'facility_cnes_code': facility_cnes_code,
            'formatted_mrn': formatted_mrn,
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
