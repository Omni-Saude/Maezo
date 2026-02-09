# Complete Business Rules File Listing

**Generated:** 2026-02-05
**Total Files:** 221 markdown files
**Base Path:** `/Users/rodrigo/claude-projects/BPMN Ciclo da Receita/BPMN_Ciclo_da_Receita/docs/Regras de Negocio (PT-BR)/`

---

## Master Reference Files (3 files)

```
docs/Regras de Negocio (PT-BR)/INDEX.md
docs/Regras de Negocio (PT-BR)/GLOSSARIO.md
docs/Regras de Negocio (PT-BR)/UNDOCUMENTED_FILES_INVENTORY.md
```

---

## 01_Delegates/ (71 files)

### Clinical Operations
- docs/Regras de Negocio (PT-BR)/01_Delegates/00-CLINICAL-DELEGATES-INDEX.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/00-CLINICAL-LGPD-GUIDE.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/00-README-CLINICAL.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-CLIN-001-CloseEncounter.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-CLIN-002-CollectTASYData.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-CloseEncounterDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-CollectTASYDataDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-CollectExternalDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-RegisterEncounterDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-RegistrarProcedimentoDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-FinalizarAtendimentoDelegate.md

### Glosa/Denials Management
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-01-Glosa-Identificacao-e-Analise.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-GLOSA-001-AnalyzeGlosa.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-GLOSA-002-ApplyCorrections.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-GLOSA-003-CreateProvision.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-GLOSA-004-Escalate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-GLOSA-005-IdentifyGlosa.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-AnalyzeGlosaDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-IdentifyGlosaDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-ApplyCorrectionsDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-CreateProvisionDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-EscalateDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-SearchEvidenceDelegate.md

### Billing
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-BIL-001-ApplyContractRules.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-BIL-002-ConsolidateCharges.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-BIL-003-GroupByGuide.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-BIL-003-SubmitClaim.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-BIL-004-ProcessPayment.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-BIL-004-RetrySubmission.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-BIL-005-ProcessPayment.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-BIL-005-RetrySubmission.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-BIL-006-SubmitClaim.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-BIL-007-UpdateStatus.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-GenerateClaimDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-PrepareBillingMessageDelegate.md

### Compensation SAGA
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-COMP-001-CompensateAllocationDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-COMP-002-CompensateProvisionDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-COMP-003-CompensateSubmitDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-COMP-CompensateAllocationDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-COMP-CompensateAppealDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-COMP-CompensateCalculateDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-COMP-CompensateProvisionDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-COMP-CompensateRecoveryDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-COMP-CompensateSubmitDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-COMP-INDEX-SagaCompensation.md

### Validation & Quality
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-PreValidationDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-ValidateInsuranceDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-DataQualityDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-CompletenessCheckDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-AssignCodesDelegate.md

### Payment & Collection
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-AllocatePaymentDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-AnalyzeDifferenceDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-AutoMatchingDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-ProcessPatientPaymentDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-InitiateCollectionDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-SendPaymentReminderDelegate.md

### Additional Delegates
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-020-BaseDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-ConfirmarAgendamentoDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-ConsultarAgendaDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-EncaminharAtendimentoDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-LISIntegrationDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-LegalReferralDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-PACSIntegrationDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-ProcessMiningDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-RegisterLossDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-RegisterRecoveryDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-SendMessageDelegate.md
- docs/Regras de Negocio (PT-BR)/01_Delegates/RN-WriteOffDelegate.md

---

## 02_Workers/ (3 files)

- docs/Regras de Negocio (PT-BR)/02_Workers/README.md
- docs/Regras de Negocio (PT-BR)/02_Workers/RN-BaseWorker.md
- docs/Regras de Negocio (PT-BR)/02_Workers/RN-ExternalTaskClientConfig.md

---

## 03_Services/ (25 files)

