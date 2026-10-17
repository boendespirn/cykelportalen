import type { Metadata } from "next";
import Link from "next/link";
import { Afsender, Afsnit, JuridiskSide, KontaktLink } from "../JuridiskSide";
import { SAMTYKKE_COOKIE } from "@/lib/samtykke";
import { UDGIVER } from "@/lib/udgiver";

const BESKRIVELSE =
  "Hvilke cookies og tredjepartstjenester Klassementet bruger, hvad de gør, hvor længe de gemmes — og hvordan du til- og fravælger dem.";

export const metadata: Metadata = {
  title: "Cookiepolitik",
  description: BESKRIVELSE,
  alternates: { canonical: "/cookiepolitik" },
  openGraph: {
    url: "/cookiepolitik",
    title: "Cookiepolitik | Klassementet",
    description: BESKRIVELSE,
    siteName: "Klassementet",
    locale: "da_DK",
    type: "website",
    images: [{ url: "/social-cover.png", width: 1200, height: 630 }],
  },
};

type Raekke = {
  navn: string;
  udbyder: string;
  formaal: string;
  varighed: string;
  type: string;
};

const NOEDVENDIGE: Raekke[] = [
  {
    navn: SAMTYKKE_COOKIE,
    udbyder: `${UDGIVER.navn} (${UDGIVER.domaene})`,
    formaal:
      "Gemmer dit valg i cookiebanneret, så du ikke bliver spurgt igen ved hver sidevisning, og så vi kan dokumentere hvad du har sagt ja til.",
    varighed: "12 måneder",
    type: "Cookie",
  },
  {
    navn: "adminKey",
    udbyder: `${UDGIVER.navn} (${UDGIVER.domaene})`,
    formaal:
      "Bruges udelukkende i redaktionens eget administrationsområde på /admin til at holde redaktøren logget ind. Sættes aldrig ved almindelig brug af siden.",
    varighed: "Indtil den slettes manuelt",
    type: "Local storage",
  },
];

const STATISTIK: Raekke[] = [
  {
    navn: "Vercel Analytics",
    udbyder: "Vercel Inc.",
    formaal:
      "Tæller sidevisninger og viser os, hvilke løb, etaper og artikler der bliver læst, så vi kan prioritere det rigtige indhold. Tjenesten er cookiefri: der gemmes ingenting på din enhed, og du kan ikke genkendes på tværs af websites.",
    varighed: "Ingen lagring på din enhed",
    type: "Måling uden cookies",
  },
];

const TREDJEPART: Raekke[] = [
  {
    navn: "VeloViewer-embed",
    udbyder: "VeloViewer",
    formaal:
      "Viser den interaktive 3D-stigningsprofil på etapesider. Indholdet indlejres direkte fra veloviewer.com, som derfor modtager din IP-adresse og selv kan sætte cookies, vi ikke har kontrol over.",
    varighed: "Fastsættes af VeloViewer",
    type: "Indlejret indhold (iframe)",
  },
];

