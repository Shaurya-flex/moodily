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

  // ---------- menu: popover on desktop, drawer on phones.
  // <details> still works with JS off; this adds backdrop, Escape, click-outside,
  // focus management and a body-scroll lock while it is open.
  var menu = document.getElementById('siteMenu');
  if (menu) {
    var summary = menu.querySelector('summary');
    var panel = menu.querySelector('.menu-panel');
    var backdrop = null, scrollY = 0;

    function focusables() {
      return panel.querySelectorAll('a[href],button:not([disabled]),input,select,textarea');
    }
    function lock() {
      scrollY = window.scrollY;
      body.style.position = 'fixed';
      body.style.top = -scrollY + 'px';
      body.style.width = '100%';
    }
    function unlock() {
      body.style.position = body.style.top = body.style.width = '';
      window.scrollTo(0, scrollY);
    }
    var isDrawer = function () { return window.matchMedia('(max-width:719px)').matches; };

    function open() {
      backdrop = document.createElement('button');
      backdrop.className = 'menu-backdrop';
      backdrop.setAttribute('aria-label', 'Menu बंद करें');
      backdrop.addEventListener('click', function () { close(true); });
      menu.parentNode.insertBefore(backdrop, menu);
      if (isDrawer()) lock();
      var first = focusables()[0];
      if (first) first.focus();
    }
    function close(refocus) {
      if (!menu.open) return;
      menu.open = false;
      if (backdrop) { backdrop.remove(); backdrop = null; }
      unlock();
      if (refocus && summary) summary.focus();
    }

    menu.addEventListener('toggle', function () { if (menu.open) open(); else close(false); });

    document.addEventListener('keydown', function (ev) {
      if (!menu.open) return;
      if (ev.key === 'Escape') { ev.preventDefault(); close(true); return; }
      if (ev.key !== 'Tab') return;
      var f = focusables();
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
      else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
    });

    document.addEventListener('click', function (ev) {
      if (!menu.open) return;
      if (summary && summary.contains(ev.target)) return;      // the toggle handles itself
      if (menu.contains(ev.target)) { if (ev.target.closest('a,[data-menu-close]')) close(false); return; }
      close(false);
    });

    // a drawer left open across the desktop breakpoint would strand the scroll lock
    window.addEventListener('resize', function () { if (menu.open && !isDrawer()) unlock(); });
  }

  // ---------- WhatsApp FAB: shrink to an icon while scrolling, step aside over the footer
  var fab = document.querySelector('.fab-wa');
  if (fab && 'IntersectionObserver' in window) {
    var footer = document.querySelector('.site-footer');
    if (footer) {
      new IntersectionObserver(function (es) {
        fab.classList.toggle('is-parked', es[0].isIntersecting);
      }, { rootMargin: '0px 0px -40px 0px' }).observe(footer);
    }
    var lastY = window.scrollY, ticking = false;
    window.addEventListener('scroll', function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () {
        fab.classList.toggle('is-compact', window.scrollY > 320 && window.scrollY > lastY);
        lastY = window.scrollY;
        ticking = false;
      });
    }, { passive: true });
  }

  // ---------- language (only on bilingual pages)
  var langBtn = document.getElementById('langToggle');
  if (langBtn) langBtn.addEventListener('click', function () {
    var next = root.getAttribute('data-lang') === 'en' ? 'hi' : 'en';
    root.setAttribute('data-lang', next);
    store('moodily_lang', next);
    track('language_switch', { label: next });
  });

  // ---------- sample catalogue: search + browse-by-need + browse-by-customer-type
  var grid = document.querySelector('[data-sample-grid]');
  if (grid) {
    var tiles = [].slice.call(grid.querySelectorAll('.sample-tile'));
    var search = document.getElementById('sampleSearch');
    var countEl = document.querySelector('[data-sample-count]');
    var emptyEl = document.querySelector('[data-sample-empty]');
    var state = { cat: '', type: '', q: '' };

    function apply() {
      var shown = 0;
      tiles.forEach(function (t) {
        var okCat = !state.cat || t.getAttribute('data-cat') === state.cat;
        var okType = !state.type || (' ' + t.getAttribute('data-types') + ' ').indexOf(' ' + state.type + ' ') > -1;
        var okQ = !state.q || t.getAttribute('data-search').indexOf(state.q) > -1;
        var show = okCat && okType && okQ;
        t.hidden = !show;
        if (show) shown++;
      });
      if (countEl) countEl.textContent = shown + ' sample' + (shown === 1 ? '' : 's');
      if (emptyEl) emptyEl.hidden = shown !== 0;
    }
    function press(group, value) {
      document.querySelectorAll('[data-filter-' + group + ']').forEach(function (b) {
        b.setAttribute('aria-pressed', String(b.getAttribute('data-filter-' + group) === value));
      });
    }
    document.querySelectorAll('[data-filter-cat]').forEach(function (b) {
      b.addEventListener('click', function () {
        state.cat = b.getAttribute('data-filter-cat'); press('cat', state.cat); apply();
        if (state.cat) track('sample_filter', { label: 'need:' + state.cat });
      });
    });
    document.querySelectorAll('[data-filter-type]').forEach(function (b) {
      b.addEventListener('click', function () {
        state.type = b.getAttribute('data-filter-type'); press('type', state.type); apply();
        if (state.type) track('sample_filter', { label: 'who:' + state.type });
      });
    });
    if (search) {
      var t0;
      search.addEventListener('input', function () {
        state.q = search.value.trim().toLowerCase();
        apply();
        clearTimeout(t0);
        t0 = setTimeout(function () { if (state.q) track('sample_search', { label: state.q.slice(0, 40) }); }, 800);
      });
    }
    // deep link: /samples/?need=ppt or ?who=coaching-library
    try {
      var qp = new URLSearchParams(location.search);
      if (qp.get('need')) { state.cat = qp.get('need'); press('cat', state.cat); }
      if (qp.get('who')) { state.type = qp.get('who'); press('type', state.type); }
    } catch (e) {}
    apply();
  }

  // sample_card_view: fire once per tile when half of it has been seen
  if ('IntersectionObserver' in window) {
    var sseen = {};
    var sio = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        var slug = en.target.getAttribute('data-sample');
        if (en.isIntersecting && !sseen[slug]) { sseen[slug] = 1; track('sample_card_view', { label: slug }); sio.unobserve(en.target); }
      });
    }, { threshold: 0.5 });
    document.querySelectorAll('.sample-tile[data-sample]').forEach(function (el) { sio.observe(el); });
    // before_after_view / evidence_card_view
    var vseen = {};
    var vio = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        var ev = en.target.getAttribute('data-view');
        if (en.isIntersecting && !vseen[ev]) { vseen[ev] = 1; track(ev.split('|')[0], { label: ev.split('|')[1] || '' }); vio.unobserve(en.target); }
      });
    }, { threshold: 0.4 });
    document.querySelectorAll('[data-view]').forEach(function (el) { vio.observe(el); });
  }

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
      try {
        var qsSample = new URLSearchParams(location.search).get('sample');
        if (qsSample) data.append('sample', qsSample.replace(/[^a-z0-9-]/gi, '').slice(0, 60));
      } catch (e) {}
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
      if (!endpoint) {
        // No server to post to. Hand the filled enquiry straight to WhatsApp so it actually
        // reaches Moodily in one tap — never pretend a submission was received.
        var wa = document.getElementById('intakeWa') || document.querySelector('a[href*="wa.me"]');
        var base = wa ? wa.getAttribute('href').split('?')[0] : '';
        if (base) {
          var lines = ['Namaste Moodily,'];
          var add = function (label, key) { if (summary[key]) lines.push(label + ': ' + summary[key]); };
          add('Naam', 'name');
          lines.push('Service: ' + (summary.service_label || summary.service || '-'));
          add('Sample', 'sample');
          add('Goal', 'goal');
          add('City', 'city');
          add('Budget', 'budget');
          add('Deadline', 'deadline');
          add('Language', 'language');
          add('Link', 'link');
          add('Requirement', 'message');
          add('WhatsApp', 'whatsapp');
          add('Email', 'email');
          window.open(base + '?text=' + encodeURIComponent(lines.join('\n')), '_blank', 'noopener');
        }
        done('whatsapp');
        return;
      }
      // Google Apps Script web app: no-cors POST (opaque response). CRM/n8n: swap endpoint, keep field names.
      fetch(endpoint, { method: 'POST', mode: 'no-cors', body: new URLSearchParams(data) })
        .then(function () { done('sent'); })
        .catch(function () { done('whatsapp'); });
    });
  }

  // ---------- auto-track sample and store links that have no explicit data-track
  document.addEventListener('click', function (ev) {
    var a = ev.target.closest('a[href]');
    if (!a || a.hasAttribute('data-track') || a.closest('[data-track]')) return;
    var href = a.getAttribute('href');
    if (href.indexOf('/case-studies/') === 0) track('portfolio_open', { label: href, link_url: href });
    else if (href.indexOf('/store/') === 0) track('store_click', { label: href, link_url: href });
  });

  // ---------- Google Form intake wrapper (/contact/) — config from src/data/intake.json
  var intake = document.getElementById('intake');
  if (intake) initIntake(intake);

  function formUrlFor(cfg, svc, offerOn, estimate, sampleName) {
    var base = (svc && svc.prefill_url) || cfg.form_url || '';
    if (!base) return '';
    var ids = cfg.entry_ids || {};
    var norm = function (id) { return 'entry.' + String(id).replace(/^entry\./, ''); };
    var params = [];
    var add = function (id, value) {
      if (id && value && base.indexOf(norm(id) + '=') === -1) params.push(norm(id) + '=' + encodeURIComponent(value));
    };
    if (svc) { add(ids.service_category, svc.category); add(ids.sub_service, svc.name); }
    if (offerOn) add(ids.offer_code, cfg.offer.id);
    // one field carries whichever context the visitor arrived with: a sample, or a website estimate
    add(ids.sample_or_estimate, sampleName || estimate);
    if (!params.length) return base;
    if (base.indexOf('usp=pp_url') === -1) params.unshift('usp=pp_url');
    return base + (base.indexOf('?') === -1 ? '?' : '&') + params.join('&');
  }

  function initIntake(box) {
    var cfg = {};
    try { cfg = JSON.parse(document.getElementById('intakeConfig').textContent); } catch (e) {}
    var q = new URLSearchParams(location.search);
    var sid = q.get('service') || '';
    var svc = (cfg.services || {})[sid];
    var offerOn = !!(svc && svc.offer_price && cfg.offer && cfg.offer.active && q.get('offer') === cfg.offer.id && !root.classList.contains('offer-ended'));
    var sampleSlug = (q.get('sample') || '').replace(/[^a-z0-9-]/gi, '').slice(0, 60);
    var sampleName = (cfg.samples || {})[sampleSlug] || '';
    var est = (q.get('estimate') || '').match(/^(\d{3,7})-(\d{3,7})$/);
    var estText = est ? '₹' + Number(est[1]).toLocaleString('en-IN') + '–₹' + Number(est[2]).toLocaleString('en-IN') : '';
    if (svc) {
      document.getElementById('intakeContext').hidden = false;
      document.getElementById('intakeService').textContent = svc.name;
      document.getElementById('intakeCategory').textContent = 'Form category: ' + svc.category;
      document.getElementById('intakePrice').textContent = offerOn ? cfg.offer.name + ' offer: ' + svc.offer_price + ' (' + cfg.offer.pct + '% छूट)' : svc.price;
      var details = document.getElementById('intakeDetails');
      if (svc.page) details.setAttribute('href', svc.page); else details.hidden = true;
      if (offerOn) {
        var note = document.getElementById('intakeOffer');
        note.hidden = false;
        note.textContent = 'आप ' + cfg.offer.name + ' offer के लिए requirement भेज रहे हैं। Slot पूरा payment मिलने पर ही पक्का होता है।';
      }
    }
    if (sampleName) {
      var sNote = document.getElementById('intakeSample');
      if (sNote) {
        sNote.hidden = false;
        sNote.innerHTML = 'Sample: <a href="/samples/' + sampleSlug + '/">' + sampleName + '</a> — इसी तरह का काम आपके लिए customize होगा।';
      }
      document.getElementById('intakeContext').hidden = false;
      track('customize_sample_start', { label: sampleSlug });
    }
    if (estText) {
      var estNote = document.getElementById('intakeEstimate');
      estNote.hidden = false;
      estNote.textContent = 'Indicative estimate: ' + estText + ' — final quote आपकी requirement देखकर मिलेगा।';
      document.getElementById('intakeContext').hidden = false;
    }
    var gbtn = document.getElementById('gformBtn');
    if (gbtn) {
      var url = formUrlFor(cfg, svc, offerOn, estText, sampleName);
      if (url) gbtn.setAttribute('href', url);
      gbtn.setAttribute('data-label', sid || 'none');
      track('form_open', { label: sid || 'none', offer: offerOn ? cfg.offer.id : '', sample: sampleSlug || '', mode: 'google-form' });
    } else {
      track('form_open', { label: sid || 'none', offer: offerOn ? cfg.offer.id : '', sample: sampleSlug || '', mode: 'fallback' });
    }
    var wa = document.getElementById('intakeWa');
    if (wa && svc) {
      var text = 'Namaste Moodily,\nMujhe ' + svc.name + (offerOn ? ' (' + cfg.offer.name + ' offer, ' + svc.offer_price + ')' : '') + ' chahiye.\n' +
        (sampleName ? 'Sample: ' + sampleName + ' (moodily.in/samples/' + sampleSlug + '/)\n' : '') + (estText ? 'Website estimate: ' + estText + '\n' : '') +
        'Main [role] hoon.\nCity [city] hai.\nDeadline [deadline] hai.\nBudget approx [budget] hai.\nReference/website link [URL] hai.';
      wa.setAttribute('href', wa.getAttribute('href').split('?')[0] + '?text=' + encodeURIComponent(text));
      wa.setAttribute('data-label', 'intake-' + sid);
    }
  }

  // ---------- impression events, once per page (labels only — never form data)
  if ('IntersectionObserver' in window) {
    var onceSeen = {};
    var watch = function (selector, event, labelFn) {
      var els = document.querySelectorAll(selector);
      if (!els.length) return;
      var obs = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (!en.isIntersecting) return;
          var label = labelFn(en.target);
          if (!onceSeen[event + ':' + label]) { onceSeen[event + ':' + label] = 1; track(event, { label: label }); }
          obs.unobserve(en.target);
        });
      }, { threshold: 0.4 });
      els.forEach(function (el) { obs.observe(el); });
    };
    watch('[data-pricing]', 'pricing_view', function () { return location.pathname; });
    watch('[data-retainer]', 'retainer_view', function (el) { return el.getAttribute('data-retainer'); });
    watch('[data-sample-section]', 'sample_view', function () { return location.pathname; });
  }

  // ---------- customer-type router: progressive disclosure on mobile
  document.querySelectorAll('[data-types-toggle]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var box = btn.previousElementSibling;
      var open = !box.classList.contains('expanded');
      box.classList.toggle('expanded', open);
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      btn.textContent = open ? 'कम दिखाएँ' : btn.getAttribute('data-label-closed');
    });
  });

  // ---------- service finder: filter chips, customer type and search (all cards visible without JS)
  var finder = document.querySelector('[data-finder]');
  if (finder) {
    var fcards = document.querySelectorAll('.finder-card');
    var fq = new URLSearchParams(location.search);
    var fs = { tag: fq.get('filter') || '', text: fq.get('q') || '', type: fq.get('type') || '' };
    var fInput = document.getElementById('finderSearch');
    var fType = document.getElementById('finderType');
    fInput.value = fs.text;
    if (fs.type && fType.querySelector('option[value="' + CSS.escape(fs.type) + '"]')) fType.value = fs.type; else fs.type = '';
    var applyFinder = function () {
      var shown = 0;
      var words = fs.text.toLowerCase().split(/\s+/).filter(Boolean);
      fcards.forEach(function (c) {
        if (c.hasAttribute('data-always')) return;
        var tags = ' ' + (c.getAttribute('data-tags') || '') + ' ';
        var types = ' ' + (c.getAttribute('data-types') || '') + ' ';
        var hay = c.getAttribute('data-search') || '';
        var ok = (!fs.tag || tags.indexOf(' ' + fs.tag + ' ') !== -1) && (!fs.type || types.indexOf(' ' + fs.type + ' ') !== -1) &&
          words.every(function (w) { return hay.indexOf(w) !== -1; });
        c.hidden = !ok;
        if (ok) shown++;
      });
      finder.querySelectorAll('[data-filter]').forEach(function (b) { b.setAttribute('aria-pressed', b.getAttribute('data-filter') === fs.tag ? 'true' : 'false'); });
      finder.querySelector('[data-finder-count]').textContent = shown + ' packages';
      document.querySelector('[data-finder-empty]').hidden = shown > 0;
      return shown;
    };
    var searchTimer;
    fInput.addEventListener('input', function () {
      fs.text = fInput.value;
      var shown = applyFinder();
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function () { if (fs.text.trim()) track('service_search', { label: shown ? 'has-results' : 'no-results' }); }, 900);
    });
    fType.addEventListener('change', function () { fs.type = fType.value; applyFinder(); track('service_filter', { label: 'type:' + (fs.type || 'all') }); });
    finder.addEventListener('click', function (ev) {
      var b = ev.target.closest('[data-filter]');
      if (!b) return;
      fs.tag = b.getAttribute('data-filter');
      applyFinder();
      track('service_filter', { label: fs.tag || 'all' });
    });
    applyFinder();
  }

  // ---------- quote estimator (indicative only — never used for payment)
  var estForm = document.getElementById('estimator');
  if (estForm) {
    var ecfg = JSON.parse(document.getElementById('estimatorConfig').textContent);
    var R = ecfg.rules;
    var eSel = document.getElementById('est-service');
    var estStarted = false, estCompleted = false;
    var preSvc = new URLSearchParams(location.search).get('service');
    if (preSvc && ecfg.services[preSvc]) eSel.value = preSvc;
    var picked = function (name) { var el = estForm.querySelector('input[name="' + name + '"]:checked'); return el ? el.value : ''; };
    var rupees = function (n) { return '₹' + n.toLocaleString('en-IN'); };
    var calc = function () {
      var sid = eSel.value, sv = ecfg.services[sid];
      var result = document.getElementById('estResult'), hint = document.getElementById('estHint');
      if (!sv) { result.hidden = true; hint.hidden = false; return; }
      var monthly = sv.unit === 'month';
      var skip = { turnaround: monthly, integrations: !sv.integrations };
      R.groups.forEach(function (g) { estForm.querySelector('[data-group="' + g.key + '"]').hidden = !!skip[g.key]; });
      var rush = document.getElementById('est-turnaround-rush');
      rush.disabled = sv.price > R.rush_max_starting_price;
      if (rush.disabled && rush.checked) document.getElementById('est-turnaround-normal').checked = true;
      // multipliers describe scope/complexity only — never the customer
      var mmin = 1, mmax = 1;
      R.groups.forEach(function (g) {
        var v = skip[g.key] ? null : R[g.key][picked(g.key)];
        if (v) { mmin *= v.min; mmax *= v.max; }
      });
      var pmin = 0, pmax = 0;
      estForm.querySelectorAll('input[name="extras"]:checked').forEach(function (x) { pmin += R.extras[x.value].min_pct; pmax += R.extras[x.value].max_pct; });
      var r = R.round_to;
      var low = Math.max(sv.price, Math.floor(sv.price * mmin * (1 + pmin / 100) / r) * r);
      var high = Math.max(low + r, Math.ceil(sv.price * mmax * (1 + pmax / 100) / r) * r);
      var unit = monthly ? '/महीना' : '';
      document.getElementById('estRange').textContent = 'Estimated ' + rupees(low) + '–' + rupees(high) + unit;
      document.getElementById('estBase').textContent = sv.name + ' की starting price ' + rupees(sv.price) + unit + ' है।' +
        (rush.disabled && !monthly ? ' इस package के लिए 24–48h delivery उपलब्ध नहीं।' : '');
      result.hidden = false;
      hint.hidden = true;
      document.getElementById('estQuote').setAttribute('href', '/contact/?service=' + encodeURIComponent(sid) + '&estimate=' + low + '-' + high);
      document.getElementById('estDetails').setAttribute('href', sv.page);
      var wa = document.getElementById('estWa');
      wa.setAttribute('href', wa.getAttribute('href').split('?')[0] + '?text=' + encodeURIComponent('Namaste Moodily,\nMujhe ' + sv.name + ' chahiye.\nWebsite estimator: ' +
        rupees(low) + '–' + rupees(high) + unit + ' (scope: ' + picked('scope') + ', content: ' + picked('content') + (monthly ? '' : ', turnaround: ' + picked('turnaround')) +
        ').\nKripya final quote bhejiye.'));
      if (estStarted && !estCompleted) { estCompleted = true; track('quote_complete', { label: 'estimator:' + sid, scope: picked('scope') }); }
    };
    estForm.addEventListener('change', function () {
      if (!estStarted) { estStarted = true; track('quote_start', { label: 'estimator:' + (eSel.value || 'none') }); }
      calc();
    });
    estForm.addEventListener('submit', function (ev) { ev.preventDefault(); });
    calc();
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
      var msg = 'Namaste Moodily,\nMain ' + (lead.name || '') + ' (' + (lead.role || '') + ') hoon.\nMujhe ' + (lead.service_label || lead.service || '') + ' chahiye.' +
        (lead.sample ? '\nSample: moodily.in/samples/' + lead.sample + '/' : '') + '\nGoal: ' + (lead.goal || '') +
        '\nCity: ' + (lead.city || '') + '\nBudget approx: ' + (lead.budget || '') + '\nDeadline: ' + (lead.deadline || '') +
        '\nCurrent website/social link: ' + (lead.link || '-') + (lead.offer ? '\nOffer: ' + lead.offer : '') + '\nLanguage: ' + (lead.language || '') + (lead.message ? '\nMessage: ' + lead.message : '');
      var base = thanks.getAttribute('href').split('?')[0];
      thanks.setAttribute('href', base + '?text=' + encodeURIComponent(msg));
    }
  }
})();
