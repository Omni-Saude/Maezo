# Healthcare-Orchest-CIB7 Test Suite

Comprehensive DMN and integration tests for the CIB7 Healthcare Orchestrator platform.

## Test Structure

```
tests/
├── dmn/                                    # DMN decision table tests
│   ├── test_billing_dmn.py                # 15 billing DMN tables
│   ├── test_clinical_dmn.py               # 10 clinical DMN tables
│   ├── test_coding_audit_dmn.py           # 10 coding/audit DMN tables
│   ├── test_glosa_prevention_dmn.py       # 10 glosa prevention DMN tables
│   └── test_access_control_dmn.py         # 5 access control DMN tables
└── integration/
    ├── patient_access/                     # Patient access integration tests
    │   ├── test_validate_patient_data_integration.py
    │   ├── test_create_appointment_integration.py
    │   ├── test_verify_insurance_coverage_integration.py
    │   ├── test_create_patient_record_integration.py
    │   ├── test_check_pre_authorization_integration.py
    │   └── test_handle_cancellation_integration.py
    └── platform_services/                  # Platform services integration tests
        ├── test_analyze_denial_patterns_integration.py
        ├── test_detect_revenue_leakage_integration.py
        ├── test_generate_regulatory_reports_integration.py
        ├── test_monitor_system_health_integration.py
        ├── test_sync_erp_data_integration.py
        └── test_reconcile_data_sources_integration.py
```

## DMN Tests (50 Decision Tables)

DMN tests validate the structure and logic of decision tables across 5 categories:

### Billing DMN Tests (15 tables)
- `Billing_Calculation` - Core billing calculation logic
- `CBHPM_Mapping` - CBHPM procedure code mapping
- `Contract_Rules_Amil` - Amil insurance contract rules
- `Contract_Rules_Bradesco` - Bradesco insurance contract rules
- `Contract_Rules_SulAmerica` - SulAmerica insurance contract rules
- `Contract_Rules_Unimed` - Unimed insurance contract rules
- `Copay_Calculation` - Patient copayment calculation
- `Discount_Rules` - Billing discount rules
- `OPME_Pricing` - Medical equipment pricing
- `Package_Pricing` - Procedure package pricing
- `Revenue_Projection` - Revenue forecasting
- `SUS_Table_Lookup` - SUS procedure table lookup
- `Tax_Calculation` - Tax calculation logic
- `TISS_Format_Rules` - TISS format validation
- `Billing_Deadline` - Billing deadline rules

### Clinical DMN Tests (10 tables)
- `Blood_Transfusion` - Blood transfusion protocols
- `Clinical_Protocol` - Clinical care protocols
- `Discharge_Readiness` - Patient discharge criteria
- `Fall_Risk` - Fall risk assessment
- `ICU_Admission` - ICU admission criteria
- `Medication_Interaction` - Drug interaction checking
- `Nutrition_Assessment` - Nutritional assessment
- `Pressure_Injury_Risk` - Pressure ulcer risk
- `Sepsis_Risk` - Sepsis risk scoring
- `Triage_Priority` - Emergency triage priority (RED/ORANGE/YELLOW/GREEN/BLUE)

### Coding/Audit DMN Tests (10 tables)
- `Audit_Sampling` - Audit sample selection
- `CBHPM_Mapping` - CBHPM code mapping for audits
- `Code_Mapping_Legacy` - Legacy code translation
- `Coding_Completeness` - Documentation completeness
- `DRG_Assignment` - DRG classification
- `ICD10_Validation` - ICD-10 code validation with age group and encounter type rules
- `Medical_Necessity` - Medical necessity determination
- `Procedure_Compatibility` - Procedure combination validation
- `TUSS_Validation` - TUSS code validation
- `Upcoding_Detection` - Upcoding pattern detection

### Glosa Prevention DMN Tests (10 tables)
- `Appeal_Viability` - Appeal success prediction
- `Batch_Validation` - Batch validation rules
- `Compliance_Check` - Regulatory compliance checking
- `Deadline_Monitor` - Deadline tracking
- `Documentation_Checklist` - Required documentation
- `Glosa_Risk_Score` - Glosa risk scoring (CRITICAL/HIGH/MEDIUM/LOW)
- `Negotiation_Strategy` - Payer negotiation strategy
- `Payer_Rules_Engine` - Payer-specific rules
- `Recovery_Prediction` - Recovery probability
- `Root_Cause_Classification` - Glosa root cause analysis

