"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useAdminKey, adminGet, adminPost, timeAgo, AdminLogin } from "../adminKey";

type Run = {
  id: string;
  job_key: string;
  race_slug: string | null;
  stage_number: number | null;
  status: string;
  queued_at: string;
  not_before: string | null;
  finished_at: string | null;
  cancel_requested: boolean;
  validation_verdict: string | null;
  validation_note: string | null;
};

type Race = {
  name: string;
  slug: string;
  start_date: string;
  end_date: string | null;
  category: string | null;
  phase: "i_gang" | "kommende" | "afsluttet";
  last_run: Run | null;
  run_count: number;
  failed_count: number;
  active_count: number;
};

type RunnerStatus = {
  online: boolean;
  host: string | null;
  last_seen: string | null;
  message: string | null;
};

type Job = {
  key: string;
  label: string;
  phase: string;
  needs_race: boolean;
  description: string;
  est_minutes: number;
  step_labels: string[];
};

const isActive = (r: Run | null | undefined) =>
  r?.status === "queued" || r?.status === "running";

/** Sekunder til et tidspunkt i fremtiden — 0 naar det er passeret. Driver
 *  fortryd-nedtaellingen paa Afbryd-knappen. */
function secondsUntil(iso: string | null | undefined, now: number): number {
  if (!iso) return 0;
  return Math.max(0, Math.ceil((new Date(iso).getTime() - now) / 1000));
}

const PHASE_ORDER: Race["phase"][] = ["i_gang", "kommende", "afsluttet"];
const PHASE_TITLES: Record<Race["phase"], string> = {
  i_gang: "Kører nu",
  kommende: "På vej",
  afsluttet: "Afsluttede",
};

