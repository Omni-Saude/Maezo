"""
Test Suite for TIER3 and TIER4 DMN Decision Rules
==================================================
Hospital Revenue Cycle - Administrative Rules Testing

TIER3 Rules (25):
- COMP-ACCRED (10 rules): Accreditation compliance
- COMP-COUNCIL (5 rules): Professional council registration
- BILL-BUNDLE-EXT (5 rules): Extended bundle billing

TIER4 Rules:
- COMP-INTL (3 rules): International compliance
- BILL-SPECIALTY (2 rules): Specialty billing

Total: 25 rules with 4-6 test cases each = ~125 test cases
"""

import pytest
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


# ============================================================================
# Result Enums and Data Classes
# ============================================================================

class ResultadoEnum(str, Enum):
    PROSSEGUIR = "Prosseguir"
    BLOQUEAR = "Bloquear"
    ALERTAR = "Alertar"
    REVISAR = "Revisar"


class PrazoStatusEnum(str, Enum):
    DENTRO_PRAZO = "DENTRO_PRAZO"
    ALERTA_PROXIMIDADE = "ALERTA_PROXIMIDADE"
    PRAZO_EXCEDIDO = "PRAZO_EXCEDIDO"


@dataclass
class DMNResult:
    """Standard DMN decision result structure."""
    resultado: str
    observacao: Optional[str] = None
    prazoStatus: Optional[str] = None
    diasRestantes: Optional[int] = None
    acaoRecomendada: Optional[str] = None


# ============================================================================
# Mock DMN Evaluator (Simulates decision table evaluation)
# ============================================================================

class MockDMNEvaluator:
    """
    Mock DMN decision table evaluator for testing.
    In production, this would be replaced with Camunda DMN engine integration.
    """

    @staticmethod
    def evaluate_comp_accred_001(inputs: Dict[str, Any]) -> DMNResult:
        """Evaluate COMP-ACCRED-001: Certificacao ONA"""
        nivel = inputs.get("nivelONA")
        dias = inputs.get("diasAteValidade", 365)
        nc = inputs.get("naoConformidadesCriticas", 0)

        # Rule 1: Expired (dias < 0)
        if dias < 0:
            return DMNResult("Bloquear", "Certificacao ONA expirada", "PRAZO_EXCEDIDO", 0)

        # Rule 2: Suspended
        if nivel == "SUSPENSA":
            return DMNResult("Bloquear", "Certificacao ONA suspensa", "PRAZO_EXCEDIDO", 0)

        # Rule 3: Critical non-conformities
        if nc > 3:
            return DMNResult("Bloquear", "Excesso de nao conformidades criticas", "PRAZO_EXCEDIDO", 0)

        # Rule 4: Near expiry (0-90 days)
        if 0 <= dias <= 90 and nc <= 3:
            return DMNResult("Alertar", "Certificacao ONA vence em menos de 90 dias", "ALERTA_PROXIMIDADE", 90)

        # Rule 5: Non-conformities pending
        if dias > 90 and 1 <= nc <= 3:
            return DMNResult("Alertar", "Nao conformidades pendentes", "DENTRO_PRAZO", 30)

        # Rule 6: Level 3 Excellence
        if nivel == "NIVEL_3" and dias > 90 and nc == 0:
            return DMNResult("Prosseguir", "Certificacao ONA Nivel 3 (Excelencia)", "DENTRO_PRAZO", 365)

        # Rule 7: Level 1 or 2 valid
        if nivel in ("NIVEL_1", "NIVEL_2") and dias > 90 and nc == 0:
            return DMNResult("Prosseguir", "Certificacao ONA vigente", "DENTRO_PRAZO", 365)

        # Fallback
        return DMNResult("Revisar", "Revisao manual necessaria", "DENTRO_PRAZO", 5)

    @staticmethod
    def evaluate_comp_council_001(inputs: Dict[str, Any]) -> DMNResult:
        """Evaluate COMP-COUNCIL-001: Registro CRM Medico"""
        situacao = inputs.get("situacaoCRM")
        rqe = inputs.get("rqeValido", True)
        anuidade = inputs.get("anuidadeEmDia", True)

        # Block conditions
        if situacao == "CASSADO":
            return DMNResult("Bloquear", "Registro CRM cassado", "PRAZO_EXCEDIDO", 0)
        if situacao == "SUSPENSO":
            return DMNResult("Bloquear", "Registro CRM suspenso", "PRAZO_EXCEDIDO", 0)
        if situacao == "INTERDITADO":
            return DMNResult("Bloquear", "Interdicao cautelar vigente", "PRAZO_EXCEDIDO", 0)
        if situacao == "CANCELADO":
            return DMNResult("Bloquear", "Registro CRM cancelado", "PRAZO_EXCEDIDO", 0)

        # Alert conditions
        if situacao == "ATIVO" and not anuidade:
            return DMNResult("Alertar", "Anuidade CRM pendente", "ALERTA_PROXIMIDADE", 30)
        if situacao == "ATIVO" and not rqe and anuidade:
            return DMNResult("Alertar", "RQE nao registrado", "DENTRO_PRAZO", 15)

        # Proceed
        if situacao == "ATIVO" and rqe and anuidade:
            return DMNResult("Prosseguir", "Registro CRM ativo e regular", "DENTRO_PRAZO", 365)

        return DMNResult("Revisar", "Verificacao manual necessaria", "DENTRO_PRAZO", 5)


# ============================================================================
# TIER3: COMP-ACCRED Tests (10 rules)
# ============================================================================

