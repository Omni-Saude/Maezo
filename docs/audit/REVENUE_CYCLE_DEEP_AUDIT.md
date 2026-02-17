# Revenue Cycle Deep Audit Report

**Date:** 2026-02-14
**Auditors:** Workers 1-5 (Billing, Glosa, Coding/Production, Collection, Top-Level)
**Aggregator:** Worker 6

---

## A) Executive Summary

| Metric | Count |
|--------|-------|
| **Total files (find validation)** | **498** |
| Python files (.py) | 178 |
| BPMN files (.bpmn) | 16 |
| DMN files (.dmn) | 304 |
| **Total** | **498** |

### Worker Counts by Subdomain

| Subdomain | v1 Workers | v2 Workers | Total |
|-----------|-----------|-----------|-------|
| Billing | 13 | 13 | 26 |
| Glosa | 10 | 10 | 20 |
| Coding | 10 | 10 | 20 |
| Production | 8 | 8 | 16 |
| Collection | 47 | 0 | 47 |
| Top-level (financial) | 6 | 6 | 12 |
| **Total** | **94** | **47** | **141** |

### Critical Issues Count: 14

| Severity | Count |
|----------|-------|
| CRITICAL | 4 |
| HIGH | 4 |
| MEDIUM | 6 |

### Key Patterns Found

- **BPMN-Worker Topic Mismatch**: Billing and Glosa subdomain BPMNs use kebab-case topics; workers use dot-notation. NO matches at runtime.
- **v1/v2 Coexistence**: All subdomains except Collection have parallel v1+v2 workers with identical topics but different base classes and signatures.
- **304 DMN files** across 6 categories, many with duplicate/overlapping subfolder names.
- **Collection subdomain** has 47 workers with NO BPMN, NO v2, NO base class -- entirely standalone pattern.
- **8 of 10 SP-RC subprocess BPMNs** lack BPMNDI diagram sections.

---

## B) Worker Inventory Table

### Billing Workers (26)

| Subdomain | Filename | Pattern | Topic Value | Lines | has_v2 | v2_matches_topic | DMN Usage | Inline Rules |
|-----------|----------|---------|-------------|-------|--------|------------------|-----------|-------------|
| billing | validate_claim_worker.py | decorator | billing.validate_claim | 267 | Yes | MATCH | FederatedDMNService | 0 |
| billing | calculate_charges_worker.py | decorator | billing.calculate_charges | 374 | Yes | MATCH | FederatedDMNService | 1 |
| billing | apply_contract_rules_worker.py | decorator | billing.apply_contract_rules | 377 | Yes | MATCH | FederatedDMNService | 0 |
| billing | apply_discounts_worker.py | decorator | billing.apply_discounts | 470 | Yes | MATCH | FederatedDMNService | 1 |
| billing | consolidate_charges_worker.py | decorator | billing.consolidate_charges | 233 | Yes | MATCH | FederatedDMNService | 0 |
| billing | generate_tiss_xml_worker.py | decorator | billing.generate_tiss_xml | 274 | Yes | MATCH | FederatedDMNService | 0 |
| billing | validate_tiss_schema_worker.py | decorator | billing.validate_tiss_schema | 199 | Yes | MATCH | FederatedDMNService | 1 |
| billing | group_by_guide_worker.py | decorator | billing.group_by_guide | 302 | Yes | MATCH | FederatedDMNService | 1 |
| billing | submit_to_payer_worker.py | decorator | billing.submit_to_payer | 197 | Yes | MATCH | FederatedDMNService | 0 |
| billing | handle_acknowledgment_worker.py | decorator | billing.handle_acknowledgment | 207 | Yes | MATCH | FederatedDMNService | 1 |
| billing | notify_submission_status_worker.py | decorator | billing.notify_submission_status | 236 | Yes | MATCH | FederatedDMNService | 1 |
| billing | retry_failed_submission_worker.py | decorator | billing.retry_failed_submission | 208 | Yes | MATCH | FederatedDMNService | 1 |
| billing | track_protocol_worker.py | decorator | billing.track_protocol | 154 | Yes | MATCH | FederatedDMNService | 0 |
| billing | validate_claim_worker_v2.py | TOPIC attr | billing.validate_claim | 127 | -- | -- | evaluate_dmn() | 0 |
| billing | calculate_charges_worker_v2.py | TOPIC attr | billing.calculate_charges | 83 | -- | -- | evaluate_dmn() | 0 |
| billing | apply_contract_rules_worker_v2.py | TOPIC attr | billing.apply_contract_rules | 131 | -- | -- | evaluate_dmn() | 0 |
| billing | apply_discounts_worker_v2.py | TOPIC attr | billing.apply_discounts | 102 | -- | -- | evaluate_dmn() | 0 |
| billing | consolidate_charges_worker_v2.py | TOPIC attr | billing.consolidate_charges | 69 | -- | -- | evaluate_dmn() | 0 |
| billing | generate_tiss_xml_worker_v2.py | TOPIC attr | billing.generate_tiss_xml | 63 | -- | -- | evaluate_dmn() | 0 |
| billing | validate_tiss_schema_worker_v2.py | TOPIC attr | billing.validate_tiss_schema | 108 | -- | -- | evaluate_dmn() | 1 |
| billing | group_by_guide_worker_v2.py | TOPIC attr | billing.group_by_guide | 67 | -- | -- | evaluate_dmn() | 0 |
| billing | submit_to_payer_worker_v2.py | TOPIC attr | billing.submit_to_payer | 112 | -- | -- | evaluate_dmn() | 0 |
| billing | handle_acknowledgment_worker_v2.py | TOPIC attr | billing.handle_acknowledgment | 61 | -- | -- | evaluate_dmn() | 0 |
| billing | notify_submission_status_worker_v2.py | TOPIC attr | billing.notify_submission_status | 126 | -- | -- | evaluate_dmn() | 0 |
| billing | retry_failed_submission_worker_v2.py | TOPIC attr | billing.retry_failed_submission | 128 | -- | -- | evaluate_dmn() | 1 |
| billing | track_protocol_worker_v2.py | TOPIC attr | billing.track_protocol | 110 | -- | -- | evaluate_dmn() | 0 |

### Glosa Workers (20)

