"""Camunda engine fixtures para testes."""

from typing import Dict, Any, List


EXTERNAL_TASK_SAMPLE: Dict[str, Any] = {
    "activityId": "task_validate_patient",
    "activityInstanceId": "task_validate_patient:12345",
    "errorMessage": None,
    "errorDetails": None,
    "executionId": "exec-12345",
    "id": "ext-task-001",
    "lockExpirationTime": "2024-03-15T11:00:00.000+0000",
    "processDefinitionId": "patient_registration:1:def-001",
    "processDefinitionKey": "patient_registration",
    "processInstanceId": "proc-inst-001",
    "tenantId": "austa-001",
    "retries": 3,
    "suspended": False,
    "workerId": "worker-001",
    "topicName": "validate-patient",
    "priority": 0,
    "businessKey": "PATIENT-REG-001",
    "variables": {
        "patient_cpf": {
            "type": "String",
            "value": "12345678901",
            "valueInfo": {},
        },
        "patient_name": {
            "type": "String",
            "value": "João Pedro Silva",
            "valueInfo": {},
        },
        "insurance_type": {
            "type": "String",
            "value": "AMB",
            "valueInfo": {},
        },
        "tenant_code": {
            "type": "String",
            "value": "AUSTA",
            "valueInfo": {},
        },
    },
}

PROCESS_INSTANCE_SAMPLE: Dict[str, Any] = {
    "id": "proc-inst-001",
    "definitionId": "patient_registration:1:def-001",
    "businessKey": "PATIENT-REG-001",
    "caseInstanceId": None,
    "ended": False,
    "suspended": False,
    "tenantId": "austa-001",
    "links": [
        {
            "method": "GET",
            "href": "http://localhost:8080/engine-rest/process-instance/proc-inst-001",
            "rel": "self",
        }
    ],
}

VARIABLE_MAP_SAMPLE: Dict[str, Any] = {
    "patient_data": {
        "type": "Object",
        "value": {
            "cpf": "12345678901",
            "name": "João Pedro Silva",
            "birth_date": "1980-05-15",
            "gender": "male",
            "phone": "+5511987654321",
        },
        "valueInfo": {
            "objectTypeName": "platform.shared.models.patient.PatientData",
            "serializationDataFormat": "application/json",
        },
    },
    "validation_result": {
        "type": "Boolean",
        "value": True,
        "valueInfo": {},
    },
    "fhir_patient_id": {
        "type": "String",
        "value": "patient-valid-001",
        "valueInfo": {},
    },
}
