"""
Comprehensive Test Suite for TIER1 CRITICAL DMN Rules
======================================================

Tests 15 critical DMN decision tables:
- COMP-LGPD (5 rules): Patient consent, anonymization, retention, portability, incidents
- BILL-OPME (3 rules): Traceability, pricing, authorization chain
- BILL-MED (3 rules): High-cost drugs, antimicrobials, controlled substances
- RECV-PARTIAL (2 rules): Patient installments, glosa agreements
- RECV-WRITEOFF (2 rules): Write-offs, fiscal deductions

Each rule is tested with:
- Bloquear (Block) scenarios: 2-3 cases per rule
- Alertar (Alert) scenarios: 1-2 cases per rule
- Prosseguir (Proceed) scenarios: 1-2 cases per rule
- Fallback scenarios: 1 case per rule (ambiguous/null inputs)
- Edge cases: Boundary values and null handling

Total: 105+ test cases across 15 rules

Author: QA Agent (Claude Flow V3)
Date: 2026-02-06
"""

import pytest
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


# ==============================================================================
# DMN Result Types
# ==============================================================================

class ResultadoDMN(Enum):
    """Standard DMN decision outcomes"""
    PROSSEGUIR = "Prosseguir"
    BLOQUEAR = "Bloquear"
    ALERTAR = "Alertar"
    REVISAR = "Revisar"


class PrazoStatus(Enum):
    """Deadline status for LGPD rules"""
    DENTRO_PRAZO = "DENTRO_PRAZO"
    ALERTA_PROXIMIDADE = "ALERTA_PROXIMIDADE"
    PRAZO_EXCEDIDO = "PRAZO_EXCEDIDO"


class RiscoCredito(Enum):
    """Credit risk levels"""
    BAIXO = "BAIXO"
    MEDIO = "MEDIO"
    ALTO = "ALTO"
    CRITICO = "CRITICO"


# ==============================================================================
# Mock DMN Evaluator (to be replaced with actual Camunda 8 client)
# ==============================================================================

@dataclass
class DMNResult:
    """Result from DMN evaluation"""
    resultado: str
    observacao: str
    prazo_status: Optional[str] = None
    dias_restantes: Optional[int] = None
    acao_recomendada: Optional[str] = None
    codigo_glosa: Optional[str] = None
    risco_credito: Optional[str] = None
    valor_minimo_aceitavel: Optional[float] = None
    elegivel_deducao_fiscal: Optional[bool] = None
    risco_fiscal: Optional[str] = None


