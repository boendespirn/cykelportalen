import Link from "next/link";

type Race = {
  name: string;
  slug: string;
  start_date: string;
  country_code: string | null;
  category: string;
};

async function getRaces(): Promise<Race[]> {
  const response = await fetch("http://127.0.0.1:8000/upcoming-races", {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("Kunne ikke hente løb");
  }

  return response.json();
}

export default async function Home() {
  const races = await getRaces();

  return (
    <main className="min-h-screen bg-slate-950 text-white px-6 py-10">
      <div className="mx-auto max-w-5xl">
        <p className="text-sm uppercase tracking-widest text-emerald-400">
          Dansk cykelportal
        </p>

        <h1 className="mt-3 text-4xl font-bold">Kommende cykelløb</h1>

        <p className="mt-4 text-slate-300">
          Kalender over kommende WorldTour-løb med dato, kategori og land.
        </p>

        <div className="mt-10 grid gap-4">
          {races.map((race) => (
            <Link
              href={`/${race.slug}`}
              key={`${race.slug}-${race.start_date}`}
              className="rounded-2xl border border-slate-800 bg-slate-900 p-5 shadow-lg transition hover:border-emerald-500 hover:bg-slate-800"
            >
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 className="text-xl font-semibold">{race.name}</h2>
                  <p className="mt-1 text-sm text-slate-400">
                    {race.start_date}
                  </p>
                </div>

                <div className="flex gap-2">
                  <span className="rounded-full bg-emerald-500/10 px-3 py-1 text-sm text-emerald-300">
                    {race.category}
                  </span>

                  <span className="rounded-full bg-slate-800 px-3 py-1 text-sm text-slate-300">
                    {race.country_code ?? "Ukendt land"}
                  </span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </main>
  );
}