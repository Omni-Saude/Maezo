"""
Configuration migration and validation for multi-tenant deployments.

Handles migration of tenant configurations from legacy properties files to
Pydantic-validated configuration models. Supports generation of secure secrets
manifests for Vault integration.

Features:
- Properties file parsing with fallback defaults
- Configuration validation using Pydantic V2
- Secrets manifest generation for Vault storage
- Regulatory compliance properties (ANS, TISS)
- Smart defaults for collection and eligibility workflows
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from revenue_cycle.multi_tenant.credentials import TenantCredentialManager

logger = logging.getLogger(__name__)


class TenantConfiguration(BaseModel):
    """
    Tenant-specific configuration for the Hospital Revenue Cycle system.

    Manages integration endpoints, compliance settings, and workflow defaults
    for each tenant. Includes read-only regulatory properties that follow
    Brazilian healthcare standards (ANS, TISS).

    Example:
        config = TenantConfiguration(
            tenant_id="hosp-001",
            tasy_base_url="https://tasy.hospital.com",
            tiss_operator_code="1234567890123456",
        )
        print(config.tiss_version)  # "4.01.00"
        print(config.appeal_deadline_days)  # 30
    """

    model_config = ConfigDict(
        populate_by_name=True,  # Support both snake_case and camelCase
        validate_assignment=True,  # Validate on attribute assignment
        frozen=False,  # Allow initialization but not direct mutation
    )

    # Required fields
    tenant_id: str = Field(
        ...,
        description="Unique tenant identifier",
        min_length=1,
        max_length=255,
    )

    tasy_base_url: str = Field(
        ...,
        description="TASY ERP base URL",
        alias="tasyBaseUrl",
    )

    tiss_operator_code: str = Field(
        ...,
        description="TISS operator code (16 digits)",
        alias="tissOperatorCode",
        min_length=16,
        max_length=16,
    )

    # Optional fields with smart defaults
    glosa_auto_appeal_threshold: Decimal = Field(
        default=Decimal("5000.00"),
        description="Threshold for automatic glosa appeal (BRL)",
        alias="glosaAutoAppealThreshold",
        ge=Decimal("0"),
    )

    collection_reminder_days: int = Field(
        default=30,
        description="Days before sending collection reminder",
        alias="collectionReminderDays",
        ge=1,
        le=365,
    )

    eligibility_cache_ttl: int = Field(
        default=15,
        description="Eligibility data cache TTL in minutes",
        alias="eligibilityCacheTtl",
        ge=1,
        le=1440,
    )

    # Optional email for notifications
    notification_email: Optional[str] = Field(
        default=None,
        description="Email for system notifications",
        alias="notificationEmail",
    )

    # Payment processing defaults
    payment_reconciliation_days: int = Field(
        default=7,
        description="Days for payment reconciliation window",
        alias="paymentReconciliationDays",
        ge=1,
        le=90,
    )

    # Audit and compliance
    enable_audit_logging: bool = Field(
        default=True,
        description="Enable audit logging for all operations",
        alias="enableAuditLogging",
    )

    @field_validator("tasy_base_url", check_fields=False)
    @classmethod
    def validate_url_format(cls, v: str) -> str:
        """Validate that TASY URL is properly formatted."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("TASY URL must start with http:// or https://")
        return v

    @field_validator("tiss_operator_code")
    @classmethod
    def validate_operator_code(cls, v: str) -> str:
        """Validate TISS operator code format (numeric, 16 digits)."""
        if not v.isdigit():
            raise ValueError("TISS operator code must contain only digits")
        if len(v) != 16:
            raise ValueError("TISS operator code must be exactly 16 digits")
        return v

    @property
    def tiss_version(self) -> str:
        """
        Get TISS standard version for ANS compliance.

        Returns:
            str: TISS version (currently 4.01.00)

        Note:
            This is a read-only property following ANS normative resolution.
        """
        return "4.01.00"

    @property
    def appeal_deadline_days(self) -> int:
        """
        Get appeal deadline in days per ANS regulations.

        Returns:
            int: Number of days to appeal (30 days per RN 635/2020)

        Note:
            This is a regulatory requirement that cannot be changed.
        """
        return 30

    @property
    def max_glosa_recovery_percentage(self) -> Decimal:
        """
        Get maximum expected glosa recovery percentage.

        Returns:
            Decimal: Expected recovery as percentage (typically 60%)

        Note:
            Used for financial projections and KPI calculations.
        """
        return Decimal("60.00")

    @property
    def min_appeal_days_before_deadline(self) -> int:
        """
        Get minimum days before deadline to file appeal.

        Returns:
            int: Minimum days (typically 2)

        Note:
            Allows buffer time for documentation preparation.
        """
        return 2


