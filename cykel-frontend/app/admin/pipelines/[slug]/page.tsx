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
  stage_number: number | null;
  status: "queued" | "running" | "success" | "failed" | "cancelled";
  trigger: string;
  queued_at: string;
  not_before: string | null;
  started_at: string | null;
  finished_at: string | null;
  exit_code: number | null;
  cancel_requested: boolean;
  validation_verdict: "ok" | "warning" | "error" | "skipped" | null;
  validation_note: string | null;
};

type Job = {
  key: string;
  label: string;
  phase: string;
  description: string;
  est_minutes: number;
  est_stage_minutes: number | null;
  supports_stage: boolean;
  step_labels: string[];
  last_run: Run | null;
  would_fix: string[];
  // Trin hvis kilde ikke findes for dette løb — agenten springer dem over.
  blocked_steps: string[];
  fully_blocked: boolean;
};

// Hvad der overhovedet KAN hentes for løbet. Adskilt fra Check, som måler
// hvad vi allerede HAR hentet.
type Source = {
  key: string;
  label: string;
  status: "ja" | "delvist" | "nej" | "ukendt" | "ikke_relevant";
  detail: string;
  paavirker: string[];
};

type Stage = {
  stage_number: number;
  label: string;
  date: string | null;
  cancelled: boolean;
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
  sources: Source[];
  stages: Stage[];
  recent_runs: Run[];
  phase_labels: Record<string, string>;
  cancel_window_seconds: number;
};

type RunnerStatus = { online: boolean; message: string | null };

const PHASE_ORDER = ["before", "during", "after"];

/** Sekunder til et tidspunkt i fremtiden — 0 når det er passeret. Bruges til
 *  fortryd-nedtællingen, så man kan se præcis hvor længe man har til at
 *  fortryde, i stedet for at gætte. */
function secondsUntil(iso: string | null | undefined, now: number): number {
  if (!iso) return 0;
  return Math.max(0, Math.ceil((new Date(iso).getTime() - now) / 1000));
}

