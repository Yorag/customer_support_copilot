import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { controlPlaneApi } from "@/lib/api/controlPlane";
import type {
  GmailScanPreviewRequest,
  GmailScanRequest,
} from "@/lib/api/types";
import { queryKeys } from "@/lib/query/keys";

export function useGmailOpsStatus() {
  return useQuery({
    queryKey: queryKeys.opsStatus,
    queryFn: () => controlPlaneApi.getOpsStatus(),
  });
}

export function usePreviewGmailScan() {
  return useMutation({
    mutationFn: (payload: GmailScanPreviewRequest) =>
      controlPlaneApi.previewGmailScan(payload),
  });
}

export function useScanGmail() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: GmailScanRequest) => controlPlaneApi.scanGmail(payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.opsStatus }),
        queryClient.invalidateQueries({ queryKey: queryKeys.dashboard() }),
        queryClient.invalidateQueries({ queryKey: ["tickets"] }),
      ]);
    },
  });
}
