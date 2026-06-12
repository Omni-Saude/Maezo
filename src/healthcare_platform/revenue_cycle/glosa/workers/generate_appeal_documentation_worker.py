"""
Generate Appeal Documentation Worker

Creates appeal documentation package with letter, evidence checklist,
and regulatory references for Brazilian healthcare glosa appeals.

Topic: generate-appeal-documentation
"""

from datetime import datetime, timezone
from typing import Any
import uuid

from healthcare_platform.revenue_cycle.billing.workers.base import WorkerResult, worker
from healthcare_platform.revenue_cycle.glosa.workers.base import GlosaWorkerMixin
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.enums import GlosaReasonCode, GlosaType
from healthcare_platform.shared.domain.exceptions import GlosaException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


# Appeal letter templates in Portuguese per reason code
APPEAL_TEMPLATES = {
    GlosaReasonCode.MISSING_SIGNATURE: _(
        "Prezados Senhores,\n\n"
        "Vimos por meio desta apresentar RECURSO DE GLOSA referente à conta nº {claim_id}, "
        "no valor de R$ {amount}, contestada por ausência de assinatura.\n\n"
        "FUNDAMENTAÇÃO:\n"
        "Conforme documentação anexa, a assinatura do profissional responsável consta "
        "nos documentos originais devidamente autenticados. A ausência verificada deve-se "
        "a falha no processo de digitalização.\n\n"
        "BASE LEGAL:\n"
        "- ANS RN 424/2017 - Prazo e procedimentos para recurso de glosa\n"
        "- TISS 4.01 - Padrão para troca de informações\n\n"
        "Solicitamos a revisão e liberação do pagamento.\n\n"
        "Atenciosamente,\n"
        "Setor de Faturamento"
    ),
    GlosaReasonCode.MISSING_CLINICAL_JUSTIFICATION: _(
        "Prezados Senhores,\n\n"
        "Apresentamos RECURSO DE GLOSA referente à conta nº {claim_id}, "
        "valor de R$ {amount}, glosada por falta de justificativa clínica.\n\n"
        "FUNDAMENTAÇÃO:\n"
        "Anexamos relatório médico completo com evolução clínica do paciente, "
        "CID-10, indicação do procedimento e justificativa técnica conforme "
        "protocolos clínicos vigentes.\n\n"
        "BASE LEGAL:\n"
        "- ANS RN 424/2017 - Recurso de glosa\n"
        "- CFM Resolução 1.638/2002 - Prontuário médico\n"
        "- Lei 12.842/2013 - Ato médico\n\n"
        "Solicitamos reavaliação e pagamento integral.\n\n"
        "Atenciosamente,\n"
        "Auditoria Médica"
    ),
    GlosaReasonCode.INVALID_CODE: _(
        "Prezados Senhores,\n\n"
        "Recurso de glosa - Conta nº {claim_id}, valor R$ {amount}, "
        "contestada por código incorreto.\n\n"
        "FUNDAMENTAÇÃO:\n"
        "O código utilizado {procedure_code} está correto conforme:\n"
        "- TUSS (Terminologia Unificada da Saúde Suplementar)\n"
        "- Tabela CBHPM vigente\n"
        "- Documentação técnica do procedimento anexa\n\n"
        "BASE LEGAL:\n"
        "- ANS RN 424/2017\n"
        "- ANS RN 395/2016 - Padrão TISS\n\n"
        "Solicitamos liberação do pagamento.\n\n"
        "Atenciosamente,\n"
        "Setor de Codificação"
    ),
    GlosaReasonCode.DUPLICATE_BILLING: _(
        "Prezados Senhores,\n\n"
        "Recurso de glosa por duplicidade - Conta nº {claim_id}, R$ {amount}.\n\n"
        "FUNDAMENTAÇÃO:\n"
        "Não se trata de cobrança duplicada. Anexamos:\n"
        "- Nota fiscal original com data e hora de cada procedimento\n"
        "- Prontuário com registro de cada atendimento\n"
        "- Comprovante de procedimentos distintos em datas diferentes\n\n"
        "BASE LEGAL:\n"
        "- ANS RN 424/2017\n"
        "- Código de Defesa do Consumidor Art. 51\n\n"
        "Solicitamos revisão e pagamento.\n\n"
        "Atenciosamente,\n"
        "Faturamento"
    ),
    GlosaReasonCode.NOT_COVERED_PROCEDURE: _(
        "Prezados Senhores,\n\n"
        "Recurso - Conta nº {claim_id}, R$ {amount}, glosada por "
        "procedimento não coberto.\n\n"
        "FUNDAMENTAÇÃO:\n"
        "O procedimento está previsto no Rol ANS (Anexo I/II) e no contrato "
        "vigente entre as partes. Anexamos:\n"
        "- Cláusula contratual específica\n"
        "- Rol ANS com procedimento incluído\n"
        "- Documentação de cobertura do beneficiário\n\n"
        "BASE LEGAL:\n"
        "- ANS RN 428/2017 - Rol de procedimentos\n"
        "- ANS RN 424/2017\n"
        "- Súmula Normativa ANS nº 23\n\n"
        "Solicitamos liberação imediata.\n\n"
        "Atenciosamente,\n"
        "Relacionamento com Operadoras"
    ),
    GlosaReasonCode.LACK_OF_PRIOR_AUTHORIZATION: _(
        "Prezados Senhores,\n\n"
        "Recurso - Conta nº {claim_id}, R$ {amount}, glosada por "
        "falta de autorização prévia.\n\n"
        "FUNDAMENTAÇÃO:\n"
        "Trata-se de atendimento de EMERGÊNCIA/URGÊNCIA conforme Art. 35-C "
        "da Lei 9.656/98, dispensando autorização prévia. Anexamos:\n"
        "- Relatório de admissão hospitalar com caráter de urgência\n"
        "- Documentação de risco imediato à vida\n"
        "- Protocolo de atendimento emergencial\n\n"
        "BASE LEGAL:\n"
        "- Lei 9.656/98 Art. 35-C - Emergência/Urgência\n"
        "- ANS RN 259/2011 - Garantia de atendimento\n"
        "- ANS RN 424/2017\n\n"
        "Solicitamos pagamento integral.\n\n"
        "Atenciosamente,\n"
        "Auditoria Médica"
    ),
}

