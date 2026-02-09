# Swarm Execution Strategy - CIB7 Platform Code Generation

**Date:** 2026-02-09  
**Status:** Planning Phase - DO NOT EXECUTE YET  
**Objective:** Leverage claude-flow swarm intelligence to generate complete CIB7 platform codebase

---

## 📋 Executive Summary

This document outlines the strategic approach to using claude-flow's advanced features (memory, learning, swarm coordination, parallel execution) to generate the complete Healthcare Orchestration Platform based on:

- **Technical Specification:** 558 lines defining 29 subprocesses, 5 patient journeys, 4 operational domains
- **13 ADRs:** Architecture decisions including ADR-013 (Claude-flow swarm intelligence)
- **Migration Patterns:** Template, example, and comparison guides (100KB documentation)
- **185 Legacy Workers:** Camunda8 implementations for reference

**Compliance:** This strategy follows **ADR-013: Claude-flow Swarm Intelligence & Best Practices**

**Mandatory Best Practices:**

- ✅ Memory-first (NO temporary markdown files for status/progress)
- ✅ Intelligent model routing (40-60% cost reduction)
- ✅ Lifecycle hooks (pre-task/post-task tracking)
- ✅ Neural learning (train on generated code)
- ✅ Hive-mind coordination (hierarchical-mesh + Byzantine consensus)
- ✅ RuVector semantic search (HNSW vector database)
- ✅ Comprehensive tool usage (memory, neural, vector, patterns, validate, analyze)

**Estimated Output:**

- 29 BPMN process files (~15-20KB each)
- 185 CIB7 Python workers (~500-1000 lines each)
- 50+ DMN decision tables
- Shared infrastructure (integrations, services, domain models)
- Tests, configuration, deployment files

**Total:** ~500,000+ lines of production code

---

## 🎯 Strategic Approach

**IMPORTANT:** All commands in this document follow **ADR-013: Claude-flow Swarm Intelligence & Best Practices**

### Claude-flow Best Practices (Mandatory)

#### 1. Memory-First (NO Markdown Status Files)

**✅ DO:**
```bash
# Store progress in memory
npx @claude-flow/cli@latest memory store \
  --key "progress-phase-2-rc" \
  --value "Revenue cycle workers: 45/89 complete, 0 failures" \
  --namespace healthcare-platform

# Search prior work
npx @claude-flow/cli@latest memory search \
  --query "revenue cycle worker patterns" \
  --namespace healthcare-platform
```

**❌ DON'T:**
```bash
# NO: Don't create PROGRESS.md, STATUS.md, TODO.md files
echo "Status: 45/89 workers done" > PROGRESS.md  # ❌ WRONG
```

#### 2. Lifecycle Hooks (Task Tracking)

**Every major task MUST use hooks:**

```bash
# Before task
npx @claude-flow/cli@latest hooks pre-task \
  --description "[task]" \
  --task-id "[unique-id]" \
  --namespace healthcare-platform

# After task (success or failure)
npx @claude-flow/cli@latest hooks post-task \
  --task-id "[unique-id]" \
  --status [success|failure] \
  --output "[results]"
```

#### 3. Neural Learning (Continuous Improvement)

**After generating code, train models:**

```bash
# Train Mixture of Experts on generated workers
npx @claude-flow/cli@latest neural train \
  --modelType moe \
  --data-source "platform/workers/[domain]" \
  --epochs 10 \
  --namespace healthcare-platform

# Extract patterns for future use
npx @claude-flow/cli@latest learn \
  --from-directory "platform/workers/[domain]" \
  --extract-patterns \
  --output ".claude-flow/patterns-[domain].json"
```

#### 4. Intelligent Model Routing (Cost Optimization)

**Use built-in routing (40-60% cost reduction):**

```bash
npx @claude-flow/cli@latest hive-mind spawn \
  --workers 10 \
  --claude \
  --model-routing intelligent \
  --objective "[task]"

# Models: claude-3-7-sonnet (complex), claude-3-5-sonnet (balanced), claude-3-haiku (simple)
```

---

### Phase 0: Memory & Pattern Preparation (Pre-execution)

#### Step 0.1: Load Technical Specifications into Memory
```bash
# Store technical specification in memory
claude-flow memory store \
  --namespace healthcare-platform \
  --key tech-spec \
  --file "docs/Technical specification/technical-specification.md" \
  --description "Complete technical specification: 29 subprocesses, 5 journeys, 4 domains"

# Store each ADR individually
for adr in docs/ADRs/*.md; do
  adr_name=$(basename "$adr" .md)
  claude-flow memory store \
    --namespace healthcare-platform \
    --key "adr-$adr_name" \
    --file "$adr" \
    --description "Architecture decision: $adr_name"
done

# Store migration patterns
claude-flow memory store \
  --namespace healthcare-platform \
  --key migration-template \
  --file "docs/Technical specification/CIB7_WORKER_TEMPLATE.md" \
  --description "CIB7 worker template with all patterns"

claude-flow memory store \
  --namespace healthcare-platform \
  --key migration-example \
  --file "docs/Technical specification/EXAMPLE_MIGRATION_validate_eligibility_worker.py" \
  --description "Real-world eligibility worker migration example"

claude-flow memory store \
  --namespace healthcare-platform \
  --key migration-comparison \
  --file "docs/Technical specification/MIGRATION_COMPARISON_Camunda8_to_CIB7.md" \
  --description "Side-by-side Camunda8 to CIB7 patterns"
```

