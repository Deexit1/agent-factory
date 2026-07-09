import "@testing-library/jest-dom/vitest";

// jsdom doesn't implement scrollTo — TanStack Router's scroll restoration calls it on
// every navigation (routes/__root.tsx renders inside a RouterProvider in tests too).
if (typeof window !== "undefined") {
  window.scrollTo = () => undefined;
}

// jsdom doesn't implement matchMedia — next-themes (used by the shadcn Toaster,
// mounted in routes/__root.tsx) calls it on mount to detect the system theme.
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (query: string): MediaQueryList => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  });
}
