# Upgrade validation

Validated locally on 30 September 2026 using synthetic data.

- 99 backend tests passed, including PostgreSQL integration tests for ownership, uploads, replacement, reset/file cleanup, outbox delivery, review restrictions and retry preservation, plus OCR orientation, label geometry, reading-order and MRZ regressions.
- Ten Playwright browser tests passed across desktop and mobile viewports, including demo outcomes, camera submission, replacement, reset and ambiguous OCR name/date comparison.
- Backend Ruff lint/format, frontend ESLint, TypeScript/Vite production build and Git whitespace checks passed.
- Fresh PostgreSQL database migrated through `e62f9140b3a1`.
- Default, showcase and GPU Compose configurations validated.
- The showcase image built and served the demo through Nginx; screenshots and the recording use synthetic fixtures.
- The CPU backend image built, passed API/worker/EasyOCR/MediaPipe/DeepFace import checks and passed all 82 backend tests inside Linux.
- Application Python dependencies and frontend dependencies reported no known vulnerabilities in local audits.

These checks establish application behavior with test doubles for inference. They do not establish OCR accuracy, biometric accuracy, spoof resistance, fairness, production KYC compliance or GPU compatibility. Real model evaluation and licensed model assets are still required. The default heuristic liveness path routes otherwise eligible applications to manual review.

The synthetic OCR runner uses the current EasyOCR provider. Superseded TrOCR reports were removed. See [specimen instructions](samples/README.md). This smoke check is not an accuracy benchmark.

Changes are local on `feature/verification-platform-upgrade`; they have not been pushed to GitHub.
