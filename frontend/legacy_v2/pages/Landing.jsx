import { useState } from "react";
import { Logo } from "@/components/Logo";
import { RegimeCompareChart } from "@/components/charts/Charts";
import { inr } from "@/lib/format";
import {
  ArrowRight, ShieldCheck, FileText, GitCompareArrows, ScanLine,
  Lock, MessageCircle, FileJson, CheckCircle2, TrendingDown,
} from "lucide-react";

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
const login = () => {
  const redirectUrl = window.location.origin + "/dashboard";
  window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
};

const Nav = () => (
  <header className="sticky top-0 z-40 bg-background/85 backdrop-blur-md border-b border-mist">
    <div className="max-w-[1200px] mx-auto px-6 h-[72px] flex items-center justify-between">
      <Logo />
      <nav className="hidden md:flex items-center bg-ash pill px-5 py-2 gap-6">
        <a href="#product" className="font-display text-[15px] text-graphite hover:text-ember transition-colors">Product</a>
        <a href="#pipeline" className="font-display text-[15px] text-graphite hover:text-ember transition-colors">AI Pipeline</a>
        <a href="#compliance" className="font-display text-[15px] text-graphite hover:text-ember transition-colors">Compliance</a>
        <a href="#ca" className="font-display text-[15px] text-graphite hover:text-ember transition-colors">For CAs</a>
      </nav>
      <button onClick={login} data-testid="nav-login-btn"
        className="font-display text-[15px] bg-graphite text-white px-5 py-2.5 rounded-none hover:bg-ember transition-colors">
        Sign in
      </button>
    </div>
  </header>
);

const HeroCards = () => (
  <div className="relative pb-10 pr-4">
    <div className="bg-white border border-mist rounded-2xl p-6 rise d1">
      <div className="flex items-center justify-between mb-4">
        <span className="font-display text-[15px] text-graphite">Old vs New Regime</span>
        <span className="text-xs text-brass font-display">AY 2026-27</span>
      </div>
      <RegimeCompareChart oldTax={159510} newTax={99450} />
    </div>
    <div className="absolute -right-3 -bottom-4 w-52 bg-graphite text-white rounded-2xl p-5 rise d3 hidden sm:block shadow-xl">
      <div className="flex items-center gap-2 text-ember"><TrendingDown className="h-4 w-4" /><span className="text-xs font-display">You save</span></div>
      <div className="font-display text-3xl mt-2">{inr(60060)}</div>
      <div className="text-xs text-white/60 mt-1">by choosing the New regime</div>
    </div>
    <div className="absolute -left-6 -top-6 w-40 bg-ivory rounded-2xl p-4 rise d4 hidden lg:block shadow-lg">
      <div className="text-xs text-steel font-display">Parser confidence</div>
      <div className="font-display text-2xl text-graphite mt-1">98.4%</div>
      <div className="mt-2 h-1.5 bg-white rounded-full overflow-hidden"><div className="h-full bg-ember" style={{ width: "98%" }} /></div>
    </div>
  </div>
);

const Feature = ({ icon: Icon, title, desc }) => (
  <div className="bg-white border border-mist rounded-lg p-8 hover:border-graphite transition-colors duration-300">
    <div className="h-11 w-11 flex items-center justify-center bg-ash mb-6"><Icon className="h-5 w-5 text-graphite" strokeWidth={1.5} /></div>
    <h3 className="font-display text-xl text-graphite">{title}</h3>
    <p className="text-steel mt-2.5 text-[15px] leading-relaxed">{desc}</p>
  </div>
);

