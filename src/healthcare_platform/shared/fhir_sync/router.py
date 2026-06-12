"""Table-to-adapter routing for CDC events to FHIR resources.

Maps Debezium CDC table names and operation types to the correct
Tasy-to-FHIR adapter class and identifier configuration.

Includes column mapping from real Oracle column names to the field
names expected by each adapter (e.g., CD_PESSOA_FISICA -> NR_PACIENTE).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from healthcare_platform.shared.integrations.tasy_adapters import (
    BaseTasyFhirAdapter,
    TasyAuthorizationAdapter,
    TasyClaimAdapter,
    TasyClaimResponseAdapter,
    TasyConditionAdapter,
    TasyCoverageAdapter,
    TasyEncounterAdapter,
    TasyOrganizationAdapter,
    TasyPatientAdapter,
    TasyPractitionerAdapter,
    TasyProcedureAdapter,
)


@dataclass(frozen=True)
class AdapterRoute:
    """Routing entry mapping a CDC table+operation to a FHIR adapter."""

    adapter_class: type[BaseTasyFhirAdapter]
    fhir_resource_type: str
    identifier_system: str
    identifier_field: str
    use_bundle: bool = False
    column_map: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Column mappings: Oracle CDC column name -> Adapter expected field name
# Only columns that differ need to be listed; identical names pass through.
# ---------------------------------------------------------------------------

# Tasy Oracle uses numeric codes for encounter type; adapters expect letters
_ENCOUNTER_TYPE_MAP = {1: "I", 2: "A", 3: "E", 4: "U", 5: "D"}

_ENCOUNTER_COLUMNS = {
    "CD_PESSOA_FISICA": "NR_PACIENTE",
    "DT_ENTRADA": "DT_ATENDIMENTO",
    "IE_TIPO_ATENDIMENTO": "TP_ATENDIMENTO",
    "IE_STATUS_ATENDIMENTO": "IE_SITUACAO",
    # SP-RC-002 fields (added per consultant team spec)
    "IE_CARATER_INTER_SUS": "IE_CARATER_INTER_SUS",
    "IE_TIPO_CONSULTA": "IE_TIPO_CONSULTA",
    # Note: IE_REGIME_INTERNACAO and CD_SETOR_ATENDIMENTO require JOIN
    # with ATEND_CATEGORIA_CONVENIO and ATEND_PACIENTE_UNIDADE — handled
    # by a future enrichment step or provided by the view directly
}

_PATIENT_COLUMNS = {
    # PESSOA_FISICA table uses CD_PESSOA_FISICA as PK
    "CD_PESSOA_FISICA": "NR_PACIENTE",
    "NM_PESSOA_FISICA": "NM_PACIENTE",
    "DT_NASCIMENTO": "DT_NASCIMENTO",
    "IE_SEXO": "TP_SEXO",
    "NR_CPF_CGC": "NR_CPF",
    "IE_SITUACAO": "IE_SITUACAO",
}

_COVERAGE_COLUMNS = {
    # ATEND_CATEGORIA_CONVENIO Oracle -> CoverageAdapter fields
    "NR_SEQ_INTERNO": "NR_SEQ_CONVENIO_PACIENTE",
    "CD_CONVENIO": "CD_CONVENIO",
    "CD_USUARIO_CONVENIO": "NR_CARTEIRA",
    "DT_VALIDADE_CARTEIRA": "DT_VALIDADE",
    "DT_INICIO_VIGENCIA": "DT_INICIO",
    "NR_ATENDIMENTO": "NR_ATENDIMENTO",
    "CD_CATEGORIA": "IE_TIPO_CONVENIO",
    "CD_TIPO_ACOMODACAO": "CD_TIPO_ACOMODACAO",
}

_ORGANIZATION_COLUMNS = {
    # CONVENIO table — Oracle column names differ from adapter expectations
    "CD_CONVENIO": "CD_CONVENIO",
    "DS_CONVENIO": "NM_CONVENIO",
    "CD_CGC": "NR_CNPJ",
    "IE_SITUACAO": "IE_ATIVO",
}

_AUTHORIZATION_COLUMNS = {
    # AUTORIZACAO_CONVENIO Oracle -> TasyAuthorizationAdapter fields
    "NR_SEQ_AUTORIZACAO": "NR_SEQ_AUTORIZACAO",
    "NR_SEQUENCIA": "NR_SEQ_AUTORIZACAO",  # some schemas use NR_SEQUENCIA as PK
    "NR_ATENDIMENTO": "NR_ATENDIMENTO",
    "CD_CONVENIO": "CD_CONVENIO",
    "CD_AUTORIZACAO": "CD_AUTORIZACAO",
    "DT_AUTORIZACAO": "DT_AUTORIZACAO",
    "CD_PESSOA_FISICA": "NR_PACIENTE",
    "IE_ECLIPSE_STATUS": "IE_STATUS_AUTORIZACAO",
    "DT_VALIDADE_GUIA": "DT_VALIDADE_GUIA",
    "DS_MOTIVO_CANCELAMENTO": "DS_MOTIVO_NEGATIVA",
    "CD_PROCEDIMENTO_PRINCIPAL": "CD_PROCEDIMENTO",
    "QT_DIA_AUTORIZADO": "QT_DIAS_AUTORIZADOS",
    # SP-RC-002 accident type (consultant team spec)
    "IE_TISS_TIPO_ACIDENTE": "IE_TISS_TIPO_ACIDENTE",
    "IE_CARATER_INT_TISS": "IE_CARATER_INT_TISS",
}

_PRACTITIONER_COLUMNS = {
    # MEDICO + MEDICO_ESPECIALIDADE + PESSOA_FISICA JOIN -> Practitioner
    "CD_PESSOA_FISICA": "CD_PESSOA_FISICA",
    "NR_CRM": "NR_CRM",
    "UF_CRM": "UF_CRM",
    "NM_GUERRA": "NM_MEDICO",
    "NM_MEDICO": "NM_MEDICO",
    "NM_PESSOA_FISICA": "NM_PESSOA_FISICA",
    "CD_ESPECIALIDADE": "CD_ESPECIALIDADE",
    "DS_ESPECIALIDADE": "DS_ESPECIALIDADE",
    "NR_TELEFONE_CELULAR": "NR_TELEFONE_CELULAR",
}

_CONDITION_COLUMNS = {
    # DIAGNOSTICO_DOENCA + ATENDIMENTO_PACIENTE JOIN -> Condition
    "NR_SEQUENCIA": "NR_SEQ_DIAGNOSTICO",
    "NR_ATENDIMENTO": "NR_ATENDIMENTO",
    "CD_PESSOA_FISICA": "NR_PACIENTE",
    "CD_DOENCA": "CD_DOENCA",
    "DS_DIAG": "DS_DIAG",
    "DT_DIAGNOSTICO": "DT_DIAGNOSTICO",
    "IE_TIPO_DIAGNOSTICO": "IE_TIPO_DIAGNOSTICO",
    "IE_CLASSIFICACAO_DOENCA": "IE_CLASSIFICACAO_DOENCA",
    "IE_SITUACAO": "IE_SITUACAO",
    "DT_LIBERACAO": "DT_LIBERACAO",
}

_PROCEDURE_COLUMNS = {
    "NR_SEQUENCIA": "NR_SEQ_PROCEDIMENTO",
    "CD_PESSOA_FISICA": "NR_PACIENTE",
    "NR_ATENDIMENTO": "NR_ATENDIMENTO",
    "CD_PROCEDIMENTO": "CD_PROCEDIMENTO",
    "DS_PROC_TUSS": "DS_PROCEDIMENTO",
    "CD_PROCEDIMENTO_TUSS": "CD_PROCEDIMENTO_TUSS",
    "DT_PROCEDIMENTO": "DT_PROCEDIMENTO",
    "QT_PROCEDIMENTO": "QT_PROCEDIMENTO",
    "CD_MEDICO_EXEC": "CD_MEDICO_EXEC",
    "NR_SEQ_AUTORIZACAO": "NR_SEQ_AUTORIZACAO",
}

_CLAIM_COLUMNS = {
    "NR_SEQ_AUTORIZACAO": "NR_SEQ_AUTORIZACAO",
    "CD_PESSOA_FISICA": "NR_PACIENTE",
    "CD_CONVENIO": "CD_CONVENIO",
}


def _route(
    adapter_class: type[BaseTasyFhirAdapter],
    fhir_resource_type: str,
    identifier_system: str,
    identifier_field: str,
    column_map: dict[str, str] | None = None,
    use_bundle: bool = False,
) -> list[AdapterRoute]:
    """Helper to create a single-element route list."""
    return [AdapterRoute(
        adapter_class=adapter_class,
        fhir_resource_type=fhir_resource_type,
        identifier_system=identifier_system,
        identifier_field=identifier_field,
        use_bundle=use_bundle,
        column_map=column_map or {},
    )]


# Maps: table_name -> { operation_code -> list[AdapterRoute] }
# Operations: c=create, u=update, r=snapshot-read
TABLE_ADAPTER_MAP: dict[str, dict[str, list[AdapterRoute]]] = {
    "CONVENIO": {
        op: _route(
            TasyOrganizationAdapter, "Organization",
            "http://tasy.com/fhir/identifier/convenio", "CD_CONVENIO",
            _ORGANIZATION_COLUMNS,
        )
        for op in ("c", "u", "r")
    },
    "PESSOA_FISICA": {
        op: _route(
            TasyPatientAdapter, "Patient",
            "http://tasy.com/fhir/identifier/mrn", "NR_PACIENTE",
            _PATIENT_COLUMNS,
        )
        for op in ("c", "u", "r")
    },
    "PACIENTE": {
        op: _route(
            TasyPatientAdapter, "Patient",
            "http://tasy.com/fhir/identifier/mrn", "NR_PACIENTE",
            _PATIENT_COLUMNS,
        )
        for op in ("c", "u", "r")
    },
    "ATEND_CATEGORIA_CONVENIO": {
        op: _route(
            TasyCoverageAdapter, "Coverage",
            "http://tasy.com/fhir/identifier/convenio",
            "NR_SEQ_CONVENIO_PACIENTE",
            _COVERAGE_COLUMNS,
        )
        for op in ("c", "u", "r")
    },
    "ATENDIMENTO_PACIENTE": {
        op: _route(
            TasyEncounterAdapter, "Encounter",
            "http://tasy.com/fhir/identifier/atendimento", "NR_ATENDIMENTO",
            _ENCOUNTER_COLUMNS,
        )
        for op in ("c", "u", "r")
    },
    "PROCEDIMENTO_PACIENTE": {
        op: _route(
            TasyProcedureAdapter, "Procedure",
            "http://tasy.com/fhir/identifier/procedimento",
            "NR_SEQ_PROCEDIMENTO",
            _PROCEDURE_COLUMNS,
        )
        for op in ("c", "u", "r")
    },
    "MEDICO": {
        op: _route(
            TasyPractitionerAdapter, "Practitioner",
            "http://tasy.com/fhir/identifier/medico",
            "CD_PESSOA_FISICA",
            _PRACTITIONER_COLUMNS,
        )
        for op in ("c", "u", "r")
    },
    "DIAGNOSTICO_DOENCA": {
        op: _route(
            TasyConditionAdapter, "Condition",
            "http://tasy.com/fhir/identifier/diagnostico",
            "NR_SEQ_DIAGNOSTICO",
            _CONDITION_COLUMNS,
        )
        for op in ("c", "u", "r")
    },
    "AUTORIZACAO_CONVENIO": {
        op: _route(
            TasyAuthorizationAdapter, "ClaimResponse",
            "http://tasy.com/fhir/identifier/autorizacao",
            "NR_SEQ_AUTORIZACAO",
            _AUTHORIZATION_COLUMNS,
        )
        for op in ("c", "u", "r")
    },
    "AUTORIZACAO_PROCEDIMENTO": {
        "c": _route(
            TasyClaimAdapter, "Claim",
            "http://tasy.com/fhir/identifier/autorizacao",
            "NR_SEQ_AUTORIZACAO", _CLAIM_COLUMNS, use_bundle=True,
        ),
        "u": _route(
            TasyClaimResponseAdapter, "ClaimResponse",
            "http://tasy.com/fhir/identifier/autorizacao",
            "NR_SEQ_AUTORIZACAO", _AUTHORIZATION_COLUMNS, use_bundle=True,
        ),
        "r": _route(
            TasyClaimAdapter, "Claim",
            "http://tasy.com/fhir/identifier/autorizacao",
            "NR_SEQ_AUTORIZACAO", _CLAIM_COLUMNS, use_bundle=True,
        ),
    },
}


def apply_column_map(
    record: dict[str, Any], column_map: dict[str, str]
) -> dict[str, Any]:
    """Rename Oracle CDC columns to adapter-expected field names.

    Columns present in column_map are renamed; all other columns
    are passed through unchanged. Numeric values are converted to
    strings for FHIR identifier compatibility.
    """
    if not column_map:
        return record

    mapped: dict[str, Any] = {}
    for key, value in record.items():
        new_key = column_map.get(key, key)
        mapped[new_key] = value

    # Convert identifier fields to strings (IDs come as int from Avro)
    for id_field in ("NR_PACIENTE", "NR_ATENDIMENTO", "CD_CONVENIO",
                     "NR_SEQ_CONVENIO_PACIENTE", "NR_SEQ_PROCEDIMENTO",
                     "NR_SEQ_AUTORIZACAO", "CD_ESTABELECIMENTO",
                     "NR_CARTEIRA", "CD_PACIENTE", "NR_CPF"):
        if id_field in mapped and isinstance(mapped[id_field], (int, float)):
            mapped[id_field] = str(mapped[id_field])

    # Convert encounter type from numeric to letter code
    if "TP_ATENDIMENTO" in mapped and isinstance(mapped["TP_ATENDIMENTO"], int):
        mapped["TP_ATENDIMENTO"] = _ENCOUNTER_TYPE_MAP.get(
            mapped["TP_ATENDIMENTO"], "A"
        )

    # Convert situation/status from any type to string
    if "IE_SITUACAO" in mapped and mapped["IE_SITUACAO"] is not None:
        mapped["IE_SITUACAO"] = str(mapped["IE_SITUACAO"])

    # Convert IE_ATIVO: Tasy uses A/I, S/N, 1/0, True/False → normalize to S/N
    if "IE_ATIVO" in mapped:
        val = mapped["IE_ATIVO"]
        if val in ("A", "S", 1, "1", True):
            mapped["IE_ATIVO"] = "S"
        elif val in ("I", "N", 0, "0", False, None):
            mapped["IE_ATIVO"] = "N"

    return mapped


class TableAdapterRouter:
    """Resolves CDC table name + operation to adapter route(s)."""

    def resolve(
        self, table_name: str, operation: str
    ) -> list[AdapterRoute] | None:
        """Return adapter route(s) for a given table and CDC operation.

        Args:
            table_name: Oracle table name (e.g., 'ATENDIMENTO_PACIENTE')
            operation: Debezium operation code (c, u, d, r)

        Returns:
            List of AdapterRoute or None if no mapping exists.
        """
        table_map = TABLE_ADAPTER_MAP.get(table_name)
        if table_map is None:
            return None
        return table_map.get(operation)