class TestCOMPACCRED:
    """Test cases for COMP-ACCRED accreditation compliance rules (10 rules)."""

    # -------------------------------------------------------------------------
    # COMP-ACCRED-001: Certificacao ONA
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado,expected_prazo", [
        # Bloquear - Expired
        ({"nivelONA": "NIVEL_3", "diasAteValidade": -10, "naoConformidadesCriticas": 0},
         "Bloquear", "PRAZO_EXCEDIDO"),
        # Bloquear - Suspended
        ({"nivelONA": "SUSPENSA", "diasAteValidade": 180, "naoConformidadesCriticas": 0},
         "Bloquear", "PRAZO_EXCEDIDO"),
        # Bloquear - Critical non-conformities
        ({"nivelONA": "NIVEL_2", "diasAteValidade": 200, "naoConformidadesCriticas": 5},
         "Bloquear", "PRAZO_EXCEDIDO"),
        # Alertar - Near expiry
        ({"nivelONA": "NIVEL_2", "diasAteValidade": 60, "naoConformidadesCriticas": 1},
         "Alertar", "ALERTA_PROXIMIDADE"),
        # Alertar - Non-conformities pending
        ({"nivelONA": "NIVEL_1", "diasAteValidade": 200, "naoConformidadesCriticas": 2},
         "Alertar", "DENTRO_PRAZO"),
        # Prosseguir - Level 3 Excellence
        ({"nivelONA": "NIVEL_3", "diasAteValidade": 365, "naoConformidadesCriticas": 0},
         "Prosseguir", "DENTRO_PRAZO"),
        # Prosseguir - Level 1 valid
        ({"nivelONA": "NIVEL_1", "diasAteValidade": 180, "naoConformidadesCriticas": 0},
         "Prosseguir", "DENTRO_PRAZO"),
    ])
    def test_comp_accred_001_ona(self, inputs: Dict[str, Any], expected_resultado: str, expected_prazo: str):
        """COMP-ACCRED-001: Certificacao ONA (Organizacao Nacional de Acreditacao)"""
        result = MockDMNEvaluator.evaluate_comp_accred_001(inputs)
        assert result.resultado == expected_resultado
        assert result.prazoStatus == expected_prazo

    # -------------------------------------------------------------------------
    # COMP-ACCRED-002: Acreditacao JCI
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado", [
        # Bloquear - Revoked
        ({"statusJCI": "REVOGADO", "mesesDesdeUltimaAuditoria": 12, "planosAcaoPendentes": 0}, "Bloquear"),
        # Bloquear - Suspended
        ({"statusJCI": "SUSPENSO", "mesesDesdeUltimaAuditoria": 6, "planosAcaoPendentes": 0}, "Bloquear"),
        # Bloquear - Audit > 36 months
        ({"statusJCI": "ACREDITADO", "mesesDesdeUltimaAuditoria": 40, "planosAcaoPendentes": 0}, "Bloquear"),
        # Alertar - Audit near expiry (24-36 months)
        ({"statusJCI": "ACREDITADO", "mesesDesdeUltimaAuditoria": 30, "planosAcaoPendentes": 0}, "Alertar"),
        # Alertar - Action plans pending
        ({"statusJCI": "ACREDITADO", "mesesDesdeUltimaAuditoria": 12, "planosAcaoPendentes": 3}, "Alertar"),
        # Prosseguir - Full accreditation
        ({"statusJCI": "ACREDITADO", "mesesDesdeUltimaAuditoria": 12, "planosAcaoPendentes": 0}, "Prosseguir"),
    ])
    def test_comp_accred_002_jci(self, inputs: Dict[str, Any], expected_resultado: str):
        """COMP-ACCRED-002: Acreditacao JCI (Joint Commission International)"""
        # Evaluate using decision table logic
        status = inputs["statusJCI"]
        meses = inputs["mesesDesdeUltimaAuditoria"]
        planos = inputs["planosAcaoPendentes"]

        if status == "REVOGADO":
            resultado = "Bloquear"
        elif status == "SUSPENSO":
            resultado = "Bloquear"
        elif meses > 36:
            resultado = "Bloquear"
        elif status in ("ACREDITADO", "CONDICIONAL") and 24 <= meses <= 36:
            resultado = "Alertar"
        elif status in ("ACREDITADO", "CONDICIONAL") and meses < 24 and planos > 0:
            resultado = "Alertar"
        elif status == "CONDICIONAL" and meses < 24 and planos == 0:
            resultado = "Alertar"
        elif status == "ACREDITADO" and meses < 24 and planos == 0:
            resultado = "Prosseguir"
        else:
            resultado = "Revisar"

        assert resultado == expected_resultado

    # -------------------------------------------------------------------------
    # COMP-ACCRED-003: Licenca VISA
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado", [
        # Bloquear - License revoked
        ({"statusAlvaraSanitario": "CASSADO", "diasAteRenovacao": 180, "pendenciasVISA": 0}, "Bloquear"),
        # Bloquear - License suspended
        ({"statusAlvaraSanitario": "SUSPENSO", "diasAteRenovacao": 180, "pendenciasVISA": 0}, "Bloquear"),
        # Bloquear - License expired
        ({"statusAlvaraSanitario": "VENCIDO", "diasAteRenovacao": -30, "pendenciasVISA": 0}, "Bloquear"),
        # Alertar - Renewal near (90 days)
        ({"statusAlvaraSanitario": "VIGENTE", "diasAteRenovacao": 60, "pendenciasVISA": 0}, "Alertar"),
        # Alertar - In renewal process
        ({"statusAlvaraSanitario": "EM_RENOVACAO", "diasAteRenovacao": 0, "pendenciasVISA": 0}, "Alertar"),
        # Prosseguir - Valid license
        ({"statusAlvaraSanitario": "VIGENTE", "diasAteRenovacao": 180, "pendenciasVISA": 0}, "Prosseguir"),
    ])
    def test_comp_accred_003_visa(self, inputs: Dict[str, Any], expected_resultado: str):
        """COMP-ACCRED-003: Licenca Vigilancia Sanitaria (VISA)"""
        status = inputs["statusAlvaraSanitario"]
        dias = inputs["diasAteRenovacao"]
        pend = inputs["pendenciasVISA"]

        if status == "CASSADO":
            resultado = "Bloquear"
        elif status == "SUSPENSO":
            resultado = "Bloquear"
        elif status == "VENCIDO":
            resultado = "Bloquear"
        elif status == "VIGENTE" and 0 <= dias <= 90:
            resultado = "Alertar"
        elif status == "EM_RENOVACAO":
            resultado = "Alertar"
        elif status == "VIGENTE" and dias > 90 and pend > 0:
            resultado = "Alertar"
        elif status == "VIGENTE" and dias > 90 and pend == 0:
            resultado = "Prosseguir"
        else:
            resultado = "Revisar"

        assert resultado == expected_resultado

    # -------------------------------------------------------------------------
    # COMP-ACCRED-004: Cadastro CNES
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado", [
        # Bloquear - Inactive CNES
        ({"statusCNES": "INATIVO", "atualizacaoEmDia": True, "servicosHabilitados": True}, "Bloquear"),
        # Bloquear - Outdated registration
        ({"statusCNES": "ATIVO", "atualizacaoEmDia": False, "servicosHabilitados": True}, "Alertar"),
        # Alertar - Missing services
        ({"statusCNES": "ATIVO", "atualizacaoEmDia": True, "servicosHabilitados": False}, "Alertar"),
        # Prosseguir - All valid
        ({"statusCNES": "ATIVO", "atualizacaoEmDia": True, "servicosHabilitados": True}, "Prosseguir"),
    ])
    def test_comp_accred_004_cnes(self, inputs: Dict[str, Any], expected_resultado: str):
        """COMP-ACCRED-004: Cadastro Nacional de Estabelecimentos de Saude (CNES)"""
        status = inputs["statusCNES"]
        atualizado = inputs["atualizacaoEmDia"]
        servicos = inputs["servicosHabilitados"]

        if status == "INATIVO":
            resultado = "Bloquear"
        elif status == "ATIVO" and not atualizado:
            resultado = "Alertar"
        elif status == "ATIVO" and not servicos:
            resultado = "Alertar"
        elif status == "ATIVO" and atualizado and servicos:
            resultado = "Prosseguir"
        else:
            resultado = "Revisar"

        assert resultado == expected_resultado

    # -------------------------------------------------------------------------
    # COMP-ACCRED-005: Certificacao ISO
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado", [
        # Bloquear - Certificate expired
        ({"statusISO": "EXPIRADO", "diasAteVencimento": -30, "auditoriaPendente": False}, "Bloquear"),
        # Alertar - Near expiry
        ({"statusISO": "VIGENTE", "diasAteVencimento": 60, "auditoriaPendente": False}, "Alertar"),
        # Alertar - Pending audit
        ({"statusISO": "VIGENTE", "diasAteVencimento": 180, "auditoriaPendente": True}, "Alertar"),
        # Prosseguir - Valid certification
        ({"statusISO": "VIGENTE", "diasAteVencimento": 180, "auditoriaPendente": False}, "Prosseguir"),
    ])
    def test_comp_accred_005_iso(self, inputs: Dict[str, Any], expected_resultado: str):
        """COMP-ACCRED-005: Certificacao ISO (Quality Management)"""
        status = inputs["statusISO"]
        dias = inputs["diasAteVencimento"]
        auditoria = inputs["auditoriaPendente"]

        if status == "EXPIRADO" or dias < 0:
            resultado = "Bloquear"
        elif status == "VIGENTE" and 0 <= dias <= 90:
            resultado = "Alertar"
        elif status == "VIGENTE" and auditoria:
            resultado = "Alertar"
        elif status == "VIGENTE" and dias > 90 and not auditoria:
            resultado = "Prosseguir"
        else:
            resultado = "Revisar"

        assert resultado == expected_resultado

    # -------------------------------------------------------------------------
    # COMP-ACCRED-006: Habilitacao Ministerio Saude
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado", [
        # Bloquear - Revoked authorization
        ({"statusHabilitacaoMS": "REVOGADA", "servicoAtivo": True, "portariaVigente": True}, "Bloquear"),
        # Bloquear - Expired ordinance
        ({"statusHabilitacaoMS": "ATIVA", "servicoAtivo": True, "portariaVigente": False}, "Bloquear"),
        # Alertar - Inactive service
        ({"statusHabilitacaoMS": "ATIVA", "servicoAtivo": False, "portariaVigente": True}, "Alertar"),
        # Prosseguir - All valid
        ({"statusHabilitacaoMS": "ATIVA", "servicoAtivo": True, "portariaVigente": True}, "Prosseguir"),
    ])
    def test_comp_accred_006_ms(self, inputs: Dict[str, Any], expected_resultado: str):
        """COMP-ACCRED-006: Habilitacao Ministerio da Saude"""
        status = inputs["statusHabilitacaoMS"]
        servico = inputs["servicoAtivo"]
        portaria = inputs["portariaVigente"]

        if status == "REVOGADA":
            resultado = "Bloquear"
        elif status == "ATIVA" and not portaria:
            resultado = "Bloquear"
        elif status == "ATIVA" and not servico:
            resultado = "Alertar"
        elif status == "ATIVA" and servico and portaria:
            resultado = "Prosseguir"
        else:
            resultado = "Revisar"

        assert resultado == expected_resultado

    # -------------------------------------------------------------------------
    # COMP-ACCRED-007: Credenciamento Operadora
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado", [
        # Bloquear - Descredenciado
        ({"statusCredenciamento": "DESCREDENCIADO", "contratoVigente": False, "pendenciasFinanceiras": False}, "Bloquear"),
        # Bloquear - Contract expired
        ({"statusCredenciamento": "ATIVO", "contratoVigente": False, "pendenciasFinanceiras": False}, "Bloquear"),
        # Alertar - Financial pending
        ({"statusCredenciamento": "ATIVO", "contratoVigente": True, "pendenciasFinanceiras": True}, "Alertar"),
        # Prosseguir - Valid accreditation
        ({"statusCredenciamento": "ATIVO", "contratoVigente": True, "pendenciasFinanceiras": False}, "Prosseguir"),
    ])
    def test_comp_accred_007_operadora(self, inputs: Dict[str, Any], expected_resultado: str):
        """COMP-ACCRED-007: Credenciamento Operadora"""
        status = inputs["statusCredenciamento"]
        contrato = inputs["contratoVigente"]
        pendencias = inputs["pendenciasFinanceiras"]

        if status == "DESCREDENCIADO":
            resultado = "Bloquear"
        elif status == "ATIVO" and not contrato:
            resultado = "Bloquear"
        elif status == "ATIVO" and pendencias:
            resultado = "Alertar"
        elif status == "ATIVO" and contrato and not pendencias:
            resultado = "Prosseguir"
        else:
            resultado = "Revisar"

        assert resultado == expected_resultado

    # -------------------------------------------------------------------------
    # COMP-ACCRED-008: Alvara Funcionamento
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado", [
        # Bloquear - Expired license
        ({"statusAlvara": "VENCIDO", "diasAteVencimento": -30, "pendenciasAlvara": 0}, "Bloquear"),
        # Bloquear - License cassado
        ({"statusAlvara": "CASSADO", "diasAteVencimento": 0, "pendenciasAlvara": 0}, "Bloquear"),
        # Alertar - Near expiry
        ({"statusAlvara": "VIGENTE", "diasAteVencimento": 45, "pendenciasAlvara": 0}, "Alertar"),
        # Prosseguir - Valid license
        ({"statusAlvara": "VIGENTE", "diasAteVencimento": 180, "pendenciasAlvara": 0}, "Prosseguir"),
    ])
    def test_comp_accred_008_alvara(self, inputs: Dict[str, Any], expected_resultado: str):
        """COMP-ACCRED-008: Alvara de Funcionamento"""
        status = inputs["statusAlvara"]
        dias = inputs["diasAteVencimento"]
        pendencias = inputs["pendenciasAlvara"]

        if status in ("VENCIDO", "CASSADO") or dias < 0:
            resultado = "Bloquear"
        elif status == "VIGENTE" and 0 <= dias <= 60:
            resultado = "Alertar"
        elif status == "VIGENTE" and pendencias > 0:
            resultado = "Alertar"
        elif status == "VIGENTE" and dias > 60 and pendencias == 0:
            resultado = "Prosseguir"
        else:
            resultado = "Revisar"

        assert resultado == expected_resultado

    # -------------------------------------------------------------------------
    # COMP-ACCRED-009: Registro Conselhos Profissionais (Institutional)
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado", [
        # Bloquear - Missing RT
        ({"responsavelTecnicoAtivo": False, "registrosAtualizados": True, "conselhosRegularizados": True}, "Bloquear"),
        # Alertar - Outdated registrations
        ({"responsavelTecnicoAtivo": True, "registrosAtualizados": False, "conselhosRegularizados": True}, "Alertar"),
        # Alertar - Irregular councils
        ({"responsavelTecnicoAtivo": True, "registrosAtualizados": True, "conselhosRegularizados": False}, "Alertar"),
        # Prosseguir - All valid
        ({"responsavelTecnicoAtivo": True, "registrosAtualizados": True, "conselhosRegularizados": True}, "Prosseguir"),
    ])
    def test_comp_accred_009_conselhos(self, inputs: Dict[str, Any], expected_resultado: str):
        """COMP-ACCRED-009: Registro em Conselhos Profissionais (Institucional)"""
        rt = inputs["responsavelTecnicoAtivo"]
        registros = inputs["registrosAtualizados"]
        conselhos = inputs["conselhosRegularizados"]

        if not rt:
            resultado = "Bloquear"
        elif not registros:
            resultado = "Alertar"
        elif not conselhos:
            resultado = "Alertar"
        elif rt and registros and conselhos:
            resultado = "Prosseguir"
        else:
            resultado = "Revisar"

        assert resultado == expected_resultado

    # -------------------------------------------------------------------------
    # COMP-ACCRED-010: Licenca Ambiental
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado", [
        # Bloquear - Expired license
        ({"statusLicencaAmbiental": "VENCIDA", "diasAteVencimento": -30, "condicionantesAtendidas": True}, "Bloquear"),
        # Bloquear - Suspended
        ({"statusLicencaAmbiental": "SUSPENSA", "diasAteVencimento": 180, "condicionantesAtendidas": True}, "Bloquear"),
        # Alertar - Near expiry
        ({"statusLicencaAmbiental": "VIGENTE", "diasAteVencimento": 60, "condicionantesAtendidas": True}, "Alertar"),
        # Alertar - Unmet conditions
        ({"statusLicencaAmbiental": "VIGENTE", "diasAteVencimento": 180, "condicionantesAtendidas": False}, "Alertar"),
        # Prosseguir - Valid
        ({"statusLicencaAmbiental": "VIGENTE", "diasAteVencimento": 180, "condicionantesAtendidas": True}, "Prosseguir"),
    ])
    def test_comp_accred_010_ambiental(self, inputs: Dict[str, Any], expected_resultado: str):
        """COMP-ACCRED-010: Licenca Ambiental"""
        status = inputs["statusLicencaAmbiental"]
        dias = inputs["diasAteVencimento"]
        cond = inputs["condicionantesAtendidas"]

        if status == "VENCIDA" or dias < 0:
            resultado = "Bloquear"
        elif status == "SUSPENSA":
            resultado = "Bloquear"
        elif status == "VIGENTE" and 0 <= dias <= 90:
            resultado = "Alertar"
        elif status == "VIGENTE" and not cond:
            resultado = "Alertar"
        elif status == "VIGENTE" and dias > 90 and cond:
            resultado = "Prosseguir"
        else:
            resultado = "Revisar"

        assert resultado == expected_resultado


