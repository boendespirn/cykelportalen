import type { Metadata } from "next";
import Link from "next/link";
import { Afsender, Afsnit, JuridiskSide, KontaktLink } from "../JuridiskSide";
import { UDGIVER } from "@/lib/udgiver";

const BESKRIVELSE =
  "Hvilke personoplysninger Klassementet behandler, hvorfor, hvad retsgrundlaget er, hvem vi deler dem med — og hvilke rettigheder du har.";

export const metadata: Metadata = {
  title: "Privatlivspolitik",
  description: BESKRIVELSE,
  alternates: { canonical: "/privatlivspolitik" },
  openGraph: {
    url: "/privatlivspolitik",
    title: "Privatlivspolitik | Klassementet",
    description: BESKRIVELSE,
    siteName: "Klassementet",
    locale: "da_DK",
    type: "website",
    images: [{ url: "/social-cover.png", width: 1200, height: 630 }],
  },
};

const MODTAGERE = [
  {
    navn: "Vercel Inc.",
    rolle: "Hosting, levering af websitet og besøgsstatistik",
    land: "USA og EU",
    grundlag:
      "Databehandleraftale. Overførsel til USA sker på grundlag af EU-Kommissionens standardkontraktbestemmelser og EU-US Data Privacy Framework.",
  },
  {
    navn: "Supabase",
    rolle: "Database og billedlager for løb, ryttere, hold og artikler",
    land: "EU/EØS eller tredjeland",
    grundlag:
      "Databehandleraftale med EU-Kommissionens standardkontraktbestemmelser, hvor behandlingen sker uden for EU/EØS.",
  },
  {
    navn: "Telegram",
    rolle:
      "Intern beskedkanal. Skriver du via kontaktformularen, videresendes din henvendelse hertil, så vi kan se og besvare den",
    land: "Uden for EU/EØS",
    grundlag:
      "Telegram behandler beskeden som led i leveringen af tjenesten. Send derfor ikke fortrolige oplysninger i formularen.",
  },
  {
    navn: "VeloViewer",
    rolle: "Indlejrede 3D-stigningsprofiler — indlæses kun med dit samtykke",
    land: "Storbritannien",
    grundlag:
      "Selvstændig dataansvarlig for det indlejrede indhold. Storbritannien er omfattet af EU-Kommissionens afgørelse om tilstrækkeligt beskyttelsesniveau.",
  },
  {
    navn: "OpenStreetMap Foundation",
    rolle: "Kortfliser til etapekort",
    land: "Storbritannien",
    grundlag:
      "Selvstændig dataansvarlig for levering af kortfliser. Omfattet af afgørelsen om tilstrækkeligt beskyttelsesniveau.",
  },
];

