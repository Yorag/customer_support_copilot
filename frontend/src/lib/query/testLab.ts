import { useMutation, useQueryClient } from "@tanstack/react-query";

import { controlPlaneApi } from "@/lib/api/controlPlane";
import type { TestEmailRequest, TestEmailResponse } from "@/lib/api/types";
import { queryKeys } from "@/lib/query/keys";

export function useCreateTestEmail() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: TestEmailRequest) => controlPlaneApi.createTestEmail(payload),
    onSuccess: async (result: TestEmailResponse) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.dashboard() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.opsStatus }),
        queryClient.invalidateQueries({ queryKey: ["tickets"] }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.ticketSnapshot(result.ticket.ticket_id),
        }),
      ]);
    },
  });
}