function Tabel({ raekker }: { raekker: Raekke[] }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-800">
      <table className="w-full min-w-[640px] text-left text-xs">
        <thead className="bg-slate-900/70 text-slate-500">
          <tr>
            <th scope="col" className="px-4 py-3 font-medium uppercase tracking-widest">
              Navn
            </th>
            <th scope="col" className="px-4 py-3 font-medium uppercase tracking-widest">
              Udbyder
            </th>
            <th scope="col" className="px-4 py-3 font-medium uppercase tracking-widest">
              Formål
            </th>
            <th scope="col" className="px-4 py-3 font-medium uppercase tracking-widest">
              Varighed
            </th>
            <th scope="col" className="px-4 py-3 font-medium uppercase tracking-widest">
              Type
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800 text-slate-300">
          {raekker.map((r) => (
            <tr key={r.navn} className="align-top">
              <th scope="row" className="px-4 py-3 text-left font-mono font-normal text-slate-200">
                {r.navn}
              </th>
              <td className="px-4 py-3 text-slate-400">{r.udbyder}</td>
              <td className="max-w-sm px-4 py-3 leading-relaxed">{r.formaal}</td>
              <td className="whitespace-nowrap px-4 py-3 text-slate-400">{r.varighed}</td>
              <td className="px-4 py-3 text-slate-500">{r.type}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function CookiepolitikPage() {
  return (
    <JuridiskSide
      kicker="Cookies og samtykke"
      titel="Cookiepolitik"
      indledning={BESKRIVELSE}
      aktivSti="/cookiepolitik"
    >
      <Afsender />

      <Afsnit nr={1} titel="Kort fortalt">
        <p>
          Vi bruger så få cookies som muligt. Der sættes <strong>én</strong> cookie, før du har
          taget stilling til noget — den husker dit svar på cookiebanneret, og den kan ikke bruges
          til at følge dig.
        </p>
        <p>
          <strong>Vi bruger ikke reklame- eller marketingcookies</strong>, og vi sælger ikke
          oplysninger om dig videre. Alt andet end det strengt nødvendige kræver, at du aktivt
          siger ja i banneret.
        </p>
      </Afsnit>

      <Afsnit nr={2} titel="Hvad er cookies?">
        <p>
          En cookie er en lille tekstfil, som et website kan gemme i din browser, så den kan
          genkendes ved næste sidevisning. Samme regler gælder for lignende teknologier, fx local
          storage og indlejret indhold fra andre websites. I denne politik bruger vi cookies som
          fællesbetegnelse for det hele.
        </p>
        <p>
          Reglerne står i cookiebekendtgørelsen (bekendtgørelse nr. 1148 af 9. december 2011) og i
          databeskyttelsesforordningen (GDPR). De betyder, at vi skal have dit samtykke, før vi
          gemmer eller læser noget på din enhed, som ikke er nødvendigt for at levere den tjeneste,
          du selv har bedt om.
        </p>
      </Afsnit>

      <Afsnit nr={3} titel="Nødvendige — kræver ikke samtykke">
        <p>
          Disse er nødvendige for, at siden virker, og de kan derfor ikke fravælges. De bruges ikke
          til statistik eller markedsføring.
        </p>
        <Tabel raekker={NOEDVENDIGE} />
      </Afsnit>

      <Afsnit nr={4} titel="Statistik — kræver dit samtykke">
        <p>
          Bruges kun til at forstå, hvilke sider der er værd at bygge videre på. Der måles først,
          når du har sagt ja.
        </p>
        <Tabel raekker={STATISTIK} />
      </Afsnit>

      <Afsnit nr={5} titel="Indlejret indhold — kræver dit samtykke">
        <p>
          På etapesider kan vi vise en interaktiv 3D-stigningsprofil, der hentes direkte fra
          VeloViewer. Fordi indholdet kommer fra deres servere, får de din IP-adresse, og de kan
          sætte deres egne cookies. Derfor indlæses det først, når du har sagt ja.
        </p>
        <Tabel raekker={TREDJEPART} />
        <p>
          Siger du nej, mister du ikke stigningen: vi viser i stedet{" "}
          <strong>vores egen tegnede højde- og stigningsprofil</strong>, hvor vi har en, og ellers
          vores egen graf over stigningsprocenterne. Du kan sige ja til en enkelt profil direkte på
          etapesiden uden at ændre dine øvrige valg.
        </p>
      </Afsnit>

      <Afsnit nr={6} titel="Kort og billeder uden cookies">
        <p>
          Etapekortene tegnes med kortfliser fra <strong>OpenStreetMap</strong> (OpenStreetMap
          Foundation, Storbritannien). Kortfliser sætter ingen cookies, men din IP-adresse sendes
          til OpenStreetMap, når kortet hentes — på samme måde som når din browser henter et
          billede fra et andet website.
        </p>
        <p>
          Vi anser kortet som en del af den tjeneste, du har bedt om, når du åbner en etapeside, og
          det indlæses derfor uden samtykke. Vi nævner det her, så du kan se det fulde billede af,
          hvem der modtager data. Vil du undgå det, kan du blokere indhold fra tredjepart i din
          browser.
        </p>
        <p>
          Rytter- og holdbilleder samt stigningsbilleder hentes fra vores eget lager hos vores
          databehandlere og sætter ingen cookies.
        </p>
      </Afsnit>

      <Afsnit nr={7} titel="Sådan ændrer eller trækker du dit samtykke tilbage">
        <p>
          Dit samtykke er frivilligt, og du kan trække det tilbage lige så let, som du gav det.
          Klik på <strong>Cookieindstillinger</strong> nederst på enhver side, slå kategorierne til
          eller fra, og gem. Fravælger du en kategori, holder vi øjeblikkeligt op med at indlæse
          den — indhold fra tredjepart indlæses ikke igen, før du siger ja.
        </p>
        <p>
          Du kan også slette cookies direkte i din browser. Det fjerner vores samtykkecookie, og så
          spørger banneret igen ved næste besøg. Vejledning findes under indstillingerne i Chrome,
          Safari, Firefox og Edge.
        </p>
        <p>
          Vi beder om samtykke igen efter højst 12 måneder, og hvis vi tilføjer en ny kategori — et
          gammelt samtykke dækker aldrig et nyt formål.
        </p>
      </Afsnit>

      <Afsnit nr={8} titel="Dine rettigheder og klage">
        <p>
          Hvordan vi behandler personoplysninger, hvad retsgrundlaget er, hvor længe vi gemmer dem,
          og hvilke rettigheder du har, står i vores{" "}
          <Link href="/privatlivspolitik">privatlivspolitik</Link>.
        </p>
        <p>
          Klager over cookies behandles af <strong>Erhvervsstyrelsen</strong>, og klager over
          behandling af personoplysninger af <strong>Datatilsynet</strong>. Du er altid velkommen
          til at skrive til os først via <KontaktLink /> — vi vil hellere rette en fejl end
          forsvare den.
        </p>
      </Afsnit>

      <Afsnit nr={9} titel="Ændringer i denne politik">
        <p>
          Tilføjer eller fjerner vi en tjeneste, opdaterer vi tabellerne ovenfor og datoen øverst på
          siden. Kommer der et nyt formål, som kræver samtykke, spørger vi dig igen, før det tages i
          brug.
        </p>
      </Afsnit>
    </JuridiskSide>
  );
}
