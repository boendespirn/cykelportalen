export const revalidate = 300;

import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { API_BASE } from "@/lib/api";

export async function generateMetadata(
  props: { searchParams: Promise<{ page?: string }> }
): Promise<Metadata> {
  const { page: pageParam } = await props.searchParams;
  const page = Math.max(1, parseInt(pageParam ?? "1", 10) || 1);
  return {
    title: page > 1 ? `Nyheder — side ${page}` : "Nyheder",
    description: "Alle nyheder om cykling — resultater, startlister, analyser og interviews fra de store cykelløb.",
    alternates: {
      canonical: page > 1 ? `/nyheder?page=${page}` : "/nyheder",
      types: { "application/rss+xml": "https://klassementet.dk/api/rss" },
    },
  };
}

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

const CATEGORY_BG: Record<string, string> = {
  race_report: "from-red-950 to-slate-900",
  resultater:  "from-red-950 to-slate-900",
  startliste:  "from-blue-950 to-slate-900",
  startlist:   "from-blue-950 to-slate-900",
  analyse:     "from-orange-950 to-slate-900",
  analysis:    "from-orange-950 to-slate-900",
  transfer:    "from-yellow-950 to-slate-900",
  profil:      "from-purple-950 to-slate-900",
  interview:   "from-purple-950 to-slate-900",
  generelt:    "from-emerald-950 to-slate-900",
  general:     "from-emerald-950 to-slate-900",
};

const CATEGORY_ICON: Record<string, string> = {
  race_report: "🏆",
  resultater:  "🏆",
  startliste:  "📋",
  startlist:   "📋",
  analyse:     "📊",
  analysis:    "📊",
  transfer:    "🔄",
  profil:      "👤",
  interview:   "🎙️",
  generelt:    "🚴",
  general:     "🚴",
};

const PAGE_SIZE = 24;

async function getArticles(page: number): Promise<{ articles: Article[]; hasMore: boolean }> {
  const offset = (page - 1) * PAGE_SIZE;
  try {
    const res = await fetch(
      `${API_BASE}/news?advertorial=false&limit=${PAGE_SIZE + 1}&offset=${offset}`,
      { next: { revalidate: 300 } }
    );
    if (!res.ok) return { articles: [], hasMore: false };
    const data: Article[] = await res.json();
    return { articles: data.slice(0, PAGE_SIZE), hasMore: data.length > PAGE_SIZE };
  } catch {
    return { articles: [], hasMore: false };
  }
}

function formatDate(d: string): string {
  return new Date(d).toLocaleDateString("da-DK", { day: "numeric", month: "short", year: "numeric" });
}

export default async function NyhederPage(
  props: { searchParams: Promise<{ page?: string }> }
) {
  const { page: pageParam } = await props.searchParams;
  const page = Math.max(1, parseInt(pageParam ?? "1", 10) || 1);
  const { articles, hasMore } = await getArticles(page);

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
            const isLarge = page === 1 && i === 0; // Kun første artikel på side 1 er stor

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
                      <Image
                        src={article.image_url}
                        alt=""
                        fill
                        sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
                        className="object-cover object-top transition-transform duration-500 group-hover:scale-105"
                        priority={i === 0}
                      />
                      <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/70 to-slate-950/10" />
                    </>
                  ) : (
                    <div className={`absolute inset-0 bg-gradient-to-br ${CATEGORY_BG[article.category] ?? "from-slate-800 to-slate-900"}`}>
                      <span className="absolute bottom-0 right-0 text-[8rem] leading-none opacity-[0.07] select-none pointer-events-none pr-2 pb-0">
                        {CATEGORY_ICON[article.category] ?? "🚴"}
                      </span>
                    </div>
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

      {(page > 1 || hasMore) && (
        <div className="mt-10 flex items-center justify-center gap-3">
          {page > 1 && (
            <Link
              href={page === 2 ? "/nyheder" : `/nyheder?page=${page - 1}`}
              className="text-xs font-medium text-slate-400 hover:text-emerald-400 transition-colors px-4 py-2 rounded-lg border border-slate-800 hover:border-emerald-500/30"
            >
              ← Forrige
            </Link>
          )}
          <span className="text-xs text-slate-600 px-2">Side {page}</span>
          {hasMore && (
            <Link
              href={`/nyheder?page=${page + 1}`}
              className="text-xs font-medium text-slate-400 hover:text-emerald-400 transition-colors px-4 py-2 rounded-lg border border-slate-800 hover:border-emerald-500/30"
            >
              Næste →
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
