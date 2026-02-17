"""V2: Capturar e validar dados demográficos do paciente."""
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


@worker(topic='patient.capture_demographics')
class CaptureDemographicsWorkerV2(BaseExternalTaskWorker):
    """Captura e valida dados demográficos do paciente com proteção PII.

        Archetype: OPERATIONAL_ROUTING
    """

    TOPIC = 'patient.capture_demographics'
    OPERATION_NAME = 'Capturar Dados Demográficos'

    def execute(self, context: TaskContext) -> TaskResult:
        correlation = extract_correlation(context.variables, self.TOPIC)
        log_worker_start(correlation)
        t0 = time.monotonic()

        # Extract inputs from context.variables
        patient_reference = context.variables.get('patient_reference') or context.variables.get('patientReference', '')
        address_cep = context.variables.get('address_cep') or context.variables.get('addressCep', '')
        address_city = context.variables.get('address_city') or context.variables.get('addressCity', '')
        address_state = context.variables.get('address_state') or context.variables.get('addressState', '')
        phone = context.variables.get('phone', '')
        email = context.variables.get('email', '')

        # Hash PII before DMN
        phone_hash = self.hash_pii(phone, 'phone') if phone else ''
        email_hash = self.hash_pii(email, 'email') if email else ''
        address_hash = self.hash_pii(address_cep, 'address') if address_cep else ''

        # DMN evaluation
        dmn = self.evaluate_dmn(
            context,
            decision_key='patient_demographics_validation',
            variables={
                'patientReference': patient_reference,
                'addressState': address_state,
                'addressCep': address_cep,
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
        out = {
            'demographics_updated': True,
            'address_hash': address_hash,
            'phone_hash': phone_hash,
            'email_hash': email_hash,
        }

        if routing == 'REVISAR':
            log_worker_end(correlation, time.monotonic() - t0, {'routing': 'REVISAR'})
            return TaskResult.success({**out, 'routing': 'REVISAR', 'requiresReview': True})

        log_worker_end(correlation, time.monotonic() - t0, {'routing': 'PROSSEGUIR'})
        return TaskResult.success({**out, 'routing': 'PROSSEGUIR'})