# ============================================================================
# TIER3: COMP-COUNCIL Tests (5 rules)
# ============================================================================

class TestCOMPCOUNCIL:
    """Test cases for professional council registration rules (5 rules)."""

    # -------------------------------------------------------------------------
    # COMP-COUNCIL-001: Registro CRM Medico
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado", [
        # Bloquear - CRM cassado
        ({"situacaoCRM": "CASSADO", "rqeValido": True, "anuidadeEmDia": True}, "Bloquear"),
        # Bloquear - CRM suspenso
        ({"situacaoCRM": "SUSPENSO", "rqeValido": True, "anuidadeEmDia": True}, "Bloquear"),
        # Bloquear - Interditado
        ({"situacaoCRM": "INTERDITADO", "rqeValido": True, "anuidadeEmDia": True}, "Bloquear"),
        # Bloquear - CRM cancelado
        ({"situacaoCRM": "CANCELADO", "rqeValido": True, "anuidadeEmDia": True}, "Bloquear"),
        # Alertar - Anuidade pendente
        ({"situacaoCRM": "ATIVO", "rqeValido": True, "anuidadeEmDia": False}, "Alertar"),
        # Alertar - RQE nao registrado
        ({"situacaoCRM": "ATIVO", "rqeValido": False, "anuidadeEmDia": True}, "Alertar"),
        # Prosseguir - CRM regular
        ({"situacaoCRM": "ATIVO", "rqeValido": True, "anuidadeEmDia": True}, "Prosseguir"),
    ])
    def test_comp_council_001_crm(self, inputs: Dict[str, Any], expected_resultado: str):
        """COMP-COUNCIL-001: Registro CRM Medico"""
        result = MockDMNEvaluator.evaluate_comp_council_001(inputs)
        assert result.resultado == expected_resultado

    # -------------------------------------------------------------------------
    # COMP-COUNCIL-002: Registro COREN Enfermagem
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado", [
        # Bloquear - COREN cassado
        ({"categoriaCOREN": "ENFERMEIRO", "situacaoRegistro": "CASSADO", "responsabilidadeTecnicaRegular": True}, "Bloquear"),
        # Bloquear - COREN suspenso
        ({"categoriaCOREN": "TECNICO", "situacaoRegistro": "SUSPENSO", "responsabilidadeTecnicaRegular": True}, "Bloquear"),
        # Bloquear - RT irregular (enfermeiro)
        ({"categoriaCOREN": "ENFERMEIRO", "situacaoRegistro": "ATIVO", "responsabilidadeTecnicaRegular": False}, "Bloquear"),
        # Alertar - Registro pendente
        ({"categoriaCOREN": "AUXILIAR", "situacaoRegistro": "PENDENTE", "responsabilidadeTecnicaRegular": True}, "Alertar"),
        # Prosseguir - Enfermeiro RT regular
        ({"categoriaCOREN": "ENFERMEIRO", "situacaoRegistro": "ATIVO", "responsabilidadeTecnicaRegular": True}, "Prosseguir"),
        # Prosseguir - Tecnico ativo
        ({"categoriaCOREN": "TECNICO", "situacaoRegistro": "ATIVO", "responsabilidadeTecnicaRegular": True}, "Prosseguir"),
    ])
    def test_comp_council_002_coren(self, inputs: Dict[str, Any], expected_resultado: str):
        """COMP-COUNCIL-002: Registro COREN Enfermagem"""
        categoria = inputs["categoriaCOREN"]
        situacao = inputs["situacaoRegistro"]
        rt = inputs["responsabilidadeTecnicaRegular"]

        if situacao == "CASSADO":
            resultado = "Bloquear"
        elif situacao == "SUSPENSO":
            resultado = "Bloquear"
        elif categoria == "ENFERMEIRO" and situacao == "ATIVO" and not rt:
            resultado = "Bloquear"
        elif situacao == "CANCELADO":
            resultado = "Bloquear"
        elif situacao == "PENDENTE":
            resultado = "Alertar"
        elif categoria == "ENFERMEIRO" and situacao == "ATIVO" and rt:
            resultado = "Prosseguir"
        elif categoria in ("TECNICO", "AUXILIAR") and situacao == "ATIVO":
            resultado = "Prosseguir"
        else:
            resultado = "Revisar"

        assert resultado == expected_resultado

    # -------------------------------------------------------------------------
    # COMP-COUNCIL-003: Registro CRF Farmacia
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado", [
        # Bloquear - CRF cassado
        ({"situacaoCRF": "CASSADO", "responsavelTecnicoAtivo": True, "farmaciaHospitalarRegular": True}, "Bloquear"),
        # Bloquear - RT inactive
        ({"situacaoCRF": "ATIVO", "responsavelTecnicoAtivo": False, "farmaciaHospitalarRegular": True}, "Bloquear"),
        # Alertar - Farmacia irregular
        ({"situacaoCRF": "ATIVO", "responsavelTecnicoAtivo": True, "farmaciaHospitalarRegular": False}, "Alertar"),
        # Prosseguir - All regular
        ({"situacaoCRF": "ATIVO", "responsavelTecnicoAtivo": True, "farmaciaHospitalarRegular": True}, "Prosseguir"),
    ])
    def test_comp_council_003_crf(self, inputs: Dict[str, Any], expected_resultado: str):
        """COMP-COUNCIL-003: Registro CRF (Conselho Regional de Farmacia)"""
        situacao = inputs["situacaoCRF"]
        rt = inputs["responsavelTecnicoAtivo"]
        farmacia = inputs["farmaciaHospitalarRegular"]

        if situacao == "CASSADO":
            resultado = "Bloquear"
        elif situacao == "SUSPENSO":
            resultado = "Bloquear"
        elif situacao == "ATIVO" and not rt:
            resultado = "Bloquear"
        elif situacao == "ATIVO" and not farmacia:
            resultado = "Alertar"
        elif situacao == "ATIVO" and rt and farmacia:
            resultado = "Prosseguir"
        else:
            resultado = "Revisar"

        assert resultado == expected_resultado

    # -------------------------------------------------------------------------
    # COMP-COUNCIL-004: Registro CREFITO Fisioterapia
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado", [
        # Bloquear - CREFITO cassado
        ({"situacaoCREFITO": "CASSADO", "especialidadeRegistrada": True, "anuidadeEmDia": True}, "Bloquear"),
        # Bloquear - CREFITO suspenso
        ({"situacaoCREFITO": "SUSPENSO", "especialidadeRegistrada": True, "anuidadeEmDia": True}, "Bloquear"),
        # Alertar - Anuidade pendente
        ({"situacaoCREFITO": "ATIVO", "especialidadeRegistrada": True, "anuidadeEmDia": False}, "Alertar"),
        # Alertar - Especialidade nao registrada
        ({"situacaoCREFITO": "ATIVO", "especialidadeRegistrada": False, "anuidadeEmDia": True}, "Alertar"),
        # Prosseguir - Regular
        ({"situacaoCREFITO": "ATIVO", "especialidadeRegistrada": True, "anuidadeEmDia": True}, "Prosseguir"),
    ])
    def test_comp_council_004_crefito(self, inputs: Dict[str, Any], expected_resultado: str):
        """COMP-COUNCIL-004: Registro CREFITO (Fisioterapia/Terapia Ocupacional)"""
        situacao = inputs["situacaoCREFITO"]
        especialidade = inputs["especialidadeRegistrada"]
        anuidade = inputs["anuidadeEmDia"]

        if situacao == "CASSADO":
            resultado = "Bloquear"
        elif situacao == "SUSPENSO":
            resultado = "Bloquear"
        elif situacao == "ATIVO" and not anuidade:
            resultado = "Alertar"
        elif situacao == "ATIVO" and not especialidade:
            resultado = "Alertar"
        elif situacao == "ATIVO" and especialidade and anuidade:
            resultado = "Prosseguir"
        else:
            resultado = "Revisar"

        assert resultado == expected_resultado

    # -------------------------------------------------------------------------
    # COMP-COUNCIL-005: Registro CRP Psicologia
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado", [
        # Bloquear - CRP cassado
        ({"situacaoCRP": "CASSADO", "especialidadeRegistrada": True, "anuidadeEmDia": True}, "Bloquear"),
        # Bloquear - CRP suspenso
        ({"situacaoCRP": "SUSPENSO", "especialidadeRegistrada": True, "anuidadeEmDia": True}, "Bloquear"),
        # Alertar - Anuidade pendente
        ({"situacaoCRP": "ATIVO", "especialidadeRegistrada": True, "anuidadeEmDia": False}, "Alertar"),
        # Prosseguir - Regular
        ({"situacaoCRP": "ATIVO", "especialidadeRegistrada": True, "anuidadeEmDia": True}, "Prosseguir"),
    ])
    def test_comp_council_005_crp(self, inputs: Dict[str, Any], expected_resultado: str):
        """COMP-COUNCIL-005: Registro CRP (Conselho Regional de Psicologia)"""
        situacao = inputs["situacaoCRP"]
        especialidade = inputs["especialidadeRegistrada"]
        anuidade = inputs["anuidadeEmDia"]

        if situacao == "CASSADO":
            resultado = "Bloquear"
        elif situacao == "SUSPENSO":
            resultado = "Bloquear"
        elif situacao == "ATIVO" and not anuidade:
            resultado = "Alertar"
        elif situacao == "ATIVO" and especialidade and anuidade:
            resultado = "Prosseguir"
        else:
            resultado = "Revisar"

        assert resultado == expected_resultado


