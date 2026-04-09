#!/usr/bin/env python3
"""One-command demo data setup for MedHarmony.

Steps:
  1. Check if Synthea bundles exist locally
  2. If not, print download instructions
  3. Upload bundles to HAPI FHIR (with rate-limit handling)
  4. Save resulting patient IDs to data/synthetic_patients/sample_patient_ids.json
  5. Test that each patient can be fetched back from FHIR

Usage:
    python scripts/seed_demo_data.py [--server URL] [--dry-run] [--skip-upload]

The --skip-upload flag re-uses whatever IDs are already in sample_patient_ids.json
and just runs the verification step.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).parent.parent
BUNDLES_DIR = PROJECT_ROOT / "data" / "synthetic_patients" / "bundles"
SAMPLE_IDS_PATH = PROJECT_ROOT / "data" / "synthetic_patients" / "sample_patient_ids.json"
DEFAULT_FHIR_SERVER = "https://hapi.fhir.org/baseR4"

SYNTHEA_INSTRUCTIONS = """
╔══════════════════════════════════════════════════════════════╗
║           Synthea Bundles Not Found — Download First         ║
╚══════════════════════════════════════════════════════════════╝

1. Clone and build Synthea:
   git clone https://github.com/synthetichealth/synthea.git
   cd synthea

