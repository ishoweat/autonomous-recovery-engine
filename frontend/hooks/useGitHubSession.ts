"use client";

import { useState, useEffect, useCallback } from "react";
import { API_BASE_URL } from "@/lib/api";

export interface GitHubUser {
  user_id: number | string;
  username: string;
  display_name?: string;
  avatar_url?: string;
}

export interface GitHubRepo {
  id: number;
  name: string;
  full_name: string;
  owner: string;
  owner_avatar?: string;
  html_url: string;
  default_branch: string;
  private: boolean;
  description?: string;
}

export function useGitHubSession() {
  const [user, setUser] = useState<GitHubUser | null>(null);
  const [authenticated, setAuthenticated] = useState<boolean>(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [ttlRemaining, setTtlRemaining] = useState<number>(0);
  const [repositories, setRepositories] = useState<GitHubRepo[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Check URL params for session_id after OAuth redirect
  useEffect(() => {
    if (typeof window !== "undefined") {
      const urlParams = new URLSearchParams(window.location.search);
      const querySessId = urlParams.get("session_id");
      if (querySessId) {
        localStorage.setItem("session_id", querySessId);
        setSessionId(querySessId);
        // Clean URL parameter without reload
        const newUrl = window.location.pathname;
        window.history.replaceState({}, document.title, newUrl);
      } else {
        const storedSessId = localStorage.getItem("session_id");
        if (storedSessId) {
          setSessionId(storedSessId);
        }
      }
    }
  }, []);

  const fetchSession = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const activeSessId = sessionId || (typeof window !== "undefined" ? localStorage.getItem("session_id") : null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (activeSessId) {
        headers["X-Session-ID"] = activeSessId;
        headers["Authorization"] = `Bearer ${activeSessId}`;
      }

      const res = await fetch(`${API_BASE_URL}/auth/github/me`, {
        headers,
        credentials: "include",
      });

      if (res.ok) {
        const data = await res.json();
        if (data.authenticated && data.session) {
          setAuthenticated(true);
          setUser({
            user_id: data.session.user_id,
            username: data.session.username,
            display_name: data.session.display_name,
            avatar_url: data.session.avatar_url,
          });
          setTtlRemaining(data.session.ttl_remaining || 0);
          setSessionId(data.session.session_id);
          if (typeof window !== "undefined") {
            localStorage.setItem("session_id", data.session.session_id);
          }
        } else {
          setAuthenticated(false);
          setUser(null);
          setTtlRemaining(0);
        }
      } else {
        setAuthenticated(false);
        setUser(null);
      }
    } catch (err: any) {
      console.error("Failed to check GitHub session:", err);
      setAuthenticated(false);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  const fetchUserRepos = useCallback(async () => {
    try {
      const activeSessId = sessionId || (typeof window !== "undefined" ? localStorage.getItem("session_id") : null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (activeSessId) {
        headers["X-Session-ID"] = activeSessId;
        headers["Authorization"] = `Bearer ${activeSessId}`;
      }

      const res = await fetch(`${API_BASE_URL}/api/v1/github/user-repos`, {
        headers,
        credentials: "include",
      });

      if (res.ok) {
        const data = await res.json();
        if (data.repositories) {
          setRepositories(data.repositories);
          if (data.repositories.length > 0 && !selectedRepo) {
            const first = data.repositories[0];
            const defaultUrl = first.html_url || `https://github.com/${first.full_name}`;
            setSelectedRepo(defaultUrl);
          }
        }
      } else {
        setRepositories([]);
      }
    } catch (err) {
      console.error("Failed to fetch user repositories:", err);
      setRepositories([]);
    }
  }, [sessionId, selectedRepo]);

  useEffect(() => {
    fetchSession();
  }, [fetchSession]);

  useEffect(() => {
    if (authenticated) {
      fetchUserRepos();
    } else {
      setRepositories([]);
    }
  }, [authenticated, fetchUserRepos]);

  // Live countdown timer for TTL
  useEffect(() => {
    if (!authenticated || ttlRemaining <= 0) return;
    const interval = setInterval(() => {
      setTtlRemaining((prev) => {
        if (prev <= 1) {
          setAuthenticated(false);
          setUser(null);
          setRepositories([]);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [authenticated, ttlRemaining]);

  const loginWithToken = async (token: string, ttl: number = 3600) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/auth/github/token-login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ token, ttl }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to log in with GitHub token.");
      }

      const data = await res.json();
      if (data.authenticated && data.session) {
        setAuthenticated(true);
        setUser({
          user_id: data.session.user_id,
          username: data.session.username,
          display_name: data.session.display_name,
          avatar_url: data.session.avatar_url,
        });
        setTtlRemaining(data.session.ttl_remaining || ttl);
        setSessionId(data.session.session_id);
        if (typeof window !== "undefined") {
          localStorage.setItem("session_id", data.session.session_id);
        }
        // Fetch repositories immediately
        await fetchUserRepos();
      }
      return data;
    } catch (err: any) {
      setError(err.message || "Token login failed.");
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const logout = async () => {
    setLoading(true);
    try {
      const activeSessId = sessionId || (typeof window !== "undefined" ? localStorage.getItem("session_id") : null);
      const headers: Record<string, string> = {};
      if (activeSessId) {
        headers["X-Session-ID"] = activeSessId;
        headers["Authorization"] = `Bearer ${activeSessId}`;
      }

      await fetch(`${API_BASE_URL}/auth/github/logout`, {
        method: "POST",
        headers,
        credentials: "include",
      });
    } catch (err) {
      console.error("Logout request failed:", err);
    } finally {
      setAuthenticated(false);
      setUser(null);
      setSessionId(null);
      setTtlRemaining(0);
      setRepositories([]);
      setSelectedRepo("");
      if (typeof window !== "undefined") {
        localStorage.removeItem("session_id");
        localStorage.removeItem("connected_repo");
      }
      setLoading(false);
    }
  };

  const formatTTL = (seconds: number) => {
    if (seconds <= 0) return "Expired";
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}m ${secs < 10 ? "0" : ""}${secs}s`;
  };

  return {
    user,
    authenticated,
    sessionId,
    ttlRemaining,
    formatTTL: () => formatTTL(ttlRemaining),
    repositories,
    selectedRepo,
    setSelectedRepo,
    loading,
    error,
    loginWithToken,
    logout,
    refreshSession: fetchSession,
    refreshRepos: fetchUserRepos,
  };
}