| Subdomain | Filename | Pattern | Topic Value | Lines | has_v2 | v2_matches_topic | DMN Usage | Inline Rules |
|-----------|----------|---------|-------------|-------|--------|------------------|-----------|-------------|
| glosa | identify_glosa_worker.py | decorator | glosa.identify | 280 | Yes | MATCH | FederatedDMNService | 1 |
| glosa | classify_glosa_type_worker.py | decorator | glosa.classify_type | 230 | Yes | MATCH | FederatedDMNService | 1 |
| glosa | analyze_glosa_reason_worker.py | decorator | glosa.analyze_reason | 283 | Yes | MATCH | FederatedDMNService | 2 |
| glosa | calculate_glosa_impact_worker.py | decorator | glosa.calculate_impact | 205 | Yes | MATCH | FederatedDMNService | 1 |
| glosa | check_appeal_eligibility_worker.py | decorator | glosa.check_appeal_eligibility | 273 | Yes | MATCH | FederatedDMNService | 2 |
| glosa | generate_appeal_documentation_worker.py | decorator | glosa.generate_appeal_documentation | 418 | Yes | MATCH | FederatedDMNService | 3 |
| glosa | submit_appeal_worker.py | decorator | glosa.submit_appeal | 319 | Yes | MATCH | FederatedDMNService | 0 |
| glosa | track_appeal_status_worker.py | decorator | glosa.track_appeal_status | 268 | Yes | MATCH | FederatedDMNService | 1 |
| glosa | escalate_to_supervisor_worker.py | decorator | glosa.escalate_to_supervisor | 378 | Yes | MATCH | FederatedDMNService | 2 |
| glosa | update_payment_worker.py | decorator | glosa.update_payment | 321 | Yes | MATCH | FederatedDMNService | 2 |
| glosa | identify_glosa_worker_v2.py | TOPIC attr | glosa.identify | 157 | -- | -- | evaluate_dmn() | 0 |
| glosa | classify_glosa_type_worker_v2.py | TOPIC attr | glosa.classify_type | 143 | -- | -- | evaluate_dmn() | 0 |
| glosa | analyze_glosa_reason_worker_v2.py | TOPIC attr | glosa.analyze_reason | 197 | -- | -- | evaluate_dmn() | 0 |
| glosa | calculate_glosa_impact_worker_v2.py | TOPIC attr | glosa.calculate_impact | 147 | -- | -- | evaluate_dmn() | 0 |
| glosa | check_appeal_eligibility_worker_v2.py | TOPIC attr | glosa.check_appeal_eligibility | 151 | -- | -- | evaluate_dmn() | 0 |
| glosa | generate_appeal_documentation_worker_v2.py | TOPIC attr | glosa.generate_appeal_documentation | 162 | -- | -- | evaluate_dmn() | 0 |
| glosa | submit_appeal_worker_v2.py | TOPIC attr | glosa.submit_appeal | 157 | -- | -- | evaluate_dmn() | 0 |
| glosa | track_appeal_status_worker_v2.py | TOPIC attr | glosa.track_appeal_status | 165 | -- | -- | evaluate_dmn() | 0 |
| glosa | escalate_to_supervisor_worker_v2.py | TOPIC attr | glosa.escalate_to_supervisor | 172 | -- | -- | evaluate_dmn() | 0 |
| glosa | update_payment_worker_v2.py | TOPIC attr | glosa.update_payment | 141 | -- | -- | evaluate_dmn() | 0 |

### Coding Workers (20)

| Subdomain | Filename | Pattern | Topic Value | Lines | has_v2 | v2_matches_topic | DMN Usage | Inline Rules |
|-----------|----------|---------|-------------|-------|--------|------------------|-----------|-------------|
| coding | apply_coding_rules_worker.py | TOPIC+decorator | coding.apply_rules | 442 | Yes | MATCH | FederatedDMNService | 4 |
| coding | audit_coding_worker.py | TOPIC+decorator | coding.audit_coding | 505 | Yes | MATCH | FederatedDMNService | 5 |
| coding | check_code_compatibility_worker.py | TOPIC+decorator | coding.check_compatibility | 348 | Yes | MATCH | FederatedDMNService | 2 |
| coding | suggest_cid10_worker.py | TOPIC+decorator | coding.suggest_cid10 | 412 | Yes | MATCH | FederatedDMNService | 15 |
| coding | suggest_tuss_worker.py | TOPIC+decorator | coding.suggest_tuss | 495 | Yes | MATCH | FederatedDMNService | 10 |
| coding | detect_fraud_worker.py | TOPIC+decorator | coding.detect_fraud | 726 | Yes | MATCH | FederatedDMNService | 5 |
| coding | calculate_complexity_worker.py | TOPIC+decorator | coding.calculate_complexity | 466 | Yes | MATCH | FederatedDMNService | 4 |
| coding | validate_codes_worker.py | TOPIC+decorator | coding.validate_coding | 471 | Yes | MATCH | FederatedDMNService | 3 |
| coding | extract_clinical_data_worker.py | TOPIC+decorator | coding.extract_clinical_data | 395 | Yes | MATCH | FederatedDMNService | 0 |
| coding | finalize_coding_worker.py | TOPIC+decorator | coding.finalize_coding | 471 | Yes | MATCH | FederatedDMNService | 3 |
| coding | apply_coding_rules_worker_v2.py | TOPIC attr | coding.apply_rules | 93 | -- | -- | FederatedDMNService | 0 |
| coding | audit_coding_worker_v2.py | TOPIC attr | coding.audit_coding | 112 | -- | -- | FederatedDMNService | 0 |
| coding | check_code_compatibility_worker_v2.py | TOPIC attr | coding.check_compatibility | 98 | -- | -- | FederatedDMNService | 0 |
| coding | suggest_cid10_worker_v2.py | TOPIC attr | coding.suggest_cid10 | 146 | -- | -- | FederatedDMNService+BaseExt | 0 |
| coding | suggest_tuss_worker_v2.py | TOPIC attr | coding.suggest_tuss | 141 | -- | -- | FederatedDMNService+BaseExt | 0 |
| coding | detect_fraud_worker_v2.py | TOPIC attr | coding.detect_fraud | 100 | -- | -- | FederatedDMNService+BaseExt | 0 |
| coding | calculate_complexity_worker_v2.py | TOPIC attr | coding.calculate_complexity | 82 | -- | -- | FederatedDMNService | 0 |
| coding | validate_codes_worker_v2.py | TOPIC attr | coding.validate_coding | 197 | -- | -- | FederatedDMNService+BaseExt | 0 |
| coding | extract_clinical_data_worker_v2.py | TOPIC attr | coding.extract_clinical_data | 105 | -- | -- | FederatedDMNService | 0 |
| coding | finalize_coding_worker_v2.py | TOPIC attr | coding.finalize_coding | 200 | -- | -- | FederatedDMNService+BaseExt | 0 |

