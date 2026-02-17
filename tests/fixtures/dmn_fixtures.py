"""DMN decision table input fixtures para testes."""

from __future__ import annotations

from typing import Dict, Any
from decimal import Decimal


# ============================================================================
# Billing DMN Inputs
# ============================================================================

DMN_INPUT_BILLING: Dict[str, Any] = {
    "insurance_type": "AMB",
    "procedure_code": "10101012",
    "porte": "1A",
    "films": 0,
    "auxiliaries": 0,
    "patient_age": 45,
    "is_emergency": False,
    "is_follow_up": False,
    "tenant_code": "AUSTA",
}

# ============================================================================
# Clinical DMN Inputs
# ============================================================================

DMN_INPUT_CLINICAL: Dict[str, Any] = {
    "patient_age": 45,
    "patient_gender": "male",
    "is_pregnant": False,
    "has_chronic_condition": True,
    "chronic_conditions": ["diabetes", "hypertension"],
    "current_medications": ["metformin", "losartan"],
    "allergy_list": ["penicillin"],
    "procedure_requested": "coronary_angiography",
    "indication": "chest_pain",
    "risk_score": 3,
    "tenant_code": "AUSTA",
}

# ============================================================================
# Coding DMN Inputs
# ============================================================================

DMN_INPUT_CODING: Dict[str, Any] = {
    "clinical_description": "Dor torácica atípica com dispneia aos esforços",
    "diagnosis_keywords": ["dor torácica", "dispneia", "esforço"],
    "procedure_performed": "consulta cardiologia",
    "insurance_type": "AMB",
    "specialty": "cardiology",
    "duration_minutes": 30,
    "complexity": "medium",
    "tenant_code": "AUSTA",
}

# ============================================================================
# Glosa Prevention DMN Inputs
# ============================================================================

DMN_INPUT_GLOSA: Dict[str, Any] = {
    "insurance_type": "AMB",
    "procedure_code": "10101012",
    "has_authorization": True,
    "authorization_valid": True,
    "has_clinical_justification": True,
    "has_medical_report": True,
    "has_exams": False,
    "procedure_matches_diagnosis": True,
    "quantity_within_limit": True,
    "value_within_contract": True,
    "tenant_code": "AUSTA",
    "historical_glosa_rate": Decimal("0.02"),
}

# ============================================================================
# Access Control DMN Inputs
# ============================================================================

DMN_INPUT_ACCESS_CONTROL: Dict[str, Any] = {
    "user_role": "physician",
    "resource_type": "Patient",
    "action": "read",
    "tenant_code": "AUSTA",
    "specialty": "cardiology",
    "department": "emergency",
    "is_emergency_access": False,
    "patient_treating_physician": False,
    "has_explicit_permission": False,
}

# ============================================================================
# Edge Case Inputs
# ============================================================================

DMN_INPUT_NULL_VALUES: Dict[str, Any] = {
    "insurance_type": None,
    "procedure_code": None,
    "porte": None,
    "films": None,
    "auxiliaries": None,
    "patient_age": None,
    "is_emergency": None,
    "tenant_code": "AUSTA",
}

DMN_INPUT_BOUNDARY: Dict[str, Any] = {
    "insurance_type": "AMB",
    "procedure_code": "99999999",  # Código inexistente
    "porte": "10Z",  # Porte inválido
    "films": -1,  # Valor negativo
    "auxiliaries": 999,  # Valor muito alto
    "patient_age": 150,  # Idade impossível
    "is_emergency": "maybe",  # Tipo inválido
    "tenant_code": "INVALID",
}
