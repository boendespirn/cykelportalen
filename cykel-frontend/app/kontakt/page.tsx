"use client";

import Link from "next/link";
import { useState } from "react";

type FormState = "idle" | "sending" | "success" | "error";

const INQUIRY_TYPES = [
  { value: "advertorial", label: "Publicere advertorial / blogindlæg" },
  { value: "annonce",     label: "Annoncering og sponsorater" },
  { value: "nyheder",     label: "Indsende nyhedstip" },
  { value: "andet",       label: "Andet" },
];

export default function KontaktPage() {
  const [state, setState] = useState<FormState>("idle");
  const [form, setForm] = useState({
    type: "",
    name: "",
    email: "",
    company: "",
    message: "",
  });

  function handleChange(e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) {
    setForm(f => ({ ...f, [e.target.name]: e.target.value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setState("sending");
    // Contact form backend activated at domain launch — formspree.io or custom endpoint
    // For now, show a "coming soon" success state
    await new Promise(r => setTimeout(r, 800));
    setState("success");
  }

  return (
    <div className="mx-auto max-w-2xl px-6 py-12">
      <header className="mb-12">
        <p className="text-xs uppercase tracking-[0.25em] text-emerald-400 mb-4">Skriv til os</p>
        <h1 className="font-display text-7xl sm:text-9xl tracking-wide leading-none text-white">
          Kontakt
        </h1>
        <p className="mt-5 text-slate-400 text-sm max-w-sm leading-relaxed">
          Interesseret i at annoncere, publicere indhold eller samarbejde med Cykelportalen?
          Udfyld formularen og vi vender tilbage hurtigst muligt.
        </p>
      </header>

      {/* Quick links */}
      <div className="grid sm:grid-cols-2 gap-3 mb-10">
        <Link href="/advertorials"
          className="group rounded-xl border border-slate-800 bg-slate-900/40 p-4 hover:border-emerald-500/30 transition-colors">
          <p className="text-sm font-medium text-slate-200 group-hover:text-emerald-400 transition-colors mb-1">
            Advertorials & Blogindlæg
          </p>
          <p className="text-xs text-slate-600 leading-relaxed">
            Publicer sponsoreret indhold med links til din hjemmeside.
          </p>
        </Link>
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
          <p className="text-sm font-medium text-slate-200 mb-1">Annoncering</p>
          <p className="text-xs text-slate-600 leading-relaxed">
            Bannere, native ads og sponsorater på relevante løbssider.
          </p>
        </div>
      </div>

      {state === "success" ? (
        <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-10 text-center">
          <div className="w-12 h-12 rounded-full bg-emerald-500/20 flex items-center justify-center mx-auto mb-4">
            <svg className="w-6 h-6 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <p className="text-slate-200 font-medium mb-2">Tak for din besked!</p>
          <p className="text-slate-500 text-sm">Vi vender tilbage til dig hurtigst muligt.</p>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Inquiry type */}
          <div>
            <label className="block text-xs uppercase tracking-widest text-slate-500 mb-2">
              Hvad drejer det sig om?
            </label>
            <select
              name="type"
              value={form.type}
              onChange={handleChange}
              required
              className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-sm text-slate-200 focus:outline-none focus:border-emerald-500/60 transition-colors appearance-none"
            >
              <option value="" disabled>Vælg emne…</option>
              {INQUIRY_TYPES.map(t => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          {/* Name + Company */}
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs uppercase tracking-widest text-slate-500 mb-2">Navn</label>
              <input
                type="text"
                name="name"
                value={form.name}
                onChange={handleChange}
                required
                placeholder="Dit navn"
                className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-sm text-slate-200 placeholder-slate-700 focus:outline-none focus:border-emerald-500/60 transition-colors"
              />
            </div>
            <div>
              <label className="block text-xs uppercase tracking-widest text-slate-500 mb-2">Virksomhed</label>
              <input
                type="text"
                name="company"
                value={form.company}
                onChange={handleChange}
                placeholder="Valgfrit"
                className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-sm text-slate-200 placeholder-slate-700 focus:outline-none focus:border-emerald-500/60 transition-colors"
              />
            </div>
          </div>

          {/* Email */}
          <div>
            <label className="block text-xs uppercase tracking-widest text-slate-500 mb-2">E-mail</label>
            <input
              type="email"
              name="email"
              value={form.email}
              onChange={handleChange}
              required
              placeholder="din@email.dk"
              className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-sm text-slate-200 placeholder-slate-700 focus:outline-none focus:border-emerald-500/60 transition-colors"
            />
          </div>

          {/* Message */}
          <div>
            <label className="block text-xs uppercase tracking-widest text-slate-500 mb-2">Besked</label>
            <textarea
              name="message"
              value={form.message}
              onChange={handleChange}
              required
              rows={5}
              placeholder="Beskriv hvad du ønsker…"
              className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-sm text-slate-200 placeholder-slate-700 focus:outline-none focus:border-emerald-500/60 transition-colors resize-none"
            />
          </div>

          <button
            type="submit"
            disabled={state === "sending"}
            className="w-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded-xl px-6 py-3.5 text-sm font-medium hover:bg-emerald-500/20 hover:border-emerald-500/40 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {state === "sending" ? "Sender…" : "Send besked"}
          </button>

          <p className="text-xs text-slate-700 text-center">
            Formularen aktiveres ved domæne-lancering. Vi kan kontaktes på{" "}
            <span className="text-slate-600">kontakt@cykelportalen.dk</span> i mellemtiden.
          </p>
        </form>
      )}
    </div>
  );
}
