"""Factory classes para criação de test data."""

from __future__ import annotations

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from decimal import Decimal
import random


class PatientFactory:
    """Factory para criar dados de pacientes FHIR."""

    @staticmethod
    def create(
        patient_id: Optional[str] = None,
        cpf: Optional[str] = None,
        name_family: Optional[str] = None,
        name_given: Optional[List[str]] = None,
        gender: Optional[str] = None,
        birth_date: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Cria um paciente FHIR com valores default ou customizados.

        Args:
            patient_id: ID do paciente
            cpf: CPF do paciente
            name_family: Sobrenome
            name_given: Lista de nomes
            gender: Gênero (male/female/other)
            birth_date: Data de nascimento (YYYY-MM-DD)
            **kwargs: Campos adicionais

        Returns:
            Recurso FHIR Patient
        """
        patient_id = patient_id or f"patient-{random.randint(1000, 9999)}"
        cpf = cpf or f"{random.randint(10000000000, 99999999999)}"
        name_family = name_family or "Silva"
        name_given = name_given or ["João"]
        gender = gender or "male"
        birth_date = birth_date or "1980-01-01"

        patient = {
            "resourceType": "Patient",
            "id": patient_id,
            "identifier": [
                {
                    "system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf",
                    "value": cpf,
                }
            ],
            "name": [
                {
                    "use": "official",
                    "family": name_family,
                    "given": name_given,
                }
            ],
            "gender": gender,
            "birthDate": birth_date,
        }

        # Merge additional fields
        patient.update(kwargs)
        return patient


class AppointmentFactory:
    """Factory para criar dados de appointments FHIR."""

    @staticmethod
    def create(
        appointment_id: Optional[str] = None,
        status: Optional[str] = None,
        patient_ref: Optional[str] = None,
        practitioner_ref: Optional[str] = None,
        start_time: Optional[datetime] = None,
        duration_minutes: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Cria um appointment FHIR com valores default ou customizados.

        Args:
            appointment_id: ID do appointment
            status: Status (booked/cancelled/fulfilled)
            patient_ref: Referência ao paciente
            practitioner_ref: Referência ao profissional
            start_time: Data/hora de início
            duration_minutes: Duração em minutos
            **kwargs: Campos adicionais

        Returns:
            Recurso FHIR Appointment
        """
        appointment_id = appointment_id or f"appointment-{random.randint(1000, 9999)}"
        status = status or "booked"
        patient_ref = patient_ref or "Patient/patient-001"
        practitioner_ref = practitioner_ref or "Practitioner/practitioner-001"
        start_time = start_time or (datetime.now() + timedelta(days=7))
        duration_minutes = duration_minutes or 30

        end_time = start_time + timedelta(minutes=duration_minutes)

        appointment = {
            "resourceType": "Appointment",
            "id": appointment_id,
            "status": status,
            "start": start_time.isoformat() + "Z",
            "end": end_time.isoformat() + "Z",
            "minutesDuration": duration_minutes,
            "participant": [
                {
                    "actor": {"reference": patient_ref},
                    "status": "accepted",
                },
                {
                    "actor": {"reference": practitioner_ref},
                    "status": "accepted",
                },
            ],
        }

        appointment.update(kwargs)
        return appointment


class BillingFactory:
    """Factory para criar dados de billing/faturamento."""

    @staticmethod
    def create(
        invoice_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        patient_id: Optional[str] = None,
        insurance_type: Optional[str] = None,
        procedure_code: Optional[str] = None,
        unit_value: Optional[Decimal] = None,
        quantity: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Cria dados de billing com valores default ou customizados.

        Args:
            invoice_id: ID da fatura
            tenant_id: ID do tenant
            patient_id: ID do paciente
            insurance_type: Tipo de convênio
            procedure_code: Código do procedimento
            unit_value: Valor unitário
            quantity: Quantidade
            **kwargs: Campos adicionais

        Returns:
            Dados de billing
        """
        invoice_id = invoice_id or f"INV-{random.randint(10000, 99999)}"
        tenant_id = tenant_id or "austa-001"
        patient_id = patient_id or "patient-001"
        insurance_type = insurance_type or "AMB"
        procedure_code = procedure_code or "10101012"
        unit_value = unit_value or Decimal("150.00")
        quantity = quantity or 1

        total_value = unit_value * quantity

        billing = {
            "invoice_id": invoice_id,
            "tenant_id": tenant_id,
            "patient_id": patient_id,
            "insurance_type": insurance_type,
            "billing_date": datetime.now().date().isoformat(),
            "procedures": [
                {
                    "code": procedure_code,
                    "description": f"Procedimento {procedure_code}",
                    "quantity": quantity,
                    "unit_value": unit_value,
                    "total_value": total_value,
                }
            ],
            "total_amount": total_value,
            "status": "pending",
        }

        billing.update(kwargs)
        return billing


class TenantFactory:
    """Factory para criar dados de tenant."""

    @staticmethod
    def create(
        tenant_id: Optional[str] = None,
        tenant_code: Optional[str] = None,
        name: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Cria configuração de tenant com valores default ou customizados.

        Args:
            tenant_id: ID do tenant
            tenant_code: Código do tenant (AUSTA/HPA)
            name: Nome do tenant
            **kwargs: Campos adicionais

        Returns:
            Configuração de tenant
        """
        tenant_id = tenant_id or f"tenant-{random.randint(100, 999)}"
        tenant_code = tenant_code or "AUSTA"
        name = name or f"Hospital {tenant_code}"

        tenant = {
            "tenant_id": tenant_id,
            "tenant_code": tenant_code,
            "name": name,
            "database_config": {
                "host": "localhost",
                "port": 5432,
                "database": f"{tenant_code.lower()}_db",
                "schema": tenant_code.lower(),
            },
            "fhir_base_url": f"http://fhir.{tenant_code.lower()}.local/fhir/r4",
            "features": {
                "whatsapp_notifications": True,
                "ai_medical_coding": True,
                "automatic_billing": True,
            },
        }

        tenant.update(kwargs)
        return tenant