export default function PipelinesPage() {
  const { adminKey, keyInput, setKeyInput, loginError, login, logout, checked } = useAdminKey();
  const [races, setRaces] = useState<Race[]>([]);
  const [runner, setRunner] = useState<RunnerStatus | null>(null);
  const [globalJobs, setGlobalJobs] = useState<Job[]>([]);
  // Seneste koersel pr. globalt job — det er den, Afbryd-knappen peger paa.
  const [globalRuns, setGlobalRuns] = useState<Record<string, Run>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [clock, setClock] = useState(() => Date.now());

  const load = useCallback(async () => {
    if (!adminKey) return;
    const [r, s, j, runs] = await Promise.all([
      adminGet<{ races: Race[] }>("/admin/pipelines/races", adminKey),
      adminGet<RunnerStatus>("/admin/pipelines/runner", adminKey),
      adminGet<{ jobs: Job[] }>("/admin/pipelines/jobs", adminKey),
      adminGet<{ runs: Run[] }>("/admin/pipelines/runs?limit=100", adminKey),
    ]);
    if (r) setRaces(r.races);
    if (s) setRunner(s);
    if (j) setGlobalJobs(j.jobs.filter((x) => !x.needs_race));
    if (runs) {
      // Listen kommer nyest foerst, saa den foerste forekomst af et job_key er
      // den seneste koersel. Kun de loebsloese job hoerer til paa denne side.
      const latest: Record<string, Run> = {};
      for (const run of runs.runs) {
        if (run.race_slug) continue;
        if (!latest[run.job_key]) latest[run.job_key] = run;
      }
      setGlobalRuns(latest);
    }
    setLoading(false);
  }, [adminKey]);

  useEffect(() => { load(); }, [load]);

  // Runner-status ældes hurtigt: hjerteslaget er 15 sekunder, så en visning,
  // der ikke opdaterer sig, ville påstå "online" længe efter at PC'en var slukket.
  useEffect(() => {
    if (!adminKey) return;
    const t = setInterval(load, 20000);
    return () => clearInterval(t);
  }, [adminKey, load]);

  const anyActive = Object.values(globalRuns).some(isActive);
  useEffect(() => {
    if (!anyActive) return;
    const t = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(t);
  }, [anyActive]);

  const say = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 5000);
  };

  const runGlobal = async (jobKey: string) => {
    setBusy(jobKey);
    const res = await adminPost<{ queued: boolean; message: string | null }>(
      "/admin/pipelines/run", adminKey, { job_key: jobKey }
    );
    setBusy(null);
    say(res ? (res.message ?? "Lagt i kø — du kan nå at fortryde") : "Kunne ikke lægges i kø");
    load();
  };

  const cancelRun = async (runId: string) => {
    setBusy(runId);
    const res = await adminPost<{ cancelled: boolean; message: string }>(
      `/admin/pipelines/runs/${runId}/cancel`, adminKey, {}
    );
    setBusy(null);
    say(res ? res.message : "Kunne ikke afbryde");
    load();
  };

  if (!checked) return null;
  if (!adminKey) {
    return <AdminLogin keyInput={keyInput} setKeyInput={setKeyInput}
                       loginError={loginError} onLogin={login} />;
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display text-3xl tracking-widest text-white">Pipelines</h1>
          <p className="text-xs text-slate-500 mt-1">Agentkørsler og datafuldstændighed · Klassementet</p>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/admin" className="text-xs text-slate-600 hover:text-emerald-400 transition-colors">
            ← Artikler
          </Link>
          <button onClick={logout}
                  className="text-xs text-slate-600 hover:text-red-400 transition-colors px-3 py-1.5 border border-slate-800 rounded-lg">
            Log ud
          </button>
        </div>
      </div>

      <RunnerBanner runner={runner} />

      {toast && (
        <div className="mb-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-2.5 text-sm text-emerald-300">
          {toast}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-slate-500">Henter …</p>
      ) : (
        <>
          {PHASE_ORDER.map((phase) => {
            const list = races.filter((r) => r.phase === phase);
            if (!list.length) return null;
            return (
              <section key={phase} className="mb-8">
                <h2 className="text-xs uppercase tracking-[0.2em] text-emerald-400 font-medium mb-3">
                  {PHASE_TITLES[phase]}
                </h2>
                <div className="space-y-2">
                  {list.map((race) => <RaceRow key={race.slug} race={race} />)}
                </div>
              </section>
            );
          })}

          <section className="mb-8">
            <h2 className="text-xs uppercase tracking-[0.2em] text-emerald-400 font-medium mb-3">
              Uafhængigt af løb
            </h2>
            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 divide-y divide-slate-800/60">
              {globalJobs.map((job) => (
                <GlobalJobRow
                  key={job.key}
                  job={job}
                  run={globalRuns[job.key] ?? null}
                  busy={busy === job.key || busy === globalRuns[job.key]?.id}
                  clock={clock}
                  onRun={() => runGlobal(job.key)}
                  onCancel={() => {
                    const run = globalRuns[job.key];
                    if (run) cancelRun(run.id);
                  }}
                />
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function GlobalJobRow({ job, run, busy, clock, onRun, onCancel }: {
  job: Job; run: Run | null; busy: boolean; clock: number;
  onRun: () => void; onCancel: () => void;
}) {
  const active = isActive(run);
  // Saa laenge not_before ligger i fremtiden, har runneren ikke roert jobbet —
  // et klik paa Afbryd her efterlader databasen fuldstaendig urort.
  const undoLeft = run?.status === "queued" ? secondsUntil(run.not_before, clock) : 0;

  return (
    <div className="px-5 py-3">
      <div className="flex items-center gap-4">
        <div className="flex-1 min-w-0">
          <div className="text-sm text-slate-200">{job.label}</div>
          <div className="text-xs text-slate-500 truncate">{job.description}</div>
        </div>
        <span className="text-xs text-slate-600 font-mono flex-shrink-0">~{job.est_minutes} min</span>
        {active ? (
          <button
            onClick={onCancel}
            disabled={busy || run?.cancel_requested}
            className="text-xs px-3 py-1.5 rounded-lg border border-red-500/50 text-red-300 hover:bg-red-500/10 transition-colors disabled:opacity-40 w-28"
          >
            {run?.cancel_requested
              ? "Stopper …"
              : undoLeft > 0
                ? `Afbryd (${undoLeft}s)`
                : run?.status === "running" ? "Afbryd kørsel" : "Afbryd"}
          </button>
        ) : (
          <button
            onClick={onRun}
            disabled={busy}
            className="text-xs px-3 py-1.5 rounded-lg border border-slate-700 text-slate-300 hover:border-emerald-500/60 hover:text-emerald-300 transition-colors disabled:opacity-40 w-28"
          >
            {busy ? "…" : "Kør"}
          </button>
        )}
      </div>
      {active && (
        <p className="text-xs mt-1.5 text-slate-500">
          {run?.status === "queued"
            ? undoLeft > 0
              ? `I kø — starter om ${undoLeft} sek. Afbryder du nu, bliver intet ændret.`
              : "I kø — venter på runneren. Afbryder du nu, bliver intet ændret."
            : "Kører nu. Afbryder du, stopper processen, men det, der allerede er gemt, bliver stående."}
        </p>
      )}
    </div>
  );
}

function RunnerBanner({ runner }: { runner: RunnerStatus | null }) {
  if (!runner) return null;
  if (runner.online) {
    return (
      <div className="mb-6 flex items-center gap-2 rounded-xl border border-emerald-500/25 bg-emerald-500/5 px-4 py-2.5">
        <span className="w-2 h-2 rounded-full bg-emerald-400 flex-shrink-0" />
        <span className="text-sm text-emerald-300">Runner kører</span>
        <span className="text-xs text-slate-500">· {runner.host} · sidst set {timeAgo(runner.last_seen)}</span>
      </div>
    );
  }
  return (
    <div className="mb-6 rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-3">
      <div className="flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-amber-400 flex-shrink-0" />
        <span className="text-sm text-amber-300">Runner kører ikke</span>
      </div>
      <p className="text-xs text-slate-400 mt-1.5">{runner.message}</p>
      <code className="mt-2 inline-block text-xs text-slate-300 bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1 font-mono">
        python runner.py
      </code>
    </div>
  );
}

function RaceRow({ race }: { race: Race }) {
  const status = race.last_run;
  return (
    <Link
      href={`/admin/pipelines/${race.slug}`}
      className="flex items-center gap-4 rounded-xl border border-slate-800 bg-slate-900/40 px-5 py-3 hover:border-slate-700 transition-colors"
    >
      <div className="flex-1 min-w-0">
        <div className="text-sm text-slate-100 truncate">{race.name}</div>
        <div className="text-xs text-slate-500">
          {race.start_date}
          {race.end_date && race.end_date !== race.start_date ? ` – ${race.end_date}` : ""}
        </div>
      </div>

      {race.active_count > 0 && (
        <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-300 border border-blue-500/30 flex-shrink-0">
          {race.active_count} i gang
        </span>
      )}
      {race.failed_count > 0 && (
        <span className="text-xs px-2 py-0.5 rounded-full bg-red-500/15 text-red-300 border border-red-500/30 flex-shrink-0">
          {race.failed_count} fejlet
        </span>
      )}

      <span className="text-xs text-slate-500 flex-shrink-0 hidden sm:inline">
        {race.run_count === 0 ? "aldrig kørt" : `sidst ${timeAgo(status?.queued_at)}`}
      </span>
      <span className="text-slate-600">→</span>
    </Link>
  );
}
