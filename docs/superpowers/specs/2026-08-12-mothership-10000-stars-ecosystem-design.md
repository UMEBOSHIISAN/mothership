# Mothership 10,000 Stars Ecosystem Design

**Date:** 2026-08-12

**Status:** HUMAN-SELECTED DIRECTION; IMPLEMENTATION GATES PENDING

**North Star:** 10,000 GitHub stars on `UMEBOSHIISAN/mothership`

**Selected approach:** Flagship funnel — one destination, independently useful companions

**Scope:** Public Mothership ecosystem presentation, documentation, visual assets,
repository metadata drafts, and release/launch materials. Runtime behavior, deployment,
credentials, schedulers, private operations, and UMEBOSHI brand-identity assets are excluded.

## 1. Outcome

Mothership becomes the single public flagship for the ecosystem:

> **The black box for AI agents. Know what your agents were allowed to do — and prove what actually happened.**

Every public companion remains independently adoptable and technically honest, but its
public presentation has one ecosystem job in addition to its own product job: increase
understanding of, trust in, and qualified traffic to Mothership.

The target is directional, not a guaranteed forecast. The work is complete when the
public funnel is coherent, truthful, visually strong, locally verified, and ready for an
explicit publication decision. Star count is the North Star outcome; it is not evidence
that can be manufactured by documentation work alone.

## 2. Why the Flagship Funnel

Three structures were considered:

1. **Flagship funnel — selected.** One call to action and one star destination. Companion
   repositories preserve ownership and release boundaries while routing discovery and
   credibility back to Mothership.
2. **Equal constellation — rejected.** Polishing all repositories as equal destinations
   divides attention, calls to action, and stars across eleven small surfaces.
3. **Physical monorepo — rejected.** It creates a large migration, erases useful ownership
   boundaries, and solves presentation by changing architecture.

The selected structure is the only one that concentrates the requested outcome without
misrepresenting the ecosystem as one package or destroying independent adoption.

## 3. Audience and Conversion Story

### Primary audience

- engineers building or supervising AI-agent systems;
- agent-platform, LLMOps, local-AI, security, and governance practitioners;
- developers who have experienced an agent claiming success without inspectable proof;
- evaluators who want a deterministic, local, non-authorizing demonstration before adopting.

### Visitor journey

The Mothership public surface must answer five questions in order:

1. **What is it?** A black box for AI agents.
2. **Why now?** Agent activity is easy to run and hard to prove.
3. **Can I see it?** Yes — one safe flight and one drifted flight in 60 seconds.
4. **Why trust it?** The proof is deterministic, local, fail-closed, and test-bound.
5. **What next?** Star Mothership, run the demo, then explore the relevant companion.

Every companion starts from its own one-sentence problem, shows one concrete proof, and
ends with the same relationship: "Part of the Mothership constellation" plus a direct
Mothership link. It must never claim that Mothership installs, invokes, or controls it.

## 4. Repository Topology

### Tier 0 — the only flagship

| Repository | Public job | Primary conversion |
| --- | --- | --- |
| `mothership` | Own the category, complete product story, Flight Recorder demo, ecosystem map | Star Mothership and run the 60-second demo |

### Tier 1 — proof products

These repositories already have a memorable principle, runnable evidence, or visual
identity. They remain distinct products and supply the strongest credibility paths.

| Repository | Irreducible idea | Signature proof |
| --- | --- | --- |
| `agent-frontdoor` | The request reaching a worker should be the request a human read | safe card versus scope drift |
| `workflow-governance-model` | A label is not evidence | typed evidence-to-verification chain and stale-reference rejection |
| `mothership-router` | Approval applies only to what it approved | registry digest invalidates stale approval |
| `secretary-tui` | An observation screen must not be able to act | read-only terminal demo and false-effect rejection |

### Tier 2 — focused primitives

These repositories should be concise, precise proof libraries rather than miniature
flagships. Each receives a clear top fold, one diagram or terminal example, accurate
metadata, and a route back to Mothership.

