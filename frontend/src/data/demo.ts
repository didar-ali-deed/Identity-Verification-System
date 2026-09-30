import type { PipelineResult, PipelineStageResult, PipelineFlag, PipelineReasonCode } from "@/types";

export const scenarios = [
  { id: "approved", title: "Consistent identity", description: "Complete evidence and matching identity fields." },
  { id: "review", title: "OCR needs review", description: "The name was read with low confidence." },
  { id: "rejected", title: "Identity mismatch", description: "Document identity numbers disagree, overriding a strong score." },
  { id: "unavailable", title: "Liveness unavailable", description: "A model failure blocks approval regardless of other scores." },
] as const;
export type Scenario = typeof scenarios[number]["id"];

export function demoResult(scenario: Scenario): PipelineResult {
  const failedLiveness = scenario === "unavailable";
  const rejected = scenario === "rejected" || failedLiveness;
  const review = scenario === "review";
  const decision = rejected ? "REJECTED" : review ? "MANUAL_REVIEW" : "APPROVED";
  const override = rejected ? "hard_reject" : review ? "manual_review" : null;
  const scores = { channel_a: 0.96, channel_b: scenario === "rejected" ? 0 : 1, channel_c: 0.98, channel_d: 0.94, channel_e: 1 };
  const total = failedLiveness ? 0 : scores.channel_a * 0.4 + scores.channel_b * 0.25 + scores.channel_c * 0.15 + scores.channel_d * 0.1 + scores.channel_e * 0.1;
  const flags: PipelineFlag[] = scenario === "approved" ? [] : [{
    flag_type: failedLiveness ? "selfie_liveness_fail" : review ? "low_ocr_confidence" : "id_mismatch",
    detail: failedLiveness ? "Passive liveness model unavailable" : review ? "Full name confidence 0.62 requires review" : "Identity numbers do not match",
  }];
  const reasons: PipelineReasonCode[] = flags.map(flag => ({
    code: flag.flag_type.toUpperCase(), stage: failedLiveness ? 1 : review ? 2 : 5,
    severity: review ? "warning" : "critical", message: flag.detail,
  }));
  const stage = (index: number, name: string, details: Record<string, unknown>, passed = true): PipelineStageResult => ({
    stage: index, name, details, passed, hard_fail: index === 1 && failedLiveness,
    flags: reasons.some(reason => reason.stage === index) ? flags : [],
    reason_codes: reasons.filter(reason => reason.stage === index), duration_ms: 120 + index * 25,
  });
  const stages = [
    stage(0, "Document Acceptance", { passport_class: "TD3", id_class: "TD1", issuing_country: "PAK", eligible: true }),
    stage(1, "Liveness & Anti-Spoofing", { selfie_liveness: {
      is_live: !failedLiveness, verified: !failedLiveness, provider: "minifasnet", frame_count: 3,
      frame_scores: failedLiveness ? [] : [0.94, 0.97, 0.96], detail: failedLiveness ? "Model unavailable" : "All frames passed",
    } }, !failedLiveness),
    ...(!failedLiveness ? [
      stage(2, "Field Extraction", { passport_mrz: { full_name: "ALEX SAMPLE", document_number: "DEMO-PASSPORT-001" },
        id_front: { full_name: "ALEX SAMPLE", national_id_number: "DEMO-ID-001" }, full_name_confidence: review ? 0.62 : 0.97 }),
      stage(3, "Normalization & Consistency", { names_consistent: true, dob_consistent: true, expiry_verified: true }),
      stage(4, "Watchlist & Fraud Checks", { watchlist_hit: false, duplicate: false, velocity_exceeded: false }),
      stage(5, "Similarity Channels", { channel_a_biometric: { verified: true, comparisons: {
        selfie_vs_passport: { verified: true, similarity: 0.98 }, selfie_vs_national_id: { verified: true, similarity: 0.96 },
      } }, identity_number_match: scenario !== "rejected" }),
      stage(6, "Weighted Scoring", { weighted_total: total, weights: { A: 0.4, B: 0.25, C: 0.15, D: 0.1, E: 0.1 } }),
    ] : []),
    stage(7, "Hard-Rule Overrides", { override, triggered_rules: flags }, !rejected),
    stage(8, "Decision Matrix", { final_decision: decision, pass_threshold: 0.9, review_threshold: 0.75,
      decision_basis: override ? `Override: ${override}` : "All evidence gates passed; weighted score exceeds threshold" }, !rejected),
    stage(9, "Result & Audit Trail", { synthetic: true, persisted: false, detail: "Illustrative fixture; no verification performed" }),
  ];
  return {
    id: `demo-${scenario}`, pipeline_version: "2.0", stage_results: stages,
    stage_0_result: stages[0], stage_1_result: stages[1],
    stage_2_result: stages.find(s => s.stage === 2) ?? null, stage_3_result: stages.find(s => s.stage === 3) ?? null,
    stage_4_result: stages.find(s => s.stage === 4) ?? null, channel_scores: failedLiveness ? null : scores,
    weighted_total: failedLiveness ? null : total, hard_rules_result: stages.find(s => s.stage === 7)?.details ?? null,
    decision_override: override, final_decision: decision, flags, reason_codes: reasons,
    started_at: "2026-01-01T10:00:00Z", completed_at: "2026-01-01T10:00:03Z",
  };
}
