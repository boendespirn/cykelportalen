"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useAdminKey, adminGet, adminPost, timeAgo, AdminLogin } from "../adminKey";

type Run = {
  id: string;
  job_key: string;
  status: string;
  queued_at: string;
  finished_at: string | null;
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
};

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
  const [busy, setBusy] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!adminKey) return;
    const [r, s, j] = await Promise.all([
      adminGet<{ races: Race[] }>("/admin/pipelines/races", adminKey),
      adminGet<RunnerStatus>("/admin/pipelines/runner", adminKey),
      adminGet<{ jobs: Job[] }>("/admin/pipelines/jobs", adminKey),
    ]);
    if (r) setRaces(r.races);
    if (s) setRunner(s);
    if (j) setGlobalJobs(j.jobs.filter((x) => !x.needs_race));
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

  const runGlobal = async (jobKey: string) => {
    setBusy(jobKey);
    const res = await adminPost<{ queued: boolean; message: string | null }>(
      "/admin/pipelines/run", adminKey, { job_key: jobKey }
    );
    setBusy(null);
    setToast(res ? (res.message ?? "Lagt i kø") : "Kunne ikke lægges i kø");
    setTimeout(() => setToast(null), 4000);
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
                <div key={job.key} className="flex items-center gap-4 px-5 py-3">
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-slate-200">{job.label}</div>
                    <div className="text-xs text-slate-500 truncate">{job.description}</div>
                  </div>
                  <span className="text-xs text-slate-600 font-mono flex-shrink-0">~{job.est_minutes} min</span>
                  <button
                    onClick={() => runGlobal(job.key)}
                    disabled={busy === job.key}
                    className="text-xs px-3 py-1.5 rounded-lg border border-slate-700 text-slate-300 hover:border-emerald-500/60 hover:text-emerald-300 transition-colors disabled:opacity-40"
                  >
                    {busy === job.key ? "…" : "Kør"}
                  </button>
                </div>
              ))}
            </div>
          </section>
        </>
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
