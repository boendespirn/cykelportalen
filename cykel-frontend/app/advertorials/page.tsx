export const dynamic = "force-dynamic";

import Link from "next/link";
import { API_BASE } from "@/lib/api";

type Article = {
  slug: string;
  title: string;
  excerpt: string | null;
  author: string;
  image_url: string | null;
  published_at: string;
};

async function getAdvertorials(): Promise<Article[]> {
  try {
    const res = await fetch(`${API_BASE}/news?advertorial=true&limit=40`, { cache: "no-store" });
    if (!res.ok) return [];
    return res.json();
  } catch { return []; }
}

function formatDate(d: string): string {
  return new Date(d).toLocaleDateString("da-DK", { day: "numeric", month: "long", year: "numeric" });
}

export default async function AdvertorialsPage() {
  const articles = await getAdvertorials();

  return (
    <div className="mx-auto max-w-5xl px-6 py-12">
      <header className="mb-14">
        <p className="text-xs uppercase tracking-[0.25em] text-emerald-400 mb-4">Sponsoreret indhold</p>
        <h1 className="font-display text-7xl sm:text-9xl tracking-wide leading-none text-white">
          Advertorials
        </h1>
        <p className="mt-5 text-slate-400 text-sm max-w-md leading-relaxed">
          Sponsoreret og kommercielt indhold fra partnere. Alle artikler er tydeligt mærket som sponsoreret.
          Vil du publicere en artikel på Cykelportalen?{" "}
          <Link href="/kontakt" className="text-emerald-400 hover:underline">Kontakt os →</Link>
        </p>
      </header>

      {articles.length === 0 ? (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-16 text-center">
          <p className="text-slate-500 text-sm mb-2">Ingen advertorials endnu.</p>
          <p className="text-slate-700 text-xs mb-6">
            Interesseret i at publicere sponsoreret indhold på Cykelportalen?
          </p>
          <Link
            href="/kontakt"
            className="inline-block text-sm bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-5 py-2.5 rounded-lg hover:bg-emerald-500/20 transition-colors"
          >
            Kontakt os om annoncering
          </Link>
        </div>
      ) : (
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {articles.map((article) => (
            <Link
              key={article.slug}
              href={`/advertorials/${article.slug}`}
              className="group flex flex-col rounded-2xl border border-slate-800/80 bg-slate-900/40 overflow-hidden hover:border-slate-700 hover:bg-slate-900 transition-all duration-150"
            >
              {article.image_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={article.image_url} alt="" className="w-full h-44 object-cover" />
              ) : (
                <div className="w-full h-44 bg-slate-800/60 flex items-center justify-center">
                  <span className="text-4xl opacity-20">📰</span>
                </div>
              )}
              <div className="p-5 flex flex-col flex-1">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-[10px] uppercase tracking-widest text-slate-500 font-medium border border-slate-700 px-1.5 py-0.5 rounded">
                    Sponsoreret
                  </span>
                </div>
                <h2 className="text-slate-100 font-semibold text-sm leading-snug mb-2 group-hover:text-slate-200 transition-colors flex-1">
                  {article.title}
                </h2>
                {article.excerpt && (
                  <p className="text-xs text-slate-500 leading-relaxed line-clamp-2 mb-3">
                    {article.excerpt}
                  </p>
                )}
                <div className="flex items-center justify-between mt-auto">
                  <p className="text-xs text-slate-700">{formatDate(article.published_at)}</p>
                  <p className="text-xs text-slate-600">{article.author}</p>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
