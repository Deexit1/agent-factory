import { useState } from "react";

import {
  useConnectUrl,
  useDisconnectRepo,
  useExportRepo,
  useProvisionRepo,
  useRepos,
} from "../api/queries";
import { useAuth } from "../auth/AuthContext";

function statusColor(status: string): string {
  if (status === "active") return "bg-green-100 text-green-800";
  if (status === "exported") return "bg-gray-200 text-gray-600";
  return "bg-red-100 text-red-800";
}

export function RepoConnectPage(): React.JSX.Element {
  const { orgId, role } = useAuth();
  const isOwner = role === "owner";
  const { data: repos } = useRepos(orgId);
  const connectUrl = useConnectUrl();
  const provisionRepo = useProvisionRepo();
  const exportRepo = useExportRepo();
  const disconnectRepo = useDisconnectRepo();

  const [newRepoName, setNewRepoName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [exportResult, setExportResult] = useState<{ repoId: number; url: string } | null>(null);

  if (!orgId) {
    return <p className="p-4 text-gray-500">Loading…</p>;
  }

  const items = repos?.items ?? [];

  const handleConnect = async (): Promise<void> => {
    setError(null);
    try {
      const { url } = await connectUrl.mutateAsync({ orgId });
      window.location.href = url;
    } catch {
      setError("Could not start the GitHub connect flow — see console for details.");
    }
  };

  const handleProvision = async (): Promise<void> => {
    setError(null);
    try {
      await provisionRepo.mutateAsync({ orgId, name: newRepoName });
      setNewRepoName("");
    } catch {
      setError("Could not provision a repo — check the name and try again.");
    }
  };

  const handleExport = async (repoId: number): Promise<void> => {
    setError(null);
    setExportResult(null);
    try {
      const result = await exportRepo.mutateAsync({ orgId, repoId, mode: "archive" });
      if (result.download_url) {
        setExportResult({ repoId, url: result.download_url });
      }
    } catch {
      setError("Could not export this repo.");
    }
  };

  return (
    <main className="mx-auto max-w-2xl p-6">
      <h1 className="text-xl font-bold text-gray-900">Repos</h1>
      <p className="mt-1 text-sm text-gray-500">
        Connect your own GitHub repo (via the GitHub App) so agents deliver PRs there, or
        provision a fresh repo we create and hand over later.
      </p>

      <ul className="mt-4 flex flex-col gap-2">
        {items.map((repo) => (
          <li
            key={repo.id}
            className="flex flex-col gap-1 rounded border border-gray-200 p-3 text-sm"
          >
            <div className="flex items-center justify-between">
              <span className="font-medium">{repo.github_full_name ?? `repo #${repo.id}`}</span>
              <span className={`rounded px-2 py-0.5 text-xs ${statusColor(repo.status)}`}>
                {repo.status}
              </span>
            </div>
            <span className="text-xs text-gray-500">
              {repo.mode} · default branch: {repo.default_branch ?? "unknown"}
            </span>
            {!repo.protected_branch_rules_verified && repo.status === "active" && (
              <p role="alert" className="text-xs text-amber-700">
                Default branch has no verified branch-protection rules on GitHub. Agent
                pushes are still restricted to agent/* branches by this platform's own
                code, but we recommend enabling protection on GitHub too.
              </p>
            )}
            {repo.disconnected_reason && (
              <p className="text-xs text-gray-500">{repo.disconnected_reason}</p>
            )}
            {isOwner && repo.status === "active" && (
              <div className="flex items-center gap-3 text-xs">
                <button
                  type="button"
                  onClick={() => void handleExport(repo.id)}
                  disabled={exportRepo.isPending}
                  className="text-gray-600 hover:underline disabled:opacity-50"
                >
                  Export (download archive)
                </button>
                <button
                  type="button"
                  onClick={() => void disconnectRepo.mutateAsync({ orgId, repoId: repo.id })}
                  disabled={disconnectRepo.isPending}
                  className="ml-auto text-red-600 hover:underline disabled:opacity-50"
                >
                  Disconnect
                </button>
              </div>
            )}
            {exportResult?.repoId === repo.id && (
              <a
                href={exportResult.url}
                className="text-xs text-blue-600 hover:underline"
                target="_blank"
                rel="noreferrer"
              >
                Download archive
              </a>
            )}
          </li>
        ))}
        {items.length === 0 && (
          <li className="text-sm text-gray-500">No repos connected or provisioned yet.</li>
        )}
      </ul>

      {isOwner && (
        <div className="mt-6 flex flex-col gap-4">
          <div className="flex flex-col gap-2 rounded border border-gray-200 p-4">
            <h2 className="text-sm font-semibold text-gray-900">Connect a GitHub repo</h2>
            <button
              type="button"
              onClick={() => void handleConnect()}
              disabled={connectUrl.isPending}
              className="self-start rounded bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
            >
              Connect via GitHub App
            </button>
          </div>

          <div className="flex flex-col gap-2 rounded border border-gray-200 p-4">
            <h2 className="text-sm font-semibold text-gray-900">Provision a new repo</h2>
            <input
              type="text"
              placeholder="repo-name"
              value={newRepoName}
              onChange={(event) => setNewRepoName(event.target.value)}
              aria-label="New repo name"
              className="rounded border border-gray-300 px-2 py-1 text-sm"
            />
            <button
              type="button"
              onClick={() => void handleProvision()}
              disabled={!newRepoName || provisionRepo.isPending}
              className="self-start rounded bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
            >
              Provision repo
            </button>
          </div>

          {error && <p className="text-xs text-red-600">{error}</p>}
        </div>
      )}
    </main>
  );
}
