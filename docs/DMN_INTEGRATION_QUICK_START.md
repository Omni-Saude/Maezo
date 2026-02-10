# DMN Integration Quick Start Guide

**Target**: Developers working with patient_access workers  
**Last Updated**: 2026-02-09

## Overview

All 23 patient_access workers are now integrated with the FederatedDMNService for dynamic, tenant-aware business rule evaluation.

## Basic Pattern

### 1. Import the Service

```python
from platform.shared.dmn.federation_service import FederatedDMNService
```

### 2. Initialize in Stub Class

```python
class StubMyChecker(MyChecker):
    def __init__(self):
        self.dmn_service = FederatedDMNService()
```

### 3. Call DMN with Fallback

```python
async def my_method(self, input_data: str) -> dict[str, Any]:
    tenant_id = get_required_tenant()
    
    try:
        result = self.dmn_service.evaluate(
            tenant_id=tenant_id,
            category='authorization',
            table_name='auth_xxx_001',
            inputs={'input_key': input_data}
        )
        return result
    except (FileNotFoundError, ValueError) as e:
        # Fallback to hardcoded logic
        logger.warning(f"DMN unavailable, using fallback: {e}")
        return self._fallback_logic(input_data)
```

## DMN Table Reference

### Category: authorization

All patient_access workers use `category='authorization'`.

### Available Subcategories

| Subcategory | Table Prefix | Count | Example |
|-------------|--------------|-------|---------|
| Urgency | `auth_urgency_` | 5 | `auth_urgency_001` |
| Documentation | `auth_documentation_` | 5 | `auth_documentation_001` |
| Pre-Auth | `auth_preauth_` | 10 | `auth_preauth_001` |
| Scope | `auth_scope_` | 5 | `auth_scope_001` |
| Timing | `auth_timing_` | 8 | `auth_timing_001` |
| Coding | `auth_coding_` | 5 | `auth_coding_001` |
| Appeal | `auth_appeal_` | 5 | `auth_appeal_001` |
| Federated | `fed_auth_` | 2 | `fed_auth_001` |

## Common Use Cases

### Check Authorization Requirements

```python
result = self.dmn_service.evaluate(
    tenant_id=tenant_id,
    category='authorization',
    table_name='auth_urgency_001',
    inputs={'procedure_code': '40101010'}
)
# Returns: {requires_authorization: bool, authorization_type: str, ...}
```

### Validate Documentation

```python
result = self.dmn_service.evaluate(
    tenant_id=tenant_id,
    category='authorization',
    table_name='auth_documentation_002',
    inputs={
        'document_type': 'insurance_card',
        'expiry_date': '2026-12-31'
    }
)
# Returns: {is_valid: bool, reason: str, days_until_expiry: int}
```

### Check Timing Rules

```python
result = self.dmn_service.evaluate(
    tenant_id=tenant_id,
    category='authorization',
    table_name='auth_timing_003',
    inputs={
        'service_type': 'consulta',
        'proposed_datetime': '2026-02-09T14:00:00'
    }
)
# Returns: {violations: [...], warnings: [...]}
```

## Tenant-Specific Overrides

### Create Tenant Override

1. Create directory structure:
```bash
mkdir -p platform/shared/dmn/tenant_overrides/{tenant_id}/authorization/
```

2. Copy base DMN and modify:
```bash
cp platform/patient_access/dmn/authorization/auth_urgency_001.dmn \
   platform/shared/dmn/tenant_overrides/hospital-xyz/authorization/
```

3. Edit the copied file with tenant-specific rules

4. FederatedDMNService automatically merges tenant overrides with base rules

### Override Behavior

- Tenant overrides **take priority** over base rules
- Rules are matched by `rule_id` attribute
- New rules can be added to tenant overrides
- Base rules remain unchanged

## Testing DMN Integration

### Unit Test Example

```python
from unittest.mock import Mock, patch

async def test_dmn_integration():
    # Mock DMN service
    mock_dmn = Mock()
    mock_dmn.evaluate.return_value = {
        'requires_authorization': True,
        'authorization_type': 'prior'
    }
    
    # Inject mock
    checker = StubAuthorizationRequirementChecker()
    checker.dmn_service = mock_dmn
    
    # Test
    result = await checker.check_ans_rules('40101010')
    
    # Verify
    assert result['requires_authorization'] is True
    mock_dmn.evaluate.assert_called_once()
```

### Test Fallback Logic

```python
async def test_dmn_fallback():
    checker = StubAuthorizationRequirementChecker()
    
    # Mock DMN to raise FileNotFoundError
    checker.dmn_service.evaluate = Mock(side_effect=FileNotFoundError())
    
    # Should fall back to hardcoded logic
    result = await checker.check_ans_rules('40101010')
    
    # Verify fallback worked
    assert 'requires_authorization' in result
```

## Troubleshooting

### DMN File Not Found

```
FileNotFoundError: DMN file not found: .../auth_xxx_001.dmn
```

**Solution**: Ensure DMN file exists in correct location:
```
platform/patient_access/dmn/authorization/auth_xxx_001.dmn
```

### DMN Evaluation Error

```
ValueError: No matching DMN rules found
```

**Solution**: Check inputs match DMN table input columns. Enable debug logging:
```python
import logging
logging.getLogger('platform.shared.dmn').setLevel(logging.DEBUG)
```

### Tenant Context Missing

```
RuntimeError: Tenant context not set
```

**Solution**: Ensure worker method is decorated with `@require_tenant`:
```python
@require_tenant
async def execute(self, task_variables: dict[str, Any]):
    ...
```

## Performance Tips

1. **Caching**: DMN tables are cached for 300s (5 minutes)
2. **Batch Evaluation**: Evaluate multiple rules in single call when possible
3. **Monitor**: Add metrics for DMN evaluation latency
4. **Optimize Inputs**: Only pass necessary input keys to DMN

## Best Practices

1. Always use try-except for DMN calls
2. Always provide fallback logic
3. Use descriptive input key names
4. Log DMN evaluation failures at WARNING level
5. Document expected DMN outputs in docstrings
6. Keep DMN inputs simple (strings, numbers, booleans)
7. Test both DMN and fallback paths

## Related Documentation

- [DMN Integration Guide](DMN_PATIENT_ACCESS_WIRING.md)
- [Validation Report](DMN_PATIENT_ACCESS_VALIDATION_REPORT.txt)
- [ADR-007: DMN Federation Service](ADRs/007-dmn-federation-service.md)
- [FederatedDMNService Source](../platform/shared/dmn/federation_service.py)

## Support

For questions or issues:
1. Check validation report: `docs/DMN_PATIENT_ACCESS_VALIDATION_REPORT.txt`
2. Review worker examples in `platform/patient_access/workers/`
3. Consult ADR-007 for architecture decisions
4. Contact platform team for DMN table schemas

---

**Quick Reference Card** 📋

```python
# 1. Import
from platform.shared.dmn.federation_service import FederatedDMNService

# 2. Initialize
self.dmn_service = FederatedDMNService()

# 3. Evaluate with fallback
try:
    result = self.dmn_service.evaluate(
        tenant_id=get_required_tenant(),
        category='authorization',
        table_name='auth_xxx_001',
        inputs={...}
    )
except (FileNotFoundError, ValueError):
    result = fallback_logic()
```
