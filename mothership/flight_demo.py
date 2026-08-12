"""Read-only projections of the packaged synthetic Flight demonstrations."""

from __future__ import annotations

from importlib import resources

from .flight_contracts import FlightError
from .flight_io import load_flight_bundle
from .flight_verify import evaluate_flight


_SCENARIOS = {"safe": "safe-run", "drift": "scope-drift"}


def run_flight_demo(name: str) -> dict[str, object]:
    """Evaluate one supplied packaged Flight bundle without granting authority."""

    resource_name = _SCENARIOS.get(name)
    if resource_name is None:
        raise FlightError("INVALID", "FLIGHT.INVALID.DEMO")
    fixture = resources.files("mothership.resources").joinpath("flight", resource_name)
    with resources.as_file(fixture) as fixture_path:
        bundle = load_flight_bundle(fixture_path)
    evaluation = evaluate_flight(bundle)
    return {
        "schema_version": "mothership.flight-demo.v1",
        "scenario": name,
        "run_id": evaluation.run_id,
        "verdict": evaluation.verdict,
        "verified_stages": len(evaluation.present_stages),
        "required_stages": len(evaluation.required_stages),
        "rule_ids": sorted({finding.rule_id for finding in evaluation.findings}),
        "authority_effect": False,
        "execution_effect": False,
        "claim": "supplied-records-only",
    }


__all__ = ("run_flight_demo",)
