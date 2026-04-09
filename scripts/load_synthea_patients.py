#!/usr/bin/env python3
"""Load Synthea-generated FHIR bundles into a target FHIR server.

Each Synthea JSON file is a FHIR Bundle (type=transaction or collection).
We POST the whole bundle to the server's root endpoint, which processes all
resources in one transaction and returns a Bundle response with resource IDs.

Usage:
    python scripts/load_synthea_patients.py [--dir PATH] [--server URL] [--dry-run]

Examples:
    python scripts/load_synthea_patients.py
    python scripts/load_synthea_patients.py --dir /tmp/synthea/output/fhir
    python scripts/load_synthea_patients.py --server https://hapi.fhir.org/baseR4
    python scripts/load_synthea_patients.py --dry-run

Outputs one line per patient:  PATIENT_ID  |  Name  |  File
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

# Defaults
DEFAULT_BUNDLES_DIR = Path(__file__).parent.parent / "data" / "synthetic_patients" / "bundles"
DEFAULT_FHIR_SERVER = "https://hapi.fhir.org/baseR4"

# Retry settings for HAPI's rate limiting
MAX_RETRIES = 4
INITIAL_BACKOFF_S = 2.0
MAX_BACKOFF_S = 60.0


def _backoff(attempt: int) -> float:
    """Exponential backoff with jitter (capped at MAX_BACKOFF_S)."""
    import random

    delay = min(INITIAL_BACKOFF_S * (2**attempt), MAX_BACKOFF_S)
    return delay + random.uniform(0, delay * 0.2)


def _extract_patient_info(bundle: dict) -> tuple[str | None, str | None]:
    """Return (name, dob) from the first Patient resource in a bundle."""
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        if resource.get("resourceType") == "Patient":
            name_obj = (resource.get("name") or [{}])[0]
            given = " ".join(name_obj.get("given", []))
            family = name_obj.get("family", "")
            name = f"{given} {family}".strip() or "Unknown"
            dob = resource.get("birthDate", "?")
            return name, dob
    return None, None


def _ensure_transaction_bundle(bundle: dict) -> dict:
    """Convert Synthea 'collection' bundles to 'transaction' type if needed."""
    if bundle.get("type") == "collection":
        bundle = bundle.copy()
        bundle["type"] = "transaction"
        entries = []
        for entry in bundle.get("entry", []):
            entry = entry.copy()
            resource = entry.get("resource", {})
            rt = resource.get("resourceType", "Unknown")
            rid = resource.get("id", "")
            entry.setdefault(
                "request",
                {
                    "method": "PUT" if rid else "POST",
                    "url": f"{rt}/{rid}" if rid else rt,
                },
            )
            entries.append(entry)
        bundle["entry"] = entries
    return bundle


def upload_bundle(
    bundle_path: Path,
    server_url: str,
    client: httpx.Client,
    dry_run: bool = False,
) -> list[str]:
    """Upload one Synthea bundle file and return extracted Patient IDs.

    Retries on HTTP 429 (rate limit) or 5xx errors with exponential backoff.

    Returns:
        List of Patient resource IDs created/updated on the server.
    """
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    name, dob = _extract_patient_info(bundle)
    bundle = _ensure_transaction_bundle(bundle)

    if dry_run:
        resource_count = len(bundle.get("entry", []))
        print(f"  [DRY-RUN] Would upload {bundle_path.name}: {name} (born {dob}), "
              f"{resource_count} resources")
        return []

    print(f"  Uploading {bundle_path.name}: {name} (born {dob})...", end=" ", flush=True)

    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.post(
                server_url,
                json=bundle,
                headers={"Content-Type": "application/fhir+json"},
                timeout=120,
            )

            if resp.status_code == 429:
                wait = _backoff(attempt)
                print(f"\n    Rate limited — waiting {wait:.1f}s (attempt {attempt + 1})...",
                      end=" ", flush=True)
                time.sleep(wait)
                continue

            if resp.status_code >= 500:
                wait = _backoff(attempt)
                print(f"\n    Server error {resp.status_code} — retrying in {wait:.1f}s...",
                      end=" ", flush=True)
                time.sleep(wait)
                continue

            resp.raise_for_status()
            response_bundle = resp.json()

            # Extract Patient IDs from the response
            patient_ids: list[str] = []
            for entry in response_bundle.get("entry", []):
                location = entry.get("response", {}).get("location", "")
                if "/Patient/" in location:
                    pid = location.split("/Patient/")[1].split("/")[0]
                    patient_ids.append(pid)

            print(f"✓  Patient IDs: {patient_ids or '(none in response)'}")
            return patient_ids

        except httpx.TimeoutException as exc:
            last_exc = exc
            wait = _backoff(attempt)
            print(f"\n    Timeout — retrying in {wait:.1f}s...", end=" ", flush=True)
            time.sleep(wait)

        except httpx.HTTPStatusError as exc:
            print(f"✗  HTTP {exc.response.status_code}: {exc.response.text[:200]}")
            return []

        except Exception as exc:
            last_exc = exc
            wait = _backoff(attempt)
            print(f"\n    Error: {exc} — retrying in {wait:.1f}s...", end=" ", flush=True)
            time.sleep(wait)

    print(f"✗  Failed after {MAX_RETRIES} attempts: {last_exc}")
    return []


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load Synthea FHIR bundles into a FHIR server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_BUNDLES_DIR,
        help=f"Directory containing Synthea JSON bundle files (default: {DEFAULT_BUNDLES_DIR})",
    )
    parser.add_argument(
        "--server",
        default=DEFAULT_FHIR_SERVER,
        help=f"FHIR server base URL (default: {DEFAULT_FHIR_SERVER})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be uploaded without actually sending anything",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds to wait between uploads (default: 1.0 — be polite to public HAPI)",
    )
    args = parser.parse_args()

    bundles_dir: Path = args.dir
    server_url: str = args.server.rstrip("/")

    if not bundles_dir.exists():
        print(f"ERROR: Bundle directory not found: {bundles_dir}")
        print(
            "\nDownload Synthea and generate bundles first:\n"
            "  git clone https://github.com/synthetichealth/synthea.git\n"
            "  cd synthea && ./run_synthea -p 5 --exporter.fhir.export=true "
            "--generate.only_alive_patients=true\n"
            f"  cp synthea/output/fhir/*.json {bundles_dir}/\n"
        )
        sys.exit(1)

    bundle_files = sorted(bundles_dir.glob("*.json"))
    # Skip the hospitalInformation and practitionerInformation bundles (no Patient)
    bundle_files = [
        f for f in bundle_files
        if "hospitalInformation" not in f.name and "practitionerInformation" not in f.name
    ]

    if not bundle_files:
        print(f"No patient bundle JSON files found in {bundles_dir}")
        sys.exit(1)

    print(f"Loading {len(bundle_files)} Synthea bundle(s) → {server_url}")
    print("=" * 60)

    all_patient_ids: list[str] = []

    with httpx.Client(timeout=120) as client:
        for i, bundle_path in enumerate(bundle_files):
            if i > 0 and not args.dry_run:
                time.sleep(args.delay)

            ids = upload_bundle(bundle_path, server_url, client, dry_run=args.dry_run)
            all_patient_ids.extend(ids)

    print("=" * 60)
    if all_patient_ids:
        print(f"\n✅ Successfully uploaded. Patient IDs on {server_url}:")
        for pid in all_patient_ids:
            print(f"   {pid}")
    elif args.dry_run:
        print("\nDry run complete — no data was sent.")
    else:
        print("\n⚠️  No Patient IDs were returned. Check server logs.")


if __name__ == "__main__":
    main()
