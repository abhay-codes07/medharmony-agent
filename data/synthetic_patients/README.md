# Synthetic Patient Data — MedHarmony

This directory holds Synthea-generated FHIR patient bundles for demo and integration testing.

---

## Quick Start: Known Demo Patients

`sample_patient_ids.json` contains pre-selected patient IDs on the public HAPI FHIR test server
plus the built-in offline demo patient. Run MedHarmony against them immediately:

```bash
# Use the built-in offline demo patient (no FHIR server needed)
python -m src.agent.server   # start the server
curl -X POST http://localhost:8000/api/analyze \
     -H "Content-Type: application/json" \
     -d '{"patient_id": "demo-001"}'

# Use a live patient from the public HAPI FHIR test server
curl -X POST http://localhost:8000/api/analyze \
     -H "Content-Type: application/json" \
     -d '{"patient_id": "592750", "fhir_server_url": "https://hapi.fhir.org/baseR4"}'
```

> ⚠️ Public HAPI FHIR data changes — IDs in `sample_patient_ids.json` may need refreshing.
> Run `python scripts/seed_demo_data.py` to load fresh Synthea patients and update the IDs.

---

## Generating Fresh Synthea Patients

### Step 1 — Download Synthea

```bash
git clone https://github.com/synthetichealth/synthea.git
cd synthea
```

### Step 2 — Generate Complex Elderly Patients with Polypharmacy

```bash
./run_synthea -p 5 \
  --exporter.fhir.export=true \
  --generate.only_alive_patients=true \
  -a 65-90 \
  -c src/main/resources/synthea.properties
```

This generates 5 alive patients aged 65–90. FHIR R4 bundles land in `output/fhir/`.

**Recommended Synthea flags for complex patients:**

| Flag | Purpose |
|------|---------|
| `-p 20` | Generate 20 patients (filter down to 5 with polypharmacy) |
| `-a 65-90` | Age range (geriatric polypharmacy focus) |
| `--exporter.fhir.export=true` | Enable FHIR R4 JSON export |
| `--generate.only_alive_patients=true` | Skip deceased patients |
| `-s 42` | Fixed seed for reproducible generation |

### Step 3 — Filter for Polypharmacy Patients

```bash
# Count medications per patient in the FHIR bundles
python3 - <<'EOF'
import json, pathlib

bundles_dir = pathlib.Path("synthea/output/fhir")
for f in bundles_dir.glob("*.json"):
    bundle = json.loads(f.read_text())
    entries = bundle.get("entry", [])
    med_requests = [e for e in entries if e.get("resource", {}).get("resourceType") == "MedicationRequest"]
    patients = [e["resource"] for e in entries if e.get("resource", {}).get("resourceType") == "Patient"]
    if med_requests and patients:
        pt = patients[0]
        name = pt["name"][0]["text"] if pt.get("name") else "Unknown"
        print(f"{len(med_requests):3d} meds — {name} — {f.name}")
EOF
```

Select bundles with **5+ active medications** and copy them to `data/synthetic_patients/bundles/`.

### Step 4 — Upload to HAPI FHIR

```bash
# Upload all bundles in the directory
python scripts/load_synthea_patients.py \
  --dir data/synthetic_patients/bundles \
  --server https://hapi.fhir.org/baseR4

# One-command setup (upload + save IDs + verify)
python scripts/seed_demo_data.py
```

---

## Directory Structure

```
data/synthetic_patients/
├── README.md                     ← This file
├── sample_patient_ids.json       ← Known-good patient IDs for demos
└── bundles/                      ← Local Synthea FHIR bundles (gitignored)
    ├── Alejandra_Ruiz_*.json
    ├── Bernard_Collins_*.json
    └── ...
```

> `bundles/` is in `.gitignore` — do not commit synthetic patient data to source control.

---

## Public HAPI FHIR Server Notes

- **URL:** https://hapi.fhir.org/baseR4
- **Rate limits:** ~10 req/s; `load_synthea_patients.py` handles retry with backoff
- **Data persistence:** Public test data is periodically wiped — always have the Synthea bundles locally
- **No auth required:** Public read/write access for testing

---

## Interesting Patient Scenarios for Demos

| Scenario | What to Look For |
|----------|-----------------|
| Warfarin + NSAID + CKD | Critical bleed risk, renal contraindication |
| Benzodiazepine in elderly | Beers Criteria — fall risk, CNS depression |
| Duplicate anticoagulation | Warfarin → DOAC transition without washout |
| Anticholinergic burden | Multiple anticholinergic drugs in 75+ yo |
| Metformin + eGFR <30 | Renal dose adjustment / discontinuation |
| NSAID + ACE inhibitor + diuretic | "Triple whammy" acute kidney injury risk |
