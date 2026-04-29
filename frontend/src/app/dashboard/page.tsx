"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  listProjects,
  listAvailableRepos,
  createProject,
  deleteProject,
  getProject,
  Project,
  RepoItem,
} from "@/lib/api";

export default function DashboardPage() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();

  const [projects, setProjects] = useState<Project[]>([]);
  const [repos, setRepos] = useState<RepoItem[]>([]);
  const [showConnect, setShowConnect] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [selectedRepo, setSelectedRepo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pollingIds, setPollingIds] = useState<Set<string>>(new Set());

  const fetchProjects = useCallback(async () => {
    try {
      const data = await listProjects();
      setProjects(data);
      // Poll any non-ready projects
      const pending = data.filter(
        (p) => p.status === "indexing" || p.status === "pending"
      );
      if (pending.length > 0) {
        setPollingIds(new Set(pending.map((p) => p.id)));
      }
    } catch {
      setError("Failed to load projects");
    }
  }, []);

  useEffect(() => {
    if (!loading && !user) router.replace("/");
  }, [user, loading, router]);

  useEffect(() => {
    if (user) fetchProjects();
  }, [user, fetchProjects]);

  // Poll pending/indexing projects
  useEffect(() => {
    if (pollingIds.size === 0) return;
    const interval = setInterval(async () => {
      const updates = await Promise.all(
        [...pollingIds].map((id) => getProject(id).catch(() => null))
      );
      setProjects((prev) =>
        prev.map((p) => {
          const updated = updates.find((u) => u && u.id === p.id);
          return updated || p;
        })
      );
      const stillPending = updates.filter(
        (u) => u && (u.status === "indexing" || u.status === "pending")
      );
      if (stillPending.length === 0) setPollingIds(new Set());
    }, 4000);
    return () => clearInterval(interval);
  }, [pollingIds]);

  const openConnectModal = async () => {
    setShowConnect(true);
    try {
      const data = await listAvailableRepos();
      setRepos(data);
    } catch {
      setError("Could not load GitHub repos");
    }
  };

  const handleConnect = async () => {
    if (!selectedRepo) return;
    setConnecting(true);
    setError(null);
    try {
      const project = await createProject(selectedRepo);
      setProjects((prev) => [project, ...prev]);
      setPollingIds((prev) => new Set([...prev, project.id]));
      setShowConnect(false);
      setSelectedRepo("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to connect repo");
    } finally {
      setConnecting(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Remove this project?")) return;
    await deleteProject(id);
    setProjects((prev) => prev.filter((p) => p.id !== id));
  };

  if (loading || !user) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-950">
      {/* Nav */}
      <nav className="flex items-center justify-between border-b border-gray-800 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-sm font-bold text-white">
            D
          </div>
          <span className="font-semibold text-white">DocMind</span>
        </div>
        <div className="flex items-center gap-4">
          {user.avatar_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={user.avatar_url}
              alt={user.github_login}
              className="h-8 w-8 rounded-full"
            />
          )}
          <span className="text-sm text-gray-400">{user.github_login}</span>
          <button
            onClick={logout}
            className="text-sm text-gray-500 hover:text-gray-300"
          >
            Sign out
          </button>
        </div>
      </nav>

      <div className="mx-auto max-w-5xl px-6 py-10">
        <div className="mb-8 flex items-center justify-between">
          <h1 className="text-2xl font-bold text-white">Projects</h1>
          <button
            onClick={openConnectModal}
            className="rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 transition"
          >
            + Connect repo
          </button>
        </div>

        {error && (
          <div className="mb-6 rounded-xl border border-red-800 bg-red-950 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {projects.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-gray-700 py-20 text-center">
            <p className="mb-2 text-lg font-medium text-gray-300">
              No projects yet
            </p>
            <p className="mb-6 text-sm text-gray-500">
              Connect a GitHub repo to get started
            </p>
            <button
              onClick={openConnectModal}
              className="rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 transition"
            >
              Connect a repo
            </button>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {projects.map((p) => (
              <ProjectCard
                key={p.id}
                project={p}
                onDelete={() => handleDelete(p.id)}
                onOpen={() => router.push(`/dashboard/${p.id}/chat`)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Connect modal */}
      {showConnect && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
          <div className="w-full max-w-md rounded-2xl border border-gray-800 bg-gray-900 p-6 shadow-2xl">
            <h2 className="mb-4 text-lg font-semibold text-white">
              Connect a GitHub repository
            </h2>
            <select
              value={selectedRepo}
              onChange={(e) => setSelectedRepo(e.target.value)}
              className="mb-4 w-full rounded-xl border border-gray-700 bg-gray-800 px-4 py-3 text-sm text-white focus:border-indigo-500 focus:outline-none"
            >
              <option value="">Select a repository…</option>
              {repos.map((r) => (
                <option key={r.full_name} value={r.full_name}>
                  {r.full_name} {r.private ? "🔒" : ""}{" "}
                  {r.language ? `· ${r.language}` : ""}
                </option>
              ))}
            </select>
            <div className="flex gap-3">
              <button
                onClick={handleConnect}
                disabled={!selectedRepo || connecting}
                className="flex-1 rounded-xl bg-indigo-600 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 transition"
              >
                {connecting ? "Connecting…" : "Connect"}
              </button>
              <button
                onClick={() => setShowConnect(false)}
                className="flex-1 rounded-xl border border-gray-700 py-2.5 text-sm font-semibold text-gray-300 hover:bg-gray-800 transition"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ProjectCard({
  project,
  onDelete,
  onOpen,
}: {
  project: Project;
  onDelete: () => void;
  onOpen: () => void;
}) {
  const statusColor: Record<string, string> = {
    ready: "text-green-400",
    indexing: "text-yellow-400",
    pending: "text-yellow-400",
    error: "text-red-400",
  };
  const statusLabel: Record<string, string> = {
    ready: "Ready",
    indexing: "Indexing…",
    pending: "Pending",
    error: "Error",
  };

  return (
    <div className="flex flex-col justify-between rounded-2xl border border-gray-800 bg-gray-900 p-5 transition hover:border-gray-700">
      <div>
        <div className="mb-1 flex items-center justify-between">
          <h3 className="font-semibold text-white">{project.repo_name}</h3>
          <span
            className={`text-xs font-medium ${
              statusColor[project.status] || "text-gray-400"
            }`}
          >
            {statusLabel[project.status] || project.status}
            {(project.status === "indexing" || project.status === "pending") && (
              <span className="ml-1 inline-block h-2 w-2 animate-pulse rounded-full bg-yellow-400" />
            )}
          </span>
        </div>
        <p className="mb-4 text-xs text-gray-500">{project.repo_owner}</p>
        <div className="grid grid-cols-3 gap-2 text-center">
          <Stat label="Files" value={project.file_count} />
          <Stat label="Chunks" value={project.chunk_count} />
          <Stat
            label="Coverage"
            value={
              project.doc_coverage_score != null
                ? `${Math.round(project.doc_coverage_score * 100)}%`
                : "—"
            }
          />
        </div>
      </div>
      <div className="mt-4 flex gap-2">
        <button
          onClick={onOpen}
          disabled={project.status !== "ready"}
          className="flex-1 rounded-xl bg-indigo-600 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40 transition"
        >
          Open
        </button>
        <button
          onClick={onDelete}
          className="rounded-xl border border-gray-700 px-3 py-2 text-sm text-gray-400 hover:border-red-800 hover:text-red-400 transition"
        >
          Remove
        </button>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg bg-gray-800 px-2 py-2">
      <div className="text-sm font-semibold text-white">{value}</div>
      <div className="text-xs text-gray-500">{label}</div>
    </div>
  );
}
