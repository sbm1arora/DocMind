"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { getGithubOAuthUrl } from "@/lib/api";

export default function LandingPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && user) {
      router.replace("/dashboard");
    }
  }, [user, loading, router]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-6 text-center">
      {/* Logo */}
      <div className="mb-8 flex items-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-600 text-xl font-bold text-white">
          D
        </div>
        <span className="text-2xl font-semibold tracking-tight text-white">
          DocMind
        </span>
      </div>

      {/* Hero */}
      <h1 className="mb-4 max-w-2xl text-5xl font-bold leading-tight text-white">
        Documentation that stays{" "}
        <span className="text-indigo-400">in sync with your code</span>
      </h1>
      <p className="mb-10 max-w-xl text-lg text-gray-400">
        Connect a GitHub repository. DocMind indexes it, answers your questions,
        and auto-generates up-to-date docs — then opens a PR.
      </p>

      {/* CTA */}
      <a
        href={getGithubOAuthUrl()}
        className="inline-flex items-center gap-3 rounded-xl bg-white px-7 py-4 text-base font-semibold text-gray-900 shadow-lg transition hover:bg-gray-100 active:scale-95"
      >
        <GitHubIcon />
        Continue with GitHub
      </a>

      {/* Features */}
      <div className="mt-20 grid max-w-3xl grid-cols-1 gap-6 text-left sm:grid-cols-3">
        {features.map((f) => (
          <div
            key={f.title}
            className="rounded-2xl border border-gray-800 bg-gray-900 p-6"
          >
            <div className="mb-3 text-2xl">{f.icon}</div>
            <h3 className="mb-1 font-semibold text-white">{f.title}</h3>
            <p className="text-sm text-gray-400">{f.desc}</p>
          </div>
        ))}
      </div>
    </main>
  );
}

const features = [
  {
    icon: "🔍",
    title: "RAG-powered search",
    desc: "Ask any question about your codebase in plain English. Get cited answers in seconds.",
  },
  {
    icon: "✍️",
    title: "Auto-generated docs",
    desc: "README, API reference, architecture docs — written by AI, reviewed by you.",
  },
  {
    icon: "🔄",
    title: "Stays up to date",
    desc: "GitHub webhooks trigger re-indexing on every push. Docs never drift.",
  },
];

function GitHubIcon() {
  return (
    <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24">
      <path
        fillRule="evenodd"
        d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
        clipRule="evenodd"
      />
    </svg>
  );
}
