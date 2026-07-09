import { useEffect } from "react";

import { Outlet, useRouterState } from "@tanstack/react-router";

import { useAuth } from "@/auth/AuthContext";
import { usePageViewAudit } from "@/api/queries";
import { TopNav } from "@/shell/TopNav";
import { ImpersonationBanner } from "@/shell/ImpersonationBanner";

export function AppShell(): React.JSX.Element {
  const { impersonating } = useAuth();
  const auditPageView = usePageViewAudit();
  const pathname = useRouterState({ select: (state) => state.location.pathname });

  useEffect(() => {
    if (impersonating) {
      auditPageView(pathname);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname, impersonating]);

  return (
    <div className="flex h-screen flex-col">
      {impersonating && <ImpersonationBanner />}
      <TopNav />
      <div className="flex-1 overflow-hidden">
        <Outlet />
      </div>
    </div>
  );
}
