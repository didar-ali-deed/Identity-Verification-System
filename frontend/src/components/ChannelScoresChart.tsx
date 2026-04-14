import type { PipelineChannelScores } from "@/types";

const CHANNEL_CONFIG = [
  { key: "channel_a" as const, label: "A: Biometric Face", weight: 0.40, color: "bg-blue-500", glow: "shadow-blue-500/30" },
  { key: "channel_b" as const, label: "B: ID Number Match", weight: 0.25, color: "bg-indigo-500", glow: "shadow-indigo-500/30" },
  { key: "channel_c" as const, label: "C: Name Similarity", weight: 0.15, color: "bg-violet-500", glow: "shadow-violet-500/30" },
  { key: "channel_d" as const, label: "D: Father Name", weight: 0.10, color: "bg-purple-500", glow: "shadow-purple-500/30" },
  { key: "channel_e" as const, label: "E: DOB Match", weight: 0.10, color: "bg-fuchsia-500", glow: "shadow-fuchsia-500/30" },
];

interface ChannelScoresChartProps {
  scores: PipelineChannelScores;
  weightedTotal: number | null;
}

export default function ChannelScoresChart({ scores, weightedTotal }: ChannelScoresChartProps) {
  return (
    <div className="space-y-4">
      {CHANNEL_CONFIG.map(({ key, label, weight, color }) => {
        const score = scores[key];
        const pct = score !== null && score !== undefined ? score * 100 : 0;
        const contribution = score !== null && score !== undefined ? score * weight : 0;

        return (
          <div key={key}>
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-foreground">{label}</span>
                <span className="text-xs text-muted-foreground px-1.5 py-0.5 bg-muted rounded-full">
                  ×{weight}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-muted-foreground">
                  +{(contribution * 100).toFixed(1)}%
                </span>
                <span
                  className={`font-bold text-sm ${
                    pct >= 75 ? "text-emerald-400" : pct >= 50 ? "text-amber-400" : "text-red-400"
                  }`}
                  style={{ fontFamily: "JetBrains Mono, monospace" }}
                >
                  {pct.toFixed(1)}%
                </span>
              </div>
            </div>
            <div className="w-full bg-muted rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all ${color}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })}

      {weightedTotal !== null && (
        <div className="pt-4 mt-2 border-t border-border">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-semibold text-foreground uppercase tracking-wider">
              Weighted Total
            </span>
            <span
              className={`text-xl font-bold ${
                weightedTotal >= 0.90 ? "text-emerald-400" :
                weightedTotal >= 0.75 ? "text-amber-400" :
                "text-red-400"
              }`}
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              {(weightedTotal * 100).toFixed(2)}%
            </span>
          </div>
          <div className="w-full bg-muted rounded-full h-3">
            <div
              className={`h-3 rounded-full transition-all ${
                weightedTotal >= 0.90 ? "bg-emerald-500" :
                weightedTotal >= 0.75 ? "bg-amber-500" :
                "bg-red-500"
              }`}
              style={{ width: `${Math.min(weightedTotal * 100, 100)}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-muted-foreground mt-1.5">
            <span>Reject &lt;75%</span>
            <span>Review 75–90%</span>
            <span>Pass ≥90%</span>
          </div>
        </div>
      )}
    </div>
  );
}
