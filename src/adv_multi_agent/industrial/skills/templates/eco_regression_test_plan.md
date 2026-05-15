---
name: eco_regression_test_plan
description: Build a regression test plan for a proposed ECO covering deployed-product compatibility
inputs: [change_summary, deployed_product_context]
---
You are a V&V engineer. Build the regression test plan covering deployed product.

Change summary: {change_summary}
Deployed product context: {deployed_product_context}

Build:
1. **Bench verification** — DV / PV / characterisation tests for the modified component / sub-assembly.
2. **System-level integration** — full-vehicle / full-machine test plan against the original system requirements.
3. **Firmware-compatibility matrix** — every deployed firmware version × new-part / old-part combination tested.
4. **Service-parts back-compat** — old service-part still functional with new build? New service-part installable on old build?
5. **Adjacent-product use** — products that share the same component class — regression scope.
6. **Field-trial scope** — number of units, duration, customer signature, escalation plan.

Output:
- Regression test matrix
- Field-trial plan
- Gate criteria for go-live
- Regression flags: [coverage gaps]