#### Step 0.2: Train Swarm on Legacy Code Patterns
```bash
# Train on existing Camunda8 workers to learn patterns
claude-flow learn \
  --from-directory "Legacy processes/workers/camunda8-implementation" \
  --namespace healthcare-platform \
  --extract-patterns \
  --pattern-types "worker,integration,error-handling,multi-tenant,business-logic" \
  --output ".claude-flow/learned-patterns.json"

# Verify pattern extraction
claude-flow patterns list \
  --namespace healthcare-platform \
  --format table
```

#### Step 0.3: Create Swarm Coordination Plan
```bash
# Generate swarm coordination manifest
claude-flow swarm plan \
  --namespace healthcare-platform \
  --strategy "domain-parallel" \
  --domains "revenue-cycle,clinical-operations,patient-access,platform-services" \
  --output ".claude-flow/swarm-plan.yaml"
```

---

## 🏗️ Phase 1: Infrastructure & Foundation (Serial Execution)

**Why Serial:** These are dependencies for all subsequent work.

### Step 1.1: Generate Shared Domain Models
```bash
# Prompt for domain models generation
claude-flow execute \
  --namespace healthcare-platform \
  --task "generate-domain-models" \
  --context "tech-spec,adr-005,adr-011" \
  --output-dir "platform/shared/domain" \
  --prompt "
Generate complete domain model layer for Healthcare Orchestration Platform:

REQUIREMENTS:
- FHIR R4 alignment (ADR-005: HAPI FHIR canonical store)
- LGPD compliance (ADR-011: data minimization, PII handling)
- Multi-tenant support (tenant_id in all entities)
- Value objects (Money, CPF, CNS, Insurance Card, etc.)
- Brazilian healthcare specifics (ANS, TISS, CBHPM codes)

STRUCTURE:
1. entities/ - Core business entities (Patient, Encounter, Procedure, etc.)
2. value_objects/ - Immutable value objects (Money, CodedValue, etc.)
3. events/ - Domain events for CDC (PatientRegistered, BillingCompleted, etc.)
4. exceptions/ - Domain-specific exceptions with BPMN error codes
5. enums/ - Enumerations (CoverageStatus, BillingStatus, etc.)

REFERENCE:
- Technical Spec: Section 2 (Hospital Digital Model)
- Technical Spec: Section 4 (Data Model - FHIR Resources)
- ADR-005: HAPI FHIR R4 canonical store
- ADR-011: LGPD history TTL variable by reference
- Legacy: Legacy processes/workers/camunda8-implementation/shared/domain/

OUTPUT: Python files with Pydantic models, type hints, comprehensive docstrings
"
```

### Step 1.2: Generate Integration Clients
```bash
# Prompt for integration clients
claude-flow execute \
  --namespace healthcare-platform \
  --task "generate-integration-clients" \
  --context "tech-spec,adr-004,adr-005,adr-006" \
  --output-dir "platform/shared/integrations" \
  --prompt "
Generate integration client layer for external systems:

REQUIREMENTS:
- No direct ERP queries (ADR-004: CDC only)
- FHIR transformations (ADR-005: canonical FHIR store)
- REST-only, no Kafka (ADR-006: REST bridge)
- Multi-tenant credentials via TenantContext
- Circuit breaker, retry, timeout patterns
- Rate limiting per tenant
- Structured logging with tenant_id

CLIENTS TO GENERATE:
1. tasy_client.py - Hospital AUSTA Tasy ERP (via CDC events)
2. mv_soul_client.py - AMH units MV Soul ERP (via CDC events)
3. ans_client.py - ANS (Agência Nacional de Saúde) APIs
4. tiss_client.py - TISS XML generation and submission
5. lis_client.py - Laboratory Information System
6. pacs_client.py - Picture Archiving and Communication System
7. whatsapp_client.py - WhatsApp Business API
8. insurance_api_client.py - Insurance eligibility verification (multi-payer)
9. fhir_client.py - HAPI FHIR server operations

EACH CLIENT MUST INCLUDE:
- Protocol/ABC definition
- Production implementation
- Stub implementation for testing
- Async/await pattern
- Error handling with custom exceptions
- Metrics collection (track_api_call decorator)
- LGPD-compliant logging (no PII in logs)

REFERENCE:
- Technical Spec: Section 3.3 (Integration Architecture)
- ADR-004: Debezium CDC ERP integration
- ADR-005: HAPI FHIR R4 canonical store
- ADR-006: Kafka REST bridge only
- Legacy: Legacy processes/workers/camunda8-implementation/shared/integrations/
"
```

### Step 1.3: Generate Multi-Tenancy Infrastructure
```bash
# Prompt for multi-tenancy layer
claude-flow execute \
  --namespace healthcare-platform \
  --task "generate-multi-tenancy" \
  --context "tech-spec,adr-002,adr-007,adr-008" \
  --output-dir "platform/shared/multi_tenant" \
  --prompt "
Generate multi-tenancy infrastructure layer:

REQUIREMENTS:
- Single engine, tenant markers (ADR-002)
- Tenant-specific business rules (ADR-007: DMN federation)
- OAuth2 per tenant (ADR-008: Keycloak)
- Thread-local tenant context
- Tenant-specific database connections
- Tenant-specific API credentials
- Tenant-specific DMN overrides

TENANTS:
- Hospital AUSTA (Tasy ERP, São Paulo)
- AMH São Paulo (MV Soul ERP)
- AMH Rio de Janeiro (MV Soul ERP)
- AMH Minas Gerais (MV Soul ERP)

FILES TO GENERATE:
1. context.py - TenantContext thread-local storage
2. database.py - TenantDatabaseManager (connection pooling per tenant)
3. credentials.py - TenantCredentialManager (vault integration)
4. configuration.py - TenantConfigurationManager (DMN overrides, feature flags)
5. middleware.py - FastAPI middleware for tenant extraction
6. decorators.py - @require_tenant, @with_tenant_context

REFERENCE:
- Technical Spec: Section 2.1 (Multi-tenant federation)
- ADR-002: Single engine tenant markers
- ADR-007: DMN federation tenant overrides
- ADR-008: Keycloak OAuth2 workers
- Legacy: Legacy processes/workers/camunda8-implementation/shared/multi_tenant/
"
```