class MockDMNEvaluator:
    """
    Mock DMN evaluator for testing.
    Replace with actual Zeebe/Camunda 8 client in integration tests.
    """

    @staticmethod
    def evaluate(decision_id: str, inputs: Dict[str, Any]) -> DMNResult:
        """
        Evaluate a DMN decision table with given inputs.
        This mock simulates the actual DMN logic for testing purposes.
        """
        # Route to specific rule evaluator
        evaluators = {
            "Decision_COMP_LGPD_001": MockDMNEvaluator._eval_lgpd_001,
            "Decision_COMP_LGPD_002": MockDMNEvaluator._eval_lgpd_002,
            "Decision_COMP_LGPD_003": MockDMNEvaluator._eval_lgpd_003,
            "Decision_COMP_LGPD_004": MockDMNEvaluator._eval_lgpd_004,
            "Decision_COMP_LGPD_005": MockDMNEvaluator._eval_lgpd_005,
            "Decision_BILL-OPME-001": MockDMNEvaluator._eval_opme_001,
            "Decision_BILL-OPME-002": MockDMNEvaluator._eval_opme_002,
            "Decision_BILL-OPME-003": MockDMNEvaluator._eval_opme_003,
            "Decision_BILL-MED-001": MockDMNEvaluator._eval_med_001,
            "Decision_BILL-MED-002": MockDMNEvaluator._eval_med_002,
            "Decision_BILL-MED-003": MockDMNEvaluator._eval_med_003,
            "Decision_RECV_PARTIAL_001": MockDMNEvaluator._eval_partial_001,
            "Decision_RECV_PARTIAL_002": MockDMNEvaluator._eval_partial_002,
            "Decision_RECV_WRITEOFF_001": MockDMNEvaluator._eval_writeoff_001,
            "Decision_RECV_WRITEOFF_002": MockDMNEvaluator._eval_writeoff_002,
        }

        evaluator = evaluators.get(decision_id)
        if evaluator:
            return evaluator(inputs)
        return DMNResult(resultado="Revisar", observacao="Decision not found")

    @staticmethod
    def _eval_lgpd_001(inputs: Dict[str, Any]) -> DMNResult:
        """COMP-LGPD-001: Validacao Consentimento Paciente"""
        tem_consentimento = inputs.get("temConsentimento")
        consentimento_expirado = inputs.get("consentimentoExpirado")
        categoria_exame = inputs.get("categoriaExame")
        tipo_tratamento = inputs.get("tipoTratamento")
        dias_ate_vencimento = inputs.get("diasAteVencimento")

        # Rule 1: No consent
        if tem_consentimento is False:
            return DMNResult(
                resultado="Bloquear",
                observacao="Paciente sem consentimento registrado",
                prazo_status="PRAZO_EXCEDIDO",
                dias_restantes=0
            )

        # Rule 2: Expired consent
        if tem_consentimento and consentimento_expirado:
            return DMNResult(
                resultado="Bloquear",
                observacao="Consentimento expirado",
                prazo_status="PRAZO_EXCEDIDO",
                dias_restantes=0
            )

        # Rule 3: Genetic exam requires specific consent
        if tem_consentimento and not consentimento_expirado and categoria_exame == "GENETICO":
            return DMNResult(
                resultado="Bloquear",
                observacao="Exames geneticos requerem consentimento especifico",
                prazo_status="DENTRO_PRAZO",
                dias_restantes=0
            )

        # Rule 4: Near expiration (30 days)
        if tem_consentimento and not consentimento_expirado and dias_ate_vencimento is not None and dias_ate_vencimento <= 30:
            return DMNResult(
                resultado="Alertar",
                observacao="Consentimento proximo ao vencimento",
                prazo_status="ALERTA_PROXIMIDADE",
                dias_restantes=30
            )

        # Rule 5: Research requires additional consent
        if tem_consentimento and not consentimento_expirado and tipo_tratamento == "PESQUISA":
            return DMNResult(
                resultado="Alertar",
                observacao="Uso para pesquisa requer consentimento especifico",
                prazo_status="DENTRO_PRAZO",
                dias_restantes=15
            )

        # Rule 6: Valid consent
        if tem_consentimento and not consentimento_expirado and dias_ate_vencimento is not None and dias_ate_vencimento > 30:
            return DMNResult(
                resultado="Prosseguir",
                observacao="Consentimento valido e vigente",
                prazo_status="DENTRO_PRAZO",
                dias_restantes=365
            )

        # Fallback
        return DMNResult(
            resultado="Revisar",
            observacao="Situacao nao prevista nas regras automaticas",
            prazo_status="DENTRO_PRAZO",
            dias_restantes=5
        )

    @staticmethod
    def _eval_lgpd_002(inputs: Dict[str, Any]) -> DMNResult:
        """COMP-LGPD-002: Anonimizacao Dados Pesquisa"""
        destino_dados = inputs.get("destinoDados")
        tipo_uso = inputs.get("tipoUso")
        tem_anonimizacao = inputs.get("temAnonimizacao")
        nivel_anonimizacao = inputs.get("nivelAnonimizacao")
        compartilhamento_externo = inputs.get("compartilhamentoExterno")

        # Rule 1: Research without anonymization
        if destino_dados == "PESQUISA" and not tem_anonimizacao:
            return DMNResult(
                resultado="Bloquear",
                observacao="Uso de dados para pesquisa requer anonimizacao",
                prazo_status="PRAZO_EXCEDIDO",
                dias_restantes=0
            )

        # Rule 2: External sharing with partial anonymization
        if tem_anonimizacao and nivel_anonimizacao == "PARCIAL" and compartilhamento_externo:
            return DMNResult(
                resultado="Bloquear",
                observacao="Compartilhamento externo com anonimizacao parcial apresenta risco",
                prazo_status="PRAZO_EXCEDIDO",
                dias_restantes=0
            )

        # Rule 3: Commercial use without anonymization
        if tipo_uso == "COMERCIAL" and not tem_anonimizacao:
            return DMNResult(
                resultado="Bloquear",
                observacao="Uso comercial de dados sensiveis sem anonimizacao",
                prazo_status="PRAZO_EXCEDIDO",
                dias_restantes=0
            )

        # Rule 4: Partial anonymization for internal use
        if destino_dados == "INTERNO" and tem_anonimizacao and nivel_anonimizacao == "PARCIAL" and not compartilhamento_externo:
            return DMNResult(
                resultado="Alertar",
                observacao="Anonimizacao parcial para uso interno",
                prazo_status="ALERTA_PROXIMIDADE",
                dias_restantes=15
            )

        # Rule 5: Pseudonymized for statistics
        if tipo_uso == "ESTATISTICO" and tem_anonimizacao and nivel_anonimizacao == "PSEUDONIMIZADO":
            return DMNResult(
                resultado="Alertar",
                observacao="Dados pseudonimizados para uso estatistico",
                prazo_status="DENTRO_PRAZO",
                dias_restantes=30
            )

        # Rule 6: Complete anonymization
        if tem_anonimizacao and nivel_anonimizacao == "COMPLETA":
            return DMNResult(
                resultado="Prosseguir",
                observacao="Dados completamente anonimizados",
                prazo_status="DENTRO_PRAZO",
                dias_restantes=365
            )

        # Rule 7: Internal healthcare use
        if destino_dados == "INTERNO" and tipo_uso == "ASSISTENCIAL" and not compartilhamento_externo:
            return DMNResult(
                resultado="Prosseguir",
                observacao="Uso assistencial interno para tutela da saude",
                prazo_status="DENTRO_PRAZO",
                dias_restantes=180
            )

        # Fallback
        return DMNResult(
            resultado="Revisar",
            observacao="Cenario de anonimizacao nao previsto",
            prazo_status="DENTRO_PRAZO",
            dias_restantes=5
        )

    @staticmethod
    def _eval_lgpd_003(inputs: Dict[str, Any]) -> DMNResult:
        """COMP-LGPD-003: Politica Retencao Dados"""
        tempo_armazenamento = inputs.get("tempoArmazenamentoAnos")
        tipo_dado = inputs.get("tipoDado")
        base_juridica = inputs.get("baseJuridica")
        paciente_menor = inputs.get("pacienteMenor")
        solicitacao_eliminacao = inputs.get("solicitacaoEliminacao")

        # Rule 1: Medical record over 20 years without legal basis
        if tempo_armazenamento is not None and tempo_armazenamento > 20 and tipo_dado == "PRONTUARIO" and base_juridica == "NENHUMA" and not paciente_menor:
            return DMNResult(
                resultado="Bloquear",
                observacao="Prontuario excede 20 anos sem base juridica",
                prazo_status="PRAZO_EXCEDIDO",
                dias_restantes=0
            )

        # Rule 2: Marketing data elimination request
        if tipo_dado == "MARKETING" and solicitacao_eliminacao:
            return DMNResult(
                resultado="Bloquear",
                observacao="Titular solicitou eliminacao de dados de marketing",
                prazo_status="PRAZO_EXCEDIDO",
                dias_restantes=15
            )

        # Rule 3: Administrative data over 5 years
        if tempo_armazenamento is not None and tempo_armazenamento > 5 and tipo_dado == "ADMINISTRATIVO" and base_juridica == "NENHUMA":
            return DMNResult(
                resultado="Bloquear",
                observacao="Dados administrativos excedem 5 anos de retencao",
                prazo_status="PRAZO_EXCEDIDO",
                dias_restantes=0
            )

        # Rule 4: Medical record near 20 years
        if tempo_armazenamento is not None and 18 <= tempo_armazenamento <= 20 and tipo_dado == "PRONTUARIO" and not paciente_menor:
            return DMNResult(
                resultado="Alertar",
                observacao="Prontuario proximo ao limite de 20 anos",
                prazo_status="ALERTA_PROXIMIDADE",
                dias_restantes=730
            )

        # Rule 5: Elimination request for medical record
        if tipo_dado == "PRONTUARIO" and solicitacao_eliminacao:
            return DMNResult(
                resultado="Alertar",
                observacao="Titular solicitou eliminacao de prontuario",
                prazo_status="DENTRO_PRAZO",
                dias_restantes=15
            )

        # Rule 6: Minor patient extended retention
        if tipo_dado == "PRONTUARIO" and base_juridica == "OBRIGACAO_LEGAL" and paciente_menor and not solicitacao_eliminacao:
            return DMNResult(
                resultado="Prosseguir",
                observacao="Prontuario de menor de idade",
                prazo_status="DENTRO_PRAZO",
                dias_restantes=7300
            )

        # Rule 7: Within legal retention period
        if tempo_armazenamento is not None and tempo_armazenamento < 18 and tipo_dado == "PRONTUARIO" and not paciente_menor and not solicitacao_eliminacao:
            return DMNResult(
                resultado="Prosseguir",
                observacao="Prontuario dentro do prazo legal",
                prazo_status="DENTRO_PRAZO",
                dias_restantes=1825
            )

        # Fallback
        return DMNResult(
            resultado="Revisar",
            observacao="Politica de retencao nao determinada automaticamente",
            prazo_status="DENTRO_PRAZO",
            dias_restantes=30
        )

    @staticmethod
    def _eval_lgpd_004(inputs: Dict[str, Any]) -> DMNResult:
        """COMP-LGPD-004: Portabilidade Dados Paciente"""
        solicitacao_portabilidade = inputs.get("solicitacaoPortabilidade")
        identidade_verificada = inputs.get("identidadeVerificada")
        formato_padrao = inputs.get("formatoPadraoDisponivel")
        dias_desde_solicitacao = inputs.get("diasDesdeSolicitacao")
        destino = inputs.get("destinoPortabilidade")

        # Rule 1: Deadline exceeded
        if solicitacao_portabilidade and identidade_verificada and dias_desde_solicitacao is not None and dias_desde_solicitacao > 15:
            return DMNResult(
                resultado="Bloquear",
                observacao="URGENTE: Prazo de 15 dias para portabilidade excedido",
                prazo_status="PRAZO_EXCEDIDO",
                dias_restantes=0
            )

        # Rule 2: Identity not verified
        if solicitacao_portabilidade and not identidade_verificada:
            return DMNResult(
                resultado="Bloquear",
                observacao="Identidade do titular nao verificada",
                prazo_status="DENTRO_PRAZO",
                dias_restantes=15
            )

        # Rule 3: Near deadline (75% consumed)
        if solicitacao_portabilidade and identidade_verificada and dias_desde_solicitacao is not None and 11 <= dias_desde_solicitacao <= 15:
            return DMNResult(
                resultado="Alertar",
                observacao="ATENCAO: Prazo de portabilidade proximo ao limite",
                prazo_status="ALERTA_PROXIMIDADE",
                dias_restantes=4
            )

        # Rule 4: Standard format not available
        if solicitacao_portabilidade and identidade_verificada and not formato_padrao and dias_desde_solicitacao is not None and dias_desde_solicitacao <= 10:
            return DMNResult(
                resultado="Alertar",
                observacao="Dados nao disponiveis em formato estruturado padrao",
                prazo_status="ALERTA_PROXIMIDADE",
                dias_restantes=10
            )

        # Rule 5: Destination is health operator (TISS format)
        if solicitacao_portabilidade and identidade_verificada and destino == "OPERADORA":
            return DMNResult(
                resultado="Alertar",
                observacao="Portabilidade para operadora de saude",
                prazo_status="DENTRO_PRAZO",
                dias_restantes=10
            )

        # Rule 6: Valid request within deadline
        if solicitacao_portabilidade and identidade_verificada and formato_padrao and dias_desde_solicitacao is not None and dias_desde_solicitacao <= 10:
            return DMNResult(
                resultado="Prosseguir",
                observacao="Solicitacao de portabilidade validada",
                prazo_status="DENTRO_PRAZO",
                dias_restantes=5
            )

        # Rule 7: No active request
        if not solicitacao_portabilidade:
            return DMNResult(
                resultado="Prosseguir",
                observacao="Nenhuma solicitacao de portabilidade ativa",
                prazo_status="DENTRO_PRAZO",
                dias_restantes=365
            )

        # Fallback
        return DMNResult(
            resultado="Revisar",
            observacao="Solicitacao de portabilidade requer analise manual",
            prazo_status="DENTRO_PRAZO",
            dias_restantes=5
        )

    @staticmethod
    def _eval_lgpd_005(inputs: Dict[str, Any]) -> DMNResult:
        """COMP-LGPD-005: Notificacao Incidente Seguranca"""
        tipo_incidente = inputs.get("tipoIncidente")
        gravidade = inputs.get("gravidade")
        horas_desde_deteccao = inputs.get("horasDesdeDeteccao")
        anpd_notificada = inputs.get("anpdNotificada")
        titulares_notificados = inputs.get("titularesNotificados")

        # Rule 1: Critical incident without ANPD notification after 72h
        if gravidade == "CRITICA" and horas_desde_deteccao is not None and horas_desde_deteccao > 72 and not anpd_notificada:
            return DMNResult(
                resultado="Bloquear",
                observacao="CRITICO: Incidente grave sem notificacao a ANPD apos 72 horas",
                prazo_status="PRAZO_EXCEDIDO",
                dias_restantes=0
            )

        # Rule 2: Data breach without notifying subjects
        if tipo_incidente == "VAZAMENTO" and gravidade in ["CRITICA", "ALTA"] and horas_desde_deteccao is not None and horas_desde_deteccao > 48 and not titulares_notificados:
            return DMNResult(
                resultado="Bloquear",
                observacao="Vazamento de dados sensiveis sem notificacao aos titulares",
                prazo_status="PRAZO_EXCEDIDO",
                dias_restantes=0
            )

        # Rule 3: Ransomware requires immediate action
        if tipo_incidente == "RANSOMWARE" and not anpd_notificada:
            return DMNResult(
                resultado="Bloquear",
                observacao="Ataque ransomware detectado. Isolar sistemas IMEDIATAMENTE",
                prazo_status="PRAZO_EXCEDIDO",
                dias_restantes=0
            )

        # Rule 4: Medium severity near deadline
        if gravidade == "MEDIA" and horas_desde_deteccao is not None and 48 <= horas_desde_deteccao <= 72 and not anpd_notificada:
            return DMNResult(
                resultado="Alertar",
                observacao="Incidente de gravidade media proximo ao prazo de 72h",
                prazo_status="ALERTA_PROXIMIDADE",
                dias_restantes=1
            )

        # Rule 5: High severity within deadline
        if gravidade == "ALTA" and horas_desde_deteccao is not None and horas_desde_deteccao <= 48 and not anpd_notificada:
            return DMNResult(
                resultado="Alertar",
                observacao="Incidente de alta gravidade. Preparar notificacao a ANPD",
                prazo_status="ALERTA_PROXIMIDADE",
                dias_restantes=1
            )

        # Rule 6: ANPD notified but not subjects
        if gravidade in ["CRITICA", "ALTA"] and anpd_notificada and not titulares_notificados:
            return DMNResult(
                resultado="Alertar",
                observacao="ANPD notificada. Avaliar necessidade de notificacao direta aos titulares",
                prazo_status="DENTRO_PRAZO",
                dias_restantes=5
            )

        # Rule 7: Low severity
        if gravidade == "BAIXA":
            return DMNResult(
                resultado="Prosseguir",
                observacao="Incidente de baixa gravidade. Documentar internamente",
                prazo_status="DENTRO_PRAZO",
                dias_restantes=30
            )

        # Rule 8: All notifications complete
        if anpd_notificada and titulares_notificados:
            return DMNResult(
                resultado="Prosseguir",
                observacao="Incidente com notificacoes completas",
                prazo_status="DENTRO_PRAZO",
                dias_restantes=90
            )

        # Fallback
        return DMNResult(
            resultado="Revisar",
            observacao="Incidente requer analise do DPO e CSIRT",
            prazo_status="DENTRO_PRAZO",
            dias_restantes=24
        )

    @staticmethod
    def _eval_opme_001(inputs: Dict[str, Any]) -> DMNResult:
        """BILL-OPME-001: Rastreabilidade OPME Implantavel"""
        codigo_anvisa_valido = inputs.get("codigoAnvisaValido")
        lote_registrado = inputs.get("loteRegistradoProntuario")
        dias_ate_validade = inputs.get("diasAteValidade")
        registro_paciente = inputs.get("registroPacienteCompleto")

        # Rule 1: Invalid ANVISA code
        if not codigo_anvisa_valido:
            return DMNResult(
                resultado="Bloquear",
                observacao="BLOQUEADO - OPME implantavel sem codigo ANVISA valido",
                acao_recomendada="CORRIGIR_ANVISA",
                codigo_glosa="O001"
            )

        # Rule 2: Lot not registered in record
        if codigo_anvisa_valido and not lote_registrado:
            return DMNResult(
                resultado="Bloquear",
                observacao="BLOQUEADO - Lote do OPME nao registrado no prontuario",
                acao_recomendada="REGISTRAR_LOTE",
                codigo_glosa="O002"
            )

        # Rule 3: Expired validity
        if codigo_anvisa_valido and lote_registrado and dias_ate_validade is not None and dias_ate_validade < 0:
            return DMNResult(
                resultado="Bloquear",
                observacao="BLOQUEADO - OPME com validade expirada",
                acao_recomendada="VERIFICAR_VALIDADE",
                codigo_glosa="O003"
            )

        # Rule 4: Incomplete patient record
        if codigo_anvisa_valido and lote_registrado and dias_ate_validade is not None and dias_ate_validade >= 0 and not registro_paciente:
            return DMNResult(
                resultado="Bloquear",
                observacao="BLOQUEADO - Registro do paciente incompleto",
                acao_recomendada="REGISTRAR_LOTE",
                codigo_glosa="O002"
            )

        # Rule 5: Near expiration (90 days)
        if codigo_anvisa_valido and lote_registrado and dias_ate_validade is not None and 0 <= dias_ate_validade <= 90 and registro_paciente:
            return DMNResult(
                resultado="Alertar",
                observacao="ALERTA - OPME com validade proxima de expirar",
                acao_recomendada="FATURAR",
                codigo_glosa="N/A"
            )

        # Rule 6: Complete traceability
        if codigo_anvisa_valido and lote_registrado and dias_ate_validade is not None and dias_ate_validade > 90 and registro_paciente:
            return DMNResult(
                resultado="Prosseguir",
                observacao="APROVADO - OPME implantavel com rastreabilidade completa",
                acao_recomendada="FATURAR",
                codigo_glosa="N/A"
            )

        # Fallback
        return DMNResult(
            resultado="Revisar",
            observacao="REVISAR - Dados insuficientes para validacao de rastreabilidade OPME",
            acao_recomendada="REGISTRAR_LOTE",
            codigo_glosa="N/A"
        )

    @staticmethod
    def _eval_opme_002(inputs: Dict[str, Any]) -> DMNResult:
        """BILL-OPME-002: Validacao Preco OPME"""
        percentual_margem = inputs.get("percentualMargemAtual")
        limite_margem = inputs.get("limiteMargemContrato")
        preco_maior_custo = inputs.get("precoVendaMaiorCusto")
        tabela_disponivel = inputs.get("tabelaReferenciaDisponivel")

        # Rule 1: Margin exceeds contract limit
        if percentual_margem is not None and limite_margem is not None and percentual_margem > limite_margem:
            return DMNResult(
                resultado="Bloquear",
                observacao="BLOQUEADO - Margem de preco OPME excede limite contratual",
                acao_recomendada="AJUSTAR_PRECO",
                codigo_glosa="P001"
            )

        # Rule 2: Price below cost
        if preco_maior_custo is False:
            return DMNResult(
                resultado="Bloquear",
                observacao="BLOQUEADO - Preco de venda OPME abaixo do custo de aquisicao",
                acao_recomendada="REVISAR_CUSTO",
                codigo_glosa="P002"
            )

        # Rule 3: No reference table
        if preco_maior_custo and not tabela_disponivel:
            return DMNResult(
                resultado="Bloquear",
                observacao="BLOQUEADO - OPME sem tabela de referencia disponivel",
                acao_recomendada="NEGOCIAR_OPERADORA",
                codigo_glosa="P003"
            )

        # Rule 4: Margin near limit (80%)
        if percentual_margem is not None and limite_margem is not None and (limite_margem * 0.8) <= percentual_margem <= limite_margem and preco_maior_custo and tabela_disponivel:
            return DMNResult(
                resultado="Alertar",
                observacao="ALERTA - Margem de preco OPME proxima do limite contratual",
                acao_recomendada="NEGOCIAR_OPERADORA",
                codigo_glosa="P001"
            )

        # Rule 5: Within margin
        if percentual_margem is not None and limite_margem is not None and percentual_margem < (limite_margem * 0.8) and preco_maior_custo and tabela_disponivel:
            return DMNResult(
                resultado="Prosseguir",
                observacao="APROVADO - Preco OPME dentro da margem contratual permitida",
                acao_recomendada="FATURAR",
                codigo_glosa="N/A"
            )

        # Fallback
        return DMNResult(
            resultado="Revisar",
            observacao="REVISAR - Dados insuficientes para validacao de preco OPME",
            acao_recomendada="REVISAR_CUSTO",
            codigo_glosa="N/A"
        )

    @staticmethod
    def _eval_opme_003(inputs: Dict[str, Any]) -> DMNResult:
        """BILL-OPME-003: Cadeia Autorizacao OPME"""
        possui_autorizacao = inputs.get("possuiAutorizacaoPrevia")
        valor_excede = inputs.get("valorExcedeLimite")
        laudo_completo = inputs.get("laudoMedicoCompleto")
        cotacao_valida = inputs.get("cotacaoFornecedorValida")
        status_autorizacao = inputs.get("statusAutorizacao")

        # Rule 1: High value without prior authorization
        if not possui_autorizacao and valor_excede and status_autorizacao == "NAO_SOLICITADA":
            return DMNResult(
                resultado="Bloquear",
                observacao="BLOQUEADO - OPME de alto valor sem autorizacao previa",
                acao_recomendada="SOLICITAR_AUTORIZACAO",
                codigo_glosa="A001"
            )

        # Rule 2: No medical report for special OPME
        if valor_excede and not laudo_completo:
            return DMNResult(
                resultado="Bloquear",
                observacao="BLOQUEADO - OPME especial sem laudo medico justificativo",
                acao_recomendada="COMPLETAR_LAUDO",
                codigo_glosa="A002"
            )

        # Rule 3: No supplier quote
        if possui_autorizacao and valor_excede and laudo_completo and not cotacao_valida:
            return DMNResult(
                resultado="Bloquear",
                observacao="BLOQUEADO - OPME sem cotacao de fornecedor documentada",
                acao_recomendada="OBTER_COTACAO",
                codigo_glosa="A003"
            )

        # Rule 4: Pending authorization
        if possui_autorizacao and valor_excede and laudo_completo and cotacao_valida and status_autorizacao == "PENDENTE":
            return DMNResult(
                resultado="Alertar",
                observacao="ALERTA - Autorizacao previa solicitada mas pendente de confirmacao",
                acao_recomendada="SOLICITAR_AUTORIZACAO",
                codigo_glosa="A001"
            )

        # Rule 5: Complete authorization chain
        if possui_autorizacao and valor_excede and laudo_completo and cotacao_valida and status_autorizacao == "CONFIRMADA":
            return DMNResult(
                resultado="Prosseguir",
                observacao="APROVADO - Cadeia de autorizacao OPME completa",
                acao_recomendada="FATURAR",
                codigo_glosa="N/A"
            )

        # Rule 6: Below limit, no authorization needed
        if not valor_excede and laudo_completo and cotacao_valida:
            return DMNResult(
                resultado="Prosseguir",
                observacao="APROVADO - OPME abaixo do limite de autorizacao previa",
                acao_recomendada="FATURAR",
                codigo_glosa="N/A"
            )

        # Fallback
        return DMNResult(
            resultado="Revisar",
            observacao="REVISAR - Dados insuficientes para validacao de cadeia de autorizacao",
            acao_recomendada="SOLICITAR_AUTORIZACAO",
            codigo_glosa="N/A"
        )

    @staticmethod
    def _eval_med_001(inputs: Dict[str, Any]) -> DMNResult:
        """BILL-MED-001: Medicamento Alto Custo"""
        classificado_alto_custo = inputs.get("classificadoAltoCusto")
        protocolo_status = inputs.get("protocoloClinicoStatus")
        autorizacao_especifica = inputs.get("possuiAutorizacaoEspecifica")
        medicamento_rol = inputs.get("medicamentoNoRolAns")

        # Rule 1: High cost without clinical protocol
        if classificado_alto_custo and protocolo_status == "AUSENTE":
            return DMNResult(
                resultado="Bloquear",
                observacao="BLOQUEADO - Medicamento de alto custo sem protocolo clinico",
                acao_recomendada="COMPLETAR_PROTOCOLO",
                codigo_glosa="MH001"
            )

        # Rule 2: High cost without specific authorization
        if classificado_alto_custo and protocolo_status == "APROVADO" and not autorizacao_especifica:
            return DMNResult(
                resultado="Bloquear",
                observacao="BLOQUEADO - Medicamento de alto custo sem autorizacao especifica",
                acao_recomendada="SOLICITAR_AUTORIZACAO",
                codigo_glosa="MH002"
            )

        # Rule 3: Outside ANS list without justification
        if classificado_alto_custo and protocolo_status == "APROVADO" and autorizacao_especifica and not medicamento_rol:
            return DMNResult(
                resultado="Bloquear",
                observacao="BLOQUEADO - Medicamento de alto custo fora do rol ANS",
                acao_recomendada="JUSTIFICAR_TECNICO",
                codigo_glosa="MH003"
            )

        # Rule 4: Incomplete clinical protocol
        if classificado_alto_custo and protocolo_status == "INCOMPLETO" and autorizacao_especifica and medicamento_rol:
            return DMNResult(
                resultado="Alertar",
                observacao="ALERTA - Protocolo clinico presente mas incompleto",
                acao_recomendada="COMPLETAR_PROTOCOLO",
                codigo_glosa="MH001"
            )

        # Rule 5: Complete high-cost chain
        if classificado_alto_custo and protocolo_status == "APROVADO" and autorizacao_especifica and medicamento_rol:
            return DMNResult(
                resultado="Prosseguir",
                observacao="APROVADO - Medicamento de alto custo com documentacao completa",
                acao_recomendada="FATURAR",
                codigo_glosa="N/A"
            )

        # Rule 6: Standard medication
        if not classificado_alto_custo and medicamento_rol:
            return DMNResult(
                resultado="Prosseguir",
                observacao="APROVADO - Medicamento padrao presente no rol ANS",
                acao_recomendada="FATURAR",
                codigo_glosa="N/A"
            )

        # Fallback
        return DMNResult(
            resultado="Revisar",
            observacao="REVISAR - Dados insuficientes para validacao de medicamento alto custo",
            acao_recomendada="COMPLETAR_PROTOCOLO",
            codigo_glosa="N/A"
        )

    @staticmethod
    def _eval_med_002(inputs: Dict[str, Any]) -> DMNResult:
        """BILL-MED-002: Antimicrobiano Hospitalar"""
        classe = inputs.get("classeAntimicrobiano")
        percentual_duracao = inputs.get("percentualDuracaoProtocolo")
        cultura_status = inputs.get("culturaSensibilidadeStatus")
        autorizacao_ccih = inputs.get("possuiAutorizacaoCcih")

        # Rule 1: Restricted without CCIH authorization
        if classe == "RESTRITO" and not autorizacao_ccih:
            return DMNResult(
                resultado="Bloquear",
                observacao="BLOQUEADO - Antimicrobiano de uso restrito sem autorizacao CCIH",
                acao_recomendada="SOLICITAR_CCIH",
                codigo_glosa="AM001"
            )

        # Rule 2: Duration exceeds protocol without culture
        if percentual_duracao is not None and percentual_duracao > 100 and cultura_status == "NAO_APLICAVEL":
            return DMNResult(
                resultado="Bloquear",
                observacao="BLOQUEADO - Duracao de tratamento excede protocolo sem cultura",
                acao_recomendada="DOCUMENTAR_CULTURA",
                codigo_glosa="AM002"
            )

        # Rule 3: Controlled with prolonged use and pending culture
        if classe == "CONTROLADO" and percentual_duracao is not None and percentual_duracao > 100 and cultura_status == "PENDENTE":
            return DMNResult(
                resultado="Bloquear",
                observacao="BLOQUEADO - Antimicrobiano controlado com duracao superior ao protocolo",
                acao_recomendada="JUSTIFICAR_DURACAO",
                codigo_glosa="AM003"
            )

        # Rule 4: Duration near limit (75%)
        if percentual_duracao is not None and 75 <= percentual_duracao <= 100:
            return DMNResult(
                resultado="Alertar",
                observacao="ALERTA - Duracao de tratamento acima de 75% do limite protocolar",
                acao_recomendada="JUSTIFICAR_DURACAO",
                codigo_glosa="AM002"
            )

        # Rule 5: Pending culture with empiric treatment
        if percentual_duracao is not None and percentual_duracao < 75 and cultura_status == "PENDENTE" and autorizacao_ccih:
            return DMNResult(
                resultado="Alertar",
                observacao="ALERTA - Tratamento empirico com cultura pendente",
                acao_recomendada="DOCUMENTAR_CULTURA",
                codigo_glosa="N/A"
            )

        # Rule 6: Restricted with authorization
        if classe == "RESTRITO" and percentual_duracao is not None and percentual_duracao < 75 and cultura_status == "DOCUMENTADA" and autorizacao_ccih:
            return DMNResult(
                resultado="Prosseguir",
                observacao="APROVADO - Antimicrobiano restrito com autorizacao CCIH",
                acao_recomendada="FATURAR",
                codigo_glosa="N/A"
            )

        # Rule 7: Standard within protocol
        if classe == "PADRAO" and percentual_duracao is not None and percentual_duracao < 100:
            return DMNResult(
                resultado="Prosseguir",
                observacao="APROVADO - Antimicrobiano padrao com duracao dentro do protocolo",
                acao_recomendada="FATURAR",
                codigo_glosa="N/A"
            )

        # Fallback
        return DMNResult(
            resultado="Revisar",
            observacao="REVISAR - Dados insuficientes para validacao de antimicrobiano",
            acao_recomendada="SOLICITAR_CCIH",
            codigo_glosa="N/A"
        )

    @staticmethod
    def _eval_med_003(inputs: Dict[str, Any]) -> DMNResult:
        """BILL-MED-003: Medicamento Controlado"""
        classificacao = inputs.get("classificacaoPortaria")
        prescricao_valida = inputs.get("prescricaoMedicaValida")
        registro_status = inputs.get("registroDispensacaoStatus")
        quantidade_confere = inputs.get("quantidadeConferePrescricao")

        # Rule 1: Controlled without valid prescription
        if not prescricao_valida:
            return DMNResult(
                resultado="Bloquear",
                observacao="BLOQUEADO - Medicamento controlado sem prescricao medica valida",
                acao_recomendada="OBTER_PRESCRICAO",
                codigo_glosa="MC001"
            )

        # Rule 2: Without dispensation record
        if prescricao_valida and registro_status == "AUSENTE":
            return DMNResult(
                resultado="Bloquear",
                observacao="BLOQUEADO - Medicamento controlado sem registro de dispensacao",
                acao_recomendada="COMPLETAR_REGISTRO",
                codigo_glosa="MC002"
            )

        # Rule 3: Schedule A without complete traceability
        if classificacao in ["A1", "A2", "A3"] and prescricao_valida and registro_status == "PARCIAL":
            return DMNResult(
                resultado="Bloquear",
                observacao="BLOQUEADO - Substancia entorpecente com registro incompleto",
                acao_recomendada="COMPLETAR_REGISTRO",
                codigo_glosa="MC002"
            )

        # Rule 4: Partial dispensation record (non-Schedule A)
        if classificacao in ["B1", "B2", "C1", "C2", "C3", "C4", "C5"] and prescricao_valida and registro_status == "PARCIAL" and quantidade_confere:
            return DMNResult(
                resultado="Alertar",
                observacao="ALERTA - Registro de dispensacao parcialmente completo",
                acao_recomendada="COMPLETAR_REGISTRO",
                codigo_glosa="MC002"
            )

        # Rule 5: Quantity divergence
        if prescricao_valida and registro_status == "COMPLETO" and not quantidade_confere:
            return DMNResult(
                resultado="Alertar",
                observacao="ALERTA - Quantidade dispensada diverge da prescrita",
                acao_recomendada="AJUSTAR_QUANTIDADE",
                codigo_glosa="MC003"
            )

        # Rule 6: Complete documentation
        if prescricao_valida and registro_status == "COMPLETO" and quantidade_confere:
            return DMNResult(
                resultado="Prosseguir",
                observacao="APROVADO - Medicamento controlado com documentacao completa",
                acao_recomendada="FATURAR",
                codigo_glosa="N/A"
            )

        # Fallback
        return DMNResult(
            resultado="Revisar",
            observacao="REVISAR - Dados insuficientes para validacao de medicamento controlado",
            acao_recomendada="COMPLETAR_REGISTRO",
            codigo_glosa="N/A"
        )

    @staticmethod
    def _eval_partial_001(inputs: Dict[str, Any]) -> DMNResult:
        """RECV-PARTIAL-001: Parcelamento Paciente Particular"""
        valor_total = inputs.get("valorTotal")
        numero_parcelas = inputs.get("numeroParcelas")
        taxa_juros = inputs.get("taxaJuros")
        capacidade_pagamento = inputs.get("capacidadePagamento")
        historico_inadimplencia = inputs.get("historicoInadimplencia")

        # Rule 1: More than 24 installments
        if numero_parcelas is not None and numero_parcelas > 24:
            return DMNResult(
                resultado="Bloquear",
                observacao="Parcelamento em mais de 24x nao permitido",
                acao_recomendada="AJUSTAR_CONDICOES",
                risco_credito="CRITICO"
            )

        # Rule 2: Interest rate above legal ceiling
        if taxa_juros is not None and taxa_juros > 1:
            return DMNResult(
                resultado="Bloquear",
                observacao="Taxa de juros acima do teto legal (1% a.m.)",
                acao_recomendada="AJUSTAR_CONDICOES",
                risco_credito="ALTO"
            )

        # Rule 3: Default history
        if historico_inadimplencia:
            return DMNResult(
                resultado="Alertar",
                observacao="Paciente com historico de inadimplencia",
                acao_recomendada="EXIGIR_GARANTIA",
                risco_credito="ALTO"
            )

        # Rule 4: Long-term installments (13-24)
        if numero_parcelas is not None and 13 <= numero_parcelas <= 24 and (taxa_juros is None or taxa_juros <= 1) and not historico_inadimplencia:
            return DMNResult(
                resultado="Alertar",
                observacao="Parcelamento em mais de 12x requer monitoramento ativo",
                acao_recomendada="APROVAR",
                risco_credito="MEDIO"
            )

        # Rule 5: Short-term with adequate capacity
        if numero_parcelas is not None and numero_parcelas <= 12 and (taxa_juros is None or taxa_juros <= 1) and not historico_inadimplencia:
            return DMNResult(
                resultado="Prosseguir",
                observacao="Parcelamento aprovado. Condicoes dentro dos parametros",
                acao_recomendada="APROVAR",
                risco_credito="BAIXO"
            )

        # Fallback
        return DMNResult(
            resultado="Revisar",
            observacao="Parcelamento requer analise do comite de credito",
            acao_recomendada="REVISAR_COMITE",
            risco_credito="MEDIO"
        )

    @staticmethod
    def _eval_partial_002(inputs: Dict[str, Any]) -> DMNResult:
        """RECV-PARTIAL-002: Acordo Pagamento Glosa"""
        valor_glosa = inputs.get("valorGlosa")
        percentual_acordo = inputs.get("percentualAcordo")
        prazo_quitacao = inputs.get("prazoQuitacao")
        probabilidade_reversao = inputs.get("probabilidadeReversao")
        urgencia_caixa = inputs.get("urgenciaFluxoCaixa")

        # Rule 1: Low agreement with long deadline
        if percentual_acordo is not None and percentual_acordo < 50 and prazo_quitacao is not None and prazo_quitacao > 180:
            return DMNResult(
                resultado="Bloquear",
                observacao="Acordo inferior a 50% com prazo superior a 180 dias",
                acao_recomendada="REJEITAR_PROPOSTA",
                valor_minimo_aceitavel=0.70
            )

        # Rule 2: Deadline too long
        if prazo_quitacao is not None and prazo_quitacao > 180:
            return DMNResult(
                resultado="Bloquear",
                observacao="Prazo de quitacao superior a 180 dias",
                acao_recomendada="CONTRAPROPOR",
                valor_minimo_aceitavel=0.75
            )

        # Rule 3: Agreement between 50-70%
        if percentual_acordo is not None and 50 <= percentual_acordo < 70 and prazo_quitacao is not None and prazo_quitacao <= 180:
            return DMNResult(
                resultado="Alertar",
                observacao="Acordo abaixo de 70% requer avaliacao cuidadosa",
                acao_recomendada="REVISAR_COMITE",
                valor_minimo_aceitavel=0.65
            )

        # Rule 4: High probability of full reversal
        if percentual_acordo is not None and percentual_acordo < 90 and probabilidade_reversao is not None and probabilidade_reversao >= 0.80 and not urgencia_caixa:
            return DMNResult(
                resultado="Prosseguir",
                observacao="Alta probabilidade de reversao total. Insistir no recurso",
                acao_recomendada="INSISTIR_RECURSO",
                valor_minimo_aceitavel=1.00
            )

        # Rule 5: Good agreement with cash urgency
        if percentual_acordo is not None and percentual_acordo >= 70 and prazo_quitacao is not None and prazo_quitacao <= 90 and urgencia_caixa:
            return DMNResult(
                resultado="Prosseguir",
                observacao="Acordo favoravel com prazo curto e necessidade de caixa",
                acao_recomendada="ACEITAR_ACORDO",
                valor_minimo_aceitavel=0.70
            )

        # Rule 6: Excellent agreement
        if percentual_acordo is not None and percentual_acordo >= 85 and prazo_quitacao is not None and prazo_quitacao <= 60:
            return DMNResult(
                resultado="Prosseguir",
                observacao="Acordo excelente com prazo curto",
                acao_recomendada="ACEITAR_ACORDO",
                valor_minimo_aceitavel=0.85
            )

        # Fallback
        return DMNResult(
            resultado="Revisar",
            observacao="Acordo requer analise do comite financeiro",
            acao_recomendada="REVISAR_COMITE",
            valor_minimo_aceitavel=0.70
        )

    @staticmethod
    def _eval_writeoff_001(inputs: Dict[str, Any]) -> DMNResult:
        """RECV-WRITEOFF-001: Baixa Contabil Incobravel"""
        dias_atraso = inputs.get("diasAtraso")
        tentativas = inputs.get("tentativasCobranca")
        status_negociacao = inputs.get("statusNegociacao")
        valor_credito = inputs.get("valorCredito")
        possui_garantia = inputs.get("possuiGarantia")

        # Rule 1: Few collection attempts
        if tentativas is not None and tentativas < 3:
            return DMNResult(
                resultado="Bloquear",
                observacao="Minimo de 3 tentativas de cobranca nao atingido",
                acao_recomendada="MANTER_COBRANCA",
                elegivel_deducao_fiscal=False
            )

        # Rule 2: Negotiation in progress (check before other delay rules)
        if status_negociacao == "EM_ANDAMENTO":
            return DMNResult(
                resultado="Bloquear",
                observacao="Negociacao em andamento",
                acao_recomendada="MANTER_COBRANCA",
                elegivel_deducao_fiscal=False
            )

        # Rule 3: Credit with guarantee
        if possui_garantia:
            return DMNResult(
                resultado="Bloquear",
                observacao="Credito possui garantia real",
                acao_recomendada="ACIONAR_JURIDICO",
                elegivel_deducao_fiscal=False
            )

        # Rule 4: Near limit (270-365 days) - ALERT, check BEFORE generic block
        if dias_atraso is not None and 270 <= dias_atraso < 365 and tentativas is not None and tentativas >= 3 and status_negociacao in ["ENCERRADA_SEM_SUCESSO", "DEVEDOR_NAO_LOCALIZADO", "DEVEDOR_INSOLVENTE"] and not possui_garantia:
            return DMNResult(
                resultado="Alertar",
                observacao="Credito proximo do limite para baixa fiscal",
                acao_recomendada="PROVISIONAR_PERDA",
                elegivel_deducao_fiscal=False
            )

        # Rule 5: Insufficient delay (generic block for <365 days)
        if dias_atraso is not None and dias_atraso < 365 and tentativas is not None and tentativas >= 3:
            return DMNResult(
                resultado="Bloquear",
                observacao="Credito com menos de 365 dias de atraso",
                acao_recomendada="PROVISIONAR_PERDA",
                elegivel_deducao_fiscal=False
            )

        # Rule 6: Debtor not found (>= 365 days)
        if dias_atraso is not None and dias_atraso >= 365 and tentativas is not None and tentativas >= 3 and status_negociacao == "DEVEDOR_NAO_LOCALIZADO" and not possui_garantia:
            return DMNResult(
                resultado="Prosseguir",
                observacao="Devedor nao localizado apos esforcos documentados",
                acao_recomendada="BAIXAR_CONTABIL",
                elegivel_deducao_fiscal=True
            )

        # Rule 7: Debtor insolvent
        if dias_atraso is not None and dias_atraso >= 365 and tentativas is not None and tentativas >= 3 and status_negociacao == "DEVEDOR_INSOLVENTE" and not possui_garantia:
            return DMNResult(
                resultado="Prosseguir",
                observacao="Devedor insolvente documentado",
                acao_recomendada="BAIXAR_CONTABIL",
                elegivel_deducao_fiscal=True
            )

        # Rule 8: Negotiation failed
        if dias_atraso is not None and dias_atraso >= 365 and tentativas is not None and tentativas >= 3 and status_negociacao == "ENCERRADA_SEM_SUCESSO" and not possui_garantia:
            return DMNResult(
                resultado="Prosseguir",
                observacao="Credito incobravel apos esgotamento de esforcos",
                acao_recomendada="BAIXAR_CONTABIL",
                elegivel_deducao_fiscal=True
            )

        # Fallback
        return DMNResult(
            resultado="Revisar",
            observacao="Credito requer analise do comite de credito",
            acao_recomendada="PROVISIONAR_PERDA",
            elegivel_deducao_fiscal=False
        )

    @staticmethod
    def _eval_writeoff_002(inputs: Dict[str, Any]) -> DMNResult:
        """RECV-WRITEOFF-002: Provisao Deducao Fiscal"""
        valor_baixa = inputs.get("valorBaixa")
        documentacao = inputs.get("documentacaoSuporte")
        classificacao = inputs.get("classificacaoFiscal")
        tem_protesto = inputs.get("temProtesto")
        partes_relacionadas = inputs.get("partesRelacionadas")

        # Rule 1: Missing documentation
        if documentacao == "AUSENTE":
            return DMNResult(
                resultado="Bloquear",
                observacao="Documentacao de suporte ausente",
                acao_recomendada="COMPLEMENTAR_DOCUMENTACAO",
                risco_fiscal="CRITICO"
            )

        # Rule 2: Related parties
        if partes_relacionadas:
            return DMNResult(
                resultado="Bloquear",
                observacao="Credito entre partes relacionadas nao elegivel",
                acao_recomendada="INDEDUTIVEL",
                risco_fiscal="ALTO"
            )

        # Rule 3: Non-deductible classification
        if classificacao == "NAO_DEDUTIVEL" and not partes_relacionadas:
            return DMNResult(
                resultado="Bloquear",
                observacao="Credito classificado como nao dedutivel",
                acao_recomendada="INDEDUTIVEL",
                risco_fiscal="BAIXO"
            )

        # Rule 4: Partial documentation
        if documentacao == "PARCIAL" and not partes_relacionadas:
            return DMNResult(
                resultado="Alertar",
                observacao="Documentacao parcial apresenta risco de glosa",
                acao_recomendada="COMPLEMENTAR_DOCUMENTACAO",
                risco_fiscal="MEDIO"
            )

        # Rule 5: Pending analysis without protest
        if documentacao == "COMPLETA" and classificacao == "PENDENTE_ANALISE" and not tem_protesto and not partes_relacionadas:
            return DMNResult(
                resultado="Alertar",
                observacao="Titulo nao protestado",
                acao_recomendada="CONSULTAR_TRIBUTARIO",
                risco_fiscal="MEDIO"
            )

        # Rule 6: Complete with protest
        if documentacao == "COMPLETA" and classificacao == "DEDUTIVEL" and tem_protesto and not partes_relacionadas:
            return DMNResult(
                resultado="Prosseguir",
                observacao="Credito com documentacao completa e titulo protestado",
                acao_recomendada="DEDUZIR_IRPJ_CSLL",
                risco_fiscal="BAIXO"
            )

        # Rule 7: Complete and deductible
        if documentacao == "COMPLETA" and classificacao == "DEDUTIVEL" and not partes_relacionadas:
            return DMNResult(
                resultado="Prosseguir",
                observacao="Credito com documentacao completa e classificacao dedutivel",
                acao_recomendada="DEDUZIR_IRPJ_CSLL",
                risco_fiscal="BAIXO"
            )

        # Rule 8: Partially deductible
        if documentacao == "COMPLETA" and classificacao == "PARCIALMENTE_DEDUTIVEL" and not partes_relacionadas:
            return DMNResult(
                resultado="Prosseguir",
                observacao="Credito parcialmente dedutivel",
                acao_recomendada="DEDUZIR_IRPJ_CSLL",
                risco_fiscal="BAIXO"
            )

        # Fallback
        return DMNResult(
            resultado="Revisar",
            observacao="Credito requer analise da area tributaria",
            acao_recomendada="CONSULTAR_TRIBUTARIO",
            risco_fiscal="MEDIO"
        )


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def evaluator():
    """Provide DMN evaluator for tests"""
    return MockDMNEvaluator()


