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
    // `loading` is true, so by here a visitor almost always has one. There is
    // no login page: a visitor with no session just stays here, loading.
    if (user) router.replace("/dashboard");
  }, [user, loading, router]);

  return (
    <main className="grid min-h-screen place-items-center">
      <LoadingState />
    </main>
  );
}
