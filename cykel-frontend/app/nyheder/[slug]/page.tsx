export const dynamic = "force-dynamic";

import Link from "next/link";
import { API_BASE } from "@/lib/api";

type Article = {
  id: string;
  slug: string;
  title: string;
  excerpt: string | null;
  content: string;
  meta_description: string | null;
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

async function getArticle(slug: string): Promise<Article | null> {
  try {
    const res = await fetch(`${API_BASE}/news/${slug}`, { cache: "no-store" });
    const data = await res.json();
    return data?.error ? null : data;
  } catch { return null; }
}

function formatDate(d: string): string {
  return new Date(d).toLocaleDateString("da-DK", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  });
}

export default async function ArticlePage(props: { params: Promise<{ slug: string }> }) {
  const { slug } = await props.params;
  const article = await getArticle(slug);

  if (!article) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-20 text-center">
        <p className="text-slate-500">Artikel ikke fundet.</p>
        <Link href="/nyheder" className="mt-4 inline-block text-sm text-emerald-400 hover:underline">
          ← Alle nyheder
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <Link href="/nyheder" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-emerald-400 transition-colors mb-10">
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Alle nyheder
      </Link>

      {/* Category + race tag */}
      <div className="flex items-center gap-3 mb-4">
        <span className="text-xs uppercase tracking-[0.2em] text-emerald-400 font-medium">
          {CATEGORY_LABELS[article.category] ?? article.category}
        </span>
        {article.races && (
          <Link href={`/${article.races.slug}`}
            className="text-xs text-slate-500 hover:text-slate-300 transition-colors">
            {article.races.name} →
          </Link>
        )}
      </div>

      {/* Title */}
      <h1 className="font-display text-4xl sm:text-6xl tracking-wide leading-tight text-white mb-4">
        {article.title}
      </h1>

      {/* Meta */}
      <div className="flex items-center gap-3 text-xs text-slate-600 mb-8 pb-8 border-b border-slate-800">
        <span className="capitalize">{formatDate(article.published_at)}</span>
        <span>·</span>
        <span>{article.author}</span>
      </div>

      {/* Hero image */}
      {article.image_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={article.image_url} alt="" className="w-full rounded-xl mb-8 border border-slate-800" />
      )}

      {/* Excerpt */}
      {article.excerpt && (
        <p className="text-lg text-slate-300 leading-relaxed mb-8 font-medium">
          {article.excerpt}
        </p>
      )}

      {/* Content */}
      <div
        className="prose prose-invert prose-sm max-w-none
          prose-headings:font-display prose-headings:tracking-wide
          prose-p:text-slate-300 prose-p:leading-relaxed
          prose-a:text-emerald-400 prose-a:no-underline hover:prose-a:underline
          prose-strong:text-slate-100
          prose-blockquote:border-emerald-500/50 prose-blockquote:text-slate-400"
        dangerouslySetInnerHTML={{ __html: article.content }}
      />
    </div>
  );
}
