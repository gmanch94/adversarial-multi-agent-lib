"""Industrial Manufacturing & IoT workflows.

Modelled on the Crown Equipment Corporation surface — vertically-integrated
discrete-manufacturing OEM with IoT telematics, automation deployment, and
extended-lifecycle aftermarket service. Generalises to any OEM that ships
hardware on a subscription-data layer.

Six tracks (27 workflows in the design doc); MVP cut is 8 workflows (D-IND-1):

- **Manufacturing Ops:** MakeVsBuy, SupplierQualification, EngineeringChangeOrder,
  QualityIncidentRootCause.
- **Safety / Recall / Reserve:** ProductLiabilityRootCause (veto),
  RecallScopeManufacturing (veto, mirrors retail.recall_scope).
- **Strategic Capital:** SupplyChainResilience.
- **Industrial IoT:** TelematicsAnomalyTriage.

Personal electronics, batch chemicals, FDA medical devices, and aerospace
primes are explicitly out of scope.

All workflows use the ARIS adversarial pattern (executor + cross-model
reviewer); veto-using workflows additionally apply the D-RETAIL-1
reviewer-veto pattern for irreversible exposures (catastrophic-injury
design-defect attribution; under-scoped recall).
"""