export default function PrivatlivspolitikPage() {
  return (
    <JuridiskSide
      kicker="Dine data"
      titel="Privatlivspolitik"
      indledning={BESKRIVELSE}
      aktivSti="/privatlivspolitik"
    >
      <Afsender />

      <Afsnit nr={1} titel="Kort fortalt">
        <p>
          Du kan bruge hele Klassementet uden at oprette en konto og uden at oplyse noget om dig
          selv. Vi indsamler ikke mere, end vi har brug for, vi sælger ikke oplysninger videre, og
          vi bruger ikke reklame- eller profileringsværktøjer.
        </p>
        <p>
          {UDGIVER.navn} ({UDGIVER.domaene}) er dataansvarlig for behandlingen beskrevet nedenfor.
          Du kan altid kontakte os via <KontaktLink />.
        </p>
      </Afsnit>

      <Afsnit nr={2} titel="Når du blot læser med">
        <p>
          <strong>Hvad:</strong> Vores hostingleverandør logger tekniske oplysninger om hver
          forespørgsel — IP-adresse, tidspunkt, hvilken side der blev hentet, browsertype og
          henvisende side.
        </p>
        <p>
          <strong>Hvorfor:</strong> For at kunne levere siden, holde den oppe og i rimelig hastighed
          samt beskytte den mod misbrug, overbelastning og indbrudsforsøg.
        </p>
        <p>
          <strong>Retsgrundlag:</strong> Vores legitime interesse i at drive og sikre et fungerende
          website, jf. databeskyttelsesforordningens artikel 6, stk. 1, litra f.
        </p>
        <p>
          <strong>Hvor længe:</strong> Tekniske logs slettes eller anonymiseres automatisk hos
          leverandøren, typisk inden for 30 dage. Vi bruger dem ikke til at identificere
          enkeltpersoner.
        </p>
      </Afsnit>

      <Afsnit nr={3} titel="Besøgsstatistik — kun med samtykke">
        <p>
          <strong>Hvad:</strong> Hvis du siger ja til statistik i cookiebanneret, tæller Vercel
          Analytics din sidevisning. Værktøjet er cookiefrit og danner ikke en profil af dig; det
          giver os samlede tal pr. side, ikke et spor efter en enkelt bruger.
        </p>
        <p>
          <strong>Hvorfor:</strong> For at se hvilke løb, etaper og artikler der faktisk bliver
          brugt, så vi lægger arbejdet der, hvor det giver læserne mest.
        </p>
        <p>
          <strong>Retsgrundlag:</strong> Dit samtykke, jf. artikel 6, stk. 1, litra a. Du kan trække
          det tilbage når som helst under <strong>Cookieindstillinger</strong> nederst på siden —
          det er lige så let som at give det.
        </p>
        <p>
          <strong>Hvor længe:</strong> Kun samlet, anonym statistik gemmes. Der ligger ingenting på
          din enhed. Detaljerne står i <Link href="/cookiepolitik">cookiepolitikken</Link>.
        </p>
      </Afsnit>

      <Afsnit nr={4} titel="Når du skriver til os">
        <p>
          <strong>Hvad:</strong> Al kontakt til os går gennem <KontaktLink />. Skriver du til os
          der, behandler vi de oplysninger, du selv giver os: navn, e-mailadresse, eventuelt
          firmanavn, emne og indholdet af din besked. Din e-mailadresse bruger vi alene til at
          kunne svare dig.
        </p>
        <p>
          <strong>Hvorfor:</strong> For at kunne svare dig, og — hvis det handler om annoncering
          eller sponsoreret indhold — for at kunne indgå og opfylde en aftale med dig.
        </p>
        <p>
          <strong>Retsgrundlag:</strong> Vores legitime interesse i at besvare henvendelser (artikel
          6, stk. 1, litra f), og ved et konkret samarbejde opfyldelse af aftalen (artikel 6, stk.
          1, litra b).
        </p>
        <p>
          <strong>Hvor længe:</strong> Almindelige henvendelser slettes, når sagen er afsluttet, og
          senest efter 12 måneder. Bliver der indgået en aftale, opbevares den dokumentation,
          bogføringsloven kræver, i 5 år fra udløbet af det regnskabsår, aftalen vedrører.
        </p>
        <p>
          <strong>Hvordan den når os:</strong> Henvendelsen videresendes til vores interne
          beskedkanal hos Telegram, så vi kan se og besvare den. Telegram behandler derfor
          indholdet af din besked, og behandlingen sker uden for EU/EØS.
        </p>
        <p>
          Du bestemmer selv, hvad du skriver. Undlad at sende fortrolige oplysninger som
          CPR-nummer, helbredsoplysninger eller kontooplysninger — hverken vi eller du har brug
          for dem, for at vi kan svare.
        </p>
      </Afsnit>

      <Afsnit nr={5} titel="Oplysninger om professionelle ryttere og hold">
        <p>
          Klassementet er en sportsmedie- og datatjeneste, og vi offentliggør derfor oplysninger om
          professionelle cykelryttere: navn, nationalitet, fødselsdato, hold, hjemby og
          konkurrenceresultater. Det er personoplysninger, så vi beskriver også dem her.
        </p>
        <p>
          <strong>Hvad:</strong> Udelukkende oplysninger, der allerede er offentliggjort af
          rytteren, holdet, arrangøren eller i etablerede resultatdatabaser — i dag UCI,
          ProCyclingStats og VeloWire. Vi indsamler ikke følsomme oplysninger, og vi offentliggør
          ikke private forhold uden sportslig relevans.
        </p>
        <p>
          <strong>Retsgrundlag:</strong> Vores legitime interesse i at formidle sportsinformation og
          offentlighedens interesse i at kunne følge professionel cykelsport, jf. artikel 6, stk. 1,
          litra f. Behandling, der sker i journalistisk øjemed, er desuden omfattet af
          databeskyttelseslovens § 3, stk. 8.
        </p>
        <p>
          Er du rytter, holdrepræsentant eller på anden måde omtalt, og mener du, at noget er
          forkert, forældet eller ikke bør være offentligt, så skriv til{" "}
          <KontaktLink />. Vi retter eller fjerner faktuelle
          fejl hurtigst muligt — korrekte data er hele pointen med siden.
        </p>
      </Afsnit>

      <Afsnit nr={6} titel="Sponsoreret indhold og advertorials">
        <p>
          Siden finansieres af sponsoreret indhold. Alt kommercielt indhold er tydeligt mærket som
          sponsoreret, jf. markedsføringslovens forbud mod skjult reklame. Vi videregiver ikke
          oplysninger om dig til annoncører, og annoncører får ikke adgang til at måle eller følge
          dig på siden.
        </p>
        <p>
          Klikker du på et link i en advertorial, forlader du Klassementet, og modtagerens egen
          privatlivspolitik gælder derefter. Vi har ingen kontrol over, hvad andre websites
          indsamler.
        </p>
      </Afsnit>

      <Afsnit nr={7} titel="Hvem vi deler oplysninger med">
        <p>
          Vi deler kun oplysninger med de leverandører, der er nødvendige for at drive siden. De
          handler efter vores instruks på grundlag af databehandleraftaler, bortset fra hvor de er
          selvstændigt dataansvarlige, som angivet nedenfor.
        </p>
        <div className="overflow-x-auto rounded-xl border border-slate-800">
          <table className="w-full min-w-[640px] text-left text-xs">
            <thead className="bg-slate-900/70 text-slate-500">
              <tr>
                <th scope="col" className="px-4 py-3 font-medium uppercase tracking-widest">
                  Modtager
                </th>
                <th scope="col" className="px-4 py-3 font-medium uppercase tracking-widest">
                  Rolle
                </th>
                <th scope="col" className="px-4 py-3 font-medium uppercase tracking-widest">
                  Placering
                </th>
                <th scope="col" className="px-4 py-3 font-medium uppercase tracking-widest">
                  Grundlag for overførsel
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800 text-slate-300">
              {MODTAGERE.map((m) => (
                <tr key={m.navn} className="align-top">
                  <th scope="row" className="px-4 py-3 text-left font-normal text-slate-200">
                    {m.navn}
                  </th>
                  <td className="max-w-[14rem] px-4 py-3 leading-relaxed text-slate-400">
                    {m.rolle}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-slate-400">{m.land}</td>
                  <td className="max-w-sm px-4 py-3 leading-relaxed text-slate-500">{m.grundlag}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          Vi sælger aldrig personoplysninger, og vi videregiver dem ikke til markedsføring hos
          tredjemand. Vi kan være forpligtet til at udlevere oplysninger til myndigheder, hvis
          lovgivningen kræver det.
        </p>
      </Afsnit>

      <Afsnit nr={8} titel="Dine rettigheder">
        <p>Efter databeskyttelsesforordningen har du ret til at:</p>
        <ul>
          <li>få indsigt i, hvilke oplysninger vi behandler om dig, og få en kopi</li>
          <li>få urigtige oplysninger rettet</li>
          <li>få oplysninger slettet, når vi ikke længere har et grundlag for at have dem</li>
          <li>få behandlingen begrænset, mens en indsigelse eller rettelse behandles</li>
          <li>
            gøre indsigelse mod behandling, der sker på grundlag af en legitim interesse — herunder
            mod offentliggørelse af oplysninger om dig
          </li>
          <li>få oplysninger, du selv har givet os, udleveret i et maskinlæsbart format</li>
          <li>trække et samtykke tilbage, uden at det påvirker lovligheden af det, der skete før</li>
        </ul>
        <p>
          Skriv til os via <KontaktLink />, så svarer vi hurtigst
          muligt og senest inden en måned. Vi kan have brug for at bekræfte, at det er dig, før vi
          udleverer oplysninger. Det er gratis at bruge sine rettigheder.
        </p>
      </Afsnit>

      <Afsnit nr={9} titel="Automatiske afgørelser og profilering">
        <p>
          Vi bruger AI-værktøjer til at samle, oversætte og sammenstille sportsdata og til at
          udarbejde artikeludkast, som et menneske godkender før udgivelse. Vi træffer ikke
          automatiske afgørelser om dig, og vi profilerer dig ikke.
        </p>
      </Afsnit>

      <Afsnit nr={10} titel="Sikkerhed">
        <p>
          Siden leveres udelukkende over krypteret forbindelse (HTTPS). Adgang til databasen og
          redaktionens administrationsområde er begrænset til de personer, der har brug for den, og
          beskyttet med adgangsnøgler. Vi gemmer kun det, vi har brug for — det er den bedste
          beskyttelse.
        </p>
      </Afsnit>

      <Afsnit nr={11} titel="Børn">
        <p>
          Siden henvender sig til cykelinteresserede generelt og ikke særligt til børn. Vi indsamler
          ikke bevidst oplysninger om børn under 13 år. Er du forælder og mener, at vi har modtaget
          oplysninger om dit barn, så skriv til os, og vi sletter dem.
        </p>
      </Afsnit>

      <Afsnit nr={12} titel="Klage til Datatilsynet">
        <p>
          Er du utilfreds med, hvordan vi behandler dine personoplysninger, hører vi det gerne
          først. Du har også altid ret til at klage til Datatilsynet, Carl Jacobsens Vej 35, 2500
          Valby, telefon 33 19 32 00, e-mail dt@datatilsynet.dk — eller via{" "}
          <a href="https://www.datatilsynet.dk" target="_blank" rel="noopener noreferrer">
            datatilsynet.dk
          </a>
          .
        </p>
      </Afsnit>

      <Afsnit nr={13} titel="Ændringer i denne politik">
        <p>
          Ændrer vi, hvad vi behandler, eller hvem vi deler det med, opdaterer vi denne side og
          datoen øverst. Er ændringen væsentlig, gør vi opmærksom på den på siden, og kræver den
          samtykke, spørger vi dig på ny.
        </p>
      </Afsnit>
    </JuridiskSide>
  );
}
