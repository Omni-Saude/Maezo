"""Example usage of ANS Rol de Procedimentos integration."""

import asyncio
from decimal import Decimal

from revenue_cycle.config import Settings
from revenue_cycle.integrations.ans import RolClient
from revenue_cycle.integrations.ans.models import (
    ProcedureStatus,
    RolSearchRequest,
)


async def example_validate_procedure():
    """Example: Validate a single procedure code."""
    settings = Settings()

    async with RolClient(settings, tenant_id="hospital-001") as client:
        # Validate procedure
        result = await client.validate_procedure("10101012")

        print(f"Procedure Code: {result.procedure_code}")
        print(f"Is Valid: {result.is_valid}")
        print(f"Is Covered: {result.is_covered}")
        print(f"Status: {result.status.value if result.status else 'unknown'}")
        print(f"Cached: {result.cached}")

        if result.error_message:
            print(f"Warning: {result.error_message}")


async def example_search_procedures():
    """Example: Search procedures by category."""
    settings = Settings()

    async with RolClient(settings, tenant_id="hospital-001") as client:
        # Search for all active consultation procedures
        request = RolSearchRequest(
            category="Consulta",
            status=ProcedureStatus.ACTIVE,
            limit=10,
        )

        response = await client.search_procedures(request)

        print(f"Total Results: {response.total_count}")
        print(f"Rol Version: {response.rol_version}")
        print(f"\nProcedures:")

        for proc in response.procedures:
            print(f"  {proc.procedure_code}: {proc.description}")
            print(f"    Coverage: {proc.coverage_type.value}")
            print(f"    Requires Auth: {proc.requires_authorization}")
            print()


async def example_get_procedure_details():
    """Example: Get detailed information about a procedure."""
    settings = Settings()

    async with RolClient(settings, tenant_id="hospital-001") as client:
        # Get procedure details
        procedure = await client.get_procedure("10101012")

        print(f"Code: {procedure.procedure_code}")
        print(f"Description: {procedure.description}")
        print(f"Status: {procedure.status.value}")
        print(f"Coverage Type: {procedure.coverage_type.value}")
        print(f"Category: {procedure.category}")
        print(f"Effective Date: {procedure.effective_date}")
        print(f"Requires Authorization: {procedure.requires_authorization}")
        print(f"Rol Version: {procedure.rol_version}")
        print(f"Resolution: {procedure.resolution_number}")


async def example_worker_integration():
    """Example: Integration with ApplyContractRulesWorker."""
    from revenue_cycle.workers.billing.apply_contract_rules_worker import (
        create_apply_contract_rules_worker,
    )

    settings = Settings()

    # Create ANS Rol client
    rol_client = RolClient(settings, tenant_id="hospital-001")
    await rol_client.initialize()

    try:
        # Create worker with Rol client
        worker = create_apply_contract_rules_worker(
            contract_service=None,  # Will use default
            rol_client=rol_client,
        )

        print("Worker created with ANS Rol integration")
        print(f"Worker will validate procedures against Rol version: 2024")

        # Worker will now validate procedures during process_task
        # Validation happens automatically before applying contract rules

    finally:
        await rol_client.close()


async def example_cache_management():
    """Example: Cache management and statistics."""
    settings = Settings()

    async with RolClient(settings, tenant_id="hospital-001", cache_ttl_hours=24) as client:
        # Validate some procedures (will be cached)
        await client.validate_procedure("10101012")
        await client.validate_procedure("10101039")
        await client.validate_procedure("20101020")

        # Get cache statistics
        stats = client.get_cache_stats()
        print("Cache Statistics:")
        print(f"  Total Entries: {stats['total_entries']}")
        print(f"  Active Entries: {stats['active_entries']}")
        print(f"  Expired Entries: {stats['expired_entries']}")

        # Validate again (will use cache)
        result = await client.validate_procedure("10101012")
        print(f"\nSecond validation cached: {result.cached}")

        # Clear cache if needed
        cleared = client.clear_cache()
        print(f"\nCleared {cleared} cache entries")


async def example_error_handling():
    """Example: Error handling and fallback behavior."""
    settings = Settings()

    async with RolClient(settings, tenant_id="hospital-001") as client:
        # Test with invalid procedure code
        try:
            result = await client.validate_procedure("INVALID")
        except Exception as e:
            print(f"Validation error (expected): {e}")

        # Test with proper code but potential API unavailability
        result = await client.validate_procedure("10101012")

        if result.error_message:
            print(f"Warning: {result.error_message}")
            print("Using cached data or graceful degradation")

        print(f"Validation result: {result.is_valid}")


if __name__ == "__main__":
    # Run examples
    print("=== Example 1: Validate Procedure ===")
    asyncio.run(example_validate_procedure())

    print("\n=== Example 2: Search Procedures ===")
    asyncio.run(example_search_procedures())

    print("\n=== Example 3: Get Procedure Details ===")
    asyncio.run(example_get_procedure_details())

    print("\n=== Example 4: Worker Integration ===")
    asyncio.run(example_worker_integration())

    print("\n=== Example 5: Cache Management ===")
    asyncio.run(example_cache_management())

    print("\n=== Example 6: Error Handling ===")
    asyncio.run(example_error_handling())
