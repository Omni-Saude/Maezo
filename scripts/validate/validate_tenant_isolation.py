#!/usr/bin/env python3
"""Validate tenant isolation for MAEZO Healthcare Platform (ADR-002).

Checks:
1. All ACT_* tables have tenant_id_ column
2. No rows with invalid/null tenant IDs
3. No global deployments without tenant markers

Usage:
    python3 scripts/validate_tenant_isolation.py
    DATABASE_URL=postgresql://user:pass@host:5432/db python3 scripts/validate_tenant_isolation.py
"""

import argparse
import os
import sys
from typing import Any

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(2)


VALID_TENANTS = {"austa-hospital", "amh-sp-morumbi", "amh-rj-barra", "amh-mg-bh"}

# Camunda tables that MUST have tenant_id_
TENANT_REQUIRED_TABLES = [
    "act_ru_execution",
    "act_ru_task",
    "act_ru_variable",
    "act_ru_job",
    "act_ru_event_subscr",
    "act_ru_incident",
    "act_re_procdef",
    "act_re_deployment",
    "act_re_decision_def",
    "act_re_decision_req_def",
    "act_hi_procinst",
    "act_hi_taskinst",
    "act_hi_actinst",
]


def check_tenant_columns(cursor: Any) -> list[str]:
    """Verify tenant_id_ column exists in all required ACT_* tables."""
    issues = []
    for table in TENANT_REQUIRED_TABLES:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s AND column_name = 'tenant_id_'
            """,
            (table,),
        )
        if cursor.fetchone() is None:
            # Check if table exists at all
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_name = %s
                """,
                (table,),
            )
            if cursor.fetchone() is not None:
                issues.append(f"Table {table} exists but missing tenant_id_ column")
    return issues


def check_cross_tenant_leakage(cursor: Any) -> list[dict]:
    """Check for rows with invalid or null tenant IDs."""
    issues = []
    runtime_tables = ["act_ru_execution", "act_ru_task"]

    for table in runtime_tables:
        # Check table exists
        cursor.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
            (table,),
        )
        if cursor.fetchone() is None:
            continue

        # Check for null tenant_id_
        cursor.execute(
            f"SELECT id_ FROM {table} WHERE tenant_id_ IS NULL LIMIT 10"  # noqa: S608
        )
        for row in cursor.fetchall():
            issues.append({
                "table": table,
                "id": row[0],
                "issue": "NULL tenant_id_",
            })

        # Check for invalid tenant_id_
        placeholders = ",".join(["%s"] * len(VALID_TENANTS))
        cursor.execute(
            f"SELECT id_, tenant_id_ FROM {table} "  # noqa: S608
            f"WHERE tenant_id_ IS NOT NULL AND tenant_id_ NOT IN ({placeholders}) "
            "LIMIT 10",
            tuple(VALID_TENANTS),
        )
        for row in cursor.fetchall():
            issues.append({
                "table": table,
                "id": row[0],
                "issue": f"Invalid tenant_id_: {row[1]}",
            })

    return issues


def check_deployment_isolation(cursor: Any) -> list[dict]:
    """Verify all deployments have tenant markers."""
    issues = []

    cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = 'act_re_deployment'"
    )
    if cursor.fetchone() is None:
        return issues

    cursor.execute(
        "SELECT id_, name_, tenant_id_ FROM act_re_deployment "
        "WHERE tenant_id_ IS NULL LIMIT 20"
    )
    for row in cursor.fetchall():
        dep_name = row[1] or "(unnamed)"
        # Allow bootstrap/system deployments
        if dep_name.startswith("__"):
            continue
        issues.append({
            "table": "act_re_deployment",
            "id": row[0],
            "issue": f"Deployment '{dep_name}' has no tenant_id_",
        })

    return issues


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate tenant isolation for MAEZO Healthcare Platform (ADR-002)"
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv(
            "DATABASE_URL", "postgresql://camunda:camunda@localhost:5432/camunda"
        ),
        help="PostgreSQL connection URL",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose output"
    )
    args = parser.parse_args()

    try:
        conn = psycopg2.connect(args.database_url)
    except psycopg2.OperationalError as e:
        print(f"ERROR: Cannot connect to database: {e}")
        sys.exit(2)

    cursor = conn.cursor()
    all_issues: list[str | dict] = []

    print("Checking tenant_id_ columns...")
    column_issues = check_tenant_columns(cursor)
    all_issues.extend(column_issues)
    if args.verbose:
        for issue in column_issues:
            print(f"  WARN: {issue}")

    print("Checking cross-tenant leakage...")
    leakage_issues = check_cross_tenant_leakage(cursor)
    all_issues.extend(leakage_issues)
    if args.verbose:
        for issue in leakage_issues:
            print(f"  WARN: {issue}")

    print("Checking deployment isolation...")
    deploy_issues = check_deployment_isolation(cursor)
    all_issues.extend(deploy_issues)
    if args.verbose:
        for issue in deploy_issues:
            print(f"  WARN: {issue}")

    cursor.close()
    conn.close()

    if all_issues:
        print(f"\nFAIL: {len(all_issues)} tenant isolation issues found")
        for issue in all_issues:
            print(f"  - {issue}")
        sys.exit(1)
    else:
        print("\nPASS: Tenant isolation validated")
        sys.exit(0)


if __name__ == "__main__":
    main()
