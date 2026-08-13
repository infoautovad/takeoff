# AutoVAD Frontend Code Dump

Generated for chat export. API routes under `app/api` are backend and are not included.

---

## `app\layout.tsx`

```tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://autovad-civil-ai.nellorevishnu.chatgpt.site"),
  title: "AutoVAD â€” More Bids. Less Counting.",
  description: "AI quantity intelligence for civil construction. Turn PDF and CAD plan sets into traceable, bid-ready quantities mapped to your bid-item template.",
  icons: { icon: "/favicon.svg", shortcut: "/favicon.svg" },
  openGraph: { title: "AutoVAD â€” More Bids. Less Counting.", description: "AI quantity intelligence for civil construction.", images: [{ url: "/og-v2.png", width: 1536, height: 1024, alt: "AutoVAD AI civil quantity takeoff platform" }] },
  twitter: { card: "summary_large_image", title: "AutoVAD â€” More Bids. Less Counting.", description: "AI quantity intelligence for civil construction.", images: ["/og-v2.png"] },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}

```

---

## `app\page.tsx`

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { prepareTakeoffSource } from "../lib/cadTakeoff";

type ResultItem = { csiCode: string; description: string; quantity: number; unit: string; sheet: string; sourceNote: string; confidence: number; reviewRequired: boolean };
type TakeoffResult = { id: string; projectName: string; sheetCount: number; summary: string; items: ResultItem[] };
type Account = { signedIn: boolean; entitled: boolean; status: string; plan?: string | null; credits?: number; creditsIncluded?: number; creditsExpireAt?: string | null; email?: string; displayName?: string };
type SavedProject = { id: string; filename: string; projectName: string | null; status: string; sheetCount: number | null; createdAt: string; completedAt: string | null };

const rows = [
  { item: "31 23 16", desc: "Unclassified excavation", qty: "8,420", unit: "CY", conf: "99.2%" },
  { item: "32 12 16", desc: "HMA pavement, 3 inch", qty: "14,860", unit: "SY", conf: "97.8%" },
  { item: "33 41 00", desc: "18\" RCP storm drain", qty: "1,245", unit: "LF", conf: "96.4%" },
];

