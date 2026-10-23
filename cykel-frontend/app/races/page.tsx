export const revalidate = 60;

import type { Metadata } from "next";
import Kalender from "./Kalender";

const BESKRIVELSE =
  "Cykelkalenderen med alle løb på landevej og i cykelcross — datoer, etaper, startlister og resultater samlet ét sted.";

export const metadata: Metadata = {
  title: "Cykelkalender – alle løb på landevej og i cykelcross",
  description: BESKRIVELSE,
  alternates: { canonical: "/races" },
  openGraph: {
    url: "/races",
    title: "Cykelkalender | Klassementet",
    description: BESKRIVELSE,
    siteName: "Klassementet",
    locale: "da_DK",
    type: "website",
    images: [{ url: "/social-cover.png", width: 1200, height: 630 }],
  },
};

export default function RacesPage() {
  return (
    <Kalender
      filter="alle"
      overlinje="Kalender · Landevej og cykelcross"
      titel="Alle"
      accent="Løb"
      intro="Alle løb, vi dækker, samlet i én kalender. Vælg landevej eller cykelcross for kun at se den ene."
    />
  );
}
