import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { UseQueryOptions } from "@tanstack/react-query";
import api from "./client";
import type { IDVApplication, DocumentType, ExtractedFields } from "@/types";

interface SubmitResponse {
  id: string;
  status: string;
  submitted_at: string;
}

export interface DocumentUploadResponse {
  id: string;
  application_id: string;
  doc_type: DocumentType;
  original_filename: string;
  file_size: number;
  mime_type: string;
  uploaded_at: string;
  extracted_fields: ExtractedFields | null;
}

// Get IDV status — returns null when no app exists (404)
export function useIDVStatus(
  options?: Partial<UseQueryOptions<IDVApplication | null>>,
) {
  return useQuery({
    queryKey: ["idv-status"],
    queryFn: async () => {
      try {
        const { data } = await api.get<IDVApplication>("/idv/status");
        return data;
      } catch (err) {
        const status = (err as { response?: { status?: number } }).response?.status;
        if (status === 404) return null;
        throw err;
      }
    },
    retry: false,
    ...options,
  });
}

// Upload document — returns extracted fields from synchronous OCR
export function useUploadDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      file,
      docType,
      applicationId,
    }: {
      file: File;
      docType: DocumentType;
      applicationId: string;
    }) => {
      const formData = new FormData();
      formData.append("file", file);

      const { data } = await api.post<DocumentUploadResponse>(
        `/idv/upload-document?application_id=${applicationId}&doc_type=${docType}`,
        formData,
        { headers: { "Content-Type": "multipart/form-data" } },
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["idv-status"] });
    },
  });
}

// Create application (auto, no doc type needed)
export function useCreateApplication() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post<SubmitResponse>("/idv/submit");
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["idv-status"] });
    },
  });
}

// Upload selfie
export function useUploadSelfie() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      file,
      applicationId,
    }: {
      file: File;
      applicationId: string;
    }) => {
      const formData = new FormData();
      formData.append("file", file);

      const { data } = await api.post(
        `/idv/upload-selfie?application_id=${applicationId}`,
        formData,
        { headers: { "Content-Type": "multipart/form-data" } },
      );
      return data as { id: string; application_id: string; selfie_path: string; created_at: string };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["idv-status"] });
    },
  });
}

// Poll a single document for OCR results
export function useDocumentOCR(docId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ["document-ocr", docId],
    queryFn: async () => {
      const { data } = await api.get<{
        id: string;
        doc_type: DocumentType;
        ocr_ready: boolean;
        extracted_fields: ExtractedFields | null;
      }>(`/idv/document/${docId}`);
      return data;
    },
    enabled: !!docId && enabled,
    refetchInterval: (query) => {
      // Stop polling once OCR is ready
      if (query.state.data?.ocr_ready) return false;
      return 3000; // poll every 3 seconds
    },
    retry: false,
  });
}

// Generate a one-time mobile selfie upload token
export function useGetMobileSelfieToken() {
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.get<{ token: string; expires_in: number }>(
        "/idv/mobile-selfie-token",
      );
      return data;
    },
  });
}

type PipelineResultResponse = {
  application_id: string;
  pipeline_version: string | null;
  pipeline_decision: string | null;
  weighted_total: number | null;
  channel_scores: Record<string, number | null> | null;
  decision_override: string | null;
  flags: unknown[] | null;
  reason_codes: unknown[] | null;
  started_at: string | null;
  completed_at: string | null;
};

// Get pipeline result for user's application
export function usePipelineResult(
  options?: Partial<UseQueryOptions<PipelineResultResponse | null>>,
) {
  return useQuery({
    queryKey: ["pipeline-result"],
    queryFn: async () => {
      try {
        const { data } = await api.get<PipelineResultResponse>("/idv/pipeline-result");
        return data;
      } catch (err) {
        const status = (err as { response?: { status?: number } }).response?.status;
        if (status === 404) return null;
        throw err;
      }
    },
    retry: false,
    ...options,
  });
}