### Access Control DMN Tests (5 tables)
- `Audit_Trail_Rules` - Audit logging rules
- `Consent_Management` - Patient consent rules
- `Data_Access_Policy` - Data access policies
- `PHI_Masking_Rules` - PHI masking/de-identification
- `User_Permissions` - Role-based access control (ADMIN/PHYSICIAN/NURSE/BILLING_ANALYST/AUDITOR)

## DMN Test Features

Each DMN test validates:

1. **Structure**: Decision, decision table, and hit policy existence
2. **Multi-tenant Support**: `tenantId` input column presence
3. **Input/Output Columns**: Expected columns are defined
4. **Portuguese Labels**: Localized labels are present
5. **Hit Policy**: Typically `FIRST` for deterministic results
6. **Rule Logic**: Parametrized tests for key decision scenarios
7. **Edge Cases**: Boundary values, null inputs, validation

### Example DMN Test Pattern

```python
@pytest.mark.dmn
class TestBillingCalculationDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("billing", "Billing_Calculation")

    def test_dmn_structure_valid(self, dmn_root):
        """Test that DMN has valid structure."""
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        """Verify tenantId input exists for multi-tenant support."""
        # ...

    @pytest.mark.parametrize("procedure_type,insurance,expected_rule", [
        ("SURGICAL", "SUS", "SUS_SURGICAL_STANDARD"),
        ("CLINICAL", "CBHPM", "CBHPM_CLINICAL_MARKUP"),
    ])
    def test_decision_rules_logic(self, dmn_root, procedure_type, insurance, expected_rule):
        """Test decision table rules match expected business logic."""
        # ...
```

## Integration Tests (12 Workers)

Integration tests validate end-to-end worker execution with mocked CIB7 engine.

### Patient Access Integration Tests (6 workers)

1. **Validate Patient Data** (`test_validate_patient_data_integration.py`)
   - CPF/CNS validation and hashing
   - Demographic data validation
   - PII protection (SHA-256 hashing)
   - Multi-tenant isolation

2. **Create Appointment** (`test_create_appointment_integration.py`)
   - Appointment scheduling
   - Resource allocation
   - Variable passing between BPMN tasks

3. **Verify Insurance Coverage** (`test_verify_insurance_coverage_integration.py`)
   - ANS eligibility verification
   - FHIR Coverage resource creation
   - Compensation handling

4. **Create Patient Record** (`test_create_patient_record_integration.py`)
   - FHIR Patient resource creation
   - Medical record number assignment
   - Process correlation

5. **Check Pre-Authorization** (`test_check_pre_authorization_integration.py`)
   - Pre-authorization status verification
   - Authorization number tracking

6. **Handle Cancellation** (`test_handle_cancellation_integration.py`)
   - Appointment cancellation
   - Resource release
   - Rebooking slot suggestions

### Platform Services Integration Tests (6 workers)

1. **Analyze Denial Patterns** (`test_analyze_denial_patterns_integration.py`)
   - Denial pattern identification
   - Recovery potential calculation
   - Top denial reason ranking

2. **Detect Revenue Leakage** (`test_detect_revenue_leakage_integration.py`)
   - Revenue leakage detection
   - Loss estimation
   - Threshold-based alerting

3. **Generate Regulatory Reports** (`test_generate_regulatory_reports_integration.py`)
   - ANS quarterly reports
   - TISS monthly reports
   - Report validation

4. **Monitor System Health** (`test_monitor_system_health_integration.py`)
   - Health status monitoring
   - CPU/memory usage tracking
   - Error rate detection

5. **Sync ERP Data** (`test_sync_erp_data_integration.py`)
   - Incremental data synchronization
   - Record count tracking
   - Sync status reporting

6. **Reconcile Data Sources** (`test_reconcile_data_sources_integration.py`)
   - Cross-database reconciliation
   - Discrepancy detection
   - Match rate calculation

## Integration Test Pattern