export default function Home() {
  const inputRef = useRef<HTMLInputElement>(null);
  const templateRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [designContext, setDesignContext] = useState("");
  const [readingDesign, setReadingDesign] = useState(false);
  const [templateFile, setTemplateFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [result, setResult] = useState<TakeoffResult | null>(null);
  const [error, setError] = useState("");
  const [account, setAccount] = useState<Account | null>(null);
  const [checkoutLoading, setCheckoutLoading] = useState(false);
  const [extraCredits, setExtraCredits] = useState("50");
  const [savedProjects, setSavedProjects] = useState<SavedProject[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [contact, setContact] = useState({ name: "", email: "", company: "", message: "" });
  const [contactStatus, setContactStatus] = useState("");
  const creditPercent = account?.creditsIncluded ? Math.min(100, Math.max(0, Math.round(((account.credits ?? 0) / account.creditsIncluded) * 100))) : 0;

  useEffect(() => { fetch("/api/account").then((response) => response.json()).then((value) => setAccount(value as Account)).catch(() => setAccount({ signedIn: false, entitled: false, status: "inactive" })); }, []);
  useEffect(() => {
    if (!account?.signedIn || !["business", "enterprise"].includes(account.plan || "")) return;
    setProjectsLoading(true);
    fetch("/api/takeoffs").then(async (response) => { const payload = await response.json() as { projects?: SavedProject[]; error?: string }; if (!response.ok) throw new Error(payload.error || "Projects could not be loaded."); setSavedProjects(payload.projects || []); }).catch((err) => setError(err instanceof Error ? err.message : "Projects could not be loaded.")).finally(() => setProjectsLoading(false));
  }, [account]);

  const subscribe = async (plan: "starter" | "professional" | "business" = "professional") => {
    if (!account?.signedIn) { window.location.href = "/signin-with-chatgpt?return_to=%2F%23pricing"; return; }
    setCheckoutLoading(true); setError("");
    try { const response = await fetch("/api/billing/checkout", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ plan }) }); const payload = await response.json() as { url?: string; error?: string }; if (!response.ok || !payload.url) throw new Error(payload.error || "Checkout could not start."); window.location.href = payload.url; }
    catch (err) { setError(err instanceof Error ? err.message : "Checkout could not start."); setCheckoutLoading(false); }
  };

  const buyCredits = async () => {
    if (!account?.signedIn) { window.location.href = "/signin-with-chatgpt?return_to=%2F%23pricing"; return; }
    const credits = Math.floor(Number(extraCredits));
    if (!Number.isFinite(credits) || credits < 50) { setError("Enter at least 50 credits."); return; }
    setExtraCredits(String(credits)); setCheckoutLoading(true); setError("");
    try { const response = await fetch("/api/billing/checkout", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ credits }) }); const payload = await response.json() as { url?: string; error?: string }; if (!response.ok || !payload.url) throw new Error(payload.error || "Credit checkout could not start."); window.location.href = payload.url; }
    catch (err) { setError(err instanceof Error ? err.message : "Credit checkout could not start."); setCheckoutLoading(false); }
  };

  const acceptFile = async (file?: File) => {
    if (file && /\.(pdf|dwg|dxf|xml|landxml)$/i.test(file.name)) {
      if (account?.plan === "starter" && !/\.pdf$/i.test(file.name)) { setError("Starter supports PDF plan sets only. Upgrade to Professional or higher for DWG, DXF, XML, and LandXML files."); setSelectedFile(null); setFileName(""); return; }
      setFileName(file.name);
      setSelectedFile(file);
      setResult(null);
      setError("");
      setDesignContext("");
      if (!/\.pdf$/i.test(file.name)) {
        setReadingDesign(true);
        try { setDesignContext(await prepareTakeoffSource(file)); }
        catch (err) { setSelectedFile(null); setFileName(""); setError(err instanceof Error ? err.message : "The civil design could not be decoded."); }
        finally { setReadingDesign(false); }
      }
    }
  };

  const analyze = async () => {
    if (!selectedFile || processing) return;
    if (!account?.signedIn) { window.location.href = "/signin-with-chatgpt?return_to=%2F"; return; }
    if (!account.entitled) { document.querySelector("#pricing")?.scrollIntoView({ behavior: "smooth" }); setError("Choose a subscription before running a takeoff."); return; }
    setProcessing(true); setError(""); setResult(null);
    try {
      const form = new FormData();
      if (designContext) { form.append("designContext", designContext); form.append("sourceName", selectedFile.name); form.append("sourceSize", String(selectedFile.size)); }
      else form.append("file", selectedFile);
      if (templateFile) form.append("template", templateFile);
      const response = await fetch("/api/takeoffs", { method: "POST", body: form });
      const responseText = await response.text();
      let payload: TakeoffResult & { error?: string };
      try { payload = JSON.parse(responseText) as TakeoffResult & { error?: string }; }
      catch { throw new Error(response.ok ? "The server returned an unreadable response." : responseText.slice(0, 240) || `Upload failed (${response.status}).`); }
      if (!response.ok) throw new Error(payload.error || "Plan analysis failed.");
      setResult(payload);
    } catch (err) { setError(err instanceof Error ? err.message : "Plan analysis failed."); }
    finally { setProcessing(false); }
  };

  return (
    <main className="app-shell">
      <nav className="topbar" aria-label="Primary navigation">
        <a className="brand" href="#top" aria-label="AutoVAD home">
          <span className="brand-mark"><i /><i /><i /></span>
          <span>AUTO<span>VAD</span></span>
        </a>
        <div className="nav-links">
          <a href="#platform">Platform</a>
          <a href="#workflow">How it works</a>
          <a href="#industries">Who itâ€™s for</a>
          <a href="#pricing">Pricing</a>
          <a href="#about">Why AutoVAD</a>
          <a href="#contact">Contact</a>
        </div>
        <div className="nav-actions">
          {account?.signedIn ? <a className="account-summary" href="/signout-with-chatgpt?return_to=%2F" title="Sign out"><span className="account-avatar">{(account.displayName || account.email || "U").trim().charAt(0).toUpperCase()}</span><span className="account-identity"><small>SIGNED IN AS</small><b>{account.displayName || account.email}</b></span><span className="credit-summary"><small>CREDITS AVAILABLE</small><b>{account.credits ?? 0} <i>Â· {creditPercent}% remaining</i></b><span className="credit-meter"><i style={{ width: `${creditPercent}%` }} /></span></span></a> : <a className="text-button account-link" href="/signin-with-chatgpt?return_to=%2F">Sign in</a>}
        </div>
      </nav>
      {account?.signedIn && <div className="account-ribbon" aria-label="Account workspace navigation"><span><b>{(account.plan || "account").toUpperCase()}</b> WORKSPACE</span><a href="#top">New takeoff</a>{["business", "enterprise"].includes(account.plan || "") && <a href="#projects">Project Management</a>}<a href="#pricing">Plan & credits</a><i>{account.credits ?? 0} credits available</i></div>}

      <section className="hero" id="top">
        <div className="grid-lines" aria-hidden="true" />
        <div className="hero-copy">
          <div className="eyebrow"><span className="pulse" /> CIVIL TAKEOFF INTELLIGENCE Â· BUILT FOR BID DAY</div>
          <h1>More bids.<br /><em>Less counting.</em></h1>
          <p className="lede">AutoVAD turns civil plan sets and CAD designs into traceable, bid-ready quantitiesâ€”mapped to your own bid-item template and ready for professional review.</p>
          <div className="hero-actions"><button className="solid-button" onClick={() => inputRef.current?.click()}>Run your first takeoff <span>â†—</span></button><a href="#workflow">See how it works <span>â†“</span></a></div>
          <div className="capability-chips"><span>PDF + CAD</span><span>SOURCE-LINKED</span><span>YOUR BID ITEMS</span><span>REVIEW-READY</span></div>

          <div
            className={`dropzone ${dragging ? "dragging" : ""} ${fileName ? "has-file" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); void acceptFile(e.dataTransfer.files[0]); }}
          >
            <input ref={inputRef} type="file" accept={account?.plan === "starter" ? ".pdf,application/pdf" : ".pdf,.dwg,.dxf,.xml,.landxml,application/pdf"} onChange={(e) => void acceptFile(e.target.files?.[0])} />
            <div className="upload-icon"><span>â†‘</span></div>
            <div>
              <strong>{fileName || "Drop your plan set here"}</strong>
              <small>{readingDesign ? "DECODING CIVIL DESIGN GEOMETRYâ€¦" : fileName ? (designContext ? "CAD geometry ready for quantity extraction" : "Ready for AI sheet analysis") : "PDF Â· DWG Â· DXF Â· LANDXML Â· up to 50 MB"}</small>
              {fileName && <button className="change-source" type="button" onClick={(event) => { event.stopPropagation(); if (inputRef.current) { inputRef.current.value = ""; inputRef.current.click(); } }}>Change or reupload file</button>}
            </div>
            <button disabled={processing || readingDesign} onClick={(e) => { e.stopPropagation(); fileName ? analyze() : inputRef.current?.click(); }}>{readingDesign ? "Readingâ€¦" : processing ? "Analyzingâ€¦" : fileName ? "Extract quantities" : "Browse files"}</button>
          </div>
          <div className={`template-upload ${templateFile ? "has-template" : ""}`}>
            <input ref={templateRef} type="file" accept=".pdf,.xlsx,.xls,.csv,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv" onChange={(e) => setTemplateFile(e.target.files?.[0] ?? null)} />
            <div><small>OPTIONAL Â· BID ITEM TEMPLATE</small><strong>{templateFile?.name ?? "Match Takeoff quantity bid items to your own entity template"}</strong><span>{templateFile ? "AI will preserve its item numbers, descriptions, and units." : "Upload PDF, Excel, or CSV before analyzing the plans."}</span></div>
            {templateFile ? <button onClick={() => { setTemplateFile(null); if (templateRef.current) templateRef.current.value = ""; }}>Remove</button> : <button onClick={() => templateRef.current?.click()}>Upload template</button>}
          </div>
          {account && !account.entitled && <div className="access-lock"><span>LOCKED</span><div><strong>{account.signedIn ? (account.status === "active" ? "No AI credits remaining" : "Subscription required") : "Sign in required"}</strong><small>{account.signedIn ? "Choose a plan or add credits to analyze files and generate quantities." : "Create your account or sign in before using AutoVAD Takeoff."}</small></div><button onClick={() => account.signedIn ? document.querySelector("#pricing")?.scrollIntoView({ behavior: "smooth" }) : window.location.href = "/signin-with-chatgpt?return_to=%2F"}>{account.signedIn ? "View pricing" : "Sign in / Sign up"}</button></div>}
          {processing && <div className="processing-banner"><span className="processing-spinner" /><div><strong>Reading every sheet in {fileName}</strong><small>Identifying scope, normalizing units, and building your source-linked bid tab. Large plan sets can take several minutes.</small></div></div>}
          {error && <div className="error-banner"><strong>Analysis couldnâ€™t start</strong><span>{error}</span><button onClick={() => inputRef.current?.click()}>Choose another PDF</button></div>}
          {result && <div className="result-panel">
            <div className="result-title"><div><small>TAKEOFF COMPLETE Â· {result.sheetCount} SHEETS</small><h3>{result.projectName}</h3><p>{result.summary}</p></div><div><strong>{result.items.length}</strong><span>bid items</span></div></div>
            {templateFile && <div className="template-applied"><span>âœ“</span> Matched to {templateFile.name}</div>}
            <div className="result-table"><div className="result-row result-head"><span>{templateFile ? "BID ITEM" : "CSI"}</span><span>DESCRIPTION / SOURCE</span><span>QTY</span><span>SHEET</span><span>CONF.</span></div>
              {result.items.slice(0, 12).map((item, index) => <div className="result-row" key={`${item.description}-${index}`}><span>{item.csiCode || "â€”"}</span><span><b>{item.description}</b><small>{item.sourceNote}</small></span><span>{item.quantity.toLocaleString()} {item.unit}</span><span>{item.sheet || "â€”"}</span><span className={item.reviewRequired ? "review" : "confident"}>{Math.round(item.confidence * 100)}%{item.reviewRequired ? " Â· REVIEW" : ""}</span></div>)}
            </div>
            {result.items.length > 12 && <div className="more-items">+ {result.items.length - 12} additional items saved in this takeoff</div>}
          </div>}
          <div className="trust-line"><span>â—‡ SECURE PROJECT STORAGE</span><span>â—‡ HUMAN REVIEW BUILT IN</span><span>â—‡ CIVIL-SPECIFIC WORKFLOW</span></div>
        </div>

        <div className="product-stage" aria-label="AutoVAD plan analysis preview">
          <div className="stage-orbit orbit-one" /><div className="stage-orbit orbit-two" />
          <div className="sheet-stack sheet-back" />
          <div className="sheet-stack sheet-mid" />
          <div className="plan-sheet">
            <div className="sheet-head"><span>AUTOVAD / SHEET ANALYSIS</span><b>C-401</b></div>
            <div className="plan-drawing">
              <div className="road road-a" /><div className="road road-b" />
              <div className="contour c1" /><div className="contour c2" /><div className="contour c3" />
              <div className="scan-line" />
              <div className="measure m1"><span>18\" RCP</span></div>
              <div className="measure m2"><span>1,245 LF</span></div>
              <div className="node n1" /><div className="node n2" /><div className="node n3" />
            </div>
            <div className="sheet-foot"><span>SITE UTILITY PLAN</span><span>SCALE 1\" = 30'</span></div>
          </div>
          <div className="analysis-card">
            <div className="card-label">LIVE EXTRACTION</div>
            <div className="metric"><strong>247</strong><span>QUANTITIES<br />IDENTIFIED</span></div>
            <div className="progress"><i /></div>
            <div className="card-foot"><span>CONFIDENCE</span><b>98.6%</b></div>
          </div>
          <div className="tag tag-one"><i /> PIPE NETWORK</div>
          <div className="tag tag-two"><i /> EARTHWORK</div>
        </div>
      </section>

      <section className="market-platform" id="platform">
        <div className="market-intro"><div className="section-kicker">THE AUTOVAD ADVANTAGE</div><h2>Takeoff speed without<br /><span>black-box quantities.</span></h2><p>Generic AI can summarize a drawing. AutoVAD is being built for the civil bid workflow: read the plans, preserve the evidence, map the scope to the right bid items, and keep an estimator in control.</p></div>
        <div className="value-grid">
          <article><span>01</span><div className="value-glyph">âŒ</div><h3>Read civil scope</h3><p>Identify roadway, drainage, utilities, earthwork, paving, concrete, striping, erosion control, and site improvements.</p></article>
          <article><span>02</span><div className="value-glyph">â—Ž</div><h3>Trace every quantity</h3><p>Keep sheet, layer, source note, confidence, and review status attached to the number your team prices.</p></article>
          <article><span>03</span><div className="value-glyph">â‡„</div><h3>Match your bid schedule</h3><p>Upload an entity template and preserve its official item numbers, descriptions, and units in the final takeoff.</p></article>
          <article><span>04</span><div className="value-glyph">âœ“</div><h3>Review before export</h3><p>Surface uncertainty instead of hiding it, giving estimators a focused checklist before quantities reach the bid.</p></article>
        </div>
      </section>

      <section className="market-outcomes">
        <div><span>BUILT TO REDUCE</span><strong>Manual sheet-by-sheet counting</strong></div>
        <div><span>BUILT TO IMPROVE</span><strong>Scope coverage and auditability</strong></div>
        <div><span>BUILT TO ACCELERATE</span><strong>Estimator review and bid readiness</strong></div>
      </section>

      <section className="workflow" id="workflow">
        <div className="section-kicker">01 / WORKFLOW</div>
        <div className="section-heading"><h2>One plan set.<br /><span>Every quantity accounted for.</span></h2><p>AutoVAD gives estimators a fast first pass without losing the audit trail. Every measurement stays connected to its sheet and source markup.</p></div>
        <div className="steps">
          <article><span className="step-num">01</span><div className="step-icon">â–±</div><h3>Upload plans</h3><p>Drop in a complete civil PDF set. AutoVAD indexes sheets, legends, details, and specifications.</p><i className="connector" /></article>
          <article><span className="step-num">02</span><div className="step-icon">âŒ</div><h3>AI reads sheets</h3><p>Computer vision traces linear, area, volume, and count items across every discipline.</p><i className="connector" /></article>
          <article><span className="step-num">03</span><div className="step-icon">â–¦</div><h3>Review bid tab</h3><p>Validate source-linked quantities, flag exclusions, and export a clean checklist for pricing.</p></article>
        </div>
      </section>

      <section className="industries" id="industries">
        <div className="industries-copy"><div className="section-kicker">WHO AUTOVAD IS FOR</div><h2>One quantity engine.<br />Built around civil teams.</h2><p>Whether you price the work, design it, or procure it, AutoVAD gives your team a common, traceable starting point.</p><a href="#pricing">Compare plans <span>â†—</span></a></div>
        <div className="industry-list">
          <article><span>01</span><h3>Heavy civil contractors</h3><p>Move faster from issued plans to a review-ready bid tab while keeping source evidence close.</p><b>ROADWAY Â· UTILITIES Â· SITEWORK</b></article>
          <article><span>02</span><h3>Civil engineering firms</h3><p>Build consistent opinion-of-cost quantities from plan sets and CAD deliverables across project teams.</p><b>DESIGN REVIEW Â· QA/QC Â· ESTIMATES</b></article>
          <article><span>03</span><h3>Municipalities and owners</h3><p>Compare scope against official bid-item schedules and create a clearer record for procurement review.</p><b>CAPITAL PROGRAMS Â· BID TABS Â· AUDIT</b></article>
        </div>
      </section>

      <section className="about" id="about">
        <div className="about-lead"><div className="section-kicker">ABOUT AUTOVAD</div><h2>Built around the way<br />civil estimators work.</h2><p>AutoVAD turns dense civil plan sets and CAD designs into a faster, more traceable first-pass takeoff. We are building practical quantity intelligence for contractors, consultants, municipalities, and infrastructure teamsâ€”without separating the result from its source.</p></div>
        <div className="about-values">
          <article><span>01</span><h3>Evidence before automation</h3><p>Every quantity carries a sheet, layer, entity, or source note so estimators can review where it came from.</p></article>
          <article><span>02</span><h3>Your bid items, preserved</h3><p>Upload your entity template and AutoVAD matches quantities to its official item numbers, descriptions, and units.</p></article>
          <article><span>03</span><h3>Designed for civil scope</h3><p>Roadway, drainage, utilities, earthwork, paving, concrete, striping, erosion control, and site improvements.</p></article>
          <article><span>04</span><h3>Human review stays central</h3><p>Uncertain measurements and unmatched scope are clearly flagged instead of hidden behind false precision.</p></article>
        </div>
      </section>

      <section className="sales-proof">
        <div><span>SUPPORTED INPUTS</span><strong>PDF Â· DWG Â· DXF Â· LANDXML</strong><small>Plans, civil designs, and entity bid schedules in PDF, Excel, or CSV.</small></div>
        <div><span>BUILT FOR</span><strong>ESTIMATORS Â· ENGINEERS Â· OWNERS</strong><small>A repeatable first pass for bid preparation and scope review.</small></div>
        <div><span>OUTPUT</span><strong>TRACEABLE BID QUANTITIES</strong><small>Normalized units, confidence flags, source evidence, and review-ready tables.</small></div>
      </section>

      <section className="pricing" id="pricing">
        <div className="pricing-head"><div className="section-kicker">PRICING</div><h2>Start bidding with<br />a faster first pass.</h2><p>Create an account, activate your subscription, and use AutoVAD Takeoff across PDF and CAD plan sources.</p></div>
        <div className="price-grid">
          <article className="price-card"><span>STARTER</span><h3>Starter</h3><div className="plan-price"><b>$59</b><small>/ month</small></div><p>For individual estimators beginning with AI-assisted takeoffs.</p><ul><li>âœ“ 100 AI credits monthly</li><li>âœ“ PDF plan takeoffs only</li><li>âœ“ Bid-item template matching</li><li>â€” No credit rollover</li></ul><button disabled={checkoutLoading || account?.plan === "starter"} onClick={() => subscribe("starter")}>{account?.plan === "starter" ? "Current plan" : "Choose Starter"}</button></article>
          <article className="price-card featured"><div className="popular">RECOMMENDED</div><span>PROFESSIONAL</span><h3>Professional</h3><div className="plan-price"><b>$199</b><small>/ month</small></div><p>For civil estimators producing frequent review-ready quantity takeoffs.</p><ul><li>âœ“ 500 AI credits monthly</li><li>âœ“ PDF, DWG, DXF and LandXML</li><li>âœ“ Source notes and confidence flags</li><li>âœ“ 90-day credit rollover</li></ul><button disabled={checkoutLoading || account?.plan === "professional"} onClick={() => subscribe("professional")}>{account?.plan === "professional" ? "Current plan" : checkoutLoading ? "Opening checkoutâ€¦" : "Choose Professional"}</button></article>
          <article className="price-card"><span>BUSINESS</span><h3>Business</h3><div className="plan-price"><b>$499</b><small>/ month</small></div><p>For engineering firms and estimating teams with sustained project volume.</p><ul><li>âœ“ 2,000 AI credits monthly</li><li>âœ“ Entity bid-item templates</li><li>âœ“ Project Management workspace</li><li>âœ“ 90-day credit rollover</li></ul><button disabled={checkoutLoading || account?.plan === "business"} onClick={() => subscribe("business")}>{account?.plan === "business" ? "Current plan" : "Choose Business"}</button></article>
          <article className="price-card"><span>ENTERPRISE</span><h3>Enterprise</h3><div className="plan-price"><b>Custom</b></div><p>For organizations needing 10,000+ AI credits, onboarding, and procurement support.</p><ul><li>âœ“ 10,000+ AI credits</li><li>âœ“ Project Management workspace</li><li>âœ“ Multi-user deployment</li><li>âœ“ Volume and annual options</li></ul><a href="#contact">Contact sales</a></article>
        </div>
        <div className="credit-policy"><div className="credit-purchase"><span>BUY EXTRA CREDITS</span><b>${(Math.max(0, Number(extraCredits) || 0) * 0.30).toFixed(2)}</b><label>Credits<div className="credit-entry"><input type="text" inputMode="numeric" pattern="[0-9]*" autoComplete="off" aria-label="Number of extra credits" placeholder="Enter credits" value={extraCredits} onFocus={(event) => event.currentTarget.select()} onChange={(event) => setExtraCredits(event.target.value.replace(/[^0-9]/g, ""))} onBlur={() => { if (extraCredits && Number(extraCredits) < 50) setError("The minimum purchase is 50 credits."); }} /><button type="button" className="credit-clear" onClick={() => setExtraCredits("")}>Clear</button></div></label><small>Type any whole number Â· Minimum 50 Â· No maximum Â· $0.30 per credit</small><button disabled={checkoutLoading || !account?.entitled || !extraCredits || Number(extraCredits) < 50} onClick={buyCredits}>{account?.entitled ? checkoutLoading ? "Opening checkoutâ€¦" : extraCredits && Number(extraCredits) >= 50 ? `Buy ${Number(extraCredits).toLocaleString()} credits` : "Enter at least 50 credits" : "Active plan required"}</button></div><div><span>ROLLOVER</span><b>90 days</b><small>Available on Professional, Business, and Enterprise plans. Starter credits reset each billing period.</small></div><div><span>LAUNCH UNIT</span><b>1 takeoff = 1 credit</b><small>Future sheet, design, and project-chat operations will use the same transparent ledger.</small></div></div>
        <small className="pricing-note">AI-generated quantities require professional review. Usage and costs will be monitored during launch and plan allowances may evolve for future billing periods.</small>
      </section>

      {account?.signedIn && ["business", "enterprise"].includes(account.plan || "") && <section className="project-management" id="projects"><div className="project-management-head"><div><div className="section-kicker">PROJECT MANAGEMENT</div><h2>Your saved takeoff projects.</h2><p>Completed and in-progress takeoffs are saved automatically to your account so your team can return to them later.</p></div><button onClick={() => inputRef.current?.click()}>+ New project</button></div><div className="project-list">{projectsLoading ? <div className="project-empty">Loading saved projectsâ€¦</div> : savedProjects.length ? savedProjects.map((project) => <a className="saved-project" key={project.id} href={`/api/takeoffs/${project.id}`} target="_blank" rel="noreferrer"><span>{project.status.toUpperCase()}</span><strong>{project.projectName || project.filename}</strong><small>{project.filename} Â· {project.sheetCount ?? 0} sheets</small><time>{new Date(project.completedAt || project.createdAt).toLocaleDateString()}</time></a>) : <div className="project-empty"><strong>No saved projects yet.</strong><span>Run your first takeoff and it will appear here automatically.</span></div>}</div></section>}

      <section className="faq-section" id="faq"><div><div className="section-kicker">COMMON QUESTIONS</div><h2>Built for confidence<br />before the bid.</h2><p>AutoVAD accelerates the first pass. Your estimator remains the decision-maker and reviews every quantity before it is used.</p></div><div className="faq-list"><details open><summary>Does AutoVAD replace an estimator?<span>+</span></summary><p>No. It reduces repetitive plan reading and organizes traceable quantities so an estimator can focus on scope, risk, pricing, and review.</p></details><details><summary>Can it use our bid-item template?<span>+</span></summary><p>Yes. Upload a PDF, Excel, or CSV bid schedule and AutoVAD will match extracted scope to its item numbers, descriptions, and units.</p></details><details><summary>Which plan formats are supported?<span>+</span></summary><p>Starter supports PDF. Professional and higher plans support PDF, DWG, DXF, XML, and LandXML sources.</p></details><details><summary>What happens when AI is uncertain?<span>+</span></summary><p>Low-confidence or ambiguous quantities are flagged for review with their source note rather than presented as false certainty.</p></details></div></section>

      <section className="contact-section" id="contact">
        <div><div className="section-kicker">CONTACT US</div><h2>Talk with the<br />AutoVAD team.</h2><p>Questions about launch access, team subscriptions, supported plan formats, or an estimator workflow? Send us a note and the AutoVAD team will follow up using your work email.</p></div>
        <form onSubmit={async (event) => { event.preventDefault(); setContactStatus("Sendingâ€¦"); try { const response = await fetch("/api/contact", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(contact) }); const payload = await response.json() as { error?: string }; if (!response.ok) throw new Error(payload.error || "Message could not be sent."); setContactStatus("Thank you. Your message has been received."); setContact({ name: "", email: "", company: "", message: "" }); } catch (err) { setContactStatus(err instanceof Error ? err.message : "Message could not be sent."); } }}>
          <label>Name<input required value={contact.name} onChange={(event) => setContact({ ...contact, name: event.target.value })} /></label><label>Work email<input required type="email" value={contact.email} onChange={(event) => setContact({ ...contact, email: event.target.value })} /></label><label>Company<input value={contact.company} onChange={(event) => setContact({ ...contact, company: event.target.value })} /></label><label>How can we help?<textarea required rows={5} value={contact.message} onChange={(event) => setContact({ ...contact, message: event.target.value })} /></label><button type="submit">Send message â†—</button>{contactStatus && <small>{contactStatus}</small>}
        </form>
      </section>

      <section className="output" id="output">
        <div className="output-copy">
          <div className="section-kicker">02 / STRUCTURED OUTPUT</div>
          <h2>A bid tab that<br />explains itself.</h2>
          <p>Move from â€œwhere did this number come from?â€ to the exact sheet, detail, and measurementâ€”with one click.</p>
          <ul><li><span>âœ“</span> CSI-coded scope checklist</li><li><span>âœ“</span> Unit-normalized quantities</li><li><span>âœ“</span> Excel-ready bid tab export</li></ul>
          <button className="solid-button" onClick={() => inputRef.current?.click()}>Analyze your first plan set <span>â†—</span></button>
        </div>
        <div className="bid-window">
          <div className="window-bar"><div><i /><i /><i /></div><span>RIVERSIDE_CIVIL_TAKEOFF.AVD</span><b>EXPORT â†—</b></div>
          <div className="project-line"><div><small>PROJECT</small><strong>Riverside Logistics Center</strong></div><div><small>STATUS</small><strong className="ready">â— REVIEW READY</strong></div><div><small>SHEETS</small><strong>42 / 42</strong></div></div>
          <div className="table-head"><span>ITEM</span><span>DESCRIPTION</span><span>QTY</span><span>UNIT</span><span>AI CONF.</span></div>
          {rows.map((row) => <div className="table-row" key={row.item}><span>{row.item}</span><strong>{row.desc}</strong><span>{row.qty}</span><span>{row.unit}</span><span><i />{row.conf}</span></div>)}
          <div className="window-summary"><span>247 items extracted</span><span>12 items need review</span><b>OPEN CHECKLIST â†’</b></div>
        </div>
      </section>

      <section className="closing" id="security">
        <div><div className="eyebrow"><span className="pulse" /> YOUR NEXT BID STARTS HERE</div><h2>Count less.<br />Compete more.</h2><p>Bring your next civil plan set and turn it into a traceable first-pass takeoff.</p></div>
        <button className="solid-button light" onClick={() => inputRef.current?.click()}>Run your first takeoff <span>â†—</span></button>
      </section>
      <footer><a className="brand" href="#top"><span className="brand-mark"><i /><i /><i /></span><span>AUTO<span>VAD</span></span></a><p>More bids. Less counting. AI quantity intelligence for civil construction.</p><span>Â© 2026 AUTOVAD</span></footer>
    </main>
  );
}

```

---

## `app\design\page.tsx`

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";
import GeoMap from "./GeoMap";
import Map3D from "./Map3D";
import type { UtilityQueryResult } from "../../lib/gis";
import { createConceptArtifacts } from "../../lib/conceptDesign";
import type { DesignCommandIntent } from "../../lib/designCommands";
import { surveySummary, type SurveyDataset } from "../../lib/surveyXml";
import { alignDeclaredSurveyCrs, autoConvertDeclaredElevations, crossCheckSurveyLocation, parseSurveyFile } from "../../lib/surveyImport";

type Upload = { name: string; size: number; type: string; file: File };
type Message = { role: "ai" | "user"; text: string };
type CommandAnalysis = { intents: DesignCommandIntent[]; primaryIntent: DesignCommandIntent; confidence: number; detectedValues: string[]; missingInputs: string[] };
type AreaContext = { city: string; state: string; street: string; roadClass: string; highwayTag: string; routeRef: string; distanceMeters: number | null; roadBearing: number | null; roadGeometry: [number, number][] | null; existingRoad: { mappedWidth: string | null; lanes: string | null; sidewalk: string | null; curb: string | null; gutter: string | null; shoulder: string | null; surface: string | null; maxSpeed: string | null; rightOfWay: string | null }; source: string };
type StandardsContext = { status: string; summary: string; sources: Array<{ title: string; url: string }>; checkedAt?: string };
type TerrainSection = { source: string; resolutionMeters: number; horizontalDatum: string; verticalDatum: string; preliminaryOnly: boolean; minimumElevationFeet: number; maximumElevationFeet: number; warning: string; points: Array<{ lng: number; lat: number; offsetFeet: number; elevationFeet: number }> };
type RibbonTab = "HOME" | "SURFACES" | "ALIGNMENTS" | "PROFILES" | "CORRIDORS" | "GRADING" | "PARCELS" | "PIPE NETWORKS" | "ANNOTATE" | "ANALYZE" | "VIEW";
type RibbonTool = { id: string; label: string; glyph: string; action?: boolean };
const roadStages = ["Design basis", "Alignment", "Typical section", "Intersections", "Grading & drainage", "Review"];

const ribbonTools: Record<RibbonTab, RibbonTool[]> = {
  HOME: [{ id: "select", label: "Select", glyph: "â†–" }, { id: "pan", label: "Pan", glyph: "âœ¥" }, { id: "polyline", label: "Polyline", glyph: "â•±" }, { id: "point", label: "COGO Point", glyph: "âŠ™" }, { id: "text", label: "Label", glyph: "T" }, { id: "undo", label: "Undo", glyph: "â†¶", action: true }],
  SURFACES: [{ id: "surface", label: "Surface Boundary", glyph: "â–³" }, { id: "breakline", label: "Breakline", glyph: "âŒ‡" }, { id: "contour", label: "Contour", glyph: "â‰ˆ" }, { id: "point", label: "Surface Point", glyph: "âŠ™" }],
  ALIGNMENTS: [{ id: "alignment", label: "Create Alignment", glyph: "âŒ" }, { id: "offset", label: "Offset Alignment", glyph: "âˆ¥" }, { id: "widening", label: "Widening", glyph: "< >" }, { id: "station", label: "Station Label", glyph: "0+00" }],
  PROFILES: [{ id: "profile", label: "Layout Profile", glyph: "âŒ’" }, { id: "feature", label: "Profile Grade", glyph: "â•±" }, { id: "point", label: "PVI Point", glyph: "â—" }, { id: "text", label: "Profile Label", glyph: "EL" }],
  CORRIDORS: [{ id: "corridor", label: "Corridor Baseline", glyph: "â–°" }, { id: "feature", label: "Assembly Control", glyph: "âŠ¥" }, { id: "offset", label: "Corridor Offset", glyph: "âˆ¥" }],
  GRADING: [{ id: "feature", label: "Feature Line", glyph: "âŒ‡" }, { id: "grading", label: "Grading Limit", glyph: "â–½" }, { id: "daylight", label: "Daylight Line", glyph: "âŒ" }, { id: "point", label: "Spot Grade", glyph: "EL" }],
  PARCELS: [{ id: "parcel", label: "Parcel Boundary", glyph: "â–±" }, { id: "row", label: "Right of Way", glyph: "ROW" }, { id: "easement", label: "Easement", glyph: "E" }, { id: "text", label: "Parcel Label", glyph: "T" }],
  "PIPE NETWORKS": [{ id: "storm", label: "Storm Pipe", glyph: "S" }, { id: "sanitary", label: "Sanitary Sewer", glyph: "SS" }, { id: "water", label: "Water Main", glyph: "W" }, { id: "pressure", label: "Pressure Network", glyph: "P" }, { id: "point", label: "Structure", glyph: "â–¡" }],
  ANNOTATE: [{ id: "text", label: "General Note", glyph: "T" }, { id: "text", label: "Station Label", glyph: "0+00" }, { id: "point", label: "Spot Elevation", glyph: "EL" }, { id: "measure", label: "Dimension", glyph: "â†”" }],
  ANALYZE: [{ id: "measure", label: "Measure", glyph: "â†”" }, { id: "point", label: "Inspect Point", glyph: "â—Ž" }, { id: "finish", label: "Finish", glyph: "âœ“", action: true }, { id: "undo", label: "Undo", glyph: "â†¶", action: true }],
  VIEW: [{ id: "pan", label: "Navigate", glyph: "âœ¥" }, { id: "select", label: "Select", glyph: "â†–" }, { id: "erase", label: "Erase", glyph: "âŒ«" }, { id: "clear", label: "Clear Manual", glyph: "Ã—", action: true }],
};

const starters = ["Design a road through the selected area", "Lay out storm and sanitary sewers", "Design a looped water system", "Create a detention and drainage concept"];

function DesignStudioWorkspace() {
  const inputRef = useRef<HTMLInputElement>(null);
  const copilotRef = useRef<HTMLElement>(null);
  const copilotChannelRef = useRef<BroadcastChannel | null>(null);
  const copilotWindowRef = useRef<Window | null>(null);
  const copilotDragRef = useRef<{ pointerX: number; pointerY: number; panelX: number; panelY: number } | null>(null);
  const sectionResizeRef = useRef<{ element: HTMLElement; pointerY: number; height: number } | null>(null);
  const dockResizeRef = useRef<{ pointerX: number; width: number } | null>(null);
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [prompt, setPrompt] = useState("");
  const [messages, setMessages] = useState<Message[]>([
    { role: "ai", text: "Tell me what youâ€™re designing, then add the survey, jurisdiction criteria, and owner requirements. Iâ€™ll organize the design basis before geometry begins." },
  ]);
  const [showPlans, setShowPlans] = useState(false);
  const [canvasMode, setCanvasMode] = useState<"plan" | "map" | "3d">("map");
  const [modelLayer, setModelLayer] = useState<"surface" | "utilities" | "corridor">("surface");
  const [mapBackground, setMapBackground] = useState(true);
  const [siteLocation, setSiteLocation] = useState<{ lat: number; lng: number } | null>(null);
  const [projectId, setProjectId] = useState("");
  const [thinking, setThinking] = useState(false);
  const [readiness, setReadiness] = useState(12);
  const [lastCommand, setLastCommand] = useState<CommandAnalysis | null>(null);
  const [roadConceptRevision, setRoadConceptRevision] = useState(0);
  const [areaContext, setAreaContext] = useState<AreaContext | null>(null);
  const [contextLoading, setContextLoading] = useState(false);
  const [roadStage, setRoadStage] = useState<number | null>(null);
  const [aiPowered, setAiPowered] = useState(true);
  const [standards, setStandards] = useState<StandardsContext | null>(null);
  const [standardsLoading, setStandardsLoading] = useState(false);
  const [terrainSection, setTerrainSection] = useState<TerrainSection | null>(null);
  const [ribbonTab, setRibbonTab] = useState<RibbonTab>("HOME");
  const [manualTool, setManualTool] = useState("select");
  const [snapOn, setSnapOn] = useState(true);
  const [manualRibbonOpen, setManualRibbonOpen] = useState(false);
  const [copilotPosition, setCopilotPosition] = useState<{ x: number; y: number } | null>(null);
  const [popoutMode] = useState(() => typeof window !== "undefined" && new URLSearchParams(window.location.search).get("copilot") === "popout");
  const [copilotDetached, setCopilotDetached] = useState(false);
  const [copilotView, setCopilotView] = useState<"open" | "collapsed" | "closed">("open");
  const [copilotWidth, setCopilotWidth] = useState(390);

  useEffect(() => {
    const timer = window.setTimeout(() => window.dispatchEvent(new Event("resize")), 80);
    return () => window.clearTimeout(timer);
  }, [copilotWidth, copilotView, copilotDetached]);

  useEffect(() => {
    const move = (event: PointerEvent) => {
      const dock = dockResizeRef.current;
      if (dock) setCopilotWidth(Math.max(320, Math.min(720, dock.width + dock.pointerX - event.clientX)));
      const section = sectionResizeRef.current;
      if (section) section.element.style.height = `${Math.max(24, section.height + event.clientY - section.pointerY)}px`;
      const origin = copilotDragRef.current;
      const panel = copilotRef.current;
      const parent = panel?.parentElement;
      if (!origin || !panel || !parent) return;
      const x = origin.panelX + event.clientX - origin.pointerX;
      const y = origin.panelY + event.clientY - origin.pointerY;
      setCopilotPosition({
        x: Math.max(0, Math.min(x, parent.clientWidth - panel.offsetWidth)),
        y: Math.max(0, Math.min(y, parent.clientHeight - panel.offsetHeight)),
      });
    };
    const stop = () => {
      copilotDragRef.current = null;
      sectionResizeRef.current = null;
      dockResizeRef.current = null;
      document.body.style.removeProperty("user-select");
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    return () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", stop); };
  }, []);

  useEffect(() => {
    const channel = new BroadcastChannel("autovad-design-copilot");
    copilotChannelRef.current = channel;
    channel.onmessage = (event: MessageEvent) => {
      const data = event.data as { type?: string; location?: { lat: number; lng: number }; context?: AreaContext; standards?: StandardsContext | null; text?: string; payload?: { reply?: string; projectId?: string; readiness?: number; command?: CommandAnalysis; roadStage?: number | null; aiPowered?: boolean } };
      if (data.type === "context" && data.location && data.context) {
        setSiteLocation(data.location);
        setAreaContext(data.context);
        if (data.standards) setStandards(data.standards);
      }
      if (data.type === "popout-ready" && !popoutMode) setCopilotDetached(true);
      if (data.type === "popout-closed" && !popoutMode) setCopilotDetached(false);
      if (data.type === "design-update" && data.payload) {
        if (data.payload.projectId) setProjectId(data.payload.projectId);
        if (typeof data.payload.readiness === "number") setReadiness(data.payload.readiness);
        if (typeof data.payload.roadStage === "number") setRoadStage(data.payload.roadStage);
        if (typeof data.payload.aiPowered === "boolean") setAiPowered(data.payload.aiPowered);
        if (data.payload.command) setLastCommand(data.payload.command);
        if (data.text && data.payload.reply) setMessages((items) => [...items, { role: "user", text: data.text! }, { role: "ai", text: data.payload!.reply! }]);
        if (data.payload.command?.intents.includes("road-design")) { setRoadConceptRevision((revision) => revision + 1); setCanvasMode("plan"); }
      }
    };
    const stored = localStorage.getItem("autovad-design-context");
    if (stored) {
      try {
        const data = JSON.parse(stored) as { location: { lat: number; lng: number }; context: AreaContext; standards?: StandardsContext | null };
        setSiteLocation(data.location); setAreaContext(data.context); if (data.standards) setStandards(data.standards);
      } catch { /* Ignore stale local workspace context. */ }
    }
    const copilotState = localStorage.getItem("autovad-copilot-state");
    if (popoutMode && copilotState) {
      try {
        const state = JSON.parse(copilotState) as { messages?: Message[]; prompt?: string; projectId?: string; readiness?: number; lastCommand?: CommandAnalysis | null; roadStage?: number | null; aiPowered?: boolean };
        if (state.messages) setMessages(state.messages);
        if (state.prompt) setPrompt(state.prompt);
        if (state.projectId) setProjectId(state.projectId);
        if (typeof state.readiness === "number") setReadiness(state.readiness);
        if (state.lastCommand) setLastCommand(state.lastCommand);
        if (typeof state.roadStage === "number") setRoadStage(state.roadStage);
        if (typeof state.aiPowered === "boolean") setAiPowered(state.aiPowered);
      } catch { /* Ignore stale detached-panel state. */ }
    }
    if (popoutMode) channel.postMessage({ type: "popout-ready" });
    const closing = () => { if (popoutMode) channel.postMessage({ type: "popout-closed" }); };
    window.addEventListener("beforeunload", closing);
    return () => { closing(); window.removeEventListener("beforeunload", closing); channel.close(); copilotChannelRef.current = null; };
  }, [popoutMode]);

  useEffect(() => {
    if (popoutMode) return;
    localStorage.setItem("autovad-copilot-state", JSON.stringify({ messages, prompt, projectId, readiness, lastCommand, roadStage, aiPowered }));
  }, [popoutMode, messages, prompt, projectId, readiness, lastCommand, roadStage, aiPowered]);

  const startCopilotDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (popoutMode || window.innerWidth <= 800 || (event.target as HTMLElement).closest("button")) return;
    const panel = copilotRef.current;
    const parent = panel?.parentElement;
    if (!panel || !parent) return;
    event.preventDefault();
    const panelBox = panel.getBoundingClientRect();
    const parentBox = parent.getBoundingClientRect();
    const panelX = panelBox.left - parentBox.left;
    const panelY = panelBox.top - parentBox.top;
    setCopilotPosition({ x: panelX, y: panelY });
    copilotDragRef.current = { pointerX: event.clientX, pointerY: event.clientY, panelX, panelY };
    document.body.style.userSelect = "none";
  };

  const startSectionResize = (event: ReactPointerEvent<HTMLElement>) => {
    const target = (event.target as HTMLElement).closest<HTMLElement>(".design-progress,.command-analysis,.location-context,.road-context,.existing-road,.standards-context,.road-workflow,.chat-stream,.intake-checks");
    if (!target) return;
    const bounds = target.getBoundingClientRect();
    if (Math.abs(event.clientY - bounds.bottom) > 10) return;
    event.preventDefault();
    event.stopPropagation();
    sectionResizeRef.current = { element: target, pointerY: event.clientY, height: bounds.height };
    document.body.style.userSelect = "none";
  };

  const resetCopilot = () => {
    setCopilotPosition(null);
    copilotRef.current?.style.removeProperty("width");
    copilotRef.current?.style.removeProperty("height");
  };

  const openCopilotWindow = () => {
    localStorage.setItem("autovad-copilot-state", JSON.stringify({ messages, prompt, projectId, readiness, lastCommand, roadStage, aiPowered }));
    const popup = window.open("/design?copilot=popout", "autovad-design-copilot", "popup,width=470,height=900,resizable=yes,scrollbars=yes");
    if (!popup) return;
    copilotWindowRef.current = popup;
    setCopilotDetached(true);
    popup.focus();
    const watcher = window.setInterval(() => {
      if (copilotWindowRef.current?.closed) {
        window.clearInterval(watcher);
        copilotWindowRef.current = null;
        setCopilotDetached(false);
      }
    }, 500);
  };
  const startDockResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (popoutMode || copilotView !== "open") return;
    event.preventDefault(); event.stopPropagation(); dockResizeRef.current = { pointerX: event.clientX, width: copilotWidth }; document.body.style.userSelect = "none";
  };

  const addFiles = async (files: FileList | null) => {
    if (!files) return;
    const incoming = Array.from(files);
    setUploads((current) => [...current, ...incoming.map((file) => ({ name: file.name, size: file.size, type: file.name.split(".").pop()?.toUpperCase() || "FILE", file }))].slice(0, 12));
    for (const file of incoming) {
      if (!/\.(xml|landxml|xlsx|xls|csv|tsv|dwg)$/i.test(file.name)) continue;
      try {
        setMessages((items) => [...items, { role: "ai", text: `Reading ${file.name}, checking coordinate fields, and preparing its survey geometry...` }]);
        const parsed = await parseSurveyFile(file);
        const aligned = parsed ? await alignDeclaredSurveyCrs(parsed) : null;
        const checked = aligned ? crossCheckSurveyLocation(aligned, siteLocation) : null;
        const dataset = checked ? await autoConvertDeclaredElevations(checked) : null;
        if (!dataset) continue;
        sessionStorage.setItem("autovad-survey-data", JSON.stringify(dataset));
        sessionStorage.setItem("autovad-survey-visibility", JSON.stringify({ points: true, breaklines: true, contours: true }));
        window.dispatchEvent(new CustomEvent("autovad:survey-data", { detail: dataset }));
        setCanvasMode("map");
        const verification = dataset.importValidation;
        const detection = dataset.crsDetection;
        setMessages((items) => [...items, { role: "ai", text: `Survey converted, checked, and displayed. ${surveySummary(dataset)} CRS detection confidence: ${detection?.confidence || "low"}. ${detection?.evidence.join("; ") || "No embedded CRS metadata found"}. ${verification?.checks.join("; ")}. ${verification?.warnings.length ? `Review needed: ${verification.warnings.join("; ")}.` : "No duplicate-coordinate or missing-elevation warnings were found."} The source remains available when its visual layers are hidden. ${dataset.transformed ? "The declared CRS was automatically transformed and checked against the selected project location." : dataset.geographic ? "Geographic ranges were detected; confirm the declared CRS before final design." : "CRS confirmation is required before geospatial design."}` }]);
      } catch (error) { setMessages((items) => [...items, { role: "ai", text: error instanceof Error ? error.message : "I couldnâ€™t read that survey file." }]); }
    }
  };

  const applySurveyVisibilityCommand = (text: string) => {
    if (!/\b(survey|survey points?|breaklines?|contours?)\b/i.test(text) || !/\b(hide|show|turn off|turn on|disable|enable)\b/i.test(text)) return;
    let visibility = { points: true, breaklines: true, contours: true };
    try { visibility = { ...visibility, ...JSON.parse(sessionStorage.getItem("autovad-survey-visibility") || "{}") }; } catch { /* use defaults */ }
    const visible = /\b(show|turn on|enable)\b/i.test(text);
    if (/\b(all|full|entire)\b/i.test(text) || /\bsurvey\b/i.test(text) && !/\b(points?|breaklines?|contours?)\b/i.test(text)) visibility = { points: visible, breaklines: visible, contours: visible };
    else {
      if (/\bpoints?\b/i.test(text)) visibility.points = visible;
      if (/\bbreaklines?\b/i.test(text)) visibility.breaklines = visible;
      if (/\bcontours?\b/i.test(text)) visibility.contours = visible;
    }
    sessionStorage.setItem("autovad-survey-visibility", JSON.stringify(visibility));
    window.dispatchEvent(new CustomEvent("autovad:survey-visibility", { detail: visibility }));
  };

  const loadArcGISUtilities = async () => {
    try {
      const area = JSON.parse(localStorage.getItem("autovad-project-area") || "null");
      if (!area) {
        setMessages((items) => [...items, { role: "ai", text: "Select a project area first so I can query the connected ArcGIS utility services." }]);
        return;
      }
      const response = await fetch("/api/gis/utilities", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ area }) });
      const payload = await response.json() as UtilityQueryResult & { error?: string };
      if (!response.ok) throw new Error(payload.error || "ArcGIS utility query failed.");
      try { sessionStorage.setItem("autovad-utility-data", JSON.stringify(payload)); } catch { /* keep large agency responses in the active view */ }
      window.dispatchEvent(new CustomEvent("autovad:utility-data", { detail: payload }));
      setCanvasMode("plan");
      setMessages((items) => [...items, { role: "ai", text: `${payload.message}${payload.warnings.length ? ` ${payload.warnings.length} connected layer${payload.warnings.length === 1 ? "" : "s"} could not be read.` : ""} Utility locations are record data and must be field-verified before design or excavation.` }]);
    } catch (error) {
      setMessages((items) => [...items, { role: "ai", text: error instanceof Error ? error.message : "I couldnâ€™t query the ArcGIS utility services for this area." }]);
    }
  };

  const send = async () => {
    if (!prompt.trim() || thinking) return;
    const text = prompt.trim();
    applySurveyVisibilityCommand(text);
    setMessages((items) => [...items, { role: "user", text }]);
    setPrompt("");
    setThinking(true);
    try {
      const form = new FormData(); form.append("message", text); if (projectId) form.append("projectId", projectId); if (siteLocation) { form.append("latitude", String(siteLocation.lat)); form.append("longitude", String(siteLocation.lng)); } if (areaContext) { form.append("city", areaContext.city); form.append("street", areaContext.street); form.append("roadClass", areaContext.roadClass); form.append("highwayTag", areaContext.highwayTag); form.append("routeRef", areaContext.routeRef); form.append("existingRoad", JSON.stringify(areaContext.existingRoad)); } if (standards?.status === "verified-sources-found") form.append("standardsContext", standards.summary);
      let survey: SurveyDataset | null = null; try { survey = JSON.parse(sessionStorage.getItem("autovad-survey-data") || "null") as SurveyDataset | null; if (survey) form.append("surveyContext", surveySummary(survey)); } catch { /* no parsed survey */ }
      let publicTerrain: TerrainSection | null = null;
      const requestsTerrainSection = /\b(road|roadway|street)\b[\s\S]*\b(section|cross section|profile|grade)\b|\b(section|cross section|profile)\b[\s\S]*\b(road|roadway|street)\b/i.test(text);
      if (!survey && requestsTerrainSection) {
        try { const area = JSON.parse(localStorage.getItem("autovad-project-area") || "null"); if (area) { const terrainResponse = await fetch("/api/gis/terrain-section", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ bounds: area, roadBearing: areaContext?.roadBearing ?? null }) }); if (terrainResponse.ok) { publicTerrain = await terrainResponse.json() as TerrainSection; setTerrainSection(publicTerrain); form.append("terrainContext", `${publicTerrain.source}, ${publicTerrain.resolutionMeters} m DEM; elevation range ${publicTerrain.minimumElevationFeet.toFixed(1)}-${publicTerrain.maximumElevationFeet.toFixed(1)} ft; ${publicTerrain.verticalDatum}; preliminary only.`); } } } catch { /* Copilot will request a survey if public terrain is unavailable. */ }
      }
      uploads.forEach((upload) => form.append("files", upload.file));
      const response = await fetch("/api/design/intake", { method: "POST", body: form });
      const payload = await response.json() as { reply?: string; error?: string; projectId?: string; readiness?: number; command?: CommandAnalysis; roadStage?: number | null; aiPowered?: boolean };
      if (payload.projectId) setProjectId(payload.projectId);
      if (typeof payload.readiness === "number") setReadiness(payload.readiness);
      if (typeof payload.roadStage === "number") setRoadStage(payload.roadStage);
      if (typeof payload.aiPowered === "boolean") setAiPowered(payload.aiPowered);
      if (payload.command) {
        setLastCommand(payload.command);
        const visualIntents: DesignCommandIntent[] = ["road-design", "access", "grading", "stormwater", "sanitary-sewer", "water-system", "detention-pond", "drainage-analysis"];
        const requestsVisualization = /\b(design|draw|lay\s*out|create|generate|show|model|place|route|propose|develop|render|add)\b/i.test(text);
        if (requestsVisualization && payload.command.intents.some((intent) => visualIntents.includes(intent))) {
          try {
            const area = JSON.parse(localStorage.getItem("autovad-project-area") || "null");
            if (area) {
              const artifacts = createConceptArtifacts(payload.command.intents, area, areaContext?.roadGeometry || undefined);
              if (publicTerrain) artifacts.push({ id: `terrain-section-${Date.now()}`, discipline: "terrain", label: "USGS 3DEP preliminary road-section transect", color: "#ffcf65", generatedAt: new Date().toISOString(), data: { type: "FeatureCollection", features: [{ type: "Feature", geometry: { type: "LineString", coordinates: publicTerrain.points.map((point) => [point.lng, point.lat]) }, properties: { role: "terrain-section", source: publicTerrain.source, resolutionMeters: publicTerrain.resolutionMeters, preliminaryOnly: true } }] } });
              sessionStorage.setItem("autovad-concept-artifacts", JSON.stringify(artifacts));
              window.dispatchEvent(new CustomEvent("autovad:concept-artifacts", { detail: artifacts }));
              setCanvasMode("plan");
            }
          } catch { /* Copilot still answers when concept visualization cannot be generated. */ }
        }
        if (payload.command.intents.includes("road-design")) {
          setCanvasMode("plan");
        }
        const requestsUtilityRecords = /\b(show|find|display|load|map|locate)\b[\s\S]*\b(existing|underground|utility|utilities|water|sewer|gas|electric)\b/i.test(text);
        if (requestsUtilityRecords && payload.command.intents.includes("utilities")) await loadArcGISUtilities();
      }
      copilotChannelRef.current?.postMessage({ type: "design-update", text, payload });
      setMessages((items) => [...items, { role: "ai", text: response.ok && payload.reply ? payload.reply : payload.error || "I couldnâ€™t save that design input. Please try again." }]);
    } catch { setMessages((items) => [...items, { role: "ai", text: "I couldnâ€™t save that design input. Please try again." }]); }
    finally { setThinking(false); }
  };

  const loadAreaContext = async (location: { lat: number; lng: number }) => {
    setContextLoading(true);
    try {
      const response = await fetch(`/api/map/context?lat=${location.lat}&lng=${location.lng}`);
      if (response.ok) {
        const context = await response.json() as AreaContext;
        setAreaContext(context);
        setStandardsLoading(true);
        try {
          const standardsResponse = await fetch("/api/design/standards", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(context) });
          let resolvedStandards: StandardsContext | null = null;
          if (standardsResponse.ok) { resolvedStandards = await standardsResponse.json() as StandardsContext; setStandards(resolvedStandards); }
          const shared = { location, context, standards: resolvedStandards };
          localStorage.setItem("autovad-design-context", JSON.stringify(shared));
          copilotChannelRef.current?.postMessage({ type: "context", ...shared });
        } finally {
          setStandardsLoading(false);
        }
      }
    } finally {
      setContextLoading(false);
    }
  };

  const useRibbonTool = (tool: RibbonTool) => {
    setCanvasMode("plan"); setMapBackground(true);
    if (tool.action) { window.dispatchEvent(new CustomEvent("autovad:manual-action", { detail: { action: tool.id } })); return; }
    const resolvedTool = tool.id === "station" ? "text" : tool.id;
    setManualTool(resolvedTool); window.dispatchEvent(new CustomEvent("autovad:manual-tool", { detail: { tool: resolvedTool, snap: snapOn } }));
  };

  const toggleManualSnap = () => {
    const next = !snapOn; setSnapOn(next); window.dispatchEvent(new CustomEvent("autovad:manual-tool", { detail: { tool: manualTool, snap: next } }));
  };

  return <main className={popoutMode ? "studio-shell copilot-popout" : `studio-shell ribbon-${manualRibbonOpen ? "open" : "closed"}`}>
    {!popoutMode && <header className="studio-topbar">
      <a className="brand" href="/"><span className="brand-mark"><i /><i /><i /></span><span>AUTO<span>VAD</span></span></a>
      <nav className="product-tabs"><a href="/">TAKEOFF</a><a className="active" href="/design">AI DESIGN <b>BETA</b></a></nav>
      <div className="project-name"><span>PROJECT</span><strong>Untitled civil concept</strong><i>âŒ„</i></div>
      <div className="studio-actions"><button>Share</button><button className="export-disabled">Export â–¾</button><button className="pro-button" onClick={() => setShowPlans(true)}>â—† DESIGN PRO</button></div>
    </header>}

    {!popoutMode && <div className={`civil-ribbon${manualRibbonOpen ? " open" : " closed"}`}>
      <button type="button" className="manual-design-toggle" onClick={() => setManualRibbonOpen((value) => !value)} aria-expanded={manualRibbonOpen}><span>âŒ˜</span><b>MANUAL DESIGN</b><small>{manualRibbonOpen ? "CLOSE RIBBON" : "OPEN CIVIL TOOLS"}</small><i>{manualRibbonOpen ? "âŒƒ" : "âŒ„"}</i></button>
      <div className="ribbon-tabs">{(Object.keys(ribbonTools) as RibbonTab[]).map((tab) => <button type="button" className={ribbonTab === tab ? "active" : ""} onClick={() => setRibbonTab(tab)} key={tab}>{tab}</button>)}</div>
      <div className="ribbon-tools"><div className="ribbon-toolset">{ribbonTools[ribbonTab].map((tool) => <button type="button" className={!tool.action && manualTool === tool.id ? "active" : ""} onClick={() => useRibbonTool(tool)} key={`${ribbonTab}-${tool.label}`} title={tool.label}><b>{tool.glyph}</b><span>{tool.label}</span></button>)}</div><div className="ribbon-options"><button type="button" className={snapOn ? "active" : ""} onClick={toggleManualSnap}><b>âŒ—</b><span>Snap {snapOn ? "On" : "Off"}</span></button><small>{["alignment", "polyline", "feature", "storm", "sanitary", "water", "measure"].includes(manualTool) ? "CLICK VERTICES Â· DOUBLE-CLICK OR FINISH" : manualTool === "erase" ? "CLICK AN OBJECT TO ERASE" : "MANUAL DESIGN READY"}</small></div></div>
    </div>}

    <section className={`studio-body copilot-${copilotDetached || copilotView === "closed" ? "hidden" : copilotView}`} style={{ "--copilot-width": `${copilotWidth}px` } as CSSProperties}>
      {!popoutMode && <div className="design-canvas">
        <div className="canvas-mode-tabs"><button className={canvasMode === "map" ? "active" : ""} onClick={() => setCanvasMode("map")}>â—Ž 2D MAP</button><button className={canvasMode === "plan" ? "active" : ""} onClick={() => setCanvasMode("plan")}>âŒ— 2D PLAN</button><button className={canvasMode === "3d" ? "active" : ""} onClick={() => setCanvasMode("3d")}>â—‡ 3D MODEL</button>{canvasMode === "plan" && <button className={mapBackground ? "map-toggle active" : "map-toggle"} onClick={() => setMapBackground((value) => !value)}>â—« MAP BG {mapBackground ? "ON" : "OFF"}</button>}</div>
        <div className={canvasMode === "map" ? "geo-layer" : canvasMode === "plan" && mapBackground ? "geo-layer plan-background" : "geo-layer hidden-map"}><GeoMap roadConceptRevision={roadConceptRevision} roadBearing={areaContext?.roadBearing ?? null} onLocationChange={setSiteLocation} onAreaSelected={(location) => { setSiteLocation(location); void loadAreaContext(location); }} onConfirm={(location) => { setSiteLocation(location); setMessages((items) => [...items, { role: "ai", text: `Project location set at ${location.lat.toFixed(6)}, ${location.lng.toFixed(6)} (WGS 84). Iâ€™ll use this as the geospatial design origin and reference it when reviewing survey coordinates.` }]); setCanvasMode("plan"); }} /></div>
        {canvasMode === "3d" && <div className={`model-workspace layer-${modelLayer}`}><Map3D location={siteLocation} /><div className="model-toolbar"><span>3D DESIGN ENVIRONMENT</span><button className={modelLayer === "surface" ? "active" : ""} onClick={() => setModelLayer("surface")}>SURFACE</button><button className={modelLayer === "utilities" ? "active" : ""} onClick={() => setModelLayer("utilities")}>UNDERGROUND UTILITIES</button><button className={modelLayer === "corridor" ? "active" : ""} onClick={() => setModelLayer("corridor")}>ROAD CORRIDOR</button></div><div className="model-status"><span>INTERACTIVE 3D MAP Â· WGS 84</span><b>{modelLayer === "surface" ? "PUBLIC TERRAIN + 3D BUILDINGS" : modelLayer === "utilities" ? "UTILITY MODEL OVERLAY WORKSPACE" : "ROAD CORRIDOR MODEL WORKSPACE"}</b><small>Right-drag to orbit Â· Wheel to zoom Â· Public terrain is not a survey surface</small></div></div>}
      </div>}

      {!copilotDetached && copilotView === "closed" && !popoutMode && <button type="button" className="copilot-restore-tab" onClick={() => setCopilotView("open")}>âœ¦ DESIGN COPILOT</button>}
      <aside ref={copilotRef} onPointerDown={startSectionResize} className={`copilot-panel${copilotDetached && !popoutMode ? " detached" : ""}${copilotView === "collapsed" && !popoutMode ? " collapsed" : ""}`}>
        {!popoutMode && copilotView === "open" && <div className="copilot-dock-resizer" onPointerDown={startDockResize} title="Drag to resize Design Copilot" />}
        <div className="copilot-head"><div><span className="ai-spark">âœ¦</span><div><strong>Design Copilot</strong><small><i /> {thinking ? "ANALYZING DESIGN INPUT" : popoutMode ? "MOVED FROM DESIGN SCREEN Â· LIVE SYNC" : "DOCKED Â· RESIZE FROM LEFT EDGE"}</small></div></div><div className="copilot-window-actions">{!popoutMode && <button type="button" onClick={() => setCopilotView((view) => view === "collapsed" ? "open" : "collapsed")} title={copilotView === "collapsed" ? "Expand Copilot" : "Collapse Copilot"}>{copilotView === "collapsed" ? "â€¹" : "â€º"}</button>}<button type="button" onClick={popoutMode ? () => window.close() : openCopilotWindow} title={popoutMode ? "Return Copilot to the design screen" : "Move Copilot to another screen"}>{popoutMode ? "â†™" : "â†—"}</button>{!popoutMode && <button type="button" onClick={() => setCopilotView("closed")} title="Close Copilot">Ã—</button>}</div></div>
        <div className="copilot-scroll">
        <div className="design-progress"><div><span>DESIGN READINESS</span><b>{readiness}%</b></div><div className="readiness-bar"><i style={{ width: `${readiness}%` }} /></div></div>
        {lastCommand && <div className="command-analysis"><div><span>COMMAND RECOGNIZED</span><b>{Math.round(lastCommand.confidence * 100)}%</b></div><strong>{lastCommand.primaryIntent.replace("-", " ")}</strong><div className="command-tags">{lastCommand.intents.map((intent) => <i key={intent}>{intent.replace("-", " ")}</i>)}</div>{lastCommand.detectedValues.length > 0 && <p>Detected: {lastCommand.detectedValues.join(" Â· ")}</p>}{lastCommand.missingInputs.length > 0 && <small>Needs: {lastCommand.missingInputs.join(" Â· ")}</small>}</div>}
        {siteLocation && <div className="location-context"><span>â—Ž SITE LOCATION SET</span><b>{siteLocation.lat.toFixed(5)}, {siteLocation.lng.toFixed(5)}</b><button onClick={() => setCanvasMode("map")}>Edit</button></div>}
        {(contextLoading || areaContext) && <div className="road-context"><span>{contextLoading ? "READING OPENSTREETMAPâ€¦" : "MAPPED ROAD CONTEXT"}</span>{areaContext && <><strong>{areaContext.street}{areaContext.routeRef ? ` Â· ${areaContext.routeRef}` : ""}</strong><b>{areaContext.city}{areaContext.state ? `, ${areaContext.state}` : ""}</b><i>{areaContext.roadClass}{areaContext.highwayTag ? ` Â· OSM ${areaContext.highwayTag}` : ""}</i><small>Nearest mapped roadway Â· Verify classification with the governing agency</small></>}</div>}
        {areaContext && <div className="existing-road"><span>EXISTING ROAD DETECTION</span><div><b>Width <i>{areaContext.existingRoad.mappedWidth || "Not mapped"}</i></b><b>Lanes <i>{areaContext.existingRoad.lanes || "Not mapped"}</i></b><b>Sidewalk <i>{areaContext.existingRoad.sidewalk || "Not mapped"}</i></b><b>Curb <i>{areaContext.existingRoad.curb || "Not mapped"}</i></b><b>Gutter <i>{areaContext.existingRoad.gutter || "Not mapped"}</i></b><b>ROW <i>{areaContext.existingRoad.rightOfWay || "Survey/GIS required"}</i></b></div><small>Public map attributes only Â· Confirm curb, gutter, sidewalk and legal ROW from survey or agency GIS</small></div>}
        {(standardsLoading || standards) && <div className="standards-context"><div><span>{standardsLoading ? "SEARCHING OFFICIAL STANDARDSâ€¦" : "JURISDICTION STANDARDS"}</span>{standards && <b className={standards.status}>{standards.status.replaceAll("-", " ")}</b>}</div>{standards && <><p>{standards.summary}</p>{standards.sources.length > 0 && <div className="standards-sources">{standards.sources.map((source) => <a href={source.url} target="_blank" rel="noreferrer" key={source.url}>{source.title} â†—</a>)}</div>}</>}</div>}
        {roadStage !== null && <div className="road-workflow"><div><span>ROAD DESIGN WORKFLOW</span><b>{roadStage + 1}/{roadStages.length}</b></div><ol>{roadStages.map((stage, index) => <li className={index < roadStage ? "done" : index === roadStage ? "active" : ""} key={stage}><i>{index < roadStage ? "âœ“" : index + 1}</i><span>{stage}</span></li>)}</ol><small>{aiPowered ? "OPENAI COPILOT ACTIVE" : "OPENAI CONNECTION REQUIRED Â· STRUCTURED FALLBACK ACTIVE"}</small></div>}
        <div className="plan-production-profile"><span>PLAN PRODUCTION PROFILE</span><b>Municipal roadway + utility sheets</b><small>242 reference sheets reviewed Â· plan/profile, station-offset labels, typical sections, cross sections, quantities and details</small><i>REFERENCE STYLE ONLY Â· PROJECT VALUES REQUIRE VERIFIED DATA</i></div>
        {terrainSection && <div className="terrain-section-status"><span>PUBLIC TERRAIN ROAD SECTION</span><b>{terrainSection.source} Â· {terrainSection.resolutionMeters} m DEM</b><small>Existing ground {terrainSection.minimumElevationFeet.toFixed(1)}-{terrainSection.maximumElevationFeet.toFixed(1)} ft Â· {terrainSection.points.length} samples</small><i>PRELIMINARY ONLY Â· REPLACE WITH PROJECT SURVEY</i></div>}
        <div className="chat-stream">
          <div className="phase-marker"><span>PHASE 01</span><b>Define design basis</b></div>
          {messages.length === 1 && <div className="prompt-starters"><span>START WITH A DESIGN TASK</span>{starters.map((starter) => <button key={starter} onClick={() => setPrompt(starter)}>{starter}<b>â†’</b></button>)}</div>}
          {messages.map((message, index) => <div className={`chat-message ${message.role}`} key={index}>{message.role === "ai" && <span className="ai-avatar">âœ¦</span>}<p>{message.text}</p></div>)}
          {thinking && <div className="chat-message ai typing"><span className="ai-avatar">âœ¦</span><p><i /><i /><i /></p></div>}
          {uploads.length > 0 && <div className="file-stack"><div className="file-stack-head"><span>PROJECT SOURCES</span><b>{uploads.length} ADDED</b></div>{uploads.map((file, index) => <div className="source-file" key={`${file.name}-${index}`}><span>{file.type}</span><div><strong>{file.name}</strong><small>{(file.size / 1048576).toFixed(1)} MB Â· Ready to index</small></div><button onClick={() => setUploads((items) => items.filter((_, i) => i !== index))}>Ã—</button></div>)}</div>}
        </div>
        <div className="intake-checks"><span>RECOMMENDED INPUTS</span><div className={uploads.length ? "done" : ""}><i>{uploads.length ? "âœ“" : "1"}</i><p><b>Existing-conditions survey</b><small>LandXML, CSV, DWG, DXF, or PDF</small></p></div><div><i>2</i><p><b>Design criteria</b><small>Municipal standards or owner specs</small></p></div><div><i>3</i><p><b>Project program</b><small>Use, access, parking, utilities</small></p></div></div>
        </div>
        <div className="chat-compose">
          <div className="command-label"><span>âœ¦ TYPE A DESIGN COMMAND</span><b>ENTER TO SEND Â· SHIFT + ENTER FOR NEW LINE</b></div>
          <div className="command-entry"><button className="attach-command" onClick={() => inputRef.current?.click()} aria-label="Attach design files">ï¼‹</button><textarea autoFocus value={prompt} onChange={(e) => setPrompt(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} placeholder="Example: Design a 40,000 SF warehouse site with 120 parking spaces, two truck entrances, detention, and utility connectionsâ€¦" rows={3} /><button className="send-command" onClick={send} disabled={!prompt.trim() || thinking}>{thinking ? "â€¢â€¢â€¢" : "SEND â†‘"}</button></div>
          <div className="compose-foot"><span>{thinking ? "Reviewing project contextâ€¦" : "Describe what to design in plain language. Engineer review required."}</span><b>{uploads.length ? `${uploads.length} FILE${uploads.length === 1 ? "" : "S"} ATTACHED` : "DWG Â· LANDXML Â· EXCEL Â· CSV"}</b><input ref={inputRef} type="file" multiple accept=".pdf,.dwg,.dxf,.xml,.landxml,.csv,.tsv,.txt,.doc,.docx,.xlsx,.xls" onChange={(e) => addFiles(e.target.files)} /></div>
        </div>
        <div className="copilot-resize-hint" aria-hidden="true">âŒŸ</div>
      </aside>
    </section>

    {showPlans && <div className="plan-modal" role="dialog" aria-modal="true"><div className="plan-card"><button className="modal-close" onClick={() => setShowPlans(false)}>Ã—</button><span className="plan-kicker">AUTOVAD DESIGN PRO</span><h2>AI-assisted civil design,<br />priced for project teams.</h2><p>Phase one includes the design copilot, source-file intake, design-basis organization, and concept workspace.</p><div className="price"><strong>$299</strong><span>/ user / month<br />Billed monthly</span></div><ul><li>âœ“ Unlimited design projects</li><li>âœ“ 100 GB source-file storage</li><li>âœ“ AI design-basis reviews</li><li>âœ“ Concept workspace and team sharing</li><li className="later">Coming next: grading, utility, and corridor generation</li></ul><button className="subscribe-cta">Request Design Pro access <span>â†—</span></button><small>Early-access pricing Â· Cancel anytime when billing launches</small></div></div>}
  </main>;
}

