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

## 🔗 Prescribing Cascade Analysis

> *Cascades are chains where Drug A's side effect caused Drug B to be prescribed, which caused Drug C...
> Pair-based checkers are blind to these. This section requires multi-hop clinical reasoning.*

### 🟠 Amlodipine → Furosemide → Potassium Chloride (3-link cascade)

- **Root side effect:** Amlodipine (calcium channel blocker) causes peripheral edema in ~10% of patients — particularly at doses ≥10 mg.
- **What's happening:** Edema attributed to "fluid overload" → Furosemide added → Furosemide causes potassium wasting (hypokalemia) → KCl 20 mEq/day added to replace potassium. Three drugs prescribed, but the root cause is amlodipine-induced vasodilatory edema — not true fluid overload.
- **Clinical recommendation:** Trial amlodipine dose reduction to 5 mg (or switch to felodipine, which causes less edema). If edema resolves, furosemide and KCl may both be deprescribed — eliminating the cascade entirely. Saves the patient two medications and eliminates the current hyperkalemia risk (K+ 5.3) from over-supplementation.
- **Medications to review for removal:** Furosemide, Potassium Chloride
- **Evidence:** Sica DA et al. J Clin Hypertens 2006; Makani H et al. BMJ 2011 (CCB-edema meta-analysis); Prescribing Cascade detection framework — Rochon & Gurwitz NEJM 1995

### 🟠 Ibuprofen → Pantoprazole (2-link cascade)

- **Root side effect:** Ibuprofen (NSAID) causes GI irritation and peptic ulcer risk → Pantoprazole (PPI) added for gastroprotection.
- **What's happening:** The PPI was added to manage a side effect of ibuprofen, not for an independent GERD or ulcer indication. Now that ibuprofen is being discontinued (contraindicated in CKD + anticoagulation), the rationale for pantoprazole disappears.
- **Clinical recommendation:** With ibuprofen discontinued, taper and discontinue pantoprazole. Avoid long-term PPI without documented indication — particularly in elderly patients where PPIs increase fracture risk, C. difficile, and B12 deficiency.
- **Medications to review for removal:** Pantoprazole
- **Evidence:** Rochon & Gurwitz Prescribing Cascade Concept (NEJM 1995); STOPP v3 Criteria (PPI >8 weeks without indication)

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
| 🔗 Prescribing Cascades Detected | 2 |

---

*🤖 Generated by **MedHarmony v1.0** (Gemini + FHIR + MCP) • Reviewed by: Attending Clinician*
*This brief is a **clinical decision support tool**. All recommendations require independent clinician review and verification before implementation. MedHarmony does not replace clinical judgment.*

---

# MedHarmony — Sample Patient Discharge Brief

> **Note:** This is the plain-language patient brief generated alongside the clinician safety brief. Written at an 8th-grade reading level for discharge counseling.

---

# Your Medication Information

**Dear Margaret,**

You are 78 years old and your care team has carefully reviewed all your medicines. Some medicines have changed. Please read this carefully and ask questions before you go home.

**Prepared by:** Your Care Team | **Date:** 2026-04-10 14:32 UTC

---

## 🛑 Medicines You Are STOPPING

These medicines are being removed from your list. **Do NOT take these at home.**

- **Ibuprofen (Advil, Motrin)** — This pain medicine is hard on your kidneys, and your kidneys are not working at full strength right now. It can also cause dangerous bleeding because you are on a blood thinner. We have given you a safer pain medicine instead. **Do not buy ibuprofen over the counter.**

- **Diazepam (Valium)** — This sleep medicine is not safe for people your age. It raises your risk of falls and can cause confusion. We will help you sleep better without it.

- **Diphenhydramine (Benadryl, ZzzQuil)** — This medicine (found in many over-the-counter sleep aids and allergy medicines) can cause confusion and falls in older adults. **Check the label of any sleep or allergy medicine before taking it — avoid any that contain diphenhydramine.**

