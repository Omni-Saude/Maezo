# Brazilian Healthcare Regulatory Research Summary

**Research Date**: 2026-01-12
**Researcher Agent**: swarm-1768209971907-lur8wwvxy
**Status**: ✅ COMPLETE

---

## Executive Summary

This document consolidates research on Brazilian healthcare regulatory requirements essential for business rules documentation and system compliance. The research covers **TISS 4.0**, **ANS Normative Resolutions**, **LGPD**, and **Domain-Driven Design patterns** for healthcare systems.

---

## 1. TISS 4.0 Standard (Padrão TISS)

### Overview
- **Current Version**: 4.01 (mandatory since 2024-12-31)
- **Next Version**: September 2025
- **Authority**: ANS (Agência Nacional de Saúde Suplementar)
- **Official Documentation**: https://www.gov.br/ans/pt-br

### Five Core Components

#### 1.1 Componente Organizacional
- **Purpose**: Establishes operational rules
- **Compliance**: Mandatory
- **Business Impact**: Defines workflow and process standards

#### 1.2 Componente de Conteúdo e Estrutura
- **Purpose**: Data architecture for electronic messages and contingency plans
- **Compliance**: Mandatory
- **Technical Requirements**: XML schema validation, data structure standardization

#### 1.3 Componente de Representação de Conceitos (TUSS)
- **Purpose**: Unified terminology for supplementary healthcare
- **Compliance**: Mandatory
- **Terminology Updates**:
  - 26,000+ OPME (Órteses, Próteses e Materiais Especiais) terms
  - 334 medication terms
- **Tables**: 19 (Materials/OPME), 20 (Medications), 64 (Submission formats)

#### 1.4 Componente de Segurança e Privacidade
- **Purpose**: Protection requirements for confidentiality and privacy
- **Compliance**: Mandatory
- **Integration**: LGPD-aligned
- **Key Requirements**:
  - Data encryption in transit and at rest
  - Access control and authentication
  - Audit trail implementation

#### 1.5 Componente de Comunicação
- **Purpose**: Electronic messaging methods
- **Compliance**: Mandatory
- **Technical Standards**:
  - XML format
  - WSDL specifications
  - Web services secure communication
  - Communication packages: 04.02.00 and 01.05.00

### Mandatory Fields (TISS 4.0)
All claims and transactions must include:
1. `unidade_medida` (unit of measure)
2. `codigo_despesa` (expense code)
3. `data_realizacao` (execution date)
4. `quantidade` (quantity)
5. `codigo_item_assistencial` (healthcare item code)

### Validation Requirements
- ✅ Test communication packages in test environment before production
- ✅ XML and WSDL standards compliance
- ✅ Web services secure communication verification
- ✅ Schema validation against ANS XSD files

---

## 2. ANS Normative Resolutions

### 2.1 RN 465/2021 - Rol de Procedimentos e Eventos em Saúde
- **Effective Date**: April 1, 2021
- **Status**: ✅ Active
- **Amendments**: RN 473/2021, RN 643/2025
- **Scope**: Comprehensive list of healthcare procedures and events covered by supplementary health insurance
- **Business Impact**: Defines which procedures are mandatory coverage

### 2.2 RN 395/2016
- **Title**: Operational standards for supplementary healthcare
- **Status**: ⚠️ Requires direct verification from ANS portal
- **Action**: Review full resolution text at https://www.ans.gov.br

### 2.3 RN 442/2018
- **Title**: ANS regulatory standards
- **Status**: ⚠️ Requires direct verification from ANS portal
- **Action**: Review full resolution text at https://www.ans.gov.br

---

## 3. LGPD (Lei Geral de Proteção de Dados)

### Overview
- **Law**: Lei No 13.709/2018
- **Authority**: ANPD (Autoridade Nacional de Proteção de Dados)
- **Effective Date**: September 18, 2020
- **Healthcare Applicability**: HIGH (sensitive health data)

### Sensitive Health Data Definition
Personal data relating to:
- Health conditions
- Sexual life
- Genetic data
- Biometric data (when linked to natural persons)

### Key Prohibitions
🚫 **Communication or shared use of sensitive health data between controllers for economic advantage**

### Access Control Requirements

#### Intra-Institutional Access
- **Rule**: Only individuals with professional secrecy obligations
- **Condition**: Must be involved in patient care
- **Audit**: High-level logging required

#### Inter-Institutional Access
- **Rule**: Written patient consent REQUIRED
- **Exception**: Legal obligations or public health emergencies
- **Audit**: High-level logging required

### Legal Basis for Health Data Processing
- Protection of health
- Proceedings performed by healthcare professionals or health entities
- Public health activities
- Scientific research (with specific safeguards per Resolution 738/2025)

