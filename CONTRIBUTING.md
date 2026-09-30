# Contributing

Keep examples, tests, screenshots and bug reports synthetic. Never commit identity documents, face images, credentials, model weights or upload directories.

1. Create a branch for your change.
2. Explain the problem and resulting behavior in the pull request.
3. Run the checks documented in the README. Verification changes should test missing evidence and model failures, not just the happy path.
4. For schema changes, add an Alembic migration and test it on a dedicated database.
5. Record model assumptions and limitations. Do not present a synthetic demo score as measured accuracy.

The public demo must run without backend services or authentication. Preserve the one-way separation between illustrative fixtures and the real verification API.
