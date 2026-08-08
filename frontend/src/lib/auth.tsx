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

import { api, getToken, setToken } from "./api";
import type { User } from "./types";

interface AuthValue {
  user: User | null;
  /** True until the stored token has been checked - guards must wait for this. */
  loading: boolean;
  signIn: (token: string, user: User) => void;
  signOut: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;

    /** Open the app without a login - the only way in.
     *
     * The session has to come from the server: every API call carries the JWT
     * and the backend reads the user id out of it. A user object invented here
     * would render a dashboard whose every request 401s - the app would look
     * signed in and load nothing.
     *
     * A failure is not fatal but there is nowhere to send the caller: if
     * guest sessions are disabled or rate limited, the route guards just show
     * a loading state forever rather than a dead end.
     */
    async function start() {
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
      } catch {
        setToken(null);
        if (!cancelled) setUser(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void start();
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback((token: string, nextUser: User) => {
    setToken(token);
    setUser(nextUser);
  }, []);

  const signOut = useCallback(() => {
    setToken(null);
    setUser(null);
    // No login page to send the caller to: land on "/", which mints a fresh
    // guest session on the next mount since there is no token to replay.
    router.replace("/");
  }, [router]);

  const refresh = useCallback(async () => {
    setUser(await api.me());
  }, []);

  const value = useMemo<AuthValue>(
    () => ({ user, loading, signIn, signOut, refresh }),
    [user, loading, signIn, signOut, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