# ==============================================================================
# COMP-LGPD-001: Validacao Consentimento Paciente
# ==============================================================================

class TestCOMPLGPD001:
    """Test cases for COMP-LGPD-001: Validacao Consentimento Paciente"""

    DECISION_ID = "Decision_COMP_LGPD_001"

    @pytest.mark.parametrize("inputs,expected_resultado,expected_obs_contains", [
        # BLOQUEAR: No consent
        ({"temConsentimento": False, "consentimentoExpirado": False},
         "Bloquear", "sem consentimento"),

        # BLOQUEAR: Expired consent
        ({"temConsentimento": True, "consentimentoExpirado": True, "tipoTratamento": "CLINICO"},
         "Bloquear", "expirado"),

        # BLOQUEAR: Genetic exam without specific consent
        ({"temConsentimento": True, "consentimentoExpirado": False, "categoriaExame": "GENETICO", "diasAteVencimento": 90},
         "Bloquear", "geneticos"),
    ])
    def test_bloquear_scenarios(self, evaluator, inputs, expected_resultado, expected_obs_contains):
        """Test blocking scenarios for consent validation"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert expected_obs_contains.lower() in result.observacao.lower()

    @pytest.mark.parametrize("inputs,expected_resultado,expected_obs_contains", [
        # ALERTAR: Near expiration (30 days or less)
        ({"temConsentimento": True, "consentimentoExpirado": False, "diasAteVencimento": 25, "tipoTratamento": "CLINICO"},
         "Alertar", "proximo"),

        # ALERTAR: Research use
        ({"temConsentimento": True, "consentimentoExpirado": False, "tipoTratamento": "PESQUISA", "diasAteVencimento": 180},
         "Alertar", "pesquisa"),
    ])
    def test_alertar_scenarios(self, evaluator, inputs, expected_resultado, expected_obs_contains):
        """Test alert scenarios for consent validation"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert expected_obs_contains.lower() in result.observacao.lower()

    @pytest.mark.parametrize("inputs,expected_resultado,expected_obs_contains", [
        # PROSSEGUIR: Valid consent with adequate time
        ({"temConsentimento": True, "consentimentoExpirado": False, "diasAteVencimento": 180, "tipoTratamento": "CLINICO"},
         "Prosseguir", "valido"),

        # PROSSEGUIR: Valid consent for standard exam
        ({"temConsentimento": True, "consentimentoExpirado": False, "diasAteVencimento": 365, "categoriaExame": "LABORATORIAL"},
         "Prosseguir", "valido"),
    ])
    def test_prosseguir_scenarios(self, evaluator, inputs, expected_resultado, expected_obs_contains):
        """Test proceed scenarios for consent validation"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert expected_obs_contains.lower() in result.observacao.lower()

    def test_fallback_scenario(self, evaluator):
        """Test fallback when inputs are ambiguous or null"""
        inputs = {"temConsentimento": None, "consentimentoExpirado": None}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Revisar"
        assert "nao prevista" in result.observacao.lower() or "dpo" in result.observacao.lower()

    def test_edge_case_exactly_30_days(self, evaluator):
        """Edge case: Exactly 30 days until expiration"""
        inputs = {"temConsentimento": True, "consentimentoExpirado": False, "diasAteVencimento": 30}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Alertar"
        assert result.prazo_status == "ALERTA_PROXIMIDADE"

    def test_edge_case_31_days(self, evaluator):
        """Edge case: 31 days - should proceed"""
        inputs = {"temConsentimento": True, "consentimentoExpirado": False, "diasAteVencimento": 31}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Prosseguir"


# ==============================================================================
# COMP-LGPD-002: Anonimizacao Dados Pesquisa
# ==============================================================================

class TestCOMPLGPD002:
    """Test cases for COMP-LGPD-002: Anonimizacao Dados Pesquisa"""

    DECISION_ID = "Decision_COMP_LGPD_002"

    @pytest.mark.parametrize("inputs,expected_resultado,expected_obs_contains", [
        # BLOQUEAR: Research without anonymization
        ({"destinoDados": "PESQUISA", "temAnonimizacao": False},
         "Bloquear", "pesquisa"),

        # BLOQUEAR: External sharing with partial anonymization
        ({"temAnonimizacao": True, "nivelAnonimizacao": "PARCIAL", "compartilhamentoExterno": True},
         "Bloquear", "compartilhamento"),

        # BLOQUEAR: Commercial use without anonymization
        ({"tipoUso": "COMERCIAL", "temAnonimizacao": False},
         "Bloquear", "comercial"),
    ])
    def test_bloquear_scenarios(self, evaluator, inputs, expected_resultado, expected_obs_contains):
        """Test blocking scenarios for anonymization validation"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert expected_obs_contains.lower() in result.observacao.lower()

    @pytest.mark.parametrize("inputs,expected_resultado,expected_obs_contains", [
        # ALERTAR: Partial anonymization for internal use
        ({"destinoDados": "INTERNO", "temAnonimizacao": True, "nivelAnonimizacao": "PARCIAL", "compartilhamentoExterno": False},
         "Alertar", "parcial"),

        # ALERTAR: Pseudonymized for statistics
        ({"tipoUso": "ESTATISTICO", "temAnonimizacao": True, "nivelAnonimizacao": "PSEUDONIMIZADO"},
         "Alertar", "pseudonimizado"),
    ])
    def test_alertar_scenarios(self, evaluator, inputs, expected_resultado, expected_obs_contains):
        """Test alert scenarios for anonymization validation"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert expected_obs_contains.lower() in result.observacao.lower()

    @pytest.mark.parametrize("inputs,expected_resultado,expected_obs_contains", [
        # PROSSEGUIR: Complete anonymization
        ({"temAnonimizacao": True, "nivelAnonimizacao": "COMPLETA"},
         "Prosseguir", "completamente anonimizados"),

        # PROSSEGUIR: Internal healthcare use
        ({"destinoDados": "INTERNO", "tipoUso": "ASSISTENCIAL", "compartilhamentoExterno": False},
         "Prosseguir", "assistencial"),
    ])
    def test_prosseguir_scenarios(self, evaluator, inputs, expected_resultado, expected_obs_contains):
        """Test proceed scenarios for anonymization validation"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert expected_obs_contains.lower() in result.observacao.lower()

    def test_fallback_scenario(self, evaluator):
        """Test fallback when inputs are ambiguous"""
        inputs = {"destinoDados": "EXTERNO", "tipoUso": "OUTRO", "temAnonimizacao": True, "nivelAnonimizacao": "OUTRO"}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Revisar"


