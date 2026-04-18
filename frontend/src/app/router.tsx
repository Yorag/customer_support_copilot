import { createBrowserRouter, createMemoryRouter } from "react-router-dom";

import { routes } from "@/app/routes";

export function createAppRouter(initialEntries?: string[]) {
  if (initialEntries) {
    return createMemoryRouter(routes, {
      initialEntries,
    });
  }

  return createBrowserRouter(routes);
}
