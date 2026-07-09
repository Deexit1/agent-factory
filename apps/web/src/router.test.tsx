import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { AuthProvider } from "./auth/AuthContext";
import { createRouter } from "./router";

function renderApp(initialPath = "/") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const router = createRouter({ history: createMemoryHistory({ initialEntries: [initialPath] }) });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe("router", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("shows the login gate when no session token is present", async () => {
    renderApp();

    expect(await screen.findByRole("link", { name: "Sign in with Google" })).toBeInTheDocument();
    expect(screen.getByText("Local dev sign-in")).toBeInTheDocument();
  });
});
