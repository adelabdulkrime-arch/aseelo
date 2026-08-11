"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { LoadingState, SessionErrorState } from "@/components/ui";
import { useAuth } from "@/lib/auth";

export default function IndexPage() {
  const { user, loading, error, retry } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    // Straight to the app. AuthProvider establishes a guest session while
    // A guest session is minted on load, so by here a visitor usually has one.
    // /login is the fallback for when none could be established at all (guests
    // disabled, or rate limited).
    router.replace(user ? "/dashboard" : "/login");
  }, [user, loading, router]);

  if (!loading && !user && error) {
    return <SessionErrorState error={error} onRetry={retry} />;
  }

  return (
    <main className="grid min-h-screen place-items-center">
      <LoadingState />
    </main>
  );
}
