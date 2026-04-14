import { useIDVStatus, usePipelineResult } from "@/api/idv";
import VerificationStatus from "@/components/VerificationStatus";
import { Link } from "react-router-dom";
import {
  FileCheck,
  FileImage,
  Camera,
  Brain,
  Loader2,
  AlertTriangle,
  Shield,
  Activity,
  Fingerprint,
  Scale,
  Gavel,
  Eye,
  Scan,
  Database,
  FileSearch,
} from "lucide-react";

// Fix: add polling so status auto-updates while pipeline is running
const REFETCH_MS = 5000;

export default function IDVStatus() {
  const { data: application, isLoading, error } = useIDVStatus({
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      // Keep polling while pending or processing
      if (!s || s === "pending" || s === "processing") return REFETCH_MS;
      return false;
    },
  } as Parameters<typeof useIDVStatus>[0]);

  const { data: pipelineData } = usePipelineResult({
    refetchInterval: (query) => {
      // Poll until we have a final decision
      if (query.state.data?.pipeline_decision) return false;
      if (!application || application.status === "approved" || application.status === "rejected") return false;
      return REFETCH_MS;
    },
  } as Parameters<typeof usePipelineResult>[0]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (error) {
    const is404 = (error as { response?: { status?: number } }).response?.status === 404;
    if (is404) {
      return (
        <div className="max-w-lg mx-auto text-center py-20">
          <div className="w-16 h-16 rounded-2xl bg-muted border border-border flex items-center justify-center mx-auto mb-5">
            <FileCheck className="h-8 w-8 text-muted-foreground" />
          </div>
          <h1 className="text-2xl font-bold text-foreground">No Application Found</h1>
          <p className="text-muted-foreground mt-2 text-sm">
            You haven&apos;t submitted an IDV application yet.
          </p>
          <Link
            to="/idv"
            className="inline-block mt-6 px-6 py-2.5 bg-primary text-white rounded-xl text-sm font-semibold hover:bg-primary/90 no-underline btn-glow transition-all"
          >
            Start Verification
          </Link>
        </div>
      );
    }
    return (
      <div className="text-center py-24">
        <AlertTriangle className="h-12 w-12 text-destructive mx-auto mb-4" />
        <p className="text-foreground font-medium">Failed to load status</p>
        <p className="text-sm text-muted-foreground mt-1">Please try again later</p>
      </div>
    );
  }

  if (!application) {
    return (
      <div className="max-w-lg mx-auto text-center py-20">
        <div className="w-16 h-16 rounded-2xl bg-muted border border-border flex items-center justify-center mx-auto mb-5">
          <FileCheck className="h-8 w-8 text-muted-foreground" />
        </div>
        <h1 className="text-2xl font-bold text-foreground">No Application Found</h1>
        <p className="text-muted-foreground mt-2 text-sm">
          You haven&apos;t submitted an IDV application yet.
        </p>
        <Link
          to="/idv"
          className="inline-block mt-6 px-6 py-2.5 bg-primary text-white rounded-xl text-sm font-semibold hover:bg-primary/90 no-underline btn-glow transition-all"
        >
          Start Verification
        </Link>
      </div>
    );
  }

  const hasFaceMatch = application.face_match_score !== null;
  const hasPipeline  =
    pipelineData?.pipeline_version !== null && pipelineData?.pipeline_version !== undefined;

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center">
            <FileCheck className="h-5 w-5 text-primary" />
          </div>
          <h1 className="text-xl font-bold text-foreground">Application Status</h1>
        </div>
        <VerificationStatus status={application.status} />
      </div>

      {/* Application Info */}
      <div className="bg-card border border-border rounded-xl p-5">
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Application ID</p>
            <p
              className="text-foreground text-xs"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              {application.id.slice(0, 8).toUpperCase()}…
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Submitted</p>
            <p className="text-foreground text-xs">
              {new Date(application.submitted_at).toLocaleDateString("en-US", {
                year: "numeric", month: "short", day: "numeric",
                hour: "2-digit", minute: "2-digit",
              })}
            </p>
          </div>
          {application.reviewed_at && (
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Reviewed</p>
              <p className="text-foreground text-xs">
                {new Date(application.reviewed_at).toLocaleDateString("en-US", {
                  year: "numeric", month: "short", day: "numeric",
                  hour: "2-digit", minute: "2-digit",
                })}
              </p>
            </div>
          )}
          {application.rejection_reason && (
            <div className="col-span-2">
              <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Rejection Reason</p>
              <p className="text-red-400 text-sm">{application.rejection_reason}</p>
            </div>
          )}
        </div>
      </div>

      {/* Progress Steps */}
      <div className="bg-card border border-border rounded-xl p-5">
        <h2 className="text-sm font-semibold text-foreground mb-4">Verification Progress</h2>
        <div className="space-y-4">
          <ProgressItem
            icon={FileImage} title="Document Upload"
            done={application.documents.length > 0}
            detail={application.documents.length > 0
              ? `${application.documents[0].doc_type.replace("_", " ")} uploaded`
              : "Awaiting document"}
          />
          <ProgressItem
            icon={Camera} title="Selfie Capture"
            done={hasFaceMatch}
            detail={hasFaceMatch ? "Selfie captured" : "Awaiting selfie"}
          />
          <ProgressItem
            icon={Brain} title="AI Processing"
            done={application.status !== "pending" && application.status !== "processing"}
            processing={application.status === "processing"}
            detail={
              application.status === "processing"
                ? "Running OCR, face match, and fraud detection..."
                : application.status === "pending"
                  ? "Waiting to start"
                  : "Processing complete"
            }
          />
          <ProgressItem
            icon={FileCheck} title="Admin Review"
            done={application.status === "approved" || application.status === "rejected"}
            detail={
              application.status === "approved" ? "Application approved" :
              application.status === "rejected" ? "Application rejected" :
              "Awaiting review"
            }
          />
        </div>
      </div>

      {/* Pipeline stage progress */}
      {hasPipeline && pipelineData && (
        <div className="bg-card border border-border rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-foreground">Pipeline Verification</h2>
            {pipelineData.pipeline_decision && (
              <span
                className={`px-2.5 py-1 rounded-full text-xs font-semibold ${
                  pipelineData.pipeline_decision === "APPROVED"
                    ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/25"
                    : pipelineData.pipeline_decision === "MANUAL_REVIEW"
                      ? "bg-amber-500/10 text-amber-400 border border-amber-500/25"
                      : "bg-red-500/10 text-red-400 border border-red-500/25"
                }`}
              >
                {pipelineData.pipeline_decision.replace("_", " ")}
              </span>
            )}
          </div>

          {pipelineData.weighted_total !== null && (
            <div className="mb-5">
              <div className="flex items-center justify-between text-sm mb-2">
                <span className="text-xs text-muted-foreground uppercase tracking-wider">
                  Verification Score
                </span>
                <span
                  className={`font-bold text-base ${
                    pipelineData.weighted_total >= 0.87 ? "text-emerald-400" :
                    pipelineData.weighted_total >= 0.70 ? "text-amber-400" :
                    "text-red-400"
                  }`}
                  style={{ fontFamily: "JetBrains Mono, monospace" }}
                >
                  {(pipelineData.weighted_total * 100).toFixed(1)}%
                </span>
              </div>
              <div className="w-full bg-muted rounded-full h-2">
                <div
                  className={`h-2 rounded-full transition-all progress-bar-glow ${
                    pipelineData.weighted_total >= 0.87 ? "bg-emerald-500" :
                    pipelineData.weighted_total >= 0.70 ? "bg-amber-500" :
                    "bg-red-500"
                  }`}
                  style={{ width: `${Math.min(pipelineData.weighted_total * 100, 100)}%` }}
                />
              </div>
            </div>
          )}

          <div className="grid grid-cols-5 gap-1.5">
            {[
              { label: "Accept",    icon: FileCheck  },
              { label: "Liveness",  icon: Eye        },
              { label: "Extract",   icon: Scan       },
              { label: "Normalize", icon: Database   },
              { label: "Watchlist", icon: Shield     },
              { label: "Similarity",icon: Fingerprint},
              { label: "Scoring",   icon: Activity   },
              { label: "Rules",     icon: Gavel      },
              { label: "Decision",  icon: Scale      },
              { label: "Result",    icon: FileSearch },
            ].map((stage, i) => {
              const StageIcon = stage.icon;
              // Fix: each stage is "done" based on pipeline having a decision (all passed)
              // vs "active" when no decision yet. Not all green on failure.
              const isDone = pipelineData.pipeline_decision !== null;
              const isApproved = pipelineData.pipeline_decision === "APPROVED";
              return (
                <div
                  key={i}
                  className={`flex flex-col items-center gap-1 p-2 rounded-lg text-center transition-all ${
                    isDone && isApproved
                      ? "bg-emerald-500/8 border border-emerald-500/15"
                      : isDone
                        ? "bg-amber-500/8 border border-amber-500/15"
                        : "bg-muted border border-border"
                  }`}
                >
                  <StageIcon
                    className={`h-3.5 w-3.5 ${
                      isDone && isApproved ? "text-emerald-400" :
                      isDone ? "text-amber-400" :
                      "text-muted-foreground"
                    }`}
                  />
                  <span className="text-[9px] leading-tight text-muted-foreground">
                    {stage.label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Documents */}
      {application.documents.length > 0 && (
        <div className="bg-card border border-border rounded-xl p-5">
          <h2 className="text-sm font-semibold text-foreground mb-4">Documents</h2>
          <div className="space-y-2">
            {application.documents.map((doc) => (
              <div
                key={doc.id}
                className="flex items-center justify-between p-3 bg-muted/50 rounded-xl"
              >
                <div className="flex items-center gap-3">
                  <FileImage className="h-4 w-4 text-muted-foreground shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-foreground capitalize">
                      {doc.doc_type.replace("_", " ")}
                    </p>
                    <p className="text-xs text-muted-foreground">{doc.original_filename}</p>
                  </div>
                </div>
                <div className="text-right text-xs space-y-0.5">
                  {doc.fraud_score !== null && (
                    <p className={doc.fraud_score > 0.7 ? "text-red-400 font-medium" : "text-emerald-400 font-medium"}>
                      Fraud: {(doc.fraud_score * 100).toFixed(0)}%
                    </p>
                  )}
                  {doc.ocr_data && <p className="text-muted-foreground">OCR complete</p>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ProgressItem({
  icon: Icon, title, done, processing = false, detail,
}: {
  icon: typeof FileImage;
  title: string;
  done: boolean;
  processing?: boolean;
  detail: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <div
        className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
          done
            ? "bg-emerald-500/10 border border-emerald-500/25"
            : processing
              ? "bg-blue-500/10 border border-blue-500/25"
              : "bg-muted border border-border"
        }`}
      >
        <Icon
          className={`h-4 w-4 ${
            done ? "text-emerald-400" : processing ? "text-blue-400 animate-pulse" : "text-muted-foreground"
          }`}
        />
      </div>
      <div>
        <p className="text-sm font-medium text-foreground">{title}</p>
        <p className="text-xs text-muted-foreground">{detail}</p>
      </div>
    </div>
  );
}