### Step 1.4: Generate Observability Stack
```bash
# Prompt for observability infrastructure
claude-flow execute \
  --namespace healthcare-platform \
  --task "generate-observability" \
  --context "tech-spec,adr-010,adr-011" \
  --output-dir "platform/shared/observability" \
  --prompt "
Generate observability infrastructure (logging, metrics, tracing):

REQUIREMENTS:
- Structured logging (ADR-010: OpenTelemetry)
- LGPD-compliant (ADR-011: PII redaction)
- Prometheus metrics
- Jaeger tracing
- Multi-tenant context in all logs
- Process instance correlation

FILES TO GENERATE:
1. logging.py - Structured logger with PII redaction
2. metrics.py - Prometheus metrics collectors (@track_task_execution, @track_api_call)
3. tracing.py - OpenTelemetry tracer configuration
4. redaction.py - PII redaction rules (CPF, email, phone, patient names)
5. correlation.py - Process instance and task correlation
6. health.py - Health check endpoints

REFERENCE:
- Technical Spec: Section 3.5 (Observability)
- ADR-010: Observability stack
- ADR-011: LGPD history TTL variable by reference
- Legacy: Legacy processes/workers/camunda8-implementation/shared/observability/
"
```

---

## 🚀 Phase 2: Revenue Cycle Domain (Parallel Swarm Execution)

**Why Parallel:** Revenue cycle subprocesses are independent and can be generated simultaneously.

