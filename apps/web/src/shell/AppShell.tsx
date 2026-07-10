import { useEffect } from "react";

import { Outlet, useRouterState } from "@tanstack/react-router";

import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { useAuth } from "@/auth/AuthContext";
import { usePageViewAudit } from "@/api/queries";
import { AppSidebar } from "@/shell/AppSidebar";
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
      <SidebarProvider className="min-h-0 flex-1">
        <AppSidebar />
        <SidebarInset className="overflow-y-auto">
          <Outlet />
        </SidebarInset>
      </SidebarProvider>
    </div>
  );
}