### Production Workers (16)

| Subdomain | Filename | Pattern | Topic Value | Lines | has_v2 | v2_matches_topic | DMN Usage | Inline Rules |
|-----------|----------|---------|-------------|-------|--------|------------------|-----------|-------------|
| production | capture_procedure_worker.py | TOPIC+decorator | production.capture_procedure | 171 | Yes | MATCH | FederatedDMNService | 2 |
| production | enrich_procedure_worker.py | TOPIC+decorator | production.enrich_procedure | 181 | Yes | MATCH | FederatedDMNService | 2 |
| production | validate_procedure_worker.py | TOPIC+decorator | production.validate_procedure | 213 | Yes | MATCH | FederatedDMNService | 3 |
| production | validate_compatibility_worker.py | TOPIC+decorator | production.validate_compatibility | 197 | Yes | MATCH | FederatedDMNService | 2 |
| production | check_authorization_worker.py | TOPIC+decorator | production.check_authorization | 306 | Yes | MATCH | FederatedDMNService | 4 |
| production | calculate_quantity_worker.py | TOPIC+decorator | production.calculate_quantity | 165 | Yes | MATCH | FederatedDMNService | 2 |
| production | assign_prices_worker.py | TOPIC+decorator | production.assign_prices | 275 | Yes | MATCH | FederatedDMNService | 4 |
| production | persist_production_worker.py | TOPIC+decorator | production.persist_production | 247 | Yes | MATCH | FederatedDMNService | 2 |
| production | capture_procedure_worker_v2.py | TOPIC attr | production.capture_procedure | 134 | -- | -- | FederatedDMNService+BaseExt | 0 |
| production | enrich_procedure_worker_v2.py | TOPIC attr | production.enrich_procedure | 118 | -- | -- | FederatedDMNService+BaseExt | 0 |
| production | validate_procedure_worker_v2.py | TOPIC attr | production.validate_procedure | 108 | -- | -- | FederatedDMNService+BaseExt | 0 |
| production | validate_compatibility_worker_v2.py | TOPIC attr | production.validate_compatibility | 108 | -- | -- | FederatedDMNService+BaseExt | 0 |
| production | check_authorization_worker_v2.py | TOPIC attr | production.check_authorization | 120 | -- | -- | FederatedDMNService+BaseExt | 0 |
| production | calculate_quantity_worker_v2.py | TOPIC attr | production.calculate_quantity | 122 | -- | -- | FederatedDMNService+BaseExt | 0 |
| production | assign_prices_worker_v2.py | TOPIC attr | production.assign_prices | 143 | -- | -- | None (direct logic) | 0 |
| production | persist_production_worker_v2.py | TOPIC attr | production.persist_production | 125 | -- | -- | FederatedDMNService+BaseExt | 0 |

### Collection Workers (47)

| Subdomain | Filename | Pattern | Topic Value (WORKER_TYPE) | Lines | has_v2 | DMN Usage | Inline Rules |
|-----------|----------|---------|---------------------------|-------|--------|-----------|-------------|
| collection | alert_anomalies_worker.py | WORKER_TYPE | alert_anomalies | 191 | No | FederatedDMNService | 10 |
| collection | analyze_payer_performance_worker.py | WORKER_TYPE | analyze_payer_performance | 166 | No | FederatedDMNService | 2 |
| collection | apply_contractual_adjustments_worker.py | WORKER_TYPE | apply_contractual_adjustments | 121 | No | FederatedDMNService | 0 |
| collection | apply_penalties_worker.py | WORKER_TYPE | apply_penalties | 125 | No | FederatedDMNService | 0 |
| collection | archive_reconciliation_worker.py | WORKER_TYPE | archive_reconciliation | 125 | No | FederatedDMNService | 1 |
| collection | auto_matching_worker.py | WORKER_TYPE | auto_matching | 205 | No | FederatedDMNService | 13 |
| collection | calculate_aging_bucket_worker.py | WORKER_TYPE | calculate_aging_bucket | 100 | No | FederatedDMNService | 5 |
| collection | calculate_collection_rate_worker.py | WORKER_TYPE | calculate_collection_rate | 113 | No | FederatedDMNService | 2 |
| collection | calculate_dso_worker.py | WORKER_TYPE | calculate_dso | 158 | No | FederatedDMNService | 9 |
| collection | calculate_net_payment_worker.py | WORKER_TYPE | calculate_net_payment | 91 | No | FederatedDMNService | 1 |
| collection | calculate_revenue_cycle_time_worker.py | WORKER_TYPE | calculate_revenue_cycle_time | 147 | No | FederatedDMNService | 5 |
| collection | calculate_variance_worker.py | WORKER_TYPE | calculate_variance | 104 | No | FederatedDMNService | 0 |
| collection | classify_payment_type_worker.py | WORKER_TYPE | classify_payment_type | 110 | No | FederatedDMNService | 5 |
| collection | convert_currency_worker.py | WORKER_TYPE | convert_currency | 106 | No | FederatedDMNService | 3 |
| collection | detect_duplicate_payment_worker.py | WORKER_TYPE | detect_duplicate_payment | 135 | No | FederatedDMNService | 7 |
| collection | detect_revenue_leakage_worker.py | WORKER_TYPE | detect_revenue_leakage | 269 | No | FederatedDMNService | 9 |
| collection | escalate_to_legal_worker.py | WORKER_TYPE | escalate_to_legal | 172 | No | FederatedDMNService | 4 |
| collection | escalate_unmatched_worker.py | WORKER_TYPE | escalate_unmatched | 118 | No | FederatedDMNService | 0 |
| collection | export_to_erp_worker.py | WORKER_TYPE | export_to_erp | 181 | No | FederatedDMNService | 5 |
| collection | finalize_allocation_worker.py | WORKER_TYPE | finalize_allocation | 102 | No | FederatedDMNService | 1 |
| collection | flag_discrepancies_worker.py | WORKER_TYPE | flag_discrepancies | 165 | No | FederatedDMNService | 9 |
| collection | generate_aging_report_worker.py | WORKER_TYPE | generate_aging_report | 175 | No | FederatedDMNService | 2 |
| collection | generate_collection_letter_worker.py | WORKER_TYPE | generate_collection_letter | 119 | No | FederatedDMNService | 2 |
| collection | generate_executive_dashboard_worker.py | WORKER_TYPE | generate_executive_dashboard | 164 | No | FederatedDMNService | 2 |
| collection | handle_overpayment_worker.py | WORKER_TYPE | handle_overpayment | 125 | No | FederatedDMNService | 0 |
| collection | handle_underpayment_worker.py | WORKER_TYPE | handle_underpayment | 129 | No | FederatedDMNService | 1 |
| collection | identify_overdue_worker.py | WORKER_TYPE | identify_overdue | 137 | No | FederatedDMNService | 1 |
| collection | identify_slow_payers_worker.py | WORKER_TYPE | identify_slow_payers | 138 | No | FederatedDMNService | 1 |
| collection | match_by_invoice_worker.py | WORKER_TYPE | match_by_invoice | 123 | No | FederatedDMNService | 4 |
| collection | match_by_patient_worker.py | WORKER_TYPE | match_by_patient | 149 | No | FederatedDMNService | 3 |
| collection | match_by_protocol_worker.py | WORKER_TYPE | match_by_protocol | 114 | No | FederatedDMNService | 2 |
| collection | negotiate_payment_plan_worker.py | WORKER_TYPE | negotiate_payment_plan | 186 | No | FederatedDMNService | 4 |
| collection | parse_payment_file_worker.py | WORKER_TYPE | parse_payment_file | 112 | No | FederatedDMNService | 1 |
| collection | partial_allocation_worker.py | WORKER_TYPE | partial_allocation | 136 | No | FederatedDMNService | 3 |
| collection | persist_payment_worker.py | WORKER_TYPE | persist_payment | 165 | No | FederatedDMNService | 4 |
| collection | predict_collection_date_worker.py | WORKER_TYPE | predict_collection_date | 146 | No | FederatedDMNService | 2 |
| collection | prioritize_collection_worker.py | WORKER_TYPE | prioritize_collection | 162 | No | FederatedDMNService | 9 |
| collection | receive_payment_notification_worker.py | WORKER_TYPE | receive_payment_notification | 144 | No | FederatedDMNService | 3 |
| collection | reconcile_daily_worker.py | WORKER_TYPE | reconcile_daily | 176 | No | FederatedDMNService | 6 |
| collection | reconcile_monthly_worker.py | WORKER_TYPE | reconcile_monthly | 181 | No | FederatedDMNService | 5 |
| collection | reconcile_weekly_worker.py | WORKER_TYPE | reconcile_weekly | 171 | No | FederatedDMNService | 4 |
| collection | schedule_collection_call_worker.py | WORKER_TYPE | schedule_collection_call | 166 | No | FederatedDMNService | 1 |
| collection | send_daily_summary_worker.py | WORKER_TYPE | send_daily_summary | 165 | No | FederatedDMNService | 0 |
| collection | send_whatsapp_reminder_worker.py | WORKER_TYPE | send_whatsapp_reminder | 139 | No | FederatedDMNService | 3 |
| collection | update_bi_datawarehouse_worker.py | WORKER_TYPE | update_bi_datawarehouse | 168 | No | FederatedDMNService | 1 |
| collection | update_forecasts_worker.py | WORKER_TYPE | update_forecasts | 142 | No | FederatedDMNService | 3 |
| collection | validate_payment_data_worker.py | WORKER_TYPE | validate_payment_data | 134 | No | FederatedDMNService | 5 |
| collection | write_off_bad_debt_worker.py | WORKER_TYPE | write_off_bad_debt | 131 | No | FederatedDMNService | 2 |