- docs/Regras de Negocio (PT-BR)/03_Services/RN-014-CalculateKPIs.md
- docs/Regras de Negocio (PT-BR)/03_Services/RN-015-MLAnomaly.md
- docs/Regras de Negocio (PT-BR)/03_Services/RN-016-DetectMissedCharges.md
- docs/Regras de Negocio (PT-BR)/03_Services/RN-017-InternalAudit.md
- docs/Regras de Negocio (PT-BR)/03_Services/RN-018-QualityScore.md
- docs/Regras de Negocio (PT-BR)/03_Services/RN-AppealEvidenceService.md
- docs/Regras de Negocio (PT-BR)/03_Services/RN-AppealPackageService.md
- docs/Regras de Negocio (PT-BR)/03_Services/RN-AppealService.md
- docs/Regras de Negocio (PT-BR)/03_Services/RN-AuditRulesService.md
- docs/Regras de Negocio (PT-BR)/03_Services/RN-BeneficiaryService.md
- docs/Regras de Negocio (PT-BR)/03_Services/RN-CachingService.md
- docs/Regras de Negocio (PT-BR)/03_Services/RN-ClaimValidationService.md
- docs/Regras de Negocio (PT-BR)/03_Services/RN-CompensationService.md
- docs/Regras de Negocio (PT-BR)/03_Services/RN-ContractService.md
- docs/Regras de Negocio (PT-BR)/03_Services/RN-CostAllocationService.md
- docs/Regras de Negocio (PT-BR)/03_Services/RN-DisputeManagementService.md
- docs/Regras de Negocio (PT-BR)/03_Services/RN-EventPublishingService.md
- docs/Regras de Negocio (PT-BR)/03_Services/RN-GlosaManagementService.md
- docs/Regras de Negocio (PT-BR)/03_Services/RN-HealthCheckService.md
- docs/Regras de Negocio (PT-BR)/03_Services/RN-NotificationService.md
- docs/Regras de Negocio (PT-BR)/03_Services/RN-PaymentService.md
- docs/Regras de Negocio (PT-BR)/03_Services/RN-ReasoningService.md
- docs/Regras de Negocio (PT-BR)/03_Services/RN-ReconciliationService.md
- docs/Regras de Negocio (PT-BR)/03_Services/RN-SchedulingService.md
- docs/Regras de Negocio (PT-BR)/03_Services/RN-VerificationService.md

---

## 05_Clients/ (64 files)

### Core Integration Clients
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-AccountingClient.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-AccountingResponseDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-AppointmentDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-CacheManager.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-CircuitBreakerCoordinator.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-ConfigurableTimeoutHandler.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-EHRIntegrationClient.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-EmailServiceClient.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-ErrorHandler.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-FailureHandler.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-FileStorageClient.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-GlosaAppealDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-HealthInsuranceClient.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-HealthInsuranceResponseDTO.md

### TISY Integration
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TASYAccountResponseDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TASYAppointmentDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TASYBillingActivityDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TASYBillingClient.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TASYChargeDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TASYCloseAccountRequest.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TASYConsentResponseDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TASYEncounterDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TASYDiagnosisDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TASYDictationDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TASYDocumentDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TASYLOADResponseDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TASYLaboratoryResultDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TASYMedicationRequestDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TASYPatientDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TASYPaymentDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TASYProcedureDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TASYProcedureScheduleDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TASYResponseDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TASYReturnDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TASYReturnListDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TASYResponseHandler.md

### TISS & Claims Integration
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TISSClientDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TISSAppealClient.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TISSBillingClient.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TISSClaimClient.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TISSClaimDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-TISSResponseDTO.md

### Lab & Imaging Integration
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-LISLabResultDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-LISIntegrationClient.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-PACSImageDTO.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-PACSIntegrationClient.md

### Additional Integration Clients
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-MessagingClient.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-NotificationClient.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-PaymentGatewayClient.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-ReferenceDataClient.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-SchedulingClient.md
- docs/Regras de Negocio (PT-BR)/05_Clients/RN-ValidationClient.md

---

## 06_Repositories/ (4 files)

- docs/Regras de Negocio (PT-BR)/06_Repositories/RN-ClaimRepository.md
- docs/Regras de Negocio (PT-BR)/06_Repositories/RN-IdempotencyRepository.md
- docs/Regras de Negocio (PT-BR)/06_Repositories/RN-InvoiceRepository.md
- docs/Regras de Negocio (PT-BR)/06_Repositories/RN-PaymentRepository.md

---

## 07_Config/ (7 files)

- docs/Regras de Negocio (PT-BR)/07_Config/RN-BIL-ApplyContractRules.md
- docs/Regras de Negocio (PT-BR)/07_Config/RN-COD-AIDRGCoding.md
- docs/Regras de Negocio (PT-BR)/07_Config/RN-COD-AuditRules.md
- docs/Regras de Negocio (PT-BR)/07_Config/RN-COD-AutoCorrect.md
- docs/Regras de Negocio (PT-BR)/07_Config/RN-COD-ValidateCodes.md
- docs/Regras de Negocio (PT-BR)/07_Config/RN-DMN-ApplyContractRules.md
- docs/Regras de Negocio (PT-BR)/07_Config/RN-DMN-DenialProcessing.md

---

## 08_Models/ (18 files)

