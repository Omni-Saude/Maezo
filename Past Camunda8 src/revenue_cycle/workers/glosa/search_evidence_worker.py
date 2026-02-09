"""
SearchEvidenceWorker - Zeebe worker for searching clinical evidence.

This worker searches for medical evidence, documentation, and clinical records
to support denial appeals and glosa disputes. It integrates with TASY (ERP),
LIS (Laboratory), and PACS (Imaging) systems to gather comprehensive evidence.

Business Rule: RN-SearchEvidenceDelegate.md
Regulatory Compliance: ANS RN 424/2017 (appeal documentation), ANS RN 395/2016
Migrated from: com.hospital.revenuecycle.delegates.glosa.SearchEvidenceDelegate
Topic: search-evidence
BPMN Task: Task_Search_Evidence (Buscar Evidencias)
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional

import structlog
from pydantic import BaseModel, Field

from revenue_cycle.config import Settings
from revenue_cycle.integrations.lis.client import LISClient
from revenue_cycle.integrations.pacs.client import PACSClient
from revenue_cycle.integrations.tasy.client import TasyClient
from revenue_cycle.multi_tenant.credentials import TenantCredentialManager
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


class DocumentType(str, Enum):
    """Types of clinical evidence documents."""

    AUTHORIZATION_GUIDE = "AUTHORIZATION_GUIDE"
    MEDICAL_ORDER = "MEDICAL_ORDER"
    MEDICAL_RECORD = "MEDICAL_RECORD"
    CLINICAL_EVOLUTION = "CLINICAL_EVOLUTION"
    DIAGNOSTIC_REPORT = "DIAGNOSTIC_REPORT"
    LAB_RESULTS = "LAB_RESULTS"
    IMAGING_REPORT = "IMAGING_REPORT"
    CLINICAL_JUSTIFICATION = "CLINICAL_JUSTIFICATION"
    CONSENT_FORM = "CONSENT_FORM"
    DISCHARGE_SUMMARY = "DISCHARGE_SUMMARY"


class DocumentRelevance(str, Enum):
    """Document relevance/criticality levels."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class DenialCategory(str, Enum):
    """Denial categories for category-specific searches."""

    CLINICAL = "CLINICAL"
    AUTHORIZATION = "AUTHORIZATION"
    CONTRACTUAL = "CONTRACTUAL"
    DOCUMENTATION = "DOCUMENTATION"
    ADMINISTRATIVE = "ADMINISTRATIVE"


class EvidenceDocument(BaseModel):
    """Clinical evidence document model."""

    document_id: str = Field(description="Unique document ID")
    document_type: DocumentType = Field(description="Type of document")
    encounter_id: str = Field(description="Associated encounter ID")
    title: str = Field(description="Document title/description")
    document_date: datetime = Field(description="Document creation date")
    author: str = Field(description="Document author (physician, system, etc.)")
    relevance: DocumentRelevance = Field(description="Document criticality level")
    source: str = Field(description="Source system (TASY, LIS, PACS)")
    found: bool = Field(default=True, description="Whether document was found")
    content_summary: Optional[str] = Field(default=None, description="Brief content summary")
    storage_location: Optional[str] = Field(default=None, description="Storage path/URL")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        """Pydantic config."""

        frozen = False


class EvidenceSearchResult(BaseModel):
    """Complete evidence search result."""

    found_documents: List[EvidenceDocument] = Field(
        default_factory=list, description="Documents found"
    )
    missing_documents: List[str] = Field(
        default_factory=list, description="Types of missing documents"
    )
    completeness_score: float = Field(ge=0.0, le=1.0, description="Completeness score (0-1)")
    critical_documents_missing: bool = Field(description="Whether critical docs are missing")
    sufficient_for_appeal: bool = Field(description="Sufficient evidence for appeal")
    recommendations: List[str] = Field(default_factory=list, description="Document recommendations")

    class Config:
        """Pydantic config."""

        frozen = False


