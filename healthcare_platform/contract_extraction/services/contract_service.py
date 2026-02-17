"""Service layer for Contract Rule Extraction — CRUD operations."""
import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from healthcare_platform.contract_extraction.dmn_generator import DMNGenerator
from healthcare_platform.contract_extraction.models import (
    ContractRule,
    ContractRuleChange,
    RuleCategory,
    RuleStatus,
)
from healthcare_platform.contract_extraction.schemas import (
    RuleCreateRequest,
    RuleUpdateRequest,
)
from healthcare_platform.contract_extraction.validators import validate_rule
from healthcare_platform.contract_extraction.services.dmn_service import DMNService


class ContractService(DMNService):
    """Business logic for contract rule management (CRUD + DMN via DMNService).

    Args:
        session: SQLAlchemy database session.
        dmn_generator: Optional DMNGenerator instance; a default is created if omitted.
    """

    def __init__(
        self,
        session: Session,
        dmn_generator: Optional[DMNGenerator] = None,
    ) -> None:
        super().__init__(session, dmn_generator)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_rule(
        self,
        tenant_id: str,
        request: RuleCreateRequest,
        created_by: str = "system",
    ) -> ContractRule:
        """Create a new ContractRule with DRAFT status and record the change.

        Args:
            tenant_id: Owning tenant identifier.
            request: Validated create payload.
            created_by: Identity of the caller (audit trail).

        Returns:
            Persisted ContractRule instance.
        """
        rule = ContractRule(
            tenant_id=tenant_id,
            payer_id=request.payer_id,
            category=request.category,
            archetype=request.archetype,
            rule_definition=request.rule_definition,
            version=request.version,
            effective_date=request.effective_date,
            expiry_date=request.expiry_date,
            status=RuleStatus.DRAFT,
        )
        self.session.add(rule)
        self.session.commit()

        change = ContractRuleChange(
            rule_id=rule.id,
            change_type="CREATED",
            new_value=request.rule_definition,
            changed_by=created_by,
        )
        self.session.add(change)
        self.session.commit()

        return rule

    def list_rules(
        self,
        tenant_id: str,
        status: Optional[RuleStatus] = None,
        category: Optional[RuleCategory] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[ContractRule]:
        """Return paginated contract rules for a tenant with optional filters.

        Args:
            tenant_id: Owning tenant identifier.
            status: Filter by rule status when provided.
            category: Filter by rule category when provided.
            skip: Number of records to skip (offset).
            limit: Maximum number of records to return.

        Returns:
            List of ContractRule instances.
        """
        query = ContractRule.get_for_tenant(self.session, tenant_id)

        if status is not None:
            query = query.filter(ContractRule.status == status)
        if category is not None:
            query = query.filter(ContractRule.category == category)

        return query.offset(skip).limit(limit).all()

    def get_rule(self, tenant_id: str, rule_id: uuid.UUID) -> ContractRule:
        """Fetch a single rule by id scoped to the tenant.

        Args:
            tenant_id: Owning tenant identifier.
            rule_id: UUID primary key of the rule.

        Raises:
            KeyError: When no matching rule is found.

        Returns:
            The matching ContractRule instance.
        """
        return self._get_rule(tenant_id, rule_id)

    def update_rule(
        self,
        tenant_id: str,
        rule_id: uuid.UUID,
        request: RuleUpdateRequest,
        updated_by: str = "system",
    ) -> ContractRule:
        """Partially update a contract rule and record the change.

        Args:
            tenant_id: Owning tenant identifier.
            rule_id: UUID primary key of the rule.
            request: Validated partial update payload.
            updated_by: Identity of the caller (audit trail).

        Raises:
            KeyError: When no matching rule is found.

        Returns:
            Updated ContractRule instance.
        """
        rule = self.get_rule(tenant_id, rule_id)

        old_snapshot = {
            "payer_id": rule.payer_id,
            "category": rule.category.value,
            "archetype": rule.archetype.value,
            "rule_definition": rule.rule_definition,
            "version": rule.version,
            "effective_date": str(rule.effective_date),
            "expiry_date": str(rule.expiry_date) if rule.expiry_date else None,
        }

        for field, value in request.model_dump(exclude_unset=True).items():
            setattr(rule, field, value)

        self.session.commit()

        new_snapshot = {
            "payer_id": rule.payer_id,
            "category": rule.category.value,
            "archetype": rule.archetype.value,
            "rule_definition": rule.rule_definition,
            "version": rule.version,
            "effective_date": str(rule.effective_date),
            "expiry_date": str(rule.expiry_date) if rule.expiry_date else None,
        }

        change = ContractRuleChange(
            rule_id=rule.id,
            change_type="UPDATED",
            old_value=old_snapshot,
            new_value=new_snapshot,
            changed_by=updated_by,
        )
        self.session.add(change)
        self.session.commit()

        return rule

    def delete_rule(self, tenant_id: str, rule_id: uuid.UUID) -> None:
        """Delete a contract rule from the database.

        Args:
            tenant_id: Owning tenant identifier.
            rule_id: UUID primary key of the rule.

        Raises:
            KeyError: When no matching rule is found.
        """
        rule = self.get_rule(tenant_id, rule_id)
        self.session.delete(rule)
        self.session.commit()
