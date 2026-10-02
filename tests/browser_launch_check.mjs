// Browser checks for the International launch gate (local only; needs Google Chrome and Node >= 22).
// usage: node tests/browser_launch_check.mjs <base-url> <out.json>
//   e.g. node tests/browser_launch_check.mjs http://127.0.0.1:8124 /tmp/launch-browser.json
// Runs every /international/ page at 1440 / 768 / 390 / 375 px: horizontal overflow, console errors, broken images,
// empty links and preview wording; axe-core accessibility (serious/critical) at desktop; then privacy tests that feed
// fake personal data through the International form and the India thanks / payment-success pages and confirm none of it
// reaches the dataLayer, storage, cookies or this site's URL. Analytics (GTM) is blocked so tests never reach real GA.
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [base, out] = process.argv.slice(2);
if (!base || !out) { console.error("usage: node tests/browser_launch_check.mjs <base-url> <out.json>"); process.exit(2); }
const PAGES = ["", "services/", "pricing/", "process/", "industries/", "customer-education/", "educators-consultants/", "clinics/",
  "work/", "journey-audit/", "about/", "contact/", "terms/", "privacy/", "refund/", "payments/", "pay/",
  // optional extra site paths, e.g. EXTRA_PAGES=/store/,/store/some-product/
  ...(process.env.EXTRA_PAGES || "").split(",").filter(Boolean)];
const pagePath = (p) => (p.startsWith("/") ? p : "/international/" + p);
const VIEWPORTS = { desktop: [1440, 900, false], tablet: [768, 1024, true], m390: [390, 844, true], m375: [375, 812, true], m360: [360, 780, true] };
const PREVIEW_WORDS = /private preview|owner approval|draft price|hypothes|approval required|owner blocker|coming after approval|preview:/i;
const FAKE = { name: "ZZTESTNAME Person", email: "zztest.person@example.com", company: "ZZTESTCO Ltd", phone: "ZZPHONE5550100",
  message: "ZZTESTMESSAGE please call ZZPHONE5550100", order: "order_ZZTESTORDER01", payment: "pay_ZZTESTPAY01" };
const FAKE_RE = /ZZTEST|zztest\.person|ZZPHONE|order_ZZTEST|pay_ZZTEST/;

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const prof = mkdtempSync(join(tmpdir(), "launchcheck-"));
const port = 9400 + Math.floor(Math.random() * 300);
const chrome = spawn(CHROME, ["--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", `--user-data-dir=${prof}`,
  `--remote-debugging-port=${port}`, "--host-resolver-rules=MAP www.googletagmanager.com 127.0.0.1, MAP lmsqueezy.com 127.0.0.1", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let wsUrl;
for (let i = 0; i < 60 && !wsUrl; i++) { await sleep(250); try { wsUrl = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find((x) => x.type === "page")?.webSocketDebuggerUrl; } catch {} }
const ws = new WebSocket(wsUrl);
await new Promise((r) => ws.addEventListener("open", r));
let id = 0; const pending = new Map(); const events = []; const consoleErrors = []; const requests = [];
ws.addEventListener("message", (m) => {
  const d = JSON.parse(m.data);
  if (d.id && pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); return; }
  if (!d.method) return;
  events.push(d.method);
  if (d.method === "Runtime.exceptionThrown") consoleErrors.push(d.params.exceptionDetails?.exception?.description || d.params.exceptionDetails?.text);
  if (d.method === "Runtime.consoleAPICalled" && d.params.type === "error") consoleErrors.push(d.params.args.map((a) => a.value || a.description).join(" "));
  if (d.method === "Network.requestWillBeSent") requests.push({ url: d.params.request.url, post: d.params.request.postData || "" });
});
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const evaluate = async (expression) => (await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true })).result?.result?.value;
await send("Page.enable"); await send("Runtime.enable"); await send("Network.enable");

async function go(url, vp) {
  const [w, h, mobile] = vp;
  await send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile });
  events.length = 0; consoleErrors.length = 0;
  await send("Page.navigate", { url });
  for (let i = 0; i < 100 && !events.includes("Page.loadEventFired"); i++) await sleep(100);
  await sleep(600);
}

const results = { base, when: new Date().toISOString(), pages: [], a11y: [], privacy: [] };

// 1. layout / errors / images / links / preview wording at four widths
for (const p of PAGES) {
  for (const [vname, vp] of Object.entries(VIEWPORTS)) {
    await go(`${base}${pagePath(p)}`, vp);
    const r = await evaluate(`(() => {
      const de = document.documentElement;
      const brokenImgs = [...document.images].filter(i => i.complete && i.naturalWidth === 0).map(i => i.getAttribute('src'));
      const emptyLinks = [...document.querySelectorAll('a')].filter(a => !a.getAttribute('href') || a.getAttribute('href') === '#').length;
      const text = document.body.innerText;
      return { overflow: de.scrollWidth > de.clientWidth + 1, scrollW: de.scrollWidth, clientW: de.clientWidth, brokenImgs, emptyLinks,
               preview: location.pathname.startsWith('/international/') && ((${PREVIEW_WORDS}).test(text) || !!document.querySelector('.preview-note,.intl-preview-banner,.draft-chip')),
               h1: document.querySelectorAll('h1').length, lang: de.lang, title: document.title };
    })()`);
    results.pages.push({ page: pagePath(p), viewport: vname, ...r, consoleErrors: [...consoleErrors] });
  }
}

