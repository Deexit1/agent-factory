import { useState } from "react";

import { devLogin, googleLoginUrl } from "../api/client";
import { useAuth, type Role } from "./AuthContext";

export function LoginPage(): React.JSX.Element {
  const { setToken } = useAuth();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("viewer");
  const [error, setError] = useState<string | null>(null);

  const handleDevLogin = async (): Promise<void> => {
    setError(null);
    try {
      const session = await devLogin(email, role);
      setToken(session.token);
    } catch {
      setError(
        "Dev login isn't available here (AUTH_DEV_MODE off) or the request failed. " +
          "Use Google sign-in instead.",
      );
    }
  };

  return (
    <main className="flex h-screen flex-col items-center justify-center gap-6 bg-white">
      <h1 className="text-2xl font-bold text-gray-900">Agent Factory</h1>

      <a
        href={googleLoginUrl()}
        className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
      >
        Sign in with Google
      </a>

      <div className="flex w-72 flex-col gap-2 rounded-md border border-gray-200 p-4">
        <p className="text-xs font-semibold text-gray-500">Local dev sign-in</p>
        <input
          type="email"
          placeholder="you@example.com"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          aria-label="Email"
          className="rounded border border-gray-300 px-2 py-1 text-sm"
        />
        <select
          value={role}
          onChange={(event) => setRole(event.target.value as Role)}
          aria-label="Role"
          className="rounded border border-gray-300 px-2 py-1 text-sm"
        >
          <option value="viewer">viewer</option>
          <option value="approver">approver</option>
          <option value="admin">admin</option>
        </select>
        <button
          type="button"
          onClick={() => void handleDevLogin()}
          disabled={!email}
          className="rounded bg-gray-800 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-900 disabled:opacity-50"
        >
          Sign in (dev)
        </button>
        {error && <p className="text-xs text-red-600">{error}</p>}
      </div>
    </main>
  );
}
