"""FHIR Client for pulling patient data from FHIR R4 servers."""

from __future__ import annotations

from typing import Optional

import httpx
from loguru import logger

from src.agent.config import FHIR_SERVER_URL
from src.models.medication import (
    Allergy,
    Condition,
    LabResult,
    Medication,
    MedicationList,
    PatientContext,
)


class FHIRClient:
    """Client for querying FHIR R4 servers."""

    def __init__(
        self,
        base_url: str = FHIR_SERVER_URL,
        auth_token: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json",
        }
        if auth_token:
            self.headers["Authorization"] = f"Bearer {auth_token}"

    async def _get(self, path: str, params: Optional[dict] = None) -> dict:
        """Make a GET request to the FHIR server."""
        url = f"{self.base_url}/{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()

    async def get_patient(self, patient_id: str) -> dict:
        """Get patient demographics."""
        return await self._get(f"Patient/{patient_id}")

    async def get_patient_context(self, patient_id: str) -> PatientContext:
        """Pull complete patient context from FHIR."""
        logger.info(f"Pulling FHIR context for patient: {patient_id}")

        # Get patient demographics
        patient_data = await self.get_patient(patient_id)
        name = self._extract_name(patient_data)
        age = self._calculate_age(patient_data)
        sex = patient_data.get("gender", "unknown")

        # Get allergies
        allergies = await self._get_allergies(patient_id)

        # Get conditions
        conditions = await self._get_conditions(patient_id)

        # Get lab results
        labs = await self._get_lab_results(patient_id)

        # Get medication lists
        med_lists = await self._get_medication_lists(patient_id)

        # Try to get weight
        weight = await self._get_weight(patient_id)

        context = PatientContext(
            patient_id=patient_id,
            name=name,
            age=age,
            sex=sex,
            weight_kg=weight,
            allergies=allergies,
            conditions=conditions,
            lab_results=labs,
            medication_lists=med_lists,
            fhir_server_url=self.base_url,
        )

        logger.info(
            f"Patient context loaded: {len(conditions)} conditions, "
            f"{len(allergies)} allergies, {len(labs)} labs, "
            f"{sum(len(ml.medications) for ml in med_lists)} total medications"
        )
        return context

    async def _get_allergies(self, patient_id: str) -> list[Allergy]:
        """Get patient allergy records."""
        try:
            bundle = await self._get(
                "AllergyIntolerance",
                {"patient": patient_id, "_count": "100"},
            )
            allergies = []
            for entry in bundle.get("entry", []):
                resource = entry.get("resource", {})
                substance = "Unknown"

                # Extract substance name from code
                code = resource.get("code", {})
                codings = code.get("coding", [])
                if codings:
                    substance = codings[0].get("display", code.get("text", "Unknown"))
                elif code.get("text"):
                    substance = code["text"]

                # Extract reaction
                reaction = None
                reactions = resource.get("reaction", [])
                if reactions:
                    manifestations = reactions[0].get("manifestation", [])
                    if manifestations:
                        coding = manifestations[0].get("coding", [])
                        if coding:
                            reaction = coding[0].get("display", "")

                allergies.append(Allergy(
                    substance=substance,
                    reaction=reaction,
                    severity=resource.get("criticality", None),
                    fhir_resource_id=resource.get("id"),
                ))
            return allergies
        except Exception as e:
            logger.warning(f"Failed to fetch allergies: {e}")
            return []

    async def _get_conditions(self, patient_id: str) -> list[Condition]:
        """Get patient conditions/diagnoses."""
        try:
            bundle = await self._get(
                "Condition",
                {"patient": patient_id, "clinical-status": "active", "_count": "100"},
            )
            conditions = []
            for entry in bundle.get("entry", []):
                resource = entry.get("resource", {})
                code = resource.get("code", {})
                codings = code.get("coding", [])

                name = code.get("text", "Unknown")
                icd_code = None
                if codings:
                    name = codings[0].get("display", name)
                    icd_code = codings[0].get("code")

                conditions.append(Condition(
                    name=name,
                    icd10_code=icd_code,
                    status="active",
                    onset_date=resource.get("onsetDateTime"),
                    fhir_resource_id=resource.get("id"),
                ))
            return conditions
        except Exception as e:
            logger.warning(f"Failed to fetch conditions: {e}")
            return []

    async def _get_lab_results(self, patient_id: str) -> list[LabResult]:
        """Get recent lab results (last 90 days of key labs)."""
        key_loinc_codes = [
            "2160-0",   # Creatinine
            "33914-3",  # eGFR
            "1742-6",   # ALT
            "1920-8",   # AST
            "6768-6",   # ALP
            "4548-4",   # HbA1c
            "2345-7",   # Glucose
            "2823-3",   # Potassium
            "2951-2",   # Sodium
            "718-7",    # Hemoglobin
            "777-3",    # Platelets
            "6690-2",   # WBC
            "2571-8",   # Triglycerides
            "2093-3",   # Total Cholesterol
            "49765-1",  # INR
        ]

        labs = []
        try:
            for code in key_loinc_codes:
                try:
                    bundle = await self._get(
                        "Observation",
                        {
                            "patient": patient_id,
                            "code": f"http://loinc.org|{code}",
                            "_sort": "-date",
                            "_count": "1",
                        },
                    )
                    for entry in bundle.get("entry", []):
                        resource = entry.get("resource", {})
                        value_quantity = resource.get("valueQuantity", {})
                        if value_quantity.get("value") is not None:
                            code_info = resource.get("code", {})
                            codings = code_info.get("coding", [])
                            name = codings[0].get("display", "") if codings else code

                            ref_range = ""
                            ref_ranges = resource.get("referenceRange", [])
                            if ref_ranges:
                                low = ref_ranges[0].get("low", {}).get("value", "")
                                high = ref_ranges[0].get("high", {}).get("value", "")
                                if low and high:
                                    ref_range = f"{low}-{high}"

                            interpretation = resource.get("interpretation", [])
                            is_abnormal = bool(interpretation)

                            labs.append(LabResult(
                                name=name,
                                loinc_code=code,
                                value=float(value_quantity["value"]),
                                unit=value_quantity.get("unit", ""),
                                reference_range=ref_range,
                                date=resource.get("effectiveDateTime"),
                                is_abnormal=is_abnormal,
                                fhir_resource_id=resource.get("id"),
                            ))
                except Exception:
                    continue  # Skip individual lab failures
        except Exception as e:
            logger.warning(f"Failed to fetch labs: {e}")

        return labs

    async def _get_medication_lists(self, patient_id: str) -> list[MedicationList]:
        """Get medication lists from MedicationRequest and MedicationStatement."""
        all_meds = []

        # MedicationRequest (prescriptions)
        try:
            bundle = await self._get(
                "MedicationRequest",
                {"patient": patient_id, "status": "active", "_count": "100"},
            )
            meds = []
            for entry in bundle.get("entry", []):
                resource = entry.get("resource", {})
                med = self._extract_medication_from_request(resource)
                if med:
                    meds.append(med)

            if meds:
                all_meds.append(MedicationList(
                    source="active_prescriptions",
                    medications=meds,
                ))
        except Exception as e:
            logger.warning(f"Failed to fetch MedicationRequests: {e}")

        # MedicationStatement (patient-reported)
        try:
            bundle = await self._get(
                "MedicationStatement",
                {"patient": patient_id, "status": "active", "_count": "100"},
            )
            meds = []
            for entry in bundle.get("entry", []):
                resource = entry.get("resource", {})
                med = self._extract_medication_from_statement(resource)
                if med:
                    meds.append(med)

            if meds:
                all_meds.append(MedicationList(
                    source="patient_reported",
                    medications=meds,
                ))
        except Exception as e:
            logger.warning(f"Failed to fetch MedicationStatements: {e}")

        return all_meds

    async def _get_weight(self, patient_id: str) -> Optional[float]:
        """Get most recent weight."""
        try:
            bundle = await self._get(
                "Observation",
                {
                    "patient": patient_id,
                    "code": "http://loinc.org|29463-7",
                    "_sort": "-date",
                    "_count": "1",
                },
            )
            entries = bundle.get("entry", [])
            if entries:
                value = entries[0]["resource"].get("valueQuantity", {})
                if value.get("value"):
                    weight = float(value["value"])
                    if value.get("unit") == "lb" or value.get("unit") == "[lb_av]":
                        weight = weight * 0.453592
                    return round(weight, 1)
        except Exception:
            pass
        return None

    def _extract_name(self, patient: dict) -> str:
        """Extract patient name from FHIR Patient resource."""
        names = patient.get("name", [])
        if names:
            name = names[0]
            given = " ".join(name.get("given", []))
            family = name.get("family", "")
            return f"{given} {family}".strip()
        return "Unknown"

    def _calculate_age(self, patient: dict) -> Optional[int]:
        """Calculate age from birthDate."""
        birth_date = patient.get("birthDate")
        if birth_date:
            from datetime import date
            birth = date.fromisoformat(birth_date)
            today = date.today()
            return today.year - birth.year - (
                (today.month, today.day) < (birth.month, birth.day)
            )
        return None

    def _extract_medication_from_request(self, resource: dict) -> Optional[Medication]:
        """Extract Medication from a MedicationRequest resource."""
        med_codeable = resource.get("medicationCodeableConcept", {})
        codings = med_codeable.get("coding", [])

        name = med_codeable.get("text", "Unknown")
        rxnorm = None
        if codings:
            name = codings[0].get("display", name)
            rxnorm = codings[0].get("code")

        # Extract dosage
        dose = None
        frequency = None
        route = None
        dosage_instructions = resource.get("dosageInstruction", [])
        if dosage_instructions:
            di = dosage_instructions[0]
            dose_quantity = di.get("doseAndRate", [{}])[0].get("doseQuantity", {}) if di.get("doseAndRate") else {}
            if dose_quantity:
                dose = f"{dose_quantity.get('value', '')} {dose_quantity.get('unit', '')}".strip()

            timing = di.get("timing", {}).get("code", {})
            if timing:
                frequency = timing.get("text") or (
                    timing.get("coding", [{}])[0].get("display") if timing.get("coding") else None
                )

            route_code = di.get("route", {})
            if route_code:
                route = route_code.get("text") or (
                    route_code.get("coding", [{}])[0].get("display") if route_code.get("coding") else None
                )

        return Medication(
            id=resource.get("id", ""),
            name=name,
            rxnorm_code=rxnorm,
            dose=dose,
            frequency=frequency,
            route=route,
            status=resource.get("status", "active"),
            start_date=resource.get("authoredOn"),
            source="active_prescriptions",
            fhir_resource_id=resource.get("id"),
        )

    def _extract_medication_from_statement(self, resource: dict) -> Optional[Medication]:
        """Extract Medication from a MedicationStatement resource."""
        med_codeable = resource.get("medicationCodeableConcept", {})
        codings = med_codeable.get("coding", [])

        name = med_codeable.get("text", "Unknown")
        rxnorm = None
        if codings:
            name = codings[0].get("display", name)
            rxnorm = codings[0].get("code")

        return Medication(
            id=resource.get("id", ""),
            name=name,
            rxnorm_code=rxnorm,
            status=resource.get("status", "active"),
            source="patient_reported",
            fhir_resource_id=resource.get("id"),
        )
