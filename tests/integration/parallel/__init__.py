"""
Integration Tests for Java vs Python Parallel Comparison
=========================================================

This package contains integration tests that validate behavioral compatibility
between Java Camunda 7 JavaDelegates and Python Camunda 8 External Task Workers.

The tests use testcontainers to spin up both Java and Python services and compare
their outputs for identical inputs to ensure 100% behavioral compatibility.

Test Structure:
- conftest.py: Fixtures, Java/Python clients, testcontainers setup
- comparison_utils.py: Result comparison logic with semantic matching
- test_parallel_analyze_glosa.py: AnalyzeGlosa worker comparison
- test_parallel_create_provision.py: CreateProvision worker comparison
- test_parallel_apply_contract_rules.py: ApplyContractRules worker comparison
- test_parallel_generate_claim.py: GenerateClaim worker comparison

Rollback Triggers (ANY triggers rollback):
- Error rate > 5% (sustained for 5 minutes)
- P95 latency > 2x Java baseline
- Mismatch rate > 1%
- Critical business logic failure (any)

Author: Revenue Cycle Development Team
Version: 1.0.0
Date: 2026-02-04
"""
