import { Navigate, Outlet } from "@tanstack/react-router";

import { useAuth } from "@/auth/AuthContext";

// UX guard only, mirroring today's hidden-nav-button behavior but now also covering
// direct URL navigation. The real authz boundary is the backend — these 4 endpoints
// must already reject non-staff callers server-side regardless of this guard.
export function StaffGuard(): React.JSX.Element {
  const { isPlatformStaff, impersonating } = useAuth();

  if (!isPlatformStaff || impersonating) {
    return <Navigate to="/board" replace />;
  }

  return <Outlet />;
}
