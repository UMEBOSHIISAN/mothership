"""Explicit public read-back of caller-attested recorded evidence.

This module cannot recreate an issued action or session. Existing export and
inspection remain offline; only an explicit call here reaches the observer.
"""

from mothership.contracts import ContractError, canonical_json_sha256

from .evidence import (
    EvidenceError,
    _invalid,
    _bounded_plain,
    _validate_bundle_shape,
    export_evidence,
    inspect_evidence,
)


def readback_evidence(bundle: object, *, opener=None) -> dict[str, object]:
    """Return a new closed bundle and its caller-retained read-back sidecar.

    Accept only complete execution evidence lacking Verification. Validate
    all original rows and the exporter-derived Receipt before any public GET.
    Never replace an existing Verification, write files, or renew authority.
    """
    try:
        checked = _validate_bundle_shape(bundle)
        inspect_evidence(checked)
        if checked["missing"] != ["verification"] or checked["receipt"] is None:
            raise _invalid()

        # Import only on the explicit network-capable route. The companion
        # validates recorded data, without constructing a FrozenAction.
        from mothership_github.verification import verify_recorded_merge_pr

        observed = verify_recorded_merge_pr(
            checked["request"]["action"], checked["receipt"], opener=opener
        )
        updated = export_evidence(
            checked["request"],
            response=checked["response"], decision=checked["decision"],
            consume=checked["consume"], started=checked["started"],
            finished=checked["finished"], executor_ref=checked["executor_ref"],
            verification=observed["verification"],
        )
        _bounded_plain(observed["evidence"])
        digest = canonical_json_sha256(observed["evidence"])
        if updated["verification"]["evidence_refs"] != [
            {"ref_id": "github-readback:" + digest, "sha256": digest}
        ]:
            raise _invalid()
        return {"bundle": updated, "evidence": observed["evidence"]}
    except EvidenceError:
        raise
    except (ContractError, ImportError, KeyError, TypeError, ValueError, RecursionError, OverflowError):
        raise _invalid() from None


__all__ = ["readback_evidence"]