| Repository | One responsibility |
| --- | --- |
| `agent-team-runtime` | local packet replay and canonical completion reduction |
| `evidence-spine-core` | append-only task-to-artifact evidence chains |
| `run-lineage-core` | deterministic joins over already-normalized lineage records |
| `source-health-core` | source-backed observation contract validation |
| `agent-decision-core` | provider-neutral advisory local-first gating |
| `knowledge-lifecycle-kit` | read-only lifecycle proposals and advisory routing evidence |

No new repository is added. No companion is renamed, archived, merged, or made a runtime
dependency as part of this work.

## 5. Mothership Public Surface

### GitHub description draft

> The black box for AI agents — record authority, replay evidence, and detect drift without executing the agent.

This replaces the older machine-portability description once the Flight Recorder change is
published. Suggested topics are drafts until current GitHub topic limits and collisions are
checked: `ai-agents`, `agent-observability`, `agent-governance`, `audit-trail`,
`flight-recorder`, `llmops`, `python`, `local-first`, `security`, `developer-tools`.

### README fixed order

1. whale mark, product name, one-sentence promise, and useful factual badges;
2. a short animated or recorded safe-versus-drift terminal proof;
3. the copyable 60-second quick start with canonical output and exit codes;
4. the incident story: intended authority versus observed execution versus verified result;
5. the complete Flight lifecycle and what causes each verdict;
6. the boundary promise: local, deterministic, non-executing, non-authorizing;
7. adoption paths: standalone Flight Recorder, generic JSONL import, protocol suite;
8. the flagship funnel map and companion cards;
9. API, compatibility, security, installation, contributing, roadmap, Japanese guide;
10. one final call to action: star the repository if inspectable agent evidence matters.

The README must stay proof-first. It must not become a marketing page that delays the
working demo, repeats feature lists, or substitutes adjectives for measured behavior.

### Message hierarchy

- **Category:** black box for AI agents.
- **Problem:** a successful agent message is not proof of authorized, completed work.
- **Mechanism:** portable metadata-only flight bundles, causal lineage, replay, and verdicts.
- **Boundary:** it reads supplied evidence; it does not run, approve, repair, retry, or publish.
- **Proof:** safe and drift examples generated from the real CLI and guarded by tests.

## 6. Visual System

The visual language is "deep-space instrument panel," not generic AI gradients and not
vendor branding. It uses the existing whale/mothership identity, navy space, restrained
cyan telemetry, warm amber warnings, red only for actual drift/failure, and high-contrast
monospace evidence.

### Mothership assets

| Asset | Purpose | Source-of-truth rule |
| --- | --- | --- |
| hero/social preview, 1280×640 | GitHub social card and README opening image | original art; no vendor logos, model likenesses, or fake UI claims |
| safe-versus-drift terminal recording | demonstrate the product in under 30 seconds | recorded from current CLI; output must match canonical fixtures |
| Flight lifecycle diagram | show intent → approval → execution → result → verification → persistence | editable SVG with accessible text and alt text |
| causal incident diagram | explain why a superficially successful run can be drifted | derived only from documented Flight semantics |
| flagship constellation diagram | show companions as independent proof nodes returning to Mothership | no install or runtime arrows; links mean discovery/composition only |

Raster art may create atmosphere but never establish a product claim. All behavioral
visuals are generated from code, schemas, fixtures, or editable SVG source.

### Companion assets

- Preserve the strong existing marks and explanatory diagrams in Agent Frontdoor, WGM,
  Router, and Secretary TUI.
- Add a compact shared "Mothership constellation" footer treatment, implemented as
  text plus a small local SVG where useful; never hotlink a mutable image from another repo.
- Give each Tier 2 primitive one signature visual, preferably an editable SVG or real
  terminal transcript:
  - replay reducer lane for Agent Team Runtime;
  - append-only chain for Evidence Spine;
  - exact/proposed/ambiguous join map for Run Lineage;
  - source envelope and claim-limit diagram for Source Health;
  - advisory gate with `execution_allowed: false` for Agent Decision;
  - inspect → propose → human decision lifecycle for Knowledge Lifecycle Kit.
