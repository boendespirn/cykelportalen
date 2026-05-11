type Race = {
  name: string;
  slug: string;
  start_date: string;
  end_date: string;
  country_code: string | null;
  category: string;
};

type Stage = {
  stage_number: number;
  name: string;
  date: string;
  distance_km: number;
};

async function getRace(slug: string): Promise<Race> {
  const res = await fetch(`http://127.0.0.1:8000/races/${slug}`, {
    cache: "no-store",
  });

  return res.json();
}

async function getStages(slug: string): Promise<Stage[]> {
  const res = await fetch(`http://127.0.0.1:8000/races/${slug}/stages`, {
    cache: "no-store",
  });

  return res.json();
}

export default async function RacePage(props: {
  params: Promise<{ slug: string }>;
}) {
  const params = await props.params;

  const race = await getRace(params.slug);
  const stages = await getStages(params.slug);

  return (
    <main className="min-h-screen bg-slate-950 text-white px-6 py-10">
      <div className="mx-auto max-w-4xl">
        <a href="/" className="text-emerald-400 text-sm">
          ← Tilbage til kalender
        </a>

        <h1 className="mt-6 text-4xl font-bold">{race.name}</h1>

        <p className="mt-2 text-slate-400">
          {race.start_date} – {race.end_date}
        </p>

        <div className="mt-6 flex gap-3">
          <span className="rounded-full bg-emerald-500/10 px-3 py-1 text-sm text-emerald-300">
            {race.category}
          </span>

          <span className="rounded-full bg-slate-800 px-3 py-1 text-sm text-slate-300">
            {race.country_code ?? "Ukendt land"}
          </span>
        </div>

        {/* STAGES */}
        <div className="mt-10">
          <h2 className="text-2xl font-semibold">Etaper</h2>

          <div className="mt-4 grid gap-3">
            {stages.map((stage) => (
              <div
                key={stage.stage_number}
                className="rounded-xl bg-slate-900 p-4 border border-slate-800"
              >
                <div className="flex justify-between">
                  <span className="font-semibold">
                    Etape {stage.stage_number}
                  </span>
                  <span className="text-sm text-slate-400">
                    {stage.date}
                  </span>
                </div>

                <p className="mt-1 text-slate-300">
                  {stage.name}
                </p>

                <p className="text-sm text-slate-400">
                  {stage.distance_km} km
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}