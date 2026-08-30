# Paper Evidence and Claim Boundaries

## Research position

Mothership is a credible artifact-paper or systems/software-engineering paper candidate. The defensible contribution is not a new language model and not a claim of autonomous-agent accuracy. It is a control-plane design that keeps recommendation, authority, execution, and observation as separate versioned data states, then composes independently adoptable tools without allowing a valid document to become implicit permission.

A suitable working title is:

> **Authority as Data: Fail-Closed Composition for Local AI Coding Control Planes**

The paper is not yet submitted or peer-reviewed. The measurements below establish reproducible artifact behavior on tracked synthetic corpora; they do not establish production effectiveness or external validity.

## Reproducible Mothership measurements

Run from a Mothership source checkout:

```sh
python3 tools/run_evaluation.py
python3 -m unittest tests.test_evaluation -v
```

The first command emits the exact tracked result in [`evaluation/results/mothership-0.3.1.json`](../../evaluation/results/mothership-0.3.1.json). The corpus is [`evaluation/corpus/protocol-validation.v1.json`](../../evaluation/corpus/protocol-validation.v1.json).

| Measurement | Result | Denominator and meaning |
| --- | ---: | --- |
| Valid protocol acceptance | 4/4 | One canonical valid document for each frozen protocol kind was accepted |
| Invalid protocol rejection | 20/20 | Five named synthetic mutations for each protocol kind were rejected |
| Total conformance agreement | 24/24 | Outcome matched the tracked accepted/rejected label |
| Demo determinism | 8/8 | Eight controlled process environments produced one byte-identical output |
| Resource integrity | passed | The packaged inventory, schema digests, registry, demo, and inert executor example passed |
| Authority-capable protocols | 0/4 | Every initial registry entry declares `authority_capable: false` |
| Execution-capable protocols | 0/4 | Every initial registry entry declares `execution_capable: false` |

These numbers are synthetic conformance results. “24/24” must not be shortened to “100% accurate” because the corpus is authored with the implementation contract and is not an independent field sample.

## Reproducible Agent Frontdoor measurements

The Agent Frontdoor corpus and metric tests at public commit [`20e0274938c0a5947445601cf2fda1eabb9beea0`](https://github.com/UMEBOSHIISAN/agent-frontdoor/commit/20e0274938c0a5947445601cf2fda1eabb9beea0) were measured with Python 3.14.6 using:

```sh
python -m pytest tests/test_fixture_metrics.py tests/test_no_execution_paths.py -q
```

Measured result: `32 passed`.

The labeled-corpus outcomes asserted by that suite were:

| Measurement | Result | Denominator and meaning |
| --- | ---: | --- |
| Positive-card validity | 31/31 | All authored valid task cards passed schema and semantic validation |
| Negative issue-code agreement | 41/41 | Every authored invalid card produced its exact expected issue-code set |
| Blocking-condition recall | 26/26 | Every labeled blocking case produced all required blocking codes |
| `UNKNOWN` fail-safe coverage | 7/7 | Every named ambiguous case failed closed for its expected reason |
| Boundary-drift detection | 16/16 | Every labeled unsafe before/after transition was detected with exact codes |
| Safe drift controls | 4/4 | Every labeled safe transition remained non-drifted |

The fixture bytes and metric test were verified to be identical between the measured checkout and that public commit. These results are exact agreement on an internal, synthetic, labeled corpus. They are not estimates of performance on naturally occurring user requests.

## Reproducible four-repository conformance measurements

Mothership's explicit companion auditor was run against four isolated local
checkouts pinned to exact commits:

| Owner | Tested commit | Native verification |
| --- | --- | --- |
| Agent Frontdoor | `4bcfcb6c1868a87076502999a38127e28e275e70` | 628/628 pytest cases passed; conformance reproduction 12/12 passed after the documentation-only fix |
| Workflow Governance Model | `98576b4f3f755aceccc657bc83df7c94260d4fc0` | 18/18 unittest cases passed |
| Mothership Router | `a23f4b651e1a8baf39a1266a66188bec21c3265c` | 20/20 unittest cases passed |
| Secretary TUI | `f3cb61e61bc88e7c4cfd09efe93006c812258fe9` | 20/20 top-level Go tests passed; race, vet, and build passed |

The closed audit result was:

| Measurement | Result | Denominator and meaning |
| --- | ---: | --- |
| Owner manifests accepted | 4/4 | Every pinned repository supplied the exact closed Mothership 0.2 manifest |
| Owner schema digests matched | 4/4 | Every manifest digest matched its owner schema bytes |
| Bundled schema byte identity | 4/4 | Every Mothership schema snapshot was byte-identical to its owner |
| Public examples accepted | 4/4 | Every pinned owner example validated against its declared protocol |
| Cross-repository chain | passed | Router input matched its owner example and shared task identity/capability/status remained consistent |
| Authority effects | 0/4 true | All four owner manifests explicitly reported `false` |
| Execution effects | 0/4 true | All four owner manifests explicitly reported `false` |

The audit requires four explicit normalized roots, exact repository order, and
exact commit identity; it does not discover repositories. Its success report is
canonical, path-free JSON. These measurements establish compatibility for the
four listed local commits only. They do not establish that those commits have
been pushed, tagged, released, or independently reproduced.

## Candidate paper claims

The evidence currently supports these bounded claims:

1. A four-stage control-plane protocol can be composed while every interchange document remains non-authorizing and non-executing.
2. The reference artifact rejects the tracked malformed, schema-drifted, authority-escalating, and execution-escalating protocol mutations.
3. The reference demo is byte-deterministic across the tracked process-environment matrix.
4. Agent Frontdoor detects every tracked boundary-drift case and preserves every tracked safe control in its current synthetic corpus.
5. The complete artifact can expose integrity and conformance evidence without contacting a model or granting execution authority.

## Claims that remain out of scope

Do not claim any of the following from the present evidence:

- production accuracy, generalization, or a population-level safety rate;
- superiority to another agent framework without a preregistered comparative study;
- prevention of every malicious input or local compromise;
- formal verification, security certification, or proof of sandbox isolation;
- successful execution of real work, because the evaluated chain deliberately does not execute;
- user adoption, productivity improvement, incident reduction, or causal business impact.

## What a submission still needs

Before submission, add an independently authored or blinded request corpus, inter-rater agreement for labels, baseline comparisons, operating-system and Python-version replication, ablation studies for each boundary check, and an external reproduction by a separate operator. Report confidence intervals once the sample design makes them meaningful; do not compute them over the current hand-authored conformance cases as if they were an independent sample.

The strongest near-term venue fit is a systems, software-engineering, AI tooling, or artifact-evaluation track. Framing it as an ML-accuracy paper would undersell the actual contribution and overstate what has been measured.
