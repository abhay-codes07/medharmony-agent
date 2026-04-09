# MedHarmony — Sample Clinician Safety Brief

> **Note:** This is a static example generated from the built-in demo patient
> (Margaret Thompson, 78F, CKD Stage 3b, polypharmacy). Run the agent yourself
> against `demo-001` to regenerate with live Gemini analysis.

---

# MedHarmony Clinician Safety Brief

**Patient:** Margaret Thompson | **Age:** 78 | **Sex:** Female | **Weight:** 62.0 kg | **eGFR:** 32.0 mL/min/1.73m² | **INR:** 2.8
**Key Allergies:** Penicillin, Sulfonamides
**Generated:** 2026-04-10 14:32 UTC

---

## 🚨 Critical Alerts

> ⚠️ **Immediate clinician review required for the following items before discharge.**

- **Ibuprofen + Warfarin** (Drug Drug): NSAIDs significantly increase bleeding risk when combined with anticoagulants, with additive effects on GI mucosa and platelet inhibition.
  - *Action required:* Discontinue ibuprofen immediately and substitute with acetaminophen 650 mg PRN for pain management. If NSAID is absolutely required, consider misoprostol prophylaxis and close INR monitoring — for clinician review.
  - *Evidence:* FDA Drug Safety Communication; BMJ 2011; Beers Criteria 2023

- **Warfarin + Apixaban (duplicate anticoagulation on discharge)** (Duplicate Therapy): Patient is being discharged on BOTH warfarin (home med) AND apixaban (new discharge med) without documented washout plan — extremely high bleeding risk.
  - *Action required:* CRITICAL — Confirm intended anticoagulation strategy. If transitioning to apixaban for Afib, warfarin must be discontinued first. Clarify with cardiology before discharge — for clinician review.
  - *Evidence:* ACC/AHA Afib Guidelines 2023; CHEST 2021 Antithrombotic Therapy

- **Ibuprofen in CKD Stage 3b** (Drug Condition): NSAIDs are contraindicated in CKD Stage ≥3 (eGFR <45). Patient's eGFR is 32 — NSAID use risks acute kidney injury on top of existing CKD.
  - *Action required:* Discontinue ibuprofen. Safe alternatives: acetaminophen (with dose adjustment), topical NSAIDs for local pain — for clinician review.
  - *Evidence:* KDIGO 2023 CKD Guidelines; Beers Criteria 2023

---

## 📋 Medication Reconciliation Summary

| Medication | Admission Dose | Discharge Dose | Action | Reason |
|------------|---------------|----------------|--------|--------|
| **Metformin** | 1000 mg twice daily | 500 mg twice daily | ✏️ MODIFY-DOSE | Dose reduced from 1000→500 mg BID due to CKD Stage 3b (eGFR 32) — metformin accumulation risk at eGFR <45 |
| **Warfarin** | 5 mg daily | 5 mg daily | ✅ CONTINUE | INR 2.8 (therapeutic); monitor closely given apixaban on discharge list |
| **Lisinopril** | 20 mg daily | 10 mg daily | ✏️ MODIFY-DOSE | Dose halved — renal protective at lower dose in CKD; K+ elevated at 5.3, monitor for hyperkalemia |
| **Amlodipine** | 10 mg daily | 10 mg daily | ✅ CONTINUE | Continued for HTN management |
| **Metoprolol Tartrate → Succinate ER** | 50 mg BID | 100 mg daily | 🔄 SUBSTITUTE | Formulary switch to extended-release — equivalent cardioprotection, better adherence |
| **Omeprazole → Pantoprazole** | 20 mg daily | 40 mg daily | 🔄 SUBSTITUTE | Dose increased; formulary switch; consider deprescribing if on PPI >8 weeks without indication |
| **Ibuprofen** | 400 mg TID | REMOVED | 🛑 DISCONTINUE | CONTRAINDICATED: CKD Stage 3b + anticoagulation. Replaced with acetaminophen |
| **Acetaminophen** | (new) | 650 mg PRN | ➕ ADD | Safer NSAID alternative for pain; dose-appropriate at 2600 mg/day max given hepatic function |
| **Diazepam** | 5 mg QHS | REMOVED | 🛑 DISCONTINUE | Beers Criteria 2023 — benzodiazepines in elderly (≥65): falls, cognitive impairment, respiratory depression |
| **Diphenhydramine** | 25 mg QHS | REMOVED | 🛑 DISCONTINUE | Beers Criteria 2023 — highly anticholinergic in elderly: confusion, urinary retention, falls |
| **Furosemide** | 40 mg daily | 40 mg daily | ✅ CONTINUE | Heart failure / fluid management; K+ is borderline high — reduce KCl supplementation |
| **Potassium Chloride** | 20 mEq daily | 40 mEq daily | 🔍 REVIEW | Dose DOUBLED on discharge but K+ already elevated at 5.3 mEq/L — review urgently |
| **Atorvastatin** | 40 mg QHS | 40 mg QHS | ✅ CONTINUE | Appropriate statin dose for cardiovascular prevention |
| **Apixaban** | (new) | 5 mg BID | 🔍 REVIEW | New DOAC on discharge — DUPLICATE with warfarin (both active). Confirm anticoagulation plan. |

