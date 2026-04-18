import type { Router as AppRouter } from "@remix-run/router";
import { RouterProvider } from "react-router-dom";

import { Providers } from "@/app/providers";
import { createAppRouter } from "@/app/router";

type AppProps = {
  router?: AppRouter;
};

export function App({ router = createAppRouter() }: AppProps) {
  return (
    <Providers>
      <RouterProvider router={router} />
    </Providers>
  );
}
