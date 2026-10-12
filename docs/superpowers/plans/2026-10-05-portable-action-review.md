# Portable action review implementation plan

Spec: [portable action review](../specs/2026-10-05-portable-action-review.md).
Base: `bf2e7ed10134c2d7b1c4be5dce29a9eb9bebaf03`.

1. Add the pure review module, facade, schemas and regression tests. Observe a
   meaningful failing test before implementation, then pass targeted tests.
2. Add an offline real-ledger/companion reference example and regression tests;
   keep host runtime integrations explicitly unimplemented.
3. Document official integration routes and completion criteria, update both
   READMEs and explanatory asset sources, regenerate and inspect SVG/GIF/posters.
4. Pair candidate versions, regenerate current CLI/evaluation outputs and
   checksums, exercise installed artifacts, and run both full suites.
5. Obtain independent review of the actual diff, resolve concrete findings,
   and preserve measured verification in the existing task result/scorecard.
   A draft PR may carry the reviewable work; no merge/release is included.

Native workers own separate files; parent owns integration and final checks.
Use the existing mutable task result rather than a duplicate runner/ledger.
Core implementation, docs/assets and example/version work share only the API
specified above. Docs consume that API and must not promise runtime fences.
Version tests consume the paired metadata. Checksum regeneration follows all
edits. This decomposition has no concurrent write scope overlap.