// 2. accessibility (axe-core, desktop)
for (const p of PAGES) {
  await go(`${base}${pagePath(p)}`, VIEWPORTS.desktop);
  const v = await evaluate(`new Promise((resolve) => {
    const s = document.createElement('script');
    s.src = 'https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js';
    s.onload = () => axe.run(document, { runOnly: ['wcag2a', 'wcag2aa'] }).then(r => resolve(r.violations.filter(v => v.impact === 'serious' || v.impact === 'critical')
      .map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.length, sample: v.nodes[0] && v.nodes[0].target.join(' ') }))));
    s.onerror = () => resolve([{ id: 'axe-load-failed', impact: 'n/a', nodes: 0 }]);
    document.head.appendChild(s);
  })`);
  results.a11y.push({ page: pagePath(p), violations: v });
}

// 3. privacy tests
async function privacyProbe(label, extra = "") {
  const r = await evaluate(`(() => {
    const dl = JSON.stringify(window.dataLayer || []);
    const store = JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage });
    return { dataLayerLeak: ${FAKE_RE}.test(dl), storageLeak: ${FAKE_RE}.test(store), cookieLeak: ${FAKE_RE}.test(document.cookie),
             urlLeak: ${FAKE_RE}.test(location.href), events: (window.dataLayer || []).filter(e => e.event && !String(e.event).startsWith('gtm')).map(e => e.event) ${extra} };
  })()`);
  const netLeak = requests.some((q) => FAKE_RE.test(q.url) && !q.url.startsWith("mailto:") && !q.url.startsWith("https://wa.me/") || FAKE_RE.test(q.post));
  results.privacy.push({ test: label, ...r, networkLeak: netLeak });
}

// 3a. International form: email path, WhatsApp path, copy path
requests.length = 0;
await go(`${base}/international/contact/?type=journey-audit`, VIEWPORTS.desktop);
await evaluate(`(() => {
  window.__opened = []; window.open = (u) => { window.__opened.push(String(u)); return null; };
  const set = (id, v) => { const el = document.getElementById(id); el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); };
  set('in-name', ${JSON.stringify(FAKE.name)}); set('in-email', ${JSON.stringify(FAKE.email)}); set('in-company', ${JSON.stringify(FAKE.company)});
  set('in-website', 'https://zztest.example'); set('in-desc', ${JSON.stringify(FAKE.message)});
  document.getElementById('in-budget').selectedIndex = 2; document.getElementById('in-timeline').selectedIndex = 1;
  document.getElementById('intlWa').click();
  return true;
})()`);
await sleep(300);
await privacyProbe("intl-form-whatsapp", `, preselectedType: document.getElementById('in-type').value, waOpenedWithOwnMessage: (window.__opened[0]||'').startsWith('https://wa.me/') `);
await evaluate(`document.getElementById('intlIntake').requestSubmit(); true`);
await sleep(600);
await privacyProbe("intl-form-email", `, resultShown: !document.getElementById('intlResult').hidden `);

// 3b. India thanks page (WhatsApp hand-off built from the visitor's own details)
requests.length = 0;
await go(`${base}/contact/thanks/`, VIEWPORTS.desktop);
await evaluate(`sessionStorage.setItem('moodily_lead', JSON.stringify({ name: ${JSON.stringify(FAKE.name)}, role: 'owner', service: 'business-website', city: 'ZZTESTCITY', budget: 'ZZTESTBUDGET', goal: 'g', message: ${JSON.stringify(FAKE.message)} })); true`);
await go(`${base}/contact/thanks/`, VIEWPORTS.desktop);
await evaluate(`document.addEventListener('click', e => e.preventDefault(), true); document.getElementById('thanksWa').click(); sessionStorage.removeItem('moodily_lead'); true`);
await privacyProbe("india-thanks-whatsapp");

// 3c. India payment success (order / payment IDs)
requests.length = 0;
await go(`${base}/payment/success/`, VIEWPORTS.desktop);
await evaluate(`sessionStorage.setItem('moodily_payment', JSON.stringify({ service: 'Test', order_id: ${JSON.stringify(FAKE.order)}, payment_id: ${JSON.stringify(FAKE.payment)} })); true`);
await go(`${base}/payment/success/`, VIEWPORTS.desktop);
await evaluate(`document.addEventListener('click', e => e.preventDefault(), true); const a = document.getElementById('payWa'); if (a) a.click(); sessionStorage.removeItem('moodily_payment'); true`);
await privacyProbe("india-payment-success");

// 3d. International project payment page with a reference in the URL: stripped from the address bar, no analytics loaded
requests.length = 0;
await go(`${base}/international/pay/?p=MI-ZZTEST-0001&t=zztesttoken`, VIEWPORTS.desktop);
const pay = await evaluate(`({ urlAfter: location.href, gtmLoaded: !!document.querySelector('script[src*="googletagmanager"]'), dataLayerEvents: (window.dataLayer||[]).length })`);
results.privacy.push({ test: "intl-pay-reference", ...pay, urlLeak: /ZZTEST|zztest/.test(pay.urlAfter) });

writeFileSync(out, JSON.stringify(results, null, 1));
ws.close(); chrome.kill(); await sleep(300); rmSync(prof, { recursive: true, force: true });
const bad = results.pages.filter((r) => r.overflow || r.brokenImgs.length || r.emptyLinks || r.preview || r.consoleErrors.length || r.h1 !== 1);
const a11yBad = results.a11y.filter((r) => r.violations.length);
const privBad = results.privacy.filter((r) => r.dataLayerLeak || r.storageLeak || r.cookieLeak || r.urlLeak || r.networkLeak || r.gtmLoaded);
console.log(`pages×viewports: ${results.pages.length}, issues: ${bad.length} · a11y pages with serious/critical: ${a11yBad.length} · privacy failures: ${privBad.length}/${results.privacy.length}`);
process.exit(bad.length || a11yBad.length || privBad.length ? 1 : 0);
