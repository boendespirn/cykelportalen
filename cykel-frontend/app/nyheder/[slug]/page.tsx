export const dynamic = "force-dynamic";

import type { Metadata } from "next";
import Link from "next/link";
import { marked } from "marked";
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
  source_url: string | null;
  races: { name: string; slug: string } | null;
};

const CATEGORY_LABELS: Record<string, string> = {
  resultater:  "Resultater",
  startliste:  "Startliste",
  generelt:    "Nyheder",
  transfer:    "Transfer",
  profil:      "Profil",
  analyse:     "Analyse",
  race_report: "Løbsrapport",
  interview:   "Interview",
  general:     "Nyheder",
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

function renderMarkdown(md: string): string {
  // Sanitér interne links: /giro-ditalia-2026 → absolute path (allerede OK)
  const renderer = new marked.Renderer();
  renderer.link = ({ href, title, text }) => {
    const isInternal = href?.startsWith("/");
    const attrs = isInternal
      ? `href="${href}"`
      : `href="${href}" target="_blank" rel="noopener noreferrer"`;
    return `<a ${attrs}>${text}</a>`;
  };
  return marked(md, { renderer, breaks: true }) as string;
}

// ── Metadata ──────────────────────────────────────────────────────────────────

export async function generateMetadata(
  props: { params: Promise<{ slug: string }> }
): Promise<Metadata> {
  const { slug } = await props.params;
  const article = await getArticle(slug);
  if (!article) return { title: "Artikel ikke fundet" };
  return {
    title: article.title,
    description: article.meta_description ?? article.excerpt ?? undefined,
    openGraph: {
      title: article.title,
      description: article.meta_description ?? article.excerpt ?? undefined,
      type: "article",
      publishedTime: article.published_at,
      images: article.image_url ? [{ url: article.image_url }] : [],
    },
    twitter: { card: "summary_large_image" },
  };
}

// ── Page ──────────────────────────────────────────────────────────────────────

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

  const contentHtml = renderMarkdown(article.content);

  // JSON-LD Article structured data
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: article.title,
    description: article.meta_description ?? article.excerpt,
    author: { "@type": "Organization", name: article.author },
    publisher: {
      "@type": "Organization",
      name: "Klassementet",
      url: "https://klassementet.dk",
    },
    datePublished: article.published_at,
    image: article.image_url ?? undefined,
    url: `https://klassementet.dk/nyheder/${article.slug}`,
  };

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />

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
        {article.source_url && (
          <>
            <span>·</span>
            <a href={article.source_url} target="_blank" rel="noopener noreferrer"
              className="hover:text-slate-400 transition-colors">
              Kilde →
            </a>
          </>
        )}
      </div>

      {/* Hero image */}
      {article.image_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={article.image_url}
          alt={article.title}
          className="w-full rounded-xl mb-8 border border-slate-800 object-cover"
          style={{ maxHeight: "400px" }}
        />
      )}

      {/* Excerpt */}
      {article.excerpt && (
        <p className="text-lg text-slate-300 leading-relaxed mb-8 font-medium">
          {article.excerpt}
        </p>
      )}

      {/* Content — rendered from markdown */}
      <div
        className="prose prose-invert prose-sm max-w-none
          prose-headings:font-display prose-headings:tracking-wide
          prose-p:text-slate-300 prose-p:leading-relaxed
          prose-a:text-emerald-400 prose-a:no-underline hover:prose-a:underline
          prose-strong:text-slate-100
          prose-li:text-slate-300
          prose-blockquote:border-emerald-500/50 prose-blockquote:text-slate-400"
        dangerouslySetInnerHTML={{ __html: contentHtml }}
      />

      {/* Relateret løb */}
      {article.races && (
        <div className="mt-10 pt-8 border-t border-slate-800">
          <p className="text-xs text-slate-600 mb-3">Relateret løb</p>
          <Link
            href={`/${article.races.slug}`}
            className="inline-flex items-center gap-2 text-sm text-slate-300 hover:text-emerald-400 transition-colors"
          >
            <span className="text-emerald-500">→</span>
            {article.races.name}
          </Link>
        </div>
      )}
    </div>
  );
}
