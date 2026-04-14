import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "./client";
import type {
  ApplicationListResponse,
  ApplicationDetail,
  StatsResponse,
  ApplicationStatus,
} from "@/types";

// Get admin stats
export function useAdminStats() {
  return useQuery({
    queryKey: ["admin-stats"],
    queryFn: async () => {
      const { data } = await api.get<StatsResponse>("/admin/stats");
      return data;
    },
    refetchInterval: 30_000,
  });
}

// List applications with pagination and filters
export function useApplications(
  page: number = 1,
  perPage: number = 10,
  status?: ApplicationStatus,
) {
  return useQuery({
    queryKey: ["admin-applications", page, perPage, status],
    queryFn: async () => {
      const params: Record<string, string | number> = { page, page_size: perPage };
      if (status) params.status = status;
      const { data } = await api.get<ApplicationListResponse>(
        "/admin/applications",
        { params },
      );
      return data;
    },
  });
}

// Get single application detail
export function useApplicationDetail(id: string) {
  return useQuery({
    queryKey: ["admin-application", id],
    queryFn: async () => {
      const { data } = await api.get<ApplicationDetail>(
        `/admin/applications/${id}`,
      );
      return data;
    },
    enabled: !!id,
  });
}

// Review application (approve/reject)
export function useReviewApplication() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      id,
      action,
      reason,
    }: {
      id: string;
      action: "approve" | "reject";
      reason?: string;
    }) => {
      const { data } = await api.patch(`/admin/applications/${id}`, {
        action,
        reason,
      });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-applications"] });
      queryClient.invalidateQueries({ queryKey: ["admin-stats"] });
      queryClient.invalidateQueries({ queryKey: ["admin-application"] });
    },
  });
}
