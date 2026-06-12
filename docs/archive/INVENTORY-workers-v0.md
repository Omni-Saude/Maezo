# Archive Inventory

**Generated:** 2026-02-16
**Total Files:** 59 (47 workers + 8 tests + 4 BPMNs)

## Workers (47 v1 workers + 8 tests)

### Billing Workers (13)

| File | Original Package | Type |
|------|-----------------|------|
| apply_contract_rules_worker.py | revenue_cycle/billing/workers | v1 worker |
| apply_discounts_worker.py | revenue_cycle/billing/workers | v1 worker |
| calculate_charges_worker.py | revenue_cycle/billing/workers | v1 worker |
| consolidate_charges_worker.py | revenue_cycle/billing/workers | v1 worker |
| generate_tiss_xml_worker.py | revenue_cycle/billing/workers | v1 worker |
| group_by_guide_worker.py | revenue_cycle/billing/workers | v1 worker |
| handle_acknowledgment_worker.py | revenue_cycle/billing/workers | v1 worker |
| notify_submission_status_worker.py | revenue_cycle/billing/workers | v1 worker |
| retry_failed_submission_worker.py | revenue_cycle/billing/workers | v1 worker |
| submit_to_payer_worker.py | revenue_cycle/billing/workers | v1 worker |
| track_protocol_worker.py | revenue_cycle/billing/workers | v1 worker |
| validate_claim_worker.py | revenue_cycle/billing/workers | v1 worker |
| validate_tiss_schema_worker.py | revenue_cycle/billing/workers | v1 worker |

### Coding Workers (10)

| File | Original Package | Type |
|------|-----------------|------|
| apply_coding_rules_worker.py | revenue_cycle/coding/workers | v1 worker |
| audit_coding_worker.py | revenue_cycle/coding/workers | v1 worker |
| calculate_complexity_worker.py | revenue_cycle/coding/workers | v1 worker |
| check_code_compatibility_worker.py | revenue_cycle/coding/workers | v1 worker |
| detect_fraud_worker.py | revenue_cycle/coding/workers | v1 worker |
| extract_clinical_data_worker.py | revenue_cycle/coding/workers | v1 worker |
| finalize_coding_worker.py | revenue_cycle/coding/workers | v1 worker |
| suggest_cid10_worker.py | revenue_cycle/coding/workers | v1 worker |
| suggest_tuss_worker.py | revenue_cycle/coding/workers | v1 worker |
| validate_codes_worker.py | revenue_cycle/coding/workers | v1 worker |

### Glosa Workers (10)

| File | Original Package | Type |
|------|-----------------|------|
| analyze_glosa_reason_worker.py | revenue_cycle/glosa/workers | v1 worker |
| calculate_glosa_impact_worker.py | revenue_cycle/glosa/workers | v1 worker |
| check_appeal_eligibility_worker.py | revenue_cycle/glosa/workers | v1 worker |
| classify_glosa_type_worker.py | revenue_cycle/glosa/workers | v1 worker |
| escalate_to_supervisor_worker.py | revenue_cycle/glosa/workers | v1 worker |
| generate_appeal_documentation_worker.py | revenue_cycle/glosa/workers | v1 worker |
| identify_glosa_worker.py | revenue_cycle/glosa/workers | v1 worker |
| submit_appeal_worker.py | revenue_cycle/glosa/workers | v1 worker |
| track_appeal_status_worker.py | revenue_cycle/glosa/workers | v1 worker |
| update_payment_worker.py | revenue_cycle/glosa/workers | v1 worker |

### Production Workers (8 workers + 8 tests)

| File | Original Package | Type |
|------|-----------------|------|
| assign_prices_worker.py | revenue_cycle/production/workers | v1 worker |
| calculate_quantity_worker.py | revenue_cycle/production/workers | v1 worker |
| capture_procedure_worker.py | revenue_cycle/production/workers | v1 worker |
| check_authorization_worker.py | revenue_cycle/production/workers | v1 worker |
| enrich_procedure_worker.py | revenue_cycle/production/workers | v1 worker |
| persist_production_worker.py | revenue_cycle/production/workers | v1 worker |
| validate_compatibility_worker.py | revenue_cycle/production/workers | v1 worker |
| validate_procedure_worker.py | revenue_cycle/production/workers | v1 worker |

#### Production Tests (8)

| File | Original Package | Type |
|------|-----------------|------|
| test_assign_prices.py | revenue_cycle/production/tests | test file |
| test_calculate_quantity.py | revenue_cycle/production/tests | test file |
| test_capture_procedure.py | revenue_cycle/production/tests | test file |
| test_check_authorization.py | revenue_cycle/production/tests | test file |
| test_enrich_procedure.py | revenue_cycle/production/tests | test file |
| test_persist_production.py | revenue_cycle/production/tests | test file |
| test_validate_compatibility.py | revenue_cycle/production/tests | test file |
| test_validate_procedure.py | revenue_cycle/production/tests | test file |

### Top-Level Workers (6)

| File | Original Package | Type |
|------|-----------------|------|
| doctor_procedure_auth_status_worker.py | revenue_cycle/workers | v1 worker |
| doctor_reimbursement_summary_worker.py | revenue_cycle/workers | v1 worker |
| patient_authorization_update_worker.py | revenue_cycle/workers | v1 worker |
| patient_bill_notification_worker.py | revenue_cycle/workers | v1 worker |
| patient_copay_estimate_worker.py | revenue_cycle/workers | v1 worker |
| patient_payment_confirmation_worker.py | revenue_cycle/workers | v1 worker |

## BPMNs (4)

| File | Original Location | Replaced By |
|------|------------------|-------------|
| billing_submission.bpmn | revenue_cycle/billing/bpmn/ | SP-RC-006_Billing_Submission.bpmn |
| coding_audit.bpmn | revenue_cycle/coding/bpmn/ | SP-RC-005_Coding_Audit.bpmn |
| glosa_management.bpmn | revenue_cycle/glosa/bpmn/ | SP-RC-007_Denial_Management.bpmn |
| production_capture.bpmn | revenue_cycle/production/bpmn/ | SP-RC-004_Clinical_Production.bpmn |

## Migration Notes

- All v1 workers were replaced by v2 workers in their original locations
- v2 workers use standardized patterns with base.py, config.py, and proper error handling
- BPMN files were consolidated into centralized SP-RC-* files in revenue_cycle/bpmn/
- Test files for production workers were archived but not replaced (coverage maintained in v2 integration tests)

## Replacement Patterns

- **v1 Pattern:** Direct DB access, minimal error handling, no logging
- **v2 Pattern:** BaseWorker inheritance, unified config, structured logging, DMN integration
- **Migration Date:** 2026-02-15 to 2026-02-16
- **Phase:** Phase 3 (Worker Batch Refactoring)