### Step 2.1: Spawn Revenue Cycle Swarm
```bash
# Create swarm configuration for revenue cycle domain
cat > .claude-flow/swarm-revenue-cycle.yaml << 'EOF'
swarm:
  name: revenue-cycle-generation
  namespace: healthcare-platform
  strategy: parallel
  coordination: shared-memory
  max-concurrent: 8
  
  shared_context:
    - tech-spec
    - adr-001
    - adr-003
    - adr-006
    - migration-template
    - migration-example
    - migration-comparison
  
  tasks:
    # Subprocess 15: Capture Clinical Production
    - id: capture-production
      worker_count: 8
      output_dir: platform/workers/revenue_cycle/production
      bpmn_output: platform/bpmn/revenue_cycle/SUB_04_Clinical_Production.bpmn
      prompt: |
        Generate BPMN process and workers for Subprocess 15: Capture Clinical Production
        
        SUBPROCESS OVERVIEW:
        - Captures all clinical consumption and production events
        - Real-time CDI (Clinical Documentation Improvement)
        - Validates completeness for billing
        
        WORKERS TO GENERATE (8):
        1. capture_production_worker.py - Listen to CDC events, create production records
        2. validate_completeness_worker.py - Check documentation completeness
        3. enrich_production_worker.py - Add CBHPM codes, prices from contracts
        4. identify_missing_docs_worker.py - Flag incomplete records
        5. alert_cdi_team_worker.py - Notify CDI team of missing documentation
        6. reconcile_production_worker.py - Match ERP production with FHIR records
        7. calculate_expected_revenue_worker.py - Estimate revenue from production
        8. flag_documentation_risks_worker.py - Identify high-risk incomplete records
        
        BPMN REQUIREMENTS:
        - Start: CDC event (MedicationAdministered, ProcedurePerformed, etc.)
        - Service tasks for each worker
        - Error boundary events for missing documentation
        - Timer for SLA monitoring (documentation within 24h)
        - Multi-instance for batch processing
        
        REFERENCE:
        - Tech Spec: Section 2.3 Stage 2 (Clinical Production Capture)
        - Tech Spec: Section 5.1 Subprocess 15
        - Migration Template: CIB7_WORKER_TEMPLATE.md
        - Legacy: Legacy processes/workers/camunda8-implementation/revenue-cycle/production/

    - id: coding-audit
      worker_count: 10
      output_dir: platform/workers/revenue_cycle/coding
      bpmn_output: platform/bpmn/revenue_cycle/SUB_05_Coding_Audit.bpmn
      prompt: |
        Generate BPMN process and workers for Subprocess 17: Coding & Billing
        
        SUBPROCESS OVERVIEW:
        - AI-assisted ICD-10, CBHPM coding
        - Automated audit rules (ANS, TISS compliance)
        - Human-in-the-loop for complex cases
        
        WORKERS TO GENERATE (10):
        1. assign_icd10_codes_worker.py - AI-based ICD-10 code assignment
        2. assign_cbhpm_codes_worker.py - CBHPM procedure code assignment
        3. apply_audit_rules_worker.py - Execute DMN audit rules
        4. check_coding_compliance_worker.py - ANS/TISS compliance validation
        5. validate_completeness_worker.py - Check all required codes present
        6. calculate_quality_score_worker.py - Coding accuracy score
        7. identify_fraud_patterns_worker.py - Fraud detection ML model
        8. route_to_human_auditor_worker.py - Complex cases to human review
        9. apply_coder_feedback_worker.py - Incorporate manual corrections
        10. finalize_coding_worker.py - Mark coding complete, ready for billing
        
        BPMN REQUIREMENTS:
        - Start: Production capture complete
        - DMN decision tables for audit rules (tenant-specific overrides)
        - User tasks for human auditor review
        - Error boundaries for compliance failures
        - Embedded subprocess for AI coding retry logic
        
        REFERENCE:
        - Tech Spec: Section 2.3 Stage 3 (Coding/Auditing)
        - Tech Spec: Section 5.1 Subprocess 17
        - ADR-007: DMN federation tenant overrides

    - id: billing-submission
      worker_count: 13
      output_dir: platform/workers/revenue_cycle/billing
      bpmn_output: platform/bpmn/revenue_cycle/SUB_06_Billing_Submission.bpmn
      prompt: |
        Generate BPMN process and workers for Billing & Submission
        
        SUBPROCESS OVERVIEW:
        - Generate TISS XML (ANS standard)
        - Apply contract rules per payer
        - Submit to payer portals
        - Track submission status
        
        WORKERS TO GENERATE (13):
        1. validate_eligibility_worker.py - Verify patient insurance (ALREADY EXISTS - USE AS REFERENCE)
        2. generate_tiss_xml_worker.py - Create TISS 4.0 XML
        3. apply_contract_rules_worker.py - Apply payer-specific rules (DMN)
        4. consolidate_charges_worker.py - Group procedures per billing rules
        5. calculate_copay_worker.py - Patient copay/coinsurance calculation
        6. submit_claim_worker.py - Submit to payer API/portal
        7. check_idempotency_worker.py - Prevent duplicate submissions
        8. apply_corrections_worker.py - Resubmit with corrections
        9. track_submission_status_worker.py - Poll payer APIs for status
        10. handle_submission_errors_worker.py - Retry logic, error notifications
        11. generate_patient_bill_worker.py - Patient-facing invoice
        12. send_bill_notification_worker.py - Email/SMS bill notification
        13. archive_billing_documents_worker.py - S3 storage for audit
        
        BPMN REQUIREMENTS:
        - Conditional flows based on payer type (AUSTA Saúde vs external)
        - Integration with insurance APIs (eligibility, submission)
        - Idempotency checks (message correlation)
        - Multi-instance for batch submissions
        
        REFERENCE:
        - Tech Spec: Section 2.3 Stage 4-6 (Billing submission)
        - EXAMPLE: EXAMPLE_MIGRATION_validate_eligibility_worker.py

    - id: glosa-management
      worker_count: 10
      output_dir: platform/workers/revenue_cycle/glosa
      bpmn_output: platform/bpmn/revenue_cycle/SUB_07_Denials_Management.bpmn
      prompt: |
        Generate BPMN process and workers for Glosa (Denials) Management
        
        SUBPROCESS OVERVIEW:
        - Identify denials from payer responses
        - Root cause analysis
        - Automated corrections
        - Appeal generation
        
        WORKERS TO GENERATE (10):
        1. identify_glosa_worker.py - Detect denials in payer responses
        2. classify_glosa_worker.py - Categorize denial reason
        3. analyze_glosa_worker.py - Root cause analysis (ML model)
        4. search_glosa_evidence_worker.py - Find supporting documentation
        5. apply_glosa_corrections_worker.py - Auto-correct coding errors
        6. generate_appeal_worker.py - Create appeal document
        7. register_appeal_worker.py - Submit appeal to payer
        8. track_appeal_status_worker.py - Monitor appeal progress
        9. create_glosa_provision_worker.py - Accounting provision for loss
        10. register_recovery_worker.py - Record successful appeal recovery
        
        BPMN REQUIREMENTS:
        - Message correlation (denial notification from payer)
        - Decision tables for auto-correction eligibility
        - Human task for complex appeals
        - Timer for appeal deadlines (ANS regulations)
        
        REFERENCE:
        - Tech Spec: Section 2.3 Stage 7 (Glosa Management)
        - Tech Spec: Problem Statement (8-12% denial rates)

    - id: payment-collection
      worker_count: 48
      output_dir: platform/workers/revenue_cycle/collection
      bpmn_output: platform/bpmn/revenue_cycle/SUB_08_Revenue_Collection.bpmn
      prompt: |
        Generate BPMN process and workers for Payment Collection
        
        SUBPROCESS OVERVIEW:
        - Process payer payments
        - Allocate to invoices
        - Reconciliation
        - Patient collections
        
        WORKERS TO GENERATE (48):
        [Payment Processing - 8 workers]
        1. process_payment_worker.py - Receive payment from payer
        2. validate_payment_worker.py - Check payment amount, date
        3. allocate_payment_worker.py - Match to invoices
        4. reconcile_payment_worker.py - Close/partial close invoices
        5. register_write_off_worker.py - Write off uncollectable
        6. refer_to_legal_worker.py - Legal collection for large debts
        7. send_payment_reminder_worker.py - Email/SMS reminders
        8. negotiate_payment_plan_worker.py - Installment plans
        
        [Compensation Handlers - 40 workers]
        9-48. [Generate compensation/rollback handlers for each payment operation]
        
        BPMN REQUIREMENTS:
        - SAGA pattern for payment allocation (compensation)
        - Message events for payment notifications
        - Escalation for collection failures
        - Multi-instance parallel for batch processing
        
        REFERENCE:
        - Tech Spec: Section 2.3 Stage 8-9 (Collection)
        - Legacy: 48 collection workers in camunda8-implementation

EOF

# Execute swarm
claude-flow swarm spawn \
  --config .claude-flow/swarm-revenue-cycle.yaml \
  --monitor \
  --report-interval 30s \
  --output-report .claude-flow/swarm-revenue-cycle-report.json
```

---

## 🏥 Phase 3: Clinical Operations Domain (Parallel Swarm Execution)