### Penalties
- **Maximum Fine**: 2% of company revenue in Brazil
- **Cap**: R$ 50,000,000 (50 million reais)
- **Additional**: Daily fines, data processing suspension, data deletion orders

### ANPD Regulatory Agenda (2025-2026)
Priority topics for supervision and regulation:
1. **Data Protection Impact Assessments (DPIAs)**: Mandatory for high-risk processing
2. **Data sharing by government entities**: Public health data sharing protocols
3. **Minors' data processing**: Enhanced protections for children/adolescents
4. **Biometric data regulations**: Stricter controls on biometric processing
5. **Security measures**: Technical and organizational safeguards
6. **Artificial Intelligence**: AI processing transparency and accountability
7. **High-risk processing**: Additional safeguards for sensitive operations

### Recent Updates (2025)
- **Resolution 738/2025**: Regulates database use for scientific research involving human beings
- **Supervision Priorities (2026-2027)**: Topic map published for enforcement focus

---

## 4. Audit Trail Requirements

### Retention Periods

| Data Type | Retention Period | Legal Basis |
|-----------|------------------|-------------|
| Medical Records | 20 years minimum | CFM Resolution |
| Financial Transactions | 5 years | Brazilian Tax Law |
| LGPD Audit Logs | Per DPIA analysis | LGPD Art. 37 |
| Access Logs | 6 months minimum | ANPD Guidance |

### Mandatory Logging Fields

Every data access event MUST log:
1. **Who**: User identification (ID, name, role)
2. **When**: Timestamp (ISO 8601 format)
3. **What**: Resource type and ID (patient, claim, financial record)
4. **Where**: IP address and geographic location
5. **Why**: Justification for access
6. **Changes**: Before/after state (for modifications)
7. **Result**: Operation status (success, failure, denied)

### Audit Log Structure Example
```json
{
  "user_id": "12345",
  "user_name": "Dr. João Silva",
  "user_role": "physician",
  "timestamp": "2026-01-12T09:30:00Z",
  "action": "READ",
  "resource_type": "medical_record",
  "resource_id": "MR-789456",
  "ip_address": "192.168.1.100",
  "location": "São Paulo, SP",
  "justification": "Patient consultation appointment",
  "result": "SUCCESS"
}
```

---

## 5. Domain-Driven Design Patterns for Healthcare

### Recommended Bounded Contexts

#### 5.1 Patient Management Context
- **Aggregate Root**: Patient
- **Key Entities**: Patient, MedicalHistory, EmergencyContact
- **Domain Events**: PatientRegistered, PatientUpdated, MedicalHistoryAdded
- **Responsibility**: Patient registration, demographics, medical history

#### 5.2 Appointment Scheduling Context
- **Aggregate Root**: Appointment
- **Key Entities**: Appointment, Schedule, TimeSlot
- **Domain Events**: AppointmentScheduled, AppointmentRescheduled, AppointmentCancelled
- **Responsibility**: Appointment booking, rescheduling, cancellations

#### 5.3 Medical Records Context
- **Aggregate Root**: MedicalRecord
- **Key Entities**: MedicalRecord, Diagnosis, Treatment, Prescription
- **Domain Events**: RecordCreated, DiagnosisAdded, TreatmentPrescribed
- **Responsibility**: Clinical documentation, diagnoses, treatments

#### 5.4 Billing & Claims Context
- **Aggregate Root**: Claim
- **Key Entities**: Claim, Invoice, Payment, Glosa
- **Domain Events**: ClaimSubmitted, ClaimApproved, GlosaApplied, PaymentReceived
- **Responsibility**: Financial processing, insurance claims, TISS integration

#### 5.5 Authorization & Audit Context
- **Aggregate Root**: Authorization
- **Key Entities**: Authorization, AuditLog, ComplianceCheck
- **Domain Events**: AuthorizationRequested, AuthorizationGranted, AuditLogCreated
- **Responsibility**: Procedure authorization, compliance, audit trails

### Aggregate Design Principles

#### Patient Aggregate
**Consistency Boundary**: All patient data modifications go through Patient aggregate root

**Invariants**:
- Patient must have valid CPF
- Patient must have at least one contact method
- Medical history entries are immutable once created

**Privacy Rules**:
- LGPD: Professional secrecy for intra-institutional access
- LGPD: Written consent for inter-institutional access
- Audit every data access

#### Claim Aggregate
**Consistency Boundary**: All claim-related operations maintain TISS 4.0 compliance

**Invariants**:
- Claim must have all TISS mandatory fields
- Claim amount must match sum of line items
- Glosas can only be applied to approved claims

**Validation Rules**:
- TISS XML schema validation
- ANS procedure code verification
- Financial provision calculation