# Critical documents that MUST be present for appeal
CRITICAL_DOCUMENT_TYPES = {
    DocumentType.AUTHORIZATION_GUIDE,
    DocumentType.MEDICAL_RECORD,
}

# Expected documents by category
EXPECTED_DOCUMENTS_BY_CATEGORY = {
    DenialCategory.CLINICAL: [
        DocumentType.MEDICAL_RECORD,
        DocumentType.CLINICAL_EVOLUTION,
        DocumentType.CLINICAL_JUSTIFICATION,
        DocumentType.LAB_RESULTS,
        DocumentType.DIAGNOSTIC_REPORT,
    ],
    DenialCategory.AUTHORIZATION: [
        DocumentType.AUTHORIZATION_GUIDE,
        DocumentType.MEDICAL_ORDER,
        DocumentType.CLINICAL_JUSTIFICATION,
    ],
    DenialCategory.CONTRACTUAL: [
        DocumentType.AUTHORIZATION_GUIDE,
        DocumentType.MEDICAL_RECORD,
    ],
    DenialCategory.DOCUMENTATION: [
        DocumentType.MEDICAL_RECORD,
        DocumentType.AUTHORIZATION_GUIDE,
        DocumentType.CLINICAL_EVOLUTION,
    ],
}


@worker(topic="search-evidence", max_jobs=8, lock_duration=60000)
class SearchEvidenceWorker(BaseWorker):
    """
    Zeebe worker for searching clinical evidence to support denial appeals.

    BPMN Task: Task_Search_Evidence
    Topic: search-evidence

    This worker integrates with:
    - TASY: Medical records, clinical notes, authorization guides
    - LIS: Laboratory results and reports
    - PACS: Imaging studies and radiology reports

    Input Variables:
        - encounterId: Encounter identifier (required)
        - denialCode: TISS denial code
        - denialCategory: Category of denial (CLINICAL, AUTHORIZATION, etc.)
        - procedureCode: Specific procedure code (optional)

    Output Variables:
        - foundDocuments: List of evidence documents found
        - missingDocuments: List of missing document types
        - documentationComplete: Boolean, if documentation is complete
        - completenessScore: Score 0.0-1.0 indicating completeness
        - sufficientForAppeal: Boolean, if evidence is sufficient
        - evidenceRecommendations: List of recommendations
        - criticalDocumentsMissing: Boolean, if critical docs missing
        - documentCount: Total documents found
        - canProceedWithAppeal: Boolean, routing variable (= sufficientForAppeal)
        - needsDocumentCollection: Boolean, if more docs needed
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        credential_manager: Optional[TenantCredentialManager] = None,
        **kwargs,
    ):
        """Initialize the worker with integration clients."""
        super().__init__(settings=settings)
        self._credential_manager = credential_manager or TenantCredentialManager()

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "search_evidence"

    async def _search_tasy_evidence(
        self,
        tasy_client: TasyClient,
        encounter_id: str,
        patient_id: str,
        category: DenialCategory,
    ) -> List[EvidenceDocument]:
        """
        Search TASY for medical records and authorization documents.

        Args:
            tasy_client: Initialized TASY client
            encounter_id: Encounter ID
            patient_id: Patient ID
            category: Denial category

        Returns:
            List of evidence documents from TASY
        """
        documents = []

        try:
            # Get complete medical record
            medical_record = await tasy_client.get_medical_record(patient_id, encounter_id)

            # Medical record document
            if medical_record:
                documents.append(
                    EvidenceDocument(
                        document_id=f"TASY-MR-{encounter_id}",
                        document_type=DocumentType.MEDICAL_RECORD,
                        encounter_id=encounter_id,
                        title="Prontuário Médico Completo",
                        document_date=medical_record.admission_date,
                        author="TASY_SYSTEM",
                        relevance=DocumentRelevance.CRITICAL,
                        source="TASY",
                        content_summary=f"{len(medical_record.diagnoses)} diagnoses, {len(medical_record.procedures)} procedures",
                        metadata={
                            "diagnoses_count": len(medical_record.diagnoses),
                            "procedures_count": len(medical_record.procedures),
                            "has_discharge_summary": medical_record.discharge_summary is not None,
                        },
                    )
                )

            # Clinical evolution notes
            if medical_record.evolucao:
                documents.append(
                    EvidenceDocument(
                        document_id=f"TASY-EVOL-{encounter_id}",
                        document_type=DocumentType.CLINICAL_EVOLUTION,
                        encounter_id=encounter_id,
                        title="Evolução Médica",
                        document_date=medical_record.admission_date,
                        author="PHYSICIAN",
                        relevance=DocumentRelevance.MEDIUM,
                        source="TASY",
                        content_summary="Clinical evolution notes",
                    )
                )

            # Discharge summary
            if medical_record.discharge_summary:
                documents.append(
                    EvidenceDocument(
                        document_id=f"TASY-DISC-{encounter_id}",
                        document_type=DocumentType.DISCHARGE_SUMMARY,
                        encounter_id=encounter_id,
                        title="Resumo de Alta",
                        document_date=medical_record.discharge_date or medical_record.admission_date,
                        author="PHYSICIAN",
                        relevance=DocumentRelevance.LOW,
                        source="TASY",
                        content_summary="Patient discharge summary",
                    )
                )

            # Clinical justification (anamnese)
            if medical_record.anamnese:
                documents.append(
                    EvidenceDocument(
                        document_id=f"TASY-ANAM-{encounter_id}",
                        document_type=DocumentType.CLINICAL_JUSTIFICATION,
                        encounter_id=encounter_id,
                        title="Justificativa Clínica",
                        document_date=medical_record.admission_date,
                        author="PHYSICIAN",
                        relevance=DocumentRelevance.HIGH,
                        source="TASY",
                        content_summary="Clinical justification and anamnesis",
                    )
                )

            # Get encounter for authorization guide
            encounter = await tasy_client.get_encounter(encounter_id)
            if encounter:
                # Authorization guide (simulated - would come from external payer system)
                documents.append(
                    EvidenceDocument(
                        document_id=f"TASY-AUTH-{encounter_id}",
                        document_type=DocumentType.AUTHORIZATION_GUIDE,
                        encounter_id=encounter_id,
                        title=f"Guia de Autorização - {encounter.convenio}",
                        document_date=encounter.date_admission,
                        author="SISTEMA_OPERADORA",
                        relevance=DocumentRelevance.CRITICAL,
                        source="TASY",
                        content_summary=f"Authorization for {encounter.tipo_atendimento}",
                        metadata={
                            "convenio": encounter.convenio,
                            "numero_carteirinha": encounter.numero_carteirinha,
                            "medico_solicitante": encounter.medico_solicitante,
                        },
                    )
                )

            self._logger.info(
                "TASY evidence search completed",
                encounter_id=encounter_id,
                documents_found=len(documents),
            )

        except Exception as e:
            self._logger.warning(
                "Error searching TASY evidence",
                encounter_id=encounter_id,
                error=str(e),
            )

        return documents

    async def _search_lis_evidence(
        self,
        lis_client: LISClient,
        encounter_id: str,
    ) -> List[EvidenceDocument]:
        """
        Search LIS for laboratory results.

        Args:
            lis_client: Initialized LIS client
            encounter_id: Encounter ID

        Returns:
            List of laboratory evidence documents
        """
        documents = []

        try:
            # Search lab results by encounter
            lab_results = await lis_client.search_results_by_encounter(encounter_id)

            if lab_results:
                for result in lab_results:
                    documents.append(
                        EvidenceDocument(
                            document_id=f"LIS-{result.result_id}",
                            document_type=DocumentType.LAB_RESULTS,
                            encounter_id=encounter_id,
                            title=f"Lab Result - {result.test_name}",
                            document_date=result.result_date,
                            author=result.lab_technician or "LIS_SYSTEM",
                            relevance=DocumentRelevance.MEDIUM,
                            source="LIS",
                            content_summary=f"{result.test_name}: {result.value} {result.unit}",
                            metadata={
                                "test_code": result.test_code,
                                "test_name": result.test_name,
                                "value": result.value,
                                "unit": result.unit,
                                "abnormal": result.abnormal_flag,
                            },
                        )
                    )

                self._logger.info(
                    "LIS evidence search completed",
                    encounter_id=encounter_id,
                    lab_results_found=len(lab_results),
                )

        except Exception as e:
            self._logger.warning(
                "Error searching LIS evidence",
                encounter_id=encounter_id,
                error=str(e),
            )

        return documents

    async def _search_pacs_evidence(
        self,
        pacs_client: PACSClient,
        encounter_id: str,
    ) -> List[EvidenceDocument]:
        """
        Search PACS for imaging studies and reports.

        Args:
            pacs_client: Initialized PACS client
            encounter_id: Encounter ID

        Returns:
            List of imaging evidence documents
        """
        documents = []

        try:
            # Search imaging studies by encounter
            studies = await pacs_client.search_studies_by_encounter(encounter_id)

            if studies:
                for study in studies:
                    # Get radiology report for each study
                    try:
                        report = await pacs_client.get_report(study.study_id)

                        documents.append(
                            EvidenceDocument(
                                document_id=f"PACS-{study.study_id}",
                                document_type=DocumentType.IMAGING_REPORT,
                                encounter_id=encounter_id,
                                title=f"Imaging Report - {study.modality}",
                                document_date=study.study_date,
                                author=report.radiologist if report else "RADIOLOGIST",
                                relevance=DocumentRelevance.MEDIUM,
                                source="PACS",
                                content_summary=f"{study.modality} - {study.study_description}",
                                storage_location=f"/pacs/studies/{study.study_id}",
                                metadata={
                                    "modality": study.modality,
                                    "study_description": study.study_description,
                                    "accession_number": study.accession_number,
                                    "report_status": report.report_status if report else "PENDING",
                                },
                            )
                        )

                    except Exception as report_error:
                        # Add study even if report retrieval fails
                        documents.append(
                            EvidenceDocument(
                                document_id=f"PACS-{study.study_id}",
                                document_type=DocumentType.IMAGING_REPORT,
                                encounter_id=encounter_id,
                                title=f"Imaging Study - {study.modality}",
                                document_date=study.study_date,
                                author="RADIOLOGIST",
                                relevance=DocumentRelevance.MEDIUM,
                                source="PACS",
                                content_summary=f"{study.modality} - Report pending",
                                metadata={
                                    "modality": study.modality,
                                    "study_description": study.study_description,
                                },
                            )
                        )

                self._logger.info(
                    "PACS evidence search completed",
                    encounter_id=encounter_id,
                    studies_found=len(studies),
                )

        except Exception as e:
            self._logger.warning(
                "Error searching PACS evidence",
                encounter_id=encounter_id,
                error=str(e),
            )

        return documents

    async def _search_category_specific_evidence(
        self,
        tasy_client: TasyClient,
        encounter_id: str,
        category: DenialCategory,
        procedure_code: Optional[str] = None,
    ) -> List[EvidenceDocument]:
        """
        Search for category-specific evidence.

        Args:
            tasy_client: TASY client
            encounter_id: Encounter ID
            category: Denial category
            procedure_code: Procedure code (optional)

        Returns:
            Additional category-specific documents
        """
        documents = []

        try:
            if category == DenialCategory.CLINICAL and procedure_code:
                # Search for clinical justification specific to procedure
                self._logger.debug(
                    "Searching clinical justification",
                    encounter_id=encounter_id,
                    procedure_code=procedure_code,
                )
                # Would call specific TASY endpoint for procedure justification
                # For now, this is placeholder

            elif category in (DenialCategory.AUTHORIZATION, DenialCategory.CONTRACTUAL):
                # Search for authorization documents
                self._logger.debug(
                    "Searching authorization documents",
                    encounter_id=encounter_id,
                    category=category.value,
                )
                # Would call specific TASY endpoint for authorization history
                # For now, this is placeholder

        except Exception as e:
            self._logger.warning(
                "Error in category-specific search",
                category=category.value,
                error=str(e),
            )

        return documents

    def _calculate_completeness(
        self,
        found_documents: List[EvidenceDocument],
        category: DenialCategory,
    ) -> tuple[float, List[str]]:
        """
        Calculate documentation completeness score.

        Args:
            found_documents: Documents found
            category: Denial category

        Returns:
            Tuple of (completeness_score, missing_document_types)
        """
        # Get expected documents for category
        expected_types = set(
            EXPECTED_DOCUMENTS_BY_CATEGORY.get(category, [DocumentType.MEDICAL_RECORD])
        )

        # Get found document types
        found_types = {doc.document_type for doc in found_documents}

        # Calculate completeness
        if not expected_types:
            return 1.0, []

        found_count = len(found_types.intersection(expected_types))
        expected_count = len(expected_types)

        completeness_score = found_count / expected_count

        # Missing documents
        missing_types = expected_types - found_types
        missing_documents = [doc_type.value for doc_type in missing_types]

        return completeness_score, missing_documents

    def _check_critical_documents(
        self,
        found_documents: List[EvidenceDocument],
    ) -> bool:
        """
        Check if critical documents are present.

        Args:
            found_documents: Documents found

        Returns:
            True if any critical documents are missing
        """
        found_types = {doc.document_type for doc in found_documents}
        missing_critical = CRITICAL_DOCUMENT_TYPES - found_types
        return len(missing_critical) > 0

    def _generate_recommendations(
        self,
        missing_documents: List[str],
        category: DenialCategory,
        critical_missing: bool,
    ) -> List[str]:
        """
        Generate recommendations for missing evidence.

        Args:
            missing_documents: List of missing document types
            category: Denial category
            critical_missing: Whether critical documents are missing

        Returns:
            List of recommendations
        """
        recommendations = []

        # Critical document recommendations
        if critical_missing:
            if DocumentType.AUTHORIZATION_GUIDE.value in missing_documents:
                recommendations.append("Obtain authorization guide from payer system")
            if DocumentType.MEDICAL_RECORD.value in missing_documents:
                recommendations.append("Request complete medical record from TASY")

        # Category-specific recommendations
        if category == DenialCategory.CLINICAL:
            if DocumentType.CLINICAL_JUSTIFICATION.value in missing_documents:
                recommendations.append("Request clinical justification from attending physician")
            if DocumentType.LAB_RESULTS.value in missing_documents:
                recommendations.append("Retrieve lab results supporting medical necessity")

        if category == DenialCategory.AUTHORIZATION:
            if DocumentType.MEDICAL_ORDER.value in missing_documents:
                recommendations.append("Obtain medical order/prescription")

        # General recommendations
        if DocumentType.IMAGING_REPORT.value in missing_documents:
            recommendations.append("Collect imaging reports referenced in medical record")

        if DocumentType.DISCHARGE_SUMMARY.value in missing_documents:
            recommendations.append("Consider obtaining discharge summary for complete record")

        return recommendations

    def _log_evidence_summary(
        self,
        found_documents: List[EvidenceDocument],
        encounter_id: str,
    ) -> None:
        """
        Log summary of found evidence by type.

        Args:
            found_documents: Documents found
            encounter_id: Encounter ID
        """
        # Group by type
        type_counts = {}
        critical_count = 0

        for doc in found_documents:
            doc_type = doc.document_type.value
            type_counts[doc_type] = type_counts.get(doc_type, 0) + 1

            if doc.relevance == DocumentRelevance.CRITICAL:
                critical_count += 1

        # Log summary
        self._logger.info(
            "Evidence document summary",
            encounter_id=encounter_id,
            total_documents=len(found_documents),
            critical_documents=critical_count,
            **{f"{k}_count": v for k, v in type_counts.items()},
        )

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the evidence search task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with evidence search results
        """
        encounter_id = variables.get("encounterId")
        denial_code = variables.get("denialCode", "")
        denial_category_str = variables.get("denialCategory", "DOCUMENTATION")
        procedure_code = variables.get("procedureCode")

        # Get tenant context
        tenant_id = variables.get("tenantId", "default")

        self._logger.info(
            "Searching evidence for encounter",
            encounter_id=encounter_id,
            denial_code=denial_code,
            denial_category=denial_category_str,
        )

        try:
            # Parse denial category
            try:
                denial_category = DenialCategory(denial_category_str)
            except ValueError:
                denial_category = DenialCategory.DOCUMENTATION

            # Initialize integration clients
            tasy_client = TasyClient(self._credential_manager, tenant_id, self._settings)
            lis_client = LISClient(self._settings, tenant_id)
            pacs_client = PACSClient(self._settings, tenant_id)

            # Get patient ID from encounter
            await tasy_client.initialize()
            encounter = await tasy_client.get_encounter(encounter_id)
            patient_id = encounter.patient_id

            # Search evidence from all systems in parallel
            tasy_docs, lis_docs, pacs_docs, category_docs = await asyncio.gather(
                self._search_tasy_evidence(tasy_client, encounter_id, patient_id, denial_category),
                self._search_lis_evidence(lis_client, encounter_id),
                self._search_pacs_evidence(pacs_client, encounter_id),
                self._search_category_specific_evidence(
                    tasy_client, encounter_id, denial_category, procedure_code
                ),
                return_exceptions=True,
            )

            # Close TASY client
            await tasy_client.close()

            # Combine all documents (filter out exceptions)
            all_documents = []
            for doc_list in [tasy_docs, lis_docs, pacs_docs, category_docs]:
                if isinstance(doc_list, list):
                    all_documents.extend(doc_list)
                elif isinstance(doc_list, Exception):
                    self._logger.warning("Exception in evidence search", error=str(doc_list))

            # Calculate completeness
            completeness_score, missing_documents = self._calculate_completeness(
                all_documents, denial_category
            )

            # Check for critical documents
            critical_missing = self._check_critical_documents(all_documents)

            # Determine if sufficient for appeal
            sufficient_for_appeal = (
                not critical_missing and completeness_score >= 0.7 and len(all_documents) > 0
            )

            # Generate recommendations
            recommendations = self._generate_recommendations(
                missing_documents, denial_category, critical_missing
            )

            # Log evidence summary
            self._log_evidence_summary(all_documents, encounter_id)

            # Prepare output
            output = {
                "foundDocuments": [doc.model_dump() for doc in all_documents],
                "missingDocuments": missing_documents,
                "documentationComplete": completeness_score == 1.0,
                "completenessScore": completeness_score,
                "sufficientForAppeal": sufficient_for_appeal,
                "evidenceRecommendations": recommendations,
                "criticalDocumentsMissing": critical_missing,
                "documentCount": len(all_documents),
                # Routing variables
                "canProceedWithAppeal": sufficient_for_appeal,
                "needsDocumentCollection": not sufficient_for_appeal and not critical_missing,
            }

            self._logger.info(
                "Evidence search completed",
                encounter_id=encounter_id,
                documents_found=len(all_documents),
                completeness_score=completeness_score,
                sufficient_for_appeal=sufficient_for_appeal,
            )

            if not sufficient_for_appeal:
                self._logger.warning(
                    "Insufficient evidence for appeal",
                    encounter_id=encounter_id,
                    missing_documents=missing_documents,
                    critical_missing=critical_missing,
                )

            return WorkerResult.ok(output)

        except Exception as e:
            self._logger.error(
                "Error searching evidence",
                encounter_id=encounter_id,
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Evidence search failed: {e}",
                retry=True,
            )
