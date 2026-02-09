# Billing Workers - Phase 2.3 Implementation

## Overview

This document describes the Phase 2.3 billing workers for the Healthcare Orchestrator platform. These workers handle the core billing calculations and rule applications for Brazilian healthcare billing (TISS standard).

## Architecture

### Base Worker

**File**: `platform/revenue_cycle/billing/workers/base.py`

The `BaseWorker` class provides:
- Standard error handling with `DomainException` catching
- BPMN error mapping
- Logging and observability
- Worker registration via `@worker` decorator
- Standardized result types (`WorkerResult`)

### Worker Pattern

All workers follow this pattern:
```python
@worker(topic="billing-xxx", max_jobs=1, lock_duration=300000)
class MyWorker(BaseWorker):
    @property
    def operation_name(self) -> str:
        return _("Operation description in Portuguese")

    async def process_task(self, job, variables) -> WorkerResult:
        # Validate inputs
        # Process logic
        # Return WorkerResult.ok() or raise exception
```

## Implemented Workers

### 1. GroupByGuideWorker

**Topic**: `billing-group-by-guide`
**File**: `platform/revenue_cycle/billing/workers/group_by_guide_worker.py`

Groups encounter procedures by TISS guide type for proper submission.

**Input Variables**:
- `encounter_id`: str - Encounter identifier
- `procedures`: List[Dict] - Procedures with code, type, quantity

**Output Variables**:
- `grouped_guides`: Dict[str, List] - Procedures grouped by guide type
- `guide_count`: int - Number of different guide types
- `total_procedures`: int - Total procedure count

**Features**:
- Maps procedure types to TISS guide types (CONSULTATION, SP_SADT, ADMISSION, etc.)
- Supports Portuguese and English type names
- Uses TUSS code patterns for classification fallback
- Validates and enriches procedures with CodedValue
- Comprehensive error handling with Portuguese messages

**TISS Guide Types**:
- `CONSULTATION` - Consultations and ambulatory care
- `SP_SADT` - Services, procedures, diagnostics, and therapy
- `ADMISSION` - Inpatient admissions
- `EXTENSION` - Stay extensions
- `HONORARIOS` - Professional fees
- `SUMMARY` - Summary reports

### 2. ApplyContractRulesWorker

**Topic**: `billing-apply-contract-rules`
**File**: `platform/revenue_cycle/billing/workers/apply_contract_rules_worker.py`

Applies payer-specific contract rules including co-payments, deductibles, and coverage limits.

**Input Variables**:
- `claim_id`: str - Claim identifier
- `payer_id`: str - Payer identifier
- `procedures`: List[Dict] - Procedures with pricing
- `contract_rules`: Dict - Rules with copay_pct, deductible, coverage_limit, procedure_limits

**Output Variables**:
- `adjusted_items`: List[Dict] - Items with adjustments applied
- `total_patient_responsibility`: Decimal - Patient amount
- `total_payer_responsibility`: Decimal - Payer amount
- `total_charges`: Decimal - Total before adjustments
- `applied_rules`: Dict - Summary of applied rules

**Features**:
- Co-payment percentage calculation (0-100%)
- Deductible application with exhaustion tracking
- Coverage limit enforcement
- Per-procedure limits
- Money type for all calculations
- Comprehensive validation

**Calculation Logic**:
1. Apply procedure-specific limits
2. Calculate co-payment (percentage of base amount)
3. Apply deductible (if remaining balance)
4. Calculate payer and patient responsibilities
5. Enforce overall coverage limit

### 3. CalculateChargesWorker

**Topic**: `billing-calculate-charges`
**File**: `platform/revenue_cycle/billing/workers/calculate_charges_worker.py`

Calculates line items with proper monetary handling and modifier adjustments.

**Input Variables**:
- `procedures`: List[Dict] - Procedures with code, quantity, unit_price
- `modifiers`: Optional[List[Dict]] - Modifiers with type, value, applies_to

**Output Variables**:
- `line_items`: List[Dict] - Calculated line items
- `total_amount`: Decimal - Total amount
- `modifier_adjustments`: Decimal - Total adjustments

**Features**:
- Quantity-based pricing
- Percentage and fixed modifiers
- Selective modifier application (by code or wildcard)
- Multiple modifiers per procedure
- Standard modifier type defaults
- Negative price prevention

**Standard Modifiers**:
- `multiple_procedure`: -50% (additional procedures)
- `assistant_surgeon`: +20% (assistant fees)
- `bilateral`: +50% (bilateral procedures)
- `unusual_circumstances`: +25%
- `professional_component`: -40%
- `technical_component`: -60%

### 4. ApplyDiscountsWorker

**Topic**: `billing-apply-discounts`
**File**: `platform/revenue_cycle/billing/workers/apply_discounts_worker.py`

Applies contractual discounts based on various conditions.

**Input Variables**:
- `line_items`: List[Dict] - Line items with total_price
- `discount_rules`: List[Dict] - Rules with type, percentage, conditions

**Output Variables**:
- `discounted_items`: List[Dict] - Items with discounts
- `total_discount`: Decimal - Total discount amount
- `final_amount`: Decimal - Final billable amount
- `original_amount`: Decimal - Original total
- `discount_percentage`: Decimal - Overall discount percentage

