"use client";

import { useState, useEffect, useCallback, use } from "react";
import Link from "next/link";
import {
  useAdminKey, adminGet, adminPost, timeAgo, formatDateTime, AdminLogin,
} from "../../adminKey";

type Check = {
  key: string;
  label: string;
  status: "ok" | "mangler" | "ikke_muligt";
  detail: string;
  fixed_by: string[];
  missing_items: string[];
};

type Run = {
  id: string;
  job_key: string;
  status: "queued" | "running" | "success" | "failed" | "cancelled";
  trigger: string;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  exit_code: number | null;
  validation_verdict: "ok" | "warning" | "error" | "skipped" | null;
  validation_note: string | null;
};

type Job = {
  key: string;
  label: string;
  phase: string;
  description: string;
  est_minutes: number;
  last_run: Run | null;
  would_fix: string[];
};

type Detail = {
  race: {
    slug: string; name: string; start_date: string; end_date: string | null;
    stage_count: number; raced_count: number;
    today_stage: number | null; cancelled_stages: number[];
  };
  completeness_pct: number;
  checks: Check[];
  jobs: Job[];
  recent_runs: Run[];
  phase_labels: Record<string, string>;
};

type RunnerStatus = { online: boolean; message: string | null };

const PHASE_ORDER = ["before", "during", "after"];

