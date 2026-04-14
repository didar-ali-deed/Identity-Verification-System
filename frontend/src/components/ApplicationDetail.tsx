import { useState } from "react";
import type { ApplicationDetail as ApplicationDetailType } from "@/types";
import { useReviewApplication } from "@/api/admin";
import PipelineBreakdown from "./PipelineBreakdown";
import VerificationStatus from "./VerificationStatus";
import {
  ArrowLeft,
  FileImage,
  Camera,
  Brain,
  Shield,
  CheckCircle2,
  XCircle,
  Loader2,
  User,
} from "lucide-react";

interface ApplicationDetailProps {
  application: ApplicationDetailType;
  onBack: () => void;
}

export default function ApplicationDetail({
  application,
  onBack,
}: ApplicationDetailProps) {
  const [rejectReason, setRejectReason] = useState("");
  const [showRejectForm, setShowRejectForm] = useState(false);
  // Local reviewed state avoids stale isSuccess from mutation persisting across selections
  const [reviewed, setReviewed] = useState(false);
  const review = useReviewApplication();

  const handleApprove = () => {
    review.mutate(
      { id: application.id, action: "approve" },
      { onSuccess: () => setReviewed(true) },
    );
  };

  const handleReject = () => {
    if (rejectReason.length < 10) return;
    review.mutate(
      { id: application.id, action: "reject", reason: rejectReason },
      { onSuccess: () => setReviewed(true) },
    );
  };

  const doc = application.documents[0];
  const canReview =
    application.status === "ready_for_review" ||
    application.status === "pending";

  return (
    <div>
      <button
        onClick={onBack}
        className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-5 cursor-pointer bg-transparent border-none transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to list
      </button>

      {/* Header */}
      <div className="flex items-start justify-between mb-6 gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h2
              className="text-lg font-bold text-foreground"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              {application.id.slice(0, 8).toUpperCase()}
            </h2>
          </div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <User className="h-3.5 w-3.5" />
            <span>{application.user_full_name}</span>
            <span className="text-border">·</span>
            <span>{application.user_email}</span>
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Submitted{" "}
            {new Date(application.submitted_at).toLocaleDateString("en-US", {
              year: "numeric",
              month: "long",
              day: "numeric",
            })}
          </p>
        </div>
        <VerificationStatus status={application.status} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Document Info */}
        {doc && (
          <div className="bg-card border border-border rounded-xl p-5">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-7 h-7 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center">
                <FileImage className="h-3.5 w-3.5 text-primary" />
              </div>
              <h3 className="text-sm font-semibold text-foreground">Document</h3>
            </div>
            <div className="space-y-2.5 text-sm">
              <InfoRow label="Type" value={doc.doc_type.replace("_", " ")} />
              <InfoRow label="File" value={doc.original_filename} />
              <InfoRow
                label="Size"
                value={`${(doc.file_size / 1024).toFixed(0)} KB`}
              />
              {doc.ocr_data && (
                <div className="pt-3 border-t border-border">
                  <div className="flex items-center gap-1.5 mb-2">
                    <Brain className="h-3.5 w-3.5 text-primary" />
                    <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                      OCR Extracted Data
                    </p>
                  </div>
                  <div className="bg-muted/40 rounded-lg p-3 space-y-2">
                    {Object.entries(doc.ocr_data).map(([key, value]) => (
                      <InfoRow
                        key={key}
                        label={key.replace(/_/g, " ")}
                        value={String(value)}
                        mono
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Fraud Analysis */}
        {doc && doc.fraud_score !== null && (
          <div className="bg-card border border-border rounded-xl p-5">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-7 h-7 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center">
                <Shield className="h-3.5 w-3.5 text-primary" />
              </div>
              <h3 className="text-sm font-semibold text-foreground">Fraud Analysis</h3>
            </div>
            <div className="mb-4">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs text-muted-foreground uppercase tracking-wider">
                  Overall Score
                </span>
                <span
                  className={`text-xl font-bold ${
                    doc.fraud_score > 0.7
                      ? "text-red-400"
                      : doc.fraud_score > 0.4
                        ? "text-amber-400"
                        : "text-emerald-400"
                  }`}
                  style={{ fontFamily: "JetBrains Mono, monospace" }}
                >
                  {(doc.fraud_score * 100).toFixed(0)}%
                </span>
              </div>
              <div className="w-full bg-muted rounded-full h-2">
                <div
                  className={`h-2 rounded-full transition-all ${
                    doc.fraud_score > 0.7
                      ? "bg-red-500"
                      : doc.fraud_score > 0.4
                        ? "bg-amber-500"
                        : "bg-emerald-500"
                  }`}
                  style={{ width: `${doc.fraud_score * 100}%` }}
                />
              </div>
            </div>
            {doc.fraud_details?.checks && (
              <div className="space-y-1.5">
                {doc.fraud_details.checks.map((check) => (
                  <div
                    key={check.name}
                    className="flex items-center justify-between text-xs p-2 bg-muted/40 rounded-lg"
                  >
                    <span className="text-foreground">{check.name}</span>
                    <span
                      className={
                        check.score > 0.7
                          ? "text-red-400 font-semibold"
                          : "text-muted-foreground"
                      }
                      style={{ fontFamily: "JetBrains Mono, monospace" }}
                    >
                      {(check.score * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Face Verification */}
        {application.face_match_score !== null && (
          <div className="bg-card border border-border rounded-xl p-5">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-7 h-7 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center">
                <Camera className="h-3.5 w-3.5 text-primary" />
              </div>
              <h3 className="text-sm font-semibold text-foreground">Face Verification</h3>
            </div>
            <div className="space-y-3">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs text-muted-foreground uppercase tracking-wider">
                    Similarity
                  </span>
                  <span
                    className={`text-xl font-bold ${
                      application.face_is_match ? "text-emerald-400" : "text-red-400"
                    }`}
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    {(application.face_match_score * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="w-full bg-muted rounded-full h-2">
                  <div
                    className={`h-2 rounded-full transition-all ${
                      application.face_is_match ? "bg-emerald-500" : "bg-red-500"
                    }`}
                    style={{ width: `${application.face_match_score * 100}%` }}
                  />
                </div>
              </div>
              <InfoRow
                label="Match"
                value={
                  application.face_is_match === null
                    ? "Pending"
                    : application.face_is_match
                      ? "Yes"
                      : "No"
                }
                valueColor={
                  application.face_is_match === null
                    ? ""
                    : application.face_is_match
                      ? "text-emerald-400"
                      : "text-red-400"
                }
              />
            </div>
          </div>
        )}

        {/* Review Actions */}
        {canReview && (
          <div className="bg-card border border-border rounded-xl p-5">
            <h3 className="text-sm font-semibold text-foreground mb-4">Review Actions</h3>
            {reviewed ? (
              <div className="text-center py-5">
                <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/25 flex items-center justify-center mx-auto mb-3">
                  <CheckCircle2 className="h-6 w-6 text-emerald-400" />
                </div>
                <p className="text-sm font-medium text-foreground">
                  Review submitted
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                <button
                  onClick={handleApprove}
                  disabled={review.isPending}
                  className="w-full py-2.5 bg-emerald-500/15 text-emerald-400 border border-emerald-500/25 rounded-xl text-sm font-semibold hover:bg-emerald-500/25 disabled:opacity-50 flex items-center justify-center gap-2 cursor-pointer transition-all"
                >
                  {review.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <CheckCircle2 className="h-4 w-4" />
                  )}
                  Approve
                </button>

                {!showRejectForm ? (
                  <button
                    onClick={() => setShowRejectForm(true)}
                    className="w-full py-2.5 bg-red-500/10 text-red-400 border border-red-500/20 rounded-xl text-sm font-semibold hover:bg-red-500/20 cursor-pointer transition-all"
                  >
                    <XCircle className="h-4 w-4 inline mr-2" />
                    Reject
                  </button>
                ) : (
                  <div className="space-y-3">
                    <textarea
                      value={rejectReason}
                      onChange={(e) => setRejectReason(e.target.value)}
                      placeholder="Rejection reason (min 10 characters)..."
                      rows={3}
                      className="w-full px-3 py-2 bg-muted border border-border rounded-xl text-sm text-foreground placeholder:text-muted-foreground resize-none focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/40 transition-all"
                    />
                    <div className="flex gap-2">
                      <button
                        onClick={() => setShowRejectForm(false)}
                        className="flex-1 py-2 bg-muted text-muted-foreground border border-border rounded-xl text-sm hover:text-foreground cursor-pointer transition-colors"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleReject}
                        disabled={rejectReason.length < 10 || review.isPending}
                        className="flex-1 py-2 bg-red-500/15 text-red-400 border border-red-500/25 rounded-xl text-sm font-semibold hover:bg-red-500/25 disabled:opacity-40 cursor-pointer transition-all"
                      >
                        Confirm Reject
                      </button>
                    </div>
                  </div>
                )}

                {review.isError && (
                  <p className="text-xs text-red-400">
                    Failed to submit review. Please try again.
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Pipeline Breakdown */}
      {application.pipeline_result && (
        <div className="mt-5">
          <PipelineBreakdown result={application.pipeline_result} />
        </div>
      )}

      {/* Rejection reason */}
      {application.rejection_reason && (
        <div className="mt-5 bg-red-500/8 border border-red-500/20 rounded-xl p-4">
          <p className="text-xs font-semibold text-red-400 uppercase tracking-wider mb-1">
            Rejection Reason
          </p>
          <p className="text-sm text-red-300">{application.rejection_reason}</p>
        </div>
      )}
    </div>
  );
}

function InfoRow({
  label,
  value,
  mono = false,
  valueColor,
}: {
  label: string;
  value: string;
  mono?: boolean;
  valueColor?: string;
}) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-xs text-muted-foreground capitalize shrink-0">{label}</span>
      <span
        className={`text-xs font-medium truncate ${valueColor ?? "text-foreground"}`}
        style={mono ? { fontFamily: "JetBrains Mono, monospace" } : undefined}
      >
        {value}
      </span>
    </div>
  );
}