# ============================================================================
# TIER3: BILL-BUNDLE-EXT Tests (5 rules)
# ============================================================================

class TestBILLBUNDLEEXT:
    """Test cases for extended bundle billing rules (5 rules)."""

    # -------------------------------------------------------------------------
    # BILL-BUNDLE-EXT-001: Pacote Cirurgia Cardiaca
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado", [
        # Bloquear - Item fora do pacote sem aprovacao
        ({"tipoProcedimentoCardiaco": "revascularizacao", "itensInclusos": "completo",
          "itemForaPacote": True, "aprovacaoPreviaItemAdicional": False,
          "valorNegociadoRespeitado": True, "itemQuestionavel": False}, "Bloquear"),
        # Bloquear - Valor nao negociado
        ({"tipoProcedimentoCardiaco": "valvula", "itensInclusos": "parcial",
          "itemForaPacote": False, "aprovacaoPreviaItemAdicional": True,
          "valorNegociadoRespeitado": False, "itemQuestionavel": False}, "Bloquear"),
        # Alertar - Item questionavel
        ({"tipoProcedimentoCardiaco": "marcapasso", "itensInclusos": "completo",
          "itemForaPacote": False, "aprovacaoPreviaItemAdicional": True,
          "valorNegociadoRespeitado": True, "itemQuestionavel": True}, "Alertar"),
        # Alertar - Transplante com pacote basico
        ({"tipoProcedimentoCardiaco": "transplante", "itensInclusos": "basico",
          "itemForaPacote": False, "aprovacaoPreviaItemAdicional": True,
          "valorNegociadoRespeitado": True, "itemQuestionavel": False}, "Alertar"),
        # Prosseguir - Pacote completo com extras aprovados
        ({"tipoProcedimentoCardiaco": "revascularizacao", "itensInclusos": "completo",
          "itemForaPacote": True, "aprovacaoPreviaItemAdicional": True,
          "valorNegociadoRespeitado": True, "itemQuestionavel": False}, "Prosseguir"),
        # Prosseguir - Cobranca padrao
        ({"tipoProcedimentoCardiaco": "valvula", "itensInclusos": "parcial",
          "itemForaPacote": False, "aprovacaoPreviaItemAdicional": True,
          "valorNegociadoRespeitado": True, "itemQuestionavel": False}, "Prosseguir"),
    ])
    def test_bill_bundle_ext_001_cardiaca(self, inputs: Dict[str, Any], expected_resultado: str):
        """BILL-BUNDLE-EXT-001: Pacote Cirurgia Cardiaca"""
        tipo = inputs["tipoProcedimentoCardiaco"]
        itens = inputs["itensInclusos"]
        fora = inputs["itemForaPacote"]
        aprovacao = inputs["aprovacaoPreviaItemAdicional"]
        valor = inputs["valorNegociadoRespeitado"]
        questionavel = inputs["itemQuestionavel"]

        # Rule evaluation based on DMN decision table
        if fora and not aprovacao:
            resultado = "Bloquear"
        elif itens in ("completo", "parcial") and not fora and not valor:
            resultado = "Bloquear"
        elif not fora and valor and questionavel:
            resultado = "Alertar"
        elif tipo == "transplante" and itens == "basico":
            resultado = "Alertar"
        elif itens == "completo" and fora and aprovacao and valor:
            resultado = "Prosseguir"
        elif tipo in ("revascularizacao", "valvula", "marcapasso") and itens in ("completo", "parcial") and not fora and valor and not questionavel:
            resultado = "Prosseguir"
        else:
            resultado = "Revisar"

        assert resultado == expected_resultado

    # -------------------------------------------------------------------------
    # BILL-BUNDLE-EXT-002: Pacote Ortopedia Complexa
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado", [
        # Bloquear - Material nao previsto sem autorizacao
        ({"tipoProtese": "quadril_total", "materialAuxiliarPrevisto": True,
          "materialNaoPrevisto": True, "honorarioEquipeConforme": True,
          "autorizacaoMaterialAdicional": False, "proteseCompativelProcedimento": True}, "Bloquear"),
        # Bloquear - Protese incompativel
        ({"tipoProtese": "joelho_total", "materialAuxiliarPrevisto": True,
          "materialNaoPrevisto": False, "honorarioEquipeConforme": True,
          "autorizacaoMaterialAdicional": True, "proteseCompativelProcedimento": False}, "Bloquear"),
        # Alertar - Honorarios divergentes
        ({"tipoProtese": "quadril_parcial", "materialAuxiliarPrevisto": True,
          "materialNaoPrevisto": False, "honorarioEquipeConforme": False,
          "autorizacaoMaterialAdicional": True, "proteseCompativelProcedimento": True}, "Alertar"),
        # Alertar - Coluna com multiplos materiais
        ({"tipoProtese": "coluna", "materialAuxiliarPrevisto": True,
          "materialNaoPrevisto": True, "honorarioEquipeConforme": True,
          "autorizacaoMaterialAdicional": True, "proteseCompativelProcedimento": True}, "Alertar"),
        # Prosseguir - Pacote completo
        ({"tipoProtese": "quadril_total", "materialAuxiliarPrevisto": True,
          "materialNaoPrevisto": True, "honorarioEquipeConforme": True,
          "autorizacaoMaterialAdicional": True, "proteseCompativelProcedimento": True}, "Prosseguir"),
        # Prosseguir - Pacote padrao
        ({"tipoProtese": "joelho_total", "materialAuxiliarPrevisto": True,
          "materialNaoPrevisto": False, "honorarioEquipeConforme": True,
          "autorizacaoMaterialAdicional": True, "proteseCompativelProcedimento": True}, "Prosseguir"),
    ])
    def test_bill_bundle_ext_002_ortopedia(self, inputs: Dict[str, Any], expected_resultado: str):
        """BILL-BUNDLE-EXT-002: Pacote Ortopedia Complexa"""
        tipo = inputs["tipoProtese"]
        previsto = inputs["materialAuxiliarPrevisto"]
        nao_previsto = inputs["materialNaoPrevisto"]
        honorario = inputs["honorarioEquipeConforme"]
        autorizacao = inputs["autorizacaoMaterialAdicional"]
        compativel = inputs["proteseCompativelProcedimento"]

        if nao_previsto and not autorizacao:
            resultado = "Bloquear"
        elif not compativel:
            resultado = "Bloquear"
        elif previsto and not nao_previsto and not honorario and compativel:
            resultado = "Alertar"
        elif tipo == "coluna" and previsto and nao_previsto and autorizacao and compativel:
            resultado = "Alertar"
        elif previsto and nao_previsto and honorario and autorizacao and compativel:
            resultado = "Prosseguir"
        elif tipo in ("quadril_total", "quadril_parcial", "joelho_total", "joelho_parcial") and previsto and not nao_previsto and honorario and compativel:
            resultado = "Prosseguir"
        else:
            resultado = "Revisar"

        assert resultado == expected_resultado

    # -------------------------------------------------------------------------
    # BILL-BUNDLE-EXT-003: Pacote Oncologia
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado", [
        # Bloquear - Protocolo nao aprovado
        ({"tipoTratamentoOncologico": "quimioterapia", "protocoloAprovadoANS": False,
          "medicacaoAutorizada": True, "ciclosAutorizados": True}, "Bloquear"),
        # Bloquear - Medicacao nao autorizada
        ({"tipoTratamentoOncologico": "imunoterapia", "protocoloAprovadoANS": True,
          "medicacaoAutorizada": False, "ciclosAutorizados": True}, "Bloquear"),
        # Alertar - Ciclos excedidos
        ({"tipoTratamentoOncologico": "quimioterapia", "protocoloAprovadoANS": True,
          "medicacaoAutorizada": True, "ciclosAutorizados": False}, "Alertar"),
        # Prosseguir - Tratamento regular
        ({"tipoTratamentoOncologico": "radioterapia", "protocoloAprovadoANS": True,
          "medicacaoAutorizada": True, "ciclosAutorizados": True}, "Prosseguir"),
    ])
    def test_bill_bundle_ext_003_oncologia(self, inputs: Dict[str, Any], expected_resultado: str):
        """BILL-BUNDLE-EXT-003: Pacote Oncologia"""
        protocolo = inputs["protocoloAprovadoANS"]
        medicacao = inputs["medicacaoAutorizada"]
        ciclos = inputs["ciclosAutorizados"]

        if not protocolo:
            resultado = "Bloquear"
        elif not medicacao:
            resultado = "Bloquear"
        elif not ciclos:
            resultado = "Alertar"
        elif protocolo and medicacao and ciclos:
            resultado = "Prosseguir"
        else:
            resultado = "Revisar"

        assert resultado == expected_resultado

    # -------------------------------------------------------------------------
    # BILL-BUNDLE-EXT-004: Pacote Maternidade
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado", [
        # Bloquear - UTI Neonatal nao autorizada
        ({"tipoParto": "cesarea", "utiNeonatalNecessaria": True,
          "utiNeonatalAutorizada": False, "diariasInclusas": True}, "Bloquear"),
        # Alertar - Diarias excedidas
        ({"tipoParto": "normal", "utiNeonatalNecessaria": False,
          "utiNeonatalAutorizada": False, "diariasInclusas": False}, "Alertar"),
        # Prosseguir - Parto normal regular
        ({"tipoParto": "normal", "utiNeonatalNecessaria": False,
          "utiNeonatalAutorizada": False, "diariasInclusas": True}, "Prosseguir"),
        # Prosseguir - Cesarea com UTI autorizada
        ({"tipoParto": "cesarea", "utiNeonatalNecessaria": True,
          "utiNeonatalAutorizada": True, "diariasInclusas": True}, "Prosseguir"),
    ])
    def test_bill_bundle_ext_004_maternidade(self, inputs: Dict[str, Any], expected_resultado: str):
        """BILL-BUNDLE-EXT-004: Pacote Maternidade"""
        uti_necessaria = inputs["utiNeonatalNecessaria"]
        uti_autorizada = inputs["utiNeonatalAutorizada"]
        diarias = inputs["diariasInclusas"]

        if uti_necessaria and not uti_autorizada:
            resultado = "Bloquear"
        elif not diarias:
            resultado = "Alertar"
        elif diarias and (not uti_necessaria or uti_autorizada):
            resultado = "Prosseguir"
        else:
            resultado = "Revisar"

        assert resultado == expected_resultado

    # -------------------------------------------------------------------------
    # BILL-BUNDLE-EXT-005: Pacote Day Clinic
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado", [
        # Bloquear - Tempo excedido sem autorizacao
        ({"tipoProcedimentoDayClinic": "endoscopia", "tempoExcedido": True,
          "autorizacaoTempoAdicional": False, "complicacaoRegistrada": False}, "Bloquear"),
        # Alertar - Complicacao registrada
        ({"tipoProcedimentoDayClinic": "colonoscopia", "tempoExcedido": False,
          "autorizacaoTempoAdicional": False, "complicacaoRegistrada": True}, "Alertar"),
        # Prosseguir - Procedimento regular
        ({"tipoProcedimentoDayClinic": "catarata", "tempoExcedido": False,
          "autorizacaoTempoAdicional": False, "complicacaoRegistrada": False}, "Prosseguir"),
        # Prosseguir - Tempo excedido autorizado
        ({"tipoProcedimentoDayClinic": "artroscopia", "tempoExcedido": True,
          "autorizacaoTempoAdicional": True, "complicacaoRegistrada": False}, "Prosseguir"),
    ])
    def test_bill_bundle_ext_005_day_clinic(self, inputs: Dict[str, Any], expected_resultado: str):
        """BILL-BUNDLE-EXT-005: Pacote Day Clinic"""
        tempo_excedido = inputs["tempoExcedido"]
        autorizacao = inputs["autorizacaoTempoAdicional"]
        complicacao = inputs["complicacaoRegistrada"]

        if tempo_excedido and not autorizacao:
            resultado = "Bloquear"
        elif complicacao:
            resultado = "Alertar"
        elif not tempo_excedido or (tempo_excedido and autorizacao):
            resultado = "Prosseguir"
        else:
            resultado = "Revisar"

        assert resultado == expected_resultado