### Step 3.1: Spawn Clinical Operations Swarm
```bash
cat > .claude-flow/swarm-clinical-operations.yaml << 'EOF'
swarm:
  name: clinical-operations-generation
  namespace: healthcare-platform
  strategy: parallel
  coordination: shared-memory
  max-concurrent: 6
  
  shared_context:
    - tech-spec
    - adr-003
    - adr-005
    - migration-template
  
  tasks:
    - id: triage-routing
      worker_count: 5
      output_dir: platform/workers/clinical/triage
      bpmn_output: platform/bpmn/clinical/SUB_03_Atendimento_Clinico.bpmn
      prompt: |
        Generate BPMN and workers for Clinical Triage & Routing
        
        OVERVIEW:
        - Manchester Triage Protocol
        - Risk stratification
        - Care team allocation
        - Sepsis screening
        
        WORKERS (5):
        1. execute_triage_worker.py - Manchester protocol execution
        2. calculate_risk_score_worker.py - MEWS, NEWS2 scores
        3. screen_sepsis_worker.py - Sepsis detection (ML model)
        4. allocate_care_team_worker.py - Assign physicians, nurses
        5. alert_clinical_team_worker.py - Urgent alerts (sepsis, stroke)

    - id: clinical-documentation
      worker_count: 13
      output_dir: platform/workers/clinical/documentation
      bpmn_output: platform/bpmn/clinical/SUB_03_Clinical_Documentation.bpmn
      prompt: |
        Generate BPMN and workers for Clinical Documentation
        
        OVERVIEW:
        - FHIR data synchronization
        - LIS/PACS integration
        - Encounter registration
        - Procedure recording
        
        WORKERS (13):
        1. sync_fhir_data_worker.py - Sync ERP to FHIR
        2. integrate_lis_worker.py - Lab results integration
        3. integrate_pacs_worker.py - Medical imaging integration
        4. register_encounter_worker.py - Create encounter record
        5. record_procedure_worker.py - Document procedure
        6. capture_vital_signs_worker.py - Vital signs from devices
        7. update_patient_summary_worker.py - Update clinical summary
        8. generate_discharge_summary_worker.py - Discharge documentation
        9. notify_follow_up_worker.py - Post-discharge follow-up
        10. validate_documentation_completeness_worker.py - Check required fields
        11. schedule_appointment_worker.py - Book appointments
        12. confirm_appointment_worker.py - Appointment confirmation
        13. reschedule_appointment_worker.py - Reschedule logic

    - id: clinical-alerts
      worker_count: 2
      output_dir: platform/workers/clinical/alerts
      bpmn_output: platform/bpmn/clinical/SUB_Clinical_Alerts.bpmn
      prompt: |
        Generate BPMN and workers for Clinical Alerts
        
        WORKERS (2):
        1. create_alert_worker.py - Generate clinical alerts
        2. trigger_clinical_event_worker.py - Trigger alert workflows

EOF

claude-flow swarm spawn \
  --config .claude-flow/swarm-clinical-operations.yaml \
  --monitor \
  --output-report .claude-flow/swarm-clinical-report.json
```

---

## 👥 Phase 4: Patient Access Domain (Parallel Swarm Execution)

### Step 4.1: Spawn Patient Access Swarm
```bash
cat > .claude-flow/swarm-patient-access.yaml << 'EOF'
swarm:
  name: patient-access-generation
  namespace: healthcare-platform
  strategy: parallel
  coordination: shared-memory
  max-concurrent: 4
  
  tasks:
    - id: scheduling-registration
      worker_count: 15
      output_dir: platform/workers/patient_access/scheduling
      bpmn_output: platform/bpmn/patient_access/SUB_01_Agendamento_Registro.bpmn
      prompt: |
        Generate scheduling and registration BPMN and workers

    - id: pre-attendance
      worker_count: 8
      output_dir: platform/workers/patient_access/pre_attendance
      bpmn_output: platform/bpmn/patient_access/SUB_02_Pre_Atendimento.bpmn
      prompt: |
        Generate pre-attendance BPMN and workers (clearance, intake)

    - id: messaging-notifications
      worker_count: 8
      output_dir: platform/workers/shared/messaging
      bpmn_output: platform/bpmn/shared/Messaging_Orchestration.bpmn
      prompt: |
        Generate messaging orchestration (WhatsApp, SMS, Email)

EOF

claude-flow swarm spawn \
  --config .claude-flow/swarm-patient-access.yaml \
  --monitor \
  --output-report .claude-flow/swarm-patient-access-report.json
```

---

## 🔧 Phase 5: Platform Services Domain (Parallel Swarm Execution)

### Step 5.1: Spawn Platform Services Swarm
```bash
cat > .claude-flow/swarm-platform-services.yaml << 'EOF'
swarm:
  name: platform-services-generation
  namespace: healthcare-platform
  strategy: parallel
  coordination: shared-memory
  max-concurrent: 5
  
  tasks:
    - id: analytics-processing
      worker_count: 12
      output_dir: platform/workers/shared/analytics
      bpmn_output: platform/bpmn/analytics/Analytics_Processing.bpmn
      prompt: |
        Generate analytics workers (ML models, process mining, KPIs)

    - id: dmn-rules-engine
      worker_count: 4
      output_dir: platform/workers/shared/rules
      bpmn_output: platform/dmn/
      prompt: |
        Generate DMN decision tables and rules engine workers

    - id: services-layer
      worker_count: 13
      output_dir: platform/shared/services
      prompt: |
        Generate shared services (accounting, contracts, pricing, etc.)

    - id: validators-middleware
      worker_count: 4
      output_dir: platform/shared/validators
      prompt: |
        Generate validators and middleware components

EOF

claude-flow swarm spawn \
  --config .claude-flow/swarm-platform-services.yaml \
  --monitor \
  --output-report .claude-flow/swarm-platform-services-report.json
```

---

## 📊 Phase 6: DMN Decision Tables (Specialized Swarm)

