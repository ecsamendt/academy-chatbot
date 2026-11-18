/* Socio AI Coach chat window. No build step, no dependencies. */
(function () {
  'use strict';

  var cfg = window.SocioCoachConfig || {};
  var root = document.getElementById('socio-coach');
  if (!root || !cfg.serviceUrl) return;

  var token = '';
  var tokenExp = 0;

  var T = {
    title: 'Socio · tu coach de negocios',
    placeholder: 'Escribe tu pregunta sobre tu negocio…',
    send: 'Enviar',
    thinking: 'Socio está pensando…',
    error: 'No pude responder en este momento. Intenta de nuevo en un minuto.',
    sources: 'Dónde lo vemos en la academia',
    tool: 'Herramienta recomendada',
    upgrade: 'Ver planes',
    helpful: '¿Te ayudó esta respuesta?',
    thanks: '¡Gracias por tu opinión!',
    disclaimer: 'Socio es un asistente de inteligencia artificial. Sus respuestas son información general, ' +
      'no asesoría legal, fiscal ni financiera. Usamos las preguntas para mejorar el contenido de la academia.',
    welcome: '¡Hola! Soy Socio. Pregúntame lo que necesites sobre tu negocio y te digo qué lección o ' +
      'herramienta de la academia te ayuda.'
  };

  function h(tag, attrs, children) {
    var el = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === 'text') el.textContent = attrs[k];
      else if (k.indexOf('on') === 0) el.addEventListener(k.slice(2), attrs[k]);
      else el.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { if (c) el.appendChild(c); });
    return el;
  }

  function paragraphs(text) {
    var frag = document.createDocumentFragment();
    String(text || '').split(/\n{2,}/).forEach(function (para) {
      var p = h('p');
      para.split('\n').forEach(function (line, i) {
        if (i) p.appendChild(document.createElement('br'));
        p.appendChild(document.createTextNode(line));
      });
      frag.appendChild(p);
    });
    return frag;
  }

  function getToken() {
    if (token && Date.now() / 1000 < tokenExp - 60) return Promise.resolve(token);
    return fetch(cfg.tokenUrl, { credentials: 'same-origin', headers: { 'X-WP-Nonce': cfg.nonce } })
      .then(function (r) { if (!r.ok) throw new Error('token ' + r.status); return r.json(); })
      .then(function (d) {
        token = d.token || '';
        try { tokenExp = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).exp; }
        catch (e) { tokenExp = 0; }
        return token;
      });
  }

  function call(path, body, retried) {
    return getToken().then(function (tok) {
      return fetch(cfg.serviceUrl.replace(/\/$/, '') + path, {
        method: 'POST',
        keepalive: path !== '/ask',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + tok },
        body: JSON.stringify(body)
      });
    }).then(function (r) {
      if (r.status === 401 && !retried) { token = ''; return call(path, body, true); }
      if (!r.ok) throw new Error(path + ' ' + r.status);
      return r.json();
    });
  }

  function track(questionId, kind, target) {
    call('/click', { question_id: questionId, kind: kind, target: target }).catch(function () {});
  }

  // --- layout ---
  var log = h('div', { class: 'socio-coach__log' });
  var input = h('textarea', { class: 'socio-coach__input', rows: '2', placeholder: T.placeholder, maxlength: '2000',
    'aria-label': T.placeholder });
  var sendBtn = h('button', { class: 'socio-coach__send', type: 'submit', text: T.send });
  var form = h('form', { class: 'socio-coach__form' }, [input, sendBtn]);
  root.appendChild(h('div', { class: 'socio-coach__header', text: T.title }));
  root.appendChild(log);
  root.appendChild(form);
  root.appendChild(h('div', { class: 'socio-coach__disclaimer', text: T.disclaimer }));

  function bubble(who, content) {
    var b = h('div', { class: 'socio-coach__msg socio-coach__msg--' + who });
    if (typeof content === 'string') b.appendChild(paragraphs(content)); else b.appendChild(content);
    log.appendChild(b);
    log.scrollTop = log.scrollHeight;
    return b;
  }

  function renderAnswer(d) {
    var wrap = h('div');
    wrap.appendChild(paragraphs(d.answer));

    if (d.citations && d.citations.length) {
      var list = h('ul', { class: 'socio-coach__sources' });
      d.citations.forEach(function (c) {
        var label = [c.course, c.title].filter(Boolean).join(' › ') + (c.timestamp_label ? ' — min ' + c.timestamp_label : '');
        list.appendChild(h('li', {}, [h('a', { href: c.url, text: label,
          onclick: function () { track(d.question_id, 'lesson', c.url); } })]));
      });
      wrap.appendChild(h('div', { class: 'socio-coach__label', text: T.sources }));
      wrap.appendChild(list);
    }

    if (d.tool) {
      wrap.appendChild(h('div', { class: 'socio-coach__card' }, [
        h('div', { class: 'socio-coach__label', text: T.tool }),
        h('a', { href: d.tool.url, text: d.tool.name, onclick: function () { track(d.question_id, 'tool', d.tool.url); } })
      ]));
    }

    if (d.upsell) {
      wrap.appendChild(h('div', { class: 'socio-coach__card socio-coach__card--upsell' }, [
        h('strong', { text: d.upsell.course }),
        h('a', { href: cfg.upgradeUrl || '/planes/', class: 'socio-coach__button', text: T.upgrade,
          onclick: function () { track(d.question_id, 'upgrade', d.upsell.course); } })
      ]));
    }

    // Phase 3: d.offers render here, in a separate "Recursos recomendados" card.

    var fb = h('div', { class: 'socio-coach__feedback' });
    function vote(v) {
      return function () {
        call('/feedback', { question_id: d.question_id, value: v }).catch(function () {});
        fb.textContent = T.thanks;
      };
    }
    fb.appendChild(h('span', { text: T.helpful + ' ' }));
    fb.appendChild(h('button', { type: 'button', 'aria-label': 'Sí', text: '👍', onclick: vote(1) }));
    fb.appendChild(h('button', { type: 'button', 'aria-label': 'No', text: '👎', onclick: vote(-1) }));
    wrap.appendChild(fb);
    return wrap;
  }

  bubble('coach', T.welcome);

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var q = input.value.trim();
    if (q.length < 2 || sendBtn.disabled) return;
    input.value = '';
    bubble('member', q);
    var pending = bubble('coach', T.thinking);
    pending.classList.add('socio-coach__msg--pending');
    sendBtn.disabled = true;
    call('/ask', { question: q })
      .then(function (d) { pending.replaceWith(bubble('coach', renderAnswer(d))); })
      .catch(function () { pending.replaceWith(bubble('coach', T.error)); })
      .then(function () { sendBtn.disabled = false; input.focus(); });
  });

  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit ? form.requestSubmit() : sendBtn.click(); }
  });
})();