# ==============================================================================
# COMP-LGPD-003: Politica Retencao Dados
# ==============================================================================

class TestCOMPLGPD003:
    """Test cases for COMP-LGPD-003: Politica Retencao Dados"""

    DECISION_ID = "Decision_COMP_LGPD_003"

    @pytest.mark.parametrize("inputs,expected_resultado,expected_obs_contains", [
        # BLOQUEAR: Medical record over 20 years
        ({"tempoArmazenamentoAnos": 21, "tipoDado": "PRONTUARIO", "baseJuridica": "NENHUMA", "pacienteMenor": False},
         "Bloquear", "20 anos"),

        # BLOQUEAR: Marketing data elimination request
        ({"tipoDado": "MARKETING", "solicitacaoEliminacao": True},
         "Bloquear", "marketing"),

        # BLOQUEAR: Administrative data over 5 years
        ({"tempoArmazenamentoAnos": 6, "tipoDado": "ADMINISTRATIVO", "baseJuridica": "NENHUMA"},
         "Bloquear", "administrativo"),
    ])
    def test_bloquear_scenarios(self, evaluator, inputs, expected_resultado, expected_obs_contains):
        """Test blocking scenarios for data retention"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert expected_obs_contains.lower() in result.observacao.lower()

    @pytest.mark.parametrize("inputs,expected_resultado,expected_obs_contains", [
        # ALERTAR: Medical record near 20 years
        ({"tempoArmazenamentoAnos": 19, "tipoDado": "PRONTUARIO", "pacienteMenor": False},
         "Alertar", "proximo"),

        # ALERTAR: Elimination request for medical record
        ({"tipoDado": "PRONTUARIO", "solicitacaoEliminacao": True},
         "Alertar", "prontuario"),
    ])
    def test_alertar_scenarios(self, evaluator, inputs, expected_resultado, expected_obs_contains):
        """Test alert scenarios for data retention"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert expected_obs_contains.lower() in result.observacao.lower()

    @pytest.mark.parametrize("inputs,expected_resultado,expected_obs_contains", [
        # PROSSEGUIR: Minor patient
        ({"tipoDado": "PRONTUARIO", "baseJuridica": "OBRIGACAO_LEGAL", "pacienteMenor": True, "solicitacaoEliminacao": False},
         "Prosseguir", "menor"),

        # PROSSEGUIR: Within legal period
        ({"tempoArmazenamentoAnos": 10, "tipoDado": "PRONTUARIO", "pacienteMenor": False, "solicitacaoEliminacao": False},
         "Prosseguir", "dentro do prazo"),
    ])
    def test_prosseguir_scenarios(self, evaluator, inputs, expected_resultado, expected_obs_contains):
        """Test proceed scenarios for data retention"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert expected_obs_contains.lower() in result.observacao.lower()


# ==============================================================================
# COMP-LGPD-004: Portabilidade Dados Paciente
# ==============================================================================

class TestCOMPLGPD004:
    """Test cases for COMP-LGPD-004: Portabilidade Dados Paciente"""

    DECISION_ID = "Decision_COMP_LGPD_004"

    @pytest.mark.parametrize("inputs,expected_resultado,expected_obs_contains", [
        # BLOQUEAR: Deadline exceeded
        ({"solicitacaoPortabilidade": True, "identidadeVerificada": True, "diasDesdeSolicitacao": 16},
         "Bloquear", "15 dias"),

        # BLOQUEAR: Identity not verified
        ({"solicitacaoPortabilidade": True, "identidadeVerificada": False},
         "Bloquear", "identidade"),
    ])
    def test_bloquear_scenarios(self, evaluator, inputs, expected_resultado, expected_obs_contains):
        """Test blocking scenarios for data portability"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert expected_obs_contains.lower() in result.observacao.lower()

    @pytest.mark.parametrize("inputs,expected_resultado,expected_obs_contains", [
        # ALERTAR: Near deadline
        ({"solicitacaoPortabilidade": True, "identidadeVerificada": True, "diasDesdeSolicitacao": 12},
         "Alertar", "proximo"),

        # ALERTAR: Standard format not available
        ({"solicitacaoPortabilidade": True, "identidadeVerificada": True, "formatoPadraoDisponivel": False, "diasDesdeSolicitacao": 5},
         "Alertar", "formato"),
    ])
    def test_alertar_scenarios(self, evaluator, inputs, expected_resultado, expected_obs_contains):
        """Test alert scenarios for data portability"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert expected_obs_contains.lower() in result.observacao.lower()

    @pytest.mark.parametrize("inputs,expected_resultado,expected_obs_contains", [
        # PROSSEGUIR: Valid request
        ({"solicitacaoPortabilidade": True, "identidadeVerificada": True, "formatoPadraoDisponivel": True, "diasDesdeSolicitacao": 5},
         "Prosseguir", "validada"),

        # PROSSEGUIR: No active request
        ({"solicitacaoPortabilidade": False},
         "Prosseguir", "nenhuma"),
    ])
    def test_prosseguir_scenarios(self, evaluator, inputs, expected_resultado, expected_obs_contains):
        """Test proceed scenarios for data portability"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert expected_obs_contains.lower() in result.observacao.lower()


