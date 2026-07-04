import { useState } from "react";

import { AuthProvider, useAuth } from "./auth/AuthContext";
import { LoginPage } from "./auth/LoginPage";
import { BoardPage } from "./board/BoardPage";
import { DashboardPage } from "./dashboard/DashboardPage";

type View = "board" | "dashboard";

function AuthedApp(): React.JSX.Element {
  const { status, actor, logout } = useAuth();
  const [view, setView] = useState<View>("board");

  if (status === "loading") {
    return <p className="p-4 text-gray-500">Loading…</p>;
  }

  if (status === "unauthenticated") {
    return <LoginPage />;
  }

  return (
    <div className="flex h-screen flex-col">
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
            onClick={() => setView("dashboard")}
            className={view === "dashboard" ? "font-semibold text-gray-900" : "text-gray-500"}
          >
            Dashboard
          </button>
        </div>
        <div className="flex items-center gap-3 text-gray-500">
          <span>{actor}</span>
          <button type="button" onClick={logout} className="hover:text-gray-900">
            Sign out
          </button>
        </div>
      </nav>
      <div className="flex-1 overflow-hidden">
        {view === "board" ? <BoardPage /> : <DashboardPage />}
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
