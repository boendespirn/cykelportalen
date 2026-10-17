import type { Metadata } from "next";
import Link from "next/link";
import { Afsender, Afsnit, JuridiskSide, KontaktLink } from "../JuridiskSide";
import { UDGIVER } from "@/lib/udgiver";

const BESKRIVELSE =
  "Vilkårene for at bruge Klassementet: hvad du må med vores indhold, hvad vi står på mål for, og hvordan sponsoreret indhold håndteres.";

export const metadata: Metadata = {
  title: "Vilkår og betingelser",
  description: BESKRIVELSE,
  alternates: { canonical: "/vilkaar-og-betingelser" },
  openGraph: {
    url: "/vilkaar-og-betingelser",
    title: "Vilkår og betingelser | Klassementet",
    description: BESKRIVELSE,
    siteName: "Klassementet",
    locale: "da_DK",
    type: "website",
    images: [{ url: "/social-cover.png", width: 1200, height: 630 }],
  },
};

export default function VilkaarPage() {
  return (
    <JuridiskSide
      kicker="Vilkår for brug"
      titel="Vilkår og betingelser"
      indledning={BESKRIVELSE}
      aktivSti="/vilkaar-og-betingelser"
    >
      <Afsender />

      <Afsnit nr={1} titel="Om disse vilkår">
        <p>
          Disse vilkår gælder for din brug af {UDGIVER.domaene} og alt indhold på siden. Ved at
          bruge siden accepterer du vilkårene. Er du ikke enig i dem, skal du undlade at bruge
          siden.
        </p>
        <p>
          Nedenfor er <strong>vi, os og vores</strong> {UDGIVER.navn} som tjeneste, og{" "}
          <strong>du</strong> er dig som bruger af siden.
        </p>
        <p>
          Siden er gratis at bruge, kræver ingen oprettelse af konto og indeholder ingen betalings-
          eller abonnementsfunktioner. Der er altså ikke noget, du kan købe her, og intet du
          forpligter dig økonomisk til.
        </p>
      </Afsnit>

      <Afsnit nr={2} titel="Hvad siden er">
        <p>
          Klassementet er en uafhængig dansk informationstjeneste om professionel cykelsport. Vi
          samler etapeinformation, højde- og stigningsprofiler, startlister, favoritvurderinger,
          resultater og nyheder på ét sted.
        </p>
        <p>
          Vi er <strong>ikke</strong> tilknyttet UCI, ASO, RCS Sport, noget cykelhold, nogen
          arrangør eller noget forbund. Navne på løb, hold og ryttere bruges udelukkende
          beskrivende til at identificere, hvad indholdet handler om.
        </p>
        <p>
          Siden tilbyder ikke live-tracking eller live-opdatering af igangværende løb, og den skal
          ikke bruges som officiel resultatkilde. Officielle resultater fastsættes af arrangøren og
          UCI.
        </p>
      </Afsnit>

      <Afsnit nr={3} titel="Sådan må du bruge siden">
        <p>Du må frit læse, dele links til og citere siden med kildeangivelse. Du må ikke:</p>
        <ul>
          <li>
            systematisk hente, kopiere eller genudgive vores indhold eller datasæt — hverken manuelt
            eller med scraping, crawling eller automatiserede værktøjer — ud over hvad almindelig
            søgemaskineindeksering indebærer
          </li>
          <li>
            bruge vores indhold til at opbygge en konkurrerende database eller tjeneste, eller
            videresælge det
          </li>
          <li>
            forsøge at få uautoriseret adgang til siden, dens API, database eller
            administrationsområde, eller omgå tekniske begrænsninger
          </li>
          <li>
            belaste siden urimeligt, forsøge at gøre den utilgængelig eller indsætte skadelig kode
          </li>
          <li>
            fjerne eller skjule mærkning af sponsoreret indhold, kildeangivelser eller kreditering
          </li>
        </ul>
        <p>
          Vil du bruge vores indhold eller data i større omfang — fx i en app, en publikation eller
          et forskningsprojekt — så spørg os via <KontaktLink />. Vi siger som regel ja, når vi
          bliver spurgt.
        </p>
      </Afsnit>

      <Afsnit nr={4} titel="Data og nøjagtighed">
        <p>
          Korrekte data er hele grundlaget for siden, og vi lægger et stort arbejde i at verificere
          dem mod kilderne. Vi oplyser, hvor data kommer fra, og vi retter fejl, så snart vi bliver
          bekendt med dem.
        </p>
        <p>
          Alligevel kan vi ikke garantere, at alt indhold altid er fuldstændigt, korrekt og
          opdateret. Ruter ændres, startlister justeres i sidste øjeblik, og kilder kan selv
          indeholde fejl. Indholdet stilles derfor til rådighed til information — ikke som
          beslutningsgrundlag.
        </p>
        <p>
          Finder du en fejl, vil vi meget gerne høre det via <KontaktLink />. Det er den hurtigste
          vej til at få den rettet for alle.
        </p>
      </Afsnit>

      <Afsnit nr={5} titel="Ingen rådgivning — og ingen opfordring til spil">
        <p>
          Favoritvurderinger, formanalyser og terrænbeskrivelser på siden er redaktionelle
          vurderinger af sportslig karakter. De er ikke væddemålsrådgivning, spilanbefalinger,
          økonomisk rådgivning eller træningsrådgivning, og de skal ikke forstås som en opfordring
          til at spille penge på cykelløb.
        </p>
        <p>
          Beslutter du at bruge siden som baggrund for noget som helst, sker det på eget ansvar.
          Stigningsprofiler og højdedata er beregnet til at forstå et løb — ikke til navigation,
          rutelægning eller sikkerhedskritisk brug under cykling.
        </p>
      </Afsnit>

      <Afsnit nr={6} titel="Immaterielle rettigheder">
        <p>
          Vores egne tekster, analyser, grafik, logo, design, databasestruktur og de højde- og
          stigningsprofiler, vi selv har tegnet, tilhører os og er beskyttet af ophavsretsloven. Du
          må gerne citere kort med tydelig kildeangivelse og et link, men ikke gengive hele
          artikler eller profiler uden vores tilladelse.
        </p>
        <p>
          Faktuelle sportsdata — resultater, distancer, højdemeter, startlister — er indsamlet fra
          offentligt tilgængelige kilder, i dag UCI, ProCyclingStats og VeloWire. Rettighederne til
          de oprindelige kilders egne databaser og fremstillinger tilhører dem.
        </p>
        <p>
          Billeder på siden anvendes på grundlag af licens, officielle indlejringer eller frie
          kilder. Mener du, at et billede eller et tekststykke er brugt uden den fornødne ret, så
          kontakt os via <KontaktLink /> med en beskrivelse af materialet. Vi reagerer hurtigt og fjerner materialet, mens sagen afklares.
        </p>
        <p>
          Varemærker, holdnavne og løbsnavne tilhører deres respektive ejere og bruges alene
          beskrivende.
        </p>
      </Afsnit>

      <Afsnit nr={7} titel="Sponsoreret indhold og annoncering">
        <p>
          Siden finansieres ved sponsoreret indhold — advertorials og kommercielle artikler, der er
          betalt af en annoncør og kan indeholde links til annoncørens website.
        </p>
        <p>
          <strong>Alt sponsoreret indhold er tydeligt mærket som sponsoreret</strong>, både i
          oversigter og øverst på selve artiklen, så du altid kan se, hvornår du læser kommercielt
          indhold. Det følger markedsføringslovens forbud mod skjult reklame, og det er noget vi
          mener principielt: du skal aldrig snydes til at klikke på noget.
        </p>
        <p>
          Indholdet i en advertorial er leveret eller godkendt af annoncøren og er ikke redaktionelt
          indhold fra Klassementet. Vi indestår ikke for annoncørens oplysninger, produkter, priser
          eller tilbud, og et sponsoreret indlæg er ikke en anbefaling fra os.
        </p>
        <p>
          Sponsoreret indhold påvirker ikke vores redaktionelle dækning af løb, ryttere og
          resultater. Vi afviser indhold, der er vildledende, ulovligt eller uden reel værdi for
          læserne.
        </p>
      </Afsnit>

      <Afsnit nr={8} titel="Links og indhold fra tredjepart">
        <p>
          Siden indeholder links til andre websites og kan vise indlejret indhold fra tredjepart, fx
          3D-stigningsprofiler fra VeloViewer og kortfliser fra OpenStreetMap. Vi har ingen kontrol
          over disse tjenester og er ikke ansvarlige for deres indhold, tilgængelighed eller
          behandling af dine oplysninger.
        </p>
        <p>
          Indlejret indhold fra tredjepart indlæses kun, hvis du har givet samtykke til det. Se{" "}
          <Link href="/cookiepolitik">cookiepolitikken</Link>.
        </p>
      </Afsnit>

      <Afsnit nr={9} titel="Hvis du sender os noget">
        <p>
          Sender du os et nyhedstip, en rettelse, en kommentar eller andet materiale, giver du os ret
          til at bruge det i vores dækning uden betaling. Du indestår for, at du har ret til at
          sende materialet, og at det ikke krænker andres rettigheder.
        </p>
        <p>
          Vi er ikke forpligtet til at bruge, besvare eller gemme indsendt materiale, og vi
          offentliggør ikke dit navn uden din accept.
        </p>
      </Afsnit>

      <Afsnit nr={10} titel="Tilgængelighed og ændringer">
        <p>
          Vi tilstræber, at siden er tilgængelig døgnet rundt, men vi garanterer ikke uafbrudt drift.
          Siden kan være utilgængelig på grund af vedligeholdelse, opdateringer, fejl eller forhold
          hos vores leverandører.
        </p>
        <p>
          Vi kan til enhver tid ændre, udvide eller fjerne funktioner og indhold på siden uden
          varsel.
        </p>
      </Afsnit>

      <Afsnit nr={11} titel="Ansvar">
        <p>
          Siden stilles til rådighed, som den er. Vi er ikke ansvarlige for indirekte tab eller
          følgeskader — herunder driftstab, tab af data, tabt fortjeneste eller tab som følge af
          beslutninger truffet på grundlag af indhold på siden.
        </p>
        <p>
          Vi er heller ikke ansvarlige for tab, der skyldes nedetid, fejl hos vores leverandører,
          tredjepartsindhold eller forhold uden for vores kontrol.
        </p>
        <p>
          Denne begrænsning gælder kun i det omfang, dansk ret tillader det. Vi begrænser ikke vores
          ansvar for forsætlige eller groft uagtsomme handlinger, for personskade, eller hvor ansvar
          i øvrigt ikke kan fraskrives — herunder efter ufravigelige forbrugerbeskyttelsesregler.
        </p>
      </Afsnit>

      <Afsnit nr={12} titel="Personoplysninger">
        <p>
          Hvordan vi behandler personoplysninger, står i vores{" "}
          <Link href="/privatlivspolitik">privatlivspolitik</Link>, og hvilke cookies vi bruger,
          står i <Link href="/cookiepolitik">cookiepolitikken</Link>. De to politikker er en del af
          disse vilkår.
        </p>
      </Afsnit>

      <Afsnit nr={13} titel="Lovvalg og tvister">
        <p>
          Vilkårene er underlagt dansk ret, og tvister afgøres af de danske domstole. Er du
          forbruger, berører dette ikke de rettigheder, du har efter ufravigelige regler i dit eget
          bopælsland, herunder retten til at anlægge sag dér.
        </p>
        <p>
          Er en enkelt bestemmelse i disse vilkår ugyldig, består de øvrige bestemmelser uændret.
        </p>
      </Afsnit>

      <Afsnit nr={14} titel="Kontakt og ændringer af vilkårene">
        <p>
          Spørgsmål til vilkårene, rettighedshenvendelser og andet sender du via <KontaktLink />.
        </p>
        <p>
          Vi kan opdatere disse vilkår, fx hvis siden får nye funktioner, eller lovgivningen ændrer
          sig. Den gældende version ligger altid her med datoen for seneste opdatering øverst.
          Fortsætter du med at bruge siden efter en ændring, gælder de opdaterede vilkår.
        </p>
      </Afsnit>
    </JuridiskSide>
  );
}
