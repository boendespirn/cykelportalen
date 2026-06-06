import { NextResponse } from "next/server";
import { API_BASE } from "@/lib/api";

export const revalidate = 300;

type Article = {
  slug: string;
  title: string;
  excerpt: string | null;
  category: string;
  published_at: string;
  image_url: string | null;
  races: { name: string; slug: string } | null;
};

export async function GET() {
  let articles: Article[] = [];
  try {
    const res = await fetch(`${API_BASE}/news?advertorial=false&limit=20`, {
      next: { revalidate: 300 },
    });
    if (res.ok) articles = await res.json();
  } catch {}

  const items = articles
    .map((a) => {
      const url = `https://klassementet.dk/nyheder/${a.slug}`;
      const pubDate = new Date(a.published_at).toUTCString();
      const description = a.excerpt
        ? `<![CDATA[${a.excerpt}]]>`
        : `<![CDATA[${a.title}]]>`;
      const imageTag = a.image_url
        ? `<enclosure url="${a.image_url}" type="image/jpeg" />`
        : "";
      return `
    <item>
      <title><![CDATA[${a.title}]]></title>
      <link>${url}</link>
      <guid isPermaLink="true">${url}</guid>
      <description>${description}</description>
      <pubDate>${pubDate}</pubDate>
      ${imageTag}
    </item>`;
    })
    .join("");

  const rss = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Klassementet — Dansk cykelportal</title>
    <link>https://klassementet.dk</link>
    <description>Seneste nyt fra professionel cykling — løbsresultater, startlister og analyser.</description>
    <language>da</language>
    <atom:link href="https://klassementet.dk/api/rss" rel="self" type="application/rss+xml" />
    <image>
      <url>https://klassementet.dk/favicon.ico</url>
      <title>Klassementet</title>
      <link>https://klassementet.dk</link>
    </image>${items}
  </channel>
</rss>`;

  return new NextResponse(rss, {
    headers: {
      "Content-Type": "application/rss+xml; charset=utf-8",
      "Cache-Control": "public, max-age=300, stale-while-revalidate=600",
    },
  });
}
