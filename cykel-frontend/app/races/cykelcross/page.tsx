export const revalidate = 60;

import type { Metadata } from "next";
import Link from "next/link";
import Kalender, { crossSaeson } from "../Kalender";

export async function generateMetadata(): Promise<Metadata> {
  const saeson = crossSaeson();
  const beskrivelse = `Cykelcross-kalenderen ${saeson}: alle løb i World Cup, Superprestige, X2O Trofee og HG Cross med datoer, startlister og resultater.`;
  return {
    title: `Cykelcross kalender ${saeson} – World Cup, Superprestige og X2O`,
    description: beskrivelse,
    alternates: { canonical: "/races/cykelcross" },
    openGraph: {
      url: "/races/cykelcross",
      title: `Cykelcross kalender ${saeson} | Klassementet`,
      description: beskrivelse,
      siteName: "Klassementet",
      locale: "da_DK",
      type: "website",
      images: [{ url: "/social-cover.png", width: 1200, height: 630 }],
    },
  };
}

export default function CykelcrossPage() {
  const saeson = crossSaeson();
  return (
    <Kalender
      filter="cykelcross"
      overlinje={`Kalender · Cykelcross ${saeson}`}
      titel="Cykel"
      accent="cross"
      intro={`Alle løb i cross-sæsonen ${saeson}: World Cup, Superprestige, X2O Trofee og HG Cross.`}
    >
      <h2>Cykelcross-sæsonen {saeson}</h2>
      <p>
        Cykelcross køres om efteråret og vinteren på korte, krævende omgange med mudder, sand,
        græs, trapper og forhindringer, hvor rytterne ofte må af cyklen og løbe. Antallet af
        omgange fastlægges undervejs, så et eliteløb varer omkring en time. Sæsonen kulminerer
        med VM i januar eller februar.
      </p>
      <h2>Serierne i kalenderen</h2>
      <p>
        <strong>UCI Cyclocross World Cup</strong> er den internationale verdensserie.{" "}
        <strong>Superprestige</strong>, <strong>X2O Trofee</strong> og <strong>HG Cross</strong>{" "}
        er de klassiske serier med løb i Belgien og Holland, hvor sporten har sit største
        publikum. I hver serie tæller rytternes placeringer til en samlet stilling.
      </p>
      <h2>Hvad du finder på hvert løb</h2>
      <p>
        For hvert løb samler vi dato, serie og startliste, så snart den er offentliggjort, og
        resultatet, når løbet er kørt — så du kan følge hele sæsonen og seriernes stillinger ét
        sted. Landevejens løb finder du i{" "}
        <Link href="/races/landevej" className="text-emerald-400 hover:underline">
          landevejskalenderen
        </Link>
        .
      </p>
    </Kalender>
  );
}
