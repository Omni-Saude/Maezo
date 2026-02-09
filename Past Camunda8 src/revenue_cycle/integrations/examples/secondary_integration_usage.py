"""Usage examples for LIS, PACS, and WhatsApp integrations."""

import asyncio
from revenue_cycle.config import get_settings
from revenue_cycle.multi_tenant.credentials import TenantCredentialManager
from revenue_cycle.integrations.lis import LISClient
from revenue_cycle.integrations.pacs import PACSClient
from revenue_cycle.integrations.whatsapp import WhatsAppClient, WhatsAppTemplateType


async def example_lis_integration():
    """Example: Using LIS client to retrieve lab results for glosa appeal."""
    settings = get_settings()
    lis_client = LISClient(settings, tenant_id="hospital-abc")

    # Get lab order details
    order = await lis_client.get_lab_order("LAB-12345")
    print(f"Lab Order: {order.order_id}, Patient: {order.patient_id}, Status: {order.status}")

    # Get results for the order
    results = await lis_client.get_lab_results("LAB-12345")
    for result in results:
        print(f"Test: {result.test_name}, Result: {result.result} {result.unit}")
        if result.abnormal_flag and result.abnormal_flag != "N":
            print(f"  ⚠️ Abnormal: {result.abnormal_flag}")

    # Search all lab results for encounter (for glosa appeal evidence)
    encounter_results = await lis_client.search_results_by_encounter("ENC-2026-001")
    print(f"Found {len(encounter_results)} lab results for encounter")


async def example_pacs_integration():
    """Example: Using PACS client to retrieve imaging studies for glosa appeal."""
    settings = get_settings()
    pacs_client = PACSClient(settings, tenant_id="hospital-abc")

    # Get imaging study details
    study = await pacs_client.get_study("1.2.840.113619.2.55.3.12345")
    print(f"Study: {study.study_id}, Modality: {study.modality}, Date: {study.study_date}")

    # Search all imaging studies for encounter (for glosa appeal evidence)
    encounter_studies = await pacs_client.search_studies_by_encounter("ENC-2026-001")
    for study in encounter_studies:
        print(f"Study: {study.modality} - {study.description}")

        # Get radiology report
        report = await pacs_client.get_report(study.study_id)
        print(f"  Radiologist: {report.radiologist}")
        print(f"  Impression: {report.impression}")


async def example_whatsapp_integration():
    """Example: Using WhatsApp client to send patient notifications."""
    settings = get_settings()
    
    # Initialize credential manager
    credential_manager = TenantCredentialManager(settings)
    await credential_manager.initialize()

    # Create WhatsApp client
    whatsapp_client = WhatsAppClient(credential_manager, "hospital-abc")

    # Send hospitalization notification
    response = await whatsapp_client.send_template_message(
        to="11999887766",  # Phone without +55 (will be auto-formatted)
        template_name=WhatsAppTemplateType.INTERNACAO_NOTIFICACAO,
        template_params={
            "patient_name": "João Silva",
            "hospital_name": "Hospital ABC",
            "admission_date": "05/02/2026",
        },
    )
    print(f"Message sent: {response.message_id}, Status: {response.status}")

    # Send discharge notification
    response = await whatsapp_client.send_template_message(
        to="+5511999887766",  # Phone with +55
        template_name=WhatsAppTemplateType.ALTA_HOSPITALAR,
        template_params={
            "patient_name": "João Silva",
            "discharge_date": "10/02/2026",
            "follow_up_instructions": "Retorno em 7 dias",
        },
    )

    # Send payment reminder
    response = await whatsapp_client.send_template_message(
        to="11999887766",
        template_name=WhatsAppTemplateType.COBRANCA_LEMBRETE,
        template_params={
            "patient_name": "Maria Santos",
            "invoice_number": "FAT-2026-001",
            "amount_due": "R$ 1.250,00",
            "due_date": "15/02/2026",
        },
    )

    # Send simple text message (within 24h conversation window)
    response = await whatsapp_client.send_text_message(
        to="11999887766",
        text="Olá! Seu resultado de exame está pronto. Acesse o portal do paciente.",
    )


async def example_glosa_appeal_evidence_gathering():
    """
    Example: Comprehensive evidence gathering for glosa appeal.
    
    When a payer denies a claim (glosa), we need to gather all clinical
    documentation to support the appeal:
    - Lab results (LIS)
    - Imaging studies and reports (PACS)
    - Patient notifications (WhatsApp)
    """
    settings = get_settings()
    encounter_id = "ENC-2026-001"
    
    # Initialize clients
    lis_client = LISClient(settings, tenant_id="hospital-abc")
    pacs_client = PACSClient(settings, tenant_id="hospital-abc")
    
    print(f"Gathering evidence for encounter: {encounter_id}")
    
    # Gather lab evidence
    lab_results = await lis_client.search_results_by_encounter(encounter_id)
    print(f"✓ Found {len(lab_results)} lab results")
    
    # Gather imaging evidence
    imaging_studies = await pacs_client.search_studies_by_encounter(encounter_id)
    print(f"✓ Found {len(imaging_studies)} imaging studies")
    
    # Get detailed reports
    reports = []
    for study in imaging_studies:
        report = await pacs_client.get_report(study.study_id)
        reports.append(report)
    print(f"✓ Retrieved {len(reports)} radiology reports")
    
    # Compile evidence package
    evidence_package = {
        "encounter_id": encounter_id,
        "lab_results": [
            {
                "test": r.test_name,
                "result": r.result,
                "date": r.result_date.isoformat(),
                "abnormal": r.abnormal_flag != "N" if r.abnormal_flag else False,
            }
            for r in lab_results
        ],
        "imaging_studies": [
            {
                "modality": s.modality,
                "description": s.description,
                "date": s.study_date.isoformat(),
            }
            for s in imaging_studies
        ],
        "radiology_reports": [
            {
                "study_id": r.study_id,
                "radiologist": r.radiologist,
                "impression": r.impression,
                "date": r.report_date.isoformat(),
            }
            for r in reports
        ],
    }
    
    print("\n📦 Evidence Package:")
    print(f"  Lab results: {len(evidence_package['lab_results'])}")
    print(f"  Imaging studies: {len(evidence_package['imaging_studies'])}")
    print(f"  Radiology reports: {len(evidence_package['radiology_reports'])}")
    
    return evidence_package


if __name__ == "__main__":
    # Run examples
    print("=== LIS Integration Example ===")
    asyncio.run(example_lis_integration())
    
    print("\n=== PACS Integration Example ===")
    asyncio.run(example_pacs_integration())
    
    print("\n=== WhatsApp Integration Example ===")
    asyncio.run(example_whatsapp_integration())
    
    print("\n=== Glosa Appeal Evidence Gathering ===")
    evidence = asyncio.run(example_glosa_appeal_evidence_gathering())