### Step 6.1: Generate Federated DMN Tables
```bash
# DMN generation requires specialized prompting
claude-flow execute \
  --namespace healthcare-platform \
  --task "generate-dmn-federation" \
  --context "tech-spec,adr-007" \
  --output-dir "platform/dmn" \
  --prompt "
Generate federated DMN decision tables with tenant overrides:

REQUIREMENTS:
- Base DMN tables (global rules)
- Tenant-specific override DMN tables
- DMN federation service to merge base + overrides
- Version control for DMN tables
- Test cases for each decision

DMN TABLES TO GENERATE (50+):

[Billing Rules - 15 tables]
1. Billing_Calculation.dmn - Base billing calculation rules
2. Billing_Calculation_AUSTA.dmn - AUSTA-specific overrides
3. Billing_Calculation_AMH_SP.dmn - AMH São Paulo overrides
4. Contract_Rules_Bradesco.dmn - Bradesco contract rules
5. Contract_Rules_Unimed.dmn - Unimed contract rules
6. Contract_Rules_SulAmerica.dmn - SulAmérica contract rules
7. Contract_Rules_Amil.dmn - Amil contract rules
8. Copay_Calculation.dmn - Patient copay rules
9. Authorization_Required.dmn - Prior authorization requirements
10. Bundled_Services.dmn - Service bundling rules
11-15. [Additional payer-specific tables]

[Coding/Audit Rules - 10 tables]
16. ICD10_Validation.dmn - ICD-10 code validation rules
17. CBHPM_Mapping.dmn - CBHPM procedure mapping
18. Documentation_Requirements.dmn - Required documentation per procedure
19. Audit_Flags.dmn - Conditions triggering manual audit
20. Fraud_Indicators.dmn - Fraud detection decision table
21-25. [Additional audit tables]

[Clinical Rules - 10 tables]
26. Triage_Priority.dmn - Manchester triage decision table
27. Sepsis_Risk.dmn - Sepsis screening criteria
28. ICU_Admission.dmn - ICU admission criteria
29. Discharge_Readiness.dmn - Patient discharge criteria
30. Medication_Interaction.dmn - Drug interaction checks
31-35. [Additional clinical tables]

[Glosa Prevention - 10 tables]
36. Glosa_Risk_Score.dmn - Denial risk calculation
37. Auto_Correction_Eligible.dmn - Can denial be auto-corrected?
38. Appeal_Viability.dmn - Should we appeal?
39. Documentation_Gap.dmn - Missing documentation identification
40-45. [Additional glosa tables]

[Authorization/Access Control - 5 tables]
46. User_Permissions.dmn - Role-based access control
47. Data_Access_Policy.dmn - LGPD data access rules
48. Workflow_Routing.dmn - Task assignment rules
49-50. [Additional access tables]

REFERENCE:
- Tech Spec: Section 4.3 (Decision Management)
- ADR-007: DMN federation tenant overrides
- Legacy: Legacy processes/dmn/
"
```

---

## 🧪 Phase 7: Testing Infrastructure (Parallel Generation)

### Step 7.1: Generate Test Suites
```bash
# Spawn test generation swarm
claude-flow swarm spawn \
  --config .claude-flow/swarm-testing.yaml \
  --parallel-workers 10 \
  --prompt "
For each worker generated in phases 2-5:

GENERATE COMPREHENSIVE TEST SUITE:

1. Unit Tests (tests/unit/workers/[domain]/test_[worker].py)
   - Mock external services
   - Test all business logic paths
   - Test error handling
   - Test BPMN error codes
   - Test multi-tenancy

2. Integration Tests (tests/integration/workers/[domain]/test_[worker]_integration.py)
   - Test with stub services
   - Test CIB7 engine integration
   - Test variable passing
   - Test idempotency

3. Contract Tests (tests/contract/[integration]/test_[api]_contract.py)
   - Test external API contracts
   - Pact/OpenAPI validation

4. E2E Tests (tests/e2e/journeys/test_[journey]_e2e.py)
   - Test complete patient journeys
   - Test cross-domain workflows

REFERENCE:
- Migration Template: Testing section
- Legacy tests: Legacy processes/workers/camunda8-implementation/tests/
"
```

---

## 📦 Phase 8: Configuration & Deployment (Serial)

### Step 8.1: Generate Configuration Files
```bash
# Generate deployment configurations
claude-flow execute \
  --namespace healthcare-platform \
  --task "generate-deployment-config" \
  --output-dir "platform/config" \
  --prompt "
Generate complete deployment configuration:

FILES TO GENERATE:

1. requirements.txt - Python dependencies with pinned versions
2. pyproject.toml - Poetry/PDM project configuration
3. Dockerfile - Multi-stage Docker build
4. docker-compose.yml - Local development environment
5. kubernetes/ - K8s manifests (deployments, services, configmaps)
6. helm/ - Helm charts for production deployment
7. .env.example - Environment variables template
8. settings.py - Pydantic settings management
9. logging.yaml - Logging configuration
10. prometheus.yml - Metrics configuration
11. jaeger.yml - Tracing configuration
12. nginx.conf - Reverse proxy configuration

REFERENCE:
- Tech Spec: Section 3.4 (Deployment Architecture)
- ADR-012: Engine replicas phased
"
```