### Top-Level Financial Workers (12)

| Subdomain | Filename | Pattern | Topic Value | Lines | has_v2 | v2_matches_topic | DMN Usage | Inline Rules |
|-----------|----------|---------|-------------|-------|--------|------------------|-----------|-------------|
| financial | doctor_procedure_auth_status_worker.py | TOPIC attr | financial.auth_pending | 217 | Yes | MATCH | None (WhatsApp) | 3 |
| financial | doctor_reimbursement_summary_worker.py | TOPIC attr | financial.reimbursement_summary | 213 | Yes | MATCH | None (WhatsApp) | 4 |
| financial | patient_authorization_update_worker.py | TOPIC attr | financial.auth_update | 199 | Yes | MATCH | None (WhatsApp) | 0 |
| financial | patient_bill_notification_worker.py | TOPIC attr | financial.bill_ready | 228 | Yes | MATCH | None (WhatsApp) | 3 |
| financial | patient_copay_estimate_worker.py | TOPIC attr | financial.copay_estimate | 251 | Yes | MATCH | None (WhatsApp) | 3 |
| financial | patient_payment_confirmation_worker.py | TOPIC attr | financial.payment_confirmed | 212 | Yes | MATCH | None (WhatsApp) | 0 |
| financial | doctor_procedure_auth_status_worker_v2.py | TOPIC attr | financial.auth_pending | 138 | -- | -- | BaseExternalTaskWorker | 3 |
| financial | doctor_reimbursement_summary_worker_v2.py | TOPIC attr | financial.reimbursement_summary | 115 | -- | -- | BaseExternalTaskWorker | 3 |
| financial | patient_authorization_update_worker_v2.py | TOPIC attr | financial.auth_update | 115 | -- | -- | BaseExternalTaskWorker | 2 |
| financial | patient_bill_notification_worker_v2.py | TOPIC attr | financial.bill_ready | 115 | -- | -- | BaseExternalTaskWorker | 2 |
| financial | patient_copay_estimate_worker_v2.py | TOPIC attr | financial.copay_estimate | 146 | -- | -- | BaseExternalTaskWorker | 5 |
| financial | patient_payment_confirmation_worker_v2.py | TOPIC attr | financial.payment_confirmed | 121 | -- | -- | BaseExternalTaskWorker | 3 |

---

## C) BPMN Inventory Table

