import { useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  useConnectUrl,
  useDisconnectRepo,
  useExportRepo,
  useProvisionRepo,
  useRepos,
} from "../api/queries";
import { useAuth } from "../auth/AuthContext";

function statusBadgeClassName(status: string): string {
  if (status === "active") return "border-green-300 bg-green-50 text-green-800";
  if (status === "exported") return "border-transparent bg-muted text-muted-foreground";
  return "border-red-300 bg-red-50 text-red-800";
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
    return <p className="p-4 text-muted-foreground">Loading…</p>;
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
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-bold text-foreground">Repos</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Connect your own GitHub repo (via the GitHub App) so agents deliver PRs there, or
          provision a fresh repo we create and hand over later.
        </p>
      </div>

      <ul className="flex flex-col gap-2">
        {items.map((repo) => (
          <li key={repo.id} className="flex flex-col gap-1 rounded-lg border p-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="font-medium">{repo.github_full_name ?? `repo #${repo.id}`}</span>
              <Badge variant="outline" className={statusBadgeClassName(repo.status)}>
                {repo.status}
              </Badge>
            </div>
            <span className="text-xs text-muted-foreground">
              {repo.mode} · default branch: {repo.default_branch ?? "unknown"}
            </span>
            {!repo.protected_branch_rules_verified && repo.status === "active" && (
              <Alert variant="destructive" role="alert" className="border-amber-300 bg-amber-50">
                <AlertDescription className="text-amber-800">
                  Default branch has no verified branch-protection rules on GitHub. Agent
                  pushes are still restricted to agent/* branches by this platform's own
                  code, but we recommend enabling protection on GitHub too.
                </AlertDescription>
              </Alert>
            )}
            {repo.disconnected_reason && (
              <p className="text-xs text-muted-foreground">{repo.disconnected_reason}</p>
            )}
            {isOwner && repo.status === "active" && (
              <div className="flex items-center gap-3 text-xs">
                <Button
                  variant="link"
                  size="sm"
                  onClick={() => void handleExport(repo.id)}
                  disabled={exportRepo.isPending}
                  className="h-auto p-0 text-muted-foreground"
                >
                  Export (download archive)
                </Button>
                <Button
                  variant="link"
                  size="sm"
                  onClick={() => void disconnectRepo.mutateAsync({ orgId, repoId: repo.id })}
                  disabled={disconnectRepo.isPending}
                  className="ml-auto h-auto p-0 text-destructive"
                >
                  Disconnect
                </Button>
              </div>
            )}
            {exportResult?.repoId === repo.id && (
              <a
                href={exportResult.url}
                className="text-xs text-primary hover:underline"
                target="_blank"
                rel="noreferrer"
              >
                Download archive
              </a>
            )}
          </li>
        ))}
        {items.length === 0 && (
          <li className="text-sm text-muted-foreground">No repos connected or provisioned yet.</li>
        )}
      </ul>

      {isOwner && (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2 rounded-lg border p-4">
            <h2 className="text-sm font-semibold text-foreground">Connect a GitHub repo</h2>
            <Button
              onClick={() => void handleConnect()}
              disabled={connectUrl.isPending}
              className="self-start"
            >
              Connect via GitHub App
            </Button>
          </div>

          <div className="flex flex-col gap-2 rounded-lg border p-4">
            <h2 className="text-sm font-semibold text-foreground">Provision a new repo</h2>
            <Input
              type="text"
              placeholder="repo-name"
              value={newRepoName}
              onChange={(event) => setNewRepoName(event.target.value)}
              aria-label="New repo name"
            />
            <Button
              onClick={() => void handleProvision()}
              disabled={!newRepoName || provisionRepo.isPending}
              className="self-start"
            >
              Provision repo
            </Button>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
      )}
    </div>
  );
}