- Avoid eleven near-identical banners. Consistency comes from typography, telemetry
  colors, relationship copy, and CTA hierarchy; distinct responsibilities remain visible.

### Accessibility and rendering

- Every image has meaningful alt text.
- Text necessary to understand a contract also exists in Markdown, not only in pixels.
- SVG text remains readable in GitHub light and dark themes.
- Raster images are compressed and reviewed at desktop and mobile README widths.
- The terminal recording has a static transcript fallback.

## 7. Companion README Contract

Every companion README uses the same compact top-fold contract:

1. identity mark or signature visual;
2. one memorable English sentence and one concise Japanese sentence where already used;
3. one paragraph defining the product and its strongest non-goal;
4. one runnable proof or import example visible without scrolling through architecture;
5. factual badges only;
6. a relationship strip linking to Mothership;
7. safety/non-goal language proportional to actual risk;
8. installation, API, development, security, and license details below the proof.

Tier 1 keeps its full storytelling depth. Tier 2 should usually stay under roughly 180
README lines unless the contract itself genuinely needs more explanation. This is an
editorial target, not an automated acceptance threshold.

### Cross-link language

Recommended shared wording:

> Part of the Mothership constellation. This project is independently adoptable and does
> not grant Mothership authority to install, invoke, or configure it.

Recommended CTA:

