export const revalidate = 60;

import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import Kalender, { crossSaeson } from "../../Kalender";
import { CROSS_SERIER, serieFor } from "@/lib/crossSerier";

export function generateStaticParams() {
  return CROSS_SERIER.map((s) => ({ serie: s.slug }));
}

export async function generateMetadata(
  { params }: { params: Promise<{ serie: string }> },
): Promise<Metadata> {
  const serie = serieFor((await params).serie);
  if (!serie) return {};
  const saeson = crossSaeson();
  const sti = `/races/cykelcross/${serie.slug}`;
  const beskrivelse = `${serie.metaTitel} ${saeson}: kalender med datoer, startlister og resultater for alle løb — samlet på Klassementet.`;
  return {
    title: `${serie.metaTitel} ${saeson} – kalender og resultater`,
    description: beskrivelse,
    alternates: { canonical: sti },
    openGraph: {
      url: sti,
      title: `${serie.metaTitel} ${saeson} | Klassementet`,
      description: beskrivelse,
      siteName: "Klassementet",
      locale: "da_DK",
      type: "website",
      images: [{ url: "/social-cover.png", width: 1200, height: 630 }],
    },
  };
}

export default async function SeriePage(
  { params }: { params: Promise<{ serie: string }> },
) {
  const serie = serieFor((await params).serie);
  if (!serie) notFound();
  const saeson = crossSaeson();
  return (
    <Kalender
      filter="cykelcross"
      serie={serie}
      overlinje={`Kalender · Cykelcross ${saeson}`}
      titel={serie.navn}
      accent={saeson}
      intro={serie.intro}
    >
      <h2>{serie.navn} {saeson}</h2>
      {serie.tekst.map((afsnit, i) => (
        <p key={i}>{afsnit}</p>
      ))}
      <p>
        Hele sæsonen på tværs af serierne finder du i{" "}
        <Link href="/races/cykelcross" className="text-emerald-400 hover:underline">
          cykelcross-kalenderen
        </Link>
        .
      </p>
    </Kalender>
  );
}
