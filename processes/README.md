# Process Definitions

This directory contains the BPMN and DMN process definitions for the Hospital Revenue Cycle.

## BPMN Processes

| Process | File | Description |
|---------|------|-------------|
| **Orchestrator** | `bpmn/ORCH_Ciclo_Receita_Hospital_Futuro.bpmn` | Main revenue cycle orchestration |
| SUB-01 | `bpmn/SUB_01_Agendamento_Registro.bpmn` | Scheduling & Registration |
| SUB-02 | `bpmn/SUB_02_Pre_Atendimento.bpmn` | Pre-Service |
| SUB-03 | `bpmn/SUB_03_Atendimento_Clinico.bpmn` | Clinical Care |
| SUB-04 | `bpmn/SUB_04_Clinical_Production.bpmn` | Clinical Production |
| SUB-05 | `bpmn/SUB_05_Coding_Audit.bpmn` | Medical Coding & Audit |
| SUB-06 | `bpmn/SUB_06_Billing_Submission.bpmn` | Billing & Submission |
| SUB-07 | `bpmn/SUB_07_Denials_Management.bpmn` | Glosa/Denials Management |
| SUB-08 | `bpmn/SUB_08_Revenue_Collection.bpmn` | Revenue Collection |
| SUB-09 | `bpmn/SUB_09_Analytics.bpmn` | Analytics & Reporting |
| SUB-10 | `bpmn/SUB_10_Maximization.bpmn` | Revenue Maximization |

## DMN Decision Tables

| Decision | File | Description |
|----------|------|-------------|
| Billing Calculation | `dmn/billing-calculation.dmn` | Billing amount calculations |
| Collection Workflow | `dmn/collection-workflow.dmn` | Collection strategy decisions |
| Eligibility Verification | `dmn/eligibility-verification.dmn` | Patient eligibility rules |
| Coding Validation | `dmn/coding-validation.dmn` | Medical coding validation |
| Authorization Approval | `dmn/authorization-approval.dmn` | Authorization decision rules |
| Glosa Classification | `dmn/glosa-classification.dmn` | Denial classification rules |

## Deployment

These processes are deployed to **Camunda 8 / Zeebe** via the Python workers.

For deployment instructions, see `/docs/HUMAN TASKS - PRIORIRY.md`.
