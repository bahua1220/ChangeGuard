# v0.4 verification evidence

## Implementation handoff

The `implementation-handoff/` directory preserves logs and synthetic evaluation outputs supplied with the v0.4 implementation package. Its base commit is `9c5c0df72f21313ae5d14d4b746d3808b154c949`. The manifest binds the 14 delivered source files by SHA-256; these hashes were checked after applying the patch.

The supplied log records 90 passing pytest cases and four successful browser scripts. These are the original implementer’s records, not new integration test results. They do not identify a final merged release SHA or independently establish results on later changes. The exported example includes an original local Windows path, not a path required on the reviewing machine.

The evaluation uses synthetic controls and two masked-change cases. It measures candidate recovery and ranking against a file-frequency baseline, not real-defect accuracy. Both methods recovered the hidden path within the top five in these two cases; only the rule method ranked it first in both. Do not describe these numbers as general accuracy or proof of completeness.

Archived text has normalized LF line endings and trailing whitespace for repository formatting; result content is unchanged. The original package remains local. Manifest hashes refer to the 14 delivered source files, not these normalized log copies.

## Integration

Integration checks, when executed, are recorded separately in `integration/`. No browser rerun or real-repository effectiveness evaluation is implied by the handoff logs. Record the tested commit SHA in the PR after committing.
