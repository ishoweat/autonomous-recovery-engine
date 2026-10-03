"use client";

import React, { useState } from "react";
import { useGitHubSession } from "@/hooks/useGitHubSession";
import { API_BASE_URL } from "@/lib/api";
import {
  Github,
  LogOut,
  Clock,
  CheckCircle2,
  FolderGit2,
  Key,
  ShieldCheck,
  ChevronDown,
  Loader2,
} from "lucide-react";

interface GitHubSessionWidgetProps {
  onSelectRepo?: (repoUrl: string, repoData?: any) => void;
  currentRepoUrl?: string;
  className?: string;
}

export function GitHubSessionWidget({
  onSelectRepo,
  currentRepoUrl,
  className = "",
}: GitHubSessionWidgetProps) {
  const {
    user,
    authenticated,
    formatTTL,
    repositories,
    selectedRepo,
    setSelectedRepo,
    loading,
    error,
    loginWithToken,
    logout,
  } = useGitHubSession();

  const [showTokenInput, setShowTokenInput] = useState(false);
  const [token, setToken] = useState("");
  const [tokenSubmitting, setTokenSubmitting] = useState(false);
  const [tokenError, setTokenError] = useState<string | null>(null);

  const handleTokenSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token.trim()) return;
    setTokenSubmitting(true);
    setTokenError(null);
    try {
      await loginWithToken(token.trim());
      setShowTokenInput(false);
      setToken("");
    } catch (err: any) {
      setTokenError(err.message || "Failed to authenticate token.");
    } finally {
      setTokenSubmitting(false);
    }
  };

  const handleRepoChange = (repoUrl: string) => {
    setSelectedRepo(repoUrl);
    const foundRepo = repositories.find(
      (r) => r.html_url === repoUrl || `https://github.com/${r.full_name}` === repoUrl
    );
    if (onSelectRepo) {
      onSelectRepo(repoUrl, foundRepo);
    }
  };

  if (loading && !authenticated) {
    return (
      <div className={`flex items-center gap-2 text-xs text-on-surface/60 ${className}`}>
        <Loader2 className="w-3.5 h-3.5 animate-spin text-primary" />
        Checking GitHub session...
      </div>
    );
  }

  return (
    <div className={`bg-surface-container border border-white/[0.08] rounded-xl p-4 shadow-sm ${className}`}>
      {authenticated && user ? (
        <div className="flex flex-col gap-3">
          {/* User Info Header & Session Badge */}
          <div className="flex items-center justify-between gap-3 pb-3 border-b border-white/[0.06]">
            <div className="flex items-center gap-2.5">
              {user.avatar_url ? (
                <img
                  src={user.avatar_url}
                  alt={user.username}
                  className="w-8 h-8 rounded-full border border-primary/30 object-cover"
                />
              ) : (
                <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center border border-primary/30">
                  <Github className="w-4 h-4 text-primary" />
                </div>
              )}
              <div>
                <div className="flex items-center gap-1.5 font-mono text-sm font-semibold text-on-surface">
                  <span>@{user.username}</span>
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                </div>
                <div className="flex items-center gap-1 text-[11px] text-emerald-400 font-mono">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  <span>Redis Live Session</span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5 bg-primary/10 border border-primary/20 text-primary-fixed px-2.5 py-1 rounded-md text-xs font-mono">
                <Clock className="w-3.5 h-3.5" />
                <span>{formatTTL()}</span>
              </div>

              <button
                onClick={logout}
                title="Logout & Destroy Redis Session"
                className="flex items-center gap-1 text-xs font-semibold text-rose-400 hover:text-rose-300 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 px-2.5 py-1 rounded-md transition-all"
              >
                <LogOut className="w-3 h-3" />
                <span>Logout</span>
              </button>
            </div>
          </div>

          {/* User Repositories Selector */}
          <div>
            <label className="block text-xs font-semibold text-on-surface/80 mb-1.5 font-mono flex items-center gap-1.5">
              <FolderGit2 className="w-3.5 h-3.5 text-primary" />
              <span>Select Repository ({repositories.length} available)</span>
            </label>

            {repositories.length > 0 ? (
              <div className="relative">
                <select
                  value={currentRepoUrl || selectedRepo}
                  onChange={(e) => handleRepoChange(e.target.value)}
                  className="w-full bg-surface-container-low border border-white/[0.1] rounded-lg px-3 py-2 text-sm text-on-surface font-mono appearance-none pr-8 focus:outline-none focus:border-primary cursor-pointer"
                >
                  <option value="" disabled>
                    -- Choose one of your GitHub repositories --
                  </option>
                  {repositories.map((repo) => (
                    <option
                      key={repo.id}
                      value={repo.html_url || `https://github.com/${repo.full_name}`}
                    >
                      {repo.full_name} {repo.private ? "🔒 (Private)" : "🌐 (Public)"}
                    </option>
                  ))}
                </select>
                <ChevronDown className="w-4 h-4 text-on-surface/50 absolute right-2.5 top-2.5 pointer-events-none" />
              </div>
            ) : (
              <div className="text-xs text-on-surface/60 font-mono py-2 bg-surface-container-low rounded-lg px-3 border border-dashed border-white/10">
                No repositories found for @{user.username}. Ensure your token has 'repo' scope.
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-on-surface font-semibold text-sm">
              <Github className="w-4 h-4 text-primary" />
              <span>GitHub Account Authentication</span>
            </div>
            <span className="text-[11px] text-amber-400 bg-amber-400/10 border border-amber-400/20 px-2 py-0.5 rounded font-mono">
              Session Required
            </span>
          </div>

          <p className="text-xs text-on-surface/70">
            Log in to create a temporary, isolated GitHub Redis session to view and analyze only your repositories.
          </p>

          {!showTokenInput ? (
            <div className="flex gap-2">
              <button
                onClick={() => (window.location.href = `${API_BASE_URL}/auth/github/login`)}
                className="flex-1 bg-primary hover:bg-primary/90 text-white font-semibold py-2 px-3 rounded-lg text-xs flex items-center justify-center gap-2 transition-all shadow-sm"
              >
                <Github className="w-4 h-4" />
                <span>Connect GitHub Account</span>
              </button>
              <button
                onClick={() => setShowTokenInput(true)}
                className="bg-surface-container-high hover:bg-surface-container-highest text-on-surface border border-white/10 py-2 px-3 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all"
              >
                <Key className="w-3.5 h-3.5 text-amber-400" />
                <span>Use Token</span>
              </button>
            </div>
          ) : (
            <form onSubmit={handleTokenSubmit} className="flex flex-col gap-2">
              <div className="flex gap-2">
                <input
                  type="password"
                  placeholder="Paste GitHub Personal Access Token (ghp_...)"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  className="flex-1 bg-surface-container-low border border-white/10 rounded-lg px-3 py-1.5 text-xs text-on-surface font-mono focus:outline-none focus:border-primary"
                  required
                />
                <button
                  type="submit"
                  disabled={tokenSubmitting || !token.trim()}
                  className="bg-primary text-white font-semibold text-xs px-3 py-1.5 rounded-lg disabled:opacity-50 flex items-center gap-1"
                >
                  {tokenSubmitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Verify"}
                </button>
              </div>
              {tokenError && <span className="text-[11px] text-rose-400">{tokenError}</span>}
              <button
                type="button"
                onClick={() => setShowTokenInput(false)}
                className="text-[11px] text-on-surface/50 hover:text-on-surface text-left font-mono"
              >
                ← Back to GitHub Login
              </button>
            </form>
          )}
        </div>
      )}
    </div>
  );
}
