"""
Example usage of TASY and TISS integration clients.

This demonstrates how to use the integration clients in Camunda workers
for the hospital revenue cycle process.
"""

import asyncio
from decimal import Decimal

from revenue_cycle.config import Settings
from revenue_cycle.integrations.tasy import TasyClient
from revenue_cycle.integrations.tiss import (
    TissAppealRequest,
    TissClient,
)
from revenue_cycle.multi_tenant.credentials import TenantCredentialManager


async def example_tasy_integration(
    credential_manager: TenantCredentialManager,
    tenant_id: str,
) -> None:
    """
    Example: Fetch patient and billing data from TASY.

    This would be used in workers like:
    - ValidateEligibilityWorker
    - ApplyContractRulesWorker
    - SubmitClaimWorker
    """
    async with TasyClient(credential_manager, tenant_id) as tasy:
        # 1. Get patient data
        patient = await tasy.get_patient("12345")
        print(f"Patient: {patient.nome} (CPF: {patient.cpf})")

        # 2. Get encounter data
        encounter = await tasy.get_encounter("encounter-67890")
        print(f"Encounter: {encounter.tipo_atendimento} ({encounter.convenio})")

        # 3. Get procedures and diagnoses
        procedures = await tasy.get_procedures("encounter-67890")
        diagnoses = await tasy.get_diagnoses("encounter-67890")
        print(f"Procedures: {len(procedures)}, Diagnoses: {len(diagnoses)}")

        # 4. Get complete billing items for TISS submission
        billing_item = await tasy.get_billing_items("encounter-67890")
        print(f"Total billing: R$ {billing_item.total_amount}")

        # 5. Check circuit breaker state
        print(f"Circuit breaker: {tasy.circuit_breaker_state}")


async def example_tiss_submission(
    credential_manager: TenantCredentialManager,
    tenant_id: str,
    claim_xml: str,
) -> None:
    """
    Example: Submit claim to TISS and track status.

    This would be used in workers like:
    - SubmitClaimWorker
    - CheckClaimStatusWorker
    """
    async with TissClient(credential_manager, tenant_id) as tiss:
        # Check certificate expiration
        days_remaining = tiss.certificate_expires_in_days
        print(f"Certificate expires in {days_remaining} days")

        # 1. Submit claim to insurance portal
        submission = await tiss.submit_claim(claim_xml)
        print(f"Claim submitted: Protocol {submission.protocol_number}")
        print(f"Batch ID: {submission.batch_id}")
        print(f"Status: {submission.status}")

        # 2. Check claim status (after some time)
        await asyncio.sleep(60)  # Wait 1 minute

        status = await tiss.check_claim_status(submission.protocol_number)
        print(f"Current status: {status.status}")
        print(f"Approved amount: R$ {status.approved_amount}")
        print(f"Glosa count: {status.glosa_count}")

        # 3. Get batch summary
        batch = await tiss.get_batch_summary(submission.batch_id)
        print(f"Batch: {batch.total_claims} claims, R$ {batch.total_amount}")


async def example_glosa_appeal(
    credential_manager: TenantCredentialManager,
    tenant_id: str,
    batch_id: str,
) -> None:
    """
    Example: Handle glosas and submit appeals.

    This would be used in workers like:
    - SearchEvidenceWorker
    - PrepareGlosaAppealWorker
    - RegisterLossWorker
    """
    async with TissClient(credential_manager, tenant_id) as tiss:
        # 1. Get all glosas for batch
        glosas = await tiss.get_glosas(batch_id)
        print(f"Found {len(glosas)} glosas")

        for glosa in glosas:
            print(f"\nGlosa: {glosa.glosa_id}")
            print(f"Type: {glosa.glosa_type}")
            print(f"Procedure: {glosa.procedure_description}")
            print(f"Denied amount: R$ {glosa.denied_amount}")
            print(f"Reason: {glosa.reason_description}")
            print(f"Appealable: {glosa.is_appealable}")
            print(f"Appeal deadline: {glosa.appeal_deadline}")

            # 2. Submit appeal if appealable
            if glosa.is_appealable:
                appeal = TissAppealRequest(
                    glosa_id=glosa.glosa_id,
                    protocol_number=glosa.protocol_number,
                    appeal_reason="Clinical justification with supporting evidence",
                    clinical_justification=(
                        "Procedure was medically necessary based on patient condition. "
                        "CID-10 diagnosis supports the procedure performed. "
                        "Medical record shows clear indication for intervention."
                    ),
                    supporting_documents=[
                        "medical_record_summary.pdf",
                        "lab_results_20240104.pdf",
                        "physician_notes.pdf",
                    ],
                    medical_record_summary=(
                        "Patient presented with acute symptoms requiring immediate intervention. "
                        "Diagnostic tests confirmed indication. Procedure performed successfully "
                        "with good clinical outcome."
                    ),
                    requested_amount=glosa.denied_amount,
                )

                appeal_response = await tiss.submit_appeal(appeal)
                print(f"Appeal submitted: Protocol {appeal_response.appeal_protocol}")
                print(f"Status: {appeal_response.status}")