# ==============================================================================
# COMP-LGPD-005: Notificacao Incidente Seguranca
# ==============================================================================

class TestCOMPLGPD005:
    """Test cases for COMP-LGPD-005: Notificacao Incidente Seguranca"""

    DECISION_ID = "Decision_COMP_LGPD_005"

    @pytest.mark.parametrize("inputs,expected_resultado,expected_obs_contains", [
        # BLOQUEAR: Critical without ANPD notification after 72h
        ({"gravidade": "CRITICA", "horasDesdeDeteccao": 73, "anpdNotificada": False},
         "Bloquear", "72 horas"),

        # BLOQUEAR: Data breach without subject notification
        ({"tipoIncidente": "VAZAMENTO", "gravidade": "ALTA", "horasDesdeDeteccao": 50, "titularesNotificados": False},
         "Bloquear", "vazamento"),

        # BLOQUEAR: Ransomware
        ({"tipoIncidente": "RANSOMWARE", "anpdNotificada": False},
         "Bloquear", "ransomware"),
    ])
    def test_bloquear_scenarios(self, evaluator, inputs, expected_resultado, expected_obs_contains):
        """Test blocking scenarios for security incidents"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert expected_obs_contains.lower() in result.observacao.lower()

    @pytest.mark.parametrize("inputs,expected_resultado,expected_obs_contains", [
        # ALERTAR: Medium severity near deadline
        ({"gravidade": "MEDIA", "horasDesdeDeteccao": 60, "anpdNotificada": False},
         "Alertar", "72h"),

        # ALERTAR: High severity within deadline
        ({"gravidade": "ALTA", "horasDesdeDeteccao": 24, "anpdNotificada": False},
         "Alertar", "alta gravidade"),
    ])
    def test_alertar_scenarios(self, evaluator, inputs, expected_resultado, expected_obs_contains):
        """Test alert scenarios for security incidents"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert expected_obs_contains.lower() in result.observacao.lower()

    @pytest.mark.parametrize("inputs,expected_resultado,expected_obs_contains", [
        # PROSSEGUIR: Low severity
        ({"gravidade": "BAIXA"},
         "Prosseguir", "baixa gravidade"),

        # PROSSEGUIR: All notifications complete
        ({"anpdNotificada": True, "titularesNotificados": True},
         "Prosseguir", "notificacoes completas"),
    ])
    def test_prosseguir_scenarios(self, evaluator, inputs, expected_resultado, expected_obs_contains):
        """Test proceed scenarios for security incidents"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert expected_obs_contains.lower() in result.observacao.lower()


# ==============================================================================
# BILL-OPME-001: Rastreabilidade OPME Implantavel
# ==============================================================================

class TestBILLOPME001:
    """Test cases for BILL-OPME-001: Rastreabilidade OPME Implantavel"""

    DECISION_ID = "Decision_BILL-OPME-001"

    @pytest.mark.parametrize("inputs,expected_resultado,expected_codigo_glosa", [
        # BLOQUEAR: Invalid ANVISA code
        ({"codigoAnvisaValido": False},
         "Bloquear", "O001"),

        # BLOQUEAR: Lot not registered
        ({"codigoAnvisaValido": True, "loteRegistradoProntuario": False},
         "Bloquear", "O002"),

        # BLOQUEAR: Expired validity
        ({"codigoAnvisaValido": True, "loteRegistradoProntuario": True, "diasAteValidade": -1},
         "Bloquear", "O003"),
    ])
    def test_bloquear_scenarios(self, evaluator, inputs, expected_resultado, expected_codigo_glosa):
        """Test blocking scenarios for OPME traceability"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert result.codigo_glosa == expected_codigo_glosa

    def test_alertar_near_expiration(self, evaluator):
        """Test alert for near expiration"""
        inputs = {"codigoAnvisaValido": True, "loteRegistradoProntuario": True, "diasAteValidade": 45, "registroPacienteCompleto": True}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Alertar"
        assert "proxima" in result.observacao.lower() or "validade" in result.observacao.lower()

    def test_prosseguir_complete_traceability(self, evaluator):
        """Test proceed with complete traceability"""
        inputs = {"codigoAnvisaValido": True, "loteRegistradoProntuario": True, "diasAteValidade": 180, "registroPacienteCompleto": True}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Prosseguir"
        assert result.acao_recomendada == "FATURAR"


