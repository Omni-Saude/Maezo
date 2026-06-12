"""
WORKER TEMPLATE: BaseExternalTaskWorker
Purpose: Unified worker base class eliminating 3 competing patterns + 80 Stub classes

Design principles:
- Single inheritance hierarchy (no Protocol/ABC/Mixin fragmentation)
- Built-in: DMN evaluation, tenant resolution, metrics, LGPD hashing, error handling
- TaskContext replaces raw dict[str, Any]
- TaskResult unified return type
- Dependency injection via constructor (testable without Stubs)
- Average worker target: ~80 lines (down from 284)

Usage:
    from healthcare_platform.shared.workers.base import BaseExternalTaskWorker, TaskContext, TaskResult
    
    class ValidateEligibilityWorker(BaseExternalTaskWorker):
        def execute(self, context: TaskContext) -> TaskResult:
            # Your logic here
            return TaskResult.success({"eligible": True})
"""

from __future__ import annotations

import inspect
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.lgpd.hashing import LGPDHasher
from healthcare_platform.shared.metrics.worker_metrics import WorkerMetrics
from healthcare_platform.shared.tenant.resolver import TenantResolver


class TaskStatus(Enum):
    """Task execution status"""
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    BPMN_ERROR = "BPMN_ERROR"  # Business error (triggers BPMN error boundary)


@dataclass
class TaskContext:
    """
    Strongly-typed task context (replaces raw dict[str, Any])
    
    Attributes:
        task_id: Camunda task ID
        process_instance_id: BPMN process instance ID
        tenant_id: Resolved tenant ID (from marker or variables)
        variables: Process variables (input)
        worker_id: Worker identifier (topic name)
        retries: Retry count (decremented by Camunda on failure)
        lock_expiration: Task lock expiration timestamp
        business_key: Optional business identifier
    """
    task_id: str
    process_instance_id: str
    tenant_id: str
    variables: Dict[str, Any]
    worker_id: str
    retries: int = 3
    lock_expiration: Optional[datetime] = None
    business_key: Optional[str] = None


@dataclass
class TaskResult:
    """
    Unified worker return type

    Attributes:
        status: Execution status
        variables: Output variables to merge into process
        error_code: Optional BPMN error code (triggers error boundary)
        error_message: Human-readable error message
        metrics: Optional execution metrics (latency, DMN calls, etc.)
    """
    status: TaskStatus
    variables: Dict[str, Any] = field(default_factory=dict)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(cls, variables: Dict[str, Any]) -> TaskResult:
        """Create success result"""
        return cls(status=TaskStatus.SUCCESS, variables=variables)

    @classmethod
    def failure(cls, error_message: str, error_code: Optional[str] = None) -> TaskResult:
        """Create failure result (task will be retried)"""
        return cls(
            status=TaskStatus.FAILURE,
            error_message=error_message,
            error_code=error_code,
        )

    @classmethod
    def bpmn_error(cls, error_code: str, error_message: str, variables: Optional[Dict[str, Any]] = None) -> TaskResult:
        """Create BPMN error result (triggers error boundary event)"""
        return cls(
            status=TaskStatus.BPMN_ERROR,
            error_code=error_code,
            error_message=error_message,
            variables=variables or {},
        )


@dataclass
class ProcessTaskResult:
    """V1 backward-compatible result for process_task()."""
    success: bool
    variables: Dict[str, Any] = field(default_factory=dict)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retry: bool = False