const isActive = (r: Run | null | undefined) =>
  r?.status === "queued" || r?.status === "running";

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
  // Valgt omfang pr. job: "" = hele ræset, ellers etapenummeret som streng.
  const [scopes, setScopes] = useState<Record<string, string>>({});
  // Tikker hvert sekund, mens noget er aktivt — uden det ville fortryd-
  // nedtællingen stå stille, og man ville ikke turde stole på den.
  const [clock, setClock] = useState(() => Date.now());

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
  const active = data?.recent_runs.some(isActive) ?? false;
  useEffect(() => {
    if (!adminKey) return;
    const t = setInterval(load, active ? 5000 : 30000);
    return () => clearInterval(t);
  }, [adminKey, load, active]);

  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);

  const say = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 5000);
  };

  const runJob = async (job: Job) => {
    const picked = scopes[job.key] ?? "";
    const stage = picked === "" ? null : Number(picked);
    setBusy(job.key);
    const res = await adminPost<{ queued: boolean; message: string | null }>(
      "/admin/pipelines/run", adminKey,
      { job_key: job.key, race_slug: slug, stage_number: stage }
    );
    setBusy(null);
    const scopeText = stage === null ? "hele ræset" : `etape ${stage}`;
    say(res
      ? (res.message ?? `Lagt i kø for ${scopeText} — du kan nå at fortryde`)
      : "Kunne ikke lægges i kø");
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

      {/* ── Datakilder ──
          Står FØR fuldstændigheden, fordi den er forudsætningen: mangler
          kilden, er en "mangel" nedenfor ikke noget, man kan trykke sig ud af. */}
      {data.sources.length > 0 && (
        <section className="mb-8">
          <h2 className="text-xs uppercase tracking-[0.2em] text-emerald-400 font-medium mb-1">
            Datakilder
          </h2>
          <p className="text-xs text-slate-600 mb-3">
            Hvad der kan hentes for dette ræs — og hvad hver kilde bruges til
          </p>
          <div className="rounded-2xl border border-slate-800 bg-slate-900/40 divide-y divide-slate-800/60">
            {data.sources.map((s) => <SourceRow key={s.key} source={s} />)}
          </div>
        </section>
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
                <JobRow
                  key={job.key}
                  job={job}
                  stages={data.stages}
                  runnerOnline={runner?.online ?? true}
                  scope={scopes[job.key] ?? ""}
                  onScope={(v) => setScopes((s) => ({ ...s, [job.key]: v }))}
                  busy={busy === job.key || busy === job.last_run?.id}
                  clock={clock}
                  onRun={() => runJob(job)}
                  onCancel={() => job.last_run && cancelRun(job.last_run.id)}
                />
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
                      busy={busy === run.id}
                      clock={clock}
                      onCancel={() => cancelRun(run.id)}
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

const SOURCE_STYLE: Record<Source["status"], { ikon: string; farve: string; tekst: string }> = {
  ja:      { ikon: "✓", farve: "text-emerald-400", tekst: "text-slate-400" },
  delvist: { ikon: "~", farve: "text-amber-400",   tekst: "text-amber-200/80" },
  nej:     { ikon: "✕", farve: "text-red-400",     tekst: "text-slate-500" },
  ukendt:  { ikon: "?", farve: "text-slate-600",   tekst: "text-slate-600" },
  // Gaelder slet ikke for loebet. Neutral graa, ikke roed: det er ikke noget,
  // der skal udbedres, og et kryds ville faa en til at lede efter en loesning,
  // der ikke findes.
  ikke_relevant: { ikon: "–", farve: "text-slate-600", tekst: "text-slate-600" },
};

function SourceRow({ source }: { source: Source }) {
  const style = SOURCE_STYLE[source.status] ?? SOURCE_STYLE.ukendt;
  return (
    <div className="flex items-start gap-3 px-5 py-3">
      <span className={`font-mono text-sm mt-0.5 flex-shrink-0 w-4 text-center ${style.farve}`}>
        {style.ikon}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-sm text-slate-200">{source.label}</div>
        <div className={`text-xs break-words ${style.tekst}`}>{source.detail}</div>
        <div className="text-xs text-slate-600 mt-0.5">
          bruges til: {source.paavirker.join(", ")}
        </div>
      </div>
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

function JobRow({ job, stages, runnerOnline, scope, onScope, busy, clock, onRun, onCancel }: {
  job: Job;
  stages: Stage[];
  runnerOnline: boolean;
  scope: string;
  onScope: (v: string) => void;
  busy: boolean;
  clock: number;
  onRun: () => void;
  onCancel: () => void;
}) {
  const last = job.last_run;
  const running = isActive(last);
  // Fortryd-vinduet: så længe not_before ligger i fremtiden, har runneren
  // stadig ikke rørt jobbet, og et klik på Afbryd efterlader databasen urørt.
  const undoLeft = last?.status === "queued" ? secondsUntil(last.not_before, clock) : 0;
  const minutes = scope === "" ? job.est_minutes : (job.est_stage_minutes ?? job.est_minutes);

  return (
    <div className="px-5 py-3.5">
      <div className="flex items-start gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm text-slate-200">{job.label}</span>
            {job.step_labels.length > 1 && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-slate-700/40 text-slate-400 border border-slate-700">
                {job.step_labels.length} trin
              </span>
            )}
            {job.would_fix.length > 0 && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30">
                lukker: {job.would_fix.join(", ")}
              </span>
            )}
            {job.fully_blocked && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-red-500/15 text-red-300 border border-red-500/30">
                kilden mangler
              </span>
            )}
          </div>
          <div className="text-xs text-slate-500">{job.description}</div>
          {job.step_labels.length > 1 && (
            <div className="text-xs text-slate-600 mt-1 font-mono truncate">
              {job.step_labels.join(" → ")}
            </div>
          )}
          {/* Agenten springer selv de trin over, hvis kilde mangler. Uden denne
              linje ville man trykke, se en grøn kørsel og undre sig over, at
              manglen stadig står. */}
          {job.blocked_steps.length > 0 && (
            <div className={`text-xs mt-1 ${job.fully_blocked ? "text-red-400" : "text-amber-400/80"}`}>
              {job.fully_blocked
                ? "Kan ikke udrette noget for dette ræs — kilden mangler."
                : `Springer ${job.blocked_steps.length} trin over (kilden mangler): ${job.blocked_steps.join(", ")}`}
            </div>
          )}
          <div className="text-xs text-slate-600 mt-0.5">
            {last ? (
              <>
                sidst {timeAgo(last.queued_at)}
                {last.stage_number ? ` · etape ${last.stage_number}` : " · hele ræset"}
                {last.validation_verdict && last.validation_verdict !== "ok" && (
                  <span className="text-amber-400"> · {last.validation_note}</span>
                )}
              </>
            ) : "aldrig kørt"}
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <select
            value={scope}
            onChange={(e) => onScope(e.target.value)}
            disabled={!job.supports_stage}
            title={job.supports_stage
              ? "Kør for hele ræset eller for én etape"
              : "Dette job gælder altid hele ræset"}
            className="text-xs bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-slate-300 outline-none focus:border-emerald-500/60 disabled:opacity-40 max-w-[15rem]"
          >
            <option value="">Hele ræset</option>
            {job.supports_stage && stages.map((s) => (
              <option key={s.stage_number} value={String(s.stage_number)}>
                {s.label}{s.cancelled ? " (aflyst)" : ""}
              </option>
            ))}
          </select>

          <span className="text-xs text-slate-600 font-mono hidden sm:inline w-14 text-right">
            ~{minutes} min
          </span>

          {/* Kør bliver stående, selv mens noget er aktivt: med etapevalg er det
              helt normalt at ville lægge etape 6 i kø, mens etape 5 venter.
              API'et afviser selv en dublet af præcis samme job + løb + etape. */}
          {running && (
            <button
              onClick={onCancel}
              disabled={busy}
              title={last?.cancel_requested && !runnerOnline
                ? "Runneren svarer ikke — tryk igen for at frigive kørslen"
                : undefined}
              className="text-xs px-3 py-1.5 rounded-lg border border-red-500/50 text-red-300 hover:bg-red-500/10 transition-colors disabled:opacity-40 w-28"
            >
              {last?.cancel_requested
                ? (runnerOnline ? "Stopper …" : "Frigiv")
                : undoLeft > 0
                  ? `Afbryd (${undoLeft}s)`
                  : last?.status === "running" ? "Afbryd kørsel" : "Afbryd"}
            </button>
          )}
          <button
            onClick={onRun}
            disabled={busy}
            className="text-xs px-3 py-1.5 rounded-lg border border-slate-700 text-slate-300 hover:border-emerald-500/60 hover:text-emerald-300 transition-colors disabled:opacity-40 w-28"
          >
            {busy ? "…" : "Kør"}
          </button>
        </div>
      </div>

      {running && (
        <p className={`text-xs mt-2 ${last?.cancel_requested && !runnerOnline ? "text-amber-400" : "text-slate-500"}`}>
          {last?.cancel_requested
            ? runnerOnline
              ? "Stopper kørslen — runneren læser beskeden inden for få sekunder."
              : "Runneren svarer ikke, så ingen kan bekræfte at processen er stoppet. "
                + "Tryk “Frigiv” for at lukke kørslen her, og kontrollér på PC'en at den faktisk er stoppet."
            : last?.status === "queued"
              ? undoLeft > 0
                ? `I kø — starter om ${undoLeft} sek. Afbryder du nu, bliver intet ændret.`
                : "I kø — venter på runneren. Afbryder du nu, bliver intet ændret."
              : "Kører nu. Afbryder du, stopper processen, men det, der allerede er gemt, bliver stående."}
        </p>
      )}
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

const STATUS_LABEL: Record<string, string> = {
  queued: "i kø", running: "kører", success: "ok", failed: "fejlet", cancelled: "afbrudt",
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

function RunRow({ run, adminKey, open, busy, clock, onToggle, onCancel }: {
  run: Run; adminKey: string; open: boolean; busy: boolean; clock: number;
  onToggle: () => void; onCancel: () => void;
}) {
  const [log, setLog] = useState<string | null>(null);
  const [label, setLabel] = useState<string | null>(null);

  useEffect(() => {
    if (!open || log !== null) return;
    adminGet<{ log_tail: string | null; job_label: string }>(
      `/admin/pipelines/runs/${run.id}`, adminKey
    ).then((d) => {
      setLog(d?.log_tail ?? "(ingen log gemt)");
      setLabel(d?.job_label ?? null);
    });
  }, [open, log, run.id, adminKey]);

  const undoLeft = run.status === "queued" ? secondsUntil(run.not_before, clock) : 0;

  return (
    <div className="px-5 py-3">
      <div className="flex items-center gap-3">
        <button onClick={onToggle} className="flex-1 min-w-0 flex items-center gap-3 text-left">
          <span className={`text-xs px-2 py-0.5 rounded-full border flex-shrink-0 ${STATUS_STYLE[run.status]}`}>
            {STATUS_LABEL[run.status] ?? run.status}
          </span>
          <span className="text-sm text-slate-300 flex-1 min-w-0 truncate">
            {label ?? run.job_key}
            <span className="text-slate-600">
              {" · "}{run.stage_number ? `etape ${run.stage_number}` : "hele ræset"}
            </span>
          </span>
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

        {isActive(run) && (
          <button
            onClick={onCancel}
            disabled={busy}
            className="text-xs px-2.5 py-1 rounded-lg border border-red-500/50 text-red-300 hover:bg-red-500/10 transition-colors disabled:opacity-40 flex-shrink-0"
          >
            {run.cancel_requested ? "Stopper …" : undoLeft > 0 ? `Afbryd (${undoLeft}s)` : "Afbryd"}
          </button>
        )}
      </div>

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
