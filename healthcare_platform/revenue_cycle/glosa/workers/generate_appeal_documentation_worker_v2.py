"""
Generate Appeal Documentation Worker (Refactored)
Purpose: Generate appeal documentation package using DMN-based decision rules

TOPIC: glosa.generate_appeal_documentation

Refactored using Keep & Augment DMN strategy:
- Existing revenue_recovery DMN preserved
- Inline rules extracted to NEW companion DMN (ADMIN_ADJUDICATION archetype)
- Worker is thin: parse → evaluate DMN → route on resultado → return

ADR Compliance: ADR-002 (tenant), ADR-003 (BaseExternalTaskWorker), ADR-007 (DMN federation)
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Dict
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker, TaskContext, TaskResult


class GenerateAppealDocumentationWorkerV2(BaseExternalTaskWorker):
    """Refactored appeal documentation generator. Thin worker pattern."""

    TOPIC = "glosa.generate_appeal_documentation"
    DMN_COMPANION_KEY = "documentation/appeal_docs_adjudication"
    DMN_COMPANION_CATEGORY = "revenue_recovery"

    # Appeal letter templates in Portuguese per reason code
    # Default template with all required sections
    DEFAULT_TEMPLATE = (
        "Data: {generation_date}\n"
        "Conta: {claim_id}\n"
        "Paciente: {patient_ref}\n"
        "Prestador: {provider_ref}\n\n"
        "RECURSO DE GLOSA\n\n"
        "Prezados Senhores,\n\n"
        "Vimos por meio desta apresentar RECURSO DE GLOSA referente à conta acima, "
        "no valor de R$ {amount}.\n\n"
        "FUNDAMENTAÇÃO:\n"
        "Conforme documentação anexa, solicitamos revisão da glosa aplicada.\n\n"
        "BASE LEGAL:\n"
        "- ANS RN 424/2017 - Prazo e procedimentos para recurso de glosa\n"
        "- ANS RN 395/2016 - Padrão TISS para troca de informações\n"
        "- Lei 9.656/98 - Lei dos Planos de Saúde\n\n"
        "Solicitamos a revisão e liberação do pagamento.\n\n"
        "Atenciosamente,\n"
        "Setor de Faturamento"
    )

    APPEAL_TEMPLATES = {
        "MISSING_SIGNATURE": (
            "Data: {generation_date}\n"
            "Conta: {claim_id}\n"
            "Paciente: {patient_ref}\n"
            "Prestador: {provider_ref}\n\n"
            "RECURSO DE GLOSA\n\n"
            "Prezados Senhores,\n\n"
            "Vimos por meio desta apresentar RECURSO DE GLOSA referente à conta acima, "
            "no valor de R$ {amount}, contestada por ausência de assinatura.\n\n"
            "FUNDAMENTAÇÃO:\n"
            "Conforme documentação anexa, a assinatura do profissional responsável consta "
            "nos documentos originais devidamente autenticados.\n\n"
            "BASE LEGAL:\n- ANS RN 424/2017 - Prazo e procedimentos para recurso de glosa\n"
            "- TISS 4.01 - Padrão para troca de informações\n\n"
            "Solicitamos a revisão e liberação do pagamento.\n\n"
            "Atenciosamente,\n"
            "Setor de Faturamento"
        ),
        "MISSING_CLINICAL_JUSTIFICATION": (
            "Data: {generation_date}\n"
            "Conta: {claim_id}\n"
            "Paciente: {patient_ref}\n"
            "Prestador: {provider_ref}\n\n"
            "RECURSO DE GLOSA\n\n"
            "Prezados Senhores,\n\n"
            "Apresentamos RECURSO DE GLOSA referente à conta acima, "
            "valor de R$ {amount}, glosada por falta de justificativa clínica.\n\n"
            "FUNDAMENTAÇÃO:\n"
            "Anexamos relatório médico completo com evolução clínica do paciente.\n\n"
            "BASE LEGAL:\n- ANS RN 424/2017 - Recurso de glosa\n- CFM Resolução 1.638/2002\n\n"
            "Solicitamos reavaliação e pagamento integral.\n\n"
            "Atenciosamente,\n"
            "Auditoria Médica"
        ),
        "INVALID_CODE": (
            "Data: {generation_date}\n"
            "Conta: {claim_id}\n"
            "Paciente: {patient_ref}\n"
            "Prestador: {provider_ref}\n\n"
            "RECURSO DE GLOSA\n\n"
            "Prezados Senhores,\n\n"
            "Recurso de glosa referente à conta acima, valor R$ {amount}, contestada por código incorreto.\n\n"
            "FUNDAMENTAÇÃO:\nO código utilizado está correto conforme TUSS vigente.\n\n"
            "BASE LEGAL:\n- ANS RN 424/2017\n- ANS RN 395/2016 - Padrão TISS\n\n"
            "Solicitamos liberação do pagamento.\n\n"
            "Atenciosamente,\n"
            "Setor de Codificação"
        ),
        "LACK_OF_PRIOR_AUTHORIZATION": (
            "Data: {generation_date}\n"
            "Conta: {claim_id}\n"
            "Paciente: {patient_ref}\n"
            "Prestador: {provider_ref}\n\n"
            "RECURSO DE GLOSA - EMERGÊNCIA/URGÊNCIA\n\n"
            "Prezados Senhores,\n\n"
            "Vimos apresentar RECURSO DE GLOSA referente à conta acima, "
            "valor de R$ {amount}, glosada por falta de autorização prévia.\n\n"
            "FUNDAMENTAÇÃO:\n"
            "Tratava-se de atendimento de EMERGÊNCIA/URGÊNCIA, nos termos do Art. 35-C da Lei 9.656/98, "
            "que DISPENSA autorização prévia para atendimentos de urgência e emergência.\n\n"
            "BASE LEGAL:\n"
            "- Lei 9.656/98 - Art. 35-C - Cobertura de urgência e emergência\n"
            "- ANS RN 424/2017 - Procedimentos de recurso\n"
            "- CFM Resolução 1.451/1995 - Definição de urgência e emergência\n\n"
            "Solicitamos a imediata revisão e liberação do pagamento integral.\n\n"
            "Atenciosamente,\n"
            "Auditoria Médica"
        ),
        # Enum value aliases (GLOSA_XXX codes)
        "GLOSA_002": (  # Alias for LACK_OF_PRIOR_AUTHORIZATION
            "Data: {generation_date}\n"
            "Conta: {claim_id}\n"
            "Paciente: {patient_ref}\n"
            "Prestador: {provider_ref}\n\n"
            "RECURSO DE GLOSA - EMERGÊNCIA/URGÊNCIA\n\n"
            "Prezados Senhores,\n\n"
            "Vimos apresentar RECURSO DE GLOSA referente à conta acima, "
            "valor de R$ {amount}, glosada por falta de autorização prévia.\n\n"
            "FUNDAMENTAÇÃO:\n"
            "Tratava-se de atendimento de EMERGÊNCIA/URGÊNCIA, nos termos do Art. 35-C da Lei 9.656/98, "
            "que DISPENSA autorização prévia para atendimentos de urgência e emergência.\n\n"
            "BASE LEGAL:\n"
            "- Lei 9.656/98 - Art. 35-C - Cobertura de urgência e emergência\n"
            "- ANS RN 424/2017 - Procedimentos de recurso\n"
            "- CFM Resolução 1.451/1995 - Definição de urgência e emergência\n\n"
            "Solicitamos a imediata revisão e liberação do pagamento integral.\n\n"
            "Atenciosamente,\n"
            "Auditoria Médica"
        ),
        "GLOSA_011": (  # MISSING_SIGNATURE
            "Data: {generation_date}\n"
            "Conta: {claim_id}\n"
            "Paciente: {patient_ref}\n"
            "Prestador: {provider_ref}\n\n"
            "RECURSO DE GLOSA\n\n"
            "Prezados Senhores,\n\n"
            "Vimos por meio desta apresentar RECURSO DE GLOSA referente à conta acima, "
            "no valor de R$ {amount}, contestada por ausência de assinatura.\n\n"
            "FUNDAMENTAÇÃO:\n"
            "Conforme documentação anexa, a assinatura do profissional responsável consta "
            "nos documentos originais devidamente autenticados.\n\n"
            "BASE LEGAL:\n- ANS RN 424/2017 - Prazo e procedimentos para recurso de glosa\n"
            "- TISS 4.01 - Padrão para troca de informações\n\n"
            "Solicitamos a revisão e liberação do pagamento.\n\n"
            "Atenciosamente,\n"
            "Setor de Faturamento"
        ),
        "GLOSA_012": (  # MISSING_CLINICAL_JUSTIFICATION
            "Data: {generation_date}\n"
            "Conta: {claim_id}\n"
            "Paciente: {patient_ref}\n"
            "Prestador: {provider_ref}\n\n"
            "RECURSO DE GLOSA\n\n"
            "Prezados Senhores,\n\n"
            "Apresentamos RECURSO DE GLOSA referente à conta acima, "
            "valor de R$ {amount}, glosada por falta de justificativa clínica.\n\n"
            "FUNDAMENTAÇÃO:\n"
            "Anexamos relatório médico completo com evolução clínica do paciente.\n\n"
            "BASE LEGAL:\n- ANS RN 424/2017 - Recurso de glosa\n- CFM Resolução 1.638/2002\n\n"
            "Solicitamos reavaliação e pagamento integral.\n\n"
            "Atenciosamente,\n"
            "Auditoria Médica"
        ),
        "GLOSA_016": (  # LACK_OF_PRIOR_AUTHORIZATION
            "Data: {generation_date}\n"
            "Conta: {claim_id}\n"
            "Paciente: {patient_ref}\n"
            "Prestador: {provider_ref}\n\n"
            "RECURSO DE GLOSA - EMERGÊNCIA/URGÊNCIA\n\n"
            "Prezados Senhores,\n\n"
            "Vimos apresentar RECURSO DE GLOSA referente à conta acima, "
            "valor de R$ {amount}, glosada por falta de autorização prévia.\n\n"
            "FUNDAMENTAÇÃO:\n"
            "Tratava-se de atendimento de EMERGÊNCIA/URGÊNCIA, nos termos do Art. 35-C da Lei 9.656/98, "
            "que DISPENSA autorização prévia para atendimentos de urgência e emergência.\n\n"
            "BASE LEGAL:\n"
            "- Lei 9.656/98 - Art. 35-C - Cobertura de urgência e emergência\n"
            "- ANS RN 424/2017 - Procedimentos de recurso\n"
            "- CFM Resolução 1.451/1995 - Definição de urgência e emergência\n\n"
            "Solicitamos a imediata revisão e liberação do pagamento integral.\n\n"
            "Atenciosamente,\n"
            "Auditoria Médica"
        ),
    }

    def execute(self, context: TaskContext) -> TaskResult:
        try:
            variables = context.variables
            eligible_glosas = variables.get("eligibleGlosas", [])
            claim_id = variables.get("claimId", "UNKNOWN")

            if not eligible_glosas:
                return TaskResult.bpmn_error(
                    error_code="ERR_NO_GLOSAS",
                    error_message="Nenhuma glosa elegível para gerar documentação",
                    variables={"error": "Nenhuma glosa elegível para gerar documentação"},
                )

            # Evaluate companion DMN for documentation requirements
            first_glosa = eligible_glosas[0]
            reason_code = first_glosa.get("reasonCode", "TISS_VALIDATION")
            glosa_type = first_glosa.get("type", "ADMINISTRATIVE")

            try:
                dmn_result = self.evaluate_dmn(
                    context=context,
                    decision_key=self.DMN_COMPANION_KEY,
                    variables={
                        "reasonCode": reason_code,
                        "glosaType": glosa_type,
                    },
                    category=self.DMN_COMPANION_CATEGORY,
                )
            except Exception as dmn_error:
                self.logger.warning(f"DMN evaluation failed, using fallback: {dmn_error}")
                dmn_result = {}

            # Handle BOTH old 5-output and new 3-output DMN schemas with fallback
            resultado = dmn_result.get("resultado", "PROSSEGUIR")
            acao = dmn_result.get("acao") or dmn_result.get("observacao", "Processar normalmente") + " " + dmn_result.get("acaoRecomendada", "")
            risco = dmn_result.get("risco") or dmn_result.get("riscoDenial", "BAIXO")

            # Generate appeal documentation
            appeal_doc_id = f"APPEAL-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            generation_date = datetime.utcnow().strftime('%Y-%m-%d')

            # Build main appeal letter
            # Parse amounts (handle both deniedAmount and amountBRL formats)
            def parse_amount(glosa):
                amount_str = glosa.get("deniedAmount") or glosa.get("amountBRL", "0")
                # Handle Brazilian format (1.234,56) and standard format (1234.56)
                if isinstance(amount_str, str):
                    # Convert Brazilian format to standard
                    amount_str = amount_str.replace(".", "").replace(",", ".")
                try:
                    return float(amount_str)
                except (ValueError, TypeError):
                    return 0.0

            total_amount = sum(parse_amount(g) for g in eligible_glosas)
            template = self.APPEAL_TEMPLATES.get(reason_code, self.DEFAULT_TEMPLATE)

            appeal_letter = template.format(
                claim_id=claim_id,
                amount=f"{total_amount:.2f}",
                generation_date=generation_date,
                patient_ref=variables.get("patientReference", "N/A"),
                provider_ref=variables.get("providerReference", "N/A"),
            )

            # Required documents based on reason
            required_documents = self._get_required_documents(reason_code)
            evidence_checklist = self._get_evidence_checklist(glosa_type, eligible_glosas)

            # Regulatory references
            regulatory_references = self._get_regulatory_references()

            # Individual letters per glosa
            individual_letters = self._generate_individual_letters(
                eligible_glosas,
                claim_id,
                variables.get("patientReference", "N/A"),
                variables.get("providerReference", "N/A")
            )

            # Format amount in Brazilian format
            total_amount_brl = f"{total_amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

            # Route on resultado
            if resultado == "BLOQUEAR":
                return TaskResult.bpmn_error(
                    error_code="ERR_DOCUMENTATION_BLOCKED",
                    error_message=f"Documentação bloqueada: {acao}",
                    variables={"risk": risco, "reason": acao},
                )
            elif resultado == "PROSSEGUIR":
                return TaskResult.success({
                    "appealDocumentId": appeal_doc_id,
                    "appealLetter": appeal_letter,
                    "evidenceChecklist": evidence_checklist,
                    "requiredDocuments": required_documents,
                    "regulatoryReferences": regulatory_references,
                    "individualLetters": individual_letters,
                    "totalAppealAmount": total_amount_brl,
                    "documentationComplete": True,
                    "generationDate": datetime.utcnow().isoformat(),
                    "risk": risco,
                    "action": acao,
                })
            else:  # REVISAR
                return TaskResult.success({
                    "appealDocumentId": appeal_doc_id,
                    "appealLetter": appeal_letter,
                    "evidenceChecklist": evidence_checklist,
                    "requiredDocuments": required_documents,
                    "regulatoryReferences": regulatory_references,
                    "individualLetters": individual_letters,
                    "totalAppealAmount": total_amount_brl,
                    "requiresReview": True,
                    "documentationComplete": False,
                    "generationDate": datetime.utcnow().isoformat(),
                    "risk": risco,
                    "action": acao,
                })

        except Exception as e:
            self.logger.error(f"Error generating appeal documentation: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_DOCUMENTATION_GENERATION",
                error_message=str(e),
            )

    def _get_required_documents(self, reason_code: str) -> list[str]:
        """Get required documents based on reason code."""
        doc_map = {
            "MISSING_SIGNATURE": ["Documentos originais com assinatura", "Termo de consentimento"],
            "MISSING_CLINICAL_JUSTIFICATION": ["Relatório médico completo", "Evolução clínica", "Exames complementares"],
            "INVALID_CODE": ["Tabela TUSS/CBHPM vigente", "Documentação técnica"],
            # Enum code aliases
            "GLOSA_011": ["Documentos originais com assinatura", "Termo de consentimento"],
            "GLOSA_012": ["Relatório médico completo", "Evolução clínica", "Exames complementares"],
        }
        return doc_map.get(reason_code, ["Documentação comprobatória"])

    def _get_evidence_checklist(self, glosa_type: str, glosas: list) -> list[str]:
        """Get evidence checklist based on glosa type."""
        checklist_items = []

        # Type-based checklist (handle both upper and lowercase)
        checklist_map = {
            "ADMINISTRATIVE": ["Cópia da nota fiscal", "Guia TISS completa"],
            "administrative": ["Cópia da nota fiscal", "Guia TISS completa"],
            "TECHNICAL": ["Relatório médico detalhado", "Exames complementares", "Evolução clínica"],
            "technical": ["Relatório médico detalhado", "Exames complementares", "Evolução clínica"],
            "PARTIAL": ["Documentação específica do item", "Justificativa de valor"],
            "partial": ["Documentação específica do item", "Justificativa de valor"],
        }
        checklist_items.extend(checklist_map.get(glosa_type, ["Documentação padrão"]))

        # Add items from all glosa types present
        types_present = {g.get("type", "") for g in glosas}
        for gtype in types_present:
            if gtype and gtype != glosa_type and gtype in checklist_map:
                checklist_items.extend(checklist_map[gtype])

        return list(set(checklist_items))  # Remove duplicates

    def _get_regulatory_references(self) -> list[str]:
        """Get regulatory references for appeals."""
        return [
            "ANS RN 424/2017 - Prazo e procedimentos para recurso de glosa",
            "ANS RN 395/2016 - Padrão TISS para troca de informações",
            "Lei 9.656/98 - Lei dos Planos de Saúde",
            "ANS RN 363/2014 - Padrões Mínimos de Informação",
        ]

    def _generate_individual_letters(self, glosas: list, claim_id: str, patient_ref: str = "N/A", provider_ref: str = "N/A") -> list[dict]:
        """Generate individual appeal letters for each glosa."""
        letters = []
        generation_date = datetime.utcnow().strftime('%Y-%m-%d')

        for glosa in glosas:
            reason_code = glosa.get("reasonCode", "UNKNOWN")
            amount_str = glosa.get("deniedAmount") or glosa.get("amountBRL", "0")
            glosa_id = glosa.get("glosaId", glosa.get("glosa_id", "UNKNOWN"))

            template = self.APPEAL_TEMPLATES.get(reason_code, self.DEFAULT_TEMPLATE)
            letter = template.format(
                claim_id=claim_id,
                amount=amount_str,
                glosa_id=glosa_id,
                generation_date=generation_date,
                patient_ref=patient_ref,
                provider_ref=provider_ref,
            )

            letters.append({
                "glosaId": glosa_id,
                "letter": letter,
                "reasonCode": reason_code,
            })

        return letters
# Backward compatibility alias
GenerateAppealDocumentationWorker = GenerateAppealDocumentationWorkerV2
