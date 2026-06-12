"""Service layer for DMN validation, preview, and deploy operations."""
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from healthcare_platform.contract_extraction.dmn_generator import DMNGenerator
from healthcare_platform.contract_extraction.models import (
    ContractRule,
    ContractRuleChange,
    RuleStatus,
)
from healthcare_platform.contract_extraction.validators import validate_rule


class DMNService:
    """Business logic for DMN-related contract rule operations.

    Args:
        session: SQLAlchemy database session.
        dmn_generator: Optional DMNGenerator instance; a default is created if omitted.
    """

    def __init__(
        self,
        session: Session,
        dmn_generator: Optional[DMNGenerator] = None,
    ) -> None:
        self.session = session
        self.dmn_generator = dmn_generator or DMNGenerator()

    def _get_rule(self, tenant_id: str, rule_id: uuid.UUID) -> ContractRule:
        """Fetch a single rule scoped to the tenant or raise KeyError."""
        rule = (
            self.session.query(ContractRule)
            .filter_by(id=rule_id, tenant_id=tenant_id)
            .first()
        )
        if rule is None:
            raise KeyError(f"Rule {rule_id} not found for tenant {tenant_id}")
        return rule

    def validate_rule_by_id(self, tenant_id: str, rule_id: uuid.UUID) -> dict:
        """Run validation checks against a persisted rule.

        Returns:
            Dict with keys: rule_id (str), is_valid (bool), errors (list of dicts).
        """
        rule = self._get_rule(tenant_id, rule_id)
        errors = validate_rule(rule.rule_definition, rule.archetype.value)
        return {
            "rule_id": str(rule_id),
            "is_valid": len(errors) == 0,
            "errors": [
                {"field": e.field, "message": e.message, "code": e.code}
                for e in errors
            ],
        }

    def preview_dmn(self, tenant_id: str, rule_id: uuid.UUID) -> dict:
        """Generate a DMN XML preview without persisting to disk.

        Returns:
            Dict with rule_id, archetype, version, xml_content, generated_at.
        """
        rule = self._get_rule(tenant_id, rule_id)
        xml_content = self.dmn_generator.generate(rule)
        return {
            "rule_id": str(rule_id),
            "archetype": rule.archetype.value,
            "version": rule.version,
            "xml_content": xml_content,
            "generated_at": datetime.utcnow().isoformat(),
        }

    def deploy_rule(
        self,
        tenant_id: str,
        rule_id: uuid.UUID,
        deployed_by: str = "system",
    ) -> dict:
        """Validate, generate, save, and activate a contract rule.

        Raises:
            KeyError: When no matching rule is found.
            ValueError: When the rule fails validation.

        Returns:
            Dict with rule_id, tenant_id, status, dmn_path, version, deployed_at.
        """
        rule = self._get_rule(tenant_id, rule_id)

        errors = validate_rule(rule.rule_definition, rule.archetype.value)
        if errors:
            details = [
                {"field": e.field, "message": e.message, "code": e.code}
                for e in errors
            ]
            raise ValueError(f"Rule {rule_id} failed validation: {details}")

        path: Path = self.dmn_generator.generate_and_save(rule, tenant_id)

        rule.status = RuleStatus.ACTIVE
        self.session.commit()

        deployed_at = datetime.utcnow()

        change = ContractRuleChange(
            rule_id=rule.id,
            change_type="DEPLOYED",
            new_value={"dmn_path": str(path)},
            changed_by=deployed_by,
        )
        self.session.add(change)
        self.session.commit()

        return {
            "rule_id": str(rule_id),
            "tenant_id": tenant_id,
            "status": rule.status.value,
            "dmn_path": str(path),
            "version": rule.version,
            "deployed_at": deployed_at.isoformat(),
        }