| Location | Filename | processId | Topics | Language | ServiceTasks | Called By | Orphan? |
|----------|----------|-----------|--------|----------|-------------|-----------|---------|
| revenue_cycle/bpmn/ | revenue-cycle-main.bpmn | revenue_cycle_main | (none - orchestrator) | MIXED | 0 | -- | No |
| revenue_cycle/bpmn/ | SP-RC-001_Scheduling_Registration.bpmn | SP_RC_001_Scheduling_Registration | revenue.verify_insurance, platform.notify_supervisor, revenue.check_eligibility, revenue.schedule_appointment, platform.notify_patient | PT-BR | 5 | revenue_cycle_main | No |
| revenue_cycle/bpmn/ | SP-RC-002_Pre_Service.bpmn | SP_RC_002_Pre_Service | revenue.check_authorization, revenue.request_authorization, revenue.validate_procedure | PT-BR | 3 | revenue_cycle_main | No |
| revenue_cycle/bpmn/ | SP-RC-003_Clinical_Service.bpmn | SP_RC_003_Clinical_Service | production.capture_procedure, production.enrich_procedure, production.calculate_quantity, production.validate_clinical_data | PT-BR | 4 | revenue_cycle_main | No |
| revenue_cycle/bpmn/ | SP-RC-004_Clinical_Production.bpmn | SP_RC_004_Clinical_Production | production.assign_prices, production.validate_compatibility, production.calculate_value, production.record_production | PT-BR | 4 | revenue_cycle_main | No |
| revenue_cycle/bpmn/ | SP-RC-005_Coding_Audit.bpmn | SP_RC_005_Coding_Audit | coding.extract_clinical_data, coding.suggest_cid10, coding.suggest_tuss, coding.check_compatibility, coding.detect_fraud, coding.validate_coding, coding.audit_coding | PT-BR | 7 | revenue_cycle_main | No |
| revenue_cycle/bpmn/ | SP-RC-006_Billing_Submission.bpmn | SP_RC_006_Billing_Submission | billing.validate_claim, billing.calculate_charges, billing.apply_contract_rules, billing.generate_tiss_xml, billing.validate_tiss_schema, billing.submit_to_payer | PT-BR | 6 | revenue_cycle_main | No |
| revenue_cycle/bpmn/ | SP-RC-007_Denial_Management.bpmn | SP_RC_007_Denial_Management | glosa.identify, glosa.classify_type, glosa.analyze_reason, glosa.check_appeal_eligibility, glosa.generate_appeal_documentation, glosa.submit_appeal, glosa.track_appeal_status | PT-BR | 7 | revenue_cycle_main | No |
| revenue_cycle/bpmn/ | SP-RC-008_Revenue_Collection.bpmn | SP_RC_008_Revenue_Collection | collection.identify_overdue, collection.prioritize, collection.receive_payment_notification, collection.auto_matching, collection.reconcile_daily, collection.update_accounts_receivable | PT-BR | 6 | revenue_cycle_main | No |
| revenue_cycle/bpmn/ | SP-RC-009_Analytics_Intelligence.bpmn | SP_RC_009_Analytics_Intelligence | analytics.calculate_dso, analytics.calculate_collection_rate, analytics.analyze_payer_performance, analytics.detect_revenue_leakage, analytics.generate_executive_dashboard, analytics.generate_operational_metrics, analytics.generate_recommendations | PT-BR | 7 | revenue_cycle_main | No |
| revenue_cycle/bpmn/ | SP-RC-010_Maximization.bpmn | SP_RC_010_Maximization | maximization.predict_collection_date, maximization.identify_slow_payers, maximization.update_forecasts, maximization.analyze_revenue_opportunities, maximization.optimize_pricing_strategy, maximization.optimize_contract_terms, maximization.generate_action_plan, maximization.negotiate_payment_plan | PT-BR | 8 | revenue_cycle_main | No |
| revenue_cycle/bpmn/ | SP-RF-003_Patient_Financial_SelfService.bpmn | SP_RF_003_Patient_Financial_SelfService | financial.copay_estimate, financial.send_estimate, financial.bill_ready, financial.bill_notification, financial.bill_detail, financial.billing_support, financial.payment_process, financial.payment_plan, financial.payment_confirmed, financial.send_receipt, financial.insurance_request, financial.verify_coverage, financial.update_record | EN | 13 | -- | No |
| billing/bpmn/ | billing_submission.bpmn | SUB_06_Billing_Submission | billing-group-by-guide, billing-apply-contract-rules, billing-calculate-charges, billing-apply-discounts, billing-consolidate-charges, billing-validate-claim, billing-generate-tiss-xml, billing-validate-tiss-schema, billing-submit-to-payer, billing-track-protocol, billing-handle-acknowledgment, billing-notify-submission-status, billing-retry-failed-submission | PT-BR | 14 | -- | **DUPLICATE** |
| glosa/bpmn/ | glosa_management.bpmn | SUB_07_Glosa_Management | identify-glosa, classify-glosa-type, calculate-glosa-impact, analyze-glosa-reason, check-appeal-eligibility, update-payment-after-glosa, generate-appeal-documentation, auto-approve-appeal, submit-glosa-appeal, handle-tiss-error, track-appeal-status, escalate-ans-timeout | PT-BR | 12 | -- | **DUPLICATE** |
| coding/bpmn/ | coding_audit.bpmn | (not specified) | extract-clinical-data, suggest-cid10-codes, suggest-tuss-codes, validate-coding, check-code-compatibility, apply-coding-rules, calculate-complexity, detect-fraud, audit-coding, finalize-coding | PT-BR | 10 | -- | **DUPLICATE** |
| production/bpmn/ | production_capture.bpmn | (not specified) | production.capture_procedure, production.validate_procedure, production.enrich_procedure, production.check_authorization, production.validate_compatibility, production.calculate_quantity, production.assign_prices, production.persist_production | PT-BR | 8 | -- | No |

---

## D) DMN Cross-Reference

| DMN Category | Subfolders | DMN Count | Consuming Workers / Services |
|-------------|------------|-----------|------------------------------|
| **billing** | 27 | 67 | billing v1/v2 workers, BillingRulesService |
| **cash_operations** | 5 | 12 | patient_authorization_update_worker_v2, patient_copay_estimate_worker_v2, PricingService |
| **coding_audit** | 16 | 53 | coding v1/v2 workers (all 10 pairs) |
| **glosa_prevention** | 11 | 64 | glosa v1/v2 workers, GlosaPreventionService |
| **pricing** | 10 | 22 | production workers, PricingService |
| **revenue_recovery** | 18 | 65 | glosa appeal workers, AppealStrategyService |
| **TOTAL** | **87** | **283** (+21 in subdomain dirs = **304 on disk**) | |

**Note:** 21 additional DMN files exist in subdomain-level `dmn/` directories (billing/dmn/, coding/dmn/) beyond the top-level `revenue_cycle/dmn/` tree. Some subfolders appear duplicated across creation waves (e.g., `code_compatibility` vs `compat`, `eligibility` vs `elig`, `tracking` vs `track`, `estimate` vs `estimates`).

---

## E) Topic Mismatch Matrix

