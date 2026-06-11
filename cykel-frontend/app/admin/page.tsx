"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { API_BASE } from "@/lib/api";

type Article = {
  id: string;
  slug: string;
  title: string;
  excerpt: string | null;
  category: string;
  author: string;
  image_url: string | null;
  published_at: string | null;
  created_at: string | null;
  source_url: string | null;
};

const CATEGORY_LABELS: Record<string, string> = {
  resultater: "Resultater",
  startliste: "Startliste",
  transfer: "Transfer",
  profil: "Profil",
  analyse: "Analyse",
  generelt: "Nyheder",
  race_report: "Løbsrapport",
  startlist: "Startliste",
  general: "Nyheder",
  interview: "Interview",
  analysis: "Analyse",
};

const CATEGORY_COLORS: Record<string, string> = {
  race_report: "bg-red-500/15 text-red-400 border-red-500/30",
  resultater: "bg-red-500/15 text-red-400 border-red-500/30",
  startliste: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  startlist: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  transfer: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  profil: "bg-purple-500/15 text-purple-400 border-purple-500/30",
  interview: "bg-purple-500/15 text-purple-400 border-purple-500/30",
  analyse: "bg-orange-500/15 text-orange-400 border-orange-500/30",
  analysis: "bg-orange-500/15 text-orange-400 border-orange-500/30",
  generelt: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  general: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
};

type Tab = "draft" | "published" | "rejected";