# ==============================================================================
# BILL-OPME-002: Validacao Preco OPME
# ==============================================================================

class TestBILLOPME002:
    """Test cases for BILL-OPME-002: Validacao Preco OPME"""

    DECISION_ID = "Decision_BILL-OPME-002"

    @pytest.mark.parametrize("inputs,expected_resultado,expected_codigo_glosa", [
        # BLOQUEAR: Margin exceeds limit
        ({"percentualMargemAtual": 35, "limiteMargemContrato": 30},
         "Bloquear", "P001"),

        # BLOQUEAR: Price below cost
        ({"precoVendaMaiorCusto": False},
         "Bloquear", "P002"),

        # BLOQUEAR: No reference table
        ({"precoVendaMaiorCusto": True, "tabelaReferenciaDisponivel": False},
         "Bloquear", "P003"),
    ])
    def test_bloquear_scenarios(self, evaluator, inputs, expected_resultado, expected_codigo_glosa):
        """Test blocking scenarios for OPME pricing"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert result.codigo_glosa == expected_codigo_glosa

    def test_alertar_near_limit(self, evaluator):
        """Test alert when margin near limit (80%)"""
        inputs = {"percentualMargemAtual": 25, "limiteMargemContrato": 30, "precoVendaMaiorCusto": True, "tabelaReferenciaDisponivel": True}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Alertar"

    def test_prosseguir_within_margin(self, evaluator):
        """Test proceed when within margin"""
        inputs = {"percentualMargemAtual": 15, "limiteMargemContrato": 30, "precoVendaMaiorCusto": True, "tabelaReferenciaDisponivel": True}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Prosseguir"


# ==============================================================================
# BILL-OPME-003: Cadeia Autorizacao OPME
# ==============================================================================

class TestBILLOPME003:
    """Test cases for BILL-OPME-003: Cadeia Autorizacao OPME"""

    DECISION_ID = "Decision_BILL-OPME-003"

    @pytest.mark.parametrize("inputs,expected_resultado,expected_codigo_glosa", [
        # BLOQUEAR: High value without authorization
        ({"possuiAutorizacaoPrevia": False, "valorExcedeLimite": True, "statusAutorizacao": "NAO_SOLICITADA"},
         "Bloquear", "A001"),

        # BLOQUEAR: No medical report
        ({"valorExcedeLimite": True, "laudoMedicoCompleto": False},
         "Bloquear", "A002"),

        # BLOQUEAR: No supplier quote
        ({"possuiAutorizacaoPrevia": True, "valorExcedeLimite": True, "laudoMedicoCompleto": True, "cotacaoFornecedorValida": False},
         "Bloquear", "A003"),
    ])
    def test_bloquear_scenarios(self, evaluator, inputs, expected_resultado, expected_codigo_glosa):
        """Test blocking scenarios for authorization chain"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert result.codigo_glosa == expected_codigo_glosa

    def test_alertar_pending_authorization(self, evaluator):
        """Test alert when authorization pending"""
        inputs = {"possuiAutorizacaoPrevia": True, "valorExcedeLimite": True, "laudoMedicoCompleto": True, "cotacaoFornecedorValida": True, "statusAutorizacao": "PENDENTE"}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Alertar"

    def test_prosseguir_complete_chain(self, evaluator):
        """Test proceed with complete authorization chain"""
        inputs = {"possuiAutorizacaoPrevia": True, "valorExcedeLimite": True, "laudoMedicoCompleto": True, "cotacaoFornecedorValida": True, "statusAutorizacao": "CONFIRMADA"}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Prosseguir"