### Step 8.2: Generate Documentation
```bash
# Generate comprehensive documentation
claude-flow execute \
  --namespace healthcare-platform \
  --task "generate-documentation" \
  --output-dir "docs" \
  --prompt "
Generate complete project documentation:

1. README.md - Project overview, quick start
2. ARCHITECTURE.md - System architecture diagram, component descriptions
3. DEPLOYMENT.md - Deployment instructions (dev, staging, prod)
4. API.md - API documentation (OpenAPI/Swagger)
5. WORKERS.md - Worker catalog with descriptions
6. TESTING.md - Testing strategy and instructions
7. TROUBLESHOOTING.md - Common issues and solutions
8. CONTRIBUTING.md - Development guidelines
9. CHANGELOG.md - Version history
10. RUNBOOK.md - Operations runbook

Include:
- Mermaid diagrams for architecture
- Code examples
- Configuration samples
- Troubleshooting decision trees
"
```

---

## 🎯 Phase 9: Validation & Quality Assurance (Automated)

### Step 9.1: Run Automated Validation
```bash
# Validate generated code
claude-flow validate \
  --namespace healthcare-platform \
  --directory platform/ \
  --checks "
    - syntax: Python syntax validation
    - imports: All imports resolvable
    - types: Type checking with mypy
    - lint: Flake8, Black formatting
    - security: Bandit security scan
    - complexity: Cyclomatic complexity < 10
    - coverage: Test coverage > 80%
    - documentation: All public APIs documented
  " \
  --output-report .claude-flow/validation-report.json
```

### Step 9.2: Generate Gap Analysis
```bash
# Compare generated code vs technical spec
claude-flow analyze \
  --namespace healthcare-platform \
  --source "docs/Technical specification/technical-specification.md" \
  --generated platform/ \
  --output-gap-analysis .claude-flow/gap-analysis.md \
  --prompt "
Compare technical specification requirements vs generated code:

ANALYZE:
1. Are all 29 subprocesses implemented?
2. Are all BPMN processes complete?
3. Are all workers present?
4. Are all integrations implemented?
5. Are all ADRs followed?
6. Are all FHIR resources handled?
7. Is multi-tenancy implemented correctly?
8. Is LGPD compliance implemented?

OUTPUT:
- Checklist of requirements (✓ complete, ⚠ partial, ✗ missing)
- List of missing components
- List of non-compliant implementations
- Prioritized remediation plan
"
```

---

## 📈 Phase 10: Monitoring & Reporting

### Step 10.1: Generate Execution Report
```bash
# Consolidate all swarm reports
claude-flow report consolidate \
  --reports .claude-flow/swarm-*-report.json \
  --output .claude-flow/FINAL_GENERATION_REPORT.md \
  --format markdown \
  --include "
    - Total files generated
    - Total lines of code
    - Success rate per domain
    - Failed tasks (with reasons)
    - Execution time per phase
    - Resource usage (CPU, memory)
    - Code quality metrics
    - Test coverage statistics
    - Gap analysis summary
  "
```

### Step 10.2: Generate Code Statistics
```bash
# Analyze generated codebase
cloc platform/ --by-file --json --out .claude-flow/code-stats.json

# Generate visual reports
claude-flow visualize \
  --input .claude-flow/code-stats.json \
  --output .claude-flow/code-visualization.html \
  --charts "
    - Files by domain (pie chart)
    - Lines of code by language (bar chart)
    - Workers per subprocess (heatmap)
    - Code quality trends (line chart)
    - Test coverage by domain (radar chart)
  "
```

---

## 🔄 Recovery & Retry Strategy

### Handling Failures

```bash
# If a swarm task fails, retry individual task
claude-flow swarm retry \
  --task-id [failed-task-id] \
  --swarm-config .claude-flow/swarm-[domain].yaml \
  --max-retries 3 \
  --backoff exponential

# If entire swarm fails, checkpoint and resume
claude-flow swarm resume \
  --checkpoint .claude-flow/swarm-[domain]-checkpoint.json \
  --skip-completed
```

---

## 📊 Expected Outputs

### File Structure
```
platform/
├── bpmn/                           # 29 BPMN files (~500KB)
│   ├── revenue_cycle/
│   │   ├── SUB_04_Clinical_Production.bpmn
│   │   ├── SUB_05_Coding_Audit.bpmn
│   │   ├── SUB_06_Billing_Submission.bpmn
│   │   ├── SUB_07_Denials_Management.bpmn
│   │   └── SUB_08_Revenue_Collection.bpmn
│   ├── clinical/
│   │   ├── SUB_03_Atendimento_Clinico.bpmn
│   │   └── SUB_03_Clinical_Documentation.bpmn
│   ├── patient_access/
│   │   ├── SUB_01_Agendamento_Registro.bpmn
│   │   └── SUB_02_Pre_Atendimento.bpmn
│   └── platform/
│       └── Analytics_Processing.bpmn
│
├── dmn/                            # 50+ DMN files (~200KB)
│   ├── billing/
│   ├── coding/
│   ├── clinical/
│   └── glosa/
│
├── workers/                        # 185+ workers (~500KB)
│   ├── revenue_cycle/
│   │   ├── production/ (8 workers)
│   │   ├── coding/ (10 workers)
│   │   ├── billing/ (13 workers)
│   │   ├── glosa/ (10 workers)
│   │   └── collection/ (48 workers)
│   ├── clinical/
│   │   ├── triage/ (5 workers)
│   │   ├── documentation/ (13 workers)
│   │   └── alerts/ (2 workers)
│   ├── patient_access/
│   │   ├── scheduling/ (15 workers)
│   │   └── pre_attendance/ (8 workers)
│   └── platform/
│       ├── analytics/ (12 workers)
│       └── messaging/ (8 workers)
│
├── shared/                         # Infrastructure (~150KB)
│   ├── domain/
│   ├── integrations/
│   ├── multi_tenant/
│   ├── observability/
│   ├── services/
│   ├── validators/
│   └── middleware/
│
├── tests/                          # Test suites (~300KB)
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── e2e/
│
├── config/                         # Configuration (~20KB)
│   ├── kubernetes/
│   ├── helm/
│   └── settings/
│
└── docs/                           # Documentation (~50KB)
    ├── ARCHITECTURE.md
    ├── API.md
    └── RUNBOOK.md

Total Estimated: 500,000+ lines of code
```

