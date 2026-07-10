// En etape regnes som historisk, når dens løb er fra en tidligere sæson end
// den nuværende — udledt af årstallet i løbs-sluggen (fx "tour-de-france-2022"),
// IKKE etapens egen "date"-kolonne, som ofte er NULL for ældre, ufuldstændigt
// udfyldte etaperækker (bekræftet: tour-de-france-2022/stage/17 har date=null).
// Historiske etapesider fjernes (404) for at undgå tusindvis af langsomme,
// sjældent besøgte landingssider; vinder/resultat forbliver tilgængelig på
// selve løbssiden og i rytterprofilers palmares (uden link til etapesiden).
export function isHistoricRaceSlug(slug: string | null | undefined): boolean {
  if (!slug) return false;
  const match = slug.match(/-(\d{4})$/);
  if (!match) return false;
  const raceYear = parseInt(match[1], 10);
  return raceYear < new Date().getFullYear();
}