### SP-RC-006 Billing (top-level BPMN) vs Workers -- MATCH

| BPMN Topic | Worker Topic | Match |
|------------|-------------|-------|
| billing.validate_claim | billing.validate_claim | YES |
| billing.calculate_charges | billing.calculate_charges | YES |
| billing.apply_contract_rules | billing.apply_contract_rules | YES |
| billing.generate_tiss_xml | billing.generate_tiss_xml | YES |
| billing.validate_tiss_schema | billing.validate_tiss_schema | YES |
| billing.submit_to_payer | billing.submit_to_payer | YES |

### billing_submission.bpmn (subdomain BPMN) vs Workers -- ALL MISMATCH

| BPMN Topic (kebab-case) | Worker Topic (dot-notation) | Match |
|--------------------------|---------------------------|-------|
| billing-group-by-guide | billing.group_by_guide | **FORMAT_MISMATCH** |
| billing-apply-contract-rules | billing.apply_contract_rules | **FORMAT_MISMATCH** |
| billing-calculate-charges | billing.calculate_charges | **FORMAT_MISMATCH** |
| billing-apply-discounts | billing.apply_discounts | **FORMAT_MISMATCH** |
| billing-consolidate-charges | billing.consolidate_charges | **FORMAT_MISMATCH** |
| billing-validate-claim | billing.validate_claim | **FORMAT_MISMATCH** |
| billing-generate-tiss-xml | billing.generate_tiss_xml | **FORMAT_MISMATCH** |
| billing-validate-tiss-schema | billing.validate_tiss_schema | **FORMAT_MISMATCH** |
| billing-submit-to-payer | billing.submit_to_payer | **FORMAT_MISMATCH** |
| billing-track-protocol | billing.track_protocol | **FORMAT_MISMATCH** |
| billing-handle-acknowledgment | billing.handle_acknowledgment | **FORMAT_MISMATCH** |
| billing-notify-submission-status | billing.notify_submission_status | **FORMAT_MISMATCH** |
| billing-retry-failed-submission | billing.retry_failed_submission | **FORMAT_MISMATCH** |

### SP-RC-007 Denial/Glosa (top-level BPMN) vs Workers -- MATCH

| BPMN Topic | Worker Topic | Match |
|------------|-------------|-------|
| glosa.identify | glosa.identify | YES |
| glosa.classify_type | glosa.classify_type | YES |
| glosa.analyze_reason | glosa.analyze_reason | YES |
| glosa.check_appeal_eligibility | glosa.check_appeal_eligibility | YES |
| glosa.generate_appeal_documentation | glosa.generate_appeal_documentation | YES |
| glosa.submit_appeal | glosa.submit_appeal | YES |
| glosa.track_appeal_status | glosa.track_appeal_status | YES |

### glosa_management.bpmn (subdomain BPMN) vs Workers -- ALL MISMATCH

| BPMN Topic (kebab-case) | Worker Topic (dot-notation) | Match |
|--------------------------|---------------------------|-------|
| identify-glosa | glosa.identify | **FORMAT_MISMATCH** |
| classify-glosa-type | glosa.classify_type | **FORMAT_MISMATCH** |
| calculate-glosa-impact | glosa.calculate_impact | **FORMAT_MISMATCH** |
| analyze-glosa-reason | glosa.analyze_reason | **FORMAT_MISMATCH** |
| check-appeal-eligibility | glosa.check_appeal_eligibility | **FORMAT_MISMATCH** |
| update-payment-after-glosa | glosa.update_payment | **FORMAT+SEMANTIC_MISMATCH** |
| generate-appeal-documentation | glosa.generate_appeal_documentation | **FORMAT_MISMATCH** |
| auto-approve-appeal | (none) | **NO WORKER** |
| submit-glosa-appeal | glosa.submit_appeal | **FORMAT_MISMATCH** |
| handle-tiss-error | (none) | **NO WORKER** |
| track-appeal-status | glosa.track_appeal_status | **FORMAT_MISMATCH** |
| escalate-ans-timeout | glosa.escalate_to_supervisor | **FORMAT+SEMANTIC_MISMATCH** |

### SP-RC-005 Coding (top-level BPMN) vs Workers -- MATCH

| BPMN Topic | Worker Topic | Match |
|------------|-------------|-------|
| coding.extract_clinical_data | coding.extract_clinical_data | YES |
| coding.suggest_cid10 | coding.suggest_cid10 | YES |
| coding.suggest_tuss | coding.suggest_tuss | YES |
| coding.check_compatibility | coding.check_compatibility | YES |
| coding.detect_fraud | coding.detect_fraud | YES |
| coding.validate_coding | coding.validate_coding | YES |
| coding.audit_coding | coding.audit_coding | YES |

### coding_audit.bpmn (subdomain BPMN) vs Workers -- ALL MISMATCH

| BPMN Topic (kebab-case) | Worker Topic (dot-notation) | Match |
|--------------------------|---------------------------|-------|
| extract-clinical-data | coding.extract_clinical_data | **FORMAT_MISMATCH** |
| suggest-cid10-codes | coding.suggest_cid10 | **FORMAT_MISMATCH** |
| suggest-tuss-codes | coding.suggest_tuss | **FORMAT_MISMATCH** |
| validate-coding | coding.validate_coding | **FORMAT_MISMATCH** |
| check-code-compatibility | coding.check_compatibility | **FORMAT_MISMATCH** |
| apply-coding-rules | coding.apply_rules | **FORMAT_MISMATCH** |
| calculate-complexity | coding.calculate_complexity | **FORMAT_MISMATCH** |
| detect-fraud | coding.detect_fraud | **FORMAT_MISMATCH** |
| audit-coding | coding.audit_coding | **FORMAT_MISMATCH** |
| finalize-coding | coding.finalize_coding | **FORMAT_MISMATCH** |

### Production (subdomain BPMN) vs Workers -- MATCH

| BPMN Topic | Worker Topic | Match |
|------------|-------------|-------|
| production.capture_procedure | production.capture_procedure | YES |
| production.validate_procedure | production.validate_procedure | YES |
| production.enrich_procedure | production.enrich_procedure | YES |
| production.check_authorization | production.check_authorization | YES |
| production.validate_compatibility | production.validate_compatibility | YES |
| production.calculate_quantity | production.calculate_quantity | YES |
| production.assign_prices | production.assign_prices | YES |
| production.persist_production | production.persist_production | YES |

### SP-RC-003/004 Clinical (top-level BPMN) vs Workers -- PARTIAL

