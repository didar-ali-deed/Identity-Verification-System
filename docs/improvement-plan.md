# Improvement plan

The immediate problem was inconsistent extraction: document review used the spatial EasyOCR parser, while pipeline Stage 2 used older regular expressions. Review and pipeline now share the visual field parser. MRZ remains separate evidence with check-digit validation; successful visible text does not prove a valid MRZ or document authenticity.

## Completed cleanup

- One OCR provider: EasyOCR. Removed TrOCR inference, fallback configuration and obsolete packages from the dependency manifests.
- One visual field parser for review and pipeline; supports spatial labels and month-name dates.
- Removed the unused legacy scoring/face task path and its scoring service.
- Removed superseded TrOCR reports. Synthetic specimen images, meaningful tests, migrations, model adapters and security documentation remain.
- Corrected country-code matching and added MediaPipe EGL/GLES runtime dependencies.

## Next work, in order

1. **Biometric reliability:** expose structured provider failures separately from a measured non-match. Diagnose face detection, crop quality and model availability on representative consented images. Require both document comparisons for automatic approval; never manufacture a score for missing evidence.
2. **Learned liveness:** configure the documented MiniFASNet provider and licensed weights, evaluate real/replay/print examples, and calibrate thresholds on a held-out dataset. Heuristic texture checks must continue to require review. Add server-verified capture challenges and injection defenses before making provenance claims.
3. **Document evidence:** improve MRZ region detection with EasyOCR, report every check-digit failure and support separate front/back ID uploads. Preserve visual/MRZ provenance and distinguish missing text from conflicting text. Add validated issuer templates without inferring citizenship from residence.
4. **Evaluation:** collect consented, access-controlled samples spanning lighting, rotation, scripts, devices and document versions. Measure per-field OCR errors, face false accepts/rejects, liveness attack errors and latency. Publish aggregate results and limitations; keep personal images out of Git.
5. **Operations:** add retention/deletion jobs, encrypted remote storage, model version pinning, task failure monitoring and a controlled retry/version workflow. Keep old decisions immutable and record reprocessing as a new version or application.
6. **GitHub presentation:** update synthetic screenshots after behavior stabilizes, document reproducible evaluation, check licenses and run CI before publishing. Present this as an engineering prototype until real evaluation supports stronger claims.

## Acceptance criteria

- Review and pipeline agree on names, DOB and expiry for the same OCR rows.
- Missing/invalid MRZ remains visible and cannot silently count as valid.
- A provider error is distinguishable from a measured biometric or liveness failure.
- Automatic approval requires verified liveness, successful face comparisons and complete identity evidence.
- Tests use synthetic fixtures; repository artifacts contain no personal documents.

See [run instructions](run-guide.md) and [model setup](models.md).