async def example_integrated_workflow(
    credential_manager: TenantCredentialManager,
    tenant_id: str,
    encounter_id: str,
) -> None:
    """
    Example: Complete workflow from TASY data retrieval to TISS submission.

    This demonstrates the full integration flow.
    """
    print("=== Integrated Revenue Cycle Workflow ===\n")

    # Step 1: Fetch billing data from TASY
    print("Step 1: Fetching billing data from TASY...")
    async with TasyClient(credential_manager, tenant_id) as tasy:
        billing_item = await tasy.get_billing_items(encounter_id)
        print(f"✓ Retrieved billing data: R$ {billing_item.total_amount}")

        # Get medical record for potential appeals
        medical_record = await tasy.get_medical_record(
            billing_item.patient_cpf,
            encounter_id,
        )
        print(f"✓ Retrieved medical record with {len(medical_record.procedures)} procedures")

    # Step 2: Generate TISS XML (simplified)
    print("\nStep 2: Generating TISS claim XML...")
    claim_xml = _generate_tiss_xml(billing_item)
    print("✓ TISS XML generated")

    # Step 3: Submit to TISS
    print("\nStep 3: Submitting claim to TISS portal...")
    async with TissClient(credential_manager, tenant_id) as tiss:
        submission = await tiss.submit_claim(claim_xml)
        print(f"✓ Claim submitted: {submission.protocol_number}")

        # Step 4: Monitor for glosas
        print("\nStep 4: Checking for glosas...")
        await asyncio.sleep(5)  # Simulate processing time

        status = await tiss.check_claim_status(submission.protocol_number)
        print(f"✓ Status: {status.status}")

        if status.glosa_count > 0:
            print(f"⚠ Found {status.glosa_count} glosas")

            # Step 5: Handle glosas with evidence from medical record
            glosas = await tiss.get_glosas(submission.batch_id)
            for glosa in glosas[:1]:  # Handle first glosa
                if glosa.is_appealable:
                    print(f"\nStep 5: Submitting appeal for glosa {glosa.glosa_id}...")
                    appeal = TissAppealRequest(
                        glosa_id=glosa.glosa_id,
                        protocol_number=glosa.protocol_number,
                        appeal_reason="Medical justification with complete documentation",
                        clinical_justification=medical_record.evolucao or "Clinical notes",
                        supporting_documents=["medical_record.pdf"],
                        medical_record_summary=medical_record.discharge_summary or "Summary",
                        requested_amount=glosa.denied_amount,
                    )
                    appeal_response = await tiss.submit_appeal(appeal)
                    print(f"✓ Appeal submitted: {appeal_response.appeal_protocol}")
        else:
            print("✓ No glosas found")

    print("\n=== Workflow Complete ===")


def _generate_tiss_xml(billing_item) -> str:
    """
    Generate TISS XML from billing item.

    Note: This is a simplified example. In production, use proper
    TISS XML schema generation with templates or XML libraries.
    """
    procedures_xml = "\n".join(
        f"""
        <procedure>
            <code>{proc.code}</code>
            <description>{proc.description}</description>
            <quantity>{proc.quantity}</quantity>
            <unitPrice>{proc.unit_price}</unitPrice>
        </procedure>
        """
        for proc in billing_item.procedures
    )

    diagnoses_xml = "\n".join(
        f"<diagnosis><code>{diag.code_cid10}</code></diagnosis>" for diag in billing_item.diagnoses
    )

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<tissClaim xmlns="http://www.ans.gov.br/tiss/schemas">
    <header>
        <protocolVersion>3.05.00</protocolVersion>
        <transactionDate>{billing_item.date_service_start.isoformat()}</transactionDate>
    </header>
    <patient>
        <cpf>{billing_item.patient_cpf}</cpf>
        <insuranceCardNumber>{billing_item.numero_carteirinha}</insuranceCardNumber>
    </patient>
    <encounter>
        <encounterId>{billing_item.encounter_id}</encounterId>
        <serviceStart>{billing_item.date_service_start.isoformat()}</serviceStart>
        <serviceEnd>{billing_item.date_service_end.isoformat() if billing_item.date_service_end else ''}</serviceEnd>
    </encounter>
    <diagnoses>
        {diagnoses_xml}
    </diagnoses>
    <procedures>
        {procedures_xml}
    </procedures>
    <billing>
        <totalAmount>{billing_item.total_amount}</totalAmount>
        <insurance>{billing_item.convenio}</insurance>
    </billing>
</tissClaim>"""
    return xml


async def main():
    """Run examples."""
    # Initialize settings and credential manager
    settings = Settings()
    credential_manager = TenantCredentialManager(settings)
    await credential_manager.initialize()

    tenant_id = "hospital-abc-123"

    try:
        # Run examples
        # await example_tasy_integration(credential_manager, tenant_id)
        # await example_tiss_submission(credential_manager, tenant_id, "<xml>...</xml>")
        # await example_glosa_appeal(credential_manager, tenant_id, "batch-123")

        # Run full integrated workflow
        await example_integrated_workflow(
            credential_manager,
            tenant_id,
            "encounter-67890",
        )

    finally:
        await credential_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