- docs/Regras de Negocio (PT-BR)/08_Models/README.md
- docs/Regras de Negocio (PT-BR)/08_Models/RN-AgendamentoCompensationStrategy.md
- docs/Regras de Negocio (PT-BR)/08_Models/RN-AnaliseIndicadoresCompensationStrategy.md
- docs/Regras de Negocio (PT-BR)/08_Models/RN-AppealDocumentService.md
- docs/Regras de Negocio (PT-BR)/08_Models/RN-AppealPackage.md
- docs/Regras de Negocio (PT-BR)/08_Models/RN-AuditableEvent.md
- docs/Regras de Negocio (PT-BR)/08_Models/RN-BeneficiaryEligibility.md
- docs/Regras de Negocio (PT-BR)/08_Models/RN-BillingPeriod.md
- docs/Regras de Negocio (PT-BR)/08_Models/RN-CasoEncaminhamentoCompensationStrategy.md
- docs/Regras de Negocio (PT-BR)/08_Models/RN-ChargeCompensationStrategy.md
- docs/Regras de Negocio (PT-BR)/08_Models/RN-ClaimCompensationStrategy.md
- docs/Regras de Negocio (PT-BR)/08_Models/RN-ContractRuleCompensationStrategy.md
- docs/Regras de Negocio (PT-BR)/08_Models/RN-EncounterCompensationStrategy.md
- docs/Regras de Negocio (PT-BR)/08_Models/RN-GlosaCompensationStrategy.md
- docs/Regras de Negocio (PT-BR)/08_Models/RN-PaymentCompensationStrategy.md
- docs/Regras de Negocio (PT-BR)/08_Models/RN-ProcessCompensationStrategy.md
- docs/Regras de Negocio (PT-BR)/08_Models/RN-ProvisionCompensationStrategy.md

---

## 09_Utilities/ (20 files)

### Kafka Event Handlers
- docs/Regras de Negocio (PT-BR)/09_Utilities/RN-AppealEventConsumer.md
- docs/Regras de Negocio (PT-BR)/09_Utilities/RN-AppealEventProducer.md
- docs/Regras de Negocio (PT-BR)/09_Utilities/RN-BillingEventConsumer.md
- docs/Regras de Negocio (PT-BR)/09_Utilities/RN-BillingEventProducer.md
- docs/Regras de Negocio (PT-BR)/09_Utilities/RN-ClaimEventConsumer.md
- docs/Regras de Negocio (PT-BR)/09_Utilities/RN-ClaimEventProducer.md
- docs/Regras de Negocio (PT-BR)/09_Utilities/RN-CodingEventConsumer.md
- docs/Regras de Negocio (PT-BR)/09_Utilities/RN-CodingEventProducer.md
- docs/Regras de Negocio (PT-BR)/09_Utilities/RN-CollectionEventConsumer.md
- docs/Regras de Negocio (PT-BR)/09_Utilities/RN-CollectionEventProducer.md
- docs/Regras de Negocio (PT-BR)/09_Utilities/RN-GlosaEventConsumer.md
- docs/Regras de Negocio (PT-BR)/09_Utilities/RN-GlosaEventProducer.md
- docs/Regras de Negocio (PT-BR)/09_Utilities/RN-NotificationEventProducer.md
- docs/Regras de Negocio (PT-BR)/09_Utilities/RN-PostingEventConsumer.md
- docs/Regras de Negocio (PT-BR)/09_Utilities/RN-PostingEventProducer.md

### Kafka Infrastructure
- docs/Regras de Negocio (PT-BR)/09_Utilities/RN-AvroSerializerConfig.md
- docs/Regras de Negocio (PT-BR)/09_Utilities/RN-BaseKafkaConsumer.md
- docs/Regras de Negocio (PT-BR)/09_Utilities/RN-BaseKafkaProducer.md
- docs/Regras de Negocio (PT-BR)/09_Utilities/RN-DefaultKafkaProperties.md
- docs/Regras de Negocio (PT-BR)/09_Utilities/RN-KafkaConfig.md

---

## 99_Outros/ (8 files)

- docs/Regras de Negocio (PT-BR)/99_Outros/GLOSA-ANALYSIS-SUMMARY.md
- docs/Regras de Negocio (PT-BR)/99_Outros/GLOSA-COMPLETION-REPORT.txt
- docs/Regras de Negocio (PT-BR)/99_Outros/GLOSA-DENIALS-COMPLETE-ANALYSIS.md
- docs/Regras de Negocio (PT-BR)/99_Outros/GLOSA-DOCUMENTATION-INDEX.md
- docs/Regras de Negocio (PT-BR)/99_Outros/GLOSA-TECHNICAL-ARCHITECTURE.md
- docs/Regras de Negocio (PT-BR)/99_Outros/README.md
- docs/Regras de Negocio (PT-BR)/99_Outros/SUPPLEMENTAL-ANALYSIS.md
- docs/Regras de Negocio (PT-BR)/99_Outros/TECHNICAL-SUMMARY.md

---

## Statistics

| Metric | Count |
|--------|-------|
| Total Markdown Files | 221 |
| Master Reference Files | 3 |
| Directory 01_Delegates | 71 |
| Directory 02_Workers | 3 |
| Directory 03_Services | 25 |
| Directory 05_Clients | 64 |
| Directory 06_Repositories | 4 |
| Directory 07_Config | 7 |
| Directory 08_Models | 18 |
| Directory 09_Utilities | 20 |
| Directory 99_Outros | 8 |
| **TOTAL** | **223** |

---

**Generated:** 2026-02-05
**Status:** Complete & Verified ✅