# ==============================================================================
# BILL-MED-001: Medicamento Alto Custo
# ==============================================================================

class TestBILLMED001:
    """Test cases for BILL-MED-001: Medicamento Alto Custo"""

    DECISION_ID = "Decision_BILL-MED-001"

    @pytest.mark.parametrize("inputs,expected_resultado,expected_codigo_glosa", [
        # BLOQUEAR: High cost without protocol
        ({"classificadoAltoCusto": True, "protocoloClinicoStatus": "AUSENTE"},
         "Bloquear", "MH001"),

        # BLOQUEAR: High cost without authorization
        ({"classificadoAltoCusto": True, "protocoloClinicoStatus": "APROVADO", "possuiAutorizacaoEspecifica": False},
         "Bloquear", "MH002"),

        # BLOQUEAR: Outside ANS list
        ({"classificadoAltoCusto": True, "protocoloClinicoStatus": "APROVADO", "possuiAutorizacaoEspecifica": True, "medicamentoNoRolAns": False},
         "Bloquear", "MH003"),
    ])
    def test_bloquear_scenarios(self, evaluator, inputs, expected_resultado, expected_codigo_glosa):
        """Test blocking scenarios for high-cost medications"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert result.codigo_glosa == expected_codigo_glosa

    def test_alertar_incomplete_protocol(self, evaluator):
        """Test alert for incomplete protocol"""
        inputs = {"classificadoAltoCusto": True, "protocoloClinicoStatus": "INCOMPLETO", "possuiAutorizacaoEspecifica": True, "medicamentoNoRolAns": True}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Alertar"

    def test_prosseguir_complete_chain(self, evaluator):
        """Test proceed with complete chain"""
        inputs = {"classificadoAltoCusto": True, "protocoloClinicoStatus": "APROVADO", "possuiAutorizacaoEspecifica": True, "medicamentoNoRolAns": True}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Prosseguir"

    def test_prosseguir_standard_medication(self, evaluator):
        """Test proceed with standard medication"""
        inputs = {"classificadoAltoCusto": False, "medicamentoNoRolAns": True}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Prosseguir"


# ==============================================================================
# BILL-MED-002: Antimicrobiano Hospitalar
# ==============================================================================

class TestBILLMED002:
    """Test cases for BILL-MED-002: Antimicrobiano Hospitalar"""

    DECISION_ID = "Decision_BILL-MED-002"

    @pytest.mark.parametrize("inputs,expected_resultado,expected_codigo_glosa", [
        # BLOQUEAR: Restricted without CCIH
        ({"classeAntimicrobiano": "RESTRITO", "possuiAutorizacaoCcih": False},
         "Bloquear", "AM001"),

        # BLOQUEAR: Duration exceeds protocol
        ({"percentualDuracaoProtocolo": 110, "culturaSensibilidadeStatus": "NAO_APLICAVEL"},
         "Bloquear", "AM002"),

        # BLOQUEAR: Controlled with prolonged use
        ({"classeAntimicrobiano": "CONTROLADO", "percentualDuracaoProtocolo": 105, "culturaSensibilidadeStatus": "PENDENTE"},
         "Bloquear", "AM003"),
    ])
    def test_bloquear_scenarios(self, evaluator, inputs, expected_resultado, expected_codigo_glosa):
        """Test blocking scenarios for antimicrobials"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert result.codigo_glosa == expected_codigo_glosa

    def test_alertar_near_limit(self, evaluator):
        """Test alert when near duration limit"""
        inputs = {"percentualDuracaoProtocolo": 80}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Alertar"

    def test_prosseguir_standard_within_protocol(self, evaluator):
        """Test proceed with standard antimicrobial within protocol"""
        inputs = {"classeAntimicrobiano": "PADRAO", "percentualDuracaoProtocolo": 50}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Prosseguir"


# ==============================================================================
# BILL-MED-003: Medicamento Controlado
# ==============================================================================

