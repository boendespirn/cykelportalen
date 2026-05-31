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
  resultater:  "Resultater",
  startliste:  "Startliste",
  transfer:    "Transfer",
  profil:      "Profil",
  analyse:     "Analyse",
  generelt:    "Nyheder",
  race_report: "Løbsrapport",
  startlist:   "Startliste",
  general:     "Nyheder",
  interview:   "Interview",
  analysis:    "Analyse",
};

const CATEGORY_COLORS: Record<string, string> = {
  resultater:  "text-emerald-400",
  startliste:  "text-blue-400",
  transfer:    "text-yellow-400",
  profil:      "text-purple-400",
  analyse:     "text-orange-400",
  race_report: "text-red-400",
  interview:   "text-cyan-400",
};

async function getArticles(): Promise<Article[]> {
  try {
    const res = await fetch(`${API_BASE}/news?advertorial=false&limit=40`, { cache: "no-store" });
    if (!res.ok) return [];
    return res.json();
  } catch { return []; }
}

function formatDate(d: string): string {
  return new Date(d).toLocaleDateString("da-DK", { day: "numeric", month: "short", year: "numeric" });
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
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {articles.map((article, i) => {
            const categoryColor = CATEGORY_COLORS[article.category] ?? "text-emerald-400";
            const isLarge = i === 0; // Første artikel er stor

            return (
              <Link
                key={article.slug}
                href={`/nyheder/${article.slug}`}
                className={`group relative overflow-hidden rounded-2xl border border-slate-800/60 hover:border-emerald-500/30 transition-all duration-200 flex flex-col ${
                  isLarge ? "sm:col-span-2 lg:col-span-2" : ""
                }`}
              >
                {/* Background image or dark gradient */}
                <div className={`relative w-full overflow-hidden ${isLarge ? "h-80 sm:h-96" : "h-56"}`}>
                  {article.image_url ? (
                    <>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={article.image_url}
                        alt=""
                        className="absolute inset-0 w-full h-full object-cover object-top transition-transform duration-500 group-hover:scale-105"
                      />
                      {/* Gradient scrim — heavier at bottom */}
                      <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/70 to-slate-950/10" />
                    </>
                  ) : (
                    <div className="absolute inset-0 bg-gradient-to-br from-slate-800 to-slate-900" />
                  )}

                  {/* Content over image */}
                  <div className="absolute inset-0 flex flex-col justify-end p-5">
                    {/* Category + race */}
                    <div className="flex items-center gap-2 mb-2">
                      <span className={`text-[10px] uppercase tracking-widest font-semibold ${categoryColor}`}>
                        {CATEGORY_LABELS[article.category] ?? article.category}
                      </span>
                      {article.races && (
                        <span className="text-[10px] text-slate-500">· {article.races.name}</span>
                      )}
                    </div>

                    {/* Title over image */}
                    <h2 className={`font-display tracking-wide leading-tight text-white group-hover:text-emerald-300 transition-colors ${
                      isLarge ? "text-2xl sm:text-3xl" : "text-lg sm:text-xl"
                    }`}>
                      {article.title}
                    </h2>

                    {/* Excerpt — only for large card */}
                    {isLarge && article.excerpt && (
                      <p className="text-xs text-slate-400 leading-relaxed mt-2 line-clamp-2">
                        {article.excerpt}
                      </p>
                    )}

                    {/* Date */}
                    <p className="text-[10px] text-slate-600 mt-2">{formatDate(article.published_at)}</p>
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