export default function Landing() {
  const [income, setIncome] = useState(1450000);
  const std = 75000;
  const taxable = Math.max(0, income - std);
  const quickTax = (() => {
    const slabs = [[400000, 0], [400000, 0.05], [400000, 0.1], [400000, 0.15], [800000, 0.2], [Infinity, 0.3]];
    let t = 0, r = taxable;
    for (const [lim, rate] of slabs) { if (r <= 0) break; const s = Math.min(r, lim); t += s * rate; r -= s; }
    if (taxable <= 700000) t = 0;
    return Math.round(t * 1.04);
  })();

  return (
    <div className="min-h-screen bg-background">
      <Nav />

      {/* Hero */}
      <section className="max-w-[1200px] mx-auto px-6 pt-20 pb-24">
        <div className="grid lg:grid-cols-2 gap-16 items-center">
          <div>
            <span className="inline-flex items-center gap-2 text-brass font-display text-sm rise">
              <span className="h-1.5 w-1.5 rounded-full bg-ember" /> Collaborative tax intelligence
            </span>
            <h1 className="display-xl text-graphite mt-6 rise d1">
              File taxes with a CA, without the <span className="link-ember">friction</span>.
            </h1>
            <p className="text-steel text-lg mt-6 max-w-lg leading-relaxed rise d2">
              Green Papaya turns Form 16s, broker reports and bank statements into evidence-linked candidate facts, deterministic computations and a structured CA review workflow.
            </p>
            <div className="flex flex-wrap items-center gap-3 mt-9 rise d3">
              <button onClick={login} data-testid="hero-get-started"
                className="font-display text-[15px] bg-graphite text-white px-6 py-3 rounded-none hover:bg-ember transition-colors flex items-center gap-2">
                Get started free <ArrowRight className="h-4 w-4" />
              </button>
              <a href="#product" className="font-display text-[15px] border border-graphite text-graphite px-6 py-3 rounded-none hover:bg-ash transition-colors">
                See how it works
              </a>
            </div>
            <div className="flex items-center gap-6 mt-10 text-slate-ink text-sm rise d4">
              <span className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-brass" /> Privacy-by-design controls</span>
              <span className="flex items-center gap-2"><Lock className="h-4 w-4 text-brass" /> AES-256-GCM</span>
            </div>
          </div>
          <HeroCards />
        </div>
      </section>

      {/* Partner strip */}
      <section className="border-y border-mist bg-fog">
        <div className="max-w-[1200px] mx-auto px-6 py-8">
          <p className="text-center font-display text-[13px] text-brass mb-4">Built around evidence, deterministic calculations and CA approval</p>
          <div className="flex flex-wrap items-center justify-center gap-x-12 gap-y-3 text-graphite/70 font-display text-sm">
            <span>PyMuPDF</span><span>Gemini Vision</span><span>AIS / TIS / 26AS</span>
            <span>ITR-1 · selected ITR-2</span><span>Section 115BAC</span><span>ICAI Audit Trails</span>
          </div>
        </div>
      </section>

      {/* Product features */}
      <section id="product" className="max-w-[1200px] mx-auto px-6 py-24">
        <div className="max-w-2xl">
          <p className="text-brass font-display text-sm">The workspace</p>
          <h2 className="heading-lg text-graphite mt-3">Everything from ingest to filing, in one auditable flow.</h2>
        </div>
        <div className="grid md:grid-cols-3 gap-5 mt-12">
          <Feature icon={ScanLine} title="Multimodal extraction" desc="Multi-page Form 16 Part A/B, capital-gains logs and scanned PDFs parsed with Gemini vision + PyMuPDF." />
          <Feature icon={GitCompareArrows} title="Old vs New sandbox" desc="Interactive slab-by-slab comparison for AY 2026-27 with exact rebate & marginal-relief logic." />
          <Feature icon={FileText} title="AIS auto-reconciler" desc="Parsed ledgers matched against AIS/TIS/26AS pre-fill to flag mismatches before a 143(1) notice." />
          <Feature icon={ShieldCheck} title="Immutable audit logs" desc="Every CA override captured with a mandatory justification for ICAI peer-review defensibility." />
          <Feature icon={FileJson} title="Versioned export pipeline" desc="Internal audit packages today; official form-specific exports remain gated by schema validation and CA approval." />
          <Feature icon={MessageCircle} title="WhatsApp ingest" desc="A consent-driven WhatsApp intake lane for mobile-first taxpayers (Twilio-ready webhook)." />
        </div>
      </section>

      {/* Sandbox teaser */}
      <section id="pipeline" className="bg-ash">
        <div className="max-w-[1200px] mx-auto px-6 py-24 grid lg:grid-cols-2 gap-16 items-center">
          <div className="bg-white rounded-2xl border border-mist p-8">
            <div className="flex items-center justify-between mb-2">
              <span className="font-display text-graphite">Instant regime estimate</span>
              <span className="text-xs text-brass font-display">FY 2025-26</span>
            </div>
            <p className="text-sm text-steel mb-6">Drag to see your New-regime liability move in real time.</p>
            <div className="flex items-baseline justify-between">
              <span className="text-sm text-slate-ink">Annual income</span>
              <span className="font-display text-2xl text-graphite">{inr(income)}</span>
            </div>
            <input type="range" min="300000" max="5000000" step="50000" value={income}
              onChange={(e) => setIncome(Number(e.target.value))}
              data-testid="landing-income-slider"
              className="w-full mt-3 accent-ember" />
            <div className="mt-6 bg-ivory rounded-lg p-5 flex items-center justify-between">
              <div>
                <div className="text-xs text-steel font-display">Estimated tax (New regime)</div>
                <div className="font-display text-3xl text-graphite mt-1" data-testid="landing-quick-tax">{inr(quickTax)}</div>
              </div>
              <TrendingDown className="h-8 w-8 text-ember" strokeWidth={1.5} />
            </div>
          </div>
          <div>
            <p className="text-brass font-display text-sm">Hybrid AI core</p>
            <h2 className="heading-lg text-graphite mt-3">Open-source vision parsing. Deterministic math.</h2>
            <p className="text-steel mt-5 leading-relaxed">
              Unstructured files pass through a vision + OCR parser into normalized JSON facts. Those facts
              flow through a symbolic rules engine — progressive slabs, HRA, 80C caps, capital gains — so there
              are zero probabilistic math errors in the numbers that matter.
            </p>
            <ul className="mt-6 space-y-3">
              {["Slabs & rates u/s 115BAC", "Deductions & exemptions (80C, 80D, HRA)", "Capital gains post-Budget 2024 (STCG 20%, LTCG 12.5%)"].map((t) => (
                <li key={t} className="flex items-center gap-3 text-graphite"><CheckCircle2 className="h-4 w-4 text-ember" /> {t}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* CA CTA */}
      <section id="ca" className="max-w-[1200px] mx-auto px-6 py-24">
        <div className="bg-graphite card-asym p-14 text-white grain relative overflow-hidden">
          <div className="max-w-xl relative">
            <p className="text-ember font-display text-sm">For Chartered Accountants</p>
            <h2 className="heading-lg mt-3">A control console built for firm-scale review.</h2>
            <p className="text-white/70 mt-5 leading-relaxed">
              Triage every client file, open a split-pane validation desk with the source document beside
              review candidate facts beside source evidence, resolve AIS mismatches and lock reproducible computation snapshots — all logged.
            </p>
            <button onClick={login} data-testid="ca-cta-btn"
              className="mt-8 font-display text-[15px] bg-white text-graphite px-6 py-3 rounded-none hover:bg-ember hover:text-white transition-colors flex items-center gap-2">
              Open the CA console <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </section>

      {/* Compliance */}
      <section id="compliance" className="bg-fog border-t border-mist">
        <div className="max-w-[1200px] mx-auto px-6 py-20 grid md:grid-cols-4 gap-8">
          {[["Section 5", "Lawful, unbundled consent"], ["Section 6", "Strict purpose limitation"], ["At rest", "AES-256-GCM encryption"], ["Auto-purge", "Erasure after e-verify window"]].map(([k, v]) => (
            <div key={k}>
              <div className="font-display text-brass text-sm">{k}</div>
              <div className="font-display text-lg text-graphite mt-1">{v}</div>
            </div>
          ))}
        </div>
      </section>

      <footer className="max-w-[1200px] mx-auto px-6 py-12 flex flex-col md:flex-row items-center justify-between gap-4 border-t border-mist">
        <Logo />
        <p className="text-slate-ink text-sm max-w-md text-center md:text-right">
          Not accounting, financial or legal advice. Verify all computations with a qualified CA before filing.
        </p>
      </footer>
    </div>
  );
}