export default function RacePipelinePage(
  { params }: { params: Promise<{ slug: string }> }
) {
  const { slug } = use(params);
  const { adminKey, keyInput, setKeyInput, loginError, login, checked } = useAdminKey();
  const [data, setData] = useState<Detail | null>(null);
  const [runner, setRunner] = useState<RunnerStatus | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [openRun, setOpenRun] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  const load = useCallback(async () => {
    if (!adminKey) return;
    const [d, s] = await Promise.all([
      adminGet<Detail>(`/admin/pipelines/races/${slug}`, adminKey),
      adminGet<RunnerStatus>("/admin/pipelines/runner", adminKey),
    ]);
    if (d) setData(d); else setNotFound(true);
    if (s) setRunner(s);
  }, [adminKey, slug]);

  useEffect(() => { load(); }, [load]);

  // Mens noget kører, opdaterer vi hyppigt — ellers ville siden vise "i kø"
  // længe efter at jobbet var færdigt, og man ville trykke igen.
  const active = data?.recent_runs.some((r) => r.status === "queued" || r.status === "running");
  useEffect(() => {
    if (!adminKey) return;
    const t = setInterval(load, active ? 5000 : 30000);
    return () => clearInterval(t);
  }, [adminKey, load, active]);

  const runJob = async (jobKey: string) => {
    setBusy(jobKey);
    const res = await adminPost<{ queued: boolean; message: string | null }>(
      "/admin/pipelines/run", adminKey, { job_key: jobKey, race_slug: slug }
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
  if (notFound) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-10">
        <p className="text-sm text-slate-400">Løbet blev ikke fundet.</p>
        <Link href="/admin/pipelines" className="text-xs text-emerald-400">← Tilbage</Link>
      </div>
    );
  }
  if (!data) return <div className="mx-auto max-w-4xl px-6 py-10 text-sm text-slate-500">Henter …</div>;

  const missing = data.checks.filter((c) => c.status === "mangler");

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <Link href="/admin/pipelines"
            className="text-xs text-slate-600 hover:text-emerald-400 transition-colors">
        ← Alle løb
      </Link>

      <div className="mt-3 mb-6">
        <h1 className="font-display text-3xl tracking-widest text-white">{data.race.name}</h1>
        <p className="text-xs text-slate-500 mt-1">
          {data.race.raced_count} af {data.race.stage_count} etaper kørt
          {data.race.today_stage ? ` · etape ${data.race.today_stage} køres i dag` : ""}
          {data.race.cancelled_stages.length
            ? ` · etape ${data.race.cancelled_stages.join(", ")} aflyst`
            : ""}
        </p>
      </div>

      <CompletenessBar pct={data.completeness_pct} missingCount={missing.length} />

      {runner && !runner.online && (
        <div className="mb-6 rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-3">
          <p className="text-sm text-amber-300">Runner kører ikke</p>
          <p className="text-xs text-slate-400 mt-1">{runner.message}</p>
        </div>
      )}

      {toast && (
        <div className="mb-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-2.5 text-sm text-emerald-300">
          {toast}
        </div>
      )}

      <section className="mb-8">
        <h2 className="text-xs uppercase tracking-[0.2em] text-emerald-400 font-medium mb-3">
          Datafuldstændighed
        </h2>
        <div className="rounded-2xl border border-slate-800 bg-slate-900/40 divide-y divide-slate-800/60">
          {data.checks.map((c) => <CheckRow key={c.key} check={c} />)}
        </div>
      </section>

      {PHASE_ORDER.map((phase) => {
        const jobs = data.jobs.filter((j) => j.phase === phase);
        if (!jobs.length) return null;
        return (
          <section key={phase} className="mb-8">
            <h2 className="text-xs uppercase tracking-[0.2em] text-emerald-400 font-medium mb-3">
              {data.phase_labels[phase] ?? phase}
            </h2>
            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 divide-y divide-slate-800/60">
              {jobs.map((job) => (
                <JobRow key={job.key} job={job} busy={busy === job.key} onRun={() => runJob(job.key)} />
              ))}
            </div>
          </section>
        );
      })}

      <section>
        <h2 className="text-xs uppercase tracking-[0.2em] text-emerald-400 font-medium mb-3">
          Seneste kørsler
        </h2>
        {data.recent_runs.length === 0 ? (
          <p className="text-sm text-slate-500">Ingen kørsler registreret for dette løb endnu.</p>
        ) : (
          <div className="rounded-2xl border border-slate-800 bg-slate-900/40 divide-y divide-slate-800/60">
            {data.recent_runs.map((run) => (
              <RunRow key={run.id} run={run} adminKey={adminKey}
                      open={openRun === run.id}
                      onToggle={() => setOpenRun(openRun === run.id ? null : run.id)} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function CompletenessBar({ pct, missingCount }: { pct: number; missingCount: number }) {
  const color = pct >= 90 ? "bg-emerald-500" : pct >= 60 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="mb-6 rounded-2xl border border-slate-800 bg-slate-900/40 px-5 py-4">
      <div className="flex items-baseline justify-between mb-2">
        <span className="text-sm text-slate-300">Fuldstændighed</span>
        <span className="font-mono text-2xl text-white">{pct}%</span>
      </div>
      <div className="h-2 rounded-full bg-slate-800 overflow-hidden">
        <div className={`h-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <p className="text-xs text-slate-500 mt-2">
        {missingCount === 0
          ? "Alt det, der kan skaffes, er skaffet."
          : `${missingCount} ${missingCount === 1 ? "område mangler" : "områder mangler"} data. Ting, der ikke findes, tæller ikke med.`}
      </p>
    </div>
  );
}

const CHECK_STYLE = {
  ok:          { dot: "bg-emerald-400", text: "text-slate-300" },
  mangler:     { dot: "bg-amber-400",   text: "text-amber-200" },
  ikke_muligt: { dot: "bg-slate-700",   text: "text-slate-500" },
} as const;

function CheckRow({ check }: { check: Check }) {
  const style = CHECK_STYLE[check.status];
  return (
    <div className="flex items-start gap-3 px-5 py-3">
      <span className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${style.dot}`} />
      <div className="min-w-0 flex-1">
        <div className="text-sm text-slate-200">{check.label}</div>
        <div className={`text-xs ${style.text}`}>{check.detail}</div>
        {check.missing_items.length > 0 && (
          <div className="text-xs text-slate-600 font-mono mt-1">
            {check.missing_items.join(", ")}
          </div>
        )}
      </div>
      {check.status === "ikke_muligt" && (
        <span className="text-xs text-slate-600 flex-shrink-0">ikke muligt</span>
      )}
    </div>
  );
}

function JobRow({ job, busy, onRun }: { job: Job; busy: boolean; onRun: () => void }) {
  const last = job.last_run;
  const isActive = last?.status === "queued" || last?.status === "running";
  return (
    <div className="flex items-center gap-4 px-5 py-3">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm text-slate-200">{job.label}</span>
          {job.would_fix.length > 0 && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30">
              lukker: {job.would_fix.join(", ")}
            </span>
          )}
        </div>
        <div className="text-xs text-slate-500 truncate">{job.description}</div>
        <div className="text-xs text-slate-600 mt-0.5">
          {last ? (
            <>
              sidst {timeAgo(last.queued_at)}
              {last.validation_verdict && last.validation_verdict !== "ok" && (
                <span className="text-amber-400"> · {last.validation_note}</span>
              )}
            </>
          ) : "aldrig kørt"}
        </div>
      </div>
      <span className="text-xs text-slate-600 font-mono flex-shrink-0 hidden sm:inline">
        ~{job.est_minutes} min
      </span>
      <button
        onClick={onRun}
        disabled={busy || isActive}
        className="text-xs px-3 py-1.5 rounded-lg border border-slate-700 text-slate-300 hover:border-emerald-500/60 hover:text-emerald-300 transition-colors disabled:opacity-40 flex-shrink-0"
      >
        {isActive ? (last?.status === "running" ? "Kører …" : "I kø") : busy ? "…" : "Kør"}
      </button>
    </div>
  );
}

const STATUS_STYLE: Record<string, string> = {
  queued:  "bg-slate-500/15 text-slate-300 border-slate-600/40",
  running: "bg-blue-500/15 text-blue-300 border-blue-500/30",
  success: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  failed:  "bg-red-500/15 text-red-300 border-red-500/30",
  cancelled: "bg-slate-500/15 text-slate-400 border-slate-600/40",
};

const VERDICT_STYLE: Record<string, string> = {
  ok:      "text-emerald-400",
  warning: "text-amber-400",
  error:   "text-red-400",
  skipped: "text-slate-500",
};

const VERDICT_LABEL: Record<string, string> = {
  ok: "Kontrolleret OK", warning: "Advarsel", error: "Fejl", skipped: "Ikke kontrolleret",
};

function RunRow({ run, adminKey, open, onToggle }: {
  run: Run; adminKey: string; open: boolean; onToggle: () => void;
}) {
  const [log, setLog] = useState<string | null>(null);

  useEffect(() => {
    if (!open || log !== null) return;
    adminGet<{ log_tail: string | null }>(`/admin/pipelines/runs/${run.id}`, adminKey)
      .then((d) => setLog(d?.log_tail ?? "(ingen log gemt)"));
  }, [open, log, run.id, adminKey]);

  return (
    <div className="px-5 py-3">
      <button onClick={onToggle} className="w-full flex items-center gap-3 text-left">
        <span className={`text-xs px-2 py-0.5 rounded-full border flex-shrink-0 ${STATUS_STYLE[run.status]}`}>
          {run.status}
        </span>
        <span className="text-sm text-slate-300 flex-1 min-w-0 truncate">{run.job_key}</span>
        {run.validation_verdict && (
          <span className={`text-xs flex-shrink-0 ${VERDICT_STYLE[run.validation_verdict]}`}>
            {VERDICT_LABEL[run.validation_verdict]}
          </span>
        )}
        <span className="text-xs text-slate-600 flex-shrink-0 hidden sm:inline">
          {formatDateTime(run.queued_at)}
        </span>
        <span className="text-slate-600 text-xs">{open ? "▲" : "▼"}</span>
      </button>

      {run.validation_note && (
        <p className={`text-xs mt-1.5 ${VERDICT_STYLE[run.validation_verdict ?? "skipped"]}`}>
          {run.validation_note}
        </p>
      )}

      {open && (
        <div className="mt-3 space-y-2">
          <div className="text-xs text-slate-500 font-mono">
            udløst af {run.trigger} · start {formatDateTime(run.started_at)} ·
            slut {formatDateTime(run.finished_at)} · exit {run.exit_code ?? "—"}
          </div>
          <pre className="text-xs text-slate-400 bg-slate-950 border border-slate-800 rounded-xl p-3 overflow-x-auto max-h-80 whitespace-pre-wrap">
            {log ?? "Henter log …"}
          </pre>
        </div>
      )}
    </div>
  );
}
