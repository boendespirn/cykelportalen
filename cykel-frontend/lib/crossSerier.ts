/**
 * Cykelcross-serierne, som kalenderen kan sorteres på (ejerens ønske
 * 2026-11-08). Hver serie har sin egen underside, /races/cykelcross/<slug>,
 * og en serie er en eller flere værdier i `races.category` — samme værdier,
 * som kalender_agent.py skriver.
 *
 * Teksterne står her og ikke i databasen: de skal skrives om, når en serie
 * skifter navn eller regler, og det er en kodeændring alligevel.
 */
export type CrossSerie = {
  slug: string;
  navn: string;
  kategorier: string[];
  /** Kort, under overskriften. */
  intro: string;
  /** SEO-teksten under kalenderen — afsnit. */
  tekst: string[];
  metaTitel: string;
};

export const CROSS_SERIER: CrossSerie[] = [
  {
    slug: "world-cup",
    navn: "World Cup",
    kategorier: ["UCI Cyclocross World Cup"],
    metaTitel: "UCI Cyclocross World Cup",
    intro: "Alle afdelinger af UCI's verdensserie i cykelcross.",
    tekst: [
      "World Cuppen er cykelcrossets internationale verdensserie under UCI. Afdelingerne køres fra november til januar, de fleste i Belgien og Holland, men også i blandt andet Tjekkiet, Skotland, Frankrig og Spanien.",
      "Serien samler hele den internationale elite og er sæsonens vigtigste prøve før VM. Rytterne får point efter placering i hvert løb, og den samlede vinder kåres efter sidste afdeling.",
    ],
  },
  {
    slug: "superprestige",
    navn: "Superprestige",
    kategorier: ["Superprestige"],
    metaTitel: "Superprestige cykelcross",
    intro: "Alle løb i Superprestige — fra oktober til januar.",
    tekst: [
      "Superprestige er en af de klassiske belgiske crossserier og har eksisteret siden begyndelsen af 1980'erne. Løbene ligger fra oktober til januar på nogle af sportens mest kendte baner, blandt andet Ruddervoorde, Heusden-Zolder og aftenløbet i Diegem mellem jul og nytår.",
      "Rytterne samler point efter placering i hvert løb, og seriens samlede vinder kåres efter sidste afdeling.",
    ],
  },
  {
    slug: "x2o-trofee",
    navn: "X2O Trofee",
    kategorier: ["X2O Trofee"],
    metaTitel: "X2O Trofee cykelcross",
    intro: "Alle løb i X2O Trofee — fra Koppenberg til Bruxelles.",
    tekst: [
      "X2O Trofee er den belgiske serie, der tidligere hed blandt andet Bpost Bank Trofee og DVV Trofee. Den byder på nogle af sæsonens mest berømte løb, blandt andet Koppenbergcross på brostensbakken i Oudenaarde og nytårsløbet i Baal.",
      "Seriens samlede stilling afgøres på tid frem for point, så hvert sekund tæller i alle afdelinger.",
    ],
  },
  {
    slug: "hg-cross",
    navn: "HG Cross",
    kategorier: ["HG Cross"],
    metaTitel: "HG Cross cykelcross",
    intro: "Alle løb i HG Cross, der tidligere hed Exact Cross.",
    tekst: [
      "HG Cross er serien, der tidligere hed Exact Cross. Løbene køres i Belgien og Holland gennem hele sæsonen, flere af dem på hverdage, og samler mange af de samme ryttere som de store serier.",
    ],
  },
  {
    slug: "mesterskaber",
    navn: "Mesterskaber",
    kategorier: [
      "UCI Cyclocross World Championships",
      "UEC Cyclocross European Championships",
      "DM i cykelcross",
    ],
    metaTitel: "VM, EM og DM i cykelcross",
    intro: "VM, EM og DM i cykelcross — sæsonens titler.",
    tekst: [
      "Sæsonen har tre mesterskaber for en dansk fan: EM i november, DM i januar og VM sidst i januar eller først i februar. Vinderne kører i mestertrøjen — regnbuetrøjen for verdensmesteren — i alle løb resten af sæsonen.",
    ],
  },
  {
    slug: "oevrige",
    navn: "Øvrige løb",
    kategorier: ["Internationale crossløb"],
    metaTitel: "Øvrige internationale crossløb",
    intro: "Store crossløb uden for serierne.",
    tekst: [
      "Ud over serierne køres en række store internationale crossløb, som står alene. Her har vi de løb, vi forventer sendt på dansk tv.",
    ],
  },
];

export function serieFor(slug: string): CrossSerie | undefined {
  return CROSS_SERIER.find((s) => s.slug === slug);
}