| BPMN Topic | Worker Topic | Match |
|------------|-------------|-------|
| production.capture_procedure | production.capture_procedure | YES |
| production.enrich_procedure | production.enrich_procedure | YES |
| production.calculate_quantity | production.calculate_quantity | YES |
| production.validate_clinical_data | (none) | **NO WORKER** |
| production.assign_prices | production.assign_prices | YES |
| production.validate_compatibility | production.validate_compatibility | YES |
| production.calculate_value | (none) | **NO WORKER** |
| production.record_production | (none -- persist_production?) | **NAME_MISMATCH** |

### SP-RC-008/009/010 Collection (top-level BPMN) vs Workers

| BPMN Topic | Worker WORKER_TYPE | Match |
|------------|-------------------|-------|
| collection.identify_overdue | identify_overdue | **NAMESPACE_MISMATCH** (prefix differs) |
| collection.prioritize | prioritize_collection | **NAME_MISMATCH** |
| collection.receive_payment_notification | receive_payment_notification | **NAMESPACE_MISMATCH** |
| collection.auto_matching | auto_matching | **NAMESPACE_MISMATCH** |
| collection.reconcile_daily | reconcile_daily | **NAMESPACE_MISMATCH** |
| collection.update_accounts_receivable | (none) | **NO WORKER** |
| analytics.calculate_dso | calculate_dso | **NAMESPACE_MISMATCH** |
| analytics.calculate_collection_rate | calculate_collection_rate | **NAMESPACE_MISMATCH** |
| analytics.analyze_payer_performance | analyze_payer_performance | **NAMESPACE_MISMATCH** |
| analytics.detect_revenue_leakage | detect_revenue_leakage | **NAMESPACE_MISMATCH** |
| analytics.generate_executive_dashboard | generate_executive_dashboard | **NAMESPACE_MISMATCH** |
| analytics.generate_operational_metrics | (none) | **NO WORKER** |
| analytics.generate_recommendations | (none) | **NO WORKER** |
| maximization.predict_collection_date | predict_collection_date | **NAMESPACE_MISMATCH** |
| maximization.identify_slow_payers | identify_slow_payers | **NAMESPACE_MISMATCH** |
| maximization.update_forecasts | update_forecasts | **NAMESPACE_MISMATCH** |
| maximization.analyze_revenue_opportunities | (none) | **NO WORKER** |
| maximization.optimize_pricing_strategy | (none) | **NO WORKER** |
| maximization.optimize_contract_terms | (none) | **NO WORKER** |
| maximization.generate_action_plan | (none) | **NO WORKER** |
| maximization.negotiate_payment_plan | negotiate_payment_plan | **NAMESPACE_MISMATCH** |

### SP-RF-003 Financial Self-Service vs Workers

| BPMN Topic | Worker Topic | Match |
|------------|-------------|-------|
| financial.copay_estimate | financial.copay_estimate | YES |
| financial.send_estimate | (none) | **NO WORKER** |
| financial.bill_ready | financial.bill_ready | YES |
| financial.bill_notification | (none) | **NO WORKER** |
| financial.bill_detail | (none) | **NO WORKER** |
| financial.billing_support | (none) | **NO WORKER** |
| financial.payment_process | (none) | **NO WORKER** |
| financial.payment_plan | (none) | **NO WORKER** |
| financial.payment_confirmed | financial.payment_confirmed | YES |
| financial.send_receipt | (none) | **NO WORKER** |
| financial.insurance_request | (none) | **NO WORKER** |
| financial.verify_coverage | (none) | **NO WORKER** |
| financial.update_record | (none) | **NO WORKER** |

### SP-RC-001/002 Scheduling & Pre-Service vs Workers

| BPMN Topic | Worker Topic | Match |
|------------|-------------|-------|
| revenue.verify_insurance | (none) | **NO WORKER** |
| platform.notify_supervisor | (none) | **NO WORKER** |
| revenue.check_eligibility | (none) | **NO WORKER** |
| revenue.schedule_appointment | (none) | **NO WORKER** |
| platform.notify_patient | (none) | **NO WORKER** |
| revenue.check_authorization | (none) | **NO WORKER** |
| revenue.request_authorization | (none) | **NO WORKER** |
| revenue.validate_procedure | (none) | **NO WORKER** |

### Mismatch Summary

| Category | Count |
|----------|-------|
| Exact match | 33 |
| Format mismatch (kebab vs dot) | 35 |
| Namespace mismatch (prefix differs) | 13 |
| Name mismatch | 2 |
| No worker exists | 26 |
| **Total BPMN topics** | **109** |

---

## F) Support Files Inventory

### Services (revenue_cycle/services/)

| File | Class | Lines | Uses FederatedDMNService | Consumed By |
|------|-------|-------|------------------------|-------------|
| billing_rules_service.py | BillingRulesService | 259 | Yes | billing workers v2 |
| glosa_prevention_service.py | GlosaPreventionService | 213 | Yes | glosa workers v2 |
| appeal_strategy_service.py | AppealStrategyService | 176 | Yes | glosa appeal workers v2 |
| pricing_service.py | PricingService | 185 | Yes | production/pricing workers v2 |

### Collection Support Files

| File | Purpose | Lines | Consumed By |
|------|---------|-------|-------------|
| collection/lib/cnab_parser.py | CNAB 240/400 Brazilian bank return file parser | 434 | parse_payment_file_worker |
| collection/lib/penalty_calculator.py | Brazilian late fee calculator (Lei 10.406/2002) | 118 | apply_penalties_worker |
| collection/entities.py | Domain entities: Payment, PaymentAllocation, Reconciliation, CollectionCase, PaymentPlan | 121 | 15 workers |
| collection/enums.py | StrEnums: PaymentStatus, PaymentType, AgingBucket, etc. | 130 | 27 workers |
| collection/exceptions.py | Domain exceptions with bpmn_error_code | 76 | 18 workers |
| collection/templates/collection_letters.py | Portuguese collection letter templates | 161 | generate_collection_letter_worker |

### Base Worker Modules

| File | Purpose | Lines | Consumed By |
|------|---------|-------|-------------|
| billing/workers/base.py | BaseWorker, WorkerResult, @worker decorator | 162 | All billing+glosa v1 workers |
| glosa/workers/base.py | Re-exports from billing base + GlosaWorkerMixin | 93 | All glosa v1 workers |
| shared/workers/base.py | BaseExternalTaskWorker, TaskContext, TaskResult | (shared) | All v2 workers |