Each integration test includes:

1. **End-to-End Process**: Complete workflow with mocked dependencies
2. **Variable Passing**: Verify BPMN process variables flow correctly
3. **Compensation Handler**: Test BPMN error compensation
4. **Process Correlation**: Test correlation keys and instance tracking
5. **Multi-Tenant Isolation**: Verify tenant context separation

### Example Integration Test Pattern

```python
@pytest.mark.integration
@pytest.mark.slow
class TestValidatePatientDataIntegration:
    @pytest.fixture
    def worker(self, mock_validator):
        return ValidatePatientDataWorker(validator=mock_validator)

    @pytest.mark.asyncio
    async def test_end_to_end_process(self, worker):
        """Test complete validation process flow."""
        task_variables = {
            "cpf": "12345678901",
            "name": "João da Silva",
            "birth_date": "1980-05-15",
            "gender": "male",
            "tenantId": "hospital-123",
        }

        result = await worker.execute(task_variables)

        assert result["is_valid"] is True
        assert "cpf_hash" in result

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, worker):
        """Test that tenant context is properly maintained."""
        # ...
```

## Running Tests

### Run All Tests
```bash
pytest tests/
```

### Run DMN Tests Only
```bash
pytest tests/dmn/ -v
```

### Run Integration Tests Only
```bash
pytest tests/integration/ -v -m integration
```

### Run Specific DMN Category
```bash
pytest tests/dmn/test_billing_dmn.py -v
pytest tests/dmn/test_clinical_dmn.py -v
pytest tests/dmn/test_coding_audit_dmn.py -v
pytest tests/dmn/test_glosa_prevention_dmn.py -v
pytest tests/dmn/test_access_control_dmn.py -v
```

### Run Specific Integration Category
```bash
pytest tests/integration/patient_access/ -v
pytest tests/integration/platform_services/ -v
```

### Run Slow Tests
```bash
pytest tests/ -v -m slow
```

### Skip Slow Tests
```bash
pytest tests/ -v -m "not slow"
```

## Test Markers

- `@pytest.mark.dmn` - DMN decision table tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.slow` - Slow-running tests (integration tests)
- `@pytest.mark.asyncio` - Async tests

## Test Coverage

### DMN Test Coverage
- 50 decision tables across 5 categories
- ~200+ individual test cases
- Structure validation, multi-tenant support, business logic

### Integration Test Coverage
- 12 critical path workers (6 patient access + 6 platform services)
- ~60+ test cases
- End-to-end flows, error handling, multi-tenant isolation

## Prerequisites

```bash
pip install pytest pytest-asyncio
```

## Key Testing Principles

1. **Multi-Tenant Isolation**: All tests verify tenant context is maintained
2. **PII Protection**: Patient data is hashed (SHA-256) before storage
3. **BPMN Compensation**: Error handling and compensation flows tested
4. **Portuguese Localization**: DMN labels and error messages in Portuguese
5. **Parametrized Tests**: Multiple scenarios tested with same test logic
6. **Mocked Dependencies**: External services mocked for isolated testing

## CI/CD Integration

Tests are designed to run in CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run DMN Tests
  run: pytest tests/dmn/ -v --junitxml=dmn-results.xml

- name: Run Integration Tests
  run: pytest tests/integration/ -v -m integration --junitxml=integration-results.xml
```

## Test Data

DMN files are located at:
```
platform/dmn/
├── billing/           # 15 DMN files
├── clinical/          # 10 DMN files
├── coding_audit/      # 10 DMN files
├── glosa_prevention/  # 10 DMN files
└── access_control/    # 5 DMN files
```

Worker implementations are located at:
```
platform/
├── patient_access/workers/
└── platform_services/workers/
```

## Contributing

When adding new DMN tables or workers:

1. **Add DMN Test**: Create test class in appropriate `test_*_dmn.py` file
2. **Add Integration Test**: Create `test_*_integration.py` file
3. **Follow Patterns**: Use existing test patterns as templates
4. **Verify Multi-Tenant**: Always test tenant isolation
5. **Test Edge Cases**: Include null, boundary, and error cases

## License

Part of CIB7 Healthcare Orchestrator Platform
