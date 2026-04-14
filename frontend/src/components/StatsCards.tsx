import type { StatsResponse } from "@/types";
import {
  Users,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  BarChart3,
} from "lucide-react";

interface StatsCardsProps {
  stats: StatsResponse;
}

export default function StatsCards({ stats }: StatsCardsProps) {
  const cards = [
    {
      label: "Total",
      value: stats.total_applications,
      icon: Users,
      color: "text-primary",
      bg: "bg-primary/10",
      border: "border-primary/20",
    },
    {
      label: "Pending Review",
      value: stats.pending + stats.ready_for_review,
      icon: Clock,
      color: "text-amber-400",
      bg: "bg-amber-500/10",
      border: "border-amber-500/20",
    },
    {
      label: "Approved",
      value: stats.approved,
      icon: CheckCircle2,
      color: "text-emerald-400",
      bg: "bg-emerald-500/10",
      border: "border-emerald-500/20",
    },
    {
      label: "Rejected",
      value: stats.rejected,
      icon: XCircle,
      color: "text-red-400",
      bg: "bg-red-500/10",
      border: "border-red-500/20",
    },
    {
      label: "Processing",
      value: stats.processing,
      icon: BarChart3,
      color: "text-blue-400",
      bg: "bg-blue-500/10",
      border: "border-blue-500/20",
    },
    {
      label: "Fraud Rate",
      value:
        stats.fraud_flag_rate !== null
          ? `${(stats.fraud_flag_rate * 100).toFixed(1)}%`
          : "N/A",
      icon: AlertTriangle,
      color: "text-orange-400",
      bg: "bg-orange-500/10",
      border: "border-orange-500/20",
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
      {cards.map((card) => (
        <div
          key={card.label}
          className="bg-card border border-border rounded-xl p-4 relative overflow-hidden"
        >
          <div
            className={`w-8 h-8 rounded-lg ${card.bg} border ${card.border} flex items-center justify-center mb-3`}
          >
            <card.icon className={`h-4 w-4 ${card.color}`} />
          </div>
          <p
            className="text-2xl font-bold text-foreground"
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            {card.value}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">{card.label}</p>
        </div>
      ))}
    </div>
  );
}
