# Compatibility

## Measured, not universal

Only measured forms are support facts. A package declaration, projection, or roadmap candidate is not a measurement.

| Form | Measured fact | Status |
| --- | --- | --- |
| Python | Python 3.14.6 | measured on macOS |
| Operating system | macOS | measured with Python 3.14.6 |
| Package source | source checkout with Python 3.14.6 | measured by the test suite |
| Runtime dependencies | zero third-party dependencies | declared and exercised by source workflow |
| v0.2 protocol projection | four frozen protocol documents | retained compatibility surface |
| Flight Bundle | safe and scope-drift fixtures | measured by deterministic CLI tests |

Mothership requires Python 3.12 or newer. That declaration does not claim every Python 3.12+ interpreter, OS, wheel, or
package-index form is measured.

## Unmeasured forms

Linux, other Python versions in the declared range, clean-machine wheel installation, package-index distribution, and
vendor adapters are unmeasured here. They remain unclaimed until a reproducible environment and command result exist.

## Compatibility projection

The v0.2 chain remains: `frontdoor-task` -> `governance-handoff` -> `router-manifest` -> `observation-snapshot`. It is
non-authorizing and non-executing with `authority_effect: false` and `execution_effect: false`; it is not a full Flight.
