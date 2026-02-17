# Coding Worker Test Fixes - Summary

## Current Status
- **Total Tests**: 155
- **Passing**: 88 (57%)
- **Failing**: 67 (43%)
- **Previous**: 74 failures → **7 tests fixed**

## Changes Made

### 1. Fixed `__init__.py` Exports
- Added V1-compatible Input/Output models for all coding workers
- V1 models use snake_case field names (risk_score, risk_level, flags)
- V2 workers use camelCase with aliases (fraudRiskScore, fraudAlerts)
- Tests can now import and instantiate models without validation errors

### 2. Enhanced DMN Mock in `conftest.py`
- Made mock_dmn_service smart about table names
- Returns appropriate responses for:
  - fraud_scoring tables (alerts, score)
  - risk_thresholds (recommendation based on risk_score)
  - audit_approval (resultado based on audit_recommendation)
  - fraud_clearance (resultado based on fraud_recommendation)
  - confidence_boosting (suggestions)
  - format_validation (valid_suggestions)

## Remaining Failures (67 tests)

### Category 1: Worker Constructor Mismatches (Most Common)
**Issue**: V1 tests instantiate workers with V1-specific dependencies (fraud_engine, rules_engine, nlp_engine, etc.) that V2 workers don't accept or use.

**Example**:
```python
# Test code:
worker = DetectFraudWorker(fraud_engine=mock_fraud_engine)

# V2 worker only accepts:
def __init__(self, dmn_service: FederatedDMNService | None = None, fraud_engine: Any = None, **kwargs)
    # fraud_engine is accepted but NOT USED (DMN-only)
```

**Files Affected**:
- `test_apply_coding_rules_worker.py` (3 failures)
- `test_audit_coding_worker.py` (5 failures)
- `test_calculate_complexity_worker.py` (6 failures)
- `test_check_code_compatibility_worker.py` (6 failures)
- `test_extract_clinical_data_worker.py` (5 failures)
- `test_finalize_coding_worker.py` (6 failures)
- `test_suggest_cid10_worker.py` (5 failures)
- `test_suggest_tuss_worker.py` (5 failures)
- `test_validate_codes_worker.py` (6 failures)

**Fix Required**: Either:
1. Update tests to use dmn_service instead of mock engines, OR
2. Make V2 workers actually use the injected engines (breaks DMN-only design), OR  
3. Create test-specific worker variants that accept both

### Category 2: Input Model Validation
**Issue**: Tests try to instantiate Input models with empty required fields.

**Example**:
```python
# Test expects ValueError:
with pytest.raises((ValueError, TypeError)):
    CalculateComplexityInput(encounter_id="ENC-001", cid10_codes=[], tuss_codes=[], age=-5)
```

**Files Affected**:
- `test_calculate_complexity_worker.py::test_negative_age_raises`
- `test_validate_codes_worker.py::test_empty_codes_raises`
- Others where min_length/validation is expected

**Fix Required**: V1 compat models need proper field validators to match V2 behavior.

### Category 3: Output Assertions
**Issue**: Tests assert on output fields that V2 workers don't produce.

**Example**:
```python
# Test expects:
assert out.all_valid == True

# V2 ValidateCodesOutput has different fields
```

**Fix Required**: Update Output model assertions to match V2 actual output schema.

## Recommended Next Steps

### Quick Win: Fix Input Models (5-10 tests)
Add field validators to V1 compat Input models:
```python
class CalculateComplexityInput(BaseModel):
    encounter_id: str
    cid10_codes: list[dict[str, Any]] = Field(default_factory=list)
    tuss_codes: list[dict[str, Any]] = Field(default_factory=list)
    age: int = Field(default=0, ge=0)  # Add validation

    @field_validator("age")
    @classmethod
    def validate_age(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Age cannot be negative")
        return v
```

### Medium Effort: Update DMN Mocking Strategy (20-30 tests)
Instead of mocking individual engines, provide comprehensive DMN mock fixtures:
```python
@pytest.fixture
def mock_dmn_with_violations(mock_dmn_service):
    """DMN service that returns violations/errors."""
    def evaluate_with_errors(*args, **kwargs):
        if "quantity_limits" in kwargs.get("table_name", ""):
            return {"resultado": "BLOQUEAR", "violations": ["Quantity exceeds limit"]}
        return {"resultado": "PROSSEGUIR"}
    mock_dmn_service.evaluate.side_effect = evaluate_with_errors
    return mock_dmn_service
```

### Large Effort: Rewrite Worker Tests (30-40 tests)
For workers where V2 behavior is fundamentally different:
1. Keep V1 tests as-is (mark with `@pytest.mark.skip(reason="V1 only")`)
2. Create new V2 test files focusing on DMN integration
3. Test actual V2 behavior (dict inputs, camelCase outputs, DMN-driven logic)

## Files That Need Attention

### High Priority (Most Failures)
1. `test_calculate_complexity_worker.py` (6 failures) - Input validation
2. `test_finalize_coding_worker.py` (6 failures) - Constructor + assertions
3. `test_validate_codes_worker.py` (6 failures) - Output schema mismatch
4. `test_check_code_compatibility_worker.py` (6 failures) - Mock dependencies

### Medium Priority
5. `test_audit_coding_worker.py` (5 failures)
6. `test_extract_clinical_data_worker.py` (5 failures)
7. `test_suggest_cid10_worker.py` (5 failures)
8. `test_suggest_tuss_worker.py` (5 failures)

### Already Improved
- `test_detect_fraud_worker.py` - Output model now compatible
- Input/Output instantiation tests - V1 compat models work

## Conclusion

**Progress Made**: 7 tests fixed by providing V1-compatible Input/Output models.

**Main Blocker**: V1 tests expect workers to use injected mock engines (fraud_engine, rules_engine, etc.), but V2 workers are DMN-only and ignore these dependencies.

**Decision Needed**: 
- Keep V1 tests as legacy and write new V2 tests? OR
- Make V2 workers accept and use both DMN and injected dependencies for test compatibility?

The cleanest path forward is likely option #1 (legacy V1 tests + new V2 tests) to avoid polluting V2 production code with test-only logic.
