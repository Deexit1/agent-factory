import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { App } from "./App";

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );
}

describe("App", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("shows the login gate when no session token is present", () => {
    renderApp();

    expect(screen.getByRole("link", { name: "Sign in with Google" })).toBeInTheDocument();
    expect(screen.getByText("Local dev sign-in")).toBeInTheDocument();
  });
});
