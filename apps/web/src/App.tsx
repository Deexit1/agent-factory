import { useEffect, useState } from "react";

import { ImpersonatePage } from "./admin/ImpersonatePage";
import { AssignmentQueuePage } from "./assignments/AssignmentQueuePage";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { LoginPage } from "./auth/LoginPage";
import { BoardPage } from "./board/BoardPage";
import { DashboardPage } from "./dashboard/DashboardPage";
import { PlanningReviewPage } from "./planning/PlanningReviewPage";
import { useMyOrgs, usePageViewAudit, useSwitchOrg } from "./api/queries";

type View = "board" | "planning" | "assignments" | "dashboard" | "impersonate";

function OrgSwitcher(): React.JSX.Element | null {
  const { orgId, setToken } = useAuth();
  const { data: orgs } = useMyOrgs();
  const switchOrg = useSwitchOrg();

  if (!orgs || orgs.items.length <= 1) {
    return null;
  }

  return (
    <select
      aria-label="Switch org"
      value={orgId ?? ""}
      onChange={(event) => {
        void switchOrg
          .mutateAsync({ orgId: event.target.value })
          .then((session) => setToken(session.token));
      }}
      className="rounded border border-gray-300 px-2 py-1 text-xs"
    >
      {orgs.items.map((org) => (
        <option key={org.id} value={org.id}>
          {org.name}
        </option>
      ))}
    </select>
  );
}

function AuthedApp(): React.JSX.Element {
  const { status, actor, isPlatformStaff, impersonating, orgId, logout } = useAuth();
  const [view, setView] = useState<View>("board");
  const auditPageView = usePageViewAudit();

  useEffect(() => {
    if (impersonating) {
      auditPageView(`/${view}`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, impersonating]);

  if (status === "loading") {
    return <p className="p-4 text-gray-500">Loading…</p>;
  }

  if (status === "unauthenticated") {
    return <LoginPage />;
  }

  return (
    <div className="flex h-screen flex-col">
      {impersonating && (
        <div
          role="alert"
          className="bg-red-600 px-4 py-1 text-center text-xs font-semibold text-white"
        >
          Staff view — viewing org {orgId} as {actor}. This session is audited.
        </div>
      )}
      <nav className="flex items-center justify-between border-b border-gray-200 px-4 py-2 text-sm">
        <div className="flex gap-4">
          <button
            type="button"
            onClick={() => setView("board")}
            className={view === "board" ? "font-semibold text-gray-900" : "text-gray-500"}
          >
            Board
          </button>
          <button
            type="button"
            onClick={() => setView("planning")}
            className={view === "planning" ? "font-semibold text-gray-900" : "text-gray-500"}
          >
            Planning
          </button>
          <button
            type="button"
            onClick={() => setView("assignments")}
            className={view === "assignments" ? "font-semibold text-gray-900" : "text-gray-500"}
          >
            Assignments
          </button>
          <button
            type="button"
            onClick={() => setView("dashboard")}
            className={view === "dashboard" ? "font-semibold text-gray-900" : "text-gray-500"}
          >
            Dashboard
          </button>
          {isPlatformStaff && !impersonating && (
            <button
              type="button"
              onClick={() => setView("impersonate")}
              className={view === "impersonate" ? "font-semibold text-gray-900" : "text-gray-500"}
            >
              Staff
            </button>
          )}
        </div>
        <div className="flex items-center gap-3 text-gray-500">
          <OrgSwitcher />
          <span>{actor}</span>
          <button type="button" onClick={logout} className="hover:text-gray-900">
            Sign out
          </button>
        </div>
      </nav>
      <div className="flex-1 overflow-hidden">
        {view === "board" && <BoardPage />}
        {view === "planning" && <PlanningReviewPage />}
        {view === "assignments" && <AssignmentQueuePage />}
        {view === "dashboard" && <DashboardPage />}
        {view === "impersonate" && <ImpersonatePage />}
      </div>
    </div>
  );
}

export function App(): React.JSX.Element {
  return (
    <AuthProvider>
      <AuthedApp />
    </AuthProvider>
  );
}