### Domain Events Pattern

**Purpose**: Ensure loose coupling between bounded contexts and enable event sourcing

**Healthcare Event Examples**:

1. **PatientAdmitted**
   - Triggers: CreateMedicalRecord, NotifyBillingContext, InitializeAuthorizationProcess
   - LGPD: Event payload should NOT contain sensitive health data; use references

2. **ClaimApproved**
   - Triggers: UpdateFinancialProvision, GenerateInvoice, NotifyPaymentContext
   - TISS: Event must include TISS transaction ID for traceability

3. **GlosaApplied**
   - Triggers: RecalculateClaimAmount, TriggerSagaCompensation, NotifyReviewQueue
   - Audit: Record glosa justification and responsible party

### Context Mapping Strategies

#### Partnership
- Patient Management ↔ Medical Records: Shared patient identity
- Medical Records ↔ Billing: Shared procedure codes

#### Customer-Supplier
- Authorization (upstream) → Billing (downstream): Authorization approval required
- Medical Records (upstream) → Claims (downstream): Clinical data feeds claims

#### Conformist
- **All contexts → TISS 4.0**: Must conform to ANS specifications
- **All contexts → LGPD**: Must conform to ANPD regulations

#### Anticorruption Layer
- Internal domain model ↔ TISS XML: ACL transforms between domain and TISS format
- Internal domain model ↔ External APIs: ACL protects domain from external changes

### Ubiquitous Language

**Clinical Terms**: Paciente, Atendimento, Diagnóstico, Procedimento, Prescrição
**Financial Terms**: Fatura, Glosa, Provisão Financeira, Ressarcimento
**TISS Terms**: Guia, Lote, Demonstrativo, TUSS, OPME
**Compliance Terms**: Auditoria, Autorização, Conformidade, Sigilo Profissional

### Tactical Patterns

**Entities**: Objects with identity (Patient, Claim, Authorization)
**Value Objects**: Immutable objects (Address, CPF, Money, DateRange, TissCode)
**Domain Services**: Operations not belonging to entities (ClaimValidationService, FinancialProvisionService, LgpdComplianceService)
**Repositories**: Persistence abstractions (PatientRepository, ClaimRepository, AuditLogRepository)

---

## 6. Architecture Benefits

| Benefit | Description |
|---------|-------------|
| **Maintainability** | Each bounded context reflects real clinical/administrative process |
| **Auditability** | Clear aggregate boundaries enable comprehensive audit trails |
| **Compliance** | Aggregates and domain events ensure LGPD-compliant data handling |
| **Flexibility** | Bounded contexts allow independent evolution of clinical and financial systems |
| **Security** | Patient aggregate encapsulates data and enforces privacy rules |

---

## 7. Key Takeaways for Business Rules Documentation

### Must Document
1. ✅ TISS 4.0 mandatory field validations
2. ✅ ANS procedure code mappings
3. ✅ LGPD data access controls
4. ✅ Audit trail requirements
5. ✅ Domain event triggers and handlers
6. ✅ Aggregate invariants and validation rules

### Compliance Checklist Template
```yaml
business_rule:
  id: BR-XXX
  name: "Rule Name"
  regulation:
    tiss_4_0: true/false
    ans_resolution: "RN XXX/YYYY"
    lgpd: true/false
  validation_logic: "Description"
  audit_requirements: "What to log"
  domain_context: "Which bounded context"
```

---

## 8. Next Steps

### For Documentation Team
1. Apply regulatory templates to existing business rules
2. Tag each rule with compliance requirements (TISS/ANS/LGPD)
3. Document aggregate boundaries and invariants
4. Map domain events to business processes

### For Development Team
1. Implement TISS XML validation schemas
2. Build LGPD-compliant audit logging
3. Create anticorruption layers for external integrations
4. Design aggregates following DDD patterns

### For Compliance Team
1. Review RN 395/2016 and RN 442/2018 directly from ANS portal
2. Conduct Data Protection Impact Assessment (DPIA)
3. Establish retention policies and automated cleanup
4. Prepare for ANPD 2026-2027 supervision priorities

---

## 9. Reference Links

- **ANS TISS Standards**: https://www.gov.br/ans/pt-br/assuntos/prestadores/padrao-para-troca-de-informacao-de-saude-suplementar-2013-tiss
- **ANS Legislation**: https://www.ans.gov.br
- **ANPD Official Site**: https://www.gov.br/anpd
- **LGPD Full Text**: http://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm

---

**Document Status**: ✅ Research Complete
**Memory Storage**: All findings stored in swarm coordination memory
**Templates Available**: TISS validation, LGPD compliance, ANS resolution, Audit trail, DDD patterns

---
