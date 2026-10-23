export const revalidate = 60;

import type { Metadata } from "next";
import Link from "next/link";
import Kalender from "../Kalender";

const BESKRIVELSE =
  "Landevejskalenderen: Grand Tours, monumenter og WorldTour-løb med etaper, stigningsprofiler, startlister og resultater.";

export const metadata: Metadata = {
  title: "Landevejskalender – Grand Tours, klassikere og WorldTour",
  description: BESKRIVELSE,
  alternates: { canonical: "/races/landevej" },
  openGraph: {
    url: "/races/landevej",
    title: "Landevejskalender | Klassementet",
    description: BESKRIVELSE,
    siteName: "Klassementet",
    locale: "da_DK",
    type: "website",
    images: [{ url: "/social-cover.png", width: 1200, height: 630 }],
  },
};

export default function LandevejPage() {
  return (
    <Kalender
      filter="landevej"
      overlinje="Kalender · Landevej"
      titel="Lande"
      accent="vej"
      intro="Årets store løb på landevejen — fra de tre Grand Tours til monumenterne og de øvrige WorldTour-løb."
    >
      <h2>Landevejssæsonen</h2>
      <p>
        Landevejskalenderen samler sæsonens største løb med UCI WorldTour som rygrad. Sæsonen
        begynder med de første etapeløb i januar, går gennem forårets klassikere og de tre{" "}
        <strong>Grand Tours</strong> — Giro d&apos;Italia, Tour de France og Vuelta a España — og
        slutter med efterårets sidste løb i oktober.
      </p>
      <h2>Hvad du finder på hvert løb</h2>
      <p>
        For hvert løb samler vi etaperne med højdeprofiler og stigninger, startlisten og
        favoritterne, og når løbet er kørt, de fulde resultater og klassementer. Alt ligger samme
        sted på hver løbsside, så du kun skal lære siden at kende én gang.
      </p>
      <p>
        Når kalenderen for næste sæson er offentliggjort, kommer løbene på her. Følger du også
        vintersæsonen, finder du den i{" "}
        <Link href="/races/cykelcross" className="text-emerald-400 hover:underline">
          cykelcross-kalenderen
        </Link>
        .
      </p>
    </Kalender>
  );
}
