import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET() {
  const API_BASE =
    process.env.NEXT_PUBLIC_API_URL ??
    "https://cykelportalen-production.up.railway.app";

  let fetchResult: unknown = null;
  let fetchError: string | null = null;

  try {
    const res = await fetch(`${API_BASE}/races`, {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    const text = await res.text();
    fetchResult = { status: res.status, preview: text.slice(0, 300) };
  } catch (e) {
    fetchError = String(e);
  }

  return NextResponse.json({
    api_base: API_BASE,
    env_var: process.env.NEXT_PUBLIC_API_URL ?? "(ikke sat)",
    fetch_result: fetchResult,
    fetch_error: fetchError,
  });
}
