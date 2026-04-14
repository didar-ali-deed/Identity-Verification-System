"""God-Level Identity Verification Pipeline.

10-stage forensic-grade verification pipeline:
  Stage 0: Document Acceptance & National Validity Gate
  Stage 1: Document Liveness & Anti-Spoofing
  Stage 2: Field Extraction (Dual-Zone, Dual-Document)
  Stage 3: Normalization & Cross-Zone Consistency
  Stage 4: Internal Fraud & Watchlist Checks
  Stage 5: Similarity Extraction (5 Channels)
  Stage 6: Weighted Score Synthesis
  Stage 7: Hard-Rule Override Layer
  Stage 8: Decision Matrix
  Stage 9: Result Object & Audit Trail
"""

from app.services.pipeline.orchestrator import run_pipeline

__all__ = ["run_pipeline"]
