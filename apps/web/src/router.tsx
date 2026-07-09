import { createRouter as createTanstackRouter } from "@tanstack/react-router";
import type { RouterHistory } from "@tanstack/react-router";

import { routeTree } from "./routeTree.gen";

export function createRouter(options?: { history?: RouterHistory }) {
  return createTanstackRouter({
    routeTree,
    history: options?.history,
    defaultPreload: "intent",
  });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createRouter>;
  }
}