export default function DesignStudio() {
  if (process.env.NEXT_PUBLIC_ENABLE_AI_DESIGN !== "true") return <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", background: "#07100e", color: "#f4f6ef", fontFamily: "Arial, sans-serif" }}><div style={{ textAlign: "center" }}><h1 style={{ fontSize: 64, margin: 0 }}>404</h1><p style={{ color: "#89948e" }}>This page is not available.</p><a href="/" style={{ color: "#d9ff43" }}>Return to AutoVAD</a></div></main>;
  return <DesignStudioWorkspace />;
}

```

---

## `app\design\GeoMap.tsx`

```tsx
"use client";

import "leaflet/dist/leaflet.css";
import { useEffect, useRef, useState } from "react";
import type { ImageOverlay, LatLng, Layer, LayerGroup, Map as LeafletMap, Marker as LeafletMarker, Rectangle, TileLayer } from "leaflet";
import { utilityColors, type UtilityQueryResult } from "../../lib/gis";
import type { ConceptArtifact } from "../../lib/conceptDesign";
import type { SurveyDataset } from "../../lib/surveyXml";

type Basemap = "streets" | "satellite" | "terrain";
type Location = { lng: number; lat: number };
export type ProjectArea = { north: number; south: number; east: number; west: number };
type SavedProjectArea = ProjectArea & { id: string; name: string };
type AreaHandle = "nw" | "n" | "ne" | "e" | "se" | "s" | "sw" | "w";

const areaHandleKinds: AreaHandle[] = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];

const sources: Record<Basemap, { label: string; attribution: string; maxzoom: number }> = {
  streets: { label: "OpenStreetMap", attribution: "Â© OpenStreetMap contributors", maxzoom: 19 },
  satellite: { label: "Aerial imagery", attribution: "Tiles Â© Esri", maxzoom: 19 },
  terrain: { label: "Topo + contours", attribution: "Â© OpenStreetMap contributors, SRTM | Â© OpenTopoMap", maxzoom: 17 },
};

const tileUrl = (type: Basemap) => `/api/map/tiles/${type}/{z}/{x}/{y}`;

const publishProjectArea = (area: ProjectArea) => {
  localStorage.setItem("autovad-project-area", JSON.stringify(area));
  window.dispatchEvent(new CustomEvent<ProjectArea>("autovad:project-area", { detail: area }));
};

export default function GeoMap({ onConfirm, onLocationChange, onAreaSelected, roadConceptRevision, roadBearing }: { onConfirm: (location: Location) => void; onLocationChange: (location: Location) => void; onAreaSelected: (location: Location, area: ProjectArea) => void; roadConceptRevision: number; roadBearing: number | null }) {
  const host = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const markerRef = useRef<LeafletMarker | null>(null);
  const layerRef = useRef<TileLayer | null>(null);
  const areaRef = useRef<Rectangle | null>(null);
  const savedAreaLayersRef = useRef<Map<string, Rectangle>>(new Map());
  const areaHandlesRef = useRef<LeafletMarker[]>([]);
  const lidarOverlayRef = useRef<ImageOverlay | null>(null);
  const contourOverlayRef = useRef<ImageOverlay | null>(null);
  const roadConceptRef = useRef<LayerGroup | null>(null);
  const utilityDataRef = useRef<LayerGroup | null>(null);
  const conceptDataRef = useRef<LayerGroup | null>(null);
  const surveyDataRef = useRef<LayerGroup | null>(null);
  const surveyDatasetRef = useRef<SurveyDataset | null>(null);
  const manualLayersRef = useRef<Layer[]>([]);
  const areaStartRef = useRef<LatLng | null>(null);
  const selectingAreaRef = useRef(false);
  const projectAreasRef = useRef<SavedProjectArea[]>([]);
  const [basemap, setBasemap] = useState<Basemap>("streets");
  const [location, setLocation] = useState<Location>({ lng: -96.797, lat: 32.777 });
  const [manualLat, setManualLat] = useState("32.777000");
  const [manualLng, setManualLng] = useState("-96.797000");
  const [coordinateError, setCoordinateError] = useState("");
  const [locating, setLocating] = useState(false);
  const [autoCentered, setAutoCentered] = useState(false);
  const [fullMap, setFullMap] = useState(false);
  const [mapError, setMapError] = useState("");
  const [manualStatus, setManualStatus] = useState("");
  const [selectingArea, setSelectingArea] = useState(false);
  const [areaPanelOpen, setAreaPanelOpen] = useState(true);
  const [areaSelected, setAreaSelected] = useState(false);
  const [projectAreas, setProjectAreas] = useState<SavedProjectArea[]>(() => { try { return typeof window === "undefined" ? [] : JSON.parse(localStorage.getItem("autovad-project-areas") || "[]"); } catch { return []; } });
  const [activeAreaId, setActiveAreaId] = useState<string | null>(null);
  projectAreasRef.current = projectAreas;
  const [mapLocked, setMapLocked] = useState(false);
  const [showLidar, setShowLidar] = useState(false);
  const [showContours, setShowContours] = useState(false);
  const [elevationStatus, setElevationStatus] = useState("");
  const [utilityData, setUtilityData] = useState<UtilityQueryResult | null>(null);
  const [conceptArtifacts, setConceptArtifacts] = useState<ConceptArtifact[]>([]);
  const [surveyDataset, setSurveyDataset] = useState<SurveyDataset | null>(null);
  const [surveyVisibility, setSurveyVisibility] = useState({ points: true, breaklines: true, contours: true });
  const [crsCode, setCrsCode] = useState("");
  const [horizontalUnits, setHorizontalUnits] = useState("US survey feet");
  const [verticalDatum, setVerticalDatum] = useState("");
  const [verticalUnits, setVerticalUnits] = useState("US survey feet");
  const [targetVerticalDatum, setTargetVerticalDatum] = useState("NAVD88");
  const [vdatumRegion, setVdatumRegion] = useState("contiguous");
  const [verticalStatus, setVerticalStatus] = useState("");
  const [convertingVertical, setConvertingVertical] = useState(false);

  useEffect(() => {
    setManualLat(location.lat.toFixed(6));
    setManualLng(location.lng.toFixed(6));
  }, [location.lat, location.lng]);
  const [crsStatus, setCrsStatus] = useState("");
  const [applyingCrs, setApplyingCrs] = useState(false);

  const drawSurvey = async (dataset: SurveyDataset | null, visibility = surveyVisibility) => {
    surveyDataRef.current?.remove();
    surveyDataRef.current = null;
    const map = mapRef.current;
    if (!dataset || !map) return;
    const area = areaRef.current?.getBounds();
    if (!dataset.geographic && !dataset.transformed && (!area || !dataset.bounds)) return;
    const module = await import("leaflet");
    const L = module.default || module;
    const convert = (northing: number, easting: number, wgs84?: [number, number]): [number, number] => {
      if (wgs84) return [wgs84[1], wgs84[0]];
      if (dataset.geographic) return [northing, easting];
      const source = dataset.bounds!;
      const target = area!;
      const nx = (easting - source.minEasting) / Math.max(source.maxEasting - source.minEasting, 1);
      const ny = (northing - source.minNorthing) / Math.max(source.maxNorthing - source.minNorthing, 1);
      return [target.getSouth() + (target.getNorth() - target.getSouth()) * (.08 + ny * .84), target.getWest() + (target.getEast() - target.getWest()) * (.08 + nx * .84)];
    };
    const groups: LayerGroup[] = [];
    if (visibility.points) groups.push(L.layerGroup(dataset.points.map((point) => { const elevation = point.convertedElevation ?? point.elevation; return L.circleMarker(convert(point.northing, point.easting, point.wgs84), { radius: 3, color: "#06100c", weight: 1, fillColor: "#ffdf6b", fillOpacity: .95 }).bindTooltip(`${point.id}${elevation === null ? "" : ` Â· EL ${elevation.toFixed(2)}`}${dataset.verticalDatum ? ` Â· ${dataset.verticalDatum}` : ""}${point.description ? ` Â· ${point.description}` : ""}`); })));
    if (visibility.breaklines) groups.push(L.layerGroup(dataset.breaklines.map((line) => L.polyline(line.points.map((point, index) => convert(point[0], point[1], line.wgs84?.[index])), { color: "#ff7d45", weight: 3, opacity: .9 }).bindTooltip(`Breakline Â· ${line.id}`))));
    if (visibility.contours) groups.push(L.layerGroup(dataset.contours.map((line) => L.polyline(line.points.map((point, index) => convert(point[0], point[1], line.wgs84?.[index])), { color: "#79dca9", weight: 1, opacity: .78 }).bindTooltip(`Contour Â· ${line.id}`))));
    surveyDataRef.current = L.layerGroup(groups).addTo(map);
    areaRef.current?.bringToFront();
    const renderedCoordinates = [
      ...dataset.points.map((point) => convert(point.northing, point.easting, point.wgs84)),
      ...dataset.breaklines.flatMap((line) => line.points.map((point, index) => convert(point[0], point[1], line.wgs84?.[index]))),
      ...dataset.contours.flatMap((line) => line.points.map((point, index) => convert(point[0], point[1], line.wgs84?.[index]))),
    ];
    if ((dataset.geographic || dataset.transformed) && renderedCoordinates.length) map.fitBounds(L.latLngBounds(renderedCoordinates), { padding: [60, 60], maxZoom: 19 });
  };

  const applySurveyCrs = async () => {
    const dataset = surveyDatasetRef.current;
    if (!dataset || applyingCrs) return;
    setApplyingCrs(true); setCrsStatus("Resolving CRSâ€¦");
    try {
      const response = await fetch(`/api/gis/crs?code=${encodeURIComponent(crsCode)}`);
      const resolved = await response.json() as { code?: string; name?: string; definition?: string; error?: string };
      if (!response.ok || !resolved.definition || !resolved.code) throw new Error(resolved.error || "CRS could not be resolved.");
      const module = await import("proj4");
      const proj4 = module.default;
      proj4.defs(resolved.code, resolved.definition);
      const transform = (northing: number, easting: number) => proj4(resolved.code!, "EPSG:4326", [easting, northing]) as [number, number];
      const updated: SurveyDataset = {
        ...dataset,
        coordinateSystem: `${resolved.code} Â· ${resolved.name || ""}`,
        transformed: true,
        horizontalUnits,
        verticalDatum: verticalDatum || "Not declared",
        verticalUnits,
        points: dataset.points.map((point) => ({ ...point, wgs84: transform(point.northing, point.easting) })),
        breaklines: dataset.breaklines.map((line) => ({ ...line, wgs84: line.points.map((point) => transform(point[0], point[1])) })),
        contours: dataset.contours.map((line) => ({ ...line, wgs84: line.points.map((point) => transform(point[0], point[1])) })),
      };
      const invalid = updated.points.some((point) => !point.wgs84 || Math.abs(point.wgs84[1]) > 90 || Math.abs(point.wgs84[0]) > 180);
      if (invalid) throw new Error("The transformed coordinates fall outside valid WGS 84 limits. Check the EPSG code and coordinate order.");
      surveyDatasetRef.current = updated; setSurveyDataset(updated);
      sessionStorage.setItem("autovad-survey-data", JSON.stringify(updated));
      window.dispatchEvent(new CustomEvent("autovad:survey-data", { detail: updated }));
      setCrsStatus(`${resolved.code} applied Â· survey aligned to WGS 84`);
    } catch (error) { setCrsStatus(error instanceof Error ? error.message : "CRS transformation failed."); }
    finally { setApplyingCrs(false); }
  };

  const convertVerticalDatum = async () => {
    const dataset = surveyDatasetRef.current;
    if (!dataset || convertingVertical) return;
    if (!verticalDatum || verticalDatum === targetVerticalDatum) { setVerticalStatus("Choose different source and target vertical datums."); return; }
    const coordinate = (northing: number, easting: number, wgs84?: [number, number]): [number, number] | null => wgs84 || (dataset.geographic ? [easting, northing] : null);
    type ElevationRef = { kind: "point" | "breakline" | "contour"; index: number; pointIndex?: number; lng: number; lat: number; elevation: number };
    const refs: ElevationRef[] = [];
    dataset.points.forEach((point, index) => { const at = coordinate(point.northing, point.easting, point.wgs84); if (at && point.elevation !== null) refs.push({ kind: "point", index, lng: at[0], lat: at[1], elevation: point.elevation }); });
    (["breaklines", "contours"] as const).forEach((kind) => dataset[kind].forEach((line, index) => line.points.forEach((point, pointIndex) => { const at = coordinate(point[0], point[1], line.wgs84?.[pointIndex]); if (at && point[2] !== null) refs.push({ kind: kind === "breaklines" ? "breakline" : "contour", index, pointIndex, lng: at[0], lat: at[1], elevation: point[2] }); })));
    if (!refs.length) { setVerticalStatus(dataset.geographic || dataset.transformed ? "No elevations were found in this survey." : "Apply the horizontal CRS first so NOAA can locate each elevation."); return; }
    const unitCode: Record<string, string> = { "US survey feet": "us_ft", "International feet": "ft", Meters: "m" };
    setConvertingVertical(true); setVerticalStatus(`Converting 0 of ${refs.length} elevations...`);
    try {
      const values: Array<{ elevation: number; uncertainty: number | null }> = [];
      let metadata: { source?: string; convertedAt?: string } = {};
      for (let start = 0; start < refs.length; start += 200) {
        const batch = refs.slice(start, start + 200);
        const response = await fetch("/api/gis/vertical-datum", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ points: batch, sourceDatum: verticalDatum, targetDatum: targetVerticalDatum, sourceUnit: unitCode[verticalUnits], targetUnit: unitCode[verticalUnits], region: vdatumRegion }) });
        const result = await response.json() as { results?: Array<{ elevation: number; uncertainty: number | null }>; source?: string; convertedAt?: string; error?: string };
        if (!response.ok || !result.results) throw new Error(result.error || "Elevation conversion failed.");
        values.push(...result.results); metadata = result; setVerticalStatus(`Converted ${values.length} of ${refs.length} elevations...`);
      }
      const points = dataset.points.map((point) => ({ ...point }));
      const breaklines = dataset.breaklines.map((line) => ({ ...line, convertedElevations: line.points.map(() => null) }));
      const contours = dataset.contours.map((line) => ({ ...line, convertedElevations: line.points.map(() => null) }));
      refs.forEach((ref, index) => { if (ref.kind === "point") points[ref.index].convertedElevation = values[index].elevation; else (ref.kind === "breakline" ? breaklines : contours)[ref.index].convertedElevations![ref.pointIndex!] = values[index].elevation; });
      const uncertainties = values.map((value) => value.uncertainty).filter((value): value is number => value !== null);
      const updated: SurveyDataset = { ...dataset, points, breaklines, contours, verticalDatum: targetVerticalDatum, verticalUnits, elevationConversion: { sourceDatum: verticalDatum, targetDatum: targetVerticalDatum, sourceUnit: verticalUnits, targetUnit: verticalUnits, region: vdatumRegion, source: metadata.source || "NOAA VDatum", convertedAt: metadata.convertedAt || new Date().toISOString(), maximumUncertainty: uncertainties.length ? Math.max(...uncertainties) : null } };
      surveyDatasetRef.current = updated; setSurveyDataset(updated); sessionStorage.setItem("autovad-survey-data", JSON.stringify(updated)); window.dispatchEvent(new CustomEvent("autovad:survey-data", { detail: updated }));
      setVerticalStatus(`${refs.length} elevations converted to ${targetVerticalDatum}${uncertainties.length ? ` Â· max uncertainty ${Math.max(...uncertainties).toFixed(3)} ${verticalUnits}` : ""}`);
    } catch (error) { setVerticalStatus(error instanceof Error ? error.message : "Elevation conversion failed."); }
    finally { setConvertingVertical(false); }
  };

  useEffect(() => {
    if (!host.current || mapRef.current) return;
    let active = true;
    let cleanupManual = () => {};
    void import("leaflet").then((module) => {
      if (!active || !host.current) return;
      const L = module.default || module;
      const map = L.map(host.current, {
        center: [location.lat, location.lng],
        zoom: 13,
        zoomControl: false,
        scrollWheelZoom: true,
        doubleClickZoom: true,
        dragging: true,
      });
      const layer = L.tileLayer(tileUrl("streets"), { attribution: sources.streets.attribution, maxZoom: sources.streets.maxzoom }).addTo(map);
      L.control.scale({ imperial: true, metric: false, position: "bottomleft" }).addTo(map);
      const marker = L.marker([location.lat, location.lng], {
        draggable: true,
        icon: L.divIcon({ className: "site-map-marker", iconSize: [18, 18], iconAnchor: [9, 9] }),
      }).addTo(map);
      let manualTool = "select"; let snapEnabled = true; let draftPoints: LatLng[] = []; let draftLayer: Layer | null = null; let selectedManualLayer: Layer | null = null;
      const lineTools = ["alignment", "polyline", "feature", "storm", "sanitary", "water", "measure", "surface", "breakline", "contour", "offset", "widening", "profile", "corridor", "grading", "daylight", "parcel", "row", "easement", "pressure"];
      const manualColors: Record<string, string> = { alignment: "#d9ff43", polyline: "#f3f5ee", feature: "#ff9f43", storm: "#25d4ae", sanitary: "#d853ff", water: "#168cff", measure: "#ffcf65", surface: "#8fd1a8", breakline: "#ff9f43", contour: "#bca06b", offset: "#d9ff43", widening: "#e9d65e", profile: "#ff7066", corridor: "#e8a348", grading: "#ff9f43", daylight: "#ffd18b", parcel: "#ec75ff", row: "#ff5d7d", easement: "#b78cff", pressure: "#168cff" };
      const snapped = (point: LatLng) => snapEnabled ? L.latLng(Math.round(point.lat * 1000000) / 1000000, Math.round(point.lng * 1000000) / 1000000) : point;
      const saveManualLayers = () => { try { sessionStorage.setItem("autovad-manual-design", JSON.stringify(manualLayersRef.current.flatMap((item) => "toGeoJSON" in item ? [(item as Layer & { toGeoJSON: () => GeoJSON.Feature }).toGeoJSON()] : []))); } catch { /* keep the drawing active in memory */ } };
      const registerLayer = (manualLayer: Layer, label: string) => {
        manualLayersRef.current.push(manualLayer);
        (manualLayer as Layer & { bindTooltip?: (text: string) => void }).bindTooltip?.(label + " Â· MANUAL DESIGN");
        manualLayer.on("click", (event) => {
          if (manualTool !== "erase" && manualTool !== "select") return; L.DomEvent.stopPropagation(event);
          if (manualTool === "erase") { manualLayer.remove(); manualLayersRef.current = manualLayersRef.current.filter((item) => item !== manualLayer); if (selectedManualLayer === manualLayer) selectedManualLayer = null; saveManualLayers(); return; }
          if (selectedManualLayer && "setStyle" in selectedManualLayer) (selectedManualLayer as Layer & { setStyle: (style: object) => void }).setStyle({ weight: 3, opacity: .95 });
          selectedManualLayer = manualLayer; if ("setStyle" in manualLayer) (manualLayer as Layer & { setStyle: (style: object) => void }).setStyle({ color: "#ffffff", weight: 7, opacity: 1 });
        });
        saveManualLayers();
      };
      const finishManualLine = () => {
        draftLayer?.remove(); draftLayer = null;
        if (draftPoints.length < 2) { draftPoints = []; setManualStatus(""); return; }
        const line = L.polyline(draftPoints, { color: manualColors[manualTool] || manualColors.polyline, weight: manualTool === "alignment" ? 5 : 3, opacity: .95, dashArray: manualTool === "measure" ? "6 5" : undefined }).addTo(map);
        const feet = draftPoints.slice(1).reduce((total, point, index) => total + map.distance(draftPoints[index], point) * 3.28084, 0);
        registerLayer(line, manualTool === "measure" ? "MEASURE " + feet.toFixed(1) + " FT" : manualTool.toUpperCase()); draftPoints = []; setManualStatus("");
      };
      const changeManualTool = (event: Event) => {
        const detail = (event as CustomEvent<{ tool: string; snap?: boolean }>).detail; finishManualLine(); manualTool = detail.tool; if (typeof detail.snap === "boolean") snapEnabled = detail.snap;
        map.getContainer().dataset.manualTool = manualTool; if (manualTool === "select" || manualTool === "pan") map.dragging.enable(); else map.dragging.disable();
      };
      const manualAction = (event: Event) => {
        const action = (event as CustomEvent<{ action: string }>).detail.action;
        if (action === "undo") { draftLayer?.remove(); draftLayer = null; draftPoints = []; manualLayersRef.current.pop()?.remove(); saveManualLayers(); }
        if (action === "finish") finishManualLine();
        if (action === "clear" && window.confirm("Clear all manual design objects from this workspace?")) { draftLayer?.remove(); draftLayer = null; draftPoints = []; manualLayersRef.current.forEach((item) => item.remove()); manualLayersRef.current = []; saveManualLayers(); }
      };
      map.on("click", (event) => {
        if (["select", "pan", "erase"].includes(manualTool) || selectingAreaRef.current) return;
        const point = snapped(event.latlng);
        if (manualTool === "point") { registerLayer(L.circleMarker(point, { radius: 5, color: "#07100e", weight: 2, fillColor: "#d9ff43", fillOpacity: 1 }).addTo(map), "COGO POINT"); return; }
        if (manualTool === "text") { const label = window.prompt("Enter design label", "DESIGN NOTE"); if (label) registerLayer(L.marker(point, { icon: L.divIcon({ className: "manual-design-label", html: label, iconSize: [140, 22], iconAnchor: [0, 11] }) }).addTo(map), label); return; }
        if (lineTools.includes(manualTool)) { draftPoints.push(point); draftLayer?.remove(); draftLayer = L.polyline([...draftPoints, point], { color: manualColors[manualTool], weight: 3, opacity: .9, dashArray: "5 4" }).addTo(map); setManualStatus(manualTool.toUpperCase() + " Â· SPECIFY NEXT POINT"); }
      });
      map.on("dblclick", () => { if (draftPoints.length > 1) finishManualLine(); });
      map.on("contextmenu", (event) => { if (!draftPoints.length) return; L.DomEvent.preventDefault(event); finishManualLine(); });
      const commandKeyDown = (event: KeyboardEvent) => {
        if (/INPUT|TEXTAREA|SELECT/.test((event.target as HTMLElement)?.tagName || "")) return;
        if (event.key === "Escape" && draftPoints.length) { event.preventDefault(); draftLayer?.remove(); draftLayer = null; draftPoints = []; setManualStatus(""); return; }
        if (event.key === "Enter" && draftPoints.length > 1) { event.preventDefault(); finishManualLine(); return; }
        if (!selectedManualLayer || event.key !== "Delete" && event.key !== "Backspace") return;
        event.preventDefault(); selectedManualLayer.remove(); manualLayersRef.current = manualLayersRef.current.filter((item) => item !== selectedManualLayer); selectedManualLayer = null; saveManualLayers();
      };
      window.addEventListener("autovad:manual-tool", changeManualTool); window.addEventListener("autovad:manual-action", manualAction);
      window.addEventListener("keydown", commandKeyDown);
      cleanupManual = () => { window.removeEventListener("autovad:manual-tool", changeManualTool); window.removeEventListener("autovad:manual-action", manualAction); window.removeEventListener("keydown", commandKeyDown); };
      try {
        const storedManual = JSON.parse(sessionStorage.getItem("autovad-manual-design") || "[]") as GeoJSON.Feature[];
        if (storedManual.length) L.geoJSON({ type: "FeatureCollection", features: storedManual }, { style: { color: "#d9ff43", weight: 3, opacity: .9 }, pointToLayer: (_feature, latlng) => L.circleMarker(latlng, { radius: 5, color: "#07100e", fillColor: "#d9ff43", fillOpacity: 1 }) }).eachLayer((savedLayer) => { savedLayer.addTo(map); registerLayer(savedLayer, "RESTORED OBJECT"); });
      } catch { /* no saved manual drawing */ }
      marker.on("dragend", () => {
        const p = marker.getLatLng();
        const next = { lng: p.lng, lat: p.lat };
        setLocation(next);
        onLocationChange(next);
      });
      map.on("mousedown", (event) => {
        if (!selectingAreaRef.current) return;
        roadConceptRef.current?.remove();
        roadConceptRef.current = null;
        areaStartRef.current = event.latlng;
        areaRef.current?.remove();
        areaRef.current = L.rectangle([event.latlng, event.latlng], { color: "#d9ff43", weight: 3, fillColor: "#d9ff43", fillOpacity: .16, dashArray: "8 6" }).addTo(map);
      });
      map.on("mousemove", (event) => {
        if (selectingAreaRef.current && areaStartRef.current && areaRef.current) areaRef.current.setBounds([areaStartRef.current, event.latlng]);
        if (!selectingAreaRef.current && lineTools.includes(manualTool) && draftPoints.length && draftLayer && "setLatLngs" in draftLayer) {
          const cursor = snapped(event.latlng); (draftLayer as Layer & { setLatLngs: (points: LatLng[]) => void }).setLatLngs([...draftPoints, cursor]);
          const committed = draftPoints.slice(1).reduce((total, point, index) => total + map.distance(draftPoints[index], point), 0); const segment = map.distance(draftPoints[draftPoints.length - 1], cursor); const last = draftPoints[draftPoints.length - 1];
          const y = Math.sin((cursor.lng - last.lng) * Math.PI / 180) * Math.cos(cursor.lat * Math.PI / 180); const x = Math.cos(last.lat * Math.PI / 180) * Math.sin(cursor.lat * Math.PI / 180) - Math.sin(last.lat * Math.PI / 180) * Math.cos(cursor.lat * Math.PI / 180) * Math.cos((cursor.lng - last.lng) * Math.PI / 180); const bearing = (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
          setManualStatus(manualTool.toUpperCase() + " Â· TOTAL " + ((committed + segment) * 3.28084).toFixed(1) + " FT Â· SEG " + (segment * 3.28084).toFixed(1) + " FT Â· " + bearing.toFixed(1) + "Â°");
        }
      });
      map.on("mouseup", (event) => {
        if (!selectingAreaRef.current || !areaStartRef.current || !areaRef.current) return;
        areaRef.current.setBounds([areaStartRef.current, event.latlng]);
        areaStartRef.current = null;
        selectingAreaRef.current = false;
        setSelectingArea(false);
        setAreaSelected(true);
        map.dragging.enable();
        const bounds = areaRef.current.getBounds();
        const center = bounds.getCenter();
        const next = { lat: center.lat, lng: center.lng };
        marker.setLatLng(center);
        setLocation(next);
        onLocationChange(next);
        const projectArea: SavedProjectArea = { id: `site-${Date.now()}`, name: `SITE ${projectAreasRef.current.length + 1}`, north: bounds.getNorth(), south: bounds.getSouth(), east: bounds.getEast(), west: bounds.getWest() };
        const nextAreas = [...projectAreasRef.current, projectArea]; projectAreasRef.current = nextAreas; setProjectAreas(nextAreas); setActiveAreaId(projectArea.id); localStorage.setItem("autovad-project-areas", JSON.stringify(nextAreas));
        onAreaSelected(next, projectArea);
        publishProjectArea(projectArea);
        map.fitBounds(bounds, { padding: [70, 70] });
        map.dragging.enable();
        map.scrollWheelZoom.enable();
        map.doubleClickZoom.enable();
        marker.dragging?.disable();
        setMapLocked(true);
      });
      mapRef.current = map;
      markerRef.current = marker;
      layerRef.current = layer;
      setMapError("");
      if (surveyDatasetRef.current) window.setTimeout(() => void drawSurvey(surveyDatasetRef.current), 0);
      if (navigator.geolocation) {
        setLocating(true);
        navigator.geolocation.getCurrentPosition((position) => {
          if (!active) return;
          setLocating(false);
          if (areaRef.current) return;
          const nearby = { lng: position.coords.longitude, lat: position.coords.latitude };
          setLocation(nearby);
          marker.setLatLng([nearby.lat, nearby.lng]);
          map.flyTo([nearby.lat, nearby.lng], 11);
          setAutoCentered(true);
        }, () => setLocating(false), {
          enableHighAccuracy: false,
          timeout: 8000,
          maximumAge: 30 * 60 * 1000,
        });
      }
    }).catch(() => setMapError("Map imagery could not start. Refresh the page to retry."));
    return () => {
      active = false;
      cleanupManual();
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const loadSurvey = (event: Event) => {
      const dataset = (event as CustomEvent<SurveyDataset>).detail;
      surveyDatasetRef.current = dataset;
      setSurveyDataset(dataset);
      void drawSurvey(dataset);
      window.setTimeout(() => { if (surveyDatasetRef.current === dataset) void drawSurvey(dataset); }, 300);
      window.setTimeout(() => { if (surveyDatasetRef.current === dataset) void drawSurvey(dataset); }, 1200);
    };
    const changeVisibility = (event: Event) => {
      const visibility = (event as CustomEvent<{ points: boolean; breaklines: boolean; contours: boolean }>).detail;
      setSurveyVisibility(visibility);
      void drawSurvey(surveyDatasetRef.current, visibility);
    };
    const refreshForArea = () => { if (surveyDatasetRef.current) void drawSurvey(surveyDatasetRef.current); };
    window.addEventListener("autovad:survey-data", loadSurvey);
    window.addEventListener("autovad:survey-visibility", changeVisibility);
    window.addEventListener("autovad:project-area", refreshForArea);
    try {
      const dataset = JSON.parse(sessionStorage.getItem("autovad-survey-data") || "null") as SurveyDataset | null;
      const visibility = JSON.parse(sessionStorage.getItem("autovad-survey-visibility") || "null") as { points: boolean; breaklines: boolean; contours: boolean } | null;
      if (visibility) setSurveyVisibility(visibility);
      if (dataset) window.setTimeout(() => loadSurvey(new CustomEvent("autovad:survey-data", { detail: dataset })), 50);
      if (visibility) window.setTimeout(() => changeVisibility(new CustomEvent("autovad:survey-visibility", { detail: visibility })), 100);
    } catch { /* no stored survey */ }
    return () => { window.removeEventListener("autovad:survey-data", loadSurvey); window.removeEventListener("autovad:survey-visibility", changeVisibility); window.removeEventListener("autovad:project-area", refreshForArea); };
  }, []);

  useEffect(() => {
    const showConcepts = (event: Event) => {
      const artifacts = (event as CustomEvent<ConceptArtifact[]>).detail || [];
      setConceptArtifacts(artifacts);
      conceptDataRef.current?.remove();
      conceptDataRef.current = null;
      if (!artifacts.length || !mapRef.current) return;
      void import("leaflet").then((module) => {
        const L = module.default || module;
        if (!mapRef.current) return;
        const layers = artifacts.map((artifact) => L.geoJSON(artifact.data, {
          style: (feature) => feature?.properties?.role === "station-tick" ? { color: "#ffffff", weight: feature.properties.major ? 3 : 1.5, opacity: 1 } : { color: artifact.color, weight: feature?.properties?.role === "centerline" ? 5 : 4, opacity: .95, fillColor: artifact.color, fillOpacity: .18 },
          pointToLayer: (feature, latlng) => feature?.properties?.role === "station-label" ? L.marker(latlng, { interactive: false, icon: L.divIcon({ className: "alignment-station-label", html: String(feature.properties.label), iconSize: [42, 18], iconAnchor: [21, 9] }) }) : L.circleMarker(latlng, { radius: 5, color: "#07100e", weight: 2, fillColor: artifact.color, fillOpacity: 1 }),
          onEachFeature: (feature, featureLayer) => { if (feature.properties?.role !== "station-label") featureLayer.bindTooltip(feature.properties?.role === "station-tick" ? `${feature.properties.major ? "Major" : "Minor"} station Â· ${feature.properties.station} ft` : `${artifact.label} Â· PRELIMINARY`); },
        }));
        conceptDataRef.current = L.layerGroup(layers).addTo(mapRef.current);
        areaRef.current?.bringToFront();
      });
    };
    window.addEventListener("autovad:concept-artifacts", showConcepts);
    try {
      const stored = JSON.parse(sessionStorage.getItem("autovad-concept-artifacts") || "[]") as ConceptArtifact[];
      if (stored.length) window.setTimeout(() => showConcepts(new CustomEvent("autovad:concept-artifacts", { detail: stored })), 0);
    } catch { /* no saved concept */ }
    return () => window.removeEventListener("autovad:concept-artifacts", showConcepts);
  }, []);

  useEffect(() => {
    const resize = window.setTimeout(() => mapRef.current?.invalidateSize(), 0);
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setFullMap(false); };
    window.addEventListener("keydown", closeOnEscape);
    return () => { window.clearTimeout(resize); window.removeEventListener("keydown", closeOnEscape); };
  }, [fullMap]);

  useEffect(() => {
    const showUtilities = (event: Event) => {
      const payload = (event as CustomEvent<UtilityQueryResult>).detail;
      setUtilityData(payload);
      const map = mapRef.current;
      if (!map) return;
      utilityDataRef.current?.remove();
      utilityDataRef.current = null;
      if (!payload?.layers.length) return;
      void import("leaflet").then((module) => {
        const L = module.default || module;
        if (!mapRef.current) return;
        const layers = payload.layers.map((layer) => L.geoJSON(layer.data, {
          style: { color: utilityColors[layer.kind], weight: 4, opacity: .95, dashArray: layer.kind === "unknown" ? "7 5" : undefined },
          pointToLayer: (_feature, latlng) => L.circleMarker(latlng, { radius: 5, color: "#07100e", weight: 2, fillColor: utilityColors[layer.kind], fillOpacity: 1 }),
          onEachFeature: (feature, featureLayer) => featureLayer.bindTooltip(`${layer.name}${feature.properties?.assettype ? ` Â· ${feature.properties.assettype}` : ""}`),
        }));
        utilityDataRef.current = L.layerGroup(layers).addTo(mapRef.current);
        areaRef.current?.bringToFront();
      });
    };
    window.addEventListener("autovad:utility-data", showUtilities);
    return () => window.removeEventListener("autovad:utility-data", showUtilities);
  }, []);

  useEffect(() => {
    if (!roadConceptRevision || !mapRef.current || !areaRef.current) return;
    void import("leaflet").then((module) => {
      const L = module.default || module;
      const map = mapRef.current;
      const area = areaRef.current;
      if (!map || !area) return;
      roadConceptRef.current?.remove();
      const bounds = area.getBounds();
      const west = bounds.getWest();
      const east = bounds.getEast();
      const south = bounds.getSouth();
      const north = bounds.getNorth();
      const width = east - west;
      const height = north - south;
      const bearing = (roadBearing ?? 68) * Math.PI / 180;
      const dx = Math.sin(bearing);
      const dy = Math.cos(bearing);
      const scale = .42 / Math.max(Math.abs(dx), Math.abs(dy), .01);
      const centerLat = south + height * .5;
      const centerLng = west + width * .5;
      const mapped = conceptArtifacts.find((artifact) => artifact.discipline === "road")?.data.features.find((feature) => feature.properties?.role === "centerline")?.geometry;
      const alignment: [number, number][] = mapped?.type === "LineString" ? mapped.coordinates.map((point) => [point[1], point[0]] as [number, number]) : [
        [centerLat - dy * height * scale, centerLng - dx * width * scale],
        [centerLat, centerLng],
        [centerLat + dy * height * scale, centerLng + dx * width * scale],
      ];
      const edgeOffset = height * .045;
      const northEdge = alignment.map(([lat, lng]) => [lat + edgeOffset, lng] as [number, number]);
      const southEdge = alignment.map(([lat, lng]) => [lat - edgeOffset, lng] as [number, number]);
      roadConceptRef.current = L.layerGroup([
        L.polyline(northEdge, { color: "#d9ff43", weight: 2, opacity: .9 }),
        L.polyline(southEdge, { color: "#d9ff43", weight: 2, opacity: .9 }),
        L.polyline(alignment, { color: "#ffffff", weight: 1, opacity: .9, dashArray: "10 8" }),
      ]).addTo(map);
    });
  }, [roadConceptRevision, roadBearing, conceptArtifacts]);

  const changeBasemap = async (type: Basemap) => {
    setBasemap(type);
    const map = mapRef.current;
    if (!map) return;
    const L = (await import("leaflet")).default;
    layerRef.current?.remove();
    layerRef.current = L.tileLayer(tileUrl(type), { attribution: sources[type].attribution, maxZoom: sources[type].maxzoom }).addTo(map);
    layerRef.current.bringToBack();
  };
  const updateLocation = (next: Location) => {
    setAutoCentered(false);
    setLocation(next);
    onLocationChange(next);
    markerRef.current?.setLatLng([next.lat, next.lng]);
    mapRef.current?.flyTo([next.lat, next.lng], 16);
  };
  const goToCoordinates = () => {
    const lat = Number(manualLat); const lng = Number(manualLng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng) || lat < -90 || lat > 90 || lng < -180 || lng > 180) { setCoordinateError("Enter valid WGS 84 latitude and longitude."); return; }
    setCoordinateError("");
    updateLocation({ lat, lng });
  };
  const zoomIn = () => mapRef.current?.zoomIn();
  const zoomOut = () => mapRef.current?.zoomOut();
  const resetView = () => mapRef.current?.flyTo([location.lat, location.lng], 16);
  const removeAreaHandles = () => {
    areaHandlesRef.current.forEach((handle) => handle.remove());
    areaHandlesRef.current = [];
  };
  const getAreaHandlePositions = (): Record<AreaHandle, [number, number]> | null => {
    if (!areaRef.current) return null;
    const bounds = areaRef.current.getBounds();
    const north = bounds.getNorth();
    const south = bounds.getSouth();
    const east = bounds.getEast();
    const west = bounds.getWest();
    const middleLat = (north + south) / 2;
    const middleLng = (east + west) / 2;
    return {
      nw: [north, west],
      n: [north, middleLng],
      ne: [north, east],
      e: [middleLat, east],
      se: [south, east],
      s: [south, middleLng],
      sw: [south, west],
      w: [middleLat, west],
    };
  };
  const syncAreaHandles = () => {
    const positions = getAreaHandlePositions();
    if (!positions) return;
    areaHandlesRef.current.forEach((handle, index) => handle.setLatLng(positions[areaHandleKinds[index]]));
  };
  const showAreaHandles = async () => {
    const map = mapRef.current;
    const positions = getAreaHandlePositions();
    if (!map || !positions) return;
    const module = await import("leaflet");
    const L = module.default || module;
    removeAreaHandles();
    areaHandlesRef.current = areaHandleKinds.map((kind) => {
      const handle = L.marker(positions[kind], {
        draggable: true,
        keyboard: false,
        zIndexOffset: 1000,
        icon: L.divIcon({
          className: `area-resize-handle handle-${kind}`,
          iconSize: [14, 14],
          iconAnchor: [7, 7],
        }),
      }).addTo(map);
      handle.on("drag", () => {
        if (!areaRef.current) return;
        const point = handle.getLatLng();
        const bounds = areaRef.current.getBounds();
        let north = bounds.getNorth();
        let south = bounds.getSouth();
        let east = bounds.getEast();
        let west = bounds.getWest();
        if (kind.includes("n")) north = point.lat;
        if (kind.includes("s")) south = point.lat;
        if (kind.includes("e")) east = point.lng;
        if (kind.includes("w")) west = point.lng;
        areaRef.current.setBounds([
          [Math.min(south, north), Math.min(west, east)],
          [Math.max(south, north), Math.max(west, east)],
        ]);
        syncAreaHandles();
      });
      handle.on("dragend", () => {
        if (!areaRef.current) return;
        const bounds = areaRef.current.getBounds();
        const center = bounds.getCenter();
        const next = { lat: center.lat, lng: center.lng };
        markerRef.current?.setLatLng(center);
        setLocation(next);
        onLocationChange(next);
        const projectArea = { north: bounds.getNorth(), south: bounds.getSouth(), east: bounds.getEast(), west: bounds.getWest() };
        if (activeAreaId) {
          const updated = projectAreasRef.current.map((area) => area.id === activeAreaId ? { ...area, ...projectArea } : area);
          projectAreasRef.current = updated; setProjectAreas(updated); localStorage.setItem("autovad-project-areas", JSON.stringify(updated));
        }
        onAreaSelected(next, projectArea);
        publishProjectArea(projectArea);
        syncAreaHandles();
      });
      return handle;
    });
  };
  const renderProjectAreas = async (areas: SavedProjectArea[], activeId: string | null) => {
    const map = mapRef.current; if (!map) return;
    const module = await import("leaflet"); const L = module.default || module;
    savedAreaLayersRef.current.forEach((layer) => layer.remove()); savedAreaLayersRef.current.clear();
    areaRef.current?.remove(); areaRef.current = null;
    areas.forEach((area) => {
      const active = area.id === activeId;
      const rectangle = L.rectangle([[area.south, area.west], [area.north, area.east]], { color: active ? "#d9ff43" : "#62a98d", weight: active ? 3 : 2, fillColor: active ? "#d9ff43" : "#62a98d", fillOpacity: active ? .16 : .08, dashArray: active ? "8 6" : "4 7" }).addTo(map);
      rectangle.bindTooltip(area.name, { sticky: true }); rectangle.on("click", () => void activateProjectArea(area.id));
      if (active) areaRef.current = rectangle; else savedAreaLayersRef.current.set(area.id, rectangle);
    });
  };
  const activateProjectArea = async (id: string) => {
    const areas = projectAreasRef.current; const area = areas.find((item) => item.id === id); if (!area) return;
    removeAreaHandles(); setActiveAreaId(id); setAreaSelected(true); setMapLocked(false);
    await renderProjectAreas(areas, id); await showAreaHandles();
    const next = { lat: (area.north + area.south) / 2, lng: (area.east + area.west) / 2 };
    setLocation(next); onLocationChange(next); onAreaSelected(next, area); publishProjectArea(area);
    mapRef.current?.fitBounds([[area.south, area.west], [area.north, area.east]], { padding: [70, 70] });
  };
  const startAreaSelection = () => {
    removeAreaHandles();
    roadConceptRef.current?.remove();
    roadConceptRef.current = null;
    void renderProjectAreas(projectAreas, null);
    setActiveAreaId(null);
    areaStartRef.current = null;
    selectingAreaRef.current = true;
    mapRef.current?.dragging.disable();
    mapRef.current?.scrollWheelZoom.enable();
    mapRef.current?.doubleClickZoom.enable();
    markerRef.current?.dragging?.enable();
    setSelectingArea(true);
    setAreaSelected(false);
    setMapLocked(false);
    localStorage.removeItem("autovad-project-area");
    window.dispatchEvent(new CustomEvent<ProjectArea | null>("autovad:project-area", { detail: null }));
  };
  const editAreaSelection = () => {
    if (!areaRef.current || mapLocked) return;
    void showAreaHandles();
  };
  const clearAreaSelection = () => {
    removeAreaHandles();
    areaRef.current?.remove();
    areaRef.current = null;
    areaStartRef.current = null;
    selectingAreaRef.current = false;
    mapRef.current?.dragging.enable();
    mapRef.current?.scrollWheelZoom.enable();
    mapRef.current?.doubleClickZoom.enable();
    markerRef.current?.dragging?.enable();
    setSelectingArea(false);
    setAreaSelected(false);
    setMapLocked(false);
    const remaining = activeAreaId ? projectAreas.filter((area) => area.id !== activeAreaId) : projectAreas;
    projectAreasRef.current = remaining; setProjectAreas(remaining); setActiveAreaId(null); localStorage.setItem("autovad-project-areas", JSON.stringify(remaining));
    if (remaining.length) void activateProjectArea(remaining[0].id);
    else { localStorage.removeItem("autovad-project-area"); window.dispatchEvent(new CustomEvent<ProjectArea | null>("autovad:project-area", { detail: null })); void renderProjectAreas([], null); }
  };
  const toggleMapLock = () => {
    const nextLocked = !mapLocked;
    const map = mapRef.current;
    map?.dragging.enable();
    map?.scrollWheelZoom.enable();
    map?.doubleClickZoom.enable();
    if (nextLocked) {
      markerRef.current?.dragging?.disable();
      removeAreaHandles();
    } else {
      markerRef.current?.dragging?.enable();
      void showAreaHandles();
    }
    setMapLocked(nextLocked);
  };
  const refreshElevationOverlays = async () => {
    lidarOverlayRef.current?.remove(); contourOverlayRef.current?.remove(); lidarOverlayRef.current = null; contourOverlayRef.current = null;
    const map = mapRef.current; const bounds = areaRef.current?.getBounds(); if (!map || !bounds || !showLidar && !showContours) { setElevationStatus(""); return; }
    const module = await import("leaflet"); const L = module.default || module; const box = [[bounds.getSouth(), bounds.getWest()], [bounds.getNorth(), bounds.getEast()]] as [[number, number], [number, number]];
    const endpoint = (type: "lidar" | "contours") => `/api/gis/elevation-overlay?type=${type}&west=${bounds.getWest()}&south=${bounds.getSouth()}&east=${bounds.getEast()}&north=${bounds.getNorth()}`;
    setElevationStatus("Loading USGS elevation data for selected area...");
    if (showLidar) { const overlay = L.imageOverlay(endpoint("lidar"), box, { opacity: .62, interactive: false, zIndex: 320 }).addTo(map); overlay.on("load", () => setElevationStatus("USGS 3DEP terrain Â· selected area only")); overlay.on("error", () => setElevationStatus("USGS terrain is unavailable for this area.")); lidarOverlayRef.current = overlay; }
    if (showContours) { const overlay = L.imageOverlay(endpoint("contours"), box, { opacity: .9, interactive: false, zIndex: 330 }).addTo(map); overlay.on("load", () => setElevationStatus("USGS contours Â· selected area only Â· NAVD88")); overlay.on("error", () => setElevationStatus("USGS contours are unavailable for this area.")); contourOverlayRef.current = overlay; }
    areaRef.current?.bringToFront();
  };
  const useCurrent = () => {
    if (!navigator.geolocation) return;
    setLocating(true);
    navigator.geolocation.getCurrentPosition((position) => {
      updateLocation({ lng: position.coords.longitude, lat: position.coords.latitude });
      setLocating(false);
    }, () => setLocating(false), { enableHighAccuracy: true, timeout: 10000 });
  };

  useEffect(() => {
    if (!mapRef.current || selectingArea || !projectAreas.length) return;
    const selected = activeAreaId || projectAreas[0].id;
    if (!activeAreaId) setActiveAreaId(selected);
    void renderProjectAreas(projectAreas, selected);
  }, [projectAreas, activeAreaId, selectingArea]);

  useEffect(() => { void refreshElevationOverlays(); }, [showLidar, showContours, activeAreaId, projectAreas]);

  return <div className={`${fullMap ? "geo-workspace full-map-view" : "geo-workspace"}${mapLocked ? " map-locked" : ""}`}>
    <div ref={host} className="geo-map" />
    {mapError && <div className="map-load-error">{mapError}</div>}
    {manualStatus && <div className="manual-command-hud"><span>ACTIVE COMMAND</span><b>{manualStatus}</b><small>CLICK: NEXT POINT Â· ENTER/DOUBLE-CLICK/RIGHT-CLICK: FINISH Â· ESC: CANCEL</small></div>}
    {fullMap && <div className="full-map-toolbar"><span>INTERACTIVE PROJECT MAP</span><b>DRAG TO PAN Â· WHEEL TO ZOOM Â· SELECT A PROJECT AREA</b><button type="button" onClick={() => setFullMap(false)}>RETURN TO WORKSPACE Ã—</button></div>}
    <div className="mouse-map-controls" aria-label="Mouse map controls">
      <button type="button" onClick={zoomIn} title="Zoom in with mouse">+</button>
      <button type="button" onClick={zoomOut} title="Zoom out with mouse">âˆ’</button>
      <button type="button" className="reset-map-view" onClick={resetView} title="Center map on the selected site">âŒ–</button>
    </div>
    {areaSelected && <div className="elevation-layer-controls"><span>FREE ELEVATION DATA Â· ACTIVE SITE ONLY</span><button type="button" className={showLidar ? "active" : ""} onClick={() => setShowLidar((value) => !value)}>3DEP TERRAIN {showLidar ? "ON" : "OFF"}</button><button type="button" className={showContours ? "active" : ""} onClick={() => setShowContours((value) => !value)}>CONTOURS {showContours ? "ON" : "OFF"}</button>{elevationStatus && <small>{elevationStatus}</small>}</div>}
    <button type="button" className={`area-panel-tab${areaPanelOpen ? " open" : ""}`} onClick={() => setAreaPanelOpen((value) => !value)} aria-expanded={areaPanelOpen} aria-controls="project-area-panel" title={areaPanelOpen ? "Collapse project area controls" : "Open project area controls"}>â–± <span>PROJECT AREA</span></button>
    {!areaPanelOpen && <button type="button" className="area-layers-tab" onClick={() => setAreaPanelOpen(true)} aria-label="Open project area layers">â–¤ <span>LAYERS</span></button>}
    {areaPanelOpen && <div id="project-area-panel" className={selectingArea ? "area-select-panel active" : "area-select-panel"}>
      <div className="area-panel-head"><span>PROJECT AREA</span><button type="button" onClick={() => setAreaPanelOpen(false)} aria-label="Close project area controls">Ã—</button></div>
      {projectAreas.length > 0 && !selectingArea && <label className="site-area-picker">ACTIVE SITE<select value={activeAreaId || ""} onChange={(event) => void activateProjectArea(event.target.value)}>{projectAreas.map((area) => <option key={area.id} value={area.id}>{area.name}</option>)}</select></label>}
      {!selectingArea && !areaSelected && <button type="button" className="start-area" onClick={startAreaSelection}>â–± SELECT PROJECT AREA</button>}
      {selectingArea && <><span>PRESS AND DRAG ACROSS THE PROJECT SITE</span><button type="button" onClick={clearAreaSelection}>CANCEL</button></>}
      {areaSelected && <><span>{mapLocked ? "â–£ PROJECT AREA LOCKED Â· MAP NAVIGATION ACTIVE" : "â–¡ AREA UNLOCKED Â· DRAG BORDER GRIPS TO RESIZE"}</span><button type="button" onClick={startAreaSelection}>+ NEW AREA</button>{!mapLocked && <button type="button" onClick={editAreaSelection}>EDIT SELECTED</button>}{!mapLocked && <button type="button" className="clear-area" onClick={clearAreaSelection}>DELETE SELECTED</button>}<button type="button" className={mapLocked ? "unlock-map" : "lock-map"} onClick={toggleMapLock}>{mapLocked ? "UNLOCK AREA" : "LOCK AREA"}</button></>}
    </div>}
    <div className="map-search-card"><span>PROJECT LOCATION</span><strong>{locating ? "Finding your approximate cityâ€¦" : autoCentered ? "Map centered near your city" : "Set the design origin"}</strong><p>{autoCentered ? "Pan and zoom to the project, then select its exact area." : "Select a project area, enter coordinates, or use your device location."}</p><div className="coordinate-inputs"><label>LATITUDE<input type="number" step="0.000001" value={manualLat} onChange={(e) => setManualLat(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") goToCoordinates(); }} /></label><label>LONGITUDE<input type="number" step="0.000001" value={manualLng} onChange={(e) => setManualLng(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") goToCoordinates(); }} /></label></div>{coordinateError && <small className="coordinate-error">{coordinateError}</small>}<button type="button" className="go-to-coordinates" onClick={goToCoordinates}>GO TO COORDINATES â†’</button><div className="location-actions"><button onClick={useCurrent}>âŒ– {locating ? "Locatingâ€¦" : "Use my location"}</button><button className="confirm-location" onClick={() => onConfirm(location)}>Use site location â†’</button></div></div>
    <div className="basemap-picker free-maps"><span>FREE BASEMAPS Â· NO KEY</span>{(Object.keys(sources) as Basemap[]).map((type) => <button className={basemap === type ? "active" : ""} onClick={() => changeBasemap(type)} key={type}><i className={`map-swatch ${type}`} />{sources[type].label}</button>)}<button type="button" className="open-map-screen" onClick={() => setFullMap(true)}>OPEN FULL MAP â†—</button></div>
    <div className="coordinate-readout"><span>WGS 84</span><b>{location.lat.toFixed(6)}Â°, {location.lng.toFixed(6)}Â°</b></div>
    {utilityData?.layers.length ? <div className="utility-legend"><span>ARCGIS UTILITY RECORDS Â· {utilityData.totalFeatures}</span>{utilityData.layers.map((layer) => <b key={`${layer.source}-${layer.name}`}><i style={{ background: utilityColors[layer.kind] }} />{layer.name}<small>{layer.featureCount}</small></b>)}<em>FIELD VERIFICATION REQUIRED</em></div> : null}
    {conceptArtifacts.length ? <div className="concept-legend"><span>LIVE AI CONCEPT Â· PRELIMINARY</span>{conceptArtifacts.map((artifact) => <b key={artifact.id}><i style={{ background: artifact.color }} />{artifact.label}</b>)}<em>NOT FOR CONSTRUCTION</em></div> : null}
    {surveyDataset ? <div className="survey-legend"><span>SURVEY SOURCE Â· STORED</span><strong>{surveyDataset.filename}</strong><b className={surveyVisibility.points ? "on" : "off"}>POINTS <i>{surveyDataset.points.length}</i></b><b className={surveyVisibility.breaklines ? "on" : "off"}>BREAKLINES <i>{surveyDataset.breaklines.length}</i></b><b className={surveyVisibility.contours ? "on" : "off"}>CONTOURS <i>{surveyDataset.contours.length}</i></b><em>{surveyDataset.transformed || surveyDataset.geographic ? surveyDataset.coordinateSystem : `${surveyDataset.coordinateSystem} Â· LOCAL DISPLAY UNTIL CRS CONFIRMED`}</em><div className="survey-crs-form">{!surveyDataset.geographic && <><label>EPSG CODE<input value={crsCode} onChange={(event) => setCrsCode(event.target.value)} placeholder="e.g. 2276" /></label><label>HORIZONTAL UNITS<select value={horizontalUnits} onChange={(event) => setHorizontalUnits(event.target.value)}><option>US survey feet</option><option>International feet</option><option>Meters</option></select></label><button type="button" disabled={!crsCode.trim() || applyingCrs} onClick={applySurveyCrs}>{applyingCrs ? "APPLYINGâ€¦" : "APPLY HORIZONTAL CRS"}</button>{crsStatus && <small>{crsStatus}</small>}</>}<span className="survey-crs-section">ELEVATION DATUM CONVERSION</span><label>SOURCE DATUM<select value={verticalDatum} onChange={(event) => setVerticalDatum(event.target.value)}><option value="">Select datum</option><option>NAVD88</option><option>NGVD29</option><option>EGM2008</option><option>EGM1996</option><option>IGLD85</option><option>MLLW</option><option>MLW</option><option>MTL</option><option>MHW</option><option>MHHW</option></select></label><label>TARGET DATUM<select value={targetVerticalDatum} onChange={(event) => setTargetVerticalDatum(event.target.value)}><option>NAVD88</option><option>NGVD29</option><option>EGM2008</option><option>EGM1996</option><option>IGLD85</option><option>MLLW</option><option>MLW</option><option>MTL</option><option>MHW</option><option>MHHW</option></select></label><label>VERTICAL UNITS<select value={verticalUnits} onChange={(event) => setVerticalUnits(event.target.value)}><option>US survey feet</option><option>International feet</option><option>Meters</option></select></label><label>NOAA REGION<select value={vdatumRegion} onChange={(event) => setVdatumRegion(event.target.value)}><option value="contiguous">Contiguous U.S.</option><option value="ak">Alaska</option><option value="as">American Samoa</option><option value="gcnmi">Guam / CNMI</option><option value="prvi">Puerto Rico / U.S. Virgin Islands</option></select></label><button type="button" disabled={!verticalDatum || verticalDatum === targetVerticalDatum || convertingVertical} onClick={convertVerticalDatum}>{convertingVertical ? "CONVERTINGâ€¦" : "CONVERT ELEVATIONS"}</button>{verticalStatus && <small>{verticalStatus}</small>}</div></div> : null}
  </div>;
}

