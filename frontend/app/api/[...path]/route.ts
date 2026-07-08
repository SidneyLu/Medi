import { NextRequest, NextResponse } from "next/server";

const apiBaseUrl = process.env.API_BASE_URL ?? "http://api:8000";

async function forward(request: NextRequest, params: { path: string[] }) {
  const target = new URL(`${apiBaseUrl}/${params.path.join("/")}`);
  request.nextUrl.searchParams.forEach((value, key) => target.searchParams.set(key, value));
  const init: RequestInit = {
    method: request.method,
    headers: { "Content-Type": request.headers.get("content-type") ?? "application/json" },
    cache: "no-store"
  };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.text();
  }
  const response = await fetch(target, init);
  const text = await response.text();
  return new NextResponse(text, {
    status: response.status,
    headers: { "Content-Type": response.headers.get("content-type") ?? "application/json" }
  });
}

export async function GET(request: NextRequest, context: { params: { path: string[] } }) {
  return forward(request, context.params);
}

export async function POST(request: NextRequest, context: { params: { path: string[] } }) {
  return forward(request, context.params);
}
