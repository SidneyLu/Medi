"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getAccessToken } from "@/lib/api/client";

/** Root entry: send users to login or dashboard. Middleware also enforces this. */
export default function Home() {
  const router = useRouter();

  useEffect(() => {
    router.replace(getAccessToken() ? "/dashboard" : "/login");
  }, [router]);

  return null;
}
