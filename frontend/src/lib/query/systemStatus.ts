import { useQuery } from "@tanstack/react-query";

import { controlPlaneApi } from "@/lib/api/controlPlane";
import { queryKeys } from "@/lib/query/keys";

export function useSystemStatus() {
  return useQuery({
    queryKey: queryKeys.opsStatus,
    queryFn: () => controlPlaneApi.getOpsStatus(),
  });
}