---

## 💊 Drug Interaction Findings

### 🔴 Critical & High Priority — Requires Action

**🔴 CRITICAL** — Drug Drug
**Drugs/Factors:** Ibuprofen + Warfarin
- *What:* NSAIDs inhibit platelet aggregation and damage GI mucosa, while warfarin impairs coagulation — combined bleeding risk is multiplicative, not additive.
- *Why it matters for this patient:* Hemoglobin already 10.8 (anemia), Platelets 145 (low-normal). Any GI bleed in an anticoagulated, anemic patient with CKD is life-threatening.
- *Recommended action:* Discontinue ibuprofen immediately. Substitute acetaminophen 650 mg PRN. If NSAID required, consider PPI prophylaxis and daily INR monitoring — for clinician review.
- *Evidence:* FDA Drug Safety Communication 2015; Beers Criteria 2023; BMJ 2011 (increased GI bleed risk 13-fold)

**🔴 CRITICAL** — Duplicate Therapy
**Drugs/Factors:** Warfarin + Apixaban
- *What:* Two anticoagulants active simultaneously. Warfarin on admission list, apixaban on discharge list — no documented transition plan.
- *Why it matters for this patient:* INR 2.8 (already therapeutic on warfarin). Adding apixaban creates dangerously supratherapeutic anticoagulation. Hemoglobin 10.8 (bleeding risk), Platelets 145.
- *Recommended action:* CRITICAL — resolve before discharge. If switching to apixaban: stop warfarin, bridge per protocol (apixaban can start when INR <2). Document decision — for clinician review.
- *Evidence:* ACC/AHA Afib Guidelines 2023; CHEST Antithrombotic 2021

**🔴 CRITICAL** — Drug Condition
**Drugs/Factors:** Ibuprofen / Condition: CKD Stage 3b
- *What:* NSAIDs reduce renal prostaglandin synthesis, causing afferent arteriole vasoconstriction — precipitates acute kidney injury in already-compromised kidneys.
- *Why it matters for this patient:* eGFR 32, Creatinine 1.8 — already at Stage 3b CKD. NSAID use risks pushing to Stage 4 or requiring dialysis.
- *Recommended action:* Discontinue ibuprofen. Switch to acetaminophen (max 2g/day in elderly with caution). Monitor creatinine 48h post-discharge — for clinician review.
- *Evidence:* KDIGO 2023; Beers Criteria 2023 (avoid NSAIDs in eGFR <30; extreme caution 30-60)

**🟠 HIGH** — Drug Lab
**Drugs/Factors:** Potassium Chloride / Lab: Potassium 5.3 mEq/L
- *What:* Potassium supplement dose doubled on discharge (20→40 mEq/day) while serum K+ is already elevated above normal range.
- *Why it matters for this patient:* Lisinopril (ACE inhibitor) also retains K+. CKD reduces renal K+ excretion. Risk of hyperkalemia → cardiac arrhythmia.
- *Recommended action:* Reduce or hold KCl supplementation. Recheck K+ in 48-72h. Consider dietary K+ counseling — for clinician review.
- *Evidence:* Clinical judgment; ACC/AHA CHF Guidelines; KDIGO CKD

**🟠 HIGH** — Drug Condition
**Drugs/Factors:** Metformin / Condition: CKD Stage 3b
- *What:* Metformin is associated with lactic acidosis at eGFR <30. eGFR 32 is borderline — dose reduction required and close monitoring mandatory.
- *Why it matters for this patient:* eGFR 32 and trending (admission Cr 1.8). If renal function deteriorates further, metformin must be discontinued.
- *Recommended action:* Dose already reduced to 500 mg BID (appropriate). Hold if eGFR drops below 30. Educate patient to hold during illness/dehydration — for clinician review.
- *Evidence:* FDA Metformin Label Update 2016; ADA Standards of Care 2024

### 🟡 Moderate Priority — Monitor Closely

- **Furosemide + Lisinopril**: Loop diuretic + ACE inhibitor — risk of first-dose hypotension and acute kidney injury ("triple whammy" with KCl). Monitor BP and renal function post-discharge. *(Clinical judgment; JNC 8)*
- **Atorvastatin + Metoprolol**: Minimal interaction; monitor for myopathy symptoms (rare). *(Clinical judgment)*
- **Warfarin + Furosemide**: Furosemide may displace warfarin from protein binding → transient INR spike. Recheck INR 5-7 days post-discharge. *(Micromedex; Beers Criteria)*

