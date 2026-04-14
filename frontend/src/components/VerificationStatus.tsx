import type { ApplicationStatus } from "@/types";
import { Clock, Loader2, Eye, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

interface VerificationStatusProps {
  status: ApplicationStatus;
  className?: string;
}

const statusConfig: Record<
  ApplicationStatus,
  { label: string; classes: string; icon: typeof Clock }
> = {
  pending: {
    label: "Pending",
    classes: "bg-amber-500/10 text-amber-400 border border-amber-500/25",
    icon: Clock,
  },
  processing: {
    label: "Processing",
    classes: "bg-blue-500/10 text-blue-400 border border-blue-500/25",
    icon: Loader2,
  },
  ready_for_review: {
    label: "Ready for Review",
    classes: "bg-violet-500/10 text-violet-400 border border-violet-500/25",
    icon: Eye,
  },
  approved: {
    label: "Approved",
    classes: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/25",
    icon: CheckCircle2,
  },
  rejected: {
    label: "Rejected",
    classes: "bg-red-500/10 text-red-400 border border-red-500/25",
    icon: XCircle,
  },
  error: {
    label: "Error",
    classes: "bg-orange-500/10 text-orange-400 border border-orange-500/25",
    icon: AlertTriangle,
  },
};

export default function VerificationStatus({
  status,
  className,
}: VerificationStatusProps) {
  const config = statusConfig[status];
  const Icon = config.icon;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium",
        config.classes,
        className,
      )}
    >
      <Icon className={cn("h-3 w-3", status === "processing" && "animate-spin")} />
      {config.label}
    </span>
  );
}