export default function AdminPage() {
  const [adminKey, setAdminKey] = useState<string>("");
  const [keyInput, setKeyInput] = useState("");
  const [loginError, setLoginError] = useState(false);
  const [loading, setLoading] = useState(false);
  const [articles, setArticles] = useState<Article[]>([]);
  const [tab, setTab] = useState<Tab>("draft");
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // Feedback panel state
  const [feedbackOpen, setFeedbackOpen] = useState<string | null>(null);
  const [feedbackTexts, setFeedbackTexts] = useState<Record<string, string>>({});
  const [editLoading, setEditLoading] = useState<string | null>(null);
  const [editError, setEditError] = useState<string | null>(null);
  const feedbackRef = useRef<HTMLTextAreaElement>(null);
  const [igPosting, setIgPosting] = useState(false);
  const [igResult, setIgResult] = useState<{ ok: boolean; message?: string; error?: string } | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    const saved = localStorage.getItem("adminKey");
    if (saved) setAdminKey(saved);
  }, []);

  const fetchArticles = useCallback(async (key: string, status: Tab) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/admin/articles?status=${status}&limit=100`, {
        headers: { "x-admin-key": key },
      });
      if (res.status === 401) {
        localStorage.removeItem("adminKey");
        setAdminKey("");
        return;
      }
      const data = await res.json();
      setArticles(Array.isArray(data) ? data : []);
    } catch {
      setArticles([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (adminKey) fetchArticles(adminKey, tab);
  }, [adminKey, tab, fetchArticles]);

  // Focus textarea when feedback panel opens
  useEffect(() => {
    if (feedbackOpen && feedbackRef.current) {
      feedbackRef.current.focus();
    }
  }, [feedbackOpen]);

  const handleLogin = async () => {
    setLoginError(false);
    const res = await fetch(`${API_BASE}/admin/articles?status=draft&limit=1`, {
      headers: { "x-admin-key": keyInput },
    });
    if (res.ok) {
      localStorage.setItem("adminKey", keyInput);
      setAdminKey(keyInput);
    } else {
      setLoginError(true);
    }
  };

  const doAction = async (id: string, action: "approve" | "reject" | "delete") => {
    setActionLoading(id + action);
    try {
      let res: Response;
      if (action === "delete") {
        res = await fetch(`${API_BASE}/admin/articles/${id}`, {
          method: "DELETE",
          headers: { "x-admin-key": adminKey },
        });
      } else {
        res = await fetch(`${API_BASE}/admin/articles/${id}/${action}`, {
          method: "PATCH",
          headers: { "x-admin-key": adminKey },
        });
      }
      if (res.ok) {
        setArticles((prev) => prev.filter((a) => a.id !== id));
        setFeedbackOpen(null);
      }
    } finally {
      setActionLoading(null);
    }
  };

  const doEdit = async (id: string) => {
    const feedback = feedbackTexts[id]?.trim();
    if (!feedback) return;
    setEditLoading(id);
    setEditError(null);
    try {
      const res = await fetch(`${API_BASE}/admin/articles/${id}/edit`, {
        method: "PATCH",
        headers: { "x-admin-key": adminKey, "Content-Type": "application/json" },
        body: JSON.stringify({ feedback }),
      });
      if (res.ok) {
        setArticles((prev) => prev.filter((a) => a.id !== id));
        setFeedbackOpen(null);
      } else {
        let msg = "Fejl — prøv igen";
        try {
          const err = await res.json();
          if (err.detail) msg = err.detail;
        } catch {}
        setEditError(msg);
      }
    } catch {
      setEditError("Netværksfejl — tjek at Railway kører");
    } finally {
      setEditLoading(null);
    }
  };

  const postDagensNyheder = async () => {
    setIgPosting(true);
    setIgResult(null);
    try {
      const res = await fetch(`${API_BASE}/admin/instagram/post-dagens-nyheder`, {
        method: "POST",
        headers: { "x-admin-key": adminKey, "Content-Type": "application/json" },
        body: JSON.stringify({ article_ids: Array.from(selectedIds) }),
      });
      const data = await res.json();
      setIgResult(data);
    } catch {
      setIgResult({ ok: false, error: "Netværksfejl — tjek at Railway kører" });
    } finally {
      setIgPosting(false);
    }
  };

  const toggleArticle = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const formatDate = (d: string | null) => {
    if (!d) return "—";
    return new Date(d).toLocaleDateString("da-DK", {
      day: "numeric", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  };

  // ── Login ────────────────────────────────────────────────────────────────────
  if (!adminKey) {
    return (
      <div className="min-h-screen flex items-center justify-center px-6">
        <div className="w-full max-w-sm">
          <h1 className="font-display text-4xl tracking-widest text-white mb-2">Admin</h1>
          <p className="text-sm text-slate-500 mb-8">Klassementet · Artikel-godkendelse</p>
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

  // ── Dashboard ────────────────────────────────────────────────────────────────
  const tabs: { id: Tab; label: string }[] = [
    { id: "draft",     label: "Kladder" },
    { id: "published", label: "Publicerede" },
    { id: "rejected",  label: "Afviste" },
  ];

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="font-display text-3xl tracking-widest text-white">Admin</h1>
          <p className="text-xs text-slate-500 mt-1">Artikel-godkendelse · Klassementet</p>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/nyheder" className="text-xs text-slate-600 hover:text-emerald-400 transition-colors">
            Se nyheder →
          </Link>
          <button
            onClick={() => { localStorage.removeItem("adminKey"); setAdminKey(""); }}
            className="text-xs text-slate-600 hover:text-red-400 transition-colors px-3 py-1.5 border border-slate-800 rounded-lg"
          >
            Log ud
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-slate-800 pb-0">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => { setTab(t.id); setSelectedIds(new Set()); setIgResult(null); }}
            className={`px-4 py-2.5 text-sm rounded-t-lg transition-colors -mb-px border-b-2 ${
              tab === t.id
                ? "text-white font-medium border-emerald-500"
                : "text-slate-500 hover:text-slate-300 border-transparent"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Artikel-liste */}
      {loading ? (
        <div className="py-16 text-center">
          <div className="w-6 h-6 border-2 border-slate-700 border-t-emerald-400 rounded-full animate-spin mx-auto" />
        </div>
      ) : articles.length === 0 ? (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-12 text-center">
          <p className="text-slate-500 text-sm">
            {tab === "draft" ? "Ingen kladder — kør ai_news_processor.py for at generere nye artikler." :
             tab === "published" ? "Ingen publicerede artikler endnu." :
             "Ingen afviste artikler."}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {articles.map((article) => {
            const isFeedbackOpen = feedbackOpen === article.id;
            const feedbackText = feedbackTexts[article.id] ?? "";
            const isEditLoading = editLoading === article.id;
            const isSelected = tab === "published" && selectedIds.has(article.id);

            return (
              <div
                key={article.id}
                className={`rounded-2xl border transition-colors overflow-hidden ${
                  isSelected
                    ? "border-purple-500/40 bg-purple-950/20"
                    : "border-slate-800/80 bg-slate-900/40 hover:border-slate-700"
                }`}
              >
                <div className="p-5">
                  <div className="flex items-start gap-4">
                    {/* Instagram-checkbox på published-tab */}
                    {tab === "published" && (
                      <button
                        onClick={() => toggleArticle(article.id)}
                        className={`flex-shrink-0 mt-0.5 w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${
                          isSelected
                            ? "border-purple-400 bg-purple-500/30 text-purple-300"
                            : "border-slate-700 hover:border-purple-500/50"
                        }`}
                      >
                        {isSelected && <span className="text-[10px] font-bold leading-none">✓</span>}
                      </button>
                    )}
                    {/* Thumbnail */}
                    {article.image_url && (
                      <div className="flex-shrink-0 w-16 h-16 rounded-lg overflow-hidden border border-slate-800">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={article.image_url} alt="" className="w-full h-full object-cover object-top" />
                      </div>
                    )}

                    {/* Indhold */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                        <span className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${
                          CATEGORY_COLORS[article.category] ?? "bg-slate-800 text-slate-400 border-slate-700"
                        }`}>
                          {CATEGORY_LABELS[article.category] ?? article.category}
                        </span>
                        <span className="text-[10px] text-slate-600">
                          {article.author} · {formatDate(article.created_at ?? article.published_at)}
                        </span>
                      </div>

                      <h2 className="text-sm font-semibold text-slate-100 leading-snug mb-1">
                        {article.title}
                      </h2>

                      {article.excerpt && (
                        <p className="text-xs text-slate-500 line-clamp-2 leading-relaxed">
                          {article.excerpt}
                        </p>
                      )}

                      {article.source_url && (
                        <a
                          href={article.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[10px] text-slate-700 hover:text-slate-500 transition-colors mt-1 inline-block"
                        >
                          Kilde →
                        </a>
                      )}
                    </div>
                  </div>

                  {/* Handlinger */}
                  <div className="flex items-center gap-2 mt-4 pt-4 border-t border-slate-800/60">
                    <Link
                      href={`/nyheder/${article.slug}`}
                      target="_blank"
                      className="text-xs text-slate-500 hover:text-slate-300 transition-colors px-3 py-1.5 border border-slate-800 rounded-lg"
                    >
                      Forhåndsvis →
                    </Link>

                    {/* Feedback-knap — vises på alle tabs */}
                    <button
                      onClick={() => {
                        setFeedbackOpen(isFeedbackOpen ? null : article.id);
                        setEditError(null);
                      }}
                      disabled={actionLoading !== null || isEditLoading}
                      className={`text-xs transition-colors px-3 py-1.5 border rounded-lg disabled:opacity-50 ${
                        isFeedbackOpen
                          ? "text-amber-400 border-amber-500/30 bg-amber-500/10"
                          : "text-slate-500 hover:text-amber-400 border-slate-800 hover:border-amber-500/30"
                      }`}
                    >
                      Ret med feedback
                    </button>

                    <div className="flex-1" />

                    {tab === "draft" && (
                      <>
                        <button
                          onClick={() => doAction(article.id, "reject")}
                          disabled={actionLoading !== null || isEditLoading}
                          className="text-xs text-red-400 hover:text-red-300 transition-colors px-3 py-1.5 border border-red-500/20 hover:border-red-500/40 rounded-lg disabled:opacity-50"
                        >
                          {actionLoading === article.id + "reject" ? "..." : "Afvis"}
                        </button>
                        <button
                          onClick={() => doAction(article.id, "approve")}
                          disabled={actionLoading !== null || isEditLoading}
                          className="text-xs text-emerald-400 hover:text-white bg-emerald-500/10 hover:bg-emerald-500 transition-all px-4 py-1.5 border border-emerald-500/30 rounded-lg font-medium disabled:opacity-50"
                        >
                          {actionLoading === article.id + "approve" ? "..." : "Godkend →"}
                        </button>
                      </>
                    )}

                    {tab === "published" && (
                      <button
                        onClick={() => doAction(article.id, "reject")}
                        disabled={actionLoading !== null || isEditLoading}
                        className="text-xs text-slate-500 hover:text-red-400 transition-colors px-3 py-1.5 border border-slate-800 rounded-lg disabled:opacity-50"
                      >
                        {actionLoading === article.id + "reject" ? "..." : "Afpublicér"}
                      </button>
                    )}

                    {tab === "rejected" && (
                      <>
                        <button
                          onClick={() => doAction(article.id, "delete")}
                          disabled={actionLoading !== null || isEditLoading}
                          className="text-xs text-red-400/60 hover:text-red-400 transition-colors px-3 py-1.5 border border-slate-800 rounded-lg disabled:opacity-50"
                        >
                          {actionLoading === article.id + "delete" ? "..." : "Slet permanent"}
                        </button>
                        <button
                          onClick={() => doAction(article.id, "approve")}
                          disabled={actionLoading !== null || isEditLoading}
                          className="text-xs text-emerald-400 hover:text-white bg-emerald-500/10 hover:bg-emerald-500 transition-all px-4 py-1.5 border border-emerald-500/30 rounded-lg font-medium disabled:opacity-50"
                        >
                          {actionLoading === article.id + "approve" ? "..." : "Genaktivér →"}
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {/* Feedback-panel */}
                {isFeedbackOpen && (
                  <div className="border-t border-amber-500/20 bg-amber-950/20 px-5 py-4">
                    <p className="text-[10px] text-amber-400/70 uppercase tracking-widest mb-2">
                      Feedback til Claude — artiklen rettes og publiceres automatisk
                    </p>
                    <textarea
                      ref={feedbackRef}
                      value={feedbackText}
                      onChange={(e) =>
                        setFeedbackTexts((prev) => ({ ...prev, [article.id]: e.target.value }))
                      }
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) doEdit(article.id);
                      }}
                      placeholder="Fx: Skift 'dansk' til 'fransk', fjern overflødige links, tilføj afsnit om..."
                      rows={3}
                      className="w-full bg-slate-900/80 border border-slate-700 rounded-xl px-4 py-3 text-white placeholder:text-slate-600 outline-none focus:border-amber-500/50 text-xs resize-none leading-relaxed"
                    />
                    <div className="flex items-center gap-2 mt-2">
                      {editError && (
                        <span className="text-xs text-red-400">{editError}</span>
                      )}
                      <div className="flex-1" />
                      <span className="text-[10px] text-slate-600">⌘↵ for at sende</span>
                      <button
                        onClick={() => setFeedbackOpen(null)}
                        className="text-xs text-slate-600 hover:text-slate-400 transition-colors px-3 py-1.5"
                      >
                        Annuller
                      </button>
                      <button
                        onClick={() => doEdit(article.id)}
                        disabled={!feedbackText.trim() || isEditLoading}
                        className="text-xs text-amber-400 hover:text-white bg-amber-500/10 hover:bg-amber-500 transition-all px-4 py-1.5 border border-amber-500/30 rounded-lg font-medium disabled:opacity-40"
                      >
                        {isEditLoading ? (
                          <span className="flex items-center gap-1.5">
                            <span className="w-3 h-3 border border-amber-400/60 border-t-amber-400 rounded-full animate-spin" />
                            Claude retter...
                          </span>
                        ) : "Send til Claude & Publicer →"}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Instagram sticky bar — vises kun når artikler er valgt på published-tab */}
      {tab === "published" && selectedIds.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-4 px-5 py-3 rounded-2xl border border-purple-500/30 bg-slate-950/95 backdrop-blur shadow-2xl shadow-purple-950/40">
          <span className="text-xs text-slate-400">
            <span className="text-white font-medium">{selectedIds.size}</span> artikel{selectedIds.size !== 1 ? "r" : ""} valgt
          </span>
          <button
            onClick={() => setSelectedIds(new Set())}
            className="text-xs text-slate-600 hover:text-slate-400 transition-colors"
          >
            Ryd
          </button>
          <button
            onClick={postDagensNyheder}
            disabled={igPosting}
            className="text-sm text-white bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 transition-all px-4 py-1.5 rounded-xl font-medium disabled:opacity-50 flex items-center gap-2"
          >
            {igPosting ? (
              <>
                <span className="w-3 h-3 border border-white/40 border-t-white rounded-full animate-spin" />
                Genererer og poster...
              </>
            ) : (
              "Post til Instagram →"
            )}
          </button>
          {igResult && (
            <span className={`text-xs ${igResult.ok ? "text-emerald-400" : "text-red-400"}`}>
              {igResult.ok ? `✓ ${igResult.message}` : `✗ ${igResult.error}`}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