> For the complete agent-flight story — authority, evidence, replay, and drift — visit
> [Mothership](https://github.com/UMEBOSHIISAN/mothership).

The Mothership link is the only star-oriented CTA. Companion READMEs may ask users to try
or adopt that companion, but they do not run separate star campaigns.

## 8. Repository Metadata and Discovery

A repository metadata manifest will hold drafts for all eleven repositories:

- GitHub description;
- homepage, when a durable public page exists;
- topics;
- social preview asset path;
- primary language and package-manager wording;
- flagship relationship line;
- verification date and source commit.

The manifest is locally reviewable and is not itself evidence that GitHub was updated.
Remote descriptions, topics, social previews, releases, or repository settings require a
separate explicit publication action and post-change measurement.

Sparse or empty current descriptions are corrected first. Descriptions use one problem,
one mechanism, and one boundary; they avoid phrases such as "production-ready," "secure,"
"complete," or "guaranteed" unless a defined test proves the exact claim.

## 9. Launch Kit

The local launch kit contains reusable drafts, not automatic posts:

- GitHub release title and release notes;
- a short announcement, a longer technical thread, and a Japanese counterpart;
- one technical article outline: "Why AI agents need a flight recorder";
- screenshots/social cards sized for GitHub and common social feeds;
- a 20–30 second demo clip plus transcript;
- an issue/discussion prompt asking users for real drift cases without requesting secrets;
- a maintainer checklist for links, release reachability, rendered images, and measured
  GitHub metadata.

No external post, release, tag, push, upload, or social action is part of local authoring.
Publication requires explicit approval for the exact target.

## 10. Measurement

### North Star

- GitHub stars on `UMEBOSHIISAN/mothership`.

### Leading indicators

- Mothership repository visitors and unique visitors;
- README-to-demo completion observed through voluntary issue/discussion feedback or a
  separately approved privacy-respecting mechanism;
- clone/package download and release download counts when the platform exposes them;
- companion-to-Mothership referral traffic where measurable;
- demo failures caused by documentation drift;
- stars gained around releases or launch events, reported as correlation, not causation.

No tracking pixel, external analytics script, fingerprinting, or hidden telemetry is added.
If GitHub traffic data cannot be observed, it remains UNKNOWN rather than being inferred.

## 11. Implementation Topology

### Branch discipline

- The completed Flight Recorder branch remains immutable at commit `62240fd`.
- The 10k work uses `feature/mothership-10000-stars`, based on that verified commit.
- Each companion receives its own branch or isolated worktree from its measured clean base.
- Existing dirty or unpushed work is never overwritten, staged, or bundled.
- Cross-repository commits remain separate so every repository can be reviewed, tested,
  and published independently.

### Waves

1. **Flagship conversion surface:** Mothership copy hierarchy, real demo recording,
   visuals, metadata manifest, and tests for commands/links/assets.
2. **Proof products:** Frontdoor, WGM, Router, and Secretary TUI relationship blocks,
   metadata, rendered proof review, and repository-native tests.
3. **Focused primitives:** six concise README rebuilds, signature visuals, descriptions,
   topics, and native test suites.
4. **Launch kit and audit:** release/article/social drafts, accessibility review, public
   boundary scan, visual render review, and final per-repo diff ownership audit.
5. **Publication checkpoint:** present exact commits and remote mutations for separate
   human approval; after publication, measure reachability and rendered state.

The waves may be implemented locally in sequence. They are not retried automatically.
Any failed repository verification stops that repository and remains visible in the
closeout; another repository's success cannot mask it.

## 12. Testing and Review

### Mothership

- Python 3.12+ full unit suite;
- focused Flight Recorder suite;
- canonical CLI outputs and exit codes;
- README command extraction and execution;
- Markdown link and image validation;
- visual inspection at desktop and narrow widths;
- `git diff --check`;
- private-path, secret-like value, raw-content, and execution-primitive scans;
- final Codex review.

### Companions

Each repository runs its documented native test and boundary command. Documentation-only
changes do not permit skipping tests when the README includes executable claims. Links,
image sources, alt text, private paths, secret markers, and Mothership relationship language
are checked in every repository.

### Cross-project design gate

Because this is cross-project design, a design-advisor gate is mandatory before runtime or
public-surface implementation. The gate reviews repository tiers, responsibility boundaries,
claim accuracy, visual scope, publication separation, and the risk of overwriting unrelated
work. Its output is advisory and cannot grant edit or publication authority.

## 13. Authority and Publication Boundaries

This design grants no authority to:

- push any branch;
- merge Flight Recorder or the 10k branch;
- edit GitHub descriptions, topics, social previews, homepage, or repository settings;
- create tags or releases;
- upload a package;
- post an announcement;
- change CI/CD, hooks, schedulers, deploy definitions, secrets, auth, or infrastructure.

Local documentation and asset implementation still requires the applicable human edit
approval. External publication is a later, target-specific human decision. "Tests pass" and
"committed" never mean "published."

## 14. Completion Criteria

Local implementation is complete only when all of the following are measured:

1. Mothership presents the black-box category, real safe/drift proof, and one unambiguous
   star destination in its first screenful.
2. Every behavioral claim in the Mothership README is backed by current code, fixtures,
   tests, or a clearly named limitation.
3. Mothership has a reviewed hero/social image, actual terminal recording, accessible
   lifecycle/incident visuals, and a static transcript fallback.
4. All ten companions have accurate top folds, one useful proof visual or transcript,
   a truthful independence statement, and a prominent Mothership route.
5. The metadata manifest contains reviewed description/topic/social-preview drafts for all
   eleven repositories.
6. The local launch kit contains English and Japanese release/announcement material,
   article outline, social images, demo clip, transcript, and publication checklist.
7. Every repository's relevant tests, link checks, asset checks, privacy scan, diff check,
   and final review pass at its recorded commit.
8. Dirty-tree ownership is measured and unrelated user work remains untouched.
9. No remote or public state is described as changed before commit reachability and the
   rendered/public side effect are measured.
10. A factual closeout lists per-repository commits, tests, remaining publication gates,
    and UNKNOWN metrics without inflating them into success claims.

The 10,000-star North Star remains active after local completion. Reaching it depends on
public distribution, sustained product quality, community response, and time; none can be
truthfully guaranteed by a single implementation wave.
