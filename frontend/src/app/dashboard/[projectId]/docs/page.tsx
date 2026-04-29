"use client";

import { useState, useEffect, use } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  getProject,
  generateDocs,
  getAgentTask,
  createPR,
  Project,
  AgentTask,
} from "@/lib/api";

const DOC_TYPES = [
  { id: "readme", label: "README" },
  { id: "api_reference", label: "API Reference" },
  { id: "architecture", label: "Architecture" },
  { id: "getting_started", label: "Getting Started" },
];

export default function DocsPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = use(params);
  const { user, loading } = useAuth();
  const router = useRouter();

  const [project, setProject] = useState<Project | null>(null);
  const [task, setTask] = useState<AgentTask | null>(null);
  const [activeDoc, setActiveDoc] = useState("readme");
  const [generating, setGenerating] = useState(false);
  const [creatingPR, setCreatingPR] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [prUrl, setPrUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/");
  }, [user, loading, router]);

  useEffect(() => {
    if (user) {
      getProject(projectId)
        .then(setProject)
        .catch(() => router.replace("/dashboard"));
    }
  }, [user, projectId, router]);

  // Poll task status
  useEffect(() => {
    if (!task || task.status === "completed" || task.status === "failed") return;
    const interval = setInterval(async () => {
      const updated = await getAgentTask(task.id).catch(() => null);
      if (updated) setTask(updated);
    }, 3000);
    return () => clearInterval(interval);
  }, [task]);

  const handleGenerate = async () => {
    setGenerating(true);
    setError(null);
    try {
      const t = await generateDocs(projectId);
      setTask(t);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to generate docs");
    } finally {
      setGenerating(false);
    }
  };

  const handleCreatePR = async () => {
    if (!task?.output) return;
    setCreatingPR(true);
    setError(null);
    try {
      const docs = task.output as Record<string, { id?: string }>;
      const docIds = Object.values(docs)
        .map((d) => d?.id)
        .filter(Boolean) as string[];
      const prTask = await createPR(projectId, docIds);
      setTask(prTask);
      // Poll for PR URL
      const poll = setInterval(async () => {
        const updated = await getAgentTask(prTask.id).catch(() => null);
        if (updated) {
          setTask(updated);
          if (updated.status === "completed" && updated.output?.pr_url) {
            setPrUrl(updated.output.pr_url as string);
            clearInterval(poll);
          }
          if (updated.status === "failed") clearInterval(poll);
        }
      }, 3000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to create PR");
    } finally {
      setCreatingPR(false);
    }
  };

  const docs =
    task?.status === "completed" && task.output
      ? (task.output as Record<string, { content?: string; quality_score?: number; issues?: string[] }>)
      : null;

  const activeContent = docs?.[activeDoc];
  const isRunning =
    task && task.status !== "completed" && task.status !== "failed";

  return (
    <div className="flex h-screen flex-col bg-gray-950">
      {/* Header */}
      <header className="flex items-center gap-4 border-b border-gray-800 px-6 py-4">
        <button
          onClick={() => router.push(`/dashboard/${projectId}/chat`)}
          className="text-gray-400 hover:text-white transition"
        >
          ← Chat
        </button>
        <div className="flex-1">
          <h1 className="font-semibold text-white">
            {project?.repo_name ?? "Loading…"} — Generated Docs
          </h1>
          {project && (
            <p className="text-xs text-gray-500">
              Coverage:{" "}
              {project.doc_coverage_score != null
                ? `${Math.round(project.doc_coverage_score * 100)}%`
                : "Not yet indexed"}
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          {prUrl && (
            <a
              href={prUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-xl border border-green-700 bg-green-900/40 px-4 py-2 text-sm text-green-300 hover:bg-green-900/70 transition"
            >
              View PR ↗
            </a>
          )}
          {docs && !prUrl && (
            <button
              onClick={handleCreatePR}
              disabled={creatingPR || !!isRunning}
              className="rounded-xl border border-gray-700 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 disabled:opacity-40 transition"
            >
              {creatingPR ? "Creating PR…" : "Open PR on GitHub"}
            </button>
          )}
          <button
            onClick={handleGenerate}
            disabled={generating || !!isRunning}
            className="rounded-xl bg-indigo-600 px-5 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-40 transition"
          >
            {isRunning ? "Generating…" : docs ? "Regenerate" : "Generate Docs"}
          </button>
        </div>
      </header>

      {error && (
        <div className="border-b border-red-800 bg-red-950 px-6 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Task status banner */}
      {task && task.status !== "completed" && (
        <div className="flex items-center gap-3 border-b border-yellow-800 bg-yellow-950/40 px-6 py-3">
          {task.status !== "failed" && (
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-yellow-400 border-t-transparent" />
          )}
          <span className="text-sm text-yellow-300">
            {task.status === "failed"
              ? "Generation failed. Try again."
              : `Status: ${task.status}${task.progress ? ` — ${JSON.stringify(task.progress)}` : ""}`}
          </span>
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar — doc type tabs */}
        <aside className="w-52 shrink-0 border-r border-gray-800 bg-gray-900 py-4">
          <p className="mb-2 px-4 text-xs font-medium uppercase tracking-wider text-gray-500">
            Documents
          </p>
          {DOC_TYPES.map((dt) => {
            const hasDoc = docs?.[dt.id];
            const score = hasDoc?.quality_score;
            return (
              <button
                key={dt.id}
                onClick={() => setActiveDoc(dt.id)}
                className={`flex w-full items-center justify-between px-4 py-2.5 text-sm transition ${
                  activeDoc === dt.id
                    ? "bg-gray-800 text-white"
                    : "text-gray-400 hover:text-white"
                }`}
              >
                <span>{dt.label}</span>
                {score != null && (
                  <span
                    className={`rounded px-1.5 py-0.5 text-xs ${
                      score > 0.7
                        ? "bg-green-900 text-green-300"
                        : score > 0.4
                        ? "bg-yellow-900 text-yellow-300"
                        : "bg-red-900 text-red-300"
                    }`}
                  >
                    {Math.round(score * 100)}%
                  </span>
                )}
              </button>
            );
          })}
        </aside>

        {/* Main content */}
        <main className="flex-1 overflow-y-auto p-6">
          {!task && (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <div className="mb-4 text-5xl">📄</div>
              <p className="mb-2 text-lg font-medium text-gray-300">
                No docs generated yet
              </p>
              <p className="mb-6 text-sm text-gray-500">
                Click &ldquo;Generate Docs&rdquo; to create README, API reference,
                architecture docs, and a getting started guide.
              </p>
              <button
                onClick={handleGenerate}
                disabled={generating}
                className="rounded-xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-40 transition"
              >
                Generate Docs
              </button>
            </div>
          )}

          {task && !docs && (
            <div className="flex h-full items-center justify-center">
              <div className="text-center">
                <div className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
                <p className="text-gray-400">AI is writing your docs…</p>
              </div>
            </div>
          )}

          {docs && activeContent && (
            <div className="mx-auto max-w-3xl">
              {/* Quality header */}
              {activeContent.quality_score != null && (
                <div className="mb-4 flex items-center gap-4 rounded-xl border border-gray-800 bg-gray-900 px-4 py-3">
                  <div>
                    <p className="text-xs text-gray-500">Quality score</p>
                    <p className="text-lg font-bold text-white">
                      {Math.round(activeContent.quality_score * 100)}%
                    </p>
                  </div>
                  {activeContent.issues && activeContent.issues.length > 0 && (
                    <div className="flex-1">
                      <p className="mb-1 text-xs font-medium text-yellow-400">
                        Issues found
                      </p>
                      <ul className="space-y-0.5">
                        {activeContent.issues.map((issue, i) => (
                          <li key={i} className="text-xs text-gray-400">
                            · {issue}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {/* Doc content */}
              <div className="rounded-2xl border border-gray-800 bg-gray-900 p-6">
                <pre className="whitespace-pre-wrap font-mono text-sm leading-relaxed text-gray-200">
                  {activeContent.content ?? "No content generated."}
                </pre>
              </div>
            </div>
          )}

          {docs && !activeContent && (
            <div className="flex h-full items-center justify-center text-gray-500">
              No content for this doc type.
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
