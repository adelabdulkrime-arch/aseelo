"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { LoadingState } from "@/components/ui";
import { useAuth } from "@/lib/auth";

export default function IndexPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    // Straight to the app. AuthProvider establishes a guest session while
    // `loading` is true, so by here a visitor with no account usually has one.
    // /login remains reachable, just never forced: it is only the fallback for
    // when a session could not be established at all (guests disabled, or rate
    // limited).
    router.replace(user ? "/dashboard" : "/login");
  }, [user, loading, router]);

  return (
    <main className="grid min-h-screen place-items-center">
      <LoadingState />
    </main>
  );
}