```

---

## `app\design\Map3D.tsx`

```tsx
"use client";

import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
import type { Map as MapLibreMap } from "maplibre-gl";
import type { ProjectArea } from "./GeoMap";
import { utilityColors, type UtilityQueryResult } from "../../lib/gis";
import type { ConceptArtifact } from "../../lib/conceptDesign";
import type { SurveyDataset } from "../../lib/surveyXml";

type Location = { lat: number; lng: number };

const syncProjectArea = (map: MapLibreMap, bounds: ProjectArea | null) => {
  if (!map.isStyleLoaded()) return;
  if (!bounds) {
    if (map.getLayer("autovad-project-area-fill")) map.removeLayer("autovad-project-area-fill");
    if (map.getLayer("autovad-project-area-line")) map.removeLayer("autovad-project-area-line");
    if (map.getSource("autovad-project-area")) map.removeSource("autovad-project-area");
    return;
  }
  const coordinates = [[
    [bounds.west, bounds.north], [bounds.east, bounds.north],
    [bounds.east, bounds.south], [bounds.west, bounds.south],
    [bounds.west, bounds.north],
  ]];
  const data = { type: "Feature" as const, properties: {}, geometry: { type: "Polygon" as const, coordinates } };
  const source = map.getSource("autovad-project-area") as { setData?: (value: typeof data) => void } | undefined;
  if (source?.setData) source.setData(data);
  else {
    map.addSource("autovad-project-area", { type: "geojson", data });
    map.addLayer({ id: "autovad-project-area-fill", type: "fill", source: "autovad-project-area", paint: { "fill-color": "#d9ff43", "fill-opacity": .14 } });
    map.addLayer({ id: "autovad-project-area-line", type: "line", source: "autovad-project-area", paint: { "line-color": "#88a321", "line-width": 4, "line-dasharray": [2, 1.5] } });
  }
  map.fitBounds([[bounds.west, bounds.south], [bounds.east, bounds.north]], { padding: 90, duration: 900 });
  map.setPitch(62);
};

const syncUtilities = (map: MapLibreMap, payload: UtilityQueryResult | null) => {
  if (!map.isStyleLoaded()) return;
  const oldLayers = map.getStyle().layers.filter((layer) => layer.id.startsWith("autovad-utility-"));
  oldLayers.forEach((layer) => map.removeLayer(layer.id));
  oldLayers.forEach((layer) => { if (map.getSource(layer.id)) map.removeSource(layer.id); });
  payload?.layers.forEach((layer, index) => {
    const id = `autovad-utility-${index}`;
    map.addSource(id, { type: "geojson", data: layer.data });
    map.addLayer({ id, type: "line", source: id, filter: ["==", ["geometry-type"], "LineString"], paint: { "line-color": utilityColors[layer.kind], "line-width": 5, "line-opacity": .95 } });
    map.addLayer({ id: `${id}-points`, type: "circle", source: id, filter: ["==", ["geometry-type"], "Point"], paint: { "circle-color": utilityColors[layer.kind], "circle-radius": 6, "circle-stroke-color": "#07100e", "circle-stroke-width": 2 } });
  });
};

const syncConcepts = (map: MapLibreMap, artifacts: ConceptArtifact[]) => {
  if (!map.isStyleLoaded()) return;
  const oldLayers = map.getStyle().layers.filter((layer) => layer.id.startsWith("autovad-concept-"));
  oldLayers.forEach((layer) => map.removeLayer(layer.id));
  oldLayers.forEach((layer) => { if (map.getSource(layer.id)) map.removeSource(layer.id); });
  artifacts.forEach((artifact, index) => {
    const id = `autovad-concept-${index}`;
    map.addSource(id, { type: "geojson", data: artifact.data });
    map.addLayer({ id, type: "line", source: id, filter: ["==", ["geometry-type"], "LineString"], paint: { "line-color": ["case", ["==", ["get", "role"], "station-tick"], "#ffffff", artifact.color], "line-width": ["case", ["==", ["get", "role"], "station-tick"], ["case", ["get", "major"], 4, 2], 7], "line-opacity": .96 } });
    map.addLayer({ id: `${id}-points`, type: "circle", source: id, filter: ["==", ["geometry-type"], "Point"], paint: { "circle-color": artifact.color, "circle-radius": 7, "circle-stroke-color": "#07100e", "circle-stroke-width": 2 } });
    map.addLayer({ id: `${id}-station-labels`, type: "symbol", source: id, filter: ["==", ["get", "role"], "station-label"], layout: { "text-field": ["get", "label"], "text-size": 13, "text-offset": [0, 1.2], "text-allow-overlap": true }, paint: { "text-color": "#ffffff", "text-halo-color": "#07100e", "text-halo-width": 2 } });
    map.addLayer({ id: `${id}-areas`, type: "fill-extrusion", source: id, filter: ["==", ["geometry-type"], "Polygon"], paint: { "fill-extrusion-color": artifact.color, "fill-extrusion-opacity": .55, "fill-extrusion-height": 4, "fill-extrusion-base": 0 } });
  });
};

const syncSurvey = (map: MapLibreMap, dataset: SurveyDataset | null, visibility: { points: boolean; breaklines: boolean; contours: boolean }, area: ProjectArea | null) => {
  if (!map.isStyleLoaded()) return;
  const oldLayers = map.getStyle().layers.filter((layer) => layer.id.startsWith("autovad-survey-"));
  oldLayers.forEach((layer) => map.removeLayer(layer.id));
  oldLayers.forEach((layer) => { if (map.getSource(layer.id)) map.removeSource(layer.id); });
  if (!dataset || !dataset.bounds || !dataset.geographic && !dataset.transformed && !area) return;
  const convert = (northing: number, easting: number, wgs84?: [number, number]): [number, number] => {
    if (wgs84) return wgs84;
    if (dataset.geographic) return [easting, northing];
    const source = dataset.bounds!; const target = area!;
    const nx = (easting - source.minEasting) / Math.max(source.maxEasting - source.minEasting, 1);
    const ny = (northing - source.minNorthing) / Math.max(source.maxNorthing - source.minNorthing, 1);
    return [target.west + (target.east - target.west) * (.08 + nx * .84), target.south + (target.north - target.south) * (.08 + ny * .84)];
  };
  if (visibility.points) {
    const id = "autovad-survey-points";
    map.addSource(id, { type: "geojson", data: { type: "FeatureCollection", features: dataset.points.map((point) => ({ type: "Feature", properties: { id: point.id, elevation: point.convertedElevation ?? point.elevation, verticalDatum: dataset.elevationConversion?.targetDatum ?? dataset.verticalDatum }, geometry: { type: "Point", coordinates: convert(point.northing, point.easting, point.wgs84) } })) } });
    map.addLayer({ id, type: "circle", source: id, paint: { "circle-color": "#ffdf6b", "circle-radius": 4, "circle-stroke-color": "#07100e", "circle-stroke-width": 1 } });
  }
  const addLines = (id: string, lines: SurveyDataset["breaklines"], color: string) => {
    map.addSource(id, { type: "geojson", data: { type: "FeatureCollection", features: lines.map((line) => ({ type: "Feature", properties: { id: line.id }, geometry: { type: "LineString", coordinates: line.points.map((point, index) => convert(point[0], point[1], line.wgs84?.[index])) } })) } });
    map.addLayer({ id, type: "line", source: id, paint: { "line-color": color, "line-width": id.endsWith("contours") ? 1 : 3, "line-opacity": .88 } });
  };
  if (visibility.breaklines) addLines("autovad-survey-breaklines", dataset.breaklines, "#ff7d45");
  if (visibility.contours) addLines("autovad-survey-contours", dataset.contours, "#79dca9");
};