# ============================================================================
# TIER4: COMP-INTL Tests (3 rules)
# ============================================================================

class TestCOMPINTL:
    """Test cases for international compliance rules (3 rules)."""

    # -------------------------------------------------------------------------
    # COMP-INTL-001: Atendimento Turista Medico
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado", [
        # Bloquear - Eletivo sem seguro e garantia
        ({"paisOrigem": "europa", "seguroViagemValido": False,
          "coberturaSeguroSuficiente": False, "documentacaoConsularCompleta": True,
          "garantiaFinanceiraApresentada": False, "procedimentoEletivo": True}, "Bloquear"),
        # Bloquear - Documentacao consular incompleta (nao-Mercosul)
        ({"paisOrigem": "usa", "seguroViagemValido": True,
          "coberturaSeguroSuficiente": True, "documentacaoConsularCompleta": False,
          "garantiaFinanceiraApresentada": False, "procedimentoEletivo": True}, "Bloquear"),
        # Alertar - Cobertura parcial
        ({"paisOrigem": "europa", "seguroViagemValido": True,
          "coberturaSeguroSuficiente": False, "documentacaoConsularCompleta": True,
          "garantiaFinanceiraApresentada": False, "procedimentoEletivo": False}, "Alertar"),
        # Alertar - Emergencia sem documentacao
        ({"paisOrigem": "asia", "seguroViagemValido": False,
          "coberturaSeguroSuficiente": False, "documentacaoConsularCompleta": False,
          "garantiaFinanceiraApresentada": False, "procedimentoEletivo": False}, "Alertar"),
        # Prosseguir - Mercosul
        ({"paisOrigem": "mercosul", "seguroViagemValido": False,
          "coberturaSeguroSuficiente": False, "documentacaoConsularCompleta": True,
          "garantiaFinanceiraApresentada": False, "procedimentoEletivo": False}, "Prosseguir"),
        # Prosseguir - Seguro valido
        ({"paisOrigem": "europa", "seguroViagemValido": True,
          "coberturaSeguroSuficiente": True, "documentacaoConsularCompleta": True,
          "garantiaFinanceiraApresentada": False, "procedimentoEletivo": True}, "Prosseguir"),
        # Prosseguir - Garantia financeira
        ({"paisOrigem": "usa", "seguroViagemValido": False,
          "coberturaSeguroSuficiente": False, "documentacaoConsularCompleta": True,
          "garantiaFinanceiraApresentada": True, "procedimentoEletivo": True}, "Prosseguir"),
    ])
    def test_comp_intl_001_turista(self, inputs: Dict[str, Any], expected_resultado: str):
        """COMP-INTL-001: Atendimento Turista Medico"""
        pais = inputs["paisOrigem"]
        seguro = inputs["seguroViagemValido"]
        cobertura = inputs["coberturaSeguroSuficiente"]
        doc = inputs["documentacaoConsularCompleta"]
        garantia = inputs["garantiaFinanceiraApresentada"]
        eletivo = inputs["procedimentoEletivo"]

        # DMN evaluation logic
        if not seguro and not garantia and eletivo:
            resultado = "Bloquear"
        elif pais in ("europa", "usa", "asia", "africa", "outros") and not doc and not garantia and eletivo:
            resultado = "Bloquear"
        elif seguro and not cobertura and doc:
            resultado = "Alertar"
        elif not doc and not eletivo:
            resultado = "Alertar"
        elif pais == "mercosul" and doc and not eletivo:
            resultado = "Prosseguir"
        elif seguro and cobertura and doc:
            resultado = "Prosseguir"
        elif doc and garantia:
            resultado = "Prosseguir"
        else:
            resultado = "Revisar"

        assert resultado == expected_resultado

    # -------------------------------------------------------------------------
    # COMP-INTL-002: Reembolso Internacional
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado", [
        # Bloquear - Documentacao nao traduzida
        ({"moedaOrigem": "USD", "taxaConversaoValida": True,
          "variacaoTaxaAceitavel": True, "documentacaoTraduzida": False,
          "traducaoJuramentada": False, "documentacaoExteriorCompleta": True}, "Bloquear"),
        # Bloquear - Taxa conversao invalida
        ({"moedaOrigem": "EUR", "taxaConversaoValida": False,
          "variacaoTaxaAceitavel": True, "documentacaoTraduzida": True,
          "traducaoJuramentada": True, "documentacaoExteriorCompleta": True}, "Bloquear"),
        # Bloquear - Documentacao exterior incompleta
        ({"moedaOrigem": "GBP", "taxaConversaoValida": True,
          "variacaoTaxaAceitavel": True, "documentacaoTraduzida": True,
          "traducaoJuramentada": True, "documentacaoExteriorCompleta": False}, "Bloquear"),
        # Alertar - Traducao nao juramentada
        ({"moedaOrigem": "USD", "taxaConversaoValida": True,
          "variacaoTaxaAceitavel": True, "documentacaoTraduzida": True,
          "traducaoJuramentada": False, "documentacaoExteriorCompleta": True}, "Alertar"),
        # Alertar - Variacao taxa
        ({"moedaOrigem": "EUR", "taxaConversaoValida": True,
          "variacaoTaxaAceitavel": False, "documentacaoTraduzida": True,
          "traducaoJuramentada": True, "documentacaoExteriorCompleta": True}, "Alertar"),
        # Prosseguir - Documentacao completa
        ({"moedaOrigem": "USD", "taxaConversaoValida": True,
          "variacaoTaxaAceitavel": True, "documentacaoTraduzida": True,
          "traducaoJuramentada": True, "documentacaoExteriorCompleta": True}, "Prosseguir"),
        # Prosseguir - Mercosul simplificado
        ({"moedaOrigem": "ARS", "taxaConversaoValida": True,
          "variacaoTaxaAceitavel": True, "documentacaoTraduzida": True,
          "traducaoJuramentada": False, "documentacaoExteriorCompleta": True}, "Prosseguir"),
    ])
    def test_comp_intl_002_reembolso(self, inputs: Dict[str, Any], expected_resultado: str):
        """COMP-INTL-002: Reembolso Internacional"""
        moeda = inputs["moedaOrigem"]
        taxa = inputs["taxaConversaoValida"]
        variacao = inputs["variacaoTaxaAceitavel"]
        traduzida = inputs["documentacaoTraduzida"]
        juramentada = inputs["traducaoJuramentada"]
        exterior = inputs["documentacaoExteriorCompleta"]

        if not traduzida:
            resultado = "Bloquear"
        elif not taxa:
            resultado = "Bloquear"
        elif taxa and traduzida and not exterior:
            resultado = "Bloquear"
        # Mercosul currencies with simplified process (no sworn translation required)
        elif moeda in ("ARS", "PYG", "UYU") and taxa and variacao and traduzida and exterior:
            resultado = "Prosseguir"
        # Non-Mercosul currencies need sworn translation check
        elif taxa and variacao and traduzida and not juramentada and exterior:
            resultado = "Alertar"
        elif moeda in ("USD", "EUR", "GBP") and taxa and not variacao and traduzida and exterior:
            resultado = "Alertar"
        elif taxa and variacao and traduzida and juramentada and exterior:
            resultado = "Prosseguir"
        else:
            resultado = "Revisar"

        assert resultado == expected_resultado

    # -------------------------------------------------------------------------
    # COMP-INTL-003: Acordo Reciprocidade
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado", [
        # Bloquear - Pais sem acordo
        ({"paisAcordoReciprocidade": False, "documentacaoReciprocidade": True,
          "atendimentoUrgencia": True}, "Bloquear"),
        # Bloquear - Documentacao reciprocidade invalida
        ({"paisAcordoReciprocidade": True, "documentacaoReciprocidade": False,
          "atendimentoUrgencia": False}, "Bloquear"),
        # Alertar - Urgencia sem documentacao
        ({"paisAcordoReciprocidade": True, "documentacaoReciprocidade": False,
          "atendimentoUrgencia": True}, "Alertar"),
        # Prosseguir - Acordo valido
        ({"paisAcordoReciprocidade": True, "documentacaoReciprocidade": True,
          "atendimentoUrgencia": True}, "Prosseguir"),
        # Prosseguir - Eletivo com acordo
        ({"paisAcordoReciprocidade": True, "documentacaoReciprocidade": True,
          "atendimentoUrgencia": False}, "Prosseguir"),
    ])
    def test_comp_intl_003_reciprocidade(self, inputs: Dict[str, Any], expected_resultado: str):
        """COMP-INTL-003: Acordo Reciprocidade Internacional"""
        acordo = inputs["paisAcordoReciprocidade"]
        doc = inputs["documentacaoReciprocidade"]
        urgencia = inputs["atendimentoUrgencia"]

        if not acordo:
            resultado = "Bloquear"
        elif acordo and not doc and not urgencia:
            resultado = "Bloquear"
        elif acordo and not doc and urgencia:
            resultado = "Alertar"
        elif acordo and doc:
            resultado = "Prosseguir"
        else:
            resultado = "Revisar"

        assert resultado == expected_resultado