---

## 📉 Deprescribing Opportunities

### 🔴 Diazepam — Beers Criteria 2023 / STOPP v3

- **Reason:** Benzodiazepines are explicitly listed as inappropriate in patients ≥65 years. Risk of cognitive impairment, delirium, falls (fracture risk), and excessive sedation — especially concerning in an 82-year-old woman with Afib and CKD.
- **Recommendation:** Taper and discontinue. Address underlying insomnia/anxiety with non-pharmacological interventions first — for clinician review.
- **Tapering plan:** Week 1-2: 5 mg QHS → 2.5 mg QHS; Week 3-4: 2.5 mg QOD; Week 5: discontinue. Monitor for withdrawal symptoms.
- **Alternatives to consider:** CBT-I (first-line for insomnia), melatonin 1-3 mg QHS, Trazodone 25-50 mg QHS (if antidepressant needed)

### 🔴 Diphenhydramine — Beers Criteria 2023 (Anticholinergic)

- **Reason:** Highly anticholinergic antihistamine in elderly. Risks: acute confusion, urinary retention, constipation, sedation, falls. Anticholinergic Cognitive Burden Scale score = 3 (highest risk).
- **Recommendation:** Discontinue. Already removed from discharge list — reinforce with patient — for clinician review.
- **Alternatives to consider:** Melatonin for sleep, fexofenadine (low anticholinergic) for allergy symptoms if needed

### 🟠 Omeprazole / Pantoprazole — STOPP v3 (PPI duration)

- **Reason:** PPIs prescribed without clear documented indication or for >8 weeks. Long-term PPI use associated with C. difficile risk, Mg²⁺ deficiency, bone fractures, and B12 deficiency — all particularly relevant in elderly with CKD.
- **Recommendation:** Review indication. If for NSAID gastroprotection — NSAID is being discontinued, so deprescribe PPI. If for GERD, trial dose reduction or H2-blocker switch — for clinician review.
- **Tapering plan:** If discontinuing: taper over 4 weeks (every other day → then stop) to prevent rebound acid hypersecretion.
- **Alternatives to consider:** H2-blocker (ranitidine-free: famotidine), lifestyle modification, PRN antacid

---

## ✅ Recommended Actions for Clinician

1. [CRITICAL] Review warfarin + apixaban: Confirm intended anticoagulation strategy for Afib. Discontinue warfarin if transitioning to apixaban. Document decision before discharge.
2. [CRITICAL] Discontinue ibuprofen — CONTRAINDICATED in CKD + anticoagulation. Acetaminophen 650 mg PRN already added to discharge list.
3. [CRITICAL] Hold or reduce Potassium Chloride — K+ already 5.3 (elevated) and dose doubled on discharge. Recheck K+ at 48h post-discharge.
4. [HIGH] Monitor metformin: eGFR 32 is borderline. Educate patient to hold during illness. Recheck renal function in 2 weeks.
5. [DEPRESCRIBE] Taper and discontinue diazepam per tapering protocol above. Refer for CBT-I.
6. [DEPRESCRIBE] Confirm diphenhydramine is off discharge list — patient must understand not to use OTC sleep aids containing diphenhydramine.
7. [DEPRESCRIBE] Review PPI indication — with ibuprofen discontinued, assess if omeprazole/pantoprazole is still needed.
8. [RECONCILE] Resolve lisinopril dose discrepancy: 20 mg (home) → 10 mg (discharge). Confirm this is intentional. Educate patient.
9. [RECONCILE] Confirm metoprolol tartrate → succinate ER switch is intentional formulary change — counsel patient.
10. [MONITOR] Recheck INR 5-7 days post-discharge (furosemide interaction + anticoagulation strategy change).
11. Schedule 7-day post-discharge follow-up: renal function, K+, INR, BP, fall risk assessment.

---

## 📊 Analysis Summary

| Metric | Count |
|--------|------:|
| Total Medications Reviewed | **14** |
| Reconciliation Changes | 8 |
| 🔴 Critical Issues | 3 |
| 🟠 High-Priority Issues | 2 |
| 🟡 Moderate Issues | 3 |
| 📉 Deprescribing Candidates | 3 |

---

*🤖 Generated by **MedHarmony v1.0** (Gemini + FHIR + MCP) • Reviewed by: Attending Clinician*
*This brief is a **clinical decision support tool**. All recommendations require independent clinician review and verification before implementation. MedHarmony does not replace clinical judgment.*
