/* Moodily International — loaded only on /international/ pages.
   The enquiry form sends nothing from this site: it prepares an email (or WhatsApp message) in the visitor's own app.
   Answers are never stored (no cookies, localStorage or sessionStorage), never put in this site's URLs, and never sent
   to analytics — analytics receives only the chosen project type and the contact method. */
(function () {
  'use strict';
  var track = window.moodilyTrack || function () {};

  // ---------- project payment page: never keep a project reference in the address bar or analytics
  if (location.pathname.indexOf('/international/pay/') === 0 && location.search) {
    try { history.replaceState(null, '', location.pathname); } catch (e) {}
  }

  var form = document.getElementById('intlIntake');
  if (!form) return;
  var email = form.getAttribute('data-email'), wa = form.getAttribute('data-wa');
  var $ = function (id) { return document.getElementById(id); };
  var REQUIRED = ['in-name', 'in-email', 'in-company', 'in-country', 'in-type', 'in-budget', 'in-timeline', 'in-contact', 'in-goal', 'in-problem'];
  var LABELS = {
    'in-name': 'Name', 'in-email': 'Work email', 'in-company': 'Company', 'in-website': 'Website', 'in-country': 'Country',
    'in-tz': 'Time zone', 'in-type': 'Project type', 'in-budget': 'Budget range', 'in-timeline': 'Desired timeline',
    'in-contact': 'Preferred contact', 'in-goal': 'Primary goal', 'in-problem': "What isn't working today",
    'in-links': 'Relevant public links', 'in-nda': 'NDA needed', 'in-source': 'How I heard about Moodily'
  };

  // Prefill the time zone from the browser, and the project type from ?type=<service-id> (a fixed category, never personal data).
  try { if (!$('in-tz').value) $('in-tz').value = Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch (e) {}
  var wanted = new URLSearchParams(location.search).get('type');
  if (wanted) {
    var sel = $('in-type');
    for (var i = 0; i < sel.options.length; i++) if (sel.options[i].value === wanted) sel.value = wanted;
  }

  var started = false;
  form.addEventListener('input', function () {
    if (started) return;
    started = true;
    track('audit_started', { label: 'intl-form', project_type: $('in-type').value || '' });
  });

  function setError(id, msg) {
    var el = $(id), err = $(id + '-err');
    if (!el || !err) return;
    if (msg) { err.textContent = msg; err.hidden = false; el.setAttribute('aria-invalid', 'true'); el.setAttribute('aria-describedby', id + '-err'); }
    else { err.textContent = ''; err.hidden = true; el.removeAttribute('aria-invalid'); el.removeAttribute('aria-describedby'); }
  }

  function validate() {
    var first = null;
    REQUIRED.forEach(function (id) {
      var v = ($(id).value || '').trim();
      var msg = v ? '' : 'Please fill this in.';
      if (!msg && id === 'in-email' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) msg = 'Please enter a valid email address.';
      setError(id, msg);
      if (msg && !first) first = $(id);
    });
    if (first) first.focus();
    return !first;
  }

  function projectLabel() {
    var sel = $('in-type');
    return sel.selectedIndex > 0 ? sel.options[sel.selectedIndex].text : '';
  }

  function message() {
    var lines = ['Hello Moodily,', '', 'I would like to discuss a project.', ''];
    Object.keys(LABELS).forEach(function (id) {
      var v = ($(id).value || '').trim();
      if (id === 'in-type') v = projectLabel();
      if (v) lines.push(LABELS[id] + ': ' + v);
    });
    return lines.join('\n');
  }

  function done(method) {
    track('audit_submitted', { label: 'intl-form', project_type: $('in-type').value || '', method: method });
  }

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    if (!validate()) return;
    var subject = 'Project enquiry: ' + (projectLabel().split(' — ')[0] || 'Moodily International');
    done('email');
    var result = $('intlResult');
    result.hidden = false;
    window.location.href = 'mailto:' + email + '?subject=' + encodeURIComponent(subject) + '&body=' + encodeURIComponent(message());
    setTimeout(function () { result.focus(); }, 300);
  });

  $('intlWa').addEventListener('click', function () {
    if (!validate()) return;
    done('whatsapp');
    window.open('https://wa.me/' + wa + '?text=' + encodeURIComponent(message()), '_blank', 'noopener');
  });

  $('intlCopy').addEventListener('click', function () {
    var status = $('intlCopied');
    var text = message();
    var ok = function () { status.textContent = 'Copied. Paste it into an email to ' + email + '.'; track('intake_copied', { label: 'intl-form', project_type: $('in-type').value || '' }); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(ok, function () { status.textContent = 'Copy failed — please select and copy manually.'; });
    else status.textContent = 'Copy is not supported in this browser.';
  });
})();
