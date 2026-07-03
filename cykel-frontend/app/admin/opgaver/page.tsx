"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { API_BASE } from "@/lib/api";

type Issue = {
  id: string;
  priority: string;
  status: string;
  owner: string;
  description: string;
};

const STATUS_COLUMNS: { id: string; label: string; color: string }[] = [
  { id: "NY", label: "Ny", color: "border-blue-500/40 text-blue-400" },
  { id: "TILDELT", label: "Tildelt", color: "border-purple-500/40 text-purple-400" },
  { id: "ESKALERET", label: "Eskaleret", color: "border-orange-500/40 text-orange-400" },
  { id: "AFVENTER_EJER", label: "Afventer ejer", color: "border-amber-500/40 text-amber-400" },
  { id: "LØST", label: "Løst", color: "border-emerald-500/40 text-emerald-400" },
  { id: "HENLAGT", label: "Henlagt", color: "border-slate-600/40 text-slate-500" },
];

const PRIORITY_COLORS: Record<string, string> = {
  HØJ: "bg-red-500/15 text-red-400 border-red-500/30",
  MIDDEL: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  LAV: "bg-slate-500/15 text-slate-400 border-slate-500/30",
};

export default function OpgaverPage() {
  const [adminKey, setAdminKey] = useState<string>("");
  const [keyInput, setKeyInput] = useState("");
  const [loginError, setLoginError] = useState(false);
  const [loading, setLoading] = useState(false);
  const [issues, setIssues] = useState<Issue[]>([]);

  useEffect(() => {
    const saved = localStorage.getItem("adminKey");
    if (saved) setAdminKey(saved);
  }, []);

  const fetchIssues = useCallback(async (key: string) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/admin/issues`, {
        headers: { "x-admin-key": key },
      });
      if (res.status === 401) {
        localStorage.removeItem("adminKey");
        setAdminKey("");
        return;
      }
      const data = await res.json();
      setIssues(Array.isArray(data) ? data : []);
    } catch {
      setIssues([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (adminKey) fetchIssues(adminKey);
  }, [adminKey, fetchIssues]);

  const handleLogin = async () => {
    setLoginError(false);
    const res = await fetch(`${API_BASE}/admin/issues`, {
      headers: { "x-admin-key": keyInput },
    });
    if (res.ok) {
      localStorage.setItem("adminKey", keyInput);
      setAdminKey(keyInput);
    } else {
      setLoginError(true);
    }
  };

  // ── Login ────────────────────────────────────────────────────────────────────
  if (!adminKey) {
    return (
      <div className="min-h-screen flex items-center justify-center px-6">
        <div className="w-full max-w-sm">
          <h1 className="font-display text-4xl tracking-widest text-white mb-2">Admin</h1>
          <p className="text-sm text-slate-500 mb-8">Klassementet · Opgaveoverblik</p>
          <div className="space-y-3">
            <input
              type="password"
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleLogin()}
              placeholder="Admin-nøgle"
              className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-white placeholder:text-slate-600 outline-none focus:border-emerald-500/60 text-sm"
            />
            {loginError && (
              <p className="text-xs text-red-400">Forkert nøgle — tjek ADMIN_KEY i .env</p>
            )}
            <button
              onClick={handleLogin}
              className="w-full bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl py-3 text-sm font-medium transition-colors"
            >
              Log ind
            </button>
          </div>
        </div>
      </div>
    );
  }

  const grouped = STATUS_COLUMNS.map((col) => ({
    ...col,
    items: issues
      .filter((i) => i.status === col.id)
      .sort((a, b) => {
        const order: Record<string, number> = { HØJ: 0, MIDDEL: 1, LAV: 2 };
        return (order[a.priority] ?? 3) - (order[b.priority] ?? 3);
      }),
  }));

  return (
    <div className="mx-auto max-w-[1600px] px-6 py-10">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="font-display text-3xl tracking-widest text-white">Opgaver</h1>
          <p className="text-xs text-slate-500 mt-1">Status på tværs af issues.md · Klassementet</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => fetchIssues(adminKey)}
            className="text-xs text-slate-500 hover:text-emerald-400 transition-colors px-3 py-1.5 border border-slate-800 rounded-lg"
          >
            Opdatér
          </button>
          <Link href="/admin" className="text-xs text-slate-600 hover:text-emerald-400 transition-colors">
            ← Artikler
          </Link>
        </div>
      </div>

      {loading ? (
        <div className="py-16 text-center">
          <div className="w-6 h-6 border-2 border-slate-700 border-t-emerald-400 rounded-full animate-spin mx-auto" />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
          {grouped.map((col) => (
            <div key={col.id} className="min-w-0">
              <div className={`flex items-center justify-between border-b-2 pb-2 mb-3 ${col.color}`}>
                <span className="text-xs font-semibold uppercase tracking-wider">{col.label}</span>
                <span className="text-xs text-slate-600">{col.items.length}</span>
              </div>
              <div className="space-y-2">
                {col.items.length === 0 ? (
                  <p className="text-xs text-slate-700 py-4 text-center">—</p>
                ) : (
                  col.items.map((issue) => (
                    <div
                      key={issue.id}
                      className="rounded-xl border border-slate-800/80 bg-slate-900/40 p-3 hover:border-slate-700 transition-colors"
                    >
                      <div className="flex items-center gap-1.5 mb-1.5 flex-wrap">
                        <span className="text-[10px] font-mono text-slate-500">{issue.id}</span>
                        <span
                          className={`text-[9px] px-1.5 py-0.5 rounded-full border font-medium ${
                            PRIORITY_COLORS[issue.priority] ?? "bg-slate-800 text-slate-400 border-slate-700"
                          }`}
                        >
                          {issue.priority}
                        </span>
                      </div>
                      <p className="text-xs text-slate-300 leading-relaxed mb-1.5">{issue.description}</p>
                      <span className="text-[10px] text-slate-600">{issue.owner}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