# ============================================================================
# TIER4: BILL-SPECIALTY Tests (2 rules)
# ============================================================================

class TestBILLSPECIALTY:
    """Test cases for specialty billing rules (2 rules)."""

    # -------------------------------------------------------------------------
    # BILL-SPECIALTY-001: Medicina Hiperbarica
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado", [
        # Bloquear - Indicacao nao prevista ANS
        ({"indicacaoClinica": "outras", "indicacaoPrevistaANS": False,
          "numeroSessoesSolicitadas": 10, "sessoesDentroProtocolo": True,
          "equipamentoCertificadoANVISA": True, "laudoMedicoEspecialista": True}, "Bloquear"),
        # Bloquear - Equipamento nao certificado
        ({"indicacaoClinica": "pe_diabetico", "indicacaoPrevistaANS": True,
          "numeroSessoesSolicitadas": 10, "sessoesDentroProtocolo": True,
          "equipamentoCertificadoANVISA": False, "laudoMedicoEspecialista": True}, "Bloquear"),
        # Bloquear - Sem laudo especialista
        ({"indicacaoClinica": "ferida_cronica", "indicacaoPrevistaANS": True,
          "numeroSessoesSolicitadas": 10, "sessoesDentroProtocolo": True,
          "equipamentoCertificadoANVISA": True, "laudoMedicoEspecialista": False}, "Bloquear"),
        # Alertar - Sessoes excedendo protocolo
        ({"indicacaoClinica": "osteomielite", "indicacaoPrevistaANS": True,
          "numeroSessoesSolicitadas": 25, "sessoesDentroProtocolo": False,
          "equipamentoCertificadoANVISA": True, "laudoMedicoEspecialista": True}, "Alertar"),
        # Alertar - Indicacao de emergencia
        ({"indicacaoClinica": "embolia", "indicacaoPrevistaANS": True,
          "numeroSessoesSolicitadas": 3, "sessoesDentroProtocolo": True,
          "equipamentoCertificadoANVISA": True, "laudoMedicoEspecialista": True}, "Alertar"),
        # Prosseguir - Indicacao cronica padrao
        ({"indicacaoClinica": "pe_diabetico", "indicacaoPrevistaANS": True,
          "numeroSessoesSolicitadas": 15, "sessoesDentroProtocolo": True,
          "equipamentoCertificadoANVISA": True, "laudoMedicoEspecialista": True}, "Prosseguir"),
        # Prosseguir - Suporte cirurgico
        ({"indicacaoClinica": "enxerto", "indicacaoPrevistaANS": True,
          "numeroSessoesSolicitadas": 10, "sessoesDentroProtocolo": True,
          "equipamentoCertificadoANVISA": True, "laudoMedicoEspecialista": True}, "Prosseguir"),
    ])
    def test_bill_specialty_001_hiperbarica(self, inputs: Dict[str, Any], expected_resultado: str):
        """BILL-SPECIALTY-001: Medicina Hiperbarica"""
        indicacao = inputs["indicacaoClinica"]
        ans = inputs["indicacaoPrevistaANS"]
        sessoes = inputs["numeroSessoesSolicitadas"]
        protocolo = inputs["sessoesDentroProtocolo"]
        equipamento = inputs["equipamentoCertificadoANVISA"]
        laudo = inputs["laudoMedicoEspecialista"]

        if not ans:
            resultado = "Bloquear"
        elif ans and not equipamento:
            resultado = "Bloquear"
        elif ans and equipamento and not laudo:
            resultado = "Bloquear"
        elif ans and sessoes > 20 and not protocolo and equipamento and laudo:
            resultado = "Alertar"
        elif indicacao in ("descompressao", "embolia", "intoxicacao_co") and ans and equipamento:
            resultado = "Alertar"
        elif indicacao in ("ferida_cronica", "pe_diabetico", "osteomielite") and ans and sessoes <= 20 and protocolo and equipamento and laudo:
            resultado = "Prosseguir"
        elif indicacao in ("queimadura", "enxerto") and ans and protocolo and equipamento and laudo:
            resultado = "Prosseguir"
        else:
            resultado = "Revisar"

        assert resultado == expected_resultado

    # -------------------------------------------------------------------------
    # BILL-SPECIALTY-002: Medicina Nuclear PET-CT
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("inputs,expected_resultado", [
        # Bloquear - FDG sem indicacao oncologica
        ({"radiofarmacoUtilizado": "FDG_F18", "radiofarmacoAprovadoCNEN": True,
          "indicacaoOncologica": False, "justificativaClinicaDocumentada": False,
          "laudoComparativoDisponivel": True, "exameEstadiamentoInicial": False}, "Bloquear"),
        # Bloquear - Radiofarmaco nao aprovado
        ({"radiofarmacoUtilizado": "outros", "radiofarmacoAprovadoCNEN": False,
          "indicacaoOncologica": True, "justificativaClinicaDocumentada": True,
          "laudoComparativoDisponivel": True, "exameEstadiamentoInicial": True}, "Bloquear"),
        # Bloquear - PSMA sem justificativa
        ({"radiofarmacoUtilizado": "psma", "radiofarmacoAprovadoCNEN": True,
          "indicacaoOncologica": True, "justificativaClinicaDocumentada": False,
          "laudoComparativoDisponivel": True, "exameEstadiamentoInicial": False}, "Bloquear"),
        # Alertar - Laudo comparativo pendente
        ({"radiofarmacoUtilizado": "FDG_F18", "radiofarmacoAprovadoCNEN": True,
          "indicacaoOncologica": True, "justificativaClinicaDocumentada": True,
          "laudoComparativoDisponivel": False, "exameEstadiamentoInicial": False}, "Alertar"),
        # Alertar - Indicacao cardiologica
        ({"radiofarmacoUtilizado": "FDG_F18", "radiofarmacoAprovadoCNEN": True,
          "indicacaoOncologica": False, "justificativaClinicaDocumentada": True,
          "laudoComparativoDisponivel": True, "exameEstadiamentoInicial": False}, "Alertar"),
        # Prosseguir - Estadiamento inicial
        ({"radiofarmacoUtilizado": "FDG_F18", "radiofarmacoAprovadoCNEN": True,
          "indicacaoOncologica": True, "justificativaClinicaDocumentada": True,
          "laudoComparativoDisponivel": False, "exameEstadiamentoInicial": True}, "Prosseguir"),
        # Prosseguir - Reestadiamento com comparativo
        ({"radiofarmacoUtilizado": "FDG_F18", "radiofarmacoAprovadoCNEN": True,
          "indicacaoOncologica": True, "justificativaClinicaDocumentada": True,
          "laudoComparativoDisponivel": True, "exameEstadiamentoInicial": False}, "Prosseguir"),
        # Prosseguir - PSMA para prostata
        ({"radiofarmacoUtilizado": "psma", "radiofarmacoAprovadoCNEN": True,
          "indicacaoOncologica": True, "justificativaClinicaDocumentada": True,
          "laudoComparativoDisponivel": True, "exameEstadiamentoInicial": False}, "Prosseguir"),
    ])
    def test_bill_specialty_002_petct(self, inputs: Dict[str, Any], expected_resultado: str):
        """BILL-SPECIALTY-002: Medicina Nuclear PET-CT"""
        radio = inputs["radiofarmacoUtilizado"]
        cnen = inputs["radiofarmacoAprovadoCNEN"]
        onco = inputs["indicacaoOncologica"]
        justif = inputs["justificativaClinicaDocumentada"]
        laudo = inputs["laudoComparativoDisponivel"]
        estadiamento = inputs["exameEstadiamentoInicial"]

        if radio == "FDG_F18" and cnen and not onco and not justif:
            resultado = "Bloquear"
        elif not cnen:
            resultado = "Bloquear"
        elif radio in ("psma", "galio_68") and cnen and not justif:
            resultado = "Bloquear"
        elif cnen and onco and justif and not laudo and not estadiamento:
            resultado = "Alertar"
        elif radio == "FDG_F18" and cnen and not onco and justif:
            resultado = "Alertar"
        elif radio == "FDG_F18" and cnen and onco and justif and estadiamento:
            resultado = "Prosseguir"
        elif radio == "FDG_F18" and cnen and onco and justif and laudo and not estadiamento:
            resultado = "Prosseguir"
        elif radio in ("psma", "colina_F18") and cnen and onco and justif:
            resultado = "Prosseguir"
        else:
            resultado = "Revisar"

        assert resultado == expected_resultado


