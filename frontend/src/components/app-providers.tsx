"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { syncAccessTokenCookie } from "@/lib/api/client";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

export function AppProviders({ children }: { children: React.ReactNode }) {
  const [mockReady, setMockReady] = useState(process.env.NEXT_PUBLIC_API_MODE !== "mock");

  useEffect(() => {
    syncAccessTokenCookie();
  }, []);

  useEffect(() => {
    if (process.env.NEXT_PUBLIC_API_MODE !== "mock") return;
    void import("@/lib/api/browser").then(({ worker }) => worker.start({ onUnhandledRequest: "bypass" })).then(() => setMockReady(true));
  }, []);

  return <QueryClientProvider client={queryClient}>{mockReady ? children : <div className="loading"><div className="spinner" /></div>}</QueryClientProvider>;
}