---

## ⚠️ Critical Considerations

### Before Execution:

1. **Resource Requirements**
   - **CPU:** 8+ cores recommended for parallel swarms
   - **Memory:** 32GB+ RAM (swarms can be memory-intensive)
   - **Disk:** 10GB+ free space for generated code
   - **Network:** Stable internet for MCP server communication

2. **Time Estimates**
   - Phase 0 (Memory prep): 10 minutes
   - Phase 1 (Infrastructure): 30-45 minutes
   - Phase 2 (Revenue cycle): 2-3 hours (parallel)
   - Phase 3 (Clinical): 1-2 hours (parallel)
   - Phase 4 (Patient access): 1-2 hours (parallel)
   - Phase 5 (Platform): 1-2 hours (parallel)
   - Phase 6 (DMN): 30-45 minutes
   - Phase 7 (Testing): 2-3 hours (parallel)
   - Phase 8 (Config/docs): 30 minutes
   - Phase 9 (Validation): 15-30 minutes
   - **Total: 8-12 hours** (with parallel execution)

3. **Cost Considerations**
   - Claude API usage (extensive token consumption)
   - Monitor token usage during execution
   - Consider batching or phased execution over multiple days

4. **Quality Assurance**
   - Manual review required after each phase
   - Code review before production deployment
   - Integration testing with actual CIB7 engine
   - Load testing for worker performance

5. **Rollback Plan**
   - Git commit after each successful phase
   - Tag major milestones
   - Keep swarm checkpoints for resume capability

---

## 🚀 Execution Commands Summary

```bash
# PHASE 0: Preparation (10 min)
claude-flow memory store --namespace healthcare-platform --key tech-spec --file "docs/Technical specification/technical-specification.md"
for adr in docs/ADRs/*.md; do claude-flow memory store --namespace healthcare-platform --key "adr-$(basename $adr .md)" --file "$adr"; done
claude-flow memory store --namespace healthcare-platform --key migration-template --file "docs/Technical specification/CIB7_WORKER_TEMPLATE.md"
claude-flow learn --from-directory "Legacy processes/workers/camunda8-implementation" --namespace healthcare-platform

# PHASE 1: Infrastructure (45 min)
claude-flow execute --task generate-domain-models --output-dir platform/shared/domain [detailed prompt]
claude-flow execute --task generate-integration-clients --output-dir platform/shared/integrations [detailed prompt]
claude-flow execute --task generate-multi-tenancy --output-dir platform/shared/multi_tenant [detailed prompt]
claude-flow execute --task generate-observability --output-dir platform/shared/observability [detailed prompt]

# PHASE 2-5: Domain Swarms (6-8 hours, parallel)
claude-flow swarm spawn --config .claude-flow/swarm-revenue-cycle.yaml --monitor
claude-flow swarm spawn --config .claude-flow/swarm-clinical-operations.yaml --monitor
claude-flow swarm spawn --config .claude-flow/swarm-patient-access.yaml --monitor
claude-flow swarm spawn --config .claude-flow/swarm-platform-services.yaml --monitor

# PHASE 6: DMN (45 min)
claude-flow execute --task generate-dmn-federation --output-dir platform/dmn [detailed prompt]

# PHASE 7: Testing (3 hours, parallel)
claude-flow swarm spawn --config .claude-flow/swarm-testing.yaml --parallel-workers 10

# PHASE 8: Config & Docs (30 min)
claude-flow execute --task generate-deployment-config --output-dir platform/config [detailed prompt]
claude-flow execute --task generate-documentation --output-dir docs [detailed prompt]

# PHASE 9: Validation (30 min)
claude-flow validate --directory platform/ --output-report .claude-flow/validation-report.json
claude-flow analyze --source "docs/Technical specification/technical-specification.md" --generated platform/

# PHASE 10: Reporting
claude-flow report consolidate --reports .claude-flow/swarm-*-report.json --output .claude-flow/FINAL_GENERATION_REPORT.md
```

---

## 📝 Next Steps (After Generation)

1. **Manual Review**
   - Review generated BPMN processes in Camunda Modeler
   - Review worker code for business logic accuracy
   - Review DMN tables for rule correctness

2. **Integration Testing**
   - Deploy CIB7 engine locally
   - Deploy generated workers
   - Test end-to-end workflows

3. **Refinement**
   - Fix any validation errors
   - Add missing business logic
   - Optimize performance bottlenecks

4. **Documentation**
   - Complete API documentation
   - Add inline code comments
   - Create operator runbook

5. **Deployment**
   - Deploy to staging environment
   - Run acceptance tests
   - Deploy to production (phased rollout per ADR-012)

---

## ✅ Success Criteria

Generation is successful when:

- ✅ All 29 BPMN processes generated
- ✅ All 185+ workers generated
- ✅ All 50+ DMN tables generated
- ✅ All shared infrastructure generated
- ✅ All tests generated (>80% coverage)
- ✅ All configuration files generated
- ✅ All documentation generated
- ✅ Zero validation errors
- ✅ Gap analysis shows 100% coverage
- ✅ Code passes security scan
- ✅ All ADRs followed

---

**STATUS:** Planning Complete - Ready for Execution  
**NEXT ACTION:** Review this strategy, get approval, then execute Phase 0

---

Generated: 2026-02-09  
Strategy: Parallel Swarm Execution with Shared Memory Coordination  
Estimated LOC: 500,000+  
Estimated Time: 8-12 hours (parallel execution)
