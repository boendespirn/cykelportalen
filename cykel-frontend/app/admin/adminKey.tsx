"use client";

import { useState, useEffect, useCallback } from "react";
import { API_BASE } from "@/lib/api";

/**
 * Admin-nøglen ligger i localStorage under "adminKey" — samme nøgle som
 * /admin-siden allerede sætter, så man kun logger ind ét sted.
 *
 * Ligger i en delt fil, fordi pipeline-siderne ellers skulle gentage
 * login-skærm og nøglehåndtering ord for ord, og de kopier ville uvægerligt
 * komme ud af trit.
 */
export function useAdminKey() {
  const [adminKey, setAdminKey] = useState<string>("");
  const [keyInput, setKeyInput] = useState<string>("");
  const [loginError, setLoginError] = useState(false);
  const [checked, setChecked] = useState(false);

  const verify = useCallback(async (key: string) => {
    try {
      const res = await fetch(`${API_BASE}/admin/pipelines/jobs`, {
        headers: { "x-admin-key": key },
      });
      return res.ok;
    } catch {
      return false;
    }
  }, []);

  useEffect(() => {
    const saved = localStorage.getItem("adminKey");
    if (!saved) {
      setChecked(true);
      return;
    }
    verify(saved).then((ok) => {
      if (ok) setAdminKey(saved);
      else localStorage.removeItem("adminKey");
      setChecked(true);
    });
  }, [verify]);

  const login = useCallback(async () => {
    const ok = await verify(keyInput);
    if (ok) {
      localStorage.setItem("adminKey", keyInput);
      setAdminKey(keyInput);
      setLoginError(false);
    } else {
      setLoginError(true);
    }
  }, [keyInput, verify]);

  const logout = useCallback(() => {
    localStorage.removeItem("adminKey");
    setAdminKey("");
  }, []);

  return { adminKey, keyInput, setKeyInput, loginError, login, logout, checked };
}

/** GET mod et admin-endpoint. Returnerer null ved fejl, så kaldsstedet kan
 *  vise "kunne ikke hentes" i stedet for at krakelere. */
export async function adminGet<T>(path: string, key: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, { headers: { "x-admin-key": key } });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export async function adminPost<T>(path: string, key: string, body: unknown): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "x-admin-key": key, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

/** "for 3 min siden" — dashboardets vigtigste oplysning er, hvor gammelt noget er. */
export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "aldrig";
  const then = new Date(iso).getTime();
  const secs = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (secs < 60) return "lige nu";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `for ${mins} min siden`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `for ${hours} ${hours === 1 ? "time" : "timer"} siden`;
  const days = Math.round(hours / 24);
  if (days < 30) return `for ${days} ${days === 1 ? "dag" : "dage"} siden`;
  return new Date(iso).toLocaleDateString("da-DK", { day: "numeric", month: "short", year: "numeric" });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("da-DK", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

/** Login-skærm, delt af begge pipeline-sider. */
export function AdminLogin(props: {
  keyInput: string;
  setKeyInput: (v: string) => void;
  loginError: boolean;
  onLogin: () => void;
}) {
  return (
    <div className="min-h-screen flex items-center justify-center px-6">
      <div className="w-full max-w-sm">
        <h1 className="font-display text-4xl tracking-widest text-white mb-2">Admin</h1>
        <p className="text-sm text-slate-500 mb-8">Klassementet · Pipelines</p>
        <div className="space-y-3">
          <input
            type="password"
            value={props.keyInput}
            onChange={(e) => props.setKeyInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && props.onLogin()}
            placeholder="Admin-nøgle"
            className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-white placeholder:text-slate-600 outline-none focus:border-emerald-500/60 text-sm"
          />
          {props.loginError && (
            <p className="text-xs text-red-400">Forkert nøgle — tjek ADMIN_KEY i .env</p>
          )}
          <button
            onClick={props.onLogin}
            className="w-full bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl py-3 text-sm font-medium transition-colors"
          >
            Log ind
          </button>
        </div>
      </div>
    </div>
  );
}