**Features**:
- Volume-based tiered discounts
- Contractual and promotional discounts
- Conditional application (code, quantity, amount)
- Wildcard procedure code matching
- Multiple discount stacking
- Detailed discount tracking per item

**Discount Types**:
- `volume` - Quantity-based with tiers (20+, 50+, 100+ units)
- `early_payment` - Early payment incentive
- `package` - Package deal pricing
- `promotional` - Promotional campaigns
- `contractual` - Standard contract terms
- `senior` - Senior citizen discount
- `emergency` - Emergency service discount

**Volume Discount Tiers**:
- 20-49 units: +15% discount bonus
- 50-99 units: +30% discount bonus
- 100+ units: +50% discount bonus

## Testing

### Test Coverage

Each worker has comprehensive test coverage including:
- Happy path scenarios
- Error conditions (missing/invalid inputs)
- Edge cases (zero values, limits, negative amounts)
- Multiple rule combinations
- Portuguese i18n strings

### Test Files

- `tests/revenue_cycle/billing/workers/test_group_by_guide_worker.py` - 300+ lines
- `tests/revenue_cycle/billing/workers/test_apply_contract_rules_worker.py` - 300+ lines
- `tests/revenue_cycle/billing/workers/test_calculate_charges_worker.py` - 450+ lines
- `tests/revenue_cycle/billing/workers/test_apply_discounts_worker.py` - 500+ lines

### Running Tests

```bash
# Run all billing worker tests
pytest tests/revenue_cycle/billing/workers/

# Run specific worker tests
pytest tests/revenue_cycle/billing/workers/test_group_by_guide_worker.py -v

# Run with coverage
pytest tests/revenue_cycle/billing/workers/ --cov=platform/revenue_cycle/billing/workers
```

## Integration

### BPMN Integration

These workers are designed to be called from BPMN service tasks:

```xml
<bpmn:serviceTask id="GroupByGuide" name="Agrupar por Guia">
  <bpmn:extensionElements>
    <zeebe:taskDefinition type="billing-group-by-guide" />
  </bpmn:extensionElements>
</bpmn:serviceTask>
```

### Workflow Sequence

Typical billing workflow sequence:
1. **GroupByGuideWorker** - Organize procedures by guide type
2. **CalculateChargesWorker** - Calculate base charges with modifiers
3. **ApplyContractRulesWorker** - Apply payer contract rules
4. **ApplyDiscountsWorker** - Apply applicable discounts

### Error Handling

All workers raise domain-specific exceptions:
- `BillingException` - General billing errors
- `ContractRuleViolation` - Contract rule violations
- `DomainException` - Base exception with BPMN error codes

BPMN error codes are automatically mapped for process error handling.

## Money Handling

All monetary calculations use the `Money` value object:

```python
from platform.shared.domain.value_objects import Money

# Create money values
price = Money.brl(Decimal("100.00"))
zero = Money.zero()

# Arithmetic
total = price * Decimal("2")  # Money object
sum_total = price + price      # Money object

# Access amount
amount = total.amount  # Decimal
```

## Internationalization

All user-facing strings use the `_()` translation function:

```python
from platform.shared.i18n import _

message = _("ID do encontro é obrigatório")
formatted = _("Código TUSS inválido: {code}").format(code=proc_code)
```

## Dependencies

### Platform Shared Modules
- `platform.shared.domain.value_objects.Money` - BRL money type
- `platform.shared.domain.entities` - FHIR entities
- `platform.shared.domain.enums` - TISSGuideType, etc.
- `platform.shared.domain.exceptions` - Exception hierarchy
- `platform.shared.domain.value_objects.CodedValue` - TUSS/CID codes
- `platform.shared.i18n._` - Translation function
- `platform.shared.observability.logging` - Logging

### External Packages
- `decimal.Decimal` - Precise decimal arithmetic
- `pytest` - Testing framework
- `pytest-asyncio` - Async test support

## File Structure

```
platform/
├── revenue_cycle/
│   └── billing/
│       └── workers/
│           ├── __init__.py
│           ├── base.py (165 lines)
│           ├── group_by_guide_worker.py (330 lines)
│           ├── apply_contract_rules_worker.py (395 lines)
│           ├── calculate_charges_worker.py (420 lines)
│           └── apply_discounts_worker.py (445 lines)
tests/
└── revenue_cycle/
    └── billing/
        └── workers/
            ├── __init__.py
            ├── test_group_by_guide_worker.py (310 lines)
            ├── test_apply_contract_rules_worker.py (350 lines)
            ├── test_calculate_charges_worker.py (470 lines)
            └── test_apply_discounts_worker.py (520 lines)
```

## Future Enhancements

1. **Performance Optimization**
   - Batch processing for large claim sets
   - Caching of contract rules
   - Parallel processing of independent line items

2. **Additional Features**
   - Time-based discount validation
   - Multi-currency support
   - Advanced bundling logic
   - Real-time price lookup integration

3. **Reporting**
   - Discount utilization reports
   - Contract compliance metrics
   - Revenue impact analysis

## Related Documentation

- [Platform Architecture](../architecture/overview.md)
- [TISS Standard Guide](./tiss-standard.md)
- [Domain Model](../architecture/domain-model.md)
- [Testing Strategy](../testing/strategy.md)