@dataclass
class ValidationResult:
    """Result of configuration validation."""

    success: bool
    errors: list[str]
    warnings: list[str]
    tenant_id: Optional[str] = None

    def __bool__(self) -> bool:
        """Check if validation succeeded."""
        return self.success


class ConfigurationMigrator:
    """
    Migrate tenant configurations from properties files to validated models.

    Handles:
    - Loading configuration from .properties files
    - Parsing and transforming legacy formats
    - Validating against Pydantic schemas
    - Generating secrets manifests for Vault storage
    - Audit logging of migration operations

    Example:
        migrator = ConfigurationMigrator()

        # Migrate from properties file
        config = migrator.migrate_from_properties(
            "tenant-config.properties",
            "tenant-001"
        )

        # Generate secrets manifest
        secrets = migrator.generate_secrets_manifest(
            "tenant-001",
            credentials
        )

        # Validate configuration
        result = migrator.validate(config)
    """

    def __init__(self, credential_manager: Optional[TenantCredentialManager] = None):
        """
        Initialize configuration migrator.

        Args:
            credential_manager: Optional credential manager for Vault integration
        """
        self._credential_manager = credential_manager
        self._migration_history: list[dict[str, Any]] = []

    def migrate_from_properties(
        self,
        properties_file: str | Path,
        tenant_id: str,
    ) -> TenantConfiguration:
        """
        Migrate tenant configuration from properties file.

        Parses a .properties file and creates a TenantConfiguration object
        with smart defaults for optional fields.

        Args:
            properties_file: Path to .properties file
            tenant_id: Tenant identifier for configuration

        Returns:
            TenantConfiguration: Validated configuration object

        Raises:
            FileNotFoundError: If properties file doesn't exist
            ValueError: If required configuration is missing
            ValidationError: If configuration doesn't validate

        Example:
            config = migrator.migrate_from_properties(
                "tenant-001.properties",
                "tenant-001"
            )
        """
        properties_file = Path(properties_file)

        if not properties_file.exists():
            raise FileNotFoundError(f"Properties file not found: {properties_file}")

        try:
            # Parse properties file
            properties = self._parse_properties_file(properties_file)
            logger.info(
                f"Parsed properties file: {properties_file} (tenant={tenant_id})"
            )

            # Transform to TenantConfiguration schema
            config_data = self._transform_to_config_schema(properties, tenant_id)

            # Create and validate configuration
            config = TenantConfiguration(**config_data)

            # Record migration
            self._migration_history.append(
                {
                    "tenant_id": tenant_id,
                    "source_file": str(properties_file),
                    "status": "success",
                    "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
                }
            )

            logger.info(
                f"Configuration migrated successfully (tenant={tenant_id}, source={properties_file})"
            )

            return config

        except Exception as e:
            # Record failed migration
            self._migration_history.append(
                {
                    "tenant_id": tenant_id,
                    "source_file": str(properties_file),
                    "status": "failed",
                    "error": str(e),
                    "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
                }
            )

            logger.error(
                f"Configuration migration failed (tenant={tenant_id}, source={properties_file}, error={str(e)})"
            )
            raise

    def _parse_properties_file(self, properties_file: Path) -> dict[str, str]:
        """
        Parse a Java-style properties file.

        Args:
            properties_file: Path to properties file

        Returns:
            dict: Parsed key-value pairs

        Note:
            Handles comments (#, !) and escaped characters.
        """
        properties = {}

        with open(properties_file, "r", encoding="utf-8") as f:
            for line in f:
                # Strip whitespace and skip comments/empty lines
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("!"):
                    continue

                # Parse key=value or key: value
                if "=" in line:
                    key, value = line.split("=", 1)
                elif ":" in line:
                    key, value = line.split(":", 1)
                else:
                    continue

                # Store with key stripped and value unescaped
                properties[key.strip()] = self._unescape_property_value(value.strip())

        return properties

    @staticmethod
    def _unescape_property_value(value: str) -> str:
        """
        Unescape Java properties file escape sequences.

        Args:
            value: Raw property value

        Returns:
            str: Unescaped value
        """
        # Handle common escape sequences
        value = value.replace("\\n", "\n")
        value = value.replace("\\r", "\r")
        value = value.replace("\\t", "\t")
        value = value.replace("\\\\", "\\")
        return value

    def _transform_to_config_schema(
        self,
        properties: dict[str, str],
        tenant_id: str,
    ) -> dict[str, Any]:
        """
        Transform properties dict to TenantConfiguration schema.

        Handles mapping of legacy property names to Pydantic field names
        and applies smart defaults.

        Args:
            properties: Parsed properties dictionary
            tenant_id: Tenant identifier

        Returns:
            dict: Configuration data ready for TenantConfiguration

        Raises:
            ValueError: If required properties are missing
        """
        config_data = {"tenant_id": tenant_id}

        # Map legacy property names to new schema
        legacy_to_new_mapping = {
            "tasy_url": "tasy_base_url",
            "tasyUrl": "tasy_base_url",
            "tiss_code": "tiss_operator_code",
            "tissCode": "tiss_operator_code",
            "tissue_operator_code": "tiss_operator_code",
            "glosa_appeal_threshold": "glosa_auto_appeal_threshold",
            "glosaAppealThreshold": "glosa_auto_appeal_threshold",
            "collection_days": "collection_reminder_days",
            "collectionDays": "collection_reminder_days",
            "cache_ttl": "eligibility_cache_ttl",
            "cacheTtl": "eligibility_cache_ttl",
            "notification_mail": "notification_email",
            "notificationMail": "notification_email",
            "payment_reconciliation": "payment_reconciliation_days",
            "paymentReconciliation": "payment_reconciliation_days",
        }

        # Transform properties
        for legacy_key, new_key in legacy_to_new_mapping.items():
            if legacy_key in properties:
                value = properties[legacy_key]

                # Type conversion
                if new_key in ["collection_reminder_days", "eligibility_cache_ttl",
                               "payment_reconciliation_days"]:
                    try:
                        config_data[new_key] = int(value)
                    except ValueError:
                        raise ValueError(f"Invalid integer for {new_key}: {value}")

                elif new_key == "glosa_auto_appeal_threshold":
                    try:
                        config_data[new_key] = Decimal(value)
                    except Exception:
                        raise ValueError(f"Invalid decimal for {new_key}: {value}")

                else:
                    config_data[new_key] = value

        # Handle enable_audit_logging
        if "enable_audit_logging" in properties or "enableAuditLogging" in properties:
            audit_value = (
                properties.get("enable_audit_logging")
                or properties.get("enableAuditLogging")
            )
            config_data["enable_audit_logging"] = audit_value.lower() in ("true", "1", "yes")

        # Verify required fields
        required_fields = ["tasy_base_url", "tiss_operator_code"]
        missing_fields = [f for f in required_fields if f not in config_data]

        if missing_fields:
            raise ValueError(f"Missing required configuration: {', '.join(missing_fields)}")

        return config_data

    def generate_secrets_manifest(
        self,
        tenant_id: str,
        credentials: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Generate a secrets manifest for Vault storage.

        Creates a structured document with all secrets and sensitive
        data that should be stored in HashiCorp Vault per tenant.

        Args:
            tenant_id: Tenant identifier
            credentials: Dictionary of credentials to include

        Returns:
            dict: Secrets manifest with metadata and secret definitions

        Example:
            manifest = migrator.generate_secrets_manifest(
                "tenant-001",
                {
                    "tasy_username": "user@hospital.com",
                    "tasy_password": "***",
                    "tiss_certificate": "-----BEGIN CERT-----...",
                }
            )
        """
        import hashlib
        from datetime import datetime

        manifest = {
            "metadata": {
                "tenant_id": tenant_id,
                "created_at": datetime.utcnow().isoformat(),
                "version": "1.0",
                "schema_version": "v2",  # Vault KV v2
            },
            "secrets": {
                "tasy_api": {
                    "path": f"secret/tenants/{tenant_id}/tasy_api",
                    "fields": {
                        "username": "string",
                        "password": "secret",
                        "api_key": "secret (optional)",
                        "base_url": "string",
                    },
                    "rotation_required": True,
                    "rotation_days": 90,
                },
                "tiss_certificate": {
                    "path": f"secret/tenants/{tenant_id}/tiss_certificate",
                    "fields": {
                        "certificate_pem": "secret",
                        "private_key_pem": "secret",
                        "passphrase": "secret (optional)",
                        "valid_until": "datetime",
                        "issuer": "string",
                    },
                    "rotation_required": True,
                    "rotation_days": 365,
                },
                "whatsapp_token": {
                    "path": f"secret/tenants/{tenant_id}/whatsapp_token",
                    "fields": {
                        "access_token": "secret",
                        "phone_number_id": "string",
                        "business_account_id": "string",
                        "webhook_verify_token": "secret (optional)",
                    },
                    "rotation_required": False,
                    "rotation_days": None,
                },
            },
            "access_control": {
                "read_policies": [
                    f"tenant-{tenant_id}-read",
                    "workers-read",
                ],
                "admin_policies": [
                    f"tenant-{tenant_id}-admin",
                    "vault-admin",
                ],
            },
            "audit": {
                "requires_mfa": True,
                "requires_approval": True,
                "approval_count": 2,
            },
        }

        # Add credentials provided
        if credentials:
            manifest["credentials_provided"] = {
                k: "provided" if v else "missing"
                for k, v in credentials.items()
            }

            # Generate checksum for integrity
            cred_string = ",".join(f"{k}={v}" for k, v in sorted(credentials.items()))
            checksum = hashlib.sha256(cred_string.encode()).hexdigest()
            manifest["metadata"]["credentials_checksum"] = checksum

        logger.info(
            f"Secrets manifest generated (tenant={tenant_id}, secrets={len(manifest['secrets'])})"
        )

        return manifest

    def validate(self, config: TenantConfiguration) -> ValidationResult:
        """
        Validate a TenantConfiguration object.

        Performs comprehensive validation including:
        - Pydantic schema validation (already done during creation)
        - Business rule validation (thresholds, dates, etc.)
        - Regulatory compliance checks
        - Format validation for external system codes

        Args:
            config: Configuration to validate

        Returns:
            ValidationResult: Validation status with any errors/warnings

        Example:
            config = TenantConfiguration(
                tenant_id="tenant-001",
                tasy_base_url="https://tasy.hospital.com",
                tiss_operator_code="1234567890123456",
            )
            result = migrator.validate(config)
            if not result:
                for error in result.errors:
                    print(f"Error: {error}")
        """
        errors = []
        warnings = []

        try:
            # Verify TISS code format
            if not config.tiss_operator_code.isdigit():
                errors.append("TISS operator code must contain only digits")

            if len(config.tiss_operator_code) != 16:
                errors.append("TISS operator code must be exactly 16 digits")

            # Verify glosa threshold is reasonable
            if config.glosa_auto_appeal_threshold <= Decimal("0"):
                errors.append("Glosa appeal threshold must be positive")

            if config.glosa_auto_appeal_threshold > Decimal("100000.00"):
                warnings.append(
                    f"Glosa appeal threshold is very high: {config.glosa_auto_appeal_threshold}"
                )

            # Verify collection reminder days
            if config.collection_reminder_days < 1:
                errors.append("Collection reminder days must be at least 1")

            if config.collection_reminder_days > 365:
                errors.append("Collection reminder days cannot exceed 365")

            # Verify cache TTL
            if config.eligibility_cache_ttl < 1:
                errors.append("Eligibility cache TTL must be at least 1 minute")

            if config.eligibility_cache_ttl > 1440:
                errors.append("Eligibility cache TTL cannot exceed 24 hours")

            # Verify payment reconciliation window
            if config.payment_reconciliation_days > config.appeal_deadline_days:
                warnings.append(
                    "Payment reconciliation window exceeds appeal deadline"
                )

            # Verify TASY URL is reachable (optional - could require external check)
            logger.info(
                f"Configuration validation completed (tenant={config.tenant_id}, success={len(errors) == 0})"
            )

            return ValidationResult(
                success=len(errors) == 0,
                errors=errors,
                warnings=warnings,
                tenant_id=config.tenant_id,
            )

        except Exception as e:
            logger.error(
                f"Configuration validation failed (tenant={config.tenant_id}, error={str(e)})"
            )
            return ValidationResult(
                success=False,
                errors=[f"Validation error: {str(e)}"],
                warnings=warnings,
                tenant_id=config.tenant_id,
            )

    @property
    def migration_history(self) -> list[dict[str, Any]]:
        """Get history of all configuration migrations performed."""
        return self._migration_history.copy()