export default function Map3D({ location }: { location: Location | null }) {
  const host = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [projectArea, setProjectArea] = useState<ProjectArea | null>(() => {
    if (typeof window === "undefined") return null;
    try { return JSON.parse(localStorage.getItem("autovad-project-area") || "null") as ProjectArea | null; } catch { return null; }
  });
  const projectAreaRef = useRef(projectArea);
  const utilityDataRef = useRef<UtilityQueryResult | null>(null);
  const conceptDataRef = useRef<ConceptArtifact[]>([]);
  const surveyDataRef = useRef<SurveyDataset | null>(null);
  const surveyVisibilityRef = useRef({ points: true, breaklines: true, contours: true });
  projectAreaRef.current = projectArea;

  useEffect(() => {
    const update = (event: Event) => { const area = (event as CustomEvent<ProjectArea | null>).detail; projectAreaRef.current = area; setProjectArea(area); if (mapRef.current) syncProjectArea(mapRef.current, area); };
    const updateUtilities = (event: Event) => {
      utilityDataRef.current = (event as CustomEvent<UtilityQueryResult>).detail;
      if (mapRef.current) syncUtilities(mapRef.current, utilityDataRef.current);
    };
    const updateConcepts = (event: Event) => {
      conceptDataRef.current = (event as CustomEvent<ConceptArtifact[]>).detail || [];
      if (mapRef.current) syncConcepts(mapRef.current, conceptDataRef.current);
    };
    const updateSurvey = (event: Event) => {
      surveyDataRef.current = (event as CustomEvent<SurveyDataset>).detail;
      if (mapRef.current) syncSurvey(mapRef.current, surveyDataRef.current, surveyVisibilityRef.current, projectAreaRef.current);
    };
    const updateSurveyVisibility = (event: Event) => {
      surveyVisibilityRef.current = (event as CustomEvent<{ points: boolean; breaklines: boolean; contours: boolean }>).detail;
      if (mapRef.current) syncSurvey(mapRef.current, surveyDataRef.current, surveyVisibilityRef.current, projectAreaRef.current);
    };
    window.addEventListener("autovad:project-area", update);
    window.addEventListener("autovad:utility-data", updateUtilities);
    window.addEventListener("autovad:concept-artifacts", updateConcepts);
    window.addEventListener("autovad:survey-data", updateSurvey);
    window.addEventListener("autovad:survey-visibility", updateSurveyVisibility);
    try { utilityDataRef.current = JSON.parse(sessionStorage.getItem("autovad-utility-data") || "null") as UtilityQueryResult | null; } catch { utilityDataRef.current = null; }
    try { conceptDataRef.current = JSON.parse(sessionStorage.getItem("autovad-concept-artifacts") || "[]") as ConceptArtifact[]; } catch { conceptDataRef.current = []; }
    try { surveyDataRef.current = JSON.parse(sessionStorage.getItem("autovad-survey-data") || "null") as SurveyDataset | null; } catch { surveyDataRef.current = null; }
    try { surveyVisibilityRef.current = JSON.parse(sessionStorage.getItem("autovad-survey-visibility") || "null") || surveyVisibilityRef.current; } catch { /* defaults */ }
    return () => { window.removeEventListener("autovad:project-area", update); window.removeEventListener("autovad:utility-data", updateUtilities); window.removeEventListener("autovad:concept-artifacts", updateConcepts); window.removeEventListener("autovad:survey-data", updateSurvey); window.removeEventListener("autovad:survey-visibility", updateSurveyVisibility); };
  }, []);

  useEffect(() => {
    if (!host.current || mapRef.current) return;
    let active = true;
    void import("maplibre-gl").then((module) => {
      if (!active || !host.current) return;
      const maplibregl = module.default || module;
      const center: [number, number] = [location?.lng ?? -96.797, location?.lat ?? 32.777];
      const map = new maplibregl.Map({
        container: host.current,
        style: "https://tiles.openfreemap.org/styles/liberty",
        center,
        zoom: location ? 16 : 12,
        pitch: 62,
        bearing: -24,
        antialias: true,
        maxPitch: 85,
      });
      map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "bottom-right");
      map.addControl(new maplibregl.ScaleControl({ unit: "imperial" }), "bottom-left");
      map.on("load", () => {
        if (!map.getSource("autovad-terrain")) {
          map.addSource("autovad-terrain", { type: "raster-dem", tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"], tileSize: 256, encoding: "terrarium", maxzoom: 15 });
          map.setTerrain({ source: "autovad-terrain", exaggeration: 1.15 });
        }
        const buildingLayer = map.getStyle().layers.find((layer) => "source-layer" in layer && layer["source-layer"] === "building");
        if (buildingLayer && "source" in buildingLayer && typeof buildingLayer.source === "string" && !map.getLayer("autovad-3d-buildings")) {
          const firstLabel = map.getStyle().layers.find((layer) => layer.type === "symbol")?.id;
          map.addLayer({
            id: "autovad-3d-buildings",
            type: "fill-extrusion",
            source: buildingLayer.source,
            "source-layer": "building",
            minzoom: 14,
            paint: {
              "fill-extrusion-color": "#b7c5bd",
              "fill-extrusion-height": ["coalesce", ["get", "render_height"], ["get", "height"], 8],
              "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], ["get", "min_height"], 0],
              "fill-extrusion-opacity": .72,
            },
          }, firstLabel);
        }
        if (location) {
          new maplibregl.Marker({ color: "#d9ff43", scale: .75 }).setLngLat([location.lng, location.lat]).addTo(map);
        }
        syncProjectArea(map, projectAreaRef.current);
        syncUtilities(map, utilityDataRef.current);
        syncConcepts(map, conceptDataRef.current);
        syncSurvey(map, surveyDataRef.current, surveyVisibilityRef.current, projectAreaRef.current);
      });
      mapRef.current = map;
    });
    return () => { active = false; mapRef.current?.remove(); mapRef.current = null; };
  }, []);

  useEffect(() => {
    if (!mapRef.current) return;
    if (projectArea) { syncProjectArea(mapRef.current, projectArea); syncSurvey(mapRef.current, surveyDataRef.current, surveyVisibilityRef.current, projectArea); }
    else if (location) mapRef.current.flyTo({ center: [location.lng, location.lat], zoom: 16, pitch: 62, essential: true });
  }, [location, projectArea]);

  return <div ref={host} className="map-3d" aria-label="Interactive three-dimensional project map" />;
}

```

---

## `app\globals.css`

```css
@import "tailwindcss";
@import "./launch.css";
@import "./future.css";
@import "./credits.css";
@import "./credit-buy.css";
@import "./marketing.css";

:root{--ink:#07100e;--paper:#f3f5ed;--acid:#d9ff43;--mint:#85ffd0;--muted:#a8b0a9;--line:rgba(255,255,255,.12)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--ink);color:#f4f6ef;font-family:Arial,Helvetica,sans-serif}button,a{font:inherit}button{cursor:pointer}.app-shell{overflow:hidden}.topbar{height:82px;display:flex;align-items:center;justify-content:space-between;padding:0 4.5vw;border-bottom:1px solid var(--line);position:relative;z-index:20}.brand{display:flex;align-items:center;gap:12px;color:white;text-decoration:none;font-weight:900;letter-spacing:-.03em;font-size:20px}.brand>span:last-child>span{color:var(--acid)}.brand-mark{width:29px;height:27px;display:flex;gap:3px;align-items:flex-end;transform:skew(-12deg)}.brand-mark i{display:block;width:7px;background:var(--acid)}.brand-mark i:nth-child(1){height:16px}.brand-mark i:nth-child(2){height:25px}.brand-mark i:nth-child(3){height:20px}.nav-links{display:flex;gap:38px}.nav-links a{color:#aeb8b2;text-decoration:none;font-size:13px}.nav-links a:hover{color:white}.nav-actions{display:flex;align-items:center;gap:22px}.text-button{background:none;border:0;color:#cdd4ce;font-size:13px}.outline-button{border:1px solid rgba(217,255,67,.5);background:rgba(217,255,67,.04);color:var(--acid);padding:12px 17px;font-size:12px;font-weight:700;letter-spacing:.04em}.outline-button span,.solid-button span{padding-left:14px}.hero{min-height:740px;position:relative;display:grid;grid-template-columns:47% 53%;padding:85px 4.5vw 80px}.grid-lines{position:absolute;inset:0;background-image:linear-gradient(rgba(155,255,207,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(155,255,207,.045) 1px,transparent 1px);background-size:44px 44px;mask-image:linear-gradient(to bottom,black,transparent 90%)}.grid-lines:after{content:"";position:absolute;inset:0;background:radial-gradient(circle at 75% 40%,rgba(72,171,135,.16),transparent 32%)}.hero-copy{position:relative;z-index:2}.eyebrow,.section-kicker{font-family:monospace;font-size:11px;letter-spacing:.15em;color:var(--acid);font-weight:700}.pulse{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--acid);box-shadow:0 0 12px var(--acid);margin-right:9px}.hero h1{font-size:clamp(58px,6vw,96px);line-height:.88;letter-spacing:-.07em;margin:38px 0 30px;max-width:700px}.hero h1 em{font-style:normal;color:transparent;-webkit-text-stroke:1px #c8d0c9}.lede{color:#aab4ad;font-size:17px;line-height:1.65;max-width:560px;margin-bottom:38px}.dropzone{width:min(620px,100%);min-height:92px;border:1px dashed rgba(217,255,67,.5);display:flex;align-items:center;gap:18px;padding:15px 16px;background:rgba(217,255,67,.035);transition:.2s}.dropzone.dragging{background:rgba(217,255,67,.12);transform:translateY(-2px)}.dropzone.has-file{border-style:solid}.dropzone input{display:none}.upload-icon{width:55px;height:55px;border:1px solid rgba(217,255,67,.35);display:grid;place-items:center;color:var(--acid);font-size:24px;background:rgba(217,255,67,.05)}.dropzone>div:nth-child(3){display:flex;flex-direction:column;gap:8px;min-width:0}.dropzone strong{font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:320px}.dropzone small{color:#76827c;font-family:monospace;font-size:10px}.dropzone button{margin-left:auto;background:var(--acid);border:0;padding:13px 18px;color:#11170c;font-size:11px;font-weight:800;text-transform:uppercase}.trust-line{display:flex;gap:24px;color:#68736d;font-family:monospace;font-size:9px;letter-spacing:.06em;margin-top:21px}.product-stage{position:relative;min-height:530px;z-index:2;perspective:1100px}.stage-orbit{position:absolute;border:1px solid rgba(133,255,208,.12);border-radius:50%;left:10%;top:-20%;width:650px;height:650px;transform:rotateX(65deg)}.orbit-two{width:480px;height:480px;left:22%;top:-5%}.sheet-stack,.plan-sheet{position:absolute;width:385px;height:485px;background:#e7ede4;left:21%;top:18px;transform:rotateY(-8deg) rotateZ(5deg);box-shadow:-24px 25px 70px rgba(0,0,0,.38)}.sheet-back{transform:translate(27px,25px) rotateY(-8deg) rotateZ(9deg);opacity:.15}.sheet-mid{transform:translate(14px,12px) rotateY(-8deg) rotateZ(7deg);opacity:.35}.plan-sheet{padding:18px;color:#14231e;background:#e9eee7}.sheet-head,.sheet-foot{display:flex;justify-content:space-between;align-items:center;font:8px monospace;letter-spacing:.08em;border-bottom:1px solid #708179;padding-bottom:8px}.sheet-head b{font-size:18px}.sheet-foot{border-top:1px solid #708179;border-bottom:0;padding-top:8px}.plan-drawing{height:410px;position:relative;overflow:hidden;background:repeating-linear-gradient(0deg,transparent,transparent 27px,rgba(9,59,45,.06) 28px),repeating-linear-gradient(90deg,transparent,transparent 27px,rgba(9,59,45,.06) 28px)}.road{position:absolute;border:17px double rgba(25,67,56,.28);width:550px;height:95px;transform:rotate(-40deg);left:-140px;top:150px}.road-b{transform:rotate(66deg);left:80px;top:110px;width:360px}.contour{position:absolute;border:1px solid rgba(20,78,60,.28);border-radius:44%;width:260px;height:110px;left:-20px;top:40px;transform:rotate(-12deg)}.c2{width:230px;height:90px;left:0;top:50px}.c3{width:180px;height:65px;left:25px;top:63px}.scan-line{position:absolute;left:0;right:0;height:2px;top:55%;background:var(--acid);box-shadow:0 0 15px var(--acid);animation:scan 4s ease-in-out infinite}.measure{position:absolute;border-top:2px solid #4ed6a2;color:#0a5b41;font:8px monospace}.measure:before,.measure:after{content:"";position:absolute;top:-4px;width:6px;height:6px;border-radius:50%;background:#20ac7b}.measure:before{left:0}.measure:after{right:0}.measure span{position:absolute;top:-17px;left:40%;white-space:nowrap;background:#d9ff43;padding:2px 4px}.m1{width:150px;left:50px;top:260px;transform:rotate(-39deg)}.m2{width:115px;left:210px;top:165px;transform:rotate(65deg)}.node{position:absolute;width:10px;height:10px;border:2px solid #0ea875;background:#d9ff43;box-shadow:0 0 0 5px rgba(17,187,128,.16)}.n1{left:65px;top:300px}.n2{left:190px;top:195px}.n3{left:280px;top:300px}.analysis-card{position:absolute;right:0;bottom:52px;width:225px;padding:19px;background:rgba(7,17,14,.93);border:1px solid rgba(217,255,67,.35);box-shadow:0 20px 60px rgba(0,0,0,.4)}.card-label{font:9px monospace;color:var(--acid);letter-spacing:.12em}.metric{display:flex;align-items:end;gap:13px;margin:17px 0}.metric strong{font-size:42px;line-height:1}.metric span{font:8px monospace;color:#89948e;line-height:1.5}.progress{height:3px;background:#29342f}.progress i{display:block;width:86%;height:100%;background:var(--acid);box-shadow:0 0 9px var(--acid)}.card-foot{display:flex;justify-content:space-between;margin-top:12px;font:8px monospace;color:#89948e}.card-foot b{color:white}.tag{position:absolute;background:#11221c;border:1px solid rgba(133,255,208,.28);padding:8px 10px;font:8px monospace;letter-spacing:.08em}.tag i{display:inline-block;width:5px;height:5px;background:var(--mint);margin-right:6px}.tag-one{left:8%;top:120px}.tag-two{right:1%;top:210px}@keyframes scan{0%,100%{top:15%;opacity:.3}50%{top:85%;opacity:1}}
.workflow{background:var(--paper);color:#0d1713;padding:100px 5vw}.section-kicker{color:#5e6b63}.section-heading{display:grid;grid-template-columns:1fr 1fr;gap:12vw;align-items:end;margin:26px 0 70px}.section-heading h2,.output h2,.closing h2{font-size:clamp(42px,5vw,72px);line-height:.98;letter-spacing:-.055em;margin:0}.section-heading h2 span{color:#8a938e}.section-heading p,.output-copy>p{color:#68736d;line-height:1.7;font-size:15px;max-width:490px}.steps{display:grid;grid-template-columns:repeat(3,1fr);border-top:1px solid #c8cec7}.steps article{position:relative;padding:35px 44px 15px 0;min-height:245px}.step-num{font:10px monospace;color:#7c8780}.step-icon{font-size:38px;margin:29px 0;color:#263c33}.steps h3{font-size:18px;margin:0 0 12px}.steps p{font-size:13px;line-height:1.65;color:#6d7871;max-width:330px}.connector{position:absolute;right:30px;top:91px;width:42px;height:1px;background:#9eaaa3}.connector:after{content:"";position:absolute;right:0;top:-3px;border-left:5px solid #9eaaa3;border-top:3px solid transparent;border-bottom:3px solid transparent}.output{padding:120px 5vw;display:grid;grid-template-columns:35% 65%;gap:5vw;background:#0a1411}.output-copy{padding-top:25px}.output-copy h2{margin:27px 0;color:white}.output-copy ul{padding:0;list-style:none;margin:35px 0}.output-copy li{padding:10px 0;color:#b6c0ba;font-size:13px}.output-copy li span{color:var(--acid);margin-right:12px}.solid-button{background:var(--acid);border:0;padding:17px 20px;color:#12190c;font-size:11px;font-weight:900;text-transform:uppercase;letter-spacing:.04em}.bid-window{border:1px solid #31423b;background:#0d1915;box-shadow:0 40px 100px rgba(0,0,0,.3)}.window-bar{height:48px;background:#15231e;display:grid;grid-template-columns:1fr 1fr 1fr;align-items:center;padding:0 17px;font:8px monospace;color:#69756f}.window-bar div{display:flex;gap:5px}.window-bar i{width:7px;height:7px;border-radius:50%;background:#46534c}.window-bar b{text-align:right;color:var(--acid)}.project-line{display:grid;grid-template-columns:2fr 1fr .7fr;padding:25px;border-bottom:1px solid #26362f;gap:20px}.project-line div{display:flex;flex-direction:column;gap:8px}.project-line small{font:8px monospace;color:#68756e}.project-line strong{font-size:12px}.project-line .ready{color:var(--mint);font:9px monospace}.table-head,.table-row{display:grid;grid-template-columns:.9fr 2.1fr .8fr .6fr .8fr;align-items:center;padding:0 25px}.table-head{height:39px;background:#101e19;font:8px monospace;color:#5f6c65}.table-row{min-height:62px;border-top:1px solid #21312a;font:10px monospace;color:#8e9b94}.table-row strong{font-family:Arial;font-size:12px;color:#dce3dd}.table-row span:last-child{color:var(--mint)}.table-row span:last-child i{display:inline-block;width:4px;height:4px;background:var(--mint);border-radius:50%;margin-right:7px}.window-summary{display:flex;gap:26px;justify-content:flex-end;padding:20px 25px;border-top:1px solid #2a3a33;font:8px monospace;color:#68756e}.window-summary b{color:var(--acid);margin-left:auto}.closing{padding:100px 5vw;background:var(--acid);color:#0b130e;display:flex;justify-content:space-between;align-items:end}.closing .eyebrow{color:#415017;margin-bottom:25px}.light{background:#0b130e;color:white;padding:19px 26px}footer{height:105px;padding:0 5vw;display:grid;grid-template-columns:1fr 1fr 1fr;align-items:center;color:#69746e;font-size:10px}footer p{text-align:center}footer>span{text-align:right;font-family:monospace}
@media(max-width:1000px){.nav-links{display:none}.hero{grid-template-columns:1fr;padding-top:65px}.product-stage{margin-top:80px}.product-stage{min-height:600px}.section-heading{gap:4vw}.output{grid-template-columns:1fr}.output-copy{max-width:600px}.bid-window{margin-top:35px}}
@media(max-width:650px){.topbar{padding:0 20px}.nav-actions .text-button{display:none}.outline-button{padding:10px}.hero{padding:55px 20px 70px}.hero h1{font-size:57px}.lede{font-size:15px}.dropzone{align-items:flex-start;flex-wrap:wrap}.dropzone button{margin-left:73px}.trust-line{flex-wrap:wrap;gap:10px}.product-stage{transform:scale(.78);transform-origin:top left;width:128%;min-height:500px}.plan-sheet,.sheet-stack{left:12%}.analysis-card{right:4%}.workflow,.output,.closing{padding:75px 20px}.section-heading{grid-template-columns:1fr;margin-bottom:45px}.steps{grid-template-columns:1fr}.steps article{min-height:auto;border-bottom:1px solid #d2d7d1;padding-bottom:35px}.connector{display:none}.bid-window{overflow-x:auto}.window-bar,.project-line,.table-head,.table-row,.window-summary{min-width:700px}.closing{display:block}.closing button{margin-top:40px}footer{grid-template-columns:1fr 1fr;height:auto;padding:35px 20px}footer p{display:none}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}.scan-line{animation:none}}

.dropzone button:disabled{opacity:.55;cursor:wait}.processing-banner,.error-banner{width:min(620px,100%);display:flex;gap:14px;align-items:center;padding:16px 18px;margin-top:12px;border:1px solid rgba(133,255,208,.25);background:#0d1c17}.processing-banner div{display:flex;flex-direction:column;gap:5px}.processing-banner strong,.error-banner strong{font-size:12px}.processing-banner small{font:9px monospace;color:#85918a;line-height:1.5}.processing-spinner{width:22px;height:22px;border:2px solid rgba(217,255,67,.2);border-top-color:var(--acid);border-radius:50%;animation:spin 1s linear infinite;flex:0 0 auto}.error-banner{border-color:rgba(255,106,106,.35);align-items:flex-start;flex-direction:column;color:#ffb1a8}.error-banner span{font-size:11px;color:#b98e89}.error-banner button{background:none;border:0;padding:0;color:var(--acid);font:9px monospace;text-transform:uppercase}.result-panel{width:min(760px,100%);margin-top:16px;border:1px solid rgba(217,255,67,.32);background:#0b1713;box-shadow:0 25px 70px rgba(0,0,0,.35)}.result-title{display:flex;justify-content:space-between;padding:20px;border-bottom:1px solid #23332c;gap:20px}.result-title small{font:8px monospace;color:var(--acid)}.result-title h3{font-size:20px;margin:7px 0}.result-title p{font-size:11px!important;color:#8b9690!important;margin:0!important;line-height:1.5!important;max-width:520px!important}.result-title>div:last-child{text-align:right}.result-title>div:last-child strong{display:block;font-size:28px;color:var(--acid)}.result-title>div:last-child span{font:8px monospace;color:#78847e}.result-row{display:grid;grid-template-columns:.65fr 2.2fr .85fr .65fr .85fr;gap:10px;align-items:center;min-height:46px;padding:7px 14px;border-top:1px solid #1c2b25;font:8px monospace;color:#839089}.result-row b{display:block;color:#e2e8e3;font:10px Arial;margin-bottom:3px}.result-row small{display:block;color:#66736c;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:270px}.result-head{min-height:28px;background:#10201a;color:#66736c}.result-row .confident{color:var(--mint)}.result-row .review{color:#ffc36a}.more-items{text-align:center;padding:12px;border-top:1px solid #26362f;color:#87948c;font:8px monospace}@keyframes spin{to{transform:rotate(360deg)}}
.template-upload{width:min(620px,100%);display:flex;align-items:center;gap:16px;margin-top:10px;padding:13px 16px;border:1px solid #26372f;background:rgba(7,20,15,.82)}.template-upload.has-template{border-color:rgba(133,255,208,.42);background:rgba(133,255,208,.05)}.template-upload input{display:none}.template-upload>div{display:flex;flex-direction:column;gap:4px;min-width:0}.template-upload small{font:8px monospace;color:var(--acid);letter-spacing:.08em}.template-upload strong{font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.template-upload span{font:9px monospace;color:#748078}.template-upload button{margin-left:auto;flex:0 0 auto;border:1px solid rgba(217,255,67,.35);background:transparent;color:var(--acid);padding:9px 12px;font:8px monospace;text-transform:uppercase}.template-applied{padding:10px 14px;border-top:1px solid #26362f;background:rgba(133,255,208,.06);color:#aee8d1;font:9px monospace}.template-applied span{color:var(--acid);margin-right:6px}

@media(max-width:650px){.result-panel{width:100%;overflow-x:auto}.result-title,.result-table,.more-items{min-width:650px}}

.new-pill{font:7px monospace;color:#07100e;background:var(--acid);padding:2px 4px;margin-left:3px}.studio-shell{height:100vh;min-height:700px;background:#07100e;color:#eaf0eb;overflow:hidden}.studio-topbar{height:62px;display:flex;align-items:center;border-bottom:1px solid #24322c;background:#0b1512;padding:0 16px;gap:28px}.studio-topbar .brand{font-size:16px}.studio-topbar .brand-mark{transform:scale(.75) skew(-12deg);margin-right:-3px}.product-tabs{height:100%;display:flex}.product-tabs a{position:relative;display:flex;align-items:center;gap:6px;padding:0 18px;color:#718078;text-decoration:none;font:9px monospace;letter-spacing:.08em;border-left:1px solid #1c2924}.product-tabs a:last-child{border-right:1px solid #1c2924}.product-tabs a.active{color:var(--acid);background:#0e1d18}.product-tabs a.active:after{content:"";position:absolute;left:0;right:0;bottom:0;height:2px;background:var(--acid)}.product-tabs b{font-size:6px;border:1px solid #729127;padding:2px 3px}.project-name{display:flex;align-items:center;gap:10px;margin:auto}.project-name span{font:7px monospace;color:#647169}.project-name strong{font-size:11px}.project-name i{font-style:normal;color:#68756e}.studio-actions{display:flex;gap:7px}.studio-actions button{border:1px solid #2a3b33;background:#101e19;color:#9aa69f;padding:9px 12px;font:8px monospace}.studio-actions .pro-button{color:#16200d;background:var(--acid);border-color:var(--acid);font-weight:bold}.studio-body{height:calc(100vh - 62px);display:grid;grid-template-columns:48px 1fr 390px}.tool-rail{border-right:1px solid #24332c;background:#0a1411;display:flex;flex-direction:column;justify-content:space-between;align-items:center;padding:10px 0}.tool-group,.tool-bottom{display:flex;flex-direction:column;gap:6px}.tool-rail button{width:34px;height:34px;border:0;background:transparent;color:#718078;font-size:16px}.tool-rail button:hover,.tool-rail button.selected{background:#1a2b24;color:var(--acid);box-shadow:inset 2px 0 var(--acid)}.design-canvas{position:relative;overflow:hidden;background-color:#0b1713;background-image:linear-gradient(rgba(109,153,135,.08) 1px,transparent 1px),linear-gradient(90deg,rgba(109,153,135,.08) 1px,transparent 1px),linear-gradient(rgba(109,153,135,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(109,153,135,.035) 1px,transparent 1px);background-size:100px 100px,100px 100px,20px 20px,20px 20px}.canvas-status{position:absolute;top:15px;left:16px;z-index:3;display:flex;gap:16px;font:7px monospace;color:#596961}.canvas-status span{color:var(--mint)}.canvas-status span i{display:inline-block;width:5px;height:5px;border-radius:50%;background:var(--mint);margin-right:5px}.north-arrow{position:absolute;left:20px;bottom:50px;display:flex;flex-direction:column;text-align:center;font:9px monospace;color:#718078}.north-arrow span{font-size:28px;color:#a5b1aa}.cad-site{position:absolute;inset:8% 7% 7% 6%;opacity:.42;transform:rotate(-5deg)}.boundary{position:absolute;inset:9% 12%;border:1px solid #69c9a3;clip-path:polygon(8% 0,85% 5%,100% 34%,92% 95%,28% 100%,0 65%)}.boundary:before{content:"";position:absolute;inset:15px;border:1px dashed #589279;clip-path:inherit}.boundary span{position:absolute;left:46%;top:45%;font:8px monospace;color:#81c7ab}.road-center{position:absolute;height:36px;border-top:1px solid #95cdb5;border-bottom:1px solid #95cdb5}.r-a{width:80%;left:3%;top:62%;transform:rotate(-24deg)}.r-a:after,.r-b:after{content:"";position:absolute;left:0;right:0;top:17px;border-top:1px dashed #7cb79f}.r-b{width:55%;right:7%;top:40%;transform:rotate(58deg)}.pad{position:absolute;width:34%;height:22%;left:35%;top:30%;border:2px solid var(--acid);background:rgba(217,255,67,.05);transform:rotate(4deg);display:grid;place-content:center;text-align:center;font:8px monospace;color:var(--acid)}.pad span{font-size:7px;margin-top:5px}.pond{position:absolute;width:25%;height:15%;right:8%;bottom:13%;border:1px solid #50b88f;border-radius:50% 40% 55% 42%;display:grid;place-items:center;font:7px monospace;color:#72cfab}.contours{position:absolute;inset:0}.contours i{position:absolute;border:1px solid #3f755f;border-radius:49% 44% 55% 46%;width:50%;height:28%;left:8%;top:10%}.contours i:nth-child(2){inset:14% auto auto 12%;width:42%;height:21%}.contours i:nth-child(3){left:5%;top:70%;width:45%;height:20%}.contours i:nth-child(4){left:8%;top:73%;width:38%;height:14%}.contours i:nth-child(5){left:67%;top:5%;width:22%;height:19%}.dimension{position:absolute;border-top:1px solid #7eb39d;padding-top:4px;font:7px monospace;color:#7eb39d}.d-a{width:30%;left:34%;top:26%;text-align:center}.d-b{width:18%;left:68%;top:43%;transform:rotate(88deg);text-align:center}.survey-point{position:absolute;color:var(--acid);font-size:8px}.survey-point span{font:6px monospace;color:#8ca198}.p-a{left:18%;top:20%}.p-b{right:16%;top:67%}.p-c{left:29%;bottom:15%}.canvas-empty{position:absolute;left:50%;top:54%;transform:translate(-50%,-50%);display:flex;gap:12px;align-items:center;background:rgba(7,16,14,.82);border:1px solid #2d4339;padding:16px 20px;box-shadow:0 20px 50px rgba(0,0,0,.3)}.ai-spark{color:var(--acid);font-size:20px}.canvas-empty div{display:flex;flex-direction:column;gap:5px}.canvas-empty strong{font-size:11px}.canvas-empty small{font:7px monospace;color:#6c7b73}.view-cube{position:absolute;right:18px;top:20px;width:64px;height:64px;border:1px solid #3a4c44;transform:rotate(-7deg);font:6px monospace;color:#819088}.view-cube div{height:38px;display:grid;place-items:center;border-bottom:1px solid #3a4c44;background:#14231d}.view-cube span,.view-cube i{position:absolute;bottom:5px;font-style:normal}.view-cube span{left:6px}.view-cube i{right:5px}.canvas-bottom{position:absolute;bottom:0;left:0;right:0;height:31px;border-top:1px solid #26362f;background:#0a1411;display:flex;align-items:center;padding:0 10px;gap:10px;font:7px monospace;color:#5f6e66}.canvas-bottom>span{height:31px;display:grid;place-items:center;color:var(--acid);border-bottom:2px solid var(--acid)}.canvas-bottom button{border:0;background:transparent;color:#829188;font:8px monospace}.canvas-bottom div{flex:1}.copilot-panel{border-left:1px solid #2a3a33;background:#0d1814;display:flex;flex-direction:column;min-width:0}.copilot-head{height:64px;border-bottom:1px solid #26362f;display:flex;align-items:center;justify-content:space-between;padding:0 16px}.copilot-head>div{display:flex;align-items:center;gap:10px}.copilot-head strong{display:block;font-size:12px}.copilot-head small{font:6px monospace;color:var(--mint)}.copilot-head small i{display:inline-block;width:5px;height:5px;border-radius:50%;background:var(--mint);margin-right:5px}.copilot-head button{border:0;background:none;color:#647168}.design-progress{padding:12px 16px;border-bottom:1px solid #25352e}.design-progress>div:first-child{display:flex;justify-content:space-between;font:7px monospace;color:#78877f}.design-progress b{color:var(--acid)}.readiness-bar{height:2px;background:#28362f;margin-top:8px}.readiness-bar i{display:block;height:100%;background:var(--acid);box-shadow:0 0 7px var(--acid);transition:.4s}.chat-stream{flex:1;overflow-y:auto;padding:18px 16px}.phase-marker{display:flex;align-items:center;gap:10px;margin-bottom:18px}.phase-marker span{font:6px monospace;background:#25382f;color:var(--mint);padding:4px 6px}.phase-marker b{font-size:9px;color:#8c9992}.chat-message{display:flex;gap:9px;margin-bottom:14px}.chat-message p{font-size:11px;line-height:1.6;margin:0;color:#b7c1bb}.chat-message.user{justify-content:flex-end}.chat-message.user p{background:#1d3028;padding:10px 12px;border-radius:8px 8px 2px 8px;max-width:85%;color:#e1e9e4}.ai-avatar{width:25px;height:25px;display:grid;place-items:center;border:1px solid #395044;background:#12251d;color:var(--acid);font-size:12px;flex:0 0 auto}.file-stack{border:1px solid #293d34;background:#101f1a;margin:16px 0}.file-stack-head{display:flex;justify-content:space-between;padding:9px 10px;border-bottom:1px solid #293d34;font:6px monospace;color:#68776f}.file-stack-head b{color:var(--mint)}.source-file{display:flex;align-items:center;gap:9px;padding:9px 10px;border-top:1px solid #1e3028}.source-file>span{width:27px;height:30px;display:grid;place-items:center;border:1px solid #41554c;font:6px monospace;color:var(--acid)}.source-file div{min-width:0;flex:1}.source-file strong,.source-file small{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.source-file strong{font-size:9px}.source-file small{font:6px monospace;color:#617068;margin-top:4px}.source-file button{border:0;background:none;color:#617068}.intake-checks{padding:12px 16px;border-top:1px solid #26362f;background:#0b1713}.intake-checks>span{font:6px monospace;color:#617067}.intake-checks>div{display:flex;gap:9px;align-items:center;margin-top:10px}.intake-checks i{width:20px;height:20px;border-radius:50%;border:1px solid #40534a;display:grid;place-items:center;font:7px monospace;color:#6e7e75}.intake-checks .done i{border-color:var(--acid);color:#17200f;background:var(--acid)}.intake-checks p{margin:0}.intake-checks b,.intake-checks small{display:block}.intake-checks b{font-size:8px}.intake-checks small{font:6px monospace;color:#617067;margin-top:2px}.chat-compose{margin:0 12px 12px;border:1px solid #34483f;background:#111f1a}.upload-strip{height:34px;display:flex;align-items:center;justify-content:space-between;padding:0 9px;border-bottom:1px solid #2c4036}.upload-strip button{border:0;background:none;color:var(--acid);font:8px monospace}.upload-strip span{font:6px monospace;color:#53625b}.upload-strip input{display:none}.chat-compose textarea{width:100%;resize:none;background:transparent;border:0;outline:0;color:white;padding:11px;font-size:11px;line-height:1.5}.chat-compose textarea::placeholder{color:#58665f}.compose-foot{display:flex;align-items:center;justify-content:space-between;padding:4px 8px 8px}.compose-foot span{font:6px monospace;color:#53625b}.compose-foot button{width:27px;height:27px;border:0;border-radius:50%;background:var(--acid);color:#10170d;font-weight:bold}.compose-foot button:disabled{opacity:.3}.plan-modal{position:fixed;z-index:100;inset:0;background:rgba(2,7,5,.82);backdrop-filter:blur(10px);display:grid;place-items:center;padding:20px}.plan-card{position:relative;width:min(510px,100%);background:#f1f4eb;color:#111a15;padding:42px;box-shadow:0 40px 100px #000}.modal-close{position:absolute;right:16px;top:14px;background:none;border:0;font-size:22px}.plan-kicker{font:8px monospace;letter-spacing:.14em;color:#59655e}.plan-card h2{font-size:34px;letter-spacing:-.05em;line-height:1;margin:20px 0}.plan-card>p{font-size:12px;line-height:1.6;color:#667169}.price{display:flex;align-items:center;gap:13px;border-top:1px solid #ccd2ca;border-bottom:1px solid #ccd2ca;padding:20px 0;margin:25px 0}.price strong{font-size:44px;letter-spacing:-.06em}.price span{font:8px monospace;line-height:1.5;color:#6b756f}.plan-card ul{list-style:none;padding:0;font-size:11px;line-height:2}.plan-card li::first-letter{color:#4c6b2f}.plan-card li.later{color:#79847d;border-top:1px dashed #c4cbc3;margin-top:7px;padding-top:7px}.subscribe-cta{width:100%;border:0;background:#111a15;color:var(--acid);padding:15px;font:9px monospace;font-weight:bold;margin-top:12px}.subscribe-cta span{float:right}.plan-card>small{display:block;text-align:center;margin-top:10px;font:7px monospace;color:#818a84}
@media(max-width:1100px){.studio-body{grid-template-columns:44px 1fr 350px}.studio-topbar{gap:12px}.project-name{display:none}.studio-actions button:not(.pro-button){display:none}}
@media(max-width:800px){.studio-shell{height:auto;min-height:100vh;overflow:auto}.studio-topbar{position:sticky;top:0;z-index:20}.studio-topbar .brand>span:last-child{display:none}.product-tabs a{padding:0 10px}.studio-body{height:auto;display:block}.tool-rail{display:none}.design-canvas{height:52vh;min-height:390px}.copilot-panel{height:720px;border-left:0;border-top:1px solid #2a3a33}.studio-actions{margin-left:auto}.export-disabled{display:none!important}}

.canvas-mode-tabs{position:absolute;z-index:12;top:14px;left:50%;transform:translateX(-50%);display:flex;background:rgba(7,16,14,.9);border:1px solid #34473f;box-shadow:0 9px 30px rgba(0,0,0,.3)}.canvas-mode-tabs button{border:0;border-right:1px solid #34473f;background:transparent;color:#78877f;padding:9px 13px;font:7px monospace;letter-spacing:.05em}.canvas-mode-tabs button:last-child{border:0}.canvas-mode-tabs button.active{background:#1c3027;color:var(--acid)}.concept-layer{position:absolute;inset:0;opacity:0;pointer-events:none;transition:opacity .25s}.concept-layer.visible{opacity:1;pointer-events:auto}.geo-workspace,.geo-map{position:absolute;inset:0}.geo-workspace{z-index:5}.geo-map{background:#14231d}.maplibregl-map{font-family:Arial,Helvetica,sans-serif}.maplibregl-ctrl-group{background:#101c18!important;border:1px solid #42534c!important;box-shadow:none!important}.maplibregl-ctrl-group button{background-color:#101c18!important}.maplibregl-ctrl button .maplibregl-ctrl-icon{filter:invert(1);opacity:.6}.maplibregl-ctrl-attrib{background:rgba(7,16,14,.8)!important;color:#9ca7a1!important;font-size:9px!important}.maplibregl-ctrl-attrib a{color:#bdd0c7!important}.maplibregl-ctrl-scale{background:rgba(7,16,14,.8)!important;color:#c2cec7!important;border-color:#c2cec7!important;font:8px monospace!important}.map-search-card{position:absolute;z-index:8;left:16px;top:58px;width:278px;background:rgba(8,18,15,.95);border:1px solid #34483f;padding:17px;box-shadow:0 20px 55px rgba(0,0,0,.38)}.map-search-card>span,.basemap-picker>span{font:7px monospace;color:var(--acid);letter-spacing:.1em}.map-search-card>strong{display:block;font-size:15px;margin:8px 0}.map-search-card>p{font-size:9px;line-height:1.5;color:#7d8b84;margin:0 0 14px}.coordinate-inputs{display:grid;grid-template-columns:1fr 1fr;gap:7px}.coordinate-inputs label{font:6px monospace;color:#69776f}.coordinate-inputs input{display:block;width:100%;margin-top:5px;border:1px solid #31443a;background:#101f1a;color:#dce5df;padding:8px;font:9px monospace;outline:0}.coordinate-inputs input:focus{border-color:var(--acid)}.location-actions{display:flex;gap:7px;margin-top:11px}.location-actions button{border:1px solid #35483f;background:#13231d;color:#aebbb4;padding:8px;font:7px monospace}.location-actions .confirm-location{flex:1;background:var(--acid);border-color:var(--acid);color:#131b0e;font-weight:bold}.basemap-picker{position:absolute;z-index:8;right:15px;top:67px;width:124px;padding:11px;background:rgba(8,18,15,.94);border:1px solid #34483f}.basemap-picker>span{display:block;margin-bottom:7px}.basemap-picker button{width:100%;display:flex;align-items:center;gap:8px;border:1px solid transparent;background:transparent;color:#9aa79f;padding:6px;font:8px monospace;text-align:left}.basemap-picker button.active{border-color:#6f8a37;background:#1b2a1f;color:var(--acid)}.map-swatch{width:26px;height:19px;display:block;background-size:cover;border:1px solid #58675f}.map-swatch.streets{background:linear-gradient(35deg,#cbd2c5 25%,#ece7d9 25% 45%,#aab9c0 45% 52%,#e9e5d8 52%)}.map-swatch.satellite{background:radial-gradient(circle at 60% 30%,#9b8a62 0 12%,transparent 13%),linear-gradient(145deg,#1d4835,#677d48 52%,#273d38 53%)}.map-swatch.terrain{background:repeating-radial-gradient(ellipse at 20% 90%,#e1d7b5 0 3px,#927f62 4px,#d5cba9 6px)}.coordinate-readout{position:absolute;z-index:8;left:50%;bottom:38px;transform:translateX(-50%);background:rgba(8,18,15,.9);border:1px solid #34483f;padding:7px 10px;display:flex;gap:10px;font:7px monospace;color:#adbab3}.coordinate-readout span{color:var(--mint)}.location-context{display:flex;align-items:center;gap:8px;padding:9px 16px;border-bottom:1px solid #26362f;background:#11241c;font:7px monospace}.location-context span{color:var(--mint)}.location-context b{margin-left:auto;color:#b6c3bc}.location-context button{border:0;background:transparent;color:var(--acid);font:7px monospace}
@media(max-width:800px){.map-search-card{width:236px;top:54px}.map-search-card>p{display:none}.basemap-picker{top:auto;right:10px;bottom:42px}.coordinate-readout{display:none}.canvas-mode-tabs{left:auto;right:10px;transform:none}.location-actions{flex-direction:column}}

.canvas-mode-tabs .map-toggle{border-left:1px solid #4a5e55;color:#819087}.canvas-mode-tabs .map-toggle.active{color:var(--mint);background:#153027}.concept-layer{z-index:7}.concept-layer.visible{pointer-events:none}.geo-layer{position:absolute;z-index:5;inset:0;transition:opacity .2s,filter .2s}.geo-layer.plan-background{filter:saturate(.55) brightness(.58);opacity:.7;pointer-events:auto}.geo-layer.hidden-map{opacity:0;visibility:hidden;pointer-events:none}.geo-layer.plan-background .map-search-card,.geo-layer.plan-background .basemap-picker,.geo-layer.plan-background .coordinate-readout{display:none}.canvas-nav-hint{position:absolute;z-index:12;left:16px;bottom:43px;display:flex;align-items:center;gap:10px;padding:8px 11px;border:1px solid #40554b;background:rgba(7,16,14,.88);box-shadow:0 10px 28px rgba(0,0,0,.35);pointer-events:none}.canvas-nav-hint span{font:7px monospace;color:var(--acid);letter-spacing:.08em}.canvas-nav-hint b{font:7px monospace;color:#a6b3ac;font-weight:400}.geo-layer.plan-background .maplibregl-ctrl-top-right{top:46px}.geo-layer.plan-background .maplibregl-ctrl-group{box-shadow:0 8px 24px rgba(0,0,0,.35)!important}
.mouse-map-controls{position:absolute;z-index:14;right:14px;bottom:126px;display:flex;flex-direction:column;border:1px solid #52655c;background:#0b1713;box-shadow:0 10px 28px rgba(0,0,0,.4);pointer-events:auto}.mouse-map-controls button{width:38px;height:38px;border:0;border-bottom:1px solid #3b4d45;background:#101f1a;color:#dbe6df;font:20px/1 monospace;cursor:pointer}.mouse-map-controls button:last-child{border-bottom:0}.mouse-map-controls button:hover{background:#21362c;color:var(--acid)}.mouse-map-controls button:active{background:var(--acid);color:#11190e}.mouse-map-controls .reset-map-view{font-size:16px}.geo-layer.plan-background .mouse-map-controls{filter:none;opacity:1}
.basemap-picker.free-maps{width:150px}.basemap-picker.free-maps .open-map-screen{display:block;margin-top:8px;padding:10px 4px 2px;border:0;border-top:1px solid #304139;color:var(--acid);font:7px monospace;text-align:center;cursor:pointer}.geo-workspace.full-map-view{position:fixed;z-index:80;inset:62px 0 0 48px;background:#0b1713}.full-map-toolbar{position:absolute;z-index:16;top:14px;left:14px;right:14px;height:38px;display:flex;align-items:center;gap:14px;padding:0 12px;border:1px solid #40554b;background:rgba(7,16,14,.92);box-shadow:0 10px 30px rgba(0,0,0,.35);pointer-events:auto}.full-map-toolbar span{font:8px monospace;color:var(--acid);letter-spacing:.09em}.full-map-toolbar b{font:7px monospace;color:#839189;font-weight:400}.full-map-toolbar button{margin-left:auto;border:1px solid #52655c;background:#17271f;color:#dbe5df;padding:7px 10px;font:7px monospace;cursor:pointer}.full-map-toolbar button:hover{border-color:var(--acid);color:var(--acid)}.full-map-view .map-search-card,.full-map-view .basemap-picker{top:67px}.full-map-view .mouse-map-controls{bottom:52px}@media(max-width:800px){.geo-workspace.full-map-view{inset:62px 0 0}.full-map-toolbar b{display:none}.full-map-toolbar button{padding:7px}}
.leaflet-container{font-family:Arial,Helvetica,sans-serif;background:#102019}.leaflet-control-attribution{background:rgba(7,16,14,.86)!important;color:#a8b4ad!important;font-size:9px!important}.leaflet-control-attribution a{color:#c9d6cf!important}.leaflet-control-scale-line{background:rgba(7,16,14,.86)!important;color:#d5dfd9!important;border-color:#d5dfd9!important;font:8px monospace!important}.site-map-marker{border:3px solid #0c1712;border-radius:50%;background:var(--acid);box-shadow:0 0 0 3px rgba(217,255,67,.35),0 4px 14px rgba(0,0,0,.55)}.leaflet-grab{cursor:grab}.leaflet-dragging .leaflet-grab{cursor:grabbing}
.map-load-error{position:absolute;z-index:20;left:50%;top:50%;transform:translate(-50%,-50%);padding:12px 16px;border:1px solid #7f473d;background:#241512;color:#ffb5a8;font:8px monospace}
.studio-body{position:relative;grid-template-columns:0 minmax(0,1fr) 390px}.tool-rail{position:absolute;z-index:95;left:0;top:0;bottom:0;width:48px;background:rgba(7,16,14,.9);backdrop-filter:blur(8px);box-shadow:8px 0 24px rgba(0,0,0,.24)}.design-canvas{grid-column:2}.copilot-panel{grid-column:3}.map-search-card{left:64px}.canvas-nav-hint{left:64px}.geo-workspace.full-map-view{inset:62px 0 0}.full-map-toolbar{left:64px}@media(max-width:1100px) and (min-width:801px){.studio-body{grid-template-columns:0 minmax(0,1fr) 350px}}@media(max-width:800px){.map-search-card{left:10px}.full-map-toolbar{left:14px}}
.tool-rail{z-index:1400;left:12px;top:14px;bottom:14px;width:42px;border:1px solid #3d5148;border-radius:4px;background:rgba(7,16,14,.88);box-shadow:0 14px 34px rgba(0,0,0,.42);pointer-events:auto}.canvas-mode-tabs{z-index:1300}.map-search-card,.basemap-picker,.coordinate-readout,.mouse-map-controls,.full-map-toolbar,.canvas-nav-hint{z-index:1200}@media(max-width:800px){.tool-rail{display:flex;top:58px;bottom:auto;height:auto;padding:7px 0}.tool-rail .tool-bottom{display:none}.map-search-card{left:62px}.canvas-nav-hint{left:62px}}
.area-select-panel{position:absolute;z-index:1250;left:64px;bottom:42px;display:flex;align-items:center;gap:7px;padding:8px;border:1px solid #43574e;background:rgba(7,16,14,.92);box-shadow:0 12px 30px rgba(0,0,0,.38);pointer-events:auto}.area-select-panel span{font:7px monospace;color:var(--acid);letter-spacing:.05em}.area-select-panel button{border:1px solid #485d53;background:#15251e;color:#c1cdc6;padding:8px 10px;font:7px monospace;cursor:pointer}.area-select-panel button:hover{border-color:var(--acid);color:var(--acid)}.area-select-panel .start-area,.area-select-panel .finish-area{background:var(--acid);border-color:var(--acid);color:#121a0e;font-weight:bold}.area-select-panel button:disabled{opacity:.35;cursor:not-allowed}.area-select-panel.active{border-color:#8ca431}.geo-workspace:has(.area-select-panel.active) .leaflet-container{cursor:crosshair}@media(max-width:800px){.area-select-panel{left:62px;bottom:40px;max-width:calc(100% - 74px);flex-wrap:wrap}}
.area-select-panel .unlock-map{background:var(--acid);border-color:var(--acid);color:#121a0e;font-weight:bold}.area-select-panel .lock-map{border-color:#c7e84a;color:var(--acid)}.geo-workspace.map-locked .leaflet-container{cursor:grab}.geo-workspace.map-locked .site-map-marker{box-shadow:0 0 0 4px rgba(217,255,67,.25),0 0 22px rgba(217,255,67,.35)}
.site-map-marker{display:none!important}
.geo-layer.plan-background{filter:none;opacity:1}.geo-layer.plan-background .area-select-panel{display:none}
.area-resize-handle{display:block!important;width:14px!important;height:14px!important;border:2px solid #0b1712;border-radius:2px;background:var(--acid);box-shadow:0 0 0 2px rgba(217,255,67,.28),0 4px 12px rgba(0,0,0,.6)}
.area-resize-handle.handle-n,.area-resize-handle.handle-s{cursor:ns-resize}
.area-resize-handle.handle-e,.area-resize-handle.handle-w{cursor:ew-resize}
.area-resize-handle.handle-ne,.area-resize-handle.handle-sw{cursor:nesw-resize}
.area-resize-handle.handle-nw,.area-resize-handle.handle-se{cursor:nwse-resize}
.geo-layer.plan-background .area-resize-handle,.geo-layer.hidden-map .area-resize-handle{display:none!important}
.geo-layer.hidden-map{opacity:1;visibility:visible;pointer-events:auto}.geo-layer.hidden-map .leaflet-tile-pane{opacity:0}.geo-layer.hidden-map .leaflet-container{background-color:#0b1713;background-image:linear-gradient(rgba(109,153,135,.12) 1px,transparent 1px),linear-gradient(90deg,rgba(109,153,135,.12) 1px,transparent 1px),linear-gradient(rgba(109,153,135,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(109,153,135,.045) 1px,transparent 1px);background-size:100px 100px,100px 100px,20px 20px,20px 20px}.geo-layer.hidden-map .map-search-card,.geo-layer.hidden-map .basemap-picker,.geo-layer.hidden-map .coordinate-readout,.geo-layer.hidden-map .area-select-panel,.geo-layer.hidden-map .leaflet-control-attribution{display:none}
.prompt-starters{display:grid;gap:6px;margin:0 0 16px 34px}.prompt-starters>span{font:6px monospace;color:#64736b;margin-bottom:2px}.prompt-starters button{display:flex;justify-content:space-between;border:1px solid #2b4036;background:#102019;color:#aebbb4;padding:9px 10px;text-align:left;font-size:9px}.prompt-starters button:hover{border-color:#6e8c3b;color:var(--acid)}.prompt-starters button b{color:var(--acid)}.chat-message.typing p{display:flex;gap:4px;align-items:center;background:#14241e;padding:10px 12px;border-radius:8px}.chat-message.typing p i{display:block;width:5px;height:5px;border-radius:50%;background:#829087;animation:typing-dot 1.2s infinite}.chat-message.typing p i:nth-child(2){animation-delay:.2s}.chat-message.typing p i:nth-child(3){animation-delay:.4s}@keyframes typing-dot{0%,70%,100%{opacity:.25;transform:translateY(0)}35%{opacity:1;transform:translateY(-3px)}}
.chat-compose{border:1px solid #627a37;box-shadow:0 0 0 2px rgba(217,255,67,.04),0 -12px 35px rgba(0,0,0,.22)}.command-label{height:29px;display:flex;align-items:center;justify-content:space-between;padding:0 10px;border-bottom:1px solid #30423a;background:#14251e}.command-label span{font:7px monospace;color:var(--acid);letter-spacing:.08em}.command-label b{font:5px monospace;color:#5f6d66}.command-entry{display:flex;align-items:flex-end;padding:8px;gap:7px}.command-entry textarea{flex:1;min-width:0;background:transparent;border:0;outline:0;resize:none;color:#eef4ef;font-size:12px;line-height:1.55;padding:4px}.command-entry textarea::placeholder{color:#65736c}.attach-command{width:31px;height:31px;border:1px solid #3b5046;background:#15251f;color:var(--acid);font-size:16px;flex:0 0 auto}.send-command{height:34px;border:0;background:var(--acid);color:#11190d;padding:0 12px;font:8px monospace;font-weight:bold;flex:0 0 auto}.send-command:disabled{opacity:.3}.compose-foot b{font:6px monospace;color:#829087}.compose-foot input{display:none}
.command-analysis{padding:11px 16px;border-bottom:1px solid #26362f;background:#0b1713}.command-analysis>div:first-child{display:flex;justify-content:space-between;font:6px monospace;color:#64736b}.command-analysis>div:first-child b{color:var(--mint)}.command-analysis>strong{display:block;margin:7px 0;text-transform:uppercase;font:10px monospace;color:#e4ebe7}.command-tags{display:flex;flex-wrap:wrap;gap:5px}.command-tags i{font:6px monospace;font-style:normal;text-transform:uppercase;padding:4px 6px;border:1px solid #4d6332;color:var(--acid);background:#142219}.command-analysis p,.command-analysis small{display:block;margin:7px 0 0;font:6px/1.5 monospace;color:#87958d}.command-analysis small{color:#c0c9c4}
.road-context{padding:10px 16px;border-bottom:1px solid #26362f;background:#101f19}.road-context>span{display:block;font:6px monospace;color:var(--acid);letter-spacing:.08em}.road-context strong,.road-context b,.road-context i,.road-context small{display:block;margin-top:5px}.road-context strong{font-size:10px}.road-context b{font:7px monospace;color:#aebbb4}.road-context i{width:max-content;padding:3px 5px;border:1px solid #557134;color:var(--acid);font:6px monospace;font-style:normal;text-transform:uppercase}.road-context small{font:6px/1.4 monospace;color:#66756d}
.copilot-panel{min-height:0;overflow:hidden}.copilot-head,.design-progress,.location-context,.command-analysis,.road-context,.intake-checks{flex:0 0 auto}.chat-stream{min-height:0;overscroll-behavior:contain}.chat-compose{position:sticky;z-index:20;bottom:0;flex:0 0 auto;background:#111f1a;box-shadow:0 -16px 38px rgba(0,0,0,.48),0 0 0 2px rgba(217,255,67,.04)}
.road-workflow{flex:0 0 auto;padding:10px 16px;border-bottom:1px solid #26362f;background:#0d1b16}.road-workflow>div{display:flex;justify-content:space-between;font:6px monospace;color:#6d7c74}.road-workflow>div b{color:var(--acid)}.road-workflow ol{display:grid;grid-template-columns:repeat(6,1fr);gap:3px;list-style:none;padding:0;margin:8px 0 0}.road-workflow li{min-width:0;color:#58675f;text-align:center}.road-workflow li i{width:18px;height:18px;margin:auto;display:grid;place-items:center;border:1px solid #34473e;border-radius:50%;font:6px monospace;font-style:normal}.road-workflow li span{display:block;margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font:5px monospace}.road-workflow li.active{color:var(--acid)}.road-workflow li.active i{border-color:var(--acid);box-shadow:0 0 9px rgba(217,255,67,.3)}.road-workflow li.done{color:var(--mint)}.road-workflow li.done i{background:var(--mint);border-color:var(--mint);color:#0d1814}.road-workflow>small{display:block;margin-top:7px;font:5px monospace;color:#7e8d85}
.standards-context{flex:0 0 auto;max-height:150px;overflow-y:auto;padding:10px 16px;border-bottom:1px solid #26362f;background:#121d19}.standards-context>div:first-child{display:flex;justify-content:space-between;gap:8px;font:6px monospace;color:var(--acid)}.standards-context>div:first-child b{text-transform:uppercase;color:var(--mint)}.standards-context>div:first-child b.needs-openai,.standards-context>div:first-child b.unverified,.standards-context>div:first-child b.search-failed{color:#e8b84b}.standards-context p{margin:7px 0;font:7px/1.5 monospace;color:#aab6af;white-space:pre-line}.standards-sources{display:flex!important;flex-wrap:wrap;justify-content:flex-start!important;gap:5px!important}.standards-sources a{border:1px solid #3c5147;padding:4px 5px;color:var(--mint);text-decoration:none;font:6px monospace}
.existing-road{flex:0 0 auto;padding:9px 16px;border-bottom:1px solid #26362f;background:#0e1a16}.existing-road>span{font:6px monospace;color:var(--acid)}.existing-road>div{display:grid;grid-template-columns:repeat(3,1fr);gap:5px;margin-top:7px}.existing-road b{font:5px monospace;color:#66756d}.existing-road b i{display:block;margin-top:2px;color:#b8c4bd;font:6px monospace;font-style:normal}.existing-road>small{display:block;margin-top:7px;font:5px/1.4 monospace;color:#7e8c85}
.studio-body{grid-template-columns:0 minmax(0,1fr)}.copilot-panel{position:absolute;z-index:96;top:0;right:0;bottom:0;width:390px;height:100%;min-width:320px;min-height:420px;max-width:calc(100% - 48px);max-height:100%;overflow:auto;resize:both;box-shadow:-16px 0 42px rgba(0,0,0,.38)}.copilot-panel .chat-stream{flex:1 0 auto;overflow:visible}.copilot-panel.moved{box-shadow:0 22px 70px rgba(0,0,0,.58)}.copilot-head{cursor:move;touch-action:none;background:#0d1814}.copilot-head button{width:30px;height:30px;cursor:pointer;font-size:16px}.copilot-grip{color:#53645b;font-size:15px}.copilot-resize-hint{position:absolute;z-index:30;right:2px;bottom:1px;color:var(--acid);font:15px monospace;pointer-events:none}.design-canvas{grid-column:2}.copilot-panel{grid-column:auto}@media(max-width:800px){.copilot-panel,.copilot-panel.moved{position:relative!important;inset:auto!important;width:100%!important;height:720px!important;min-width:0;max-width:none;max-height:none;resize:none;box-shadow:none}.copilot-head{cursor:default}.copilot-grip,.copilot-resize-hint{display:none}}
.copilot-window-actions{margin-left:auto;gap:3px!important}.copilot-window-actions button:hover{color:var(--acid);background:#192a22}.copilot-popout{min-height:100vh}.copilot-popout .studio-body{height:100vh;display:block}.copilot-popout .copilot-panel{position:fixed!important;inset:0!important;width:100%!important;height:100%!important;min-width:0;max-width:none;max-height:none;resize:none;box-shadow:none}.copilot-popout .copilot-head{cursor:default}.copilot-popout .copilot-grip,.copilot-popout .copilot-resize-hint{display:none}
.copilot-panel.detached{display:none}.copilot-scroll{flex:1;min-height:0;overflow:auto;overscroll-behavior:contain}.copilot-panel .design-progress,.copilot-panel .command-analysis,.copilot-panel .location-context,.copilot-panel .road-context,.copilot-panel .existing-road,.copilot-panel .standards-context,.copilot-panel .road-workflow,.copilot-panel .chat-stream,.copilot-panel .intake-checks{position:relative;resize:none;overflow:auto;min-height:24px;max-height:none}.copilot-panel .design-progress:after,.copilot-panel .command-analysis:after,.copilot-panel .location-context:after,.copilot-panel .road-context:after,.copilot-panel .existing-road:after,.copilot-panel .standards-context:after,.copilot-panel .road-workflow:after,.copilot-panel .chat-stream:after,.copilot-panel .intake-checks:after{content:"";position:absolute;z-index:40;left:0;right:0;bottom:0;height:10px;cursor:ns-resize;background:linear-gradient(to bottom,transparent 4px,#53685e 4px,#53685e 5px,transparent 5px)}.copilot-panel .chat-stream{min-height:24px}.copilot-panel .standards-context{max-height:none}.copilot-panel .chat-compose{position:relative;bottom:auto;flex:0 0 auto;min-height:124px;margin:8px 12px 12px}.copilot-popout .copilot-panel.detached{display:flex}
.model-workspace{position:absolute;z-index:8;inset:0;overflow:hidden;background:radial-gradient(circle at 50% 35%,#183128,#07110e 68%);perspective:900px}.model-toolbar{position:absolute;z-index:5;top:65px;left:64px;display:flex;border:1px solid #41544b;background:rgba(8,18,15,.94);box-shadow:0 12px 30px rgba(0,0,0,.35)}.model-toolbar span,.model-toolbar button{padding:9px 11px;border:0;border-right:1px solid #35483f;background:transparent;color:#829087;font:7px monospace}.model-toolbar span{color:var(--acid)}.model-toolbar button.active{background:#213328;color:var(--acid)}.model-stage{position:absolute;left:8%;right:8%;top:18%;bottom:8%;transform:rotateX(58deg) rotateZ(-18deg);transform-style:preserve-3d}.model-ground{position:absolute;inset:0;background-color:#13241e;background-image:linear-gradient(rgba(107,170,144,.18) 1px,transparent 1px),linear-gradient(90deg,rgba(107,170,144,.18) 1px,transparent 1px);background-size:38px 38px;border:1px solid #3f6253;box-shadow:0 40px 80px rgba(0,0,0,.5)}.model-corridor{display:none;position:absolute;left:5%;right:5%;top:43%;height:19%;transform:translateZ(8px) rotate(-4deg);background:#3b4641;border:2px solid var(--acid)}.model-corridor i{position:absolute;left:0;right:0;top:50%;border-top:2px dashed #edf2ee}.model-corridor i:nth-child(2){top:8%;border-color:#87a197}.model-corridor i:nth-child(3){top:92%;border-color:#87a197}.model-utilities{display:none;position:absolute;inset:0;transform:translateZ(18px)}.model-utilities i{position:absolute;left:8%;right:7%;height:8px;border-radius:10px;box-shadow:0 8px 12px rgba(0,0,0,.5)}.model-utilities .water{top:32%;background:#2b8cff}.model-utilities .sanitary{top:52%;background:#c95cff;transform:rotate(8deg)}.model-utilities .storm{top:70%;background:#48c79d;transform:rotate(-5deg)}.model-surface{display:none;position:absolute;inset:5%;transform:translateZ(6px)}.model-surface i{position:absolute;width:72%;height:48%;border:2px solid #78c4a5;border-radius:50%;left:8%;top:9%;box-shadow:0 0 0 18px rgba(74,133,109,.08),0 0 0 36px rgba(74,133,109,.06)}.model-surface i:nth-child(2){width:45%;height:30%;left:40%;top:48%}.model-surface i:nth-child(3){width:26%;height:18%;left:16%;top:63%}.model-surface i:nth-child(4){width:19%;height:12%;left:65%;top:14%}.model-surface .unused{display:none}.model-surface i{transform:translateZ(14px)}.model-surface~*{transform-style:preserve-3d}.model-surface .x{display:none}.model-surface,.model-surface i{pointer-events:none}.model-surface{opacity:.9}.model-surface i:nth-child(2){transform:translateZ(28px)}.model-surface i:nth-child(3){transform:translateZ(42px)}.model-surface i:nth-child(4){transform:translateZ(20px)}.model-surface{display:none}.model-surface{}.model-surface i{}.model-workspace.model-surface .model-surface,.model-workspace.model-utilities .model-utilities,.model-workspace.model-corridor .model-corridor{display:block}.model-status{position:absolute;z-index:5;left:64px;bottom:42px;padding:11px 13px;border:1px solid #3d5148;background:rgba(7,16,14,.92)}.model-status span,.model-status b,.model-status small{display:block}.model-status span{font:6px monospace;color:var(--acid)}.model-status b{margin-top:6px;font:9px monospace;color:#d7e1db}.model-status small{margin-top:5px;font:6px monospace;color:#718078}
.map-3d{position:absolute;inset:0;background:#0c1713}.model-workspace .maplibregl-map{position:absolute;inset:0}.model-workspace .maplibregl-ctrl-bottom-right{right:410px}.model-workspace .maplibregl-ctrl-group{background:#0d1915!important}.model-workspace .maplibregl-canvas{outline:none}
.utility-legend{position:absolute;z-index:1250;left:64px;top:112px;width:220px;padding:11px;border:1px solid #416579;background:rgba(6,18,24,.94);box-shadow:0 14px 34px rgba(0,0,0,.42)}.utility-legend>span{display:block;margin-bottom:8px;font:7px monospace;color:#8dd5ff}.utility-legend>b{display:flex;align-items:center;gap:7px;padding:5px 0;border-top:1px solid rgba(255,255,255,.08);font:7px monospace;color:#d5e0e4}.utility-legend>b i{width:15px;height:4px}.utility-legend>b small{margin-left:auto;color:#7d929c;font:6px monospace}.utility-legend>em{display:block;margin-top:8px;color:#ffcf65;font:6px monospace;font-style:normal}@media(max-width:800px){.utility-legend{left:62px;top:104px;width:190px}}
.concept-legend{position:absolute;z-index:1250;right:410px;top:112px;width:225px;padding:11px;border:1px solid #617a38;background:rgba(11,24,17,.94);box-shadow:0 14px 34px rgba(0,0,0,.42)}.concept-legend>span{display:block;margin-bottom:8px;font:7px monospace;color:var(--acid)}.concept-legend>b{display:flex;align-items:center;gap:7px;padding:5px 0;border-top:1px solid rgba(255,255,255,.08);font:7px monospace;color:#dce5df}.concept-legend>b i{width:15px;height:4px}.concept-legend>em{display:block;margin-top:8px;color:#ffcf65;font:6px monospace;font-style:normal}@media(max-width:800px){.concept-legend{right:10px;top:104px;width:190px}}
.survey-legend{position:absolute;z-index:1250;left:64px;bottom:42px;width:235px;padding:11px;border:1px solid #806f36;background:rgba(23,20,9,.94);box-shadow:0 14px 34px rgba(0,0,0,.42)}.survey-legend>span,.survey-legend>strong,.survey-legend>b,.survey-legend>em{display:block}.survey-legend>span{font:7px monospace;color:#ffdf6b}.survey-legend>strong{margin:7px 0;font-size:9px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.survey-legend>b{padding:4px 0;border-top:1px solid rgba(255,255,255,.08);font:6px monospace;color:#9ead9f}.survey-legend>b.on{color:#e7eee8}.survey-legend>b.off{text-decoration:line-through;opacity:.5}.survey-legend>b i{float:right;color:#ffdf6b;font-style:normal}.survey-legend>em{margin-top:7px;font:5px/1.4 monospace;color:#ffb765;font-style:normal}@media(max-width:800px){.survey-legend{left:62px;bottom:38px;width:205px}}
.survey-legend{width:265px;max-height:calc(100% - 170px);overflow:auto}.survey-crs-form{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:9px;padding-top:9px;border-top:1px solid #6d5f31}.survey-crs-section{grid-column:1/-1;margin-top:4px;padding-top:8px;border-top:1px solid #3f3a25;color:#ffdf6b;font:6px monospace;letter-spacing:.1em}.survey-crs-form label{font:5px monospace;color:#b5a96f}.survey-crs-form input,.survey-crs-form select{display:block;width:100%;height:28px;margin-top:4px;border:1px solid #5d5635;background:#17170f;color:#eef1e7;padding:0 6px;font:7px monospace;outline:none}.survey-crs-form input:focus,.survey-crs-form select:focus{border-color:#ffdf6b}.survey-crs-form button{grid-column:1/-1;height:30px;border:0;background:#ffdf6b;color:#17170f;font:7px monospace;font-weight:bold}.survey-crs-form button:disabled{opacity:.4}.survey-crs-form small{grid-column:1/-1;color:#ffb765;font:6px/1.4 monospace}@media(max-width:800px){.survey-legend{width:230px}}
.coordinate-error{display:block;color:#ff8b6b;font:6px/1.4 monospace;margin-top:7px}.go-to-coordinates{width:100%;margin-top:8px;border:1px solid #708c3b;background:#1b2b20;color:var(--acid);padding:9px;font:7px monospace;font-weight:bold}.area-select-panel .clear-area{border-color:#9a4e3e;color:#ff9c84}.area-select-panel .clear-area:hover{border-color:#ff7f62;color:#ffb09d}
.alignment-station-label{display:grid!important;place-items:center;background:rgba(7,16,14,.9);border:1px solid #fff;color:#fff;font:7px monospace;font-weight:bold;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,.5)}
.site-area-picker{display:flex;align-items:center;gap:6px;color:#8fa198;font:6px monospace}.site-area-picker select{min-width:82px;border:1px solid #52675d;background:#101f1a;color:var(--acid);padding:7px;font:7px monospace;outline:none}.site-area-picker select:focus{border-color:var(--acid)}
.elevation-layer-controls{position:absolute;z-index:1250;right:15px;top:225px;width:170px;padding:10px;border:1px solid #476756;background:rgba(7,18,14,.94);box-shadow:0 12px 30px rgba(0,0,0,.38)}.elevation-layer-controls>span{display:block;margin-bottom:7px;color:#9bb4a7;font:6px/1.4 monospace}.elevation-layer-controls button{width:100%;margin-top:5px;border:1px solid #42584e;background:#12231c;color:#94a69d;padding:8px;font:7px monospace;text-align:left}.elevation-layer-controls button.active{border-color:var(--acid);background:#20331f;color:var(--acid)}.elevation-layer-controls small{display:block;margin-top:7px;color:#ffcf65;font:6px/1.4 monospace}@media(max-width:800px){.elevation-layer-controls{right:10px;top:205px;width:150px}}

/* Docked project-area drawer */
.area-select-panel{left:12px;bottom:45px;width:min(330px,calc(100% - 24px));align-items:stretch;align-content:flex-start;flex-wrap:wrap;padding:10px;padding-top:42px;border-radius:0 7px 7px 7px;background:rgba(7,16,14,.97)}.area-select-panel>span{width:100%;line-height:1.5}.area-select-panel .site-area-picker{width:100%;justify-content:space-between}.area-select-panel .site-area-picker select{flex:1}.area-panel-head{position:absolute;left:0;right:0;top:0;height:32px;display:flex;align-items:center;justify-content:space-between;padding:0 8px 0 11px;border-bottom:1px solid #34483f;background:#12221c}.area-panel-head span{font:7px monospace;color:var(--acid);letter-spacing:.09em}.area-panel-head button{width:25px;height:25px;padding:0;border:0;background:transparent;color:#93a098;font-size:18px}.area-panel-tab,.area-layers-tab{position:absolute;z-index:1251;left:12px;bottom:12px;height:34px;border:1px solid #4c6258;background:rgba(8,18,15,.97);color:var(--acid);box-shadow:0 8px 22px rgba(0,0,0,.4);font:7px monospace;letter-spacing:.07em;cursor:pointer}.area-panel-tab{padding:0 12px}.area-panel-tab.open{border-color:var(--acid);background:#1b2d24}.area-panel-tab span,.area-layers-tab span{margin-left:5px}.area-layers-tab{left:131px;padding:0 11px}.area-panel-tab:hover,.area-layers-tab:hover{background:#243a2e;border-color:var(--acid)}.geo-layer.plan-background .area-panel-tab,.geo-layer.plan-background .area-layers-tab,.geo-layer.hidden-map .area-panel-tab,.geo-layer.hidden-map .area-layers-tab{display:none}@media(max-width:800px){.area-select-panel{left:10px;bottom:45px;max-width:calc(100% - 20px)}.area-panel-tab{left:10px}.area-layers-tab{left:129px}}
.plan-production-profile{margin:0 12px 10px;padding:10px 11px;border:1px solid #3d554a;background:#101f1a;display:flex;flex-direction:column;gap:5px}.plan-production-profile span{font:6px monospace;color:var(--acid);letter-spacing:.09em}.plan-production-profile b{font-size:9px;color:#dce5df}.plan-production-profile small{font:6px/1.5 monospace;color:#819087}.plan-production-profile i{font:5px monospace;color:#d0a45a;font-style:normal}
.terrain-section-status{margin:0 12px 10px;padding:10px 11px;border:1px solid #765f2e;background:#211d12;display:flex;flex-direction:column;gap:5px}.terrain-section-status span{font:6px monospace;color:#ffcf65;letter-spacing:.09em}.terrain-section-status b{font-size:9px;color:#f4ead0}.terrain-section-status small{font:6px/1.5 monospace;color:#afa080}.terrain-section-status i{font:5px monospace;color:#ffb765;font-style:normal}

/* Manual civil-design ribbon */
.civil-ribbon{height:82px;background:#0c1713;border-bottom:1px solid #32443b;display:flex;flex-direction:column;position:relative;z-index:40}.ribbon-tabs{height:25px;display:flex;align-items:end;padding-left:52px;border-bottom:1px solid #27372f}.ribbon-tabs button{height:25px;border:0;border-right:1px solid #24342c;background:transparent;color:#7f8d86;padding:0 15px;font:7px monospace;letter-spacing:.06em}.ribbon-tabs button.active{color:var(--acid);background:#17271f;box-shadow:inset 0 -2px var(--acid)}.ribbon-tools{height:57px;display:flex;align-items:stretch;padding:4px 10px 4px 52px;overflow-x:auto}.ribbon-toolset{display:flex;align-items:stretch;border-right:1px solid #35483f;padding-right:7px}.ribbon-toolset button,.ribbon-options button{min-width:57px;border:1px solid transparent;background:transparent;color:#9aa7a0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;padding:3px 7px}.ribbon-toolset button:hover,.ribbon-toolset button.active,.ribbon-options button:hover,.ribbon-options button.active{border-color:#566b61;background:#1a2c24;color:var(--acid)}.ribbon-toolset b,.ribbon-options b{font:15px monospace;line-height:1}.ribbon-toolset span,.ribbon-options span{font:6px monospace;white-space:nowrap}.ribbon-options{display:flex;align-items:stretch;padding-left:7px}.ribbon-options small{align-self:center;margin-left:10px;color:#65746c;font:6px monospace;white-space:nowrap}.studio-shell:not(.copilot-popout) .studio-body{height:calc(100vh - 144px)}.manual-design-label{width:auto!important;height:auto!important;background:#101a16;border:1px solid #d9ff43;color:#d9ff43;padding:3px 5px;font:7px monospace;white-space:nowrap;box-shadow:0 3px 12px rgba(0,0,0,.45)}.leaflet-container[data-manual-tool="alignment"],.leaflet-container[data-manual-tool="polyline"],.leaflet-container[data-manual-tool="feature"],.leaflet-container[data-manual-tool="storm"],.leaflet-container[data-manual-tool="sanitary"],.leaflet-container[data-manual-tool="water"],.leaflet-container[data-manual-tool="measure"],.leaflet-container[data-manual-tool="point"],.leaflet-container[data-manual-tool="text"]{cursor:crosshair}.leaflet-container[data-manual-tool="erase"]{cursor:not-allowed}@media(max-width:900px){.ribbon-tabs{padding-left:8px;overflow-x:auto}.ribbon-tools{padding-left:8px}.ribbon-options small{display:none}}
.studio-body{grid-template-columns:0 minmax(0,1fr) var(--copilot-width,390px);transition:grid-template-columns .2s ease}.studio-body.copilot-collapsed{grid-template-columns:0 minmax(0,1fr) 56px}.studio-body.copilot-hidden{grid-template-columns:0 minmax(0,1fr) 0}.copilot-panel{position:relative;inset:auto;width:100%;height:100%;min-width:0;max-width:none;max-height:none;resize:none;box-shadow:-10px 0 28px rgba(0,0,0,.28)}.copilot-head{cursor:default}.copilot-dock-resizer{position:absolute;z-index:60;left:-5px;top:0;bottom:0;width:10px;cursor:ew-resize;background:transparent}.copilot-dock-resizer:hover{background:rgba(217,255,67,.18)}.copilot-panel.collapsed{display:flex}.copilot-panel.collapsed .copilot-head{height:100%;padding:12px 0;flex-direction:column;justify-content:flex-start;gap:15px}.copilot-panel.collapsed .copilot-head>div:first-child>div,.copilot-panel.collapsed .copilot-scroll,.copilot-panel.collapsed .chat-compose,.copilot-panel.collapsed .copilot-resize-hint{display:none}.copilot-panel.collapsed .copilot-head>div:first-child{justify-content:center}.copilot-panel.collapsed .copilot-window-actions{margin:0;flex-direction:column}.copilot-panel.collapsed .copilot-window-actions button:not(:first-child){display:none}.copilot-restore-tab{position:absolute;z-index:1400;right:12px;top:12px;border:1px solid #7e9c3d;background:#12241b;color:var(--acid);padding:10px 13px;font:7px monospace;font-weight:bold;box-shadow:0 10px 28px rgba(0,0,0,.4)}@media(max-width:800px){.studio-body,.studio-body.copilot-collapsed,.studio-body.copilot-hidden{display:block}.copilot-panel.collapsed{height:58px!important}.copilot-panel.collapsed .copilot-head{height:58px;flex-direction:row;padding:0 12px}.copilot-dock-resizer{display:none}.copilot-restore-tab{position:fixed;top:72px}}
.copilot-popout .studio-body{display:block}.copilot-popout .copilot-panel{position:fixed!important;inset:0!important;width:100%!important;height:100%!important;max-width:none;display:flex}.copilot-popout .copilot-dock-resizer{display:none}

/* The top Civil ribbon replaces the legacy left tool rail. */
.tool-rail{display:none!important}.ribbon-tabs{padding-left:12px}.ribbon-tools{padding-left:12px}.map-search-card{left:16px}.canvas-nav-hint{left:16px}.full-map-toolbar{left:16px}@media(max-width:800px){.map-search-card{left:10px}.canvas-nav-hint{left:10px}}

/* Collapsible Manual Design workspace */
.civil-ribbon{height:112px;transition:height .2s ease;overflow:hidden}.manual-design-toggle{height:30px;min-height:30px;width:100%;display:flex;align-items:center;gap:9px;padding:0 13px;border:0;border-bottom:1px solid #34483f;background:#101e19;color:#dce6df;text-align:left}.manual-design-toggle>span{color:var(--acid);font-size:14px}.manual-design-toggle>b{font:8px monospace;letter-spacing:.09em}.manual-design-toggle>small{font:6px monospace;color:#6f7e76}.manual-design-toggle>i{margin-left:auto;color:var(--acid);font-style:normal;font-size:13px}.civil-ribbon.closed{height:34px}.civil-ribbon.closed .ribbon-tabs,.civil-ribbon.closed .ribbon-tools{display:none}.studio-shell.ribbon-open .studio-body{height:calc(100vh - 174px)}.studio-shell.ribbon-closed .studio-body{height:calc(100vh - 96px)}.ribbon-tabs{overflow-x:auto;scrollbar-width:thin}.ribbon-tabs button{flex:0 0 auto}.ribbon-toolset button{min-width:68px}.ribbon-tools{overflow-x:auto}.leaflet-interactive{transition:stroke-width .12s,stroke .12s}@media(max-width:800px){.studio-shell.ribbon-open .studio-body,.studio-shell.ribbon-closed .studio-body{height:auto}.manual-design-toggle{position:sticky;left:0}}
.manual-command-hud{position:absolute;z-index:1500;left:50%;bottom:39px;transform:translateX(-50%);min-width:390px;max-width:calc(100% - 30px);display:grid;grid-template-columns:auto 1fr;gap:4px 12px;align-items:center;padding:8px 11px;border:1px solid #7d963d;background:rgba(9,19,15,.96);box-shadow:0 10px 30px rgba(0,0,0,.45);pointer-events:none}.manual-command-hud span{font:6px monospace;color:var(--acid);letter-spacing:.08em}.manual-command-hud b{font:8px monospace;color:#edf4ef}.manual-command-hud small{grid-column:1/-1;font:5px monospace;color:#829188}@media(max-width:700px){.manual-command-hud{min-width:0;width:calc(100% - 20px)}}
.dropzone .change-source{align-self:flex-start;margin:1px 0 0!important;padding:0!important;border:0!important;background:transparent!important;color:var(--acid)!important;font:8px monospace!important;text-transform:uppercase;text-decoration:underline;text-underline-offset:3px}
.live-pill,.later-pill{display:inline-block;margin-left:5px;padding:3px 5px;border:1px solid rgba(217,255,67,.45);color:var(--acid);font:6px monospace;letter-spacing:.08em;vertical-align:1px}.later-pill{border-color:#52625a;color:#829188}.product-roadmap{padding:100px 5vw;background:#0c1814;border-top:1px solid #25362e;border-bottom:1px solid #25362e;display:grid;grid-template-columns:.8fr 1.2fr;gap:7vw}.roadmap-intro h2{font-size:clamp(44px,5vw,72px);line-height:.95;letter-spacing:-.055em;margin:25px 0}.roadmap-intro h2 span{color:#76837b}.roadmap-intro p{max-width:500px;color:#8e9a93;font-size:14px;line-height:1.7}.product-cards{display:grid;grid-template-columns:1fr 1fr;gap:16px}.product-card{min-height:330px;padding:27px;display:flex;flex-direction:column;border:1px solid #33463d;background:#101f1a}.product-card>div{display:flex;justify-content:space-between;align-items:center;font:8px monospace;color:#78867e}.product-card>div b{padding:6px 8px;border:1px solid #46574f;color:#94a29a}.product-card h3{font-size:25px;margin:65px 0 15px}.product-card p{font-size:13px;line-height:1.65;color:#86938c;margin:0}.active-product{border-color:rgba(217,255,67,.45);background:linear-gradient(145deg,rgba(217,255,67,.07),#101f1a 60%)}.active-product>div b{color:var(--acid);border-color:rgba(217,255,67,.4)}.product-card button{align-self:flex-start;margin-top:auto;padding:13px 16px;border:0;background:var(--acid);color:#10170d;font:9px monospace;font-weight:800;text-transform:uppercase}.future-product{opacity:.82}.future-product small{margin-top:auto;color:#65736b;font:8px monospace;line-height:1.6}@media(max-width:900px){.product-roadmap{grid-template-columns:1fr}.product-cards{grid-template-columns:1fr 1fr}}@media(max-width:650px){.product-roadmap{padding:70px 20px}.product-cards{grid-template-columns:1fr}.product-card{min-height:280px}.product-card h3{margin-top:42px}}
.about{padding:115px 5vw;background:#eef2e9;color:#0d1713;display:grid;grid-template-columns:.85fr 1.15fr;gap:8vw}.about-lead h2{font-size:clamp(44px,5vw,72px);line-height:.96;letter-spacing:-.055em;margin:26px 0}.about-lead p{max-width:520px;color:#647168;font-size:15px;line-height:1.75}.about-values{display:grid;grid-template-columns:1fr 1fr;border-top:1px solid #bdc6bd;border-left:1px solid #bdc6bd}.about-values article{min-height:220px;padding:26px;border-right:1px solid #bdc6bd;border-bottom:1px solid #bdc6bd}.about-values span{font:9px monospace;color:#7b877f}.about-values h3{font-size:18px;margin:42px 0 12px}.about-values p{font-size:12px;line-height:1.65;color:#6a766e}.sales-proof{display:grid;grid-template-columns:repeat(3,1fr);background:#0c1814;border-top:1px solid #2c3c35;border-bottom:1px solid #2c3c35}.sales-proof>div{min-height:190px;padding:35px 5vw;border-right:1px solid #2c3c35;display:flex;flex-direction:column}.sales-proof span{font:8px monospace;color:var(--acid);letter-spacing:.1em}.sales-proof strong{font-size:17px;margin:38px 0 12px}.sales-proof small{font:9px monospace;color:#748179;line-height:1.6}@media(max-width:900px){.about{grid-template-columns:1fr}.sales-proof{grid-template-columns:1fr}.sales-proof>div{min-height:150px;border-right:0;border-bottom:1px solid #2c3c35}.sales-proof strong{margin-top:25px}}@media(max-width:650px){.about{padding:75px 20px}.about-values{grid-template-columns:1fr}.about-values article{min-height:190px}}

```

---

## `app\marketing.css`

```css
.brand-mark{width:34px!important;height:31px!important;position:relative!important;display:block!important;transform:none!important;filter:drop-shadow(0 0 8px rgba(217,255,67,.22))}
.brand-mark:before{content:"";position:absolute;inset:1px;border:1px solid rgba(217,255,67,.42);clip-path:polygon(50% 0,100% 28%,88% 85%,50% 100%,12% 85%,0 28%);background:linear-gradient(145deg,rgba(217,255,67,.12),transparent)}
.brand-mark i{position:absolute!important;display:block!important;background:var(--acid)!important;height:3px!important;transform-origin:center!important}
.brand-mark i:nth-child(1){width:19px!important;left:6px!important;top:9px!important;transform:rotate(-57deg) skew(-17deg)!important}
.brand-mark i:nth-child(2){width:16px!important;left:10px!important;top:15px!important;transform:rotate(57deg) skew(-17deg)!important}
.brand-mark i:nth-child(3){width:14px!important;left:11px!important;top:22px!important;transform:rotate(-57deg) skew(-17deg)!important;background:var(--mint)!important}
.brand>span:last-child{letter-spacing:-.045em}.topbar{background:rgba(7,16,14,.88);backdrop-filter:blur(18px);position:sticky;top:0}.nav-links a{position:relative}.nav-links a:after{content:"";position:absolute;left:0;right:100%;bottom:-9px;height:1px;background:var(--acid);transition:right .2s}.nav-links a:hover:after{right:0}
.hero{min-height:850px;background:radial-gradient(circle at 75% 35%,rgba(82,255,191,.11),transparent 30%),linear-gradient(135deg,#07100e,#091a15 65%,#07100e)}.hero:after{content:"AUTOVAD";position:absolute;right:-2vw;bottom:-3vw;color:transparent;-webkit-text-stroke:1px rgba(217,255,67,.045);font-size:16vw;font-weight:900;letter-spacing:-.08em;pointer-events:none}.hero-copy{max-width:680px}.hero h1{font-size:clamp(62px,6.8vw,108px);margin-bottom:25px}.hero h1 em{-webkit-text-stroke:1px rgba(217,255,67,.75)}.hero-actions{display:flex;align-items:center;gap:23px;margin:0 0 25px}.hero-actions a{color:#aebbb4;text-decoration:none;font:9px monospace;text-transform:uppercase;letter-spacing:.07em}.hero-actions a:hover{color:var(--acid)}.capability-chips{margin-bottom:22px!important}
.market-platform{padding:115px 5vw;background:#eef2e9;color:#0d1713}.market-intro{display:grid;grid-template-columns:1.1fr .9fr;gap:8vw;align-items:end;margin-bottom:70px}.market-intro h2{font-size:clamp(46px,5vw,76px);line-height:.94;letter-spacing:-.06em;margin:25px 0 0}.market-intro h2 span{color:#7c8880}.market-intro p{color:#647168;line-height:1.75;font-size:15px}.value-grid{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid #bcc5bc;border-left:1px solid #bcc5bc}.value-grid article{min-height:310px;padding:26px;border-right:1px solid #bcc5bc;border-bottom:1px solid #bcc5bc;display:flex;flex-direction:column}.value-grid article>span{font:9px monospace;color:#738078}.value-glyph{margin:36px 0 50px;width:44px;height:44px;display:grid;place-items:center;border:1px solid #93a198;color:#24382f;font-size:22px}.value-grid h3{font-size:18px;margin:0 0 12px}.value-grid p{font-size:12px;line-height:1.7;color:#6a766e;margin:0}.market-outcomes{display:grid;grid-template-columns:repeat(3,1fr);background:#0a1713;border-top:1px solid #2c4037;border-bottom:1px solid #2c4037}.market-outcomes>div{min-height:180px;padding:34px 5vw;border-right:1px solid #2c4037;display:flex;flex-direction:column;justify-content:space-between}.market-outcomes span{font:8px monospace;color:var(--acid);letter-spacing:.1em}.market-outcomes strong{max-width:290px;font-size:20px;line-height:1.25}
.industries{padding:110px 5vw;background:#07100e;display:grid;grid-template-columns:.8fr 1.2fr;gap:8vw}.industries-copy{position:sticky;top:130px;align-self:start}.industries-copy h2{font-size:clamp(44px,5vw,72px);line-height:.96;letter-spacing:-.055em;margin:25px 0}.industries-copy p{color:#839088;line-height:1.7;max-width:480px}.industries-copy a{display:inline-block;margin-top:20px;color:var(--acid);font:9px monospace;text-transform:uppercase;text-decoration:none}.industry-list{border-top:1px solid #31443b}.industry-list article{display:grid;grid-template-columns:50px 1fr;gap:10px 20px;padding:32px 0;border-bottom:1px solid #31443b}.industry-list article>span{grid-row:1/4;font:9px monospace;color:#66756d}.industry-list h3{font-size:24px;margin:0}.industry-list p{max-width:560px;margin:0;color:#819087;line-height:1.65;font-size:13px}.industry-list b{color:var(--acid);font:7px monospace;letter-spacing:.08em}
.faq-section{padding:105px 5vw;background:#e9eee6;color:#101a16;display:grid;grid-template-columns:.75fr 1.25fr;gap:8vw}.faq-section h2{font-size:clamp(42px,5vw,70px);line-height:.96;letter-spacing:-.055em;margin:25px 0}.faq-section>div:first-child p{max-width:480px;color:#68756d;line-height:1.7}.faq-list{border-top:1px solid #bdc6bd}.faq-list details{border-bottom:1px solid #bdc6bd;padding:0 4px}.faq-list summary{list-style:none;cursor:pointer;padding:25px 0;font-weight:bold;display:flex;justify-content:space-between;gap:20px}.faq-list summary::-webkit-details-marker{display:none}.faq-list summary span{color:#6b7d28;font-size:20px}.faq-list details[open] summary span{transform:rotate(45deg)}.faq-list p{color:#68756d;line-height:1.7;font-size:13px;max-width:650px;margin:0 0 25px}
.pricing{background:linear-gradient(180deg,#eef2e9,#e5ebe2)}.price-card.featured{box-shadow:0 28px 70px rgba(38,57,46,.14)}.closing{background:radial-gradient(circle at 80% 20%,rgba(217,255,67,.12),transparent 35%),#0a1713}
@media(max-width:1000px){.nav-links{display:none}.value-grid{grid-template-columns:1fr 1fr}.market-intro,.industries,.faq-section{grid-template-columns:1fr}.industries-copy{position:static}.hero{grid-template-columns:1fr}.product-stage{display:none}.hero-copy{max-width:760px}}
@media(max-width:650px){.hero{padding-top:65px}.hero-actions{align-items:flex-start;flex-direction:column}.market-platform,.industries,.faq-section{padding:75px 20px}.market-intro{grid-template-columns:1fr;margin-bottom:45px}.value-grid{grid-template-columns:1fr}.market-outcomes{grid-template-columns:1fr}.market-outcomes>div{min-height:135px;border-right:0;border-bottom:1px solid #2c4037}.industry-list article{grid-template-columns:35px 1fr}}

```

---

## `app\launch.css`

```css
.account-link{text-decoration:none;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.access-lock{width:min(620px,100%);margin-top:12px;padding:14px 16px;display:flex;align-items:center;gap:13px;border:1px solid #5f4932;background:#1b1711}.access-lock>span{padding:6px 7px;border:1px solid #8b6b40;color:#ffc36a;font:7px monospace}.access-lock>div{display:flex;flex-direction:column;gap:4px}.access-lock strong{font-size:11px}.access-lock small{color:#9e8e7a;font:8px monospace}.access-lock button{margin-left:auto;border:0;background:var(--acid);padding:10px 12px;color:#11170c;font:8px monospace;font-weight:800;text-transform:uppercase}.pricing{padding:115px 5vw;background:#f0f3eb;color:#0d1713}.pricing-head{display:grid;grid-template-columns:.25fr 1fr 1fr;gap:4vw;align-items:end;margin-bottom:65px}.pricing-head h2{font-size:clamp(44px,5vw,70px);line-height:.96;letter-spacing:-.055em;margin:0}.pricing-head p{color:#68746c;line-height:1.7;max-width:460px}.price-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;align-items:stretch}.price-card{position:relative;min-height:520px;padding:30px;display:flex;flex-direction:column;border:1px solid #c2cbc2;background:#f8faf5}.price-card>span{font:8px monospace;color:#718078;letter-spacing:.1em}.price-card h3{font-size:22px;margin:30px 0 20px}.plan-price{display:flex;align-items:end;gap:8px}.plan-price b{font-size:46px;letter-spacing:-.05em}.plan-price small{padding-bottom:8px;color:#728078;font:9px monospace}.price-card>p{font-size:12px;line-height:1.65;color:#6c786f;margin:22px 0}.price-card ul{list-style:none;padding:0;margin:12px 0 28px;color:#536158;font-size:12px;line-height:2}.price-card>a,.price-card>button{margin-top:auto;text-align:center;text-decoration:none;padding:14px;border:1px solid #25372f;background:transparent;color:#18271f;font:9px monospace;font-weight:800;text-transform:uppercase}.price-card.featured{background:#0e1b16;color:white;border-color:#8ba231;box-shadow:0 22px 55px rgba(22,39,31,.18)}.price-card.featured>p,.price-card.featured ul,.price-card.featured .plan-price small{color:#91a097}.price-card.featured>button{border:0;background:var(--acid);color:#10170d}.price-card button:disabled{opacity:.58}.popular{position:absolute;right:18px;top:18px;padding:6px 8px;background:var(--acid);color:#17200f;font:7px monospace}.pricing-note{display:block;margin-top:22px;color:#77837b;font:8px monospace}.contact-section{padding:110px 5vw;background:#091410;display:grid;grid-template-columns:1fr 1fr;gap:10vw}.contact-section h2{font-size:clamp(44px,5vw,70px);line-height:.96;letter-spacing:-.055em;margin:27px 0}.contact-section>div p{color:#849188;line-height:1.7;max-width:500px}.contact-section>div>a{color:var(--acid);font:12px monospace}.contact-section form{display:grid;grid-template-columns:1fr 1fr;gap:15px}.contact-section label{display:flex;flex-direction:column;gap:8px;color:#8b978f;font:8px monospace;text-transform:uppercase;letter-spacing:.08em}.contact-section label:last-of-type{grid-column:1/-1}.contact-section input,.contact-section textarea{width:100%;border:1px solid #34463e;background:#101f19;color:#ecf2ed;padding:13px;outline:none;font:12px Arial;resize:vertical}.contact-section input:focus,.contact-section textarea:focus{border-color:var(--acid)}.contact-section form button{justify-self:start;border:0;background:var(--acid);padding:14px 18px;color:#10170d;font:9px monospace;font-weight:800;text-transform:uppercase}.contact-section form>small{align-self:center;color:#9eaaa3;font:9px monospace}@media(max-width:900px){.pricing-head{grid-template-columns:1fr}.price-grid{grid-template-columns:1fr}.price-card{min-height:440px}.contact-section{grid-template-columns:1fr}.access-lock{align-items:flex-start;flex-wrap:wrap}.access-lock button{margin-left:0}}@media(max-width:650px){.pricing,.contact-section{padding:75px 20px}.contact-section form{grid-template-columns:1fr}.contact-section label:last-of-type{grid-column:auto}}

```

---

## `app\future.css`

```css
body{background:#040a08;background-image:radial-gradient(circle at 78% 8%,rgba(41,255,185,.11),transparent 28%),radial-gradient(circle at 8% 32%,rgba(217,255,67,.055),transparent 24%)}.app-shell{position:relative}.app-shell:before{content:"";position:fixed;inset:0;pointer-events:none;z-index:9999;opacity:.2;background:repeating-linear-gradient(0deg,transparent 0,transparent 3px,rgba(151,255,213,.025) 4px);mix-blend-mode:screen}.system-strip{height:28px;padding:0 4.5vw;display:flex;align-items:center;gap:14px;border-bottom:1px solid rgba(133,255,208,.16);background:#030806;color:#52665c;font:7px monospace;letter-spacing:.12em}.system-strip i{width:3px;height:3px;border-radius:50%;background:#577065}.system-strip b{margin-left:auto;color:var(--acid);font-weight:500}.system-strip b:before{content:"";display:inline-block;width:5px;height:5px;margin-right:7px;border-radius:50%;background:var(--acid);box-shadow:0 0 9px var(--acid);animation:systemPulse 2s ease-in-out infinite}.topbar{position:sticky!important;top:0;z-index:300!important;height:74px!important;background:rgba(4,12,9,.78);backdrop-filter:blur(20px) saturate(135%);border-bottom-color:rgba(133,255,208,.2)!important;box-shadow:0 16px 45px rgba(0,0,0,.22)}.brand-mark{filter:drop-shadow(0 0 8px rgba(217,255,67,.45))}.nav-links a{position:relative;font-family:monospace!important;text-transform:uppercase;letter-spacing:.06em;font-size:10px!important}.nav-links a:after{content:"";position:absolute;left:0;right:100%;bottom:-10px;height:1px;background:var(--acid);box-shadow:0 0 8px var(--acid);transition:right .2s}.nav-links a:hover:after{right:0}.outline-button,.solid-button,.price-card>button,.contact-section form button{clip-path:polygon(0 0,calc(100% - 9px) 0,100% 9px,100% 100%,9px 100%,0 calc(100% - 9px));box-shadow:inset 0 0 18px rgba(217,255,67,.08)}.hero{min-height:810px!important;padding-top:100px!important;border-bottom:1px solid rgba(133,255,208,.12);overflow:hidden}.hero:before{content:"AUTOVAD / CIVIL INTELLIGENCE / 01";position:absolute;right:4.5vw;top:28px;color:rgba(133,255,208,.3);font:7px monospace;letter-spacing:.18em}.grid-lines{opacity:1}.grid-lines:before{content:"";position:absolute;inset:0;background:linear-gradient(105deg,transparent 0 49.9%,rgba(217,255,67,.08) 50%,transparent 50.1%),radial-gradient(circle at 76% 38%,rgba(70,255,191,.14),transparent 22%)}.hero h1{text-shadow:0 10px 45px rgba(0,0,0,.45)}.hero h1 em{-webkit-text-stroke:1px rgba(217,255,67,.72)!important;filter:drop-shadow(0 0 16px rgba(217,255,67,.12))}.capability-chips{display:flex;gap:7px;flex-wrap:wrap;margin:-18px 0 24px}.capability-chips span{padding:7px 9px;border:1px solid rgba(133,255,208,.18);background:rgba(133,255,208,.025);color:#75877e;font:7px monospace;letter-spacing:.08em}.dropzone,.template-upload,.access-lock{position:relative;backdrop-filter:blur(14px);box-shadow:inset 0 0 25px rgba(133,255,208,.025),0 18px 50px rgba(0,0,0,.2);clip-path:polygon(0 0,calc(100% - 13px) 0,100% 13px,100% 100%,0 100%)}.dropzone:before{content:"";position:absolute;left:-1px;top:15px;width:2px;height:38px;background:var(--acid);box-shadow:0 0 12px var(--acid)}.upload-icon{clip-path:polygon(0 0,calc(100% - 8px) 0,100% 8px,100% 100%,0 100%);box-shadow:inset 0 0 18px rgba(217,255,67,.07)}.product-stage{filter:drop-shadow(0 40px 70px rgba(0,0,0,.38))}.plan-sheet{box-shadow:-24px 28px 90px rgba(0,0,0,.55),0 0 35px rgba(133,255,208,.08)!important}.analysis-card{backdrop-filter:blur(20px);background:rgba(5,16,12,.88)!important;clip-path:polygon(0 0,calc(100% - 14px) 0,100% 14px,100% 100%,0 100%)}.tag{backdrop-filter:blur(12px);box-shadow:0 10px 30px rgba(0,0,0,.25)}.workflow,.about,.pricing{background-color:#e9eee7;background-image:linear-gradient(rgba(20,50,38,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(20,50,38,.035) 1px,transparent 1px);background-size:32px 32px}.steps article,.about-values article,.price-card{transition:transform .22s ease,box-shadow .22s ease,border-color .22s ease}.steps article:hover,.about-values article:hover,.price-card:hover{transform:translateY(-4px)}.price-card:hover{box-shadow:0 25px 65px rgba(19,45,34,.15);border-color:#7b9186}.price-card.featured{background-image:radial-gradient(circle at 85% 8%,rgba(217,255,67,.12),transparent 28%),linear-gradient(145deg,#12241d,#08120e)}.price-card.featured:before{content:"";position:absolute;inset:-1px;pointer-events:none;background:linear-gradient(120deg,var(--acid),transparent 24%,transparent 78%,var(--mint));clip-path:polygon(0 0,100% 0,100% 1px,1px 1px,1px 100%,0 100%)}.sales-proof,.contact-section,.output{background-image:radial-gradient(circle at 12% 15%,rgba(133,255,208,.055),transparent 25%),linear-gradient(rgba(133,255,208,.018) 1px,transparent 1px),linear-gradient(90deg,rgba(133,255,208,.018) 1px,transparent 1px);background-size:auto,38px 38px,38px 38px}.bid-window{box-shadow:0 45px 110px rgba(0,0,0,.48),0 0 0 1px rgba(133,255,208,.05);clip-path:polygon(0 0,calc(100% - 15px) 0,100% 15px,100% 100%,0 100%)}.contact-section input,.contact-section textarea{box-shadow:inset 0 0 20px rgba(133,255,208,.015)}.closing{position:relative;overflow:hidden;background:linear-gradient(112deg,#d9ff43,#a8ff6a 52%,#85ffd0)!important}.closing:after{content:"";position:absolute;right:-6%;top:-170%;width:520px;height:520px;border:1px solid rgba(8,25,16,.16);border-radius:50%;box-shadow:0 0 0 45px rgba(8,25,16,.035),0 0 0 90px rgba(8,25,16,.025)}@keyframes systemPulse{0%,100%{opacity:.45}50%{opacity:1}}@media(max-width:650px){.system-strip span:nth-of-type(n+2),.system-strip i{display:none}.system-strip{padding:0 20px}.hero{padding-top:70px!important}.capability-chips{margin-top:-8px}.topbar{top:0}.app-shell:before{display:none}}@media(prefers-reduced-motion:reduce){.system-strip b:before{animation:none}.steps article,.about-values article,.price-card{transition:none}}

```

---

## `app\credits.css`

```css
@media(min-width:1101px){.price-grid{grid-template-columns:repeat(4,1fr)}.price-card{padding:26px;min-height:545px}.price-card h3{font-size:20px}.plan-price b{font-size:39px}}.credit-policy{display:grid;grid-template-columns:repeat(3,1fr);margin-top:18px;border:1px solid #c2cbc2;background:#e6ebe3}.credit-policy>div{padding:22px 25px;display:flex;flex-direction:column;gap:8px;border-right:1px solid #c2cbc2}.credit-policy>div:last-child{border-right:0}.credit-policy span{font:8px monospace;color:#66746c;letter-spacing:.1em}.credit-policy b{font-size:16px}.credit-policy small{font:9px monospace;color:#748078;line-height:1.55}@media(max-width:800px){.credit-policy{grid-template-columns:1fr}.credit-policy>div{border-right:0;border-bottom:1px solid #c2cbc2}.credit-policy>div:last-child{border-bottom:0}}
.account-ribbon{min-height:42px;position:sticky;top:0;z-index:30;display:flex;align-items:center;gap:24px;padding:0 4.5vw;border-bottom:1px solid rgba(217,255,67,.25);background:rgba(11,25,20,.97);backdrop-filter:blur(14px);font:9px monospace}.account-ribbon span{color:#85938b}.account-ribbon span b{color:var(--acid)}.account-ribbon a{color:#d6dfd9;text-decoration:none;padding:15px 0}.account-ribbon a:hover{color:var(--acid)}.account-ribbon i{margin-left:auto;color:#8f9d95;font-style:normal}.project-management{padding:95px 5vw;background:#e9eee6;color:#101a16;border-top:1px solid #c1cac1}.project-management-head{display:flex;align-items:end;justify-content:space-between;gap:30px;margin-bottom:34px}.project-management h2{font-size:clamp(38px,4vw,62px);letter-spacing:-.05em;margin:20px 0 12px}.project-management-head p{max-width:620px;color:#66736b;line-height:1.65}.project-management-head button{border:0;background:#101b16;color:var(--acid);padding:14px 18px;font:9px monospace;font-weight:bold;text-transform:uppercase}.project-list{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.saved-project,.project-empty{min-height:170px;padding:22px;border:1px solid #bdc7bd;background:#f5f7f1;color:#101a16;text-decoration:none;display:flex;flex-direction:column}.saved-project:hover{border-color:#6d822c;transform:translateY(-2px)}.saved-project span{font:8px monospace;color:#65736b}.saved-project strong{margin-top:34px;font-size:17px}.saved-project small{margin-top:8px;color:#748078;font:9px monospace}.saved-project time{margin-top:auto;color:#7f8a83;font:8px monospace}.project-empty{justify-content:center;gap:8px;color:#68746d}@media(max-width:850px){.account-ribbon{gap:14px;overflow-x:auto}.account-ribbon i{display:none}.project-list{grid-template-columns:1fr}.project-management-head{align-items:flex-start;flex-direction:column}}
.account-summary{display:flex;align-items:center;gap:11px;color:#eef4ef;text-decoration:none}.account-avatar{width:31px;height:31px;display:grid;place-items:center;border:1px solid rgba(217,255,67,.45);background:rgba(217,255,67,.08);color:var(--acid);font:11px monospace;font-weight:bold}.account-identity,.credit-summary{display:flex;flex-direction:column;gap:3px}.account-identity{max-width:155px;padding-right:13px;border-right:1px solid rgba(255,255,255,.12)}.account-summary small{color:#738078;font:6px monospace;letter-spacing:.08em}.account-summary b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font:9px monospace}.credit-summary{min-width:145px}.credit-summary b{color:var(--acid)}.credit-summary b i{color:#aab6af;font-style:normal;font-weight:normal}.credit-meter{width:100%;height:2px;background:#26342e}.credit-meter>i{display:block;height:100%;background:var(--acid);box-shadow:0 0 6px rgba(217,255,67,.6)}@media(max-width:720px){.account-identity{display:none}.credit-summary{min-width:128px}}

```

---

## `app\credit-buy.css`

```css
.credit-purchase{background:linear-gradient(145deg,rgba(217,255,67,.08),transparent)}.credit-purchase label{display:flex;align-items:center;justify-content:space-between;gap:14px;color:#66746c;font:8px monospace;text-transform:uppercase}.credit-entry{display:flex;align-items:stretch}.credit-purchase input{width:120px;padding:9px 10px;border:1px solid #aab6ad;background:#f4f7f1;color:#101b16;font:13px monospace;outline:none}.credit-purchase input:focus{border-color:#6f872b;box-shadow:0 0 0 2px rgba(217,255,67,.25)}.credit-purchase button{margin-top:5px;padding:10px 12px;border:0;background:#101b16;color:var(--acid);font:8px monospace;font-weight:800;text-transform:uppercase;clip-path:polygon(0 0,calc(100% - 7px) 0,100% 7px,100% 100%,0 100%)}.credit-purchase .credit-clear{margin:0;padding:0 10px;border:1px solid #aab6ad;border-left:0;background:#dfe5dc;color:#334039;clip-path:none}.credit-purchase button:disabled{opacity:.48;cursor:not-allowed}

```

---

## `lib\cadTakeoff.ts`

```ts
type Point = { x?: number; y?: number; z?: number };
type CadMetric = { layer: string; entityType: string; count: number; totalLength: number; totalArea: number; labels: string[] };

const distance = (a: Point, b: Point) => Math.hypot(Number(b.x) - Number(a.x), Number(b.y) - Number(a.y), Number(b.z || 0) - Number(a.z || 0));
const polygonArea = (points: Point[]) => Math.abs(points.reduce((sum, point, index) => {
  const next = points[(index + 1) % points.length];
  return sum + Number(point.x) * Number(next.y) - Number(next.x) * Number(point.y);
}, 0) / 2);

export async function prepareTakeoffSource(file: File) {
  if (/\.pdf$/i.test(file.name)) return "";
  if (/\.(dxf|xml|landxml)$/i.test(file.name)) {
    const text = await file.text();
    if (!text.trim()) throw new Error(`${file.name} does not contain readable design data.`);
    return `SOURCE FORMAT: ${file.name.split(".").pop()?.toUpperCase()}\nSOURCE FILE: ${file.name}\nThe following source is truncated only if it exceeds 150,000 characters. Parse entity/layer, alignment, pipe-network, surface, material, and quantity information conservatively.\n\n${text.slice(0, 150_000)}`;
  }
  if (!/\.dwg$/i.test(file.name)) throw new Error("Choose a PDF, DWG, DXF, LandXML, or XML design file.");

  const { LibreDwg, Dwg_File_Type } = await import("@mlightcad/libredwg-web");
  const reader = await LibreDwg.create();
  const pointer = reader.dwg_read_data(await file.arrayBuffer(), Dwg_File_Type.DWG);
  if (pointer === undefined) throw new Error(`${file.name} could not be decoded as a supported DWG drawing.`);
  try {
    const database = reader.convert(pointer) as unknown as { header?: unknown; entities?: Array<Record<string, any>> };
    const groups = new Map<string, CadMetric>();
    for (const item of database.entities || []) {
      const entityType = String(item.type || "UNKNOWN").toUpperCase();
      const layer = String(item.layer || "0");
      const key = `${layer}\u0000${entityType}`;
      const metric = groups.get(key) || { layer, entityType, count: 0, totalLength: 0, totalArea: 0, labels: [] };
      metric.count += 1;
      if (entityType === "LINE" && item.startPoint && item.endPoint) metric.totalLength += distance(item.startPoint, item.endPoint);
      const vertices: Point[] = ["LWPOLYLINE", "POLYLINE2D", "POLYLINE3D"].includes(entityType) ? item.vertices || [] : [];
      if (vertices.length > 1) {
        for (let index = 1; index < vertices.length; index++) metric.totalLength += distance(vertices[index - 1], vertices[index]);
        const closed = Boolean(item.closed || item.isClosed || item.flag === 1 || item.flags === 1);
        if (closed) { metric.totalLength += distance(vertices[vertices.length - 1], vertices[0]); metric.totalArea += polygonArea(vertices); }
      }
      if (entityType === "CIRCLE" && Number.isFinite(Number(item.radius))) {
        const radius = Number(item.radius); metric.totalLength += 2 * Math.PI * radius; metric.totalArea += Math.PI * radius * radius;
      }
      if (["TEXT", "MTEXT", "ATTRIB"].includes(entityType)) {
        const label = String(item.text || item.textValue || item.value || item.plainText || "").trim();
        if (label && metric.labels.length < 30 && !metric.labels.includes(label)) metric.labels.push(label.slice(0, 180));
      }
      groups.set(key, metric);
    }
    if (!groups.size) throw new Error(`${file.name} did not contain recognizable DWG entities.`);
    return JSON.stringify({
      sourceFormat: "DWG", filename: file.name,
      measurementUnits: "native drawing units; infer a named unit only when explicitly supported by DWG metadata or labels",
      entityCount: (database.entities || []).length,
      header: database.header,
      metricsByLayerAndEntity: Array.from(groups.values()).map((metric) => ({ ...metric, totalLength: Number(metric.totalLength.toFixed(4)), totalArea: Number(metric.totalArea.toFixed(4)) })),
    }).slice(0, 150_000);
  } finally { reader.dwg_free(pointer); }
}

```

---

## `lib\conceptDesign.ts`

```ts
import type { DesignCommandIntent } from "./designCommands";

export type ConceptArtifact = {
  id: string;
  discipline: string;
  label: string;
  color: string;
  generatedAt: string;
  data: GeoJSON.FeatureCollection;
};

type Bounds = { north: number; south: number; east: number; west: number };
const feature = (geometry: GeoJSON.Geometry, properties: Record<string, unknown>): GeoJSON.Feature => ({ type: "Feature", geometry, properties });

const feetBetween = (a: [number, number], b: [number, number]) => {
  const lat = (a[1] + b[1]) / 2 * Math.PI / 180;
  return Math.hypot((b[0] - a[0]) * 111_320 * Math.cos(lat), (b[1] - a[1]) * 111_320) * 3.28084;
};

const stationFeatures = (alignment: [number, number][]) => {
  const features: GeoJSON.Feature[] = [];
  const segments = alignment.slice(1).map((point, index) => feetBetween(alignment[index], point));
  const total = segments.reduce((sum, length) => sum + length, 0);
  for (let station = 0; station <= total; station += 50) {
    let remaining = station; let segment = 0;
    while (segment < segments.length - 1 && remaining > segments[segment]) { remaining -= segments[segment]; segment += 1; }
    const start = alignment[segment]; const end = alignment[segment + 1]; const ratio = Math.min(1, remaining / Math.max(segments[segment], .001));
    const lng = start[0] + (end[0] - start[0]) * ratio; const lat = start[1] + (end[1] - start[1]) * ratio;
    const dx = end[0] - start[0]; const dy = end[1] - start[1]; const norm = Math.hypot(dx * Math.cos(lat * Math.PI / 180), dy) || 1;
    const major = station % 100 === 0; const tickFeet = major ? 18 : 10; const meters = tickFeet / 3.28084;
    const offsetLat = dx * Math.cos(lat * Math.PI / 180) / norm * meters / 111_320;
    const offsetLng = -dy / norm * meters / (111_320 * Math.cos(lat * Math.PI / 180));
    features.push(feature({ type: "LineString", coordinates: [[lng - offsetLng, lat - offsetLat], [lng + offsetLng, lat + offsetLat]] }, { role: "station-tick", major, station }));
    if (major) features.push(feature({ type: "Point", coordinates: [lng + offsetLng * 1.8, lat + offsetLat * 1.8] }, { role: "station-label", station, label: `${Math.floor(station / 100)}+${String(station % 100).padStart(2, "0")}` }));
  }
  return features;
};

export function createConceptArtifacts(intents: DesignCommandIntent[], bounds: Bounds, mappedRoadGeometry?: [number, number][]): ConceptArtifact[] {
  const x = (ratio: number) => bounds.west + (bounds.east - bounds.west) * ratio;
  const y = (ratio: number) => bounds.south + (bounds.north - bounds.south) * ratio;
  const now = new Date().toISOString();
  const artifacts: ConceptArtifact[] = [];
  const add = (discipline: string, label: string, color: string, features: GeoJSON.Feature[]) => artifacts.push({ id: `${discipline}-${Date.now()}-${artifacts.length}`, discipline, label, color, generatedAt: now, data: { type: "FeatureCollection", features } });

  if (intents.includes("road-design") || intents.includes("access")) {
    const inside = (mappedRoadGeometry || []).filter(([lng, lat]) => lng >= bounds.west && lng <= bounds.east && lat >= bounds.south && lat <= bounds.north);
    const alignment = (inside.length >= 2 ? inside : mappedRoadGeometry && mappedRoadGeometry.length >= 2 ? mappedRoadGeometry : [[x(.08), y(.42)], [x(.35), y(.5)], [x(.65), y(.54)], [x(.92), y(.68)]]) as [number, number][];
    add("road", "Mapped-road centerline alignment + 50/100 ft stationing", "#d9ff43", [feature({ type: "LineString", coordinates: alignment }, { role: "centerline", source: mappedRoadGeometry?.length ? "OpenStreetMap roadway geometry" : "preliminary fallback" }), ...stationFeatures(alignment)]);
  }
  if (intents.includes("stormwater")) add("storm", "Concept storm sewer", "#25d4ae", [
    feature({ type: "LineString", coordinates: [[x(.18), y(.78)], [x(.38), y(.58)], [x(.6), y(.4)], [x(.82), y(.2)]] }, { role: "storm-main" }),
    ...[[.18,.78],[.38,.58],[.6,.4],[.82,.2]].map(([a,b]) => feature({ type: "Point", coordinates: [x(a), y(b)] }, { role: "inlet" })),
  ]);
  if (intents.includes("sanitary-sewer")) add("sanitary", "Concept sanitary sewer", "#d853ff", [
    feature({ type: "LineString", coordinates: [[x(.12), y(.32)], [x(.36), y(.38)], [x(.62), y(.31)], [x(.9), y(.18)]] }, { role: "sanitary-main" }),
    ...[[.12,.32],[.36,.38],[.62,.31],[.9,.18]].map(([a,b]) => feature({ type: "Point", coordinates: [x(a), y(b)] }, { role: "manhole" })),
  ]);
  if (intents.includes("water-system")) add("water", "Concept water distribution loop", "#168cff", [
    feature({ type: "LineString", coordinates: [[x(.15),y(.2)],[x(.85),y(.2)],[x(.85),y(.8)],[x(.15),y(.8)],[x(.15),y(.2)]] }, { role: "water-main" }),
    ...[[.15,.2],[.85,.2],[.85,.8],[.15,.8]].map(([a,b]) => feature({ type: "Point", coordinates: [x(a), y(b)] }, { role: "hydrant" })),
  ]);
  if (intents.includes("detention-pond")) add("detention", "Concept detention facility", "#35b9ff", [
    feature({ type: "Polygon", coordinates: [[[x(.62),y(.12)],[x(.9),y(.14)],[x(.86),y(.36)],[x(.68),y(.4)],[x(.58),y(.26)],[x(.62),y(.12)]]] }, { role: "pond" }),
    feature({ type: "Point", coordinates: [x(.88), y(.16)] }, { role: "outfall" }),
  ]);
  if (intents.includes("grading") || intents.includes("drainage-analysis")) add("drainage", "Concept drainage paths", "#ffb347", [
    feature({ type: "LineString", coordinates: [[x(.18),y(.82)],[x(.42),y(.58)],[x(.65),y(.35)],[x(.86),y(.16)]] }, { role: "flow-path" }),
    feature({ type: "LineString", coordinates: [[x(.78),y(.84)],[x(.68),y(.6)],[x(.65),y(.35)]] }, { role: "flow-path" }),
  ]);
  return artifacts;
}

```

---

## `lib\designCommands.ts`

```ts
export type DesignCommandIntent =
  | "site-layout"
  | "grading"
  | "stormwater"
  | "sanitary-sewer"
  | "water-system"
  | "detention-pond"
  | "drainage-analysis"
  | "utilities"
  | "access"
  | "road-design"
  | "plan-production"
  | "parking"
  | "survey-control"
  | "general";

export type DesignCommandAnalysis = {
  intents: DesignCommandIntent[];
  primaryIntent: DesignCommandIntent;
  confidence: number;
  detectedValues: string[];
  missingInputs: string[];
};

const commandPatterns: Array<{ intent: DesignCommandIntent; pattern: RegExp }> = [
  { intent: "plan-production", pattern: /\b(plan set|plan sheet|construction plan|sheet set|title block|annotation|label(?:s|ing)?|plan and profile|plan\/profile|cross section|quantity table|bid tab|drafting standard)\b/i },
  { intent: "road-design", pattern: /\b(road|roadway|street|boulevard|avenue|collector|arterial|local street|cul[- ]de[- ]sac|lane width|right[- ]of[- ]way|row|design speed|horizontal curve|vertical curve)\b/i },
  { intent: "grading", pattern: /\b(grade|grading|elevation|slope|earthwork|cut|fill|retaining|finished[- ]floor|ffe)\b/i },
  { intent: "detention-pond", pattern: /\b(detention|retention|detention pond|retention pond)\b/i },
  { intent: "drainage-analysis", pattern: /\b(drainage analysis|watershed|drainage area|hydrology|hydraulic|runoff|rational method)\b/i },
  { intent: "sanitary-sewer", pattern: /\b(sanitary sewer|wastewater|sanitary main|manhole)\b/i },
  { intent: "water-system", pattern: /\b(water system|water distribution|water main|waterline|hydrant|fire flow)\b/i },
  { intent: "stormwater", pattern: /\b(storm|storm sewer|drain|drainage|inlet|culvert|outfall|water quality)\b/i },
  { intent: "utilities", pattern: /\b(utility|utilities|waterline|water main|sanitary|sewer|gas|electric|fire flow|tie[- ]in)\b/i },
  { intent: "access", pattern: /\b(access|entrance|driveway|curb cut|truck court|fire lane|turning|intersection)\b/i },
  { intent: "parking", pattern: /\b(parking|spaces|stalls|ada|accessible parking|loading)\b/i },
  { intent: "survey-control", pattern: /\b(survey|boundary|benchmark|control point|landxml|topo|topographic|coordinates)\b/i },
  { intent: "site-layout", pattern: /\b(layout|site plan|building|warehouse|retail|commercial|residential|footprint|pad|subdivision)\b/i },
];

const requiredInputs: Record<DesignCommandIntent, string[]> = {
  "site-layout": ["proposed use and footprint", "setbacks", "access requirements"],
  grading: ["survey surface", "finished-floor target", "maximum slopes"],
  stormwater: ["governing storm event", "allowable outfall", "release-rate criteria"],
  "sanitary-sewer": ["design flow", "connection point and invert", "minimum slope and cover criteria"],
  "water-system": ["demand and fire flow", "connection pressure", "pipe and hydrant criteria"],
  "detention-pond": ["hydrology and storm events", "allowable release rate", "outfall and geotechnical constraints"],
  "drainage-analysis": ["survey surface", "drainage criteria", "outfall and watershed limits"],
  utilities: ["utility connection points", "utility criteria", "easements"],
  access: ["access points", "design vehicle", "fire-access criteria"],
  "road-design": ["road classification", "right-of-way width", "design speed and vehicle", "lane and shoulder section", "grading and drainage criteria"],
  "plan-production": ["verified design geometry", "sheet scale and deliverable format", "governing drafting and jurisdiction standards"],
  parking: ["required parking count", "stall criteria", "ADA requirements"],
  "survey-control": ["coordinate system", "survey control", "existing-conditions surface"],
  general: ["proposed use", "survey base", "jurisdiction criteria"],
};

export function analyzeDesignCommand(message: string, filenames: string[], hasLocation: boolean): DesignCommandAnalysis {
  const intents = commandPatterns.filter(({ pattern }) => pattern.test(message)).map(({ intent }) => intent);
  if (!intents.length) intents.push("general");
  const detectedValues = Array.from(message.matchAll(/\b\d[\d,]*(?:\.\d+)?\s*(?:sf|sq\.?\s*ft|acres?|spaces?|stalls?|lanes?|mph|ft|feet|%|inches?|in)\b/gi), (match) => match[0]);
  if (hasLocation) detectedValues.push("geospatial project area");
  if (filenames.some((name) => /\.(xml|landxml|csv|dwg|dxf)$/i.test(name))) detectedValues.push("survey/CAD source");
  if (filenames.some((name) => /\.(pdf|docx?|txt)$/i.test(name))) detectedValues.push("criteria document");
  if (filenames.some((name) => /(?:plan|bid|certified).*\.pdf$/i.test(name))) detectedValues.push("reference plan set");
  const missingInputs = requiredInputs[intents[0]].filter((input) => {
    if (input.includes("survey") && filenames.some((name) => /\.(xml|landxml|csv|dwg|dxf|pdf)$/i.test(name))) return false;
    if (input.includes("access") && /\b(access|entrance|driveway|curb cut|fire lane)\b/i.test(message)) return false;
    if (input.includes("parking") && /\b\d+\s*(spaces?|stalls?)\b/i.test(message)) return false;
    if (input.includes("footprint") && /\b\d[\d,]*\s*(sf|sq\.?\s*ft)\b/i.test(message)) return false;
    if (input.includes("right-of-way") && /\b\d+(?:\.\d+)?\s*(ft|feet|')?\s*(right[- ]of[- ]way|row)\b/i.test(message)) return false;
    if (input.includes("design speed") && /\b\d+(?:\.\d+)?\s*mph\b/i.test(message)) return false;
    if (input.includes("lane") && /\b\d+(?:\.\d+)?\s*(ft|feet|')?\s*(lane|shoulder)/i.test(message)) return false;
    return true;
  });
  return {
    intents,
    primaryIntent: intents[0],
    confidence: Math.min(0.96, 0.56 + Math.min(3, intents.length) * 0.1 + Math.min(2, detectedValues.length) * 0.08),
    detectedValues,
    missingInputs,
  };
}

```

---

## `lib\surveyImport.ts`

```ts
import { parseSurveyXml, type SurveyDataset, type SurveyLine, type SurveyPoint } from "./surveyXml";

type Row = Record<string, unknown>;
const aliases = { northing: ["northing", "north", "y", "latitude", "lat"], easting: ["easting", "east", "x", "longitude", "lon", "lng"], elevation: ["elevation", "elev", "z", "level", "rl"], id: ["point", "pointno", "pointnumber", "pointid", "id", "name", "number"], description: ["description", "desc", "code", "feature", "layer"] };
const normalized = (value: string) => value.toLowerCase().replace(/[^a-z0-9]/g, "");
const findColumn = (row: Row, options: string[]) => Object.keys(row).find((key) => options.includes(normalized(key)));
const numeric = (value: unknown) => typeof value === "number" ? value : Number(String(value ?? "").replace(/,/g, "").trim());
const metadataDetection = (text: string) => {
  const epsg = text.match(/EPSG\s*[:=#]?\s*(\d{4,6})/i)?.[1] || null;
  const vertical = text.match(/\b(NAVD\s*88|NGVD\s*29|EGM\s*2008|EGM\s*1996|IGLD\s*85|MLLW|MLW|MTL|MHW|MHHW)\b/i)?.[1]?.replace(/\s/g, "").toUpperCase() || null;
  const units = /\b(meters?|metres?)\b/i.test(text) ? "Meters" : /\b(?:us\s*survey\s*)?(?:feet|foot|ft)\b/i.test(text) ? "US survey feet" : undefined;
  return { epsg, vertical, units };
};

function finish(filename: string, format: string, points: SurveyPoint[], breaklines: SurveyLine[] = [], contours: SurveyLine[] = []): SurveyDataset {
  const all = [...points.map((point) => [point.northing, point.easting] as const), ...breaklines.flatMap((line) => line.points.map((point) => [point[0], point[1]] as const)), ...contours.flatMap((line) => line.points.map((point) => [point[0], point[1]] as const))];
  if (!all.length) throw new Error(`${filename} did not contain recognizable survey coordinates.`);
  const bounds = { minNorthing: Math.min(...all.map((point) => point[0])), maxNorthing: Math.max(...all.map((point) => point[0])), minEasting: Math.min(...all.map((point) => point[1])), maxEasting: Math.max(...all.map((point) => point[1])) };
  const geographic = all.every(([northing, easting]) => Math.abs(northing) <= 90 && Math.abs(easting) <= 180);
  const duplicateCount = points.length - new Set(points.map((point) => `${point.northing.toFixed(6)}:${point.easting.toFixed(6)}`)).size;
  const missingElevations = points.filter((point) => point.elevation === null).length;
  const warnings: string[] = [];
  if (duplicateCount) warnings.push(`${duplicateCount} duplicate point coordinate${duplicateCount === 1 ? "" : "s"}`);
  if (missingElevations) warnings.push(`${missingElevations} point${missingElevations === 1 ? "" : "s"} without elevation`);
  if (bounds.maxNorthing === bounds.minNorthing || bounds.maxEasting === bounds.minEasting) warnings.push("coordinate extent has zero width or height");
  const checks = [`${all.length} coordinate records are numeric and finite`, `Extent N/Y ${bounds.minNorthing.toFixed(3)}â€“${bounds.maxNorthing.toFixed(3)}`, `Extent E/X ${bounds.minEasting.toFixed(3)}â€“${bounds.maxEasting.toFixed(3)}`];
  return { filename, coordinateSystem: geographic ? "Geographic coordinate range detected (CRS confirmation required)" : "Not declared", geographic, points, breaklines, contours, bounds, importValidation: { status: geographic ? (warnings.length ? "warning" : "verified") : "needs-crs", checks, warnings, sourceFormat: format } };
}

function rowsToDataset(filename: string, format: string, rows: Row[]) {
  const sample = rows.find((row) => Object.values(row).some((value) => String(value ?? "").trim()));
  if (!sample) throw new Error(`${filename} does not contain survey rows.`);
  const northing = findColumn(sample, aliases.northing); const easting = findColumn(sample, aliases.easting);
  if (!northing || !easting) throw new Error(`${filename} needs Northing/Easting, Y/X, or Latitude/Longitude columns.`);
  const elevation = findColumn(sample, aliases.elevation); const id = findColumn(sample, aliases.id); const description = findColumn(sample, aliases.description);
  const points = rows.map((row, index) => ({ id: String(id ? row[id] || `P${index + 1}` : `P${index + 1}`), northing: numeric(row[northing]), easting: numeric(row[easting]), elevation: elevation && Number.isFinite(numeric(row[elevation])) ? numeric(row[elevation]) : null, description: description ? String(row[description] || "") : "" })).filter((point) => Number.isFinite(point.northing) && Number.isFinite(point.easting));
  return finish(filename, format, points);
}

async function parseTabular(file: File) {
  const XLSX = await import("xlsx");
  const workbook = XLSX.read(await file.arrayBuffer(), { type: "array", cellDates: false });
  const grids = workbook.SheetNames.map((sheetName) => XLSX.utils.sheet_to_json<unknown[]>(workbook.Sheets[sheetName], { header: 1, defval: "" }));
  const metadata = metadataDetection(grids.flat(2).map(String).join(" "));
  const rows: Row[] = grids.flatMap((grid) => {
    const headerIndex = grid.findIndex((row) => { const cells = row.map((cell) => normalized(String(cell))); return aliases.northing.some((name) => cells.includes(name)) && aliases.easting.some((name) => cells.includes(name)); });
    if (headerIndex < 0) return [];
    const headers = grid[headerIndex].map(String);
    return grid.slice(headerIndex + 1).map((values) => Object.fromEntries(headers.map((header, index) => [header, values[index]])));
  });
  const dataset = rowsToDataset(file.name, file.name.split(".").pop()?.toUpperCase() || "TABULAR", rows);
  dataset.coordinateSystem = metadata.epsg ? `EPSG:${metadata.epsg}` : dataset.coordinateSystem; dataset.verticalDatum = metadata.vertical || undefined; dataset.verticalUnits = metadata.units;
  dataset.crsDetection = { horizontal: metadata.epsg ? `EPSG:${metadata.epsg}` : null, vertical: metadata.vertical, confidence: metadata.epsg ? "high" : "low", evidence: [metadata.epsg ? `Workbook metadata contains EPSG:${metadata.epsg}` : "No EPSG code found in workbook", metadata.vertical ? `Workbook metadata contains ${metadata.vertical}` : "No vertical datum found in workbook"], requiresConfirmation: !metadata.epsg };
  return dataset;
}

async function parseDwg(file: File) {
  const { LibreDwg, Dwg_File_Type } = await import("@mlightcad/libredwg-web");
  const reader = await LibreDwg.create();
  const pointer = reader.dwg_read_data(await file.arrayBuffer(), Dwg_File_Type.DWG);
  if (pointer === undefined) throw new Error(`${file.name} could not be decoded as a supported DWG drawing.`);
  try {
    const database = reader.convert(pointer); const points: SurveyPoint[] = []; const breaklines: SurveyLine[] = []; const contours: SurveyLine[] = [];
    database.entities.forEach((entity, index) => {
      const item = entity as unknown as Record<string, any>; const layer = String(item.layer || "");
      if (item.type === "POINT" && item.position) points.push({ id: item.handle || `P${index + 1}`, northing: item.position.y, easting: item.position.x, elevation: Number.isFinite(item.position.z) ? item.position.z : null, description: layer });
      let vertices: Array<{ x: number; y: number; z?: number }> = [];
      if (item.type === "LINE") vertices = [item.startPoint, item.endPoint];
      if (["LWPOLYLINE", "POLYLINE2D", "POLYLINE3D"].includes(item.type)) vertices = item.vertices || [];
      if (vertices.length > 1) { const line = { id: item.handle || `${item.type}-${index + 1}`, points: vertices.map((vertex) => [vertex.y, vertex.x, Number.isFinite(vertex.z) ? vertex.z : Number.isFinite(item.elevation) ? item.elevation : null] as [number, number, number | null]) }; (/contour|topo/i.test(layer) ? contours : breaklines).push(line); }
    });
    const dataset = finish(file.name, "DWG", points, breaklines, contours);
    const detected = metadataDetection(JSON.stringify(database.header));
    dataset.coordinateSystem = detected.epsg ? `EPSG:${detected.epsg}` : dataset.coordinateSystem; dataset.verticalDatum = detected.vertical || undefined; dataset.verticalUnits = detected.units;
    dataset.crsDetection = { horizontal: detected.epsg ? `EPSG:${detected.epsg}` : null, vertical: detected.vertical, confidence: detected.epsg ? "high" : "low", evidence: [detected.epsg ? `DWG header contains EPSG:${detected.epsg}` : "DWG has no machine-readable EPSG code", detected.vertical ? `DWG header contains ${detected.vertical}` : "DWG has no machine-readable vertical datum"], requiresConfirmation: !detected.epsg };
    return dataset;
  } finally { reader.dwg_free(pointer); }
}

export async function parseSurveyFile(file: File): Promise<SurveyDataset | null> {
  if (/\.(xml|landxml)$/i.test(file.name)) {
    const dataset = await parseSurveyXml(file); if (!dataset) return null;
    const checked = finish(dataset.filename, "LANDXML", dataset.points, dataset.breaklines, dataset.contours);
    return { ...checked, coordinateSystem: dataset.coordinateSystem, geographic: dataset.geographic, verticalDatum: dataset.verticalDatum, verticalUnits: dataset.verticalUnits, crsDetection: dataset.crsDetection };
  }
  if (/\.(xlsx|xls|csv|tsv)$/i.test(file.name)) return parseTabular(file);
  if (/\.dwg$/i.test(file.name)) return parseDwg(file);
  return null;
}

export async function alignDeclaredSurveyCrs(dataset: SurveyDataset): Promise<SurveyDataset> {
  if (dataset.geographic || dataset.transformed) return dataset;
  const match = dataset.coordinateSystem.match(/(?:EPSG\s*[:#]?\s*)?(\d{4,6})/i);
  if (!match) return dataset;
  try {
    const response = await fetch(`/api/gis/crs?code=${encodeURIComponent(match[1])}`);
    const resolved = await response.json() as { code?: string; name?: string; definition?: string; error?: string };
    if (!response.ok || !resolved.code || !resolved.definition) throw new Error(resolved.error || "Declared CRS could not be resolved.");
    const module = await import("proj4"); const proj4 = module.default; proj4.defs(resolved.code, resolved.definition);
    const transform = (northing: number, easting: number) => proj4(resolved.code!, "EPSG:4326", [easting, northing]) as [number, number];
    const updated: SurveyDataset = { ...dataset, coordinateSystem: `${resolved.code} Â· ${resolved.name || ""}`, transformed: true, points: dataset.points.map((point) => ({ ...point, wgs84: transform(point.northing, point.easting) })), breaklines: dataset.breaklines.map((line) => ({ ...line, wgs84: line.points.map((point) => transform(point[0], point[1])) })), contours: dataset.contours.map((line) => ({ ...line, wgs84: line.points.map((point) => transform(point[0], point[1])) })) };
    const invalid = updated.points.some((point) => !point.wgs84 || Math.abs(point.wgs84[1]) > 90 || Math.abs(point.wgs84[0]) > 180);
    if (invalid) throw new Error("Declared CRS produced coordinates outside WGS 84 limits.");
    if (updated.importValidation) { updated.importValidation.status = updated.importValidation.warnings.length ? "warning" : "verified"; updated.importValidation.checks.push(`${resolved.code} resolved and transformed to WGS 84`); }
    return updated;
  } catch (error) {
    const warning = error instanceof Error ? error.message : "Declared CRS could not be applied.";
    return { ...dataset, importValidation: { ...(dataset.importValidation || { status: "needs-crs", checks: [], warnings: [], sourceFormat: "SURVEY" }), status: "warning", warnings: [...(dataset.importValidation?.warnings || []), warning] } };
  }
}

export function crossCheckSurveyLocation(dataset: SurveyDataset, selected: { lat: number; lng: number } | null): SurveyDataset {
  if (!selected || (!dataset.geographic && !dataset.transformed)) return dataset;
  const positions = dataset.points.map((point) => point.wgs84 || (dataset.geographic ? [point.easting, point.northing] as [number, number] : null)).filter((point): point is [number, number] => Boolean(point));
  if (!positions.length) return dataset;
  const center = { lng: positions.reduce((sum, point) => sum + point[0], 0) / positions.length, lat: positions.reduce((sum, point) => sum + point[1], 0) / positions.length };
  const radians = (value: number) => value * Math.PI / 180; const dLat = radians(center.lat - selected.lat); const dLng = radians(center.lng - selected.lng);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(radians(selected.lat)) * Math.cos(radians(center.lat)) * Math.sin(dLng / 2) ** 2;
  const distanceKm = 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  const validation = dataset.importValidation || { status: "verified" as const, checks: [], warnings: [], sourceFormat: "SURVEY" };
  validation.checks = [...validation.checks, `Survey centroid cross-checked against selected project location (${distanceKm.toFixed(1)} km)`];
  if (distanceKm > 50) { validation.status = "warning"; validation.warnings = [...validation.warnings, `Survey is ${distanceKm.toFixed(1)} km from the selected project location; confirm CRS and coordinate order`]; if (dataset.crsDetection) { dataset.crsDetection.confidence = "low"; dataset.crsDetection.requiresConfirmation = true; } }
  else if (dataset.crsDetection?.horizontal) { dataset.crsDetection.requiresConfirmation = false; dataset.crsDetection.evidence.push("Transformed survey is consistent with the selected project location"); }
  return { ...dataset, importValidation: validation };
}

export async function autoConvertDeclaredElevations(dataset: SurveyDataset): Promise<SurveyDataset> {
  const sourceDatum = dataset.verticalDatum?.toUpperCase();
  if (!sourceDatum || sourceDatum === "NAVD88" || (!dataset.geographic && !dataset.transformed)) return dataset;
  const supported = new Set(["NGVD29", "EGM2008", "EGM1996", "IGLD85", "MLLW", "MLW", "MTL", "MHW", "MHHW"]);
  const unitCode: Record<string, string> = { "US survey feet": "us_ft", "International feet": "ft", Meters: "m" };
  if (!supported.has(sourceDatum) || !dataset.verticalUnits || !unitCode[dataset.verticalUnits]) return dataset;
  const coordinate = (northing: number, easting: number, wgs84?: [number, number]): [number, number] | null => wgs84 || (dataset.geographic ? [easting, northing] : null);
  type Ref = { kind: "point" | "breakline" | "contour"; index: number; pointIndex?: number; lng: number; lat: number; elevation: number };
  const refs: Ref[] = [];
  dataset.points.forEach((point, index) => { const at = coordinate(point.northing, point.easting, point.wgs84); if (at && point.elevation !== null) refs.push({ kind: "point", index, lng: at[0], lat: at[1], elevation: point.elevation }); });
  (["breaklines", "contours"] as const).forEach((kind) => dataset[kind].forEach((line, index) => line.points.forEach((point, pointIndex) => { const at = coordinate(point[0], point[1], line.wgs84?.[pointIndex]); if (at && point[2] !== null) refs.push({ kind: kind === "breaklines" ? "breakline" : "contour", index, pointIndex, lng: at[0], lat: at[1], elevation: point[2] }); })));
  if (!refs.length) return dataset;
  const sample = refs[0]; const region = sample.lat > 50 ? "ak" : sample.lng > 140 ? "gcnmi" : sample.lat < 20 && sample.lng < -60 ? "prvi" : "contiguous";
  const values: Array<{ elevation: number; uncertainty: number | null }> = []; let metadata: { source?: string; convertedAt?: string } = {};
  for (let start = 0; start < refs.length; start += 200) {
    const response = await fetch("/api/gis/vertical-datum", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ points: refs.slice(start, start + 200), sourceDatum, targetDatum: "NAVD88", sourceUnit: unitCode[dataset.verticalUnits], targetUnit: unitCode[dataset.verticalUnits], region }) });
    const result = await response.json() as { results?: Array<{ elevation: number; uncertainty: number | null }>; source?: string; convertedAt?: string; error?: string };
    if (!response.ok || !result.results) { const warning = result.error || "Automatic elevation conversion was unavailable."; return { ...dataset, importValidation: { ...(dataset.importValidation || { status: "warning", checks: [], warnings: [], sourceFormat: "SURVEY" }), status: "warning", warnings: [...(dataset.importValidation?.warnings || []), warning] } }; }
    values.push(...result.results); metadata = result;
  }
  const points = dataset.points.map((point) => ({ ...point })); const breaklines = dataset.breaklines.map((line) => ({ ...line, convertedElevations: line.points.map(() => null) })); const contours = dataset.contours.map((line) => ({ ...line, convertedElevations: line.points.map(() => null) }));
  refs.forEach((ref, index) => { if (ref.kind === "point") points[ref.index].convertedElevation = values[index].elevation; else (ref.kind === "breakline" ? breaklines : contours)[ref.index].convertedElevations![ref.pointIndex!] = values[index].elevation; });
  const uncertainties = values.map((value) => value.uncertainty).filter((value): value is number => value !== null); const maximumUncertainty = uncertainties.length ? Math.max(...uncertainties) : null;
  return { ...dataset, points, breaklines, contours, verticalDatum: "NAVD88", elevationConversion: { sourceDatum, targetDatum: "NAVD88", sourceUnit: dataset.verticalUnits, targetUnit: dataset.verticalUnits, region, source: metadata.source || "NOAA VDatum", convertedAt: metadata.convertedAt || new Date().toISOString(), maximumUncertainty }, importValidation: dataset.importValidation ? { ...dataset.importValidation, checks: [...dataset.importValidation.checks, `${refs.length} elevations automatically converted ${sourceDatum}â†’NAVD88`] } : dataset.importValidation };
}

```

---

## `lib\surveyXml.ts`

```ts
export type SurveyPoint = { id: string; northing: number; easting: number; elevation: number | null; convertedElevation?: number | null; description: string; wgs84?: [number, number] };
export type SurveyLine = { id: string; points: Array<[number, number, number | null]>; convertedElevations?: Array<number | null>; wgs84?: Array<[number, number]> };
export type SurveyDataset = {
  filename: string;
  coordinateSystem: string;
  geographic: boolean;
  points: SurveyPoint[];
  breaklines: SurveyLine[];
  contours: SurveyLine[];
  bounds: { minNorthing: number; maxNorthing: number; minEasting: number; maxEasting: number } | null;
  transformed?: boolean;
  horizontalUnits?: string;
  verticalDatum?: string;
  verticalUnits?: string;
  elevationConversion?: { sourceDatum: string; targetDatum: string; sourceUnit: string; targetUnit: string; region: string; source: string; convertedAt: string; maximumUncertainty: number | null };
  importValidation?: { status: "verified" | "needs-crs" | "warning"; checks: string[]; warnings: string[]; sourceFormat: string };
  crsDetection?: { horizontal: string | null; vertical: string | null; confidence: "high" | "medium" | "low"; evidence: string[]; requiresConfirmation: boolean };
};

const localName = (element: Element) => element.localName.toLowerCase();
const numbers = (text: string | null) => (text || "").trim().split(/[\s,]+/).map(Number).filter(Number.isFinite);

export async function parseSurveyXml(file: File): Promise<SurveyDataset | null> {
  if (!/\.(xml|landxml)$/i.test(file.name)) return null;
  const document = new DOMParser().parseFromString(await file.text(), "application/xml");
  if (document.querySelector("parsererror")) throw new Error(`${file.name} is not valid XML.`);
  const elements = Array.from(document.getElementsByTagName("*"));
  const coordinateElement = elements.find((element) => localName(element) === "coordinatesystem");
  const metadata = elements.flatMap((element) => [element.textContent || "", ...Array.from(element.attributes).map((attribute) => `${attribute.name}=${attribute.value}`)]).join(" ");
  const epsg = coordinateElement?.getAttribute("epsgCode") || metadata.match(/EPSG\s*[:=#]?\s*(\d{4,6})/i)?.[1] || null;
  const coordinateSystem = epsg ? `EPSG:${epsg}` : coordinateElement?.getAttribute("name") || coordinateElement?.getAttribute("desc") || "Not declared";
  const verticalDatum = metadata.match(/\b(NAVD\s*88|NGVD\s*29|EGM\s*2008|EGM\s*1996|IGLD\s*85|MLLW|MLW|MTL|MHW|MHHW)\b/i)?.[1]?.replace(/\s/g, "").toUpperCase();
  const unitMatch = metadata.match(/(?:linearUnit|elevationUnit|verticalUnit|unit)\s*=\s*["']?([^\s"']+)/i)?.[1]?.toLowerCase();
  const verticalUnits = unitMatch?.includes("meter") ? "Meters" : unitMatch?.includes("foot") || unitMatch?.includes("feet") ? "US survey feet" : undefined;
  const points = elements.filter((element) => ["cgpoint", "surveypoint", "point"].includes(localName(element))).map((element, index) => {
    const values = numbers(element.textContent);
    if (values.length < 2) return null;
    return { id: element.getAttribute("name") || element.getAttribute("id") || `P${index + 1}`, northing: values[0], easting: values[1], elevation: values[2] ?? null, description: element.getAttribute("desc") || element.getAttribute("code") || "" };
  }).filter((point): point is SurveyPoint => Boolean(point));
  const readLines = (names: string[]): SurveyLine[] => elements.filter((element) => names.includes(localName(element))).map((element, index) => {
    const list = Array.from(element.getElementsByTagName("*")).find((child) => ["pntlist3d", "pntlist2d", "coordgeom"].includes(localName(child)));
    const values = numbers(list?.textContent || element.textContent);
    const stride = values.length % 3 === 0 ? 3 : 2;
    const linePoints: Array<[number, number, number | null]> = [];
    for (let i = 0; i + 1 < values.length; i += stride) linePoints.push([values[i], values[i + 1], stride === 3 ? values[i + 2] : null]);
    return linePoints.length > 1 ? { id: element.getAttribute("name") || `${names[0]}-${index + 1}`, points: linePoints } : null;
  }).filter((line): line is SurveyLine => Boolean(line));
  const breaklines = readLines(["breakline", "breaklinepnts", "boundary"]);
  const contours = readLines(["contour"]);
  const all = [...points.map((point) => [point.northing, point.easting] as const), ...breaklines.flatMap((line) => line.points.map((point) => [point[0], point[1]] as const)), ...contours.flatMap((line) => line.points.map((point) => [point[0], point[1]] as const))];
  const bounds = all.length ? { minNorthing: Math.min(...all.map((point) => point[0])), maxNorthing: Math.max(...all.map((point) => point[0])), minEasting: Math.min(...all.map((point) => point[1])), maxEasting: Math.max(...all.map((point) => point[1])) } : null;
  const sample = all[0];
  const geographic = Boolean(sample && Math.abs(sample[0]) <= 90 && Math.abs(sample[1]) <= 180);
  return { filename: file.name, coordinateSystem, geographic, points, breaklines, contours, bounds, verticalDatum, verticalUnits, crsDetection: { horizontal: epsg ? `EPSG:${epsg}` : coordinateSystem === "Not declared" ? null : coordinateSystem, vertical: verticalDatum || null, confidence: epsg ? "high" : "low", evidence: [epsg ? `Embedded EPSG code ${epsg}` : "No embedded EPSG code", verticalDatum ? `Embedded vertical datum ${verticalDatum}` : "No embedded vertical datum"], requiresConfirmation: !epsg } };
}

export function surveySummary(dataset: SurveyDataset) {
  const elevations = dataset.points.map((point) => point.convertedElevation ?? point.elevation).filter((value): value is number => value !== null);
  const conversion = dataset.elevationConversion;
  return `${dataset.filename}: ${dataset.points.length} survey points, ${dataset.breaklines.length} breaklines, ${dataset.contours.length} contours; coordinate system ${dataset.coordinateSystem}; ${dataset.geographic ? "geographic coordinates" : "projected/local coordinates"}${elevations.length ? `; elevation range ${Math.min(...elevations).toFixed(2)} to ${Math.max(...elevations).toFixed(2)} ${dataset.verticalUnits || ""}` : ""}${conversion ? `; elevations converted from ${conversion.sourceDatum} to ${conversion.targetDatum} by ${conversion.source}${conversion.maximumUncertainty === null ? "" : ` (maximum reported uncertainty ${conversion.maximumUncertainty})`}` : dataset.verticalDatum ? `; vertical datum ${dataset.verticalDatum}` : ""}.`;
}

```

---

## `lib\gis.ts`

```ts
export type UtilityKind = "water" | "sanitary" | "storm" | "gas" | "electric" | "communications" | "unknown";

export type UtilityLayer = {
  name: string;
  kind: UtilityKind;
  source: string;
  featureCount: number;
  data: GeoJSON.FeatureCollection;
};

export type UtilityQueryResult = {
  configured: boolean;
  layers: UtilityLayer[];
  totalFeatures: number;
  warnings: string[];
  message: string;
};

export const utilityColors: Record<UtilityKind, string> = {
  water: "#168cff",
  sanitary: "#d853ff",
  storm: "#25d4ae",
  gas: "#ffd238",
  electric: "#ff4b3e",
  communications: "#ff8fd8",
  unknown: "#ffffff",
};

```

---

## `public\favicon.svg`

```xml
<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M22 19.2727C22 20.779 20.779 22 19.2727 22H14.7273C13.221 22 12 20.779 12 19.2727V12H19.2727C20.779 12 22 13.221 22 14.7273V19.2727Z" fill="#68C4FF"/>
<path d="M20 2C21.1046 2 22 2.89543 22 4V7C22 8.10457 21.1046 9 20 9H17C15.8954 9 15 8.10457 15 7V4C15 2.89543 15.8954 2 17 2H20Z" fill="#0C79D8"/>
<path d="M7 15C8.10457 15 9 15.8954 9 17V20C9 21.1046 8.10457 22 7 22H4C2.89543 22 2 21.1046 2 20V17C2 15.8954 2.89543 15 4 15H7Z" fill="#0C79D8"/>
<path d="M12 12H4.72727C3.22104 12 2 10.779 2 9.27273V4.72727C2 3.22104 3.22104 2 4.72727 2H9.27273C10.779 2 12 3.22104 12 4.72727V12Z" fill="#2E9EFF"/>
</svg>

```

