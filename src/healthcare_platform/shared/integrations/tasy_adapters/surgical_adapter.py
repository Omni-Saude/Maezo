"""Tasy Surgical Services to FHIR R4 adapter.

Maps Tasy surgical API responses to FHIR resources:
- Operating room management (Location, Schedule, Slot)
- Surgery scheduling (Procedure)
- Team assignment (PractitionerRole, CareTeam, Schedule)
- Materials and kits (SupplyRequest, SupplyDelivery, Device)
- Surgical records (Procedure, DiagnosticReport, AdverseEvent, Observation)

Example Tasy data:
{
    "operation_type": "surgery_creation",
    "NR_CIRURGIA": "SRG-12345",
    "NR_PACIENTE": "123456",
    "NR_ATENDIMENTO": "ATD-789",
    "CD_SALA": "OR-01",
    "DT_CIRURGIA": "2024-02-15T08:00:00",
    "HR_INICIO": "08:00",
    "HR_FIM": "10:30",
    "CD_PROCEDIMENTO": "40301052",
    "DS_PROCEDIMENTO": "Apendicectomia laparoscópica",
    "NR_MEDICO": "MED-001",
    "IE_STATUS": "SCHEDULED"
}
"""

from __future__ import annotations

from typing import Any

from healthcare_platform.shared.integrations.tasy_adapters.base_adapter import (
    BaseTasyFhirAdapter,
)


