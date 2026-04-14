import { useState } from "react";
import {
  useAdminStats,
  useApplications,
  useApplicationDetail,
} from "@/api/admin";
import StatsCards from "@/components/StatsCards";
import ApplicationsTable from "@/components/ApplicationsTable";
import ApplicationDetail from "@/components/ApplicationDetail";
import type { ApplicationStatus } from "@/types";
import { LayoutDashboard, Loader2, AlertTriangle } from "lucide-react";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from "recharts";

const STATUS_COLORS: Record<string, string> = {
  pending:         "#f59e0b",
  processing:      "#3b82f6",
  ready_for_review:"#a855f7",
  approved:        "#10b981",
  rejected:        "#ef4444",
  error:           "#f97316",
};

export default function AdminDashboard() {
  const [page, setPage]           = useState(1);
  const [statusFilter, setStatusFilter] = useState<ApplicationStatus | undefined>();
  const [selectedAppId, setSelectedAppId] = useState<string | null>(null);

  const stats        = useAdminStats();
  const applications = useApplications(page, 10, statusFilter);
  const selectedApp  = useApplicationDetail(selectedAppId ?? "");

  if (stats.isLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (stats.isError) {
    return (
      <div className="text-center py-24">
        <AlertTriangle className="h-12 w-12 text-destructive mx-auto mb-4" />
        <p className="text-foreground font-medium">Failed to load dashboard</p>
      </div>
    );
  }

  if (selectedAppId && selectedApp.data) {
    return (
      <ApplicationDetail
        application={selectedApp.data}
        onBack={() => setSelectedAppId(null)}
      />
    );
  }

  const pieData = stats.data
    ? [
        { name: "Pending",    value: stats.data.pending,          color: STATUS_COLORS.pending },
        { name: "Processing", value: stats.data.processing,       color: STATUS_COLORS.processing },
        { name: "Review",     value: stats.data.ready_for_review, color: STATUS_COLORS.ready_for_review },
        { name: "Approved",   value: stats.data.approved,         color: STATUS_COLORS.approved },
        { name: "Rejected",   value: stats.data.rejected,         color: STATUS_COLORS.rejected },
        { name: "Error",      value: stats.data.error,            color: STATUS_COLORS.error },
      ].filter((d) => d.value > 0)
    : [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center">
          <LayoutDashboard className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-foreground">Admin Dashboard</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Review and manage IDV applications
          </p>
        </div>
      </div>

      {/* Stats */}
      {stats.data && <StatsCards stats={stats.data} />}

      {/* Chart + Metrics */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {pieData.length > 0 && (
          <div className="lg:col-span-2 bg-card border border-border rounded-xl p-5">
            <h2 className="text-sm font-semibold text-foreground mb-4">Status Distribution</h2>
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={95}
                  paddingAngle={2}
                  dataKey="value"
                >
                  {pieData.map((entry) => (
                    <Cell key={entry.name} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    background: "#071428",
                    border: "1px solid #1a3460",
                    borderRadius: "10px",
                    color: "#dce8ff",
                    fontSize: "12px",
                  }}
                />
                <Legend
                  wrapperStyle={{ color: "#5c7aa3", fontSize: "11px" }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}

        <div className="bg-card border border-border rounded-xl p-5">
          <h2 className="text-sm font-semibold text-foreground mb-5">Key Metrics</h2>
          <div className="space-y-5">
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">
                Avg Processing Time
              </p>
              <p
                className="text-2xl font-bold text-foreground"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                {stats.data?.avg_processing_hours !== null
                  ? `${stats.data?.avg_processing_hours?.toFixed(1)}h`
                  : "—"}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">
                Approval Rate
              </p>
              <p
                className="text-2xl font-bold text-emerald-400"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                {stats.data && stats.data.total_applications > 0
                  ? `${((stats.data.approved / stats.data.total_applications) * 100).toFixed(0)}%`
                  : "—"}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">
                Fraud Flag Rate
              </p>
              <p
                className="text-2xl font-bold text-amber-400"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                {stats.data?.fraud_flag_rate !== null
                  ? `${((stats.data?.fraud_flag_rate ?? 0) * 100).toFixed(1)}%`
                  : "—"}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Applications Table */}
      <div>
        <h2 className="text-sm font-semibold text-foreground mb-3">Applications</h2>
        {applications.isLoading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
          </div>
        ) : applications.data ? (
          <ApplicationsTable
            applications={applications.data.items}
            total={applications.data.total}
            page={applications.data.page}
            pageSize={applications.data.page_size}
            onPageChange={setPage}
            onSelect={setSelectedAppId}
            statusFilter={statusFilter}
            onStatusFilterChange={(s) => {
              setStatusFilter(s);
              setPage(1);
            }}
          />
        ) : null}
      </div>
    </div>
  );
}
