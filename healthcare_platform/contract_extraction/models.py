import enum
import uuid
from datetime import date, datetime
from sqlalchemy import Column, String, JSON, Date, DateTime, Enum, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class RuleCategory(enum.Enum):
    PRICING = "PRICING"
    BUNDLE = "BUNDLE"
    OPME = "OPME"
    AUTHORIZATION = "AUTHORIZATION"
    DISCOUNT = "DISCOUNT"


class RuleArchetype(enum.Enum):
    LOOKUP = "LOOKUP"
    ROUTING = "ROUTING"
    PRICING = "PRICING"
    AUTHORIZATION = "AUTHORIZATION"
    BUNDLING = "BUNDLING"


class RuleStatus(enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


class ContractRule(Base):
    __tablename__ = "contract_rules"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String, nullable=False, index=True)
    payer_id = Column(String, nullable=False)
    category = Column(Enum(RuleCategory), nullable=False)
    archetype = Column(Enum(RuleArchetype), nullable=False)
    rule_definition = Column(JSON, nullable=False)
    version = Column(String, nullable=False, default="1.0.0")
    effective_date = Column(Date, nullable=False)
    expiry_date = Column(Date, nullable=True)
    status = Column(Enum(RuleStatus), nullable=False, default=RuleStatus.DRAFT)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    changes = relationship("ContractRuleChange", back_populates="rule", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_contract_rules_tenant_id", "tenant_id"),
    )

    @staticmethod
    def get_for_tenant(session, tenant_id: str):
        return session.query(ContractRule).filter_by(tenant_id=tenant_id)


class ContractRuleChange(Base):
    __tablename__ = "contract_rule_changes"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("contract_rules.id"),
        nullable=False,
        index=True,
    )
    changed_by = Column(String, nullable=False)
    changed_at = Column(DateTime, default=datetime.utcnow)
    change_type = Column(String, nullable=False)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)

    rule = relationship("ContractRule", back_populates="changes")

    __table_args__ = (
        Index("ix_contract_rule_changes_rule_id", "rule_id"),
    )
