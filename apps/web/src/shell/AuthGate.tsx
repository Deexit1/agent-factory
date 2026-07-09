import { Outlet } from "@tanstack/react-router";

import { useAuth } from "@/auth/AuthContext";
import { LoginPage } from "@/auth/LoginPage";

// Component-level gate, not a router beforeLoad — status resolves asynchronously
// (AuthContext's fetchMe() on mount) and beforeLoad/router context don't reactively
// track React state without manually calling router.invalidate() on every change.
// See docs/07-conventions.md's routing section for the full rationale.
export function AuthGate(): React.JSX.Element {
  const { status } = useAuth();

  if (status === "loading") {
    return <p className="p-4 text-gray-500">Loading…</p>;
  }

  if (status === "unauthenticated") {
    return <LoginPage />;
  }

  return <Outlet />;
}