2. Generate 20 complex elderly patients (we'll filter for polypharmacy):
   ./run_synthea -p 20 \\
     --exporter.fhir.export=true \\
     --generate.only_alive_patients=true \\
     -a 65-90 -s 42

3. Copy bundles to this project:
   mkdir -p {bundles_dir}
   cp output/fhir/*.json {bundles_dir}/
   # (Exclude hospitalInformation and practitionerInformation bundles)

4. Then re-run this script:
   python scripts/seed_demo_data.py

Or use the built-in offline demo patient (no FHIR server needed):
   python scripts/seed_demo_data.py --skip-upload
""".format(bundles_dir=BUNDLES_DIR)


def _load_existing_ids() -> list[dict]:
    if SAMPLE_IDS_PATH.exists():
        return json.loads(SAMPLE_IDS_PATH.read_text(encoding="utf-8"))
    return []


def _save_ids(records: list[dict]) -> None:
    SAMPLE_IDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SAMPLE_IDS_PATH.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"  ✓ Saved {len(records)} patient record(s) → {SAMPLE_IDS_PATH}")


def _extract_name_from_bundle(bundle: dict) -> str:
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        if resource.get("resourceType") == "Patient":
            name_obj = (resource.get("name") or [{}])[0]
            given = " ".join(name_obj.get("given", []))
            family = name_obj.get("family", "")
            return f"{given} {family}".strip() or "Unknown Patient"
    return "Unknown Patient"


def _count_meds_in_bundle(bundle: dict) -> int:
    return sum(
        1 for e in bundle.get("entry", [])
        if e.get("resource", {}).get("resourceType") in ("MedicationRequest", "MedicationStatement")
    )


def _extract_conditions_from_bundle(bundle: dict) -> list[str]:
    conditions = []
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        if resource.get("resourceType") == "Condition":
            code = resource.get("code", {})
            text = code.get("text") or (code.get("coding") or [{}])[0].get("display", "")
            if text:
                conditions.append(text)
    return conditions[:5]


def _verify_patient_fetchable(patient_id: str, server_url: str, client: httpx.Client) -> bool:
    """Check that a patient can be fetched from the FHIR server."""
    if patient_id == "demo-001":
        return True  # Built-in demo always available
    try:
        resp = client.get(
            f"{server_url}/Patient/{patient_id}",
            headers={"Accept": "application/fhir+json"},
            timeout=30,
        )
        return resp.status_code == 200
    except Exception as exc:
        print(f"    Warning: fetch check failed for {patient_id}: {exc}")
        return False


def upload_bundles(server_url: str, dry_run: bool) -> list[dict]:
    """Upload all bundles and return list of patient records."""
    # Import from the sibling script
    sys.path.insert(0, str(PROJECT_ROOT))
    from scripts.load_synthea_patients import upload_bundle, _extract_patient_info

    bundle_files = sorted(BUNDLES_DIR.glob("*.json"))
    bundle_files = [
        f for f in bundle_files
        if "hospitalInformation" not in f.name and "practitionerInformation" not in f.name
    ]

    if not bundle_files:
        return []

    print(f"\nStep 3/5 — Uploading {len(bundle_files)} bundle(s) to {server_url}...")
    records: list[dict] = []

    with httpx.Client(timeout=120) as client:
        for i, bf in enumerate(bundle_files):
            if i > 0 and not dry_run:
                time.sleep(1.5)  # polite delay for public HAPI

            bundle = json.loads(bf.read_text(encoding="utf-8"))
            name = _extract_name_from_bundle(bundle)
            med_count = _count_meds_in_bundle(bundle)
            conditions = _extract_conditions_from_bundle(bundle)

            if dry_run:
                print(f"  [DRY-RUN] {bf.name}: {name}, {med_count} meds")
                records.append({
                    "patient_id": f"dry-run-{i}",
                    "name": name,
                    "age": 0,
                    "fhir_server": server_url,
                    "conditions": conditions,
                    "medication_count": med_count,
                    "why_interesting": "Dry-run upload",
                })
                continue

            patient_ids = upload_bundle(bf, server_url, client)
            for pid in patient_ids:
                records.append({
                    "patient_id": pid,
                    "name": name,
                    "age": 0,  # Would need DOB parsing for exact age
                    "fhir_server": server_url,
                    "conditions": conditions,
                    "medication_count": med_count,
                    "why_interesting": (
                        f"Synthea patient with {med_count} medications and "
                        f"conditions: {', '.join(conditions[:3])}"
                    ),
                })

    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed MedHarmony demo patient data")
    parser.add_argument("--server", default=DEFAULT_FHIR_SERVER, help="FHIR server URL")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually upload")
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Skip upload, just verify existing IDs in sample_patient_ids.json",
    )
    args = parser.parse_args()

    server_url = args.server.rstrip("/")

    print("=" * 60)
    print("  MedHarmony Demo Data Seeder")
    print("=" * 60)

    # Step 1: Check bundles
    print(f"\nStep 1/5 — Checking for Synthea bundles in {BUNDLES_DIR}...")
    has_bundles = BUNDLES_DIR.exists() and any(BUNDLES_DIR.glob("*.json"))

    if not has_bundles and not args.skip_upload:
        print(SYNTHEA_INSTRUCTIONS)
        print("Tip: Use --skip-upload to verify the built-in demo patient without Synthea.")
        sys.exit(0)
    elif has_bundles:
        bundle_count = len(list(BUNDLES_DIR.glob("*.json")))
        print(f"  ✓ Found {bundle_count} bundle file(s)")
    else:
        print("  ℹ️  No bundles found — will verify existing IDs only")

    # Step 2: Load existing IDs
    print("\nStep 2/5 — Loading existing sample_patient_ids.json...")
    existing_records = _load_existing_ids()
    print(f"  ✓ Found {len(existing_records)} existing record(s)")

    # Step 3: Upload (if we have bundles and aren't skipping)
    new_records: list[dict] = []
    if has_bundles and not args.skip_upload:
        new_records = upload_bundles(server_url, args.dry_run)

    # Step 4: Merge and save
    print("\nStep 4/5 — Saving patient IDs...")
    # Always keep the built-in demo patient
    demo_record = {
        "patient_id": "demo-001",
        "name": "Margaret Thompson",
        "age": 78,
        "fhir_server": "local-demo",
        "conditions": [
            "Atrial Fibrillation", "CKD Stage 3b", "Type 2 Diabetes",
            "Osteoarthritis", "Insomnia", "GERD", "Hypertension",
        ],
        "medication_count": 12,
        "why_interesting": (
            "Built-in offline demo patient — works without FHIR connectivity. "
            "Classic polypharmacy: warfarin+NSAID+CKD, dual Beers Criteria agents, "
            "warfarin→apixaban transition on discharge."
        ),
        "note": "Always available via --demo-mode or when FHIR is unreachable.",
    }

    # Merge: new uploads + existing non-demo IDs + demo record
    merged: dict[str, dict] = {}
    for r in existing_records:
        if r.get("patient_id") != "demo-001":
            merged[r["patient_id"]] = r
    for r in new_records:
        if r.get("patient_id") and not r["patient_id"].startswith("dry-run"):
            merged[r["patient_id"]] = r
    merged["demo-001"] = demo_record

    all_records = list(merged.values())

    if not args.dry_run:
        _save_ids(all_records)
    else:
        print(f"  [DRY-RUN] Would save {len(all_records)} record(s)")

    # Step 5: Verify
    print("\nStep 5/5 — Verifying patients are fetchable...")
    passed = 0
    failed = 0

    with httpx.Client(timeout=30) as client:
        for record in all_records:
            pid = record["patient_id"]
            name = record.get("name", pid)
            fhir = record.get("fhir_server", server_url)

            if fhir == "local-demo":
                print(f"  ✓ {pid} ({name}) — built-in demo [offline]")
                passed += 1
                continue

            ok = _verify_patient_fetchable(pid, fhir, client)
            if ok:
                print(f"  ✓ {pid} ({name}) — reachable on {fhir}")
                passed += 1
            else:
                print(f"  ✗ {pid} ({name}) — NOT found on {fhir}")
                failed += 1

    print("\n" + "=" * 60)
    print(f"  Results: {passed} passed, {failed} failed")
    if failed == 0:
        print("  ✅ All demo patients are ready!")
    else:
        print("  ⚠️  Some patients could not be verified (HAPI data may have been wiped).")
        print("     Run with fresh Synthea bundles to reload them.")

    print(f"\n  Run the demo:")
    print(f"  python -m src.agent.server &")
    print(f"  curl -X POST http://localhost:8000/api/analyze \\")
    print(f"    -H 'Content-Type: application/json' \\")
    print(f"    -d '{{\"patient_id\": \"demo-001\"}}'")
    print("=" * 60)


if __name__ == "__main__":
    main()
