# Integration verification

Date: 2026-11-28T15:39:19.583438+08:00
Base: `9c5c0df72f21313ae5d14d4b746d3808b154c949`.

Applied the supplied patch on a clean clone and verified the SHA-256 of all 14 delivered files against the implementation manifest. No production-source changes were made during integration. Evidence files were added separately.

## Executed checks

- `git apply --check`: passed before application.
- `git diff --check`: passed.
- `/tmp/changeguard-submit-venv/bin/python -m pytest -q`: **90 passed in 6.67s**, with localhost, 127.0.0.1 and ::1 appended to process-local NO_PROXY/no_proxy.
- `python scripts/evaluate_completeness.py --demo --output docs/verification/v0.4/integration/evaluation`: three synthetic controls passed; two masked cases. Rule Hit@1=2/2, baseline Hit@1=0/2; both Hit@5=2/2. These are synthetic recovery results, not real-defect accuracy.

The initial suite returned 88 passed and two failed local HTTP adapter cases with HTTP 502. The successful rerun bypassed the environment proxy for loopback only. Both logs are retained; no application or test code was modified to obtain the pass.

The environment was created using dependency ranges in requirements-dev.txt, not the lockfile. See environment.txt for direct installed versions. Browser smoke scripts, paid AI calls and real-repository effectiveness evaluation were not rerun during integration. Historical browser logs remain in the separate implementation-handoff directory.

## Revision binding

The PR identifies the commit carrying this evidence. The delivered source hashes are fixed in the handoff manifest. Before merging later source changes, rerun affected checks and bind the new results to their tested revision.