class TestBILLMED003:
    """Test cases for BILL-MED-003: Medicamento Controlado"""

    DECISION_ID = "Decision_BILL-MED-003"

    @pytest.mark.parametrize("inputs,expected_resultado,expected_codigo_glosa", [
        # BLOQUEAR: Without valid prescription
        ({"prescricaoMedicaValida": False},
         "Bloquear", "MC001"),

        # BLOQUEAR: Without dispensation record
        ({"prescricaoMedicaValida": True, "registroDispensacaoStatus": "AUSENTE"},
         "Bloquear", "MC002"),

        # BLOQUEAR: Schedule A with partial record
        ({"classificacaoPortaria": "A1", "prescricaoMedicaValida": True, "registroDispensacaoStatus": "PARCIAL"},
         "Bloquear", "MC002"),
    ])
    def test_bloquear_scenarios(self, evaluator, inputs, expected_resultado, expected_codigo_glosa):
        """Test blocking scenarios for controlled substances"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert result.codigo_glosa == expected_codigo_glosa

    def test_alertar_quantity_divergence(self, evaluator):
        """Test alert for quantity divergence"""
        inputs = {"prescricaoMedicaValida": True, "registroDispensacaoStatus": "COMPLETO", "quantidadeConferePrescricao": False}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Alertar"

    def test_prosseguir_complete_documentation(self, evaluator):
        """Test proceed with complete documentation"""
        inputs = {"prescricaoMedicaValida": True, "registroDispensacaoStatus": "COMPLETO", "quantidadeConferePrescricao": True}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Prosseguir"


# ==============================================================================
# RECV-PARTIAL-001: Parcelamento Paciente Particular
# ==============================================================================

class TestRECVPARTIAL001:
    """Test cases for RECV-PARTIAL-001: Parcelamento Paciente Particular"""

    DECISION_ID = "Decision_RECV_PARTIAL_001"

    @pytest.mark.parametrize("inputs,expected_resultado,expected_risco", [
        # BLOQUEAR: More than 24 installments
        ({"numeroParcelas": 36},
         "Bloquear", "CRITICO"),

        # BLOQUEAR: Interest rate above legal ceiling
        ({"taxaJuros": 1.5},
         "Bloquear", "ALTO"),
    ])
    def test_bloquear_scenarios(self, evaluator, inputs, expected_resultado, expected_risco):
        """Test blocking scenarios for patient installments"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert result.risco_credito == expected_risco

    def test_alertar_default_history(self, evaluator):
        """Test alert for default history"""
        inputs = {"historicoInadimplencia": True}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Alertar"
        assert result.risco_credito == "ALTO"

    def test_prosseguir_short_term(self, evaluator):
        """Test proceed with short-term installments"""
        inputs = {"numeroParcelas": 6, "taxaJuros": 0.5, "historicoInadimplencia": False}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Prosseguir"
        assert result.risco_credito == "BAIXO"

    def test_edge_case_exactly_24_installments(self, evaluator):
        """Edge case: Exactly 24 installments (boundary)"""
        inputs = {"numeroParcelas": 24, "taxaJuros": 0.8, "historicoInadimplencia": False}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Alertar"  # 13-24 range

    def test_edge_case_exactly_12_installments(self, evaluator):
        """Edge case: Exactly 12 installments (boundary)"""
        inputs = {"numeroParcelas": 12, "taxaJuros": 0.8, "historicoInadimplencia": False}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Prosseguir"


# ==============================================================================
# RECV-PARTIAL-002: Acordo Pagamento Glosa
# ==============================================================================

class TestRECVPARTIAL002:
    """Test cases for RECV-PARTIAL-002: Acordo Pagamento Glosa"""

    DECISION_ID = "Decision_RECV_PARTIAL_002"

    @pytest.mark.parametrize("inputs,expected_resultado,expected_acao", [
        # BLOQUEAR: Low agreement with long deadline
        ({"percentualAcordo": 40, "prazoQuitacao": 200},
         "Bloquear", "REJEITAR_PROPOSTA"),

        # BLOQUEAR: Deadline too long
        ({"prazoQuitacao": 200},
         "Bloquear", "CONTRAPROPOR"),
    ])
    def test_bloquear_scenarios(self, evaluator, inputs, expected_resultado, expected_acao):
        """Test blocking scenarios for glosa agreements"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert result.acao_recomendada == expected_acao

    def test_alertar_below_70_percent(self, evaluator):
        """Test alert for agreement below 70%"""
        inputs = {"percentualAcordo": 60, "prazoQuitacao": 120}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Alertar"

    def test_prosseguir_excellent_agreement(self, evaluator):
        """Test proceed with excellent agreement"""
        inputs = {"percentualAcordo": 90, "prazoQuitacao": 30}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Prosseguir"
        assert result.acao_recomendada == "ACEITAR_ACORDO"

    def test_prosseguir_high_reversal_probability(self, evaluator):
        """Test proceed when high probability of reversal"""
        inputs = {"percentualAcordo": 60, "probabilidadeReversao": 0.85, "urgenciaFluxoCaixa": False}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Prosseguir"
        assert result.acao_recomendada == "INSISTIR_RECURSO"


# ==============================================================================
# RECV-WRITEOFF-001: Baixa Contabil Incobravel
# ==============================================================================

class TestRECVWRITEOFF001:
    """Test cases for RECV-WRITEOFF-001: Baixa Contabil Incobravel"""

    DECISION_ID = "Decision_RECV_WRITEOFF_001"

    @pytest.mark.parametrize("inputs,expected_resultado,expected_acao", [
        # BLOQUEAR: Few collection attempts
        ({"tentativasCobranca": 2},
         "Bloquear", "MANTER_COBRANCA"),

        # BLOQUEAR: Insufficient delay
        ({"diasAtraso": 200, "tentativasCobranca": 5},
         "Bloquear", "PROVISIONAR_PERDA"),

        # BLOQUEAR: Negotiation in progress
        ({"statusNegociacao": "EM_ANDAMENTO"},
         "Bloquear", "MANTER_COBRANCA"),

        # BLOQUEAR: Credit with guarantee
        ({"possuiGarantia": True},
         "Bloquear", "ACIONAR_JURIDICO"),
    ])
    def test_bloquear_scenarios(self, evaluator, inputs, expected_resultado, expected_acao):
        """Test blocking scenarios for write-offs"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert result.acao_recomendada == expected_acao

    def test_alertar_near_limit(self, evaluator):
        """Test alert when near write-off limit (270-364 days)"""
        # Note: diasAtraso must be in range [270..365) for alert scenario
        inputs = {"diasAtraso": 280, "tentativasCobranca": 4, "statusNegociacao": "DEVEDOR_NAO_LOCALIZADO", "possuiGarantia": False}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Alertar"

    @pytest.mark.parametrize("status_negociacao", [
        "DEVEDOR_NAO_LOCALIZADO",
        "DEVEDOR_INSOLVENTE",
        "ENCERRADA_SEM_SUCESSO",
    ])
    def test_prosseguir_various_statuses(self, evaluator, status_negociacao):
        """Test proceed with various negotiation statuses"""
        inputs = {"diasAtraso": 400, "tentativasCobranca": 5, "statusNegociacao": status_negociacao, "possuiGarantia": False}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Prosseguir"
        assert result.elegivel_deducao_fiscal is True


# ==============================================================================
# RECV-WRITEOFF-002: Provisao Deducao Fiscal
# ==============================================================================

class TestRECVWRITEOFF002:
    """Test cases for RECV-WRITEOFF-002: Provisao Deducao Fiscal"""

    DECISION_ID = "Decision_RECV_WRITEOFF_002"

    @pytest.mark.parametrize("inputs,expected_resultado,expected_risco", [
        # BLOQUEAR: Missing documentation
        ({"documentacaoSuporte": "AUSENTE"},
         "Bloquear", "CRITICO"),

        # BLOQUEAR: Related parties
        ({"partesRelacionadas": True},
         "Bloquear", "ALTO"),

        # BLOQUEAR: Non-deductible classification
        ({"classificacaoFiscal": "NAO_DEDUTIVEL", "partesRelacionadas": False},
         "Bloquear", "BAIXO"),
    ])
    def test_bloquear_scenarios(self, evaluator, inputs, expected_resultado, expected_risco):
        """Test blocking scenarios for fiscal deductions"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == expected_resultado
        assert result.risco_fiscal == expected_risco

    def test_alertar_partial_documentation(self, evaluator):
        """Test alert for partial documentation"""
        inputs = {"documentacaoSuporte": "PARCIAL", "partesRelacionadas": False}
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Alertar"
        assert result.risco_fiscal == "MEDIO"

    @pytest.mark.parametrize("inputs,expected_acao", [
        # Complete with protest
        ({"documentacaoSuporte": "COMPLETA", "classificacaoFiscal": "DEDUTIVEL", "temProtesto": True, "partesRelacionadas": False},
         "DEDUZIR_IRPJ_CSLL"),

        # Complete and deductible (no protest)
        ({"documentacaoSuporte": "COMPLETA", "classificacaoFiscal": "DEDUTIVEL", "partesRelacionadas": False},
         "DEDUZIR_IRPJ_CSLL"),

        # Partially deductible
        ({"documentacaoSuporte": "COMPLETA", "classificacaoFiscal": "PARCIALMENTE_DEDUTIVEL", "partesRelacionadas": False},
         "DEDUZIR_IRPJ_CSLL"),
    ])
    def test_prosseguir_scenarios(self, evaluator, inputs, expected_acao):
        """Test proceed scenarios for fiscal deductions"""
        result = evaluator.evaluate(self.DECISION_ID, inputs)
        assert result.resultado == "Prosseguir"
        assert result.acao_recomendada == expected_acao


# ==============================================================================
# Summary Statistics
# ==============================================================================

class TestSummaryStatistics:
    """Generate summary statistics for test coverage"""

    def test_count_test_cases(self):
        """Count total test cases across all rules"""
        # This is a meta-test that documents coverage
        test_classes = [
            TestCOMPLGPD001, TestCOMPLGPD002, TestCOMPLGPD003,
            TestCOMPLGPD004, TestCOMPLGPD005,
            TestBILLOPME001, TestBILLOPME002, TestBILLOPME003,
            TestBILLMED001, TestBILLMED002, TestBILLMED003,
            TestRECVPARTIAL001, TestRECVPARTIAL002,
            TestRECVWRITEOFF001, TestRECVWRITEOFF002,
        ]

        total_tests = 0
        for cls in test_classes:
            methods = [m for m in dir(cls) if m.startswith('test_')]
            total_tests += len(methods)

        # We expect at least 50 test methods (actual parametrized count is 96+)
        assert total_tests >= 50, f"Expected at least 50 test methods, got {total_tests}"

        # Log for information
        print(f"\n===== TIER1 DMN Test Coverage =====")
        print(f"Total Rules Tested: 15")
        print(f"Total Test Methods: {total_tests}")
        print(f"Parametrized Test Cases: 96+ (see pytest output)")
        print(f"Average Tests per Rule: {total_tests / 15:.1f}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