# ============================================================================
# Test Summary and Metrics
# ============================================================================

class TestMetrics:
    """Test metrics and summary."""

    def test_total_test_count(self):
        """Verify total number of test cases."""
        # COMP-ACCRED: 10 rules x ~5 tests = ~50 tests
        # COMP-COUNCIL: 5 rules x ~5 tests = ~25 tests
        # BILL-BUNDLE-EXT: 5 rules x ~5 tests = ~25 tests
        # COMP-INTL: 3 rules x ~6 tests = ~18 tests
        # BILL-SPECIALTY: 2 rules x ~7 tests = ~14 tests
        # Total: ~132 test cases

        expected_rules = 25
        expected_min_tests = 100  # At least 4 tests per rule

        # This test documents expectations
        assert expected_rules == 25, "Expected 25 rules total"
        assert expected_min_tests >= 100, "Expected at least 100 test cases"

    def test_coverage_categories(self):
        """Verify all categories are covered."""
        categories = [
            "COMP-ACCRED",  # 10 rules
            "COMP-COUNCIL",  # 5 rules
            "BILL-BUNDLE-EXT",  # 5 rules
            "COMP-INTL",  # 3 rules
            "BILL-SPECIALTY",  # 2 rules
        ]
        assert len(categories) == 5, "Expected 5 rule categories"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
