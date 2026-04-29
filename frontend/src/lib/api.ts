const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("docmind_token");
}

export function setAuthToken(token: string) {
  localStorage.setItem("docmind_token", token);
}

export function clearAuthToken() {
  localStorage.removeItem("docmind_token");
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getAuthToken();
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `Request failed: ${res.status}`);
  }

  return res.json();
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export function getGithubOAuthUrl() {
  return `${API_URL}/api/v1/auth/github`;
}

export interface User {
  id: string;
  github_login: string;
  github_name: string | null;
  avatar_url: string | null;
  email: string | null;
  created_at: string;
}

export function getMe(): Promise<User> {
  return request<User>("/api/v1/auth/me");
}

// ── Projects ──────────────────────────────────────────────────────────────────

export interface RepoItem {
  name: string;
  full_name: string;
  private: boolean;
  language: string | null;
  updated_at: string;
}

export interface Project {
  id: string;
  repo_full_name: string;
  repo_name: string;
  repo_owner: string;
  default_branch: string;
  status: string;
  file_count: number;
  chunk_count: number;
  doc_coverage_score: number | null;
  last_indexed_at: string | null;
  created_at: string;
}

export function listAvailableRepos(): Promise<RepoItem[]> {
  return request<RepoItem[]>("/api/v1/projects/available-repos");
}

export function listProjects(): Promise<Project[]> {
  return request<Project[]>("/api/v1/projects");
}

export function getProject(id: string): Promise<Project> {
  return request<Project>(`/api/v1/projects/${id}`);
}

export function createProject(repo_full_name: string, branch = "main"): Promise<Project> {
  return request<Project>("/api/v1/projects", {
    method: "POST",
    body: JSON.stringify({ repo_full_name, branch }),
  });
}

export function deleteProject(id: string): Promise<void> {
  return request<void>(`/api/v1/projects/${id}`, { method: "DELETE" });
}

// ── Queries ───────────────────────────────────────────────────────────────────

export interface QueryResponse {
  answer: string;
  citations: string[];
  confidence: number;
  follow_ups: string[];
  latency_ms: number;
}

export function queryProject(
  projectId: string,
  query: string
): Promise<QueryResponse> {
  return request<QueryResponse>(`/api/v1/projects/${projectId}/query`, {
    method: "POST",
    body: JSON.stringify({ query, channel: "web" }),
  });
}

// ── Agent Tasks ───────────────────────────────────────────────────────────────

export interface AgentTask {
  id: string;
  task_type: string;
  status: string;
  output: Record<string, unknown> | null;
  progress: Record<string, unknown> | null;
}

export function generateDocs(
  projectId: string,
  doc_types = ["readme", "api_reference", "architecture", "getting_started"]
): Promise<AgentTask> {
  return request<AgentTask>(`/api/v1/projects/${projectId}/documents/generate`, {
    method: "POST",
    body: JSON.stringify({ doc_types }),
  });
}

export function createPR(
  projectId: string,
  document_ids: string[]
): Promise<AgentTask> {
  return request<AgentTask>(`/api/v1/projects/${projectId}/documents/create-pr`, {
    method: "POST",
    body: JSON.stringify({ document_ids }),
  });
}

export function getAgentTask(taskId: string): Promise<AgentTask> {
  return request<AgentTask>(`/api/v1/agents/tasks/${taskId}`);
}

// ── Health ────────────────────────────────────────────────────────────────────

export function healthCheck(): Promise<{ status: string }> {
  return request<{ status: string }>("/api/v1/health");
}