---

## ✏️ Medicines With CHANGES

These medicines continue, but the dose or type has changed.

- **Metformin** (diabetes medicine) — Your dose is now **500 mg twice a day** (it was 1000 mg). Lower dose protects your kidneys. Take with food to avoid an upset stomach. **If you get sick with vomiting or diarrhea, stop this medicine and call your doctor that day.**

- **Lisinopril** (blood pressure medicine) — Your dose is now **10 mg once a day** (it was 20 mg). This helps protect your kidneys while keeping your blood pressure controlled. Watch for dizziness when you stand up.

- **Metoprolol** — You are now taking the **extended-release (ER) tablet**, taken **once a day** instead of twice. This is a formulary change — it works the same way. **Do not cut or crush the tablet.**

- **Pantoprazole (stomach acid medicine)** — Dose changed to 40 mg once a day. Your doctor will review whether you still need this medicine at your follow-up.

---

## ➕ NEW Medicines

- **Acetaminophen (Tylenol) 650 mg** — Take as needed for pain (up to 4 times a day). This is your new pain medicine replacing ibuprofen. **Do not take more than 2600 mg (4 tablets) in one day.** Do not drink alcohol with this medicine.

- **Apixaban (Eliquis) 5 mg** — NEW blood thinner for your irregular heartbeat. **IMPORTANT: Your doctor needs to confirm whether you should still take Warfarin OR switch to this medicine. Do NOT take both at the same time.** This will be decided before you leave the hospital.

---

## ✅ Medicines You Are CONTINUING

These stay the same. Keep taking them every day.

- **Warfarin 5 mg** — blood thinner (your doctor will confirm the plan — see above)
- **Amlodipine 10 mg** — blood pressure medicine
- **Furosemide (water pill) 40 mg** — removes extra fluid
- **Potassium Chloride 20 mEq** — *(dose may be adjusted — your nurse will confirm before discharge)*
- **Atorvastatin 40 mg** — cholesterol medicine (take at bedtime)

---

## ⚠️ Warning Signs — When to Get Help

**Call your doctor (same day) if you notice:**
- Dizziness or feeling faint when you stand up
- Swelling in your legs that gets worse
- Unusual bruising or bleeding gums
- Blood in your urine or dark/black stools
- Muscle weakness or irregular heartbeat (could mean potassium is too high)

**Call 911 or go to the ER immediately if:**
- You are coughing up blood or vomiting blood
- You have a bad headache or vision changes (could be a stroke)
- You have chest pain or trouble breathing
- You fall and hit your head (you are on a blood thinner — this is an emergency)

---

## 📋 Important Dos and Don'ts

**DO:**
- Bring this paper and your full medication list to every doctor visit
- Take medicines at the same time each day
- Check with your pharmacist before starting ANY new medicine — even vitamins or supplements
- Drink enough water (unless your doctor told you to limit fluids)
- Eat consistent amounts of green leafy vegetables (Vitamin K affects your Warfarin level)

**DO NOT:**
- Take ibuprofen, aspirin, or Advil/Motrin — these are dangerous with your blood thinners and kidneys
- Take Benadryl, ZzzQuil, or ANY medicine with "diphenhydramine" on the label
- Stop taking your blood thinners without talking to your doctor first
- Start herbal supplements (fish oil, turmeric, St. John's Wort) without asking — some affect blood thinning

---

## 📅 Next Steps

1. **Follow-up appointment:** Within **7 days** of discharge — your kidney function, potassium level, and INR (blood thinner level) need to be checked.
2. **Pharmacy:** Bring your full medication list. Ask the pharmacist to review everything.
3. **Questions?** Call your care team at any time.

---

*Generated by **MedHarmony v1.0** • Prepared by: Your Care Team*
*This information does not replace the advice of your doctor or nurse. Always ask your healthcare team if you have questions.*
