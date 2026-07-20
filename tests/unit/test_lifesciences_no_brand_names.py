"""D-LIFESCI-3 tripwire: no brand/company name in any lifesciences artifact.

The denylist seed is base64-encoded ON PURPOSE so the literal company/brand
strings never appear in plaintext anywhere in this repository (that is the
whole point of D-LIFESCI-3). Decoded only at runtime for the scan. This is a
tripwire for the KNOWN archetype case — it cannot prove the absence of every
possible brand, so it complements, not replaces, the ship-audit review.
"""
from __future__ import annotations

import base64
from pathlib import Path

import pytest

# base64 of the archetype company name + its DISTINCTIVE flagship product brands,
# lowercased. Decoded at runtime only. Add new seeds as base64 to keep plaintext
# clean. RULE: only seed distinctive tokens — the scan is a case-insensitive
# SUBSTRING match, so a brand that is also a common word (e.g. a nutrition brand
# spelled like the verb "ensure") is deliberately EXCLUDED to avoid false
# positives on ordinary regulatory prose. Distinctive tokens only.
_ENCODED_DENYLIST: tuple[str, ...] = (
    "YWJib3R0",          # <company>
    "YmluYXhub3c=",      # <rapid-test brand>
    "c2ltaWxhYw==",      # <infant-formula brand>
    "cGVkaWFzdXJl",      # <pediatric-nutrition brand>
    "YWxpbml0eQ==",      # <core-lab brand>
    "bWl0cmFjbGlw",      # <structural-heart brand>
    # Third-party enterprise-tool brands. D-LIFESCI-3 also bars vendor product
    # names (they appeared in PRODUCTION_GAPS docstrings); these slipped past the
    # archetype seed and were caught by the ship-audit (2026-07-19). Distinctive
    # tokens only — a common-word requirements tool (spelled like the plural of
    # "door") is deliberately EXCLUDED to avoid substring false positives; the
    # ship-audit remains the general catch for non-distinctive brands.
    "dmFsZ2VuZXNpcw==",  # <validation-lifecycle vendor>
    "YXJndXM=",          # <safety-database vendor>
    "d2luZGNoaWxs",      # <PLM vendor>
    "dGVhbWNlbnRlcg==",  # <PLM vendor>
    "dHJhY2t3aXNl",      # <complaint-handling QMS vendor>
    "cHJvbW9tYXRz",      # <promo-review DAM vendor>
)

_DENYLIST = tuple(base64.b64decode(s).decode("ascii").lower() for s in _ENCODED_DENYLIST)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCAN_ROOTS = (
    _REPO_ROOT / "src" / "adv_multi_agent" / "lifesciences",
    _REPO_ROOT / "examples" / "lifesciences",
)
_SCAN_TESTS_GLOB = "test_*.py"  # lifesciences workflow tests in tests/unit


def _lifesciences_files() -> list[Path]:
    files: list[Path] = []
    for root in _SCAN_ROOTS:
        if root.exists():
            files.extend(p for p in root.rglob("*") if p.suffix in {".py", ".md"})
    tests_dir = _REPO_ROOT / "tests" / "unit"
    lifesci_modules = {
        "test_design_control_traceability.py",
        "test_nutrition_health_claim.py",
        "test_combination_product_pmoa.py",
        "test_assay_performance_claim.py",
        "test_substantial_equivalence_510k.py",
        "test_promotional_off_label_review.py",
        "test_device_reportability.py",
        "test_field_action_classification.py",
        # Phase-2 batch A (#9-16) — guarded by .exists() below, so listing them
        # before the files exist is harmless (the case is skipped).
        "test_gxp_data_integrity.py",
        "test_computer_system_validation.py",
        "test_stability_shelf_life.py",
        "test_batch_release_deviation.py",
        "test_cmo_qualification.py",
        "test_udi_labeling.py",
        "test_clinical_protocol_design.py",
        "test_pharmacovigilance_signal.py",
        # Phase-2 batch B (#17-27) — same .exists() guard.
        "test_rems_design.py",
        "test_premarket_cybersecurity.py",
        "test_post_market_clinical_followup.py",
        "test_heor_dossier.py",
        "test_serialization_dscsa.py",
        "test_biosimilar_comparability.py",
        "test_sterility_assurance.py",
        "test_cold_chain_excursion.py",
        "test_bioequivalence.py",
        "test_medical_information_response.py",
        "test_ccds_label_change.py",
    }
    files.extend(tests_dir / name for name in lifesci_modules if (tests_dir / name).exists())
    return files


def test_denylist_decodes_nonempty() -> None:
    # Guards against a corrupted seed silently disabling the tripwire.
    assert _DENYLIST
    assert all(term for term in _DENYLIST)


@pytest.mark.parametrize("path", _lifesciences_files(), ids=lambda p: p.name)
def test_no_brand_name_in_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8").lower()
    hits = [term for term in _DENYLIST if term in text]
    assert not hits, (
        f"{path.relative_to(_REPO_ROOT)} contains brand/company name(s) "
        f"(D-LIFESCI-3 violation). Use a generic product CATEGORY instead."
    )
