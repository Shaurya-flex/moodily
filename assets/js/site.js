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

  // ---------- founding offer countdown (fixed deadline from src/site.json — never resets per visitor)
  var offerEnds = root.getAttribute('data-offer-ends');
  if (offerEnds) {
    var endAt = Date.parse(offerEnds);
    var countdowns = document.querySelectorAll('[data-countdown]');
    var pad = function (n) { return (n < 10 ? '0' : '') + n; };
    var timer;
    var tick = function () {
      var ms = endAt - Date.now();
      if (ms <= 0) { root.classList.add('offer-ended'); clearInterval(timer); return; }
      var d = Math.floor(ms / 864e5), h = Math.floor(ms % 864e5 / 36e5), m = Math.floor(ms % 36e5 / 6e4), s = Math.floor(ms % 6e4 / 1e3);
      var txt = (d ? d + ' दिन ' : '') + pad(h) + ':' + pad(m) + ':' + pad(s);
      countdowns.forEach(function (c) { c.textContent = txt; });
    };
    timer = setInterval(tick, 1000);
    tick();
    if (!root.classList.contains('offer-ended') && document.querySelector('.offer-banner, .offer-section, .offer-note')) {
      track('offer_view', { label: root.getAttribute('data-offer-id') || '' });
    }
  }

  // ---------- Razorpay Standard Checkout (buttons exist only when payments are enabled — see _project/06)
  var checkoutButtons = document.querySelectorAll('[data-checkout]');
  if (checkoutButtons.length) {
    var loadCheckout = function () {
      return new Promise(function (resolve, reject) {
        if (window.Razorpay) return resolve();
        var s = document.createElement('script');
        s.src = 'https://checkout.razorpay.com/v1/checkout.js';
        s.onload = resolve;
        s.onerror = function () { reject(new Error('Razorpay checkout load नहीं हुआ')); };
        document.head.appendChild(s);
      });
    };
    var postJSON = function (url, data) {
      return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
        .then(function (r) {
          return r.json().catch(function () { return {}; }).then(function (b) {
            if (!r.ok) throw new Error(b.error || 'Server error (' + r.status + ')');
            return b;
          });
        });
    };
    checkoutButtons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var api = btn.getAttribute('data-api') || '';
        var base = api === '/' ? '' : api.replace(/\/$/, '');
        var serviceId = btn.getAttribute('data-checkout');
        var label = btn.textContent;
        var msg = btn.parentNode.querySelector('.pay-msg[data-for="' + serviceId + '"]');
        if (!msg) {
          msg = document.createElement('p');
          msg.className = 'pay-msg';
          msg.setAttribute('role', 'alert');
          msg.setAttribute('data-for', serviceId);
          btn.parentNode.appendChild(msg);
        }
        var failed = false;
        var show = function (text) { msg.textContent = text; };
        var reset = function () { btn.disabled = false; btn.textContent = label; };
        btn.disabled = true;
        btn.textContent = 'Checkout खुल रहा है…';
        show('');
        Promise.all([loadCheckout(), postJSON(base + '/api/create-order', { service_id: serviceId })])
          .then(function (res) {
            var order = res[1];
            var rzp = new window.Razorpay({
              key: order.key_id,
              amount: order.amount,
              currency: order.currency,
              order_id: order.order_id,
              name: order.name || 'Moodily',
              description: order.description,
              notes: { service_id: serviceId },
              theme: { color: '#7B2FFF' },
              handler: function (resp) {
                btn.textContent = 'Payment verify हो रहा है…';
                postJSON(base + '/api/verify-payment', {
                  razorpay_order_id: resp.razorpay_order_id,
                  razorpay_payment_id: resp.razorpay_payment_id,
                  razorpay_signature: resp.razorpay_signature
                }).then(function (v) {
                  track('payment_success', { label: serviceId });
                  try { sessionStorage.setItem('moodily_payment', JSON.stringify({ service: order.description, order_id: v.order_id, payment_id: v.payment_id })); } catch (e) {}
                  location.href = '/payment/success/';
                }).catch(function (err) {
                  track('payment_verify_failed', { label: serviceId });
                  reset();
                  show('Payment verify नहीं हो सका (' + err.message + ')। कृपया Payment ID ' + resp.razorpay_payment_id + ' के साथ WhatsApp करें — हम dashboard में जाँच करेंगे।');
                });
              },
              modal: {
                ondismiss: function () {
                  track('payment_dismissed', { label: serviceId });
                  reset();
                  if (!failed) show('Payment cancel हो गया। आप दोबारा कोशिश कर सकते हैं या WhatsApp पर पूछ सकते हैं।');
                }
              }
            });
            rzp.on('payment.failed', function (r) {
              failed = true;
              track('payment_failed', { label: serviceId, reason: (r.error && r.error.reason) || '' });
              show('Payment fail हुआ: ' + ((r.error && r.error.description) || 'कृपया दोबारा कोशिश करें') + '। पैसा कटा हो तो bank उसे अपने-आप लौटा देता है।');
            });
            rzp.open();
            btn.textContent = label;
          })
          .catch(function (err) {
            reset();
            show('Checkout शुरू नहीं हो सका: ' + err.message);
          });
      });
    });
  }

  // ---------- payment success page (details from sessionStorage, never from URL)
  var payOk = document.getElementById('payOk');
  if (payOk) {
    var pay = null;
    try { pay = JSON.parse(sessionStorage.getItem('moodily_payment') || 'null'); } catch (e) {}
    if (pay && pay.payment_id) {
      payOk.hidden = false;
      document.getElementById('payUnknown').hidden = true;
      document.getElementById('payService').textContent = pay.service || '';
      document.getElementById('payOrder').textContent = pay.order_id;
      document.getElementById('payId').textContent = pay.payment_id;
      var payWa = document.getElementById('payWa');
      payWa.setAttribute('href', payWa.getAttribute('href').split('?')[0] + '?text=' + encodeURIComponent(
        'Namaste Moodily,\nMaine ' + (pay.service || '') + ' ka payment kar diya hai.\nOrder ID: ' + pay.order_id + '\nPayment ID: ' + pay.payment_id + '\nOnboarding shuru karein.'));
    }
  }

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
    var offerId = form.getAttribute('data-offer-id');
    if (offerId && params.get('offer') === offerId) {
      form.querySelector('#f-offer').value = offerId;
      document.getElementById('offerNote').hidden = false;
    }

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
        '\nCurrent website/social link: ' + (lead.link || '-') + (lead.offer ? '\nOffer: ' + lead.offer : '') + '\nLanguage: ' + (lead.language || '') + (lead.message ? '\nMessage: ' + lead.message : '');
      var base = thanks.getAttribute('href').split('?')[0];
      thanks.setAttribute('href', base + '?text=' + encodeURIComponent(msg));
    }
  }
})();
