"""Service layer for Contract Rule Extraction — CRUD operations."""
import uuid
from datetime import date
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
        conflicts = self.detect_conflicts(
            tenant_id, request.payer_id, request.category,
            request.effective_date, request.expiry_date,
        )
        if conflicts:
            raise ValueError(
                f"Conflicting rules found for {request.category.value} "
                f"with payer {request.payer_id} in the given date range"
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

    def get_rule_history(
        self, tenant_id: str, rule_id: uuid.UUID
    ) -> List[ContractRuleChange]:
        """Return all change records for a rule ordered newest-first.

        Args:
            tenant_id: Owning tenant identifier.
            rule_id: UUID primary key of the rule.

        Raises:
            KeyError: When no matching rule is found.

        Returns:
            List of ContractRuleChange instances.
        """
        rule = self.get_rule(tenant_id, rule_id)
        return (
            self.session.query(ContractRuleChange)
            .filter(ContractRuleChange.rule_id == rule.id)
            .order_by(ContractRuleChange.changed_at.desc())
            .all()
        )

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

        if "rule_definition" in request.model_dump(exclude_unset=True):
            if request.rule_definition != old_snapshot["rule_definition"]:
                self.auto_bump_version(rule)

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

    @staticmethod
    def auto_bump_version(rule: ContractRule) -> str:
        """Increment the patch segment of a semver version string in-place.

        Args:
            rule: The ContractRule whose version will be bumped.

        Returns:
            The new version string.
        """
        parts = rule.version.split(".")
        parts[2] = str(int(parts[2]) + 1)
        rule.version = ".".join(parts)
        return rule.version

    def detect_conflicts(
        self,
        tenant_id: str,
        payer_id: str,
        category: RuleCategory,
        effective_date: date,
        expiry_date: Optional[date],
        exclude_rule_id: Optional[uuid.UUID] = None,
    ) -> List[ContractRule]:
        """Return existing non-archived rules whose date range overlaps the given range.

        Args:
            tenant_id: Owning tenant identifier.
            payer_id: Payer identifier to scope the search.
            category: Rule category to match.
            effective_date: Start of the candidate rule's validity period.
            expiry_date: End of the candidate rule's validity period (None = open-ended).
            exclude_rule_id: Optional rule id to exclude from the search (used on update).

        Returns:
            List of conflicting ContractRule instances.
        """
        query = (
            self.session.query(ContractRule)
            .filter(
                ContractRule.tenant_id == tenant_id,
                ContractRule.payer_id == payer_id,
                ContractRule.category == category,
                ContractRule.status != RuleStatus.ARCHIVED,
            )
        )
        if exclude_rule_id:
            query = query.filter(ContractRule.id != exclude_rule_id)
        results = []
        for rule in query.all():
            rule_end = rule.expiry_date
            new_end = expiry_date
            if rule_end is None and new_end is None:
                results.append(rule)
            elif rule_end is None:
                if rule.effective_date <= new_end:
                    results.append(rule)
            elif new_end is None:
                if effective_date <= rule_end:
                    results.append(rule)
            else:
                if effective_date <= rule_end and rule.effective_date <= new_end:
                    results.append(rule)
        return results

    def delete_rule(self, tenant_id: str, rule_id: uuid.UUID) -> None:
        """Delete a contract rule from the database.

        Args:
            tenant_id: Owning tenant identifier.
            rule_id: UUID primary key of the rule.

        Raises:
            KeyError: When no matching rule is found.
        """
        rule = self.get_rule(tenant_id, rule_id)
        snapshot = {
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
            change_type="DELETED",
            old_value=snapshot,
            changed_by="system",
        )
        self.session.add(change)
        self.session.flush()
        # Delete via SQL to avoid ORM cascade removing the DELETED change record
        self.session.execute(
            ContractRule.__table__.delete().where(ContractRule.id == rule.id)
        )
        self.session.commit()