class TasySurgicalAdapter(BaseTasyFhirAdapter):
    """Adapter for converting Tasy surgical data to FHIR R4 resources."""

    ADAPTER_TYPE = "surgical"
    FHIR_RESOURCE_TYPE = "Procedure"

    SURGICAL_PII_FIELDS = {
        "DS_COMPLICACAO",
        "DS_EVOLUCAO",
        "DS_ANAMNESE",
        "NM_PACIENTE",
        "NR_CPF",
    }

    TASY_SURGERY_SYSTEM = "http://tasy.com/fhir/identifier/surgery"
    TASY_ROOM_SYSTEM = "http://tasy.com/fhir/identifier/operating-room"
    TASY_TEAM_SYSTEM = "http://tasy.com/fhir/identifier/surgical-team"
    TASY_MATERIAL_SYSTEM = "http://tasy.com/fhir/identifier/surgical-material"

    TUSS_SYSTEM = "http://www.ans.gov.br/tuss"
    SNOMED_SYSTEM = "http://snomed.info/sct"

    SURGERY_STATUS_MAP = {
        "SCHEDULED": "preparation",
        "IN_PROGRESS": "in-progress",
        "COMPLETED": "completed",
        "CANCELLED": "cancelled",
        "SUSPENDED": "stopped",
    }

    ROOM_STATUS_MAP = {
        "AVAILABLE": "active",
        "OCCUPIED": "active",
        "CLEANING": "inactive",
        "MAINTENANCE": "suspended",
    }

    def __init__(
        self,
        fhir_client,
        tenant_id: str,
    ) -> None:
        """Initialize surgical adapter.

        Args:
            fhir_client: FHIR client for creating/updating resources
            tenant_id: Tenant identifier for multi-tenancy
        """
        super().__init__(fhir_client, tenant_id)
        self.PII_FIELDS.update(self.SURGICAL_PII_FIELDS)

    async def adapt(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Tasy surgical data to FHIR R4 resource.

        Routes to specific adapter method based on operation_type.

        Args:
            tasy_data: Tasy surgical data

        Returns:
            FHIR R4 resource (type depends on operation_type)

        Raises:
            ValueError: If required fields are missing or operation_type unknown
        """
        try:
            self._validate_required_fields(tasy_data, ["operation_type"])

            operation_type = tasy_data["operation_type"]

            self._logger.debug(
                "Converting Tasy surgical data to FHIR",
                extra={
                    "operation_type": operation_type,
                    "tenant_id": self._tenant_id,
                },
            )

            adapter_method = {
                "room_availability": self.adapt_room_availability,
                "room_schedule": self.adapt_room_schedule,
                "room_booking": self.adapt_room_booking,
                "room_release": self.adapt_room_release,
                "turnover_status": self.adapt_turnover_status,
                "surgery_creation": self.adapt_surgery_creation,
                "surgery_update": self.adapt_surgery_update,
                "surgery_cancellation": self.adapt_surgery_cancellation,
                "surgery_details": self.adapt_surgery_details,
                "surgery_search": self.adapt_surgery_search,
                "surgeon_availability": self.adapt_surgeon_availability,
                "team_assignment": self.adapt_team_assignment,
                "team_availability": self.adapt_team_availability,
                "preference_card": self.adapt_preference_card,
                "material_request": self.adapt_material_request,
                "material_availability": self.adapt_material_availability,
                "surgical_kit": self.adapt_surgical_kit,
                "surgical_record": self.adapt_surgical_record,
                "surgical_notes": self.adapt_surgical_notes,
                "complication": self.adapt_complication,
                "surgical_outcome": self.adapt_surgical_outcome,
            }.get(operation_type)

            if not adapter_method:
                raise ValueError(f"Unknown operation_type: {operation_type}")

            return await adapter_method(tasy_data)

        except Exception as exc:
            self._track_conversion_error(type(exc).__name__)
            self._logger.error(
                "Failed to convert Tasy surgical data to FHIR",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "tenant_id": self._tenant_id,
                    "tasy_data": self._sanitize_for_lgpd(tasy_data),
                },
            )
            raise

    async def adapt_room_availability(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert operating room availability to FHIR Location.

        Args:
            tasy_data: Tasy room availability data

        Returns:
            FHIR Location R4 resource
        """
        self._validate_required_fields(tasy_data, ["CD_SALA"])

        location = {
            "resourceType": "Location",
            "meta": {
                "profile": ["http://hl7.org/fhir/StructureDefinition/Location"],
                "tag": [{"system": "http://tasy.com/fhir/tenant", "code": self._tenant_id}],
            },
            "identifier": [
                self._build_identifier(
                    system=self.TASY_ROOM_SYSTEM,
                    value=tasy_data["CD_SALA"],
                )
            ],
            "status": self.ROOM_STATUS_MAP.get(tasy_data.get("IE_STATUS", "AVAILABLE"), "active"),
            "name": tasy_data.get("DS_SALA", tasy_data["CD_SALA"]),
            "mode": "instance",
            "type": [
                self._build_codeable_concept(
                    codings=[
                        self._build_coding(
                            system=self.SNOMED_SYSTEM,
                            code="225738002",
                            display="Operating theatre",
                        )
                    ],
                    text="Operating Room",
                )
            ],
            "physicalType": self._build_codeable_concept(
                codings=[
                    self._build_coding(
                        system="http://terminology.hl7.org/CodeSystem/location-physical-type",
                        code="ro",
                        display="Room",
                    )
                ],
            ),
        }

        if "NR_ANDAR" in tasy_data:
            location["extension"] = [
                {
                    "url": "http://tasy.com/fhir/StructureDefinition/floor-number",
                    "valueString": str(tasy_data["NR_ANDAR"]),
                }
            ]

        self._track_conversion_success()
        return location

    async def adapt_room_schedule(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert room schedule to FHIR Schedule.

        Args:
            tasy_data: Tasy room schedule data

        Returns:
            FHIR Schedule R4 resource
        """
        self._validate_required_fields(tasy_data, ["CD_SALA", "DT_INICIO", "DT_FIM"])

        schedule = {
            "resourceType": "Schedule",
            "meta": {
                "profile": ["http://hl7.org/fhir/StructureDefinition/Schedule"],
                "tag": [{"system": "http://tasy.com/fhir/tenant", "code": self._tenant_id}],
            },
            "identifier": [
                self._build_identifier(
                    system=self.TASY_ROOM_SYSTEM,
                    value=f"{tasy_data['CD_SALA']}-{tasy_data['DT_INICIO']}",
                )
            ],
            "active": True,
            "serviceType": [
                self._build_codeable_concept(
                    codings=[
                        self._build_coding(
                            system=self.SNOMED_SYSTEM,
                            code="387713003",
                            display="Surgical procedure",
                        )
                    ],
                )
            ],
            "actor": [
                self._build_reference("Location", tasy_data["CD_SALA"], tasy_data.get("DS_SALA"))
            ],
            "planningHorizon": {
                "start": tasy_data["DT_INICIO"],
                "end": tasy_data["DT_FIM"],
            },
        }

        self._track_conversion_success()
        return schedule

    async def adapt_room_booking(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert room booking to FHIR Slot.

        Args:
            tasy_data: Tasy room booking data

        Returns:
            FHIR Slot R4 resource
        """
        self._validate_required_fields(tasy_data, ["CD_SALA", "DT_INICIO", "DT_FIM"])

        slot = {
            "resourceType": "Slot",
            "meta": {
                "profile": ["http://hl7.org/fhir/StructureDefinition/Slot"],
                "tag": [{"system": "http://tasy.com/fhir/tenant", "code": self._tenant_id}],
            },
            "identifier": [
                self._build_identifier(
                    system=self.TASY_ROOM_SYSTEM,
                    value=f"{tasy_data['CD_SALA']}-{tasy_data['DT_INICIO']}",
                )
            ],
            "serviceType": [
                self._build_codeable_concept(
                    codings=[
                        self._build_coding(
                            system=self.SNOMED_SYSTEM,
                            code="387713003",
                            display="Surgical procedure",
                        )
                    ],
                )
            ],
            "schedule": self._build_reference("Schedule", f"{tasy_data['CD_SALA']}-schedule"),
            "status": "busy",
            "start": tasy_data["DT_INICIO"],
            "end": tasy_data["DT_FIM"],
        }

        self._track_conversion_success()
        return slot

    async def adapt_room_release(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert room release to FHIR Slot.

        Args:
            tasy_data: Tasy room release data

        Returns:
            FHIR Slot R4 resource
        """
        self._validate_required_fields(tasy_data, ["CD_SALA", "DT_INICIO", "DT_FIM"])

        slot = {
            "resourceType": "Slot",
            "meta": {
                "profile": ["http://hl7.org/fhir/StructureDefinition/Slot"],
                "tag": [{"system": "http://tasy.com/fhir/tenant", "code": self._tenant_id}],
            },
            "identifier": [
                self._build_identifier(
                    system=self.TASY_ROOM_SYSTEM,
                    value=f"{tasy_data['CD_SALA']}-{tasy_data['DT_INICIO']}",
                )
            ],
            "schedule": self._build_reference("Schedule", f"{tasy_data['CD_SALA']}-schedule"),
            "status": "free",
            "start": tasy_data["DT_INICIO"],
            "end": tasy_data["DT_FIM"],
        }

        self._track_conversion_success()
        return slot

    async def adapt_turnover_status(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert turnover status to FHIR Observation.

        Args:
            tasy_data: Tasy turnover metrics data

        Returns:
            FHIR Observation R4 resource
        """
        self._validate_required_fields(tasy_data, ["CD_SALA", "DT_TURNOVER"])

        observation = {
            "resourceType": "Observation",
            "meta": {
                "profile": ["http://hl7.org/fhir/StructureDefinition/Observation"],
                "tag": [{"system": "http://tasy.com/fhir/tenant", "code": self._tenant_id}],
            },
            "identifier": [
                self._build_identifier(
                    system=self.TASY_ROOM_SYSTEM,
                    value=f"turnover-{tasy_data['CD_SALA']}-{tasy_data['DT_TURNOVER']}",
                )
            ],
            "status": "final",
            "category": [
                self._build_codeable_concept(
                    codings=[
                        self._build_coding(
                            system="http://terminology.hl7.org/CodeSystem/observation-category",
                            code="procedure",
                        )
                    ],
                )
            ],
            "code": self._build_codeable_concept(
                codings=[
                    self._build_coding(
                        system="http://tasy.com/fhir/CodeSystem/metrics",
                        code="OR-TURNOVER",
                        display="Operating Room Turnover Time",
                    )
                ],
                text="OR Turnover Time",
            ),
            "effectiveDateTime": tasy_data["DT_TURNOVER"],
        }

        if "VL_TEMPO_MINUTOS" in tasy_data:
            observation["valueQuantity"] = {
                "value": tasy_data["VL_TEMPO_MINUTOS"],
                "unit": "min",
                "system": "http://unitsofmeasure.org",
                "code": "min",
            }

        self._track_conversion_success()
        return observation

    async def adapt_surgery_creation(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert surgery creation to FHIR Procedure.

        Args:
            tasy_data: Tasy surgery creation data

        Returns:
            FHIR Procedure R4 resource
        """
        return await self._build_surgery_procedure(tasy_data, "preparation")

    async def adapt_surgery_update(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert surgery update to FHIR Procedure.

        Args:
            tasy_data: Tasy surgery update data

        Returns:
            FHIR Procedure R4 resource
        """
        status = self.SURGERY_STATUS_MAP.get(tasy_data.get("IE_STATUS", "SCHEDULED"), "preparation")
        return await self._build_surgery_procedure(tasy_data, status)

    async def adapt_surgery_cancellation(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert surgery cancellation to FHIR Procedure.

        Args:
            tasy_data: Tasy surgery cancellation data

        Returns:
            FHIR Procedure R4 resource
        """
        return await self._build_surgery_procedure(tasy_data, "cancelled")

    async def adapt_surgery_details(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert surgery details to FHIR Procedure.

        Args:
            tasy_data: Tasy surgery details data

        Returns:
            FHIR Procedure R4 resource
        """
        status = self.SURGERY_STATUS_MAP.get(tasy_data.get("IE_STATUS", "SCHEDULED"), "preparation")
        return await self._build_surgery_procedure(tasy_data, status)

    async def adapt_surgery_search(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert surgery search results to FHIR Bundle.

        Args:
            tasy_data: Tasy surgery search results

        Returns:
            FHIR Bundle R4 resource
        """
        bundle = {
            "resourceType": "Bundle",
            "type": "searchset",
            "total": len(tasy_data.get("results", [])),
            "entry": [],
        }

        for surgery in tasy_data.get("results", []):
            status = self.SURGERY_STATUS_MAP.get(surgery.get("IE_STATUS", "SCHEDULED"), "preparation")
            procedure = await self._build_surgery_procedure(surgery, status)
            bundle["entry"].append(
                {
                    "fullUrl": f"Procedure/{surgery.get('NR_CIRURGIA')}",
                    "resource": procedure,
                }
            )

        self._track_conversion_success()
        return bundle

    async def adapt_surgeon_availability(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert surgeon availability to FHIR PractitionerRole.

        Args:
            tasy_data: Tasy surgeon availability data

        Returns:
            FHIR PractitionerRole R4 resource
        """
        self._validate_required_fields(tasy_data, ["NR_MEDICO"])

        practitioner_role = {
            "resourceType": "PractitionerRole",
            "meta": {
                "profile": ["http://hl7.org/fhir/StructureDefinition/PractitionerRole"],
                "tag": [{"system": "http://tasy.com/fhir/tenant", "code": self._tenant_id}],
            },
            "identifier": [
                self._build_identifier(
                    system="http://tasy.com/fhir/identifier/practitioner",
                    value=tasy_data["NR_MEDICO"],
                )
            ],
            "active": tasy_data.get("IE_ATIVO", True),
            "practitioner": self._build_reference(
                "Practitioner",
                tasy_data["NR_MEDICO"],
                tasy_data.get("NM_MEDICO"),
            ),
            "code": [
                self._build_codeable_concept(
                    codings=[
                        self._build_coding(
                            system=self.SNOMED_SYSTEM,
                            code="304292004",
                            display="Surgeon",
                        )
                    ],
                )
            ],
        }

        if "availableTimes" in tasy_data:
            practitioner_role["availableTime"] = [
                {
                    "daysOfWeek": slot.get("days", []),
                    "availableStartTime": slot.get("start"),
                    "availableEndTime": slot.get("end"),
                }
                for slot in tasy_data["availableTimes"]
            ]

        self._track_conversion_success()
        return practitioner_role

    async def adapt_team_assignment(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert team assignment to FHIR CareTeam.

        Args:
            tasy_data: Tasy team assignment data

        Returns:
            FHIR CareTeam R4 resource
        """
        self._validate_required_fields(tasy_data, ["NR_CIRURGIA"])

        care_team = {
            "resourceType": "CareTeam",
            "meta": {
                "profile": ["http://hl7.org/fhir/StructureDefinition/CareTeam"],
                "tag": [{"system": "http://tasy.com/fhir/tenant", "code": self._tenant_id}],
            },
            "identifier": [
                self._build_identifier(
                    system=self.TASY_TEAM_SYSTEM,
                    value=f"team-{tasy_data['NR_CIRURGIA']}",
                )
            ],
            "status": "active",
            "category": [
                self._build_codeable_concept(
                    codings=[
                        self._build_coding(
                            system="http://loinc.org",
                            code="LA27976-2",
                            display="Surgical team",
                        )
                    ],
                )
            ],
            "name": tasy_data.get("DS_EQUIPE", f"Surgical Team {tasy_data['NR_CIRURGIA']}"),
            "subject": self._build_reference("Patient", tasy_data.get("NR_PACIENTE", "")),
            "participant": [],
        }

        if "team_members" in tasy_data:
            for member in tasy_data["team_members"]:
                care_team["participant"].append(
                    {
                        "role": [
                            self._build_codeable_concept(
                                codings=[
                                    self._build_coding(
                                        system=self.SNOMED_SYSTEM,
                                        code=member.get("CD_FUNCAO", ""),
                                        display=member.get("DS_FUNCAO", ""),
                                    )
                                ],
                            )
                        ],
                        "member": self._build_reference(
                            "Practitioner",
                            member.get("NR_PROFISSIONAL", ""),
                            member.get("NM_PROFISSIONAL"),
                        ),
                    }
                )

        self._track_conversion_success()
        return care_team

    async def adapt_team_availability(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert team availability to FHIR Schedule.

        Args:
            tasy_data: Tasy team availability data

        Returns:
            FHIR Schedule R4 resource
        """
        self._validate_required_fields(tasy_data, ["NR_EQUIPE", "DT_INICIO", "DT_FIM"])

        schedule = {
            "resourceType": "Schedule",
            "meta": {
                "profile": ["http://hl7.org/fhir/StructureDefinition/Schedule"],
                "tag": [{"system": "http://tasy.com/fhir/tenant", "code": self._tenant_id}],
            },
            "identifier": [
                self._build_identifier(
                    system=self.TASY_TEAM_SYSTEM,
                    value=f"{tasy_data['NR_EQUIPE']}-{tasy_data['DT_INICIO']}",
                )
            ],
            "active": True,
            "serviceType": [
                self._build_codeable_concept(
                    codings=[
                        self._build_coding(
                            system=self.SNOMED_SYSTEM,
                            code="387713003",
                            display="Surgical procedure",
                        )
                    ],
                )
            ],
            "actor": [self._build_reference("CareTeam", tasy_data["NR_EQUIPE"])],
            "planningHorizon": {
                "start": tasy_data["DT_INICIO"],
                "end": tasy_data["DT_FIM"],
            },
        }

        self._track_conversion_success()
        return schedule

    async def adapt_preference_card(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert preference card to FHIR SupplyRequest.

        Args:
            tasy_data: Tasy preference card data

        Returns:
            FHIR SupplyRequest R4 resource
        """
        self._validate_required_fields(tasy_data, ["CD_PROCEDIMENTO"])

        supply_request = {
            "resourceType": "SupplyRequest",
            "meta": {
                "profile": ["http://hl7.org/fhir/StructureDefinition/SupplyRequest"],
                "tag": [{"system": "http://tasy.com/fhir/tenant", "code": self._tenant_id}],
            },
            "identifier": [
                self._build_identifier(
                    system=self.TASY_MATERIAL_SYSTEM,
                    value=f"pref-{tasy_data['CD_PROCEDIMENTO']}",
                )
            ],
            "status": "active",
            "category": self._build_codeable_concept(
                codings=[
                    self._build_coding(
                        system="http://terminology.hl7.org/CodeSystem/supply-item-type",
                        code="device",
                    )
                ],
            ),
            "priority": "routine",
        }

        if "items" in tasy_data:
            supply_request["item"] = self._build_codeable_concept(
                codings=[
                    self._build_coding(
                        system=self.TASY_MATERIAL_SYSTEM,
                        code=item.get("CD_MATERIAL", ""),
                        display=item.get("DS_MATERIAL", ""),
                    )
                    for item in tasy_data["items"]
                ],
            )

        self._track_conversion_success()
        return supply_request

    async def adapt_material_request(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert material request to FHIR SupplyDelivery.

        Args:
            tasy_data: Tasy material request data

        Returns:
            FHIR SupplyDelivery R4 resource
        """
        self._validate_required_fields(tasy_data, ["CD_MATERIAL", "QT_MATERIAL"])

        supply_delivery = {
            "resourceType": "SupplyDelivery",
            "meta": {
                "profile": ["http://hl7.org/fhir/StructureDefinition/SupplyDelivery"],
                "tag": [{"system": "http://tasy.com/fhir/tenant", "code": self._tenant_id}],
            },
            "identifier": [
                self._build_identifier(
                    system=self.TASY_MATERIAL_SYSTEM,
                    value=f"req-{tasy_data.get('NR_SOLICITACAO', tasy_data['CD_MATERIAL'])}",
                )
            ],
            "status": "in-progress",
            "suppliedItem": {
                "quantity": {
                    "value": tasy_data["QT_MATERIAL"],
                },
                "itemCodeableConcept": self._build_codeable_concept(
                    codings=[
                        self._build_coding(
                            system=self.TASY_MATERIAL_SYSTEM,
                            code=tasy_data["CD_MATERIAL"],
                            display=tasy_data.get("DS_MATERIAL"),
                        )
                    ],
                ),
            },
        }

        if "NR_PACIENTE" in tasy_data:
            supply_delivery["patient"] = self._build_reference("Patient", tasy_data["NR_PACIENTE"])

        self._track_conversion_success()
        return supply_delivery

    async def adapt_material_availability(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert material availability to FHIR SupplyDelivery.

        Args:
            tasy_data: Tasy material availability data

        Returns:
            FHIR SupplyDelivery R4 resource
        """
        self._validate_required_fields(tasy_data, ["CD_MATERIAL"])

        supply_delivery = {
            "resourceType": "SupplyDelivery",
            "meta": {
                "profile": ["http://hl7.org/fhir/StructureDefinition/SupplyDelivery"],
                "tag": [{"system": "http://tasy.com/fhir/tenant", "code": self._tenant_id}],
            },
            "identifier": [
                self._build_identifier(
                    system=self.TASY_MATERIAL_SYSTEM,
                    value=f"avail-{tasy_data['CD_MATERIAL']}",
                )
            ],
            "status": "completed" if tasy_data.get("IE_DISPONIVEL") else "abandoned",
            "suppliedItem": {
                "quantity": {
                    "value": tasy_data.get("QT_DISPONIVEL", 0),
                },
                "itemCodeableConcept": self._build_codeable_concept(
                    codings=[
                        self._build_coding(
                            system=self.TASY_MATERIAL_SYSTEM,
                            code=tasy_data["CD_MATERIAL"],
                            display=tasy_data.get("DS_MATERIAL"),
                        )
                    ],
                ),
            },
        }

        self._track_conversion_success()
        return supply_delivery

    async def adapt_surgical_kit(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert surgical kit to FHIR Device.

        Args:
            tasy_data: Tasy surgical kit data

        Returns:
            FHIR Device R4 resource
        """
        self._validate_required_fields(tasy_data, ["CD_KIT"])

        device = {
            "resourceType": "Device",
            "meta": {
                "profile": ["http://hl7.org/fhir/StructureDefinition/Device"],
                "tag": [{"system": "http://tasy.com/fhir/tenant", "code": self._tenant_id}],
            },
            "identifier": [
                self._build_identifier(
                    system=self.TASY_MATERIAL_SYSTEM,
                    value=tasy_data["CD_KIT"],
                )
            ],
            "status": "active",
            "deviceName": [
                {
                    "name": tasy_data.get("DS_KIT", tasy_data["CD_KIT"]),
                    "type": "user-friendly-name",
                }
            ],
            "type": self._build_codeable_concept(
                codings=[
                    self._build_coding(
                        system=self.SNOMED_SYSTEM,
                        code="32504003",
                        display="Surgical kit",
                    )
                ],
            ),
        }

        self._track_conversion_success()
        return device

    async def adapt_surgical_record(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert surgical record to FHIR Procedure.

        Args:
            tasy_data: Tasy surgical record data

        Returns:
            FHIR Procedure R4 resource
        """
        return await self._build_surgery_procedure(tasy_data, "completed")

    async def adapt_surgical_notes(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert surgical notes to FHIR DiagnosticReport.

        Args:
            tasy_data: Tasy surgical notes data

        Returns:
            FHIR DiagnosticReport R4 resource
        """
        self._validate_required_fields(tasy_data, ["NR_CIRURGIA", "NR_PACIENTE"])

        diagnostic_report = {
            "resourceType": "DiagnosticReport",
            "meta": {
                "profile": ["http://hl7.org/fhir/StructureDefinition/DiagnosticReport"],
                "tag": [{"system": "http://tasy.com/fhir/tenant", "code": self._tenant_id}],
            },
            "identifier": [
                self._build_identifier(
                    system=self.TASY_SURGERY_SYSTEM,
                    value=f"notes-{tasy_data['NR_CIRURGIA']}",
                )
            ],
            "status": "final",
            "code": self._build_codeable_concept(
                codings=[
                    self._build_coding(
                        system="http://loinc.org",
                        code="11504-8",
                        display="Surgical operation note",
                    )
                ],
            ),
            "subject": self._build_reference("Patient", tasy_data["NR_PACIENTE"]),
        }

        if "DT_CIRURGIA" in tasy_data:
            diagnostic_report["effectiveDateTime"] = tasy_data["DT_CIRURGIA"]

        if "DS_NOTA" in tasy_data:
            diagnostic_report["conclusion"] = tasy_data["DS_NOTA"]

        self._track_conversion_success()
        return diagnostic_report

    async def adapt_complication(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert complication to FHIR AdverseEvent.

        Args:
            tasy_data: Tasy complication data (LGPD-sensitive)

        Returns:
            FHIR AdverseEvent R4 resource
        """
        self._validate_required_fields(tasy_data, ["NR_CIRURGIA", "NR_PACIENTE"])

        adverse_event = {
            "resourceType": "AdverseEvent",
            "meta": {
                "profile": ["http://hl7.org/fhir/StructureDefinition/AdverseEvent"],
                "tag": [{"system": "http://tasy.com/fhir/tenant", "code": self._tenant_id}],
            },
            "identifier": [
                self._build_identifier(
                    system=self.TASY_SURGERY_SYSTEM,
                    value=f"comp-{tasy_data['NR_CIRURGIA']}-{tasy_data.get('NR_COMPLICACAO', '1')}",
                )
            ],
            "actuality": "actual",
            "category": [
                self._build_codeable_concept(
                    codings=[
                        self._build_coding(
                            system="http://terminology.hl7.org/CodeSystem/adverse-event-category",
                            code="procedure",
                        )
                    ],
                )
            ],
            "subject": self._build_reference("Patient", tasy_data["NR_PACIENTE"]),
        }

        if "CD_COMPLICACAO" in tasy_data:
            adverse_event["event"] = self._build_codeable_concept(
                codings=[
                    self._build_coding(
                        system=self.SNOMED_SYSTEM,
                        code=tasy_data["CD_COMPLICACAO"],
                        display=tasy_data.get("DS_COMPLICACAO"),
                    )
                ],
            )

        if "DT_COMPLICACAO" in tasy_data:
            adverse_event["date"] = tasy_data["DT_COMPLICACAO"]

        self._track_conversion_success()
        return adverse_event

    async def adapt_surgical_outcome(self, tasy_data: dict[str, Any]) -> dict[str, Any]:
        """Convert surgical outcome to FHIR Observation.

        Args:
            tasy_data: Tasy surgical outcome data

        Returns:
            FHIR Observation R4 resource
        """
        self._validate_required_fields(tasy_data, ["NR_CIRURGIA", "NR_PACIENTE"])

        observation = {
            "resourceType": "Observation",
            "meta": {
                "profile": ["http://hl7.org/fhir/StructureDefinition/Observation"],
                "tag": [{"system": "http://tasy.com/fhir/tenant", "code": self._tenant_id}],
            },
            "identifier": [
                self._build_identifier(
                    system=self.TASY_SURGERY_SYSTEM,
                    value=f"outcome-{tasy_data['NR_CIRURGIA']}",
                )
            ],
            "status": "final",
            "category": [
                self._build_codeable_concept(
                    codings=[
                        self._build_coding(
                            system="http://terminology.hl7.org/CodeSystem/observation-category",
                            code="procedure",
                        )
                    ],
                )
            ],
            "code": self._build_codeable_concept(
                codings=[
                    self._build_coding(
                        system="http://loinc.org",
                        code="59768-2",
                        display="Procedure outcome",
                    )
                ],
            ),
            "subject": self._build_reference("Patient", tasy_data["NR_PACIENTE"]),
        }

        if "IE_RESULTADO" in tasy_data:
            observation["valueCodeableConcept"] = self._build_codeable_concept(
                codings=[
                    self._build_coding(
                        system=self.SNOMED_SYSTEM,
                        code=tasy_data["IE_RESULTADO"],
                        display=tasy_data.get("DS_RESULTADO"),
                    )
                ],
            )

        if "DT_CIRURGIA" in tasy_data:
            observation["effectiveDateTime"] = tasy_data["DT_CIRURGIA"]

        self._track_conversion_success()
        return observation

    async def _build_surgery_procedure(
        self, tasy_data: dict[str, Any], status: str
    ) -> dict[str, Any]:
        """Build base FHIR Procedure structure for surgery.

        Args:
            tasy_data: Tasy surgery data
            status: FHIR Procedure status

        Returns:
            FHIR Procedure R4 resource
        """
        self._validate_required_fields(tasy_data, ["NR_CIRURGIA", "NR_PACIENTE"])

        procedure = {
            "resourceType": "Procedure",
            "meta": {
                "profile": ["http://hl7.org/fhir/StructureDefinition/Procedure"],
                "tag": [{"system": "http://tasy.com/fhir/tenant", "code": self._tenant_id}],
            },
            "identifier": [
                self._build_identifier(
                    system=self.TASY_SURGERY_SYSTEM,
                    value=tasy_data["NR_CIRURGIA"],
                )
            ],
            "status": status,
            "category": self._build_codeable_concept(
                codings=[
                    self._build_coding(
                        system=self.SNOMED_SYSTEM,
                        code="387713003",
                        display="Surgical procedure",
                    )
                ],
            ),
            "subject": self._build_reference("Patient", tasy_data["NR_PACIENTE"]),
        }

        if "CD_PROCEDIMENTO" in tasy_data:
            procedure["code"] = self._build_codeable_concept(
                codings=[
                    self._build_coding(
                        system=self.TUSS_SYSTEM,
                        code=tasy_data["CD_PROCEDIMENTO"],
                        display=tasy_data.get("DS_PROCEDIMENTO"),
                    )
                ],
                text=tasy_data.get("DS_PROCEDIMENTO"),
            )

        if "NR_ATENDIMENTO" in tasy_data:
            procedure["encounter"] = self._build_reference("Encounter", tasy_data["NR_ATENDIMENTO"])

        if "DT_CIRURGIA" in tasy_data and "HR_INICIO" in tasy_data:
            performed_period = {"start": f"{tasy_data['DT_CIRURGIA']}T{tasy_data['HR_INICIO']}"}
            if "HR_FIM" in tasy_data:
                performed_period["end"] = f"{tasy_data['DT_CIRURGIA']}T{tasy_data['HR_FIM']}"
            procedure["performedPeriod"] = performed_period

        if "NR_MEDICO" in tasy_data:
            procedure["performer"] = [
                {
                    "function": self._build_codeable_concept(
                        codings=[
                            self._build_coding(
                                system=self.SNOMED_SYSTEM,
                                code="304292004",
                                display="Surgeon",
                            )
                        ],
                    ),
                    "actor": self._build_reference("Practitioner", tasy_data["NR_MEDICO"]),
                }
            ]

        if "CD_SALA" in tasy_data:
            procedure["location"] = self._build_reference(
                "Location",
                tasy_data["CD_SALA"],
                tasy_data.get("DS_SALA"),
            )

        return procedure
