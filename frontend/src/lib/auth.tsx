"use client";

/** JWT session state shared across the app.
 *
 * The token lives in localStorage and is replayed on mount via /api/auth/me,
 * so a refresh keeps the user signed in and a revoked token signs them out.
 */

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { ApiError, api, getToken, setToken } from "./api";
import type { User } from "./types";

export type AuthErrorKind = "rate_limited" | "disabled" | "unknown";

interface AuthValue {
  user: User | null;
  /** True until the stored token has been checked - guards must wait for this. */
  loading: boolean;
  /** Set when no session could be established at all, so the UI has something
   *  concrete to show instead of a spinner with nothing behind it. */
  error: AuthErrorKind | null;
  signIn: (token: string, user: User) => void;
  signOut: () => void;
  refresh: () => Promise<void>;
  /** Re-runs session establishment - what the "retry" button in the guard calls. */
  retry: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

function classifyAuthError(cause: unknown): AuthErrorKind {
  if (cause instanceof ApiError) {
    if (cause.status === 429) return "rate_limited";
    if (cause.status === 403) return "disabled";
  }
  return "unknown";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AuthErrorKind | null>(null);
  const [attempt, setAttempt] = useState(0);
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;

    /** Open the app without a login, when the backend allows it.
     *
     * The session has to come from the server: every API call carries the JWT
     * and the backend reads the user id out of it. A user object invented here
     * would render a dashboard whose every request 401s - the app would look
     * signed in and load nothing.
     *
     * A failure is not fatal, but the caller needs to know *why* there is no
     * session (rate limited vs. disabled vs. something else) so the route
     * guards can show a real message instead of spinning forever. With login
     * restored there is also a real fallback: the visitor can sign in.
     */
    async function start() {
      setError(null);
      try {
        if (getToken()) {
          const me = await api.me();
          if (!cancelled) setUser(me);
          return;
        }
        const session = await api.guest();
        // The token is written even if this effect was cancelled: it is real,
        // the server issued it, and discarding it would mint another guest row
        // on the next mount.
        setToken(session.access_token);
        if (!cancelled) setUser(session.user);
      } catch (cause) {
        setToken(null);
        if (!cancelled) {
          setUser(null);
          setError(classifyAuthError(cause));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void start();
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const retry = useCallback(() => {
    setLoading(true);
    setAttempt((n) => n + 1);
  }, []);

  const signIn = useCallback((token: string, nextUser: User) => {
    setToken(token);
    setUser(nextUser);
  }, []);

  const signOut = useCallback(() => {
    setToken(null);
    setUser(null);
    // Login exists again, so a signed-out caller belongs on the login screen
    // rather than being handed a fresh anonymous session.
    router.replace("/login");
  }, [router]);

  const refresh = useCallback(async () => {
    setUser(await api.me());
  }, []);

  const value = useMemo<AuthValue>(
    () => ({ user, loading, error, signIn, signOut, refresh, retry }),
    [user, loading, error, signIn, signOut, refresh, retry],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
