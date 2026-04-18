import type { PropsWithChildren } from "react";
import { useState } from "react";
import { QueryClientProvider } from "@tanstack/react-query";

import { createQueryClient } from "@/lib/query/query-client";

export function Providers({ children }: PropsWithChildren) {
  const [queryClient] = useState(createQueryClient);

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
