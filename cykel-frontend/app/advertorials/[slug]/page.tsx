export const revalidate = 3600;

import Image from "next/image";
import Link from "next/link";
import { API_BASE } from "@/lib/api";

type Article = {
  slug: string;
  title: string;
  excerpt: string | null;
  content: string;
  author: string;
  image_url: string | null;
  published_at: string;
};

async function getArticle(slug: string): Promise<Article | null> {
  try {
    const res = await fetch(`${API_BASE}/news/${slug}`, { cache: "no-store" });
    const data = await res.json();
    if (data?.error || !data?.is_advertorial) return null;
    return data;
  } catch { return null; }
}

function formatDate(d: string): string {
  return new Date(d).toLocaleDateString("da-DK", {
    day: "numeric", month: "long", year: "numeric",
  });
}

export default async function AdvertorialPage(props: { params: Promise<{ slug: string }> }) {
  const { slug } = await props.params;
  const article = await getArticle(slug);

  if (!article) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-20 text-center">
        <p className="text-slate-500">Artikel ikke fundet.</p>
        <Link href="/advertorials" className="mt-4 inline-block text-sm text-emerald-400 hover:underline">
          ← Advertorials
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <Link href="/advertorials" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-emerald-400 transition-colors mb-10">
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Advertorials
      </Link>

      <div className="inline-block text-xs uppercase tracking-widest text-slate-500 border border-slate-700 px-2 py-1 rounded mb-5">
        Sponsoreret indhold
      </div>

      <h1 className="font-display text-4xl sm:text-6xl tracking-wide leading-tight text-white mb-4">
        {article.title}
      </h1>

      <div className="flex items-center gap-3 text-xs text-slate-600 mb-8 pb-8 border-b border-slate-800">
        <span>{formatDate(article.published_at)}</span>
        <span>·</span>
        <span>{article.author}</span>
      </div>

      {article.image_url && (
        <div className="relative w-full h-64 sm:h-96 rounded-xl mb-8 border border-slate-800 overflow-hidden">
          <Image src={article.image_url} alt="" fill sizes="(max-width: 768px) 100vw, 768px" className="object-cover object-top" priority />
        </div>
      )}

      {article.excerpt && (
        <p className="text-lg text-slate-300 leading-relaxed mb-8 font-medium">{article.excerpt}</p>
      )}

      <div
        className="prose prose-invert prose-sm max-w-none
          prose-headings:font-display prose-headings:tracking-wide
          prose-p:text-slate-300 prose-p:leading-relaxed
          prose-a:text-emerald-400 prose-a:no-underline hover:prose-a:underline
          prose-strong:text-slate-100"
        dangerouslySetInnerHTML={{ __html: article.content }}
      />

      <div className="mt-12 pt-8 border-t border-slate-800 text-xs text-slate-600">
        Dette er sponsoreret indhold. Artiklens indhold er leveret af annoncøren og er ikke redaktionelt indhold fra Klassementet.
      </div>
    </div>
  );
}
