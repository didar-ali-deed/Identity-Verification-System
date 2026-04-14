import { useState } from "react";
import type { PipelineResult, PipelineStageResult, PipelineFlag, PipelineReasonCode } from "@/types";
import ChannelScoresChart from "./ChannelScoresChart";
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Shield,
  Activity,
  Fingerprint,
  FileSearch,
  Scale,
  Gavel,
  FileCheck,
  Eye,
  Scan,
  Database,
} from "lucide-react";

const STAGE_META: { name: string; icon: typeof Shield }[] = [
  { name: "Document Acceptance", icon: FileCheck },
  { name: "Liveness & Anti-Spoofing", icon: Eye },
  { name: "Field Extraction", icon: Scan },
  { name: "Normalization & Consistency", icon: Database },
  { name: "Watchlist & Fraud Checks", icon: Shield },
  { name: "Similarity Channels", icon: Fingerprint },
  { name: "Weighted Scoring", icon: Activity },
  { name: "Hard-Rule Overrides", icon: Gavel },
  { name: "Decision Matrix", icon: Scale },
  { name: "Result & Audit Trail", icon: FileSearch },
];

interface PipelineBreakdownProps {
  result: PipelineResult;
}

export default function PipelineBreakdown({ result }: PipelineBreakdownProps) {
  const stages: (PipelineStageResult | null)[] = [
    result.stage_0_result,
    result.stage_1_result,
    result.stage_2_result,
    result.stage_3_result,
    result.stage_4_result,
    null,
    null,
    result.hard_rules_result as PipelineStageResult | null,
    null,
    null,
  ];

  return (
    <div className="space-y-5">
      {/* Decision Badge */}
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold text-foreground">
          Pipeline{" "}
          <span
            className="text-muted-foreground"
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            v{result.pipeline_version}
          </span>
        </h3>
        <DecisionBadge decision={result.final_decision} />
      </div>

      {/* 10-Stage Stepper */}
      <div className="bg-card border border-border rounded-xl p-5">
        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-4">
          Stage Progression
        </h4>
        <div className="space-y-1.5">
          {STAGE_META.map((meta, i) => (
            <StageStep
              key={i}
              stageNum={i}
              meta={meta}
              stageResult={stages[i]}
              channelScores={i === 5 ? result.channel_scores : undefined}
              weightedTotal={i === 6 ? result.weighted_total : undefined}
              finalDecision={i === 8 ? result.final_decision : undefined}
              decisionOverride={i === 7 ? result.decision_override : undefined}
            />
          ))}
        </div>
      </div>

      {/* Channel Scores Chart */}
      {result.channel_scores && (
        <div className="bg-card border border-border rounded-xl p-5">
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-4">
            Similarity Channel Scores
          </h4>
          <ChannelScoresChart
            scores={result.channel_scores}
            weightedTotal={result.weighted_total}
          />
        </div>
      )}

      {/* Flags & Reason Codes */}
      {((result.flags && result.flags.length > 0) || (result.reason_codes && result.reason_codes.length > 0)) && (
        <div className="bg-card border border-border rounded-xl p-5">
          <CollapsibleSection
            title={`Flags & Reason Codes (${(result.flags?.length ?? 0) + (result.reason_codes?.length ?? 0)})`}
          >
            {result.reason_codes && result.reason_codes.length > 0 && (
              <div className="mb-4 space-y-1.5">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                  Reason Codes
                </p>
                {result.reason_codes.map((rc: PipelineReasonCode, i: number) => (
                  <div
                    key={i}
                    className={`text-xs p-2.5 rounded-lg flex items-start gap-2 border ${
                      rc.severity === "critical"
                        ? "bg-red-500/8 text-red-300 border-red-500/20"
                        : rc.severity === "warning"
                          ? "bg-amber-500/8 text-amber-300 border-amber-500/20"
                          : "bg-muted/50 text-foreground border-border"
                    }`}
                  >
                    {rc.severity === "critical" ? (
                      <XCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                    ) : (
                      <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                    )}
                    <div>
                      <span
                        className="font-semibold"
                        style={{ fontFamily: "JetBrains Mono, monospace" }}
                      >
                        {rc.code}
                      </span>
                      <span className="mx-1 opacity-50">—</span>
                      <span className="opacity-80">{rc.message}</span>
                      <span className="opacity-40 ml-2">(Stage {rc.stage})</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
            {result.flags && result.flags.length > 0 && (
              <div className="space-y-1.5">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                  Flags
                </p>
                {result.flags.map((flag: PipelineFlag, i: number) => (
                  <div
                    key={i}
                    className="text-xs p-2.5 bg-orange-500/8 text-orange-300 border border-orange-500/20 rounded-lg flex items-start gap-2"
                  >
                    <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                    <div>
                      <span className="font-semibold">{flag.flag_type}</span>
                      <span className="mx-1 opacity-50">—</span>
                      <span className="opacity-80">{flag.detail}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CollapsibleSection>
        </div>
      )}

      {/* Timing */}
      {result.started_at && result.completed_at && (
        <p
          className="text-xs text-muted-foreground text-right"
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          {new Date(result.started_at).toLocaleTimeString()} →{" "}
          {new Date(result.completed_at).toLocaleTimeString()} (
          {((new Date(result.completed_at).getTime() - new Date(result.started_at).getTime()) / 1000).toFixed(1)}s)
        </p>
      )}
    </div>
  );
}

function DecisionBadge({ decision }: { decision: string | null }) {
  if (!decision) return null;

  const config = {
    APPROVED: {
      bg: "bg-emerald-500/10",
      text: "text-emerald-400",
      border: "border-emerald-500/25",
      icon: CheckCircle2,
    },
    MANUAL_REVIEW: {
      bg: "bg-amber-500/10",
      text: "text-amber-400",
      border: "border-amber-500/25",
      icon: AlertTriangle,
    },
    REJECTED: {
      bg: "bg-red-500/10",
      text: "text-red-400",
      border: "border-red-500/25",
      icon: XCircle,
    },
  }[decision] ?? {
    bg: "bg-muted",
    text: "text-muted-foreground",
    border: "border-border",
    icon: AlertTriangle,
  };

  const Icon = config.icon;

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-semibold border ${config.bg} ${config.text} ${config.border}`}
    >
      <Icon className="h-4 w-4" />
      {decision.replace("_", " ")}
    </span>
  );
}

function StageStep({
  stageNum,
  meta,
  stageResult,
  channelScores,
  weightedTotal,
  finalDecision,
  decisionOverride,
}: {
  stageNum: number;
  meta: { name: string; icon: typeof Shield };
  stageResult: PipelineStageResult | null;
  channelScores?: PipelineResult["channel_scores"];
  weightedTotal?: number | null;
  finalDecision?: string | null;
  decisionOverride?: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const Icon = meta.icon;

  let status: "passed" | "failed" | "skipped" | "info" = "skipped";
  if (stageResult) {
    status = stageResult.passed ? "passed" : "failed";
  } else if (stageNum === 5 && channelScores) {
    status = "passed";
  } else if (stageNum === 6 && weightedTotal !== undefined && weightedTotal !== null) {
    status = "passed";
  } else if (stageNum === 8 && finalDecision) {
    status = finalDecision === "REJECTED" ? "failed" : "passed";
  } else if (stageNum === 9) {
    status = "info";
  }

  const statusStyles = {
    passed: {
      dot: "bg-emerald-500/10 border-emerald-500/25 text-emerald-400",
      row: "",
    },
    failed: {
      dot: "bg-red-500/10 border-red-500/25 text-red-400",
      row: "bg-red-500/5",
    },
    skipped: {
      dot: "bg-muted border-border text-muted-foreground",
      row: "",
    },
    info: {
      dot: "bg-primary/10 border-primary/25 text-primary",
      row: "",
    },
  };

  const hasDetails =
    stageResult?.details ||
    channelScores ||
    weightedTotal !== undefined ||
    finalDecision ||
    decisionOverride;

  return (
    <div
      className={`border rounded-lg overflow-hidden ${
        status === "failed" ? "border-red-500/20" : "border-border"
      } ${statusStyles[status].row}`}
    >
      <button
        onClick={() => hasDetails && setExpanded(!expanded)}
        className={`w-full flex items-center gap-3 px-3 py-2.5 text-left bg-transparent border-none ${
          hasDetails ? "cursor-pointer hover:bg-muted/20" : "cursor-default"
        } transition-colors`}
      >
        <div
          className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 border ${statusStyles[status].dot}`}
        >
          <Icon className="h-3 w-3" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-foreground">
            <span
              className="text-muted-foreground mr-1.5"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              {stageNum.toString().padStart(2, "0")}
            </span>
            {meta.name}
          </p>
          {stageResult && (
            <p className="text-xs text-muted-foreground mt-0.5" style={{ fontFamily: "JetBrains Mono, monospace" }}>
              {stageResult.duration_ms.toFixed(0)}ms
              {stageResult.flags?.length > 0 && (
                <span className="text-amber-400 ml-2">· {stageResult.flags.length} flag(s)</span>
              )}
            </p>
          )}
          {stageNum === 6 && weightedTotal !== undefined && weightedTotal !== null && (
            <p className="text-xs text-muted-foreground mt-0.5" style={{ fontFamily: "JetBrains Mono, monospace" }}>
              Score:{" "}
              <span className={
                weightedTotal >= 0.90 ? "text-emerald-400" :
                weightedTotal >= 0.75 ? "text-amber-400" :
                "text-red-400"
              }>
                {(weightedTotal * 100).toFixed(2)}%
              </span>
            </p>
          )}
          {stageNum === 8 && finalDecision && (
            <p className="text-xs text-muted-foreground mt-0.5" style={{ fontFamily: "JetBrains Mono, monospace" }}>
              {finalDecision}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {status === "passed" && (
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
          )}
          {status === "failed" && (
            <XCircle className="h-3.5 w-3.5 text-red-400" />
          )}
          {hasDetails &&
            (expanded ? (
              <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
            ))}
        </div>
      </button>
      {expanded && hasDetails && (
        <div className="px-3 pb-3 pt-1 border-t border-border">
          <pre
            className="text-xs bg-muted/40 rounded-lg p-3 overflow-x-auto max-h-56 overflow-y-auto text-foreground/80"
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            {JSON.stringify(
              stageResult?.details ??
                (channelScores
                  ? { channel_scores: channelScores }
                  : {
                      decision: finalDecision,
                      override: decisionOverride,
                      weighted_total: weightedTotal,
                    }),
              null,
              2,
            )}
          </pre>
        </div>
      )}
    </div>
  );
}

function CollapsibleSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(true);

  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3 bg-transparent border-none cursor-pointer p-0 hover:text-foreground transition-colors"
      >
        {open ? (
          <ChevronDown className="h-4 w-4" />
        ) : (
          <ChevronRight className="h-4 w-4" />
        )}
        {title}
      </button>
      {open && children}
    </div>
  );
}