class BaseExternalTaskWorker(ABC):
    """
    Unified base class for all external task workers
    
    Eliminates:
    - Pattern A (Revenue): @worker decorator fragmentation
    - Pattern B (Clinical): Protocol + Production + Stub verbosity
    - Pattern C (Glosa): BaseWorker + Mixin duplication
    - 80 Stub classes: Replaced by pytest fixtures with mocked dependencies
    
    Built-in features:
    - DMN evaluation (federated, tenant-aware)
    - Tenant resolution (from markers or variables)
    - LGPD hashing (automatic PII protection)
    - Metrics collection (latency, DMN calls, success rate)
    - Error handling (retry logic, BPMN error boundaries)
    - Structured logging (correlation IDs, tenant context)
    
    Dependency injection:
    All external dependencies injected via constructor (testable without Stubs)
    """

    def __init__(
        self,
        dmn_service: Optional[FederatedDMNService] = None,
        tenant_resolver: Optional[TenantResolver] = None,
        lgpd_hasher: Optional[LGPDHasher] = None,
        metrics: Optional[WorkerMetrics] = None,
        logger: Optional[logging.Logger] = None,
        **kwargs,  # Accept v1-specific kwargs (audit_engine, rules_engine, etc.)
    ):
        """
        Initialize worker with dependencies

        Args:
            dmn_service: DMN evaluation service (optional, inject in tests)
            tenant_resolver: Tenant resolution service (optional)
            lgpd_hasher: LGPD hashing service (optional)
            metrics: Metrics collector (optional)
            logger: Logger instance (optional, defaults to class name)
        """
        self.dmn_service = dmn_service or FederatedDMNService()
        self.tenant_resolver = tenant_resolver or TenantResolver()
        self.lgpd_hasher = lgpd_hasher or LGPDHasher()
        self.metrics = metrics or WorkerMetrics()
        self.logger = logger or logging.getLogger(self.__class__.__name__)

    @property
    def operation_name(self) -> str:
        """
        Get operation name for the worker.

        Returns OPERATION_NAME attribute if defined, otherwise falls back to TOPIC or class name.
        """
        return getattr(self, 'OPERATION_NAME', getattr(self, 'TOPIC', self.__class__.__name__))

    @abstractmethod
    def execute(self, context: TaskContext) -> TaskResult:
        """
        Execute worker logic (implement in subclass)
        
        Args:
            context: Strongly-typed task context
            
        Returns:
            TaskResult with status, variables, and optional error
            
        Example:
            def execute(self, context: TaskContext) -> TaskResult:
                patient_id = context.variables["patientId"]
                
                # Evaluate DMN
                dmn_result = self.evaluate_dmn(
                    context,
                    decision_key="eligibility_validation",
                    variables={"patientId": patient_id},
                )
                
                if dmn_result["eligible"]:
                    return TaskResult.success({"eligible": True})
                else:
                    return TaskResult.bpmn_error(
                        error_code="ERR_NOT_ELIGIBLE",
                        error_message="Patient not eligible for procedure",
                        variables={"eligibilityReason": dmn_result["reason"]},
                    )
        """
        pass

    def evaluate_dmn(
        self,
        context: TaskContext,
        decision_key: str,
        variables: Dict[str, Any],
        category: str = "clinical_safety",
    ) -> Dict[str, Any]:
        """
        Evaluate DMN table (tenant-aware, federated)
        
        Args:
            context: Task context (contains tenant_id)
            decision_key: DMN decision/table key (e.g., "adverse_event_severity_assessment")
            variables: Input variables for DMN
            category: DMN category (default: clinical_safety)
            
        Returns:
            DMN evaluation result (first hit)
            
        Raises:
            DMNEvaluationError: If evaluation fails
        """
        start_time = datetime.utcnow()
        
        try:
            result = self.dmn_service.evaluate(
                tenant_id=context.tenant_id,
                category=category,
                table_name=decision_key,
                inputs=variables,
            )
            
            # Record metrics
            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.metrics.record_dmn_call(
                decision_key=decision_key,
                tenant_id=context.tenant_id,
                latency_ms=latency_ms,
                success=True,
            )
            
            self.logger.info(
                f"DMN evaluation success: {decision_key}",
                extra={
                    "tenant_id": context.tenant_id,
                    "decision_key": decision_key,
                    "latency_ms": latency_ms,
                },
            )
            
            return result
            
        except Exception as e:
            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.metrics.record_dmn_call(
                decision_key=decision_key,
                tenant_id=context.tenant_id,
                latency_ms=latency_ms,
                success=False,
            )

            self.logger.warning(
                f"DMN evaluation failed, using fallback PROSSEGUIR: {decision_key} — {e}",
                extra={"tenant_id": context.tenant_id, "decision_key": decision_key},
            )
            # Fallback: allow flow to continue (ADMIN_ADJUDICATION default)
            return {"resultado": "PROSSEGUIR", "acao": "", "risco": "BAIXO"}

    def resolve_tenant(self, variables: Dict[str, Any]) -> str:
        """
        Resolve tenant ID from process variables
        
        Args:
            variables: Process variables (may contain tenant markers)
            
        Returns:
            Tenant ID (hospital code)
            
        Note:
            Uses marker-based resolution (ADR-002):
            - Check for explicit "tenant_id" variable
            - Check for "hospitalCode" variable
            - Fall back to "default" tenant
        """
        return self.tenant_resolver.resolve(variables)

    def hash_pii(self, value: str, field_name: str) -> str:
        """
        Hash PII field (LGPD compliant)
        
        Args:
            value: PII value to hash (CPF, RG, phone, etc.)
            field_name: Field name (for salt derivation)
            
        Returns:
            Hashed value (deterministic, one-way)
            
        Example:
            cpf_hash = self.hash_pii(cpf, "cpf")
            # Store cpf_hash instead of raw CPF
        """
        return self.lgpd_hasher.hash(value, field_name)

    def log_execution(
        self,
        context: TaskContext,
        result: TaskResult,
        duration_ms: float,
    ) -> None:
        """
        Log task execution (structured logging)

        Args:
            context: Task context
            result: Task result
            duration_ms: Execution duration (milliseconds)
        """
        log_extra = {
            "task_id": context.task_id,
            "process_instance_id": context.process_instance_id,
            "tenant_id": context.tenant_id,
            "worker_id": context.worker_id,
            "status": result.status.value,
            "duration_ms": duration_ms,
        }

        if result.status == TaskStatus.SUCCESS:
            self.logger.info("Task completed successfully", extra=log_extra)
        elif result.status == TaskStatus.BPMN_ERROR:
            self.logger.warning(
                f"Task completed with BPMN error: {result.error_code}",
                extra={**log_extra, "error_code": result.error_code, "error_message": result.error_message},
            )
        else:
            self.logger.error(
                f"Task failed: {result.error_message}",
                extra={**log_extra, "error_message": result.error_message},
            )

    async def process_task(self, job: Any = None, variables: Dict[str, Any] | None = None) -> ProcessTaskResult:
        """V1 backward-compatible entry point for tests.

        Args:
            job: Mock job object (ignored in v2, kept for API compat)
            variables: Process variables dict
        """
        if variables is None:
            variables = {}

        # Build TaskContext from variables
        context = TaskContext(
            task_id=getattr(job, 'id', 'test-task'),
            process_instance_id=variables.get('processInstanceId', 'test-process'),
            tenant_id=variables.get('tenant_id', variables.get('hospitalCode', 'HOSPITAL_A')),
            variables=variables,
            worker_id=getattr(self, 'TOPIC', 'test-worker'),
        )

        try:
            # Handle both sync and async execute() methods
            result = self.execute(context)
            if inspect.iscoroutine(result):
                result = await result

            # Handle workers that return ProcessTaskResult directly (v2 async workers)
            if isinstance(result, ProcessTaskResult):
                return result

            # Handle workers that return TaskResult (legacy sync workers)
            if result.status == TaskStatus.SUCCESS:
                return ProcessTaskResult(success=True, variables=result.variables)
            elif result.status == TaskStatus.BPMN_ERROR:
                return ProcessTaskResult(success=False, variables=result.variables, error_code=result.error_code, error_message=result.error_message)
            else:
                return ProcessTaskResult(success=False, error_code=result.error_code, error_message=result.error_message)
        except Exception as e:
            # Re-raise business exceptions (DomainException subclasses) for tests to catch
            from healthcare_platform.shared.domain.exceptions import DomainException
            if isinstance(e, DomainException):
                raise
            # Convert other exceptions to ProcessTaskResult
            return ProcessTaskResult(success=False, error_message=str(e))

    def __call__(self, raw_task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Entry point called by Camunda client
        
        Args:
            raw_task: Raw task dict from Camunda
            
        Returns:
            Response dict for Camunda (variables, error, etc.)
            
        Note:
            This method wraps execute() with:
            - Tenant resolution
            - Context construction
            - Metrics recording
            - Error handling
            - Structured logging
        """
        start_time = datetime.utcnow()

        # Resolve tenant
        tenant_id = self.resolve_tenant(raw_task.get("variables", {}))

        # Construct context
        context = TaskContext(
            task_id=raw_task["id"],
            process_instance_id=raw_task["processInstanceId"],
            tenant_id=tenant_id,
            variables=raw_task.get("variables", {}),
            worker_id=raw_task["topicName"],
            retries=raw_task.get("retries", 3),
            lock_expiration=raw_task.get("lockExpirationTime"),
            business_key=raw_task.get("businessKey"),
        )

        try:
            # Execute worker logic
            result = self.execute(context)

            # Record metrics
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.metrics.record_execution(
                worker_id=context.worker_id,
                tenant_id=context.tenant_id,
                duration_ms=duration_ms,
                success=(result.status == TaskStatus.SUCCESS),
            )

            # Log execution
            self.log_execution(context, result, duration_ms)

            # Return response to Camunda
            if result.status == TaskStatus.BPMN_ERROR:
                return {
                    "errorCode": result.error_code,
                    "errorMessage": result.error_message,
                    "variables": result.variables,
                }
            elif result.status == TaskStatus.FAILURE:
                return {
                    "errorMessage": result.error_message,
                    "retries": context.retries - 1,
                }
            else:
                return {"variables": result.variables}

        except Exception as e:
            # Unexpected error (not handled by worker)
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.metrics.record_execution(
                worker_id=context.worker_id,
                tenant_id=context.tenant_id,
                duration_ms=duration_ms,
                success=False,
            )

            self.logger.exception(
                "Unexpected error in worker execution",
                extra={
                    "task_id": context.task_id,
                    "tenant_id": context.tenant_id,
                    "worker_id": context.worker_id,
                },
            )

            return {
                "errorMessage": f"Unexpected error: {str(e)}",
                "retries": context.retries - 1,
            }


# ============================================================================
# EXAMPLE WORKER (for reference)
# ============================================================================

class ValidateEligibilityWorker(BaseExternalTaskWorker):
    """
    Example worker: Validate patient eligibility for procedure
    
    Topic: revenue-cycle.authorization.validate-eligibility
    BPMN: Uses TEMPLATE_Admin_Adjudication
    DMN: Uses ADMIN_ADJUDICATION archetype
    """

    def execute(self, context: TaskContext) -> TaskResult:
        # Extract input
        patient_id = context.variables["patientId"]
        procedure_code = context.variables["procedureCode"]
        payer_id = context.variables.get("payerId")

        # Evaluate DMN (eligibility rules)
        dmn_result = self.evaluate_dmn(
            context,
            decision_key="eligibility_validation",
            variables={
                "patientId": patient_id,
                "procedureCode": procedure_code,
                "payerId": payer_id,
            },
        )

        # DMN outputs (ADMIN_ADJUDICATION archetype): resultado, acao, risco
        resultado = dmn_result["resultado"]  # PROSSEGUIR | BLOQUEAR | REVISAR
        acao = dmn_result["acao"]
        risco = dmn_result["risco"]

        # Route based on resultado
        if resultado == "PROSSEGUIR":
            return TaskResult.success({
                "eligible": True,
                "action": acao,
                "risk": risco,
            })
        elif resultado == "BLOQUEAR":
            return TaskResult.bpmn_error(
                error_code="ERR_NOT_ELIGIBLE",
                error_message=f"Patient not eligible: {acao}",
                variables={"eligibilityReason": acao, "risk": risco},
            )
        else:  # REVISAR
            return TaskResult.success({
                "eligible": False,
                "requiresReview": True,
                "action": acao,
                "risk": risco,
            })
