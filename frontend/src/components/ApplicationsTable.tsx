import type { ApplicationListItem, ApplicationStatus } from "@/types";
import VerificationStatus from "./VerificationStatus";
import { ChevronLeft, ChevronRight } from "lucide-react";

interface ApplicationsTableProps {
  applications: ApplicationListItem[];
  total: number;
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onSelect: (id: string) => void;
  statusFilter: ApplicationStatus | undefined;
  onStatusFilterChange: (status: ApplicationStatus | undefined) => void;
}

const statuses: (ApplicationStatus | undefined)[] = [
  undefined,
  "pending",
  "processing",
  "ready_for_review",
  "approved",
  "rejected",
  "error",
];

export default function ApplicationsTable({
  applications,
  total,
  page,
  pageSize,
  onPageChange,
  onSelect,
  statusFilter,
  onStatusFilterChange,
}: ApplicationsTableProps) {
  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden">
      {/* Filter bar */}
      <div className="px-4 py-3 border-b border-border flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-muted-foreground uppercase tracking-wider">Filter:</span>
          <div className="flex gap-1 flex-wrap">
            {statuses.map((s) => (
              <button
                key={s ?? "all"}
                onClick={() => onStatusFilterChange(s)}
                className={`px-2.5 py-1 rounded-full text-xs font-medium border cursor-pointer transition-all ${
                  statusFilter === s
                    ? "bg-primary/15 text-primary border-primary/30"
                    : "bg-muted text-muted-foreground border-border hover:border-primary/30 hover:text-foreground"
                }`}
              >
                {s ? s.replace("_", " ") : "All"}
              </button>
            ))}
          </div>
        </div>
        <span
          className="text-xs text-muted-foreground"
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          {total} application{total !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              <th className="text-left py-3 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Applicant
              </th>
              <th className="text-left py-3 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Status
              </th>
              <th className="text-left py-3 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Submitted
              </th>
              <th className="text-center py-3 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Docs
              </th>
            </tr>
          </thead>
          <tbody>
            {applications.length === 0 ? (
              <tr>
                <td
                  colSpan={4}
                  className="py-14 text-center text-sm text-muted-foreground"
                >
                  No applications found
                </td>
              </tr>
            ) : (
              applications.map((app) => (
                <tr
                  key={app.id}
                  onClick={() => onSelect(app.id)}
                  className="border-b border-border hover:bg-muted/20 cursor-pointer transition-colors"
                >
                  <td className="py-3 px-4">
                    <p className="font-medium text-foreground text-sm">
                      {app.user_full_name}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {app.user_email}
                    </p>
                  </td>
                  <td className="py-3 px-4">
                    <VerificationStatus status={app.status} />
                  </td>
                  <td
                    className="py-3 px-4 text-xs text-muted-foreground"
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    {new Date(app.submitted_at).toLocaleDateString()}
                  </td>
                  <td
                    className="py-3 px-4 text-center text-xs font-medium text-foreground"
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    {app.document_count}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="px-4 py-3 border-t border-border flex items-center justify-between">
          <p className="text-xs text-muted-foreground">
            Page {page} of {totalPages}
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => onPageChange(page - 1)}
              disabled={page <= 1}
              className="p-2 rounded-lg border border-border hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer bg-transparent transition-colors"
            >
              <ChevronLeft className="h-4 w-4 text-muted-foreground" />
            </button>
            <button
              onClick={() => onPageChange(page + 1)}
              disabled={page >= totalPages}
              className="p-2 rounded-lg border border-border hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer bg-transparent transition-colors"
            >
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