### Init Files Status

| File | Exports | Issue |
|------|---------|-------|
| billing/workers/__init__.py | 4 of 13 v1 workers | Missing 9 v1, all v2 |
| glosa/workers/__init__.py | 2 of 10 v1 workers | Missing 8 v1, all v2 |
| coding/workers/__init__.py | 10 v1 workers | Missing all v2 |
| production/workers/__init__.py | 8 v1 workers | Missing all v2 |
| revenue_cycle/workers/__init__.py | none | Empty |

---

## G) Critical Findings

### CRITICAL (runtime-breaking)

1. **CRITICAL-01: Subdomain BPMN topic format mismatch (billing, glosa, coding).** Three subdomain-level BPMNs (billing_submission.bpmn, glosa_management.bpmn, coding_audit.bpmn) use kebab-case topics (e.g., `billing-validate-claim`) while ALL workers register with dot-notation topics (e.g., `billing.validate_claim`). These will NEVER match at runtime in Camunda. 35 service tasks affected.

2. **CRITICAL-02: 26 BPMN topics reference workers that do not exist.** Across SP-RC-001/002 (8 topics), SP-RF-003 (9 topics), SP-RC-003/004 (3 topics), SP-RC-008/009/010 (7 topics), and glosa_management.bpmn (2 topics: auto-approve-appeal, handle-tiss-error). These are dead service tasks.

3. **CRITICAL-03: Collection workers use WORKER_TYPE without namespace prefix** but BPMNs reference them with namespace prefix (e.g., `collection.identify_overdue` vs bare `identify_overdue`). 13 workers affected.

4. **CRITICAL-04: Duplicate BPMN files with conflicting topic formats.** Billing has both SP-RC-006 (dot-notation topics) and billing/bpmn/billing_submission.bpmn (kebab-case topics). Similarly for glosa (SP-RC-007 vs glosa_management.bpmn) and coding (SP-RC-005 vs coding_audit.bpmn). It is unclear which is authoritative.

### HIGH

5. **HIGH-01: v1/v2 class name collision.** Billing v1 and v2 workers use identical class names (e.g., both `ValidateClaimWorker`). Simultaneous import will cause shadowing. __init__.py only imports v1.

6. **HIGH-02: 8 of 10 SP-RC BPMNs lack BPMNDI diagram sections.** Only SP-RC-001 has diagram elements. SP-RC-002 through SP-RC-010 have no visual layout data.

7. **HIGH-03: DMN duplicate subfolders.** Multiple categories have likely-duplicate subfolders from different creation waves: `code_compatibility` vs `compat`, `eligibility` vs `elig`, `tracking` vs `track`, `estimate` vs `estimates`. Risk of stale/conflicting rules.

8. **HIGH-04: glosa_management.bpmn has empty BPMNDI.** The BPMNDiagram element exists but contains no actual diagram shapes or edges.

### MEDIUM

9. **MEDIUM-01: __init__.py export gaps.** Billing exports 4/26, glosa exports 2/20, top-level exports 0/12. No v2 workers are exported anywhere.

10. **MEDIUM-02: Inconsistent BaseExternalTaskWorker adoption in coding v2.** Only 5/10 coding v2 workers extend BaseExternalTaskWorker; the other 5 use direct FederatedDMNService without the shared base.

11. **MEDIUM-03: generate_tiss_xml_worker_v2.py is a stub.** The _generate_xml method returns trivial placeholder XML, not real TISS 4.01 XML.

12. **MEDIUM-04: 3 glosa v1 workers lack BaseWorker.** check_appeal_eligibility, generate_appeal_documentation, and escalate_to_supervisor extend only GlosaWorkerMixin, not BaseWorker.

13. **MEDIUM-05: Collection workers have 162 total inline rules.** High-inline-rule workers (auto_matching: 13, alert_anomalies: 10, calculate_dso: 9, detect_revenue_leakage: 9, flag_discrepancies: 9, prioritize_collection: 9) should migrate to DMN tables.

14. **MEDIUM-06: Production tests in non-canonical location.** Tests exist at `revenue_cycle/production/tests/` instead of `tests/revenue_cycle/production/`.

---

## H) Recommendations

### Priority 1: Fix Runtime-Breaking Issues (Swarm: topic-alignment)

1. **Resolve duplicate BPMNs.** Decide which is authoritative per subdomain: the top-level SP-RC-00X files (dot-notation) or the subdomain-level files (kebab-case). Delete or deprecate the non-authoritative version.
2. **Standardize topic format to dot-notation** across all remaining BPMNs. Update the 35 kebab-case topics in subdomain BPMNs or delete those files.
3. **Add namespace prefix to collection WORKER_TYPE values.** Change bare `identify_overdue` to `collection.identify_overdue` to match BPMN references.
4. **Create missing workers** for the 26 BPMN topics that have no implementation, or remove those service tasks from BPMNs if they are not needed.

### Priority 2: Resolve v1/v2 Coexistence (Swarm: v2-migration)

5. **Rename v2 classes** to avoid collision with v1 (e.g., `ValidateClaimWorkerV2`). Glosa v2 already does this; billing v2 does not.
6. **Update all __init__.py** to export v2 workers (or remove v1 exports if v2 is the target).
7. **Standardize coding v2 to consistently use BaseExternalTaskWorker.** Migrate the 5 non-compliant workers.
8. **Complete generate_tiss_xml_worker_v2** -- replace stub with real TISS 4.01 XML generation.

### Priority 3: DMN Hygiene (Swarm: dmn-cleanup)

9. **Audit and deduplicate DMN subfolders.** Merge or remove `compat` vs `code_compatibility`, `elig` vs `eligibility`, `track` vs `tracking`, `estimate` vs `estimates`.
10. **Migrate collection inline rules to DMN.** The 6 workers with 9+ inline rules should externalize decision logic.

### Priority 4: BPMN Quality (Swarm: bpmn-diagrams)

11. **Add BPMNDI sections** to SP-RC-002 through SP-RC-010 for Camunda Modeler compatibility.
12. **Fix glosa_management.bpmn empty BPMNDI** -- populate with actual diagram elements.

### Priority 5: Structural Cleanup

13. **Fix glosa v1 workers missing BaseWorker** -- add BaseWorker to the 3 workers that only extend GlosaWorkerMixin.
14. **Move production tests** from `revenue_cycle/production/tests/` to `tests/revenue_cycle/production/`.
15. **Populate revenue_cycle/workers/__init__.py** with financial worker exports.
