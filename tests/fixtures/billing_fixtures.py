"""Billing, invoice, and glosa fixtures para testes."""

from __future__ import annotations

from typing import Dict, Any
from decimal import Decimal


INVOICE_SUS: Dict[str, Any] = {
    "invoice_id": "INV-SUS-001",
    "tenant_id": "austa-001",
    "patient_id": "patient-valid-001",
    "insurance_type": "SUS",
    "billing_date": "2024-03-15",
    "procedures": [
        {
            "code": "0301010064",  # Código SIGTAP
            "description": "Consulta médica em atenção básica",
            "quantity": 1,
            "unit_value": Decimal("10.00"),
            "total_value": Decimal("10.00"),
        }
    ],
    "total_amount": Decimal("10.00"),
    "status": "pending",
}

INVOICE_AMB: Dict[str, Any] = {
    "invoice_id": "INV-AMB-001",
    "tenant_id": "austa-001",
    "patient_id": "patient-valid-001",
    "insurance_type": "AMB",
    "insurance_code": "12345",
    "billing_date": "2024-03-15",
    "procedures": [
        {
            "code": "10101012",  # Código AMB
            "description": "Consulta médica em consultório",
            "quantity": 1,
            "unit_value": Decimal("150.00"),
            "porte": "1A",
            "total_value": Decimal("150.00"),
        }
    ],
    "total_amount": Decimal("150.00"),
    "status": "pending",
}

CONTRACT_RULE_SUS: Dict[str, Any] = {
    "contract_id": "CONTRACT-SUS-AUSTA",
    "tenant_id": "austa-001",
    "insurance_type": "SUS",
    "table": "SIGTAP",
    "rules": {
        "billing_frequency": "monthly",
        "submission_deadline": 10,  # Dia do mês
        "requires_authorization": False,
        "glosa_tolerance": Decimal("0.05"),  # 5%
    },
    "procedure_overrides": {
        "0301010064": {
            "unit_value": Decimal("10.00"),
            "requires_justification": False,
        }
    },
}

CONTRACT_RULE_CBHPM: Dict[str, Any] = {
    "contract_id": "CONTRACT-CBHPM-AUSTA",
    "tenant_id": "austa-001",
    "insurance_type": "CBHPM",
    "table": "CBHPM",
    "rules": {
        "billing_frequency": "immediate",
        "requires_authorization": True,
        "authorization_validity_days": 30,
        "glosa_tolerance": Decimal("0.02"),  # 2%
    },
    "porte_multipliers": {
        "1A": Decimal("1.00"),
        "2A": Decimal("1.40"),
        "3A": Decimal("2.00"),
        "4A": Decimal("3.00"),
    },
}

BILLING_INPUT_CONSULTATION: Dict[str, Any] = {
    "encounter_id": "encounter-001",
    "patient_id": "patient-valid-001",
    "practitioner_id": "practitioner-general",
    "insurance_type": "AMB",
    "insurance_code": "12345",
    "procedure_code": "10101012",
    "procedure_description": "Consulta médica em consultório",
    "date": "2024-03-15",
    "porte": "1A",
    "films": 0,
    "auxiliaries": 0,
}

BILLING_INPUT_SURGICAL: Dict[str, Any] = {
    "encounter_id": "encounter-surgical-001",
    "patient_id": "patient-valid-001",
    "practitioner_id": "surgeon-001",
    "insurance_type": "CBHPM",
    "insurance_code": "67890",
    "procedure_code": "31003117",  # Colecistectomia videolaparoscópica
    "procedure_description": "Colecistectomia por videolaparoscopia",
    "date": "2024-03-20",
    "porte": "4A",
    "films": 2,
    "auxiliaries": 2,
    "anesthesia_type": "GERAL",
    "surgical_time_minutes": 180,
    "materials": [
        {
            "code": "MAT-001",
            "description": "Trocarte 10mm",
            "quantity": 3,
            "unit_value": Decimal("50.00"),
        },
        {
            "code": "MAT-002",
            "description": "Grampeador cirúrgico",
            "quantity": 1,
            "unit_value": Decimal("800.00"),
        },
    ],
}

GLOSA_SAMPLE: Dict[str, Any] = {
    "glosa_id": "GLOSA-001",
    "invoice_id": "INV-AMB-001",
    "tenant_id": "austa-001",
    "insurance_type": "AMB",
    "glosa_date": "2024-03-25",
    "glosa_type": "TECHNICAL",
    "items": [
        {
            "procedure_code": "10101012",
            "original_value": Decimal("150.00"),
            "glosa_value": Decimal("30.00"),
            "glosa_reason": "FALTA_DOCUMENTO",
            "glosa_description": "Relatório médico não anexado",
            "can_appeal": True,
        }
    ],
    "total_glosa": Decimal("30.00"),
    "status": "pending_review",
}
