export const dynamic = "force-dynamic";

import Link from "next/link";
import { API_BASE } from "@/lib/api";

type Article = {
  slug: string;
  title: string;
  excerpt: string | null;
  category: string;
  author: string;
  image_url: string | null;
  published_at: string;
  races: { name: string; slug: string } | null;
};

const CATEGORY_LABELS: Record<string, string> = {
  race_report: "Løbsrapport",
  startlist:   "Startliste",
  general:     "Nyheder",
  interview:   "Interview",
  analysis:    "Analyse",
};

async function getArticles(): Promise<Article[]> {
  try {
    const res = await fetch(`${API_BASE}/news?advertorial=false&limit=40`, { cache: "no-store" });
    if (!res.ok) return [];
    return res.json();
  } catch { return []; }
}

function formatDate(d: string): string {
  return new Date(d).toLocaleDateString("da-DK", { day: "numeric", month: "long", year: "numeric" });
}

export default async function NyhederPage() {
  const articles = await getArticles();

  return (
    <div className="mx-auto max-w-5xl px-6 py-12">
      <header className="mb-14">
        <p className="text-xs uppercase tracking-[0.25em] text-emerald-400 mb-4">UCI WorldTour · 2026</p>
        <h1 className="font-display text-7xl sm:text-9xl tracking-wide leading-none text-white">
          Nyheder
        </h1>
        <p className="mt-5 text-slate-400 text-sm max-w-sm leading-relaxed">
          Seneste nyt fra professionel cykling — løbsresultater, startlister og analyser.
        </p>
      </header>

      {articles.length === 0 ? (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-16 text-center">
          <p className="text-slate-500 text-sm mb-2">Nyheder er på vej.</p>
          <p className="text-slate-700 text-xs">Redaktionelle artikler publiceres løbende i sæsonen.</p>
        </div>
      ) : (
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {articles.map((article) => (
            <Link
              key={article.slug}
              href={`/nyheder/${article.slug}`}
              className="group flex flex-col rounded-2xl border border-slate-800/80 bg-slate-900/40 overflow-hidden hover:border-emerald-500/30 hover:bg-slate-900 transition-all duration-150"
            >
              {article.image_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={article.image_url} alt="" className="w-full h-44 object-cover" />
              ) : (
                <div className="w-full h-44 bg-slate-800/60 flex items-center justify-center">
                  <span className="text-4xl opacity-20">🚴</span>
                </div>
              )}
              <div className="p-5 flex flex-col flex-1">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-[10px] uppercase tracking-widest text-emerald-400 font-medium">
                    {CATEGORY_LABELS[article.category] ?? article.category}
                  </span>
                  {article.races && (
                    <span className="text-[10px] text-slate-600">· {article.races.name}</span>
                  )}
                </div>
                <h2 className="text-slate-100 font-semibold text-sm leading-snug mb-2 group-hover:text-emerald-400 transition-colors flex-1">
                  {article.title}
                </h2>
                {article.excerpt && (
                  <p className="text-xs text-slate-500 leading-relaxed line-clamp-2 mb-3">
                    {article.excerpt}
                  </p>
                )}
                <p className="text-xs text-slate-700 mt-auto">{formatDate(article.published_at)}</p>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