# Evidence checklist per glosa type
EVIDENCE_CHECKLIST = {
    GlosaType.ADMINISTRATIVE: [
        _("Cópia da nota fiscal original"),
        _("Guia TISS completa e assinada"),
        _("Comprovante de protocolo de entrega"),
        _("Documentação administrativa completa"),
    ],
    GlosaType.TECHNICAL: [
        _("Relatório médico detalhado"),
        _("Evolução clínica do paciente"),
        _("Exames complementares"),
        _("Justificativa técnica do procedimento"),
        _("CID-10 e indicação clínica"),
    ],
    GlosaType.PARTIAL: [
        _("Documentação específica do item glosado"),
        _("Justificativa de quantidade/valor"),
        _("Comprovante de execução"),
        _("Nota técnica se aplicável"),
    ],
}

# Standard regulatory references for appeals
REGULATORY_REFERENCES = [
    _("ANS RN 424/2017 - Procedimentos de recurso de glosa"),
    _("ANS RN 395/2016 - Padrão TISS para troca de informações"),
    _("Lei 9.656/98 - Lei dos Planos de Saúde"),
    _("Código Civil Brasileiro - Contratos"),
]


@worker(topic="generate-appeal-documentation", max_jobs=5, lock_duration=60000)
class GenerateAppealDocumentationWorker(GlosaWorkerMixin):
    """
    Worker that generates complete appeal documentation package.

    Creates:
    1. Appeal letter in Portuguese with legal references
    2. Evidence checklist per glosa type
    3. Regulatory references (ANS RN 424/2017, TISS 4.01)
    4. Required documents list

        Archetype: ADMIN_ADJUDICATION
    """

    def __init__(self) -> None:
        super().__init__()
        self.dmn_service = FederatedDMNService()

    def _evaluate_glosa_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate glosa_prevention DMN decision table."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='glosa_prevention',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    def _evaluate_appeal_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate revenue_recovery DMN decision table."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='revenue_recovery',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    async def process_task(self, job: Any, variables: dict[str, Any]) -> WorkerResult:
        """
        Generate appeal documentation package.

        Args:
            job: Zeebe job instance
            variables: Task variables containing:
                - eligibleGlosas: List of eligible glosa dicts
                - claimId: Claim identifier
                - patientReference: Patient ID
                - providerReference: Provider ID

        Returns:
            WorkerResult with documentation package
        """
        claim_id = variables.get("claimId", "UNKNOWN")
        logger.info(
            _("Gerando documentação de recurso para conta {claim_id}").format(
                claim_id=claim_id
            )
        )

        try:
            # Parse input
            eligible_glosas = variables.get("eligibleGlosas", [])
            patient_ref = variables.get("patientReference", "")
            provider_ref = variables.get("providerReference", "")

            if not eligible_glosas:
                raise GlosaException(_("Nenhuma glosa elegível para gerar documentação"))

            # Generate unique document ID
            appeal_doc_id = str(uuid.uuid4())
            generation_date = datetime.now(timezone.utc)

            # Build appeal letter
            appeal_letters = []
            evidence_checklist_items = set()
            required_documents = set()

            total_amount = self._parse_money("0,00")

            for glosa in eligible_glosas:
                reason_code_str = glosa.get("reasonCode")
                glosa_type_str = glosa.get("type")
                amount_brl = self._parse_money(glosa.get("amountBRL", "0,00"))
                procedure_code = glosa.get("procedureCode", "N/A")

                total_amount += amount_brl

                # Get template
                try:
                    reason_code = GlosaReasonCode[reason_code_str]
                    template = APPEAL_TEMPLATES.get(
                        reason_code,
                        _(
                            "Prezados Senhores,\n\nRecurso de glosa - Conta {claim_id}, "
                            "R$ {amount}.\n\nSolicitamos revisão."
                        ),
                    )
                except (KeyError, TypeError):
                    template = _(
                        "Prezados Senhores,\n\nRecurso de glosa - Conta {claim_id}, "
                        "R$ {amount}.\n\nSolicitamos revisão."
                    )

                # Format letter
                letter = template.format(
                    claim_id=claim_id,
                    amount=amount_brl.format_brl(),
                    procedure_code=procedure_code,
                )
                appeal_letters.append(
                    {
                        "glosaId": glosa.get("glosaId", ""),
                        "reasonCode": reason_code_str,
                        "letter": letter,
                    }
                )

                # Add evidence checklist
                try:
                    glosa_type = GlosaType[glosa_type_str]
                    checklist = EVIDENCE_CHECKLIST.get(glosa_type, [])
                    evidence_checklist_items.update(checklist)
                except (KeyError, TypeError):
                    pass

                # Add required documents per reason
                if reason_code_str == "MISSING_SIGNATURE":
                    required_documents.update(
                        [
                            _("Documentos originais com assinatura"),
                            _("Termo de consentimento assinado"),
                        ]
                    )
                elif reason_code_str == "MISSING_CLINICAL_JUSTIFICATION":
                    required_documents.update(
                        [
                            _("Relatório médico completo"),
                            _("Evolução clínica"),
                            _("Exames complementares"),
                        ]
                    )
                elif reason_code_str == "INVALID_CODE":
                    required_documents.update(
                        [
                            _("Tabela TUSS/CBHPM vigente"),
                            _("Documentação técnica do procedimento"),
                        ]
                    )
                elif reason_code_str == "DUPLICATE_BILLING":
                    required_documents.update(
                        [_("Nota fiscal original"), _("Registro de procedimentos")]
                    )
                elif reason_code_str == "NOT_COVERED_PROCEDURE":
                    required_documents.update(
                        [_("Cláusula contratual"), _("Rol ANS"), _("Guia de autorização")]
                    )
                elif reason_code_str == "LACK_OF_PRIOR_AUTHORIZATION":
                    required_documents.update(
                        [
                            _("Relatório de emergência/urgência"),
                            _("Documentação de risco à vida"),
                        ]
                    )

            # Build main appeal letter with all glosas
            main_letter = self._build_main_appeal_letter(
                claim_id=claim_id,
                total_amount=total_amount,
                glosa_count=len(eligible_glosas),
                generation_date=generation_date,
                patient_ref=patient_ref,
                provider_ref=provider_ref,
            )

            # Check documentation completeness
            documentation_complete = len(required_documents) <= 10  # Arbitrary threshold

            logger.info(
                _(
                    "Documentação de recurso gerada: {count} glosas, "
                    "valor total R$ {amount}, {docs} documentos necessários"
                ).format(
                    count=len(eligible_glosas),
                    amount=total_amount.format_brl(),
                    docs=len(required_documents),
                )
            )

            return WorkerResult(
                variables={
                    "appealDocumentId": appeal_doc_id,
                    "appealLetter": main_letter,
                    "individualLetters": appeal_letters,
                    "evidenceChecklist": sorted(evidence_checklist_items),
                    "regulatoryReferences": REGULATORY_REFERENCES,
                    "requiredDocuments": sorted(required_documents),
                    "documentationComplete": documentation_complete,
                    "totalAppealAmount": total_amount.format_brl(),
                    "generationDate": generation_date.isoformat(),
                },
                success=True,
            )

        except Exception as e:
            logger.error(
                _("Erro ao gerar documentação de recurso: {error}").format(error=str(e))
            )
            return WorkerResult(
                variables={"error": str(e), "appealDocumentId": ""},
                success=False,
            )

    def _build_main_appeal_letter(
        self,
        claim_id: str,
        total_amount: Any,
        glosa_count: int,
        generation_date: datetime,
        patient_ref: str,
        provider_ref: str,
    ) -> str:
        """Build main appeal letter covering all glosas."""
        return _(
            "RECURSO DE GLOSA\n\n"
            "Data: {date}\n"
            "Conta: {claim_id}\n"
            "Paciente: {patient}\n"
            "Prestador: {provider}\n\n"
            "Prezados Senhores,\n\n"
            "Vimos por meio desta apresentar RECURSO DE GLOSA referente à conta supracitada, "
            "contendo {count} item(ns) glosado(s) no valor total de R$ {amount}.\n\n"
            "Anexamos documentação completa conforme exigido pela ANS RN 424/2017 e RN 395/2016, "
            "incluindo:\n"
            "- Justificativas técnicas individuais por item\n"
            "- Documentação comprobatória completa\n"
            "- Base legal e regulatória aplicável\n"
            "- Evidências clínicas e administrativas\n\n"
            "Solicitamos a reavaliação e liberação do pagamento integral no prazo regulamentar "
            "de 30 (trinta) dias.\n\n"
            "BASE LEGAL:\n"
            "- ANS RN 424/2017 - Procedimentos de recurso de glosa\n"
            "- ANS RN 395/2016 - Padrão TISS\n"
            "- Lei 9.656/98 - Lei dos Planos de Saúde\n\n"
            "Permanecemos à disposição para esclarecimentos.\n\n"
            "Atenciosamente,\n\n"
            "Setor de Gestão de Glosas\n"
            "Auditoria e Faturamento"
        ).format(
            date=generation_date.strftime("%d/%m/%Y"),
            claim_id=claim_id,
            patient=patient_ref or _("Não informado"),
            provider=provider_ref or _("Não informado"),
            count=glosa_count,
            amount=total_amount.format_brl(),
        )
