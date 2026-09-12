/* Moodily site JS — progressive enhancement only. Every link/form works without it except the form's async submit. */
(function () {
  'use strict';
  var root = document.documentElement;
  window.dataLayer = window.dataLayer || [];

  // ---------- analytics: data-track="event" data-label="..." (see _project/03-forms-payments-analytics.md)
  function track(event, params) {
    var payload = { event: event, page_path: location.pathname };
    for (var k in params) if (Object.prototype.hasOwnProperty.call(params, k)) payload[k] = params[k];
    window.dataLayer.push(payload);
  }
  window.moodilyTrack = track;

  document.addEventListener('click', function (ev) {
    var el = ev.target.closest('[data-track]');
    if (!el) return;
    track(el.getAttribute('data-track'), {
      label: el.getAttribute('data-label') || '',
      link_url: el.getAttribute('href') || ''
    });
  });

  var body = document.body;
  if (body.hasAttribute('data-view-event')) {
    track(body.getAttribute('data-view-event'), { label: body.getAttribute('data-view-label') || '' });
  }

  // product_view: fire once per product card when 50% visible
  if ('IntersectionObserver' in window) {
    var seen = {};
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        var slug = en.target.getAttribute('data-product');
        if (en.isIntersecting && !seen[slug]) { seen[slug] = 1; track('product_view', { label: slug }); io.unobserve(en.target); }
      });
    }, { threshold: 0.5 });
    document.querySelectorAll('[data-product]').forEach(function (el) { io.observe(el); });
  }

  // ---------- storage helpers (may throw in private mode)
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }

  // ---------- theme
  var themeBtn = document.getElementById('themeToggle');
  if (themeBtn) themeBtn.addEventListener('click', function () {
    var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    store('moodily_theme', next);
  });

  // ---------- language (only on bilingual pages)
  var langBtn = document.getElementById('langToggle');
  if (langBtn) langBtn.addEventListener('click', function () {
    var next = root.getAttribute('data-lang') === 'en' ? 'hi' : 'en';
    root.setAttribute('data-lang', next);
    store('moodily_lang', next);
    track('language_switch', { label: next });
  });

  // ---------- legacy anchors from the old single-page site
  var legacy = { '#curriculum': '/learn/#curriculum', '#learn': '/learn/', '#services': '/services/ai-workflows/', '#linkedin': '/services/professionals/#linkedin', '#tools': '/tools/', '#intake': '/contact/', '#weekly-tip': '/learn/#weekly-tip', '#why': '/about/' };
  if (location.pathname === '/' && legacy[location.hash]) location.replace(legacy[location.hash]);

  // ---------- learn: expand/collapse + private star rating (kept from original site)
  document.querySelectorAll('[data-stages]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var open = btn.getAttribute('data-stages') === 'open';
      document.querySelectorAll('details.stage').forEach(function (d) { d.open = open; });
    });
  });
  function paintStars(id) {
    var val = parseInt(store('moodily_rating_' + id) || '0', 10);
    document.querySelectorAll('.star[data-stage="' + id + '"]').forEach(function (s) {
      var on = parseInt(s.getAttribute('data-value'), 10) <= val;
      s.classList.toggle('filled', on);
      s.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    var label = document.getElementById('ratingLabel-' + id);
    if (label) label.textContent = val ? 'Your rating: ' + val + '/5' : '';
  }
  var stageIds = {};
  document.querySelectorAll('.star').forEach(function (s) {
    var id = s.getAttribute('data-stage');
    stageIds[id] = 1;
    s.addEventListener('click', function () { store('moodily_rating_' + id, s.getAttribute('data-value')); paintStars(id); });
  });
  Object.keys(stageIds).forEach(paintStars);

  // ---------- lead form
  var form = document.getElementById('leadForm');
  if (form) initForm(form);

  function initForm(form) {
    var params = new URLSearchParams(location.search);
    var svc = params.get('service');
    var sel = form.querySelector('#f-service');
    if (svc && sel && sel.querySelector('option[value="' + CSS.escape(svc) + '"]')) sel.value = svc;

    var started = false;
    form.addEventListener('input', function () {
      if (started) return;
      started = true;
      track('form_start', { label: sel ? sel.value : '' });
    });

    var err = document.getElementById('formError');
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      if (form.company_hp && form.company_hp.value) return; // bot
      var firstBad = null;
      Array.prototype.forEach.call(form.elements, function (el) {
        if (!el.willValidate) return;
        var ok = el.checkValidity();
        el.setAttribute('aria-invalid', ok ? 'false' : 'true');
        if (!ok && !firstBad) firstBad = el;
      });
      if (firstBad) {
        err.hidden = false;
        err.textContent = 'कृपया सभी ज़रूरी (*) fields सही भरें। Please complete the required fields.';
        firstBad.focus();
        return;
      }
      err.hidden = true;
      var data = new FormData(form);
      data.delete('company_hp');
      data.append('page', location.pathname + location.search);
      data.append('submitted_at', new Date().toISOString());
      var summary = {};
      data.forEach(function (v, k) { summary[k] = v; });
      if (sel && sel.selectedIndex >= 0) summary.service_label = sel.options[sel.selectedIndex].text;
      try { sessionStorage.setItem('moodily_lead', JSON.stringify(summary)); } catch (e) {}

      var endpoint = form.getAttribute('data-endpoint');
      var btn = form.querySelector('button[type="submit"]');
      btn.disabled = true;
      btn.textContent = 'भेज रहे हैं…';
      var done = function (status) {
        track('form_submit', { label: summary.service || '', budget: summary.budget || '', role: summary.role || '', delivery: status });
        location.href = form.getAttribute('data-success') + '?s=' + status;
      };
      if (!endpoint) { done('whatsapp'); return; }
      // Google Apps Script web app: no-cors POST (opaque response). CRM/n8n: swap endpoint, keep field names.
      fetch(endpoint, { method: 'POST', mode: 'no-cors', body: new URLSearchParams(data) })
        .then(function () { done('sent'); })
        .catch(function () { done('whatsapp'); });
    });
  }

  // ---------- thank-you page: WhatsApp fallback built from sessionStorage (never from URL)
  var thanks = document.getElementById('thanksWa');
  if (thanks) {
    var lead = null;
    try { lead = JSON.parse(sessionStorage.getItem('moodily_lead') || 'null'); } catch (e) {}
    var status = new URLSearchParams(location.search).get('s');
    if (status === 'sent') {
      document.getElementById('thanksSent').hidden = false;
      document.getElementById('thanksMustWa').hidden = true;
    }
    if (lead) {
      var msg = 'Namaste Moodily,\nMain ' + (lead.name || '') + ' (' + (lead.role || '') + ') hoon.\nMujhe ' + (lead.service_label || lead.service || '') + ' chahiye.\nGoal: ' + (lead.goal || '') +
        '\nCity: ' + (lead.city || '') + '\nBudget approx: ' + (lead.budget || '') + '\nDeadline: ' + (lead.deadline || '') +
        '\nCurrent website/social link: ' + (lead.link || '-') + '\nLanguage: ' + (lead.language || '') + (lead.message ? '\nMessage: ' + lead.message : '');
      var base = thanks.getAttribute('href').split('?')[0];
      thanks.setAttribute('href', base + '?text=' + encodeURIComponent(msg));
    }
  }
})();
