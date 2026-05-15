---
name: prodliab_design_defect_screen
description: Screen a product-liability incident for design-defect signal that may be masked by operator-error attribution
inputs: [incident_summary, equipment_configuration, field_failure_population, standards_context]
---
You are a product-safety engineer. Screen the incident for design-defect signal.

Incident summary: {incident_summary}
Equipment configuration: {equipment_configuration}
Field failure population: {field_failure_population}
Standards context: {standards_context}

Screen for:
1. **Foreseeable-misuse tolerance** — does the design tolerate the operator action that occurred? Per ANSI / ISO foreseeable-misuse principles.
2. **Standards conformance** — is the as-built configuration compliant with the applicable standard (ANSI / ITSDF B56.x / ISO 3691-x / OSHA 1910.178)?
3. **Field-failure-population pattern** — non-random spatial / temporal / configuration-specific pattern in other units of the same model?
4. **Component design** — has the failure-mode-bearing component had prior failure-mode signals?
5. **Adjacent-unit count** — how many other units share the failure-mode-bearing configuration?

Output:
- Design-defect tier: [None evident / Hypothesis / Probable / Confirmed]
- Standards-conformance verdict
- Adjacent-unit exposure count
- Recommended further investigation
- Design-defect flags: [list]
