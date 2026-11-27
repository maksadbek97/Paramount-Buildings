/* «Финансы»: финплан план / факт как таблица Excel.
   - ячейки правятся прямо в таблице, итоги и остатки пересчитываются сразу;
   - каждая правка сохраняется сразу: на сервере — в базу (/finance/api/), на сайте по ссылке — в этом браузере;
   - «Доход / Расход»: объект → категория → сумма, одним окном (удобно с телефона);
   - уведомления, когда факт больше плана;
   - договоры, доп. договоры и АВР по каждому объекту;
   - «Скачать Excel» — файл по шаблону компании «Фин план до 2026 года». */
(function () {
  'use strict';
  var app = document.querySelector('[data-fin-app]');
  if (!app) return;
  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); }

  var cfg = app.dataset, LOCAL = cfg.mode === 'local', KEY = 'pb:fin:v2';
  var seed = JSON.parse($('#finState').textContent);
  var SEC = {income: 'Поступления', labor: 'Оплата работ', material: 'Материальные расходы', overhead: 'Накладные расходы', debt: 'Общий долг компании'};
  var SHORT = {income: 'Поступление', labor: 'Оплата работ', material: 'Материалы', overhead: 'Накладные', debt: 'Долг компании'};
  var OBJ_SECS = ['income', 'labor', 'material', 'overhead'], EXP = ['labor', 'material', 'overhead'];
  var S = load();

  function clone(x) { return JSON.parse(JSON.stringify(x)); }
  function load() {
    var s = clone(seed);
    if (LOCAL) {
      try {
        var x = JSON.parse(localStorage.getItem(KEY) || 'null');
        if (x && x.lines) { s.lines = x.lines; s.contracts = x.contracts || []; s.acts = x.acts || []; s.saved = x.saved; }
      } catch (e) { /* хранилище недоступно — работаем с данными страницы */ }
    }
    return s;
  }

  /* ---------- числа и даты ---------- */
  function num(v) { if (typeof v === 'number') return v; v = String(v || '').replace(/[\s ]/g, '').replace('−', '-').replace(',', '.'); var n = parseFloat(v); return isNaN(n) ? 0 : n; }
  function fmt(n, keepZero) {
    n = Math.round(num(n) * 100) / 100;
    if (!n && !keepZero) return '';
    var neg = n < 0, p = String(Math.abs(n)).split('.');
    return (neg ? '−' : '') + p[0].replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + (p[1] ? ',' + p[1] : '');
  }
  function money(n) { return fmt(n, true) + ' ₸'; }
  function short(n) {
    var a = Math.abs(n), s = n < 0 ? '−' : '';
    if (a >= 1e9) return s + (a / 1e9).toFixed(1).replace('.0', '').replace('.', ',') + ' млрд ₸';
    if (a >= 1e6) return s + (a / 1e6).toFixed(1).replace('.0', '').replace('.', ',') + ' млн ₸';
    if (a >= 1e3) return s + Math.round(a / 1e3) + ' тыс ₸';
    return s + Math.round(a) + ' ₸';
  }
  function today() { var d = new Date(); return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2); }
  function dshow(iso) { return iso ? iso.slice(8, 10) + '.' + iso.slice(5, 7) + '.' + iso.slice(0, 4) : ''; }

  /* ---------- данные ---------- */
  function objById(id) { return S.objects.filter(function (o) { return o.id === id; })[0]; }
  function objName(id) { var o = objById(id); return o ? o.name : 'Без объекта'; }
  function lines(oid, sec) {
    return S.lines.filter(function (l) { return (sec ? l.section === sec : true) && (sec === 'debt' ? true : l.object === oid); })
      .sort(function (a, b) { return (a.pos - b.pos) || (a.id - b.id); });
  }
  function sum(list, f) { return list.reduce(function (s, x) { return s + num(x[f]); }, 0); }
  function sec(oid, s) { var l = lines(oid, s); return {plan: sum(l, 'plan'), fact: sum(l, 'fact')}; }
  function calc(oid) {
    var r = {}; OBJ_SECS.forEach(function (s) { r[s] = sec(oid, s); });
    r.exp = {plan: r.labor.plan + r.material.plan + r.overhead.plan, fact: r.labor.fact + r.material.fact + r.overhead.fact};
    r.bal = {plan: r.income.plan - r.exp.plan, fact: r.income.fact - r.exp.fact};
    var acts = S.acts.filter(function (a) { return a.object === oid; }), cs = S.contracts.filter(function (c) { return c.object === oid; });
    r.acts = sum(acts, 'amount'); r.contracts = sum(cs, 'amount');
    r.due = r.acts - r.income.fact;  // заказчик должен за выполненное
    return r;
  }
  function total() {
    var t = {income: {plan: 0, fact: 0}, labor: {plan: 0, fact: 0}, material: {plan: 0, fact: 0}, overhead: {plan: 0, fact: 0}, acts: 0, contracts: 0};
    S.objects.forEach(function (o) {
      var c = calc(o.id);
      OBJ_SECS.forEach(function (s) { t[s].plan += c[s].plan; t[s].fact += c[s].fact; });
      t.acts += c.acts; t.contracts += c.contracts;
    });
    t.debt = sec(null, 'debt');
    t.exp = {plan: t.labor.plan + t.material.plan + t.overhead.plan, fact: t.labor.fact + t.material.fact + t.overhead.fact};
    t.expAll = {plan: t.exp.plan + t.debt.plan, fact: t.exp.fact + t.debt.fact};
    t.bal = {plan: t.income.plan - t.expAll.plan, fact: t.income.fact - t.expAll.fact};
    t.due = t.acts - t.income.fact;
    return t;
  }

  /* ---------- уведомления: факт больше плана ---------- */
  function overruns() {
    var out = [];
    S.objects.forEach(function (o) {
      EXP.forEach(function (s) {
        var x = sec(o.id, s);
        if (x.fact > x.plan) out.push({key: o.id + ':' + s, level: 'bad', obj: o.id, where: o.name, text: SEC[s] + ': факт ' + money(x.fact) + ' больше плана ' + money(x.plan) + ' на ' + money(x.fact - x.plan)});
      });
      lines(o.id).forEach(function (l) {
        if (l.section !== 'income' && num(l.plan) > 0 && num(l.fact) > num(l.plan)) out.push({key: 'l' + l.id, level: 'warn', obj: o.id, where: o.name, text: (l.name || SHORT[l.section]) + ': факт ' + money(l.fact) + ' больше плана ' + money(l.plan) + ' на ' + money(num(l.fact) - num(l.plan))});
      });
    });
    lines(null, 'debt').forEach(function (l) {
      if (num(l.plan) > 0 && num(l.fact) > num(l.plan)) out.push({key: 'l' + l.id, level: 'warn', obj: null, where: 'Долг компании', text: (l.name || 'Долг') + ': оплачено ' + money(l.fact) + ' больше суммы долга ' + money(l.plan)});
    });
    return out;
  }

  /* ---------- сохранение ---------- */
  var queue = Promise.resolve(), pending = 0, tmpId = -1;
  S.lines.concat(S.contracts, S.acts).forEach(function (r) { if (r.id <= tmpId) tmpId = r.id - 1; });
  function status(state, text) {
    $$('[data-fin-status]').forEach(function (el) { el.dataset.state = state; el.textContent = text; });
  }
  function persistLocal() {
    try { localStorage.setItem(KEY, JSON.stringify({lines: S.lines, contracts: S.contracts, acts: S.acts, saved: Date.now()})); status('ok', 'Сохранено'); }
    catch (e) { status('err', 'Не удалось сохранить в браузере'); }
  }
  function send(kind, row, op, data) {
    if (LOCAL) { persistLocal(); return; }
    pending++; status('busy', 'Сохраняю…');
    queue = queue.then(function () {
      if (op === 'delete' && !(row.id > 0)) return null;
      return fetch(cfg.api, {method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': cfg.csrf},
        body: JSON.stringify({kind: kind, op: op, id: row.id > 0 ? row.id : null, data: data})
      }).then(function (r) { return r.json().catch(function () { return {ok: false, error: 'Ошибка сервера'}; }); })
        .then(function (res) {
          if (!res.ok) throw new Error(res.error || 'Не сохранено');
          if (res.row && row.id <= 0) {  // новая строка получила номер в базе
            var old = row.id; row.id = res.row.id;
            $$('[data-rk="' + kind + ':' + old + '"]').forEach(function (el) { el.dataset.rk = kind + ':' + row.id; });
          }
        });
    }).then(function () { if (--pending === 0) status('ok', 'Сохранено'); })
      .catch(function (e) { pending = Math.max(pending - 1, 0); status('err', e.message); toast(e.message, 'bad'); });
  }
  function listOf(kind) { return kind === 'line' ? S.lines : kind === 'contract' ? S.contracts : S.acts; }
  function maxPos(kind) { return listOf(kind).reduce(function (m, r) { return Math.max(m, r.pos || 0); }, 0); }
  function create(kind, row) {
    row.id = tmpId--; row.pos = maxPos(kind) + 1;
    listOf(kind).push(row);
    send(kind, row, 'save', row);
    return row;
  }
  function update(kind, row, changes) {
    var before = overruns().map(function (x) { return x.key; });
    Object.keys(changes).forEach(function (k) { row[k] = changes[k]; });
    if (kind === 'line' && changes.fact && num(row.fact) && !row.fdate) { row.fdate = today(); changes.fdate = row.fdate; }
    send(kind, row, 'save', changes);
    warnNew(before);
  }
  function remove(kind, row) {
    var list = listOf(kind), i = list.indexOf(row);
    if (i >= 0) list.splice(i, 1);
    send(kind, row, 'delete', {});
  }
  function warnNew(before) {
    overruns().forEach(function (x) { if (before.indexOf(x.key) < 0) toast('Факт больше плана · ' + x.where + ' · ' + x.text, 'bad'); });
  }

  /* ---------- сообщения ---------- */
  function toast(text, level) {
    var box = $('.fg-toasts') || document.body.appendChild(Object.assign(document.createElement('div'), {className: 'fg-toasts'}));
    var t = document.createElement('div'); t.className = 'fg-toast ' + (level || 'ok'); t.textContent = text;
    box.appendChild(t); setTimeout(function () { t.classList.add('out'); setTimeout(function () { t.remove(); }, 400); }, level === 'bad' ? 6000 : 3500);
  }

  /* ---------- ячейки ---------- */
  function cell(kind, row, f, type, extra) {
    var v = row ? row[f] : '', rk = kind + ':' + (row ? row.id : 'new'), attrs = ' data-f="' + f + '" data-t="' + type + '"' + (extra || '');
    if (type === 'date') return '<input class="fc fc-date" type="date" value="' + esc(v) + '"' + attrs + (v ? '' : ' data-empty') + ' aria-label="Дата">';
    if (type === 'money') return '<input class="fc fc-num" inputmode="decimal" autocomplete="off" value="' + esc(fmt(v)) + '"' + attrs + '>';
    return '<input class="fc" autocomplete="off" value="' + esc(v) + '"' + attrs + '>';
  }
  function delBtn() { return '<button type="button" class="fg-del" data-del title="Удалить строку" aria-label="Удалить строку">×</button>'; }

  /* ---------- лист объекта / долги ---------- */
  function sheetHTML(oid, debt) {
    var secs = debt ? ['debt'] : OBJ_SECS, h = [];
    h.push('<div class="fg-wrap"><table class="fg fg-sheet"><colgroup><col class="c-n"><col class="c-name"><col class="c-m"><col class="c-d"><col class="c-m"><col class="c-d"><col class="c-m"><col class="c-note"><col class="c-x"></colgroup>');
    h.push('<thead><tr><th>№</th><th>' + (debt ? 'Кому должны' : 'Наименование / получатель') + '</th><th>' + (debt ? 'Сумма долга' : 'План') + '</th><th>' + (debt ? 'Срок оплаты' : 'Плановая дата') + '</th><th>' + (debt ? 'Факт оплаты' : 'Факт') + '</th><th>' + (debt ? 'Дата оплаты' : 'Дата факта') + '</th><th>' + (debt ? 'Остаток долга' : 'Остаток') + '</th><th>Статус / примечание</th><th></th></tr></thead>');
    secs.forEach(function (s) {
      h.push('<tbody class="fg-sec s-' + s + '" data-sec="' + s + '"><tr class="fg-sh"><td colspan="2">' + (debt ? 'Кредиторы' : SEC[s]) + '</td>' +
        '<td class="r" data-calc="' + s + ':plan"></td><td></td><td class="r" data-calc="' + s + ':fact"></td><td></td><td class="r" data-calc="' + s + ':left"></td><td data-calc="' + s + ':flag"></td><td></td></tr>');
      lines(oid, s).forEach(function (l, i) {
        h.push('<tr class="fg-row" data-rk="line:' + l.id + '"><td class="n">' + (i + 1) + '</td><td>' + cell('line', l, 'name', 'text') + '</td><td>' + cell('line', l, 'plan', 'money') +
          '</td><td>' + cell('line', l, 'pdate', 'date') + '</td><td>' + cell('line', l, 'fact', 'money') + '</td><td>' + cell('line', l, 'fdate', 'date') +
          '</td><td class="r fg-left" data-left></td><td>' + cell('line', l, 'note', 'text') + '</td><td>' + delBtn() + '</td></tr>');
      });
      h.push('<tr class="fg-new" data-rk="line:new" data-sec="' + s + '"><td class="n">+</td><td>' + cell('line', null, 'name', 'text', ' placeholder="Новая строка…"') + '</td><td>' + cell('line', null, 'plan', 'money') +
        '</td><td>' + cell('line', null, 'pdate', 'date') + '</td><td>' + cell('line', null, 'fact', 'money') + '</td><td>' + cell('line', null, 'fdate', 'date') + '</td><td></td><td>' + cell('line', null, 'note', 'text') + '</td><td></td></tr></tbody>');
    });
    if (debt) {
      h.push('<tbody><tr class="fg-total"><td colspan="2">ИТОГО ДОЛГ</td><td class="r" data-calc="debt:plan"></td><td></td><td class="r" data-calc="debt:fact"></td><td></td><td class="r" data-calc="debt:left"></td><td colspan="2"></td></tr></tbody>');
    } else {
      h.push('<tbody><tr class="fg-total"><td colspan="2">ИТОГО РАСХОДЫ</td><td class="r" data-calc="exp:plan"></td><td></td><td class="r" data-calc="exp:fact"></td><td></td><td class="r" data-calc="exp:left"></td><td colspan="2" data-calc="exp:flag"></td></tr>' +
        '<tr class="fg-total main"><td colspan="2">ОСТАТОК: ПОСТУПЛЕНИЯ − РАСХОДЫ</td><td class="r" data-calc="bal:plan"></td><td></td><td class="r" data-calc="bal:fact"></td><td colspan="4"></td></tr></tbody>');
    }
    h.push('</table></div>');
    return h.join('');
  }

  function contractsHTML(oid) {
    var cs = S.contracts.filter(function (c) { return c.object === oid; }).sort(function (a, b) { return (a.pos - b.pos) || (a.id - b.id); });
    var h = ['<div class="fg-wrap"><table class="fg fg-small"><colgroup><col class="c-kind"><col class="c-num"><col class="c-d"><col class="c-name"><col class="c-m"><col class="c-note"><col class="c-x"></colgroup>',
      '<thead><tr><th>Вид</th><th>№</th><th>Дата</th><th>Предмет / вид работ</th><th>Сумма</th><th>Примечание</th><th></th></tr></thead><tbody>'];
    function kindSel(c) {
      var v = c ? c.kind : 'main';
      return '<select class="fc" data-f="kind" data-t="select"><option value="main"' + (v === 'main' ? ' selected' : '') + '>Договор</option><option value="extra"' + (v === 'extra' ? ' selected' : '') + '>Доп. договор</option></select>';
    }
    cs.forEach(function (c) {
      h.push('<tr class="fg-row' + (c.kind === 'extra' ? ' extra' : '') + '" data-rk="contract:' + c.id + '"><td>' + kindSel(c) + '</td><td>' + cell('contract', c, 'number', 'text') + '</td><td>' + cell('contract', c, 'date', 'date') +
        '</td><td>' + cell('contract', c, 'subject', 'text') + '</td><td>' + cell('contract', c, 'amount', 'money') + '</td><td>' + cell('contract', c, 'note', 'text') + '</td><td>' + delBtn() + '</td></tr>');
    });
    h.push('<tr class="fg-new" data-rk="contract:new"><td>' + kindSel(null) + '</td><td>' + cell('contract', null, 'number', 'text', ' placeholder="№"') + '</td><td>' + cell('contract', null, 'date', 'date') +
      '</td><td>' + cell('contract', null, 'subject', 'text', ' placeholder="Новый договор…"') + '</td><td>' + cell('contract', null, 'amount', 'money') + '</td><td>' + cell('contract', null, 'note', 'text') + '</td><td></td></tr>');
    h.push('<tr class="fg-total"><td colspan="4">Итого по договорам</td><td class="r" data-calc="contracts"></td><td colspan="2"></td></tr></tbody></table></div>');
    return h.join('');
  }

  function actsHTML(oid) {
    var as = S.acts.filter(function (a) { return a.object === oid; }).sort(function (a, b) { return (a.pos - b.pos) || (a.id - b.id); });
    var h = ['<div class="fg-wrap"><table class="fg fg-small"><colgroup><col class="c-d"><col class="c-name"><col class="c-m"><col class="c-note"><col class="c-x"></colgroup>',
      '<thead><tr><th>Дата</th><th>Вид работ / договор</th><th>Сумма</th><th>Примечание</th><th></th></tr></thead><tbody>'];
    as.forEach(function (a) {
      h.push('<tr class="fg-row" data-rk="act:' + a.id + '"><td>' + cell('act', a, 'date', 'date') + '</td><td>' + cell('act', a, 'work', 'text') + '</td><td>' + cell('act', a, 'amount', 'money') + '</td><td>' + cell('act', a, 'note', 'text') + '</td><td>' + delBtn() + '</td></tr>');
    });
    h.push('<tr class="fg-new" data-rk="act:new"><td>' + cell('act', null, 'date', 'date') + '</td><td>' + cell('act', null, 'work', 'text', ' placeholder="Новый АВР: вид работ…"') + '</td><td>' + cell('act', null, 'amount', 'money') + '</td><td>' + cell('act', null, 'note', 'text') + '</td><td></td></tr>');
    h.push('<tr class="fg-total"><td colspan="2">Итого по АВР</td><td class="r" data-calc="acts"></td><td colspan="2"></td></tr></tbody></table></div>');
    return h.join('');
  }

  function kpi(label, val, hint, tone, key) {
    return '<div class="k fg-k"><span class="kl">' + label + '</span><b class="kv ' + (tone || '') + '"' + (key ? ' data-calc="' + key + '"' : '') + '>' + val + '</b><span class="kh"' + (key ? ' data-calc="' + key + ':h"' : '') + '>' + hint + '</span></div>';
  }

  function alertsHTML(oid) {
    return '<section class="card fg-alerts" data-alerts' + (oid != null ? ' data-obj="' + oid + '"' : '') + ' hidden><header><h3>Уведомления</h3><span class="pill" data-alerts-n></span><span class="muted">факт больше плана</span></header><ul class="att" data-alerts-list></ul></section>';
  }

  function viewObject(box, oid) {
    box.innerHTML = '<div class="kgrid fg-kpis">' +
      kpi('Поступления', '', '', 'ok', 'k:inc') + kpi('Расходы', '', '', '', 'k:exp') + kpi('Остаток', '', '', '', 'k:bal') + kpi('Выполнено по АВР', '', '', '', 'k:due') + '</div>' +
      alertsHTML(oid) +
      '<section class="card flat fg-card"><header><h3>План / факт</h3><span class="muted">нажмите на ячейку и пишите · Enter — вниз · строка «Новая строка…» — новая запись</span><span class="muted fg-legend"><i></i>без плана <i class="r"></i>факт больше плана</span></header>' + sheetHTML(oid, false) + '</section>' +
      '<div class="row2 fg-row2"><section class="card flat fg-card"><header><h3>Договоры и доп. договоры</h3><span class="muted" data-calc="contracts:h"></span></header>' + contractsHTML(oid) + '</section>' +
      '<section class="card flat fg-card"><header><h3>АВР — выполненные работы</h3><span class="muted" data-calc="acts:h"></span></header>' + actsHTML(oid) + '</section></div>';
  }

  function viewDebts(box) {
    box.innerHTML = '<div class="kgrid fg-kpis">' + kpi('Всего долг', '', '', '', 'k:dplan') + kpi('Оплачено', '', '', 'ok', 'k:dfact') + kpi('Остаток долга', '', '', 'bad', 'k:dleft') + kpi('Кредиторов', '', 'в реестре', '', 'k:dn') + '</div>' +
      alertsHTML(-1) + '<section class="card flat fg-card"><header><h3>Реестр кредиторов</h3><span class="muted">долги не распределяются по объектам · остаток считается сам</span></header>' + sheetHTML(null, true) + '</section>';
  }

  function viewSummary(box) {
    var objs = S.objects, h = [];
    h.push('<div class="kgrid fg-kpis">' + kpi('Поступления', '', '', 'ok', 'k:inc') + kpi('Расходы по объектам', '', '', '', 'k:exp') + kpi('Общий долг компании', '', '', 'bad', 'k:debt') + kpi('Итог остаток', '', '', '', 'k:bal') + '</div>');
    h.push(alertsHTML(null));
    h.push('<section class="card flat fg-card"><header><h3>Сводная таблица</h3><span class="muted">план и факт по объектам · нажмите на объект, чтобы открыть его лист</span></header><div class="fg-wrap"><table class="fg fg-sum"><thead><tr><th rowspan="2" class="lbl">Статья</th>');
    objs.forEach(function (o, i) { h.push('<th colspan="2" class="oh c' + (i % 6) + '"><a href="' + esc(o.fin) + '">' + esc(o.name) + '</a></th>'); });
    h.push('<th colspan="2" class="oh all">ВСЕ ОБЪЕКТЫ</th></tr><tr>');
    objs.concat([{id: 'all'}]).forEach(function () { h.push('<th>План</th><th>Факт</th>'); });
    h.push('</tr></thead><tbody>');
    function row(label, key, cls) {
      var r = '<tr class="' + (cls || '') + '"><th class="lbl">' + label + '</th>';
      objs.forEach(function (o) { r += '<td class="r" data-calc="o' + o.id + ':' + key + ':plan"></td><td class="r f" data-calc="o' + o.id + ':' + key + ':fact"></td>'; });
      return r + '<td class="r t" data-calc="t:' + key + ':plan"></td><td class="r t f" data-calc="t:' + key + ':fact"></td></tr>';
    }
    h.push(row('Поступления', 'income', 'inc') + row('Оплата работ', 'labor') + row('Материальные расходы', 'material') + row('Накладные расходы', 'overhead'));
    var dr = '<tr class="debt"><th class="lbl">ОБЩИЙ ДОЛГ КОМПАНИИ</th>'; objs.forEach(function () { dr += '<td></td><td></td>'; });
    h.push(dr + '<td class="r t" data-calc="t:debt:plan"></td><td class="r t f" data-calc="t:debt:fact"></td></tr>');
    h.push(row('ИТОГО РАСХОДЫ', 'exp', 'tot') + row('ИТОГ ОСТАТОК', 'bal', 'bal'));
    var ar = '<tr class="acts"><th class="lbl">Выполнено по АВР</th>'; objs.forEach(function (o) { ar += '<td colspan="2" class="r" data-calc="o' + o.id + ':acts"></td>'; });
    h.push(ar + '<td colspan="2" class="r t" data-calc="t:acts"></td></tr>');
    var du = '<tr class="acts"><th class="lbl">АВР − поступления (факт)</th>'; objs.forEach(function (o) { du += '<td colspan="2" class="r" data-calc="o' + o.id + ':due"></td>'; });
    h.push(du + '<td colspan="2" class="r t" data-calc="t:due"></td></tr>');
    h.push('</tbody></table></div></section>');
    var orphan = S.acts.filter(function (a) { return !a.object; });
    if (orphan.length) h.push('<section class="card fg-orphan"><header><h3>АВР без объекта</h3><span class="muted">в таблице не указан объект — откройте нужный объект и добавьте АВР там</span></header><ul>' +
      orphan.map(function (a) { return '<li><b>' + esc(a.work) + '</b> — ' + money(a.amount) + '</li>'; }).join('') + '</ul></section>');
    box.innerHTML = h.join('');
  }

  /* ---------- пересчёт без перерисовки (фокус в ячейке не теряется) ---------- */
  function setCalc(key, text, cls) {
    $$('[data-calc="' + key + '"]').forEach(function (el) { el.textContent = text; if (cls !== undefined) el.className = el.className.replace(/\b(neg|over|okc|muted-c)\b/g, '').trim() + (cls ? ' ' + cls : ''); });
  }
  function recalc() {
    var view = $('[data-fin-view]'); if (!view) return;
    var v = view.dataset.finView, oid = view.dataset.object ? +view.dataset.object : null;
    if (v === 'object' || v === 'debts') {
      var secs = v === 'debts' ? ['debt'] : OBJ_SECS;
      secs.forEach(function (s) {
        var x = sec(oid, s), over = s !== 'income' && x.fact > x.plan;
        setCalc(s + ':plan', fmt(x.plan, true)); setCalc(s + ':fact', fmt(x.fact, true), over ? 'over' : '');
        setCalc(s + ':left', fmt(x.plan - x.fact, true), x.plan - x.fact < 0 ? 'neg' : '');
        setCalc(s + ':flag', over ? 'факт больше плана на ' + money(x.fact - x.plan) : '', over ? 'over' : '');
        // строки: остаток (у поступлений — нарастающим итогом, как в таблице), подсветка
        var run = 0;
        lines(oid, s).forEach(function (l) {
          var tr = $('[data-rk="line:' + l.id + '"]'); if (!tr) return;
          var left;
          if (s === 'income') { run += num(l.plan) - num(l.fact); left = run; } else left = num(l.plan) - num(l.fact);
          var cellL = $('[data-left]', tr); cellL.textContent = (num(l.plan) || num(l.fact)) ? fmt(left, true) : '';
          cellL.className = 'r fg-left' + (left < 0 ? ' neg' : '');
          var lover = s !== 'income' && num(l.plan) > 0 && num(l.fact) > num(l.plan);
          tr.classList.toggle('over', lover);
          tr.classList.toggle('noplan', s !== 'income' && !num(l.plan) && num(l.fact) > 0);
          tr.classList.toggle('done', num(l.fact) > 0 && num(l.fact) >= num(l.plan) && num(l.plan) > 0);
        });
      });
      if (v === 'object') {
        var c = calc(oid);
        setCalc('exp:plan', fmt(c.exp.plan, true)); setCalc('exp:fact', fmt(c.exp.fact, true), c.exp.fact > c.exp.plan ? 'over' : '');
        setCalc('exp:left', fmt(c.exp.plan - c.exp.fact, true)); setCalc('exp:flag', c.exp.fact > c.exp.plan ? 'расходы больше плана на ' + money(c.exp.fact - c.exp.plan) : '', c.exp.fact > c.exp.plan ? 'over' : '');
        setCalc('bal:plan', fmt(c.bal.plan, true), c.bal.plan < 0 ? 'neg' : ''); setCalc('bal:fact', fmt(c.bal.fact, true), c.bal.fact < 0 ? 'neg' : '');
        setCalc('contracts', fmt(c.contracts, true)); setCalc('acts', fmt(c.acts, true));
        var nc = S.contracts.filter(function (x) { return x.object === oid; }), ne = nc.filter(function (x) { return x.kind === 'extra'; }).length;
        setCalc('contracts:h', nc.length ? (nc.length - ne) + ' договор' + (ne ? ' и ' + ne + ' доп.' : '') + ' · ' + money(c.contracts) : 'договоров пока нет');
        setCalc('acts:h', 'выполнено на ' + money(c.acts) + (c.contracts ? ' · ' + Math.round(c.acts * 100 / c.contracts) + '% от договоров' : ''));
        setCalc('k:inc', short(c.income.fact)); setCalc('k:inc:h', 'получено · по плану ' + short(c.income.plan));
        setCalc('k:exp', short(c.exp.fact), c.exp.fact > c.exp.plan ? 'over' : ''); setCalc('k:exp:h', 'оплачено · по плану ' + short(c.exp.plan));
        setCalc('k:bal', short(c.bal.fact), c.bal.fact < 0 ? 'neg' : 'okc'); setCalc('k:bal:h', 'по факту · по плану ' + short(c.bal.plan));
        setCalc('k:due', short(c.acts)); setCalc('k:due:h', 'получено ' + short(c.income.fact) + ' · разница ' + short(c.due));
      } else {
        var d = sec(null, 'debt');
        setCalc('k:dplan', short(d.plan)); setCalc('k:dfact', short(d.fact)); setCalc('k:dfact:h', d.plan ? Math.round(d.fact * 100 / d.plan) + '% вернули' : '');
        setCalc('k:dleft', short(d.plan - d.fact)); setCalc('k:dleft:h', 'осталось вернуть'); setCalc('k:dn', String(lines(null, 'debt').length));
      }
    }
    if (v === 'summary') {
      var t = total();
      S.objects.forEach(function (o) {
        var c = calc(o.id);
        ['income', 'labor', 'material', 'overhead', 'exp', 'bal'].forEach(function (k) {
          var over = k !== 'income' && k !== 'bal' && c[k].fact > c[k].plan;
          setCalc('o' + o.id + ':' + k + ':plan', fmt(c[k].plan), k === 'bal' && c[k].plan < 0 ? 'neg' : '');
          setCalc('o' + o.id + ':' + k + ':fact', fmt(c[k].fact), over ? 'over' : (k === 'bal' && c[k].fact < 0 ? 'neg' : ''));
        });
        setCalc('o' + o.id + ':acts', fmt(c.acts)); setCalc('o' + o.id + ':due', fmt(c.due), c.due > 0 ? 'neg' : '');
      });
      ['income', 'labor', 'material', 'overhead', 'debt'].forEach(function (k) { setCalc('t:' + k + ':plan', fmt(t[k].plan, true)); setCalc('t:' + k + ':fact', fmt(t[k].fact, true)); });
      setCalc('t:exp:plan', fmt(t.expAll.plan, true)); setCalc('t:exp:fact', fmt(t.expAll.fact, true));
      setCalc('t:bal:plan', fmt(t.bal.plan, true), t.bal.plan < 0 ? 'neg' : ''); setCalc('t:bal:fact', fmt(t.bal.fact, true), t.bal.fact < 0 ? 'neg' : '');
      setCalc('t:acts', fmt(t.acts, true)); setCalc('t:due', fmt(t.due, true), t.due > 0 ? 'neg' : '');
      setCalc('k:inc', short(t.income.fact)); setCalc('k:inc:h', 'получено · по плану ' + short(t.income.plan));
      setCalc('k:exp', short(t.exp.fact), t.exp.fact > t.exp.plan ? 'over' : ''); setCalc('k:exp:h', 'оплачено · по плану ' + short(t.exp.plan));
      setCalc('k:debt', short(t.debt.plan - t.debt.fact)); setCalc('k:debt:h', 'осталось вернуть · всего ' + short(t.debt.plan));
      setCalc('k:bal', short(t.bal.fact), t.bal.fact < 0 ? 'neg' : 'okc'); setCalc('k:bal:h', 'по факту · по плану ' + short(t.bal.plan));
    }
    // уведомления
    var all = overruns();
    $$('[data-alerts]').forEach(function (box) {
      var o = box.dataset.obj, list = all.filter(function (x) { return o === undefined ? true : (o === '-1' ? x.obj === null : x.obj === +o); });
      box.hidden = !list.length;
      $('[data-alerts-n]', box).textContent = list.length;
      $('[data-alerts-list]', box).innerHTML = list.slice(0, 12).map(function (x) {
        var ob = objById(x.obj);
        return '<li class="' + x.level + '"><span class="mk"></span><span class="df-att"><small>' + esc(x.where) + '</small>' + (ob && o === undefined ? '<a href="' + esc(ob.fin) + '">' + esc(x.text) + '</a>' : esc(x.text)) + '</span></li>';
      }).join('') + (list.length > 12 ? '<li class="info"><span class="mk"></span>и ещё ' + (list.length - 12) + '</li>' : '');
    });
    $$('[data-fin-alert-count]').forEach(function (el) { el.textContent = all.length || ''; el.hidden = !all.length; });
  }

  /* ---------- отрисовка ---------- */
  function render(focus) {
    var view = $('[data-fin-view]'); if (!view) return;
    var v = view.dataset.finView, oid = view.dataset.object ? +view.dataset.object : null;
    if (v === 'object') viewObject(view, oid); else if (v === 'debts') viewDebts(view); else viewSummary(view);
    recalc();
    if (focus) {
      var el = $('[data-rk="' + focus.rk + '"] [data-f="' + focus.f + '"]', view);
      if (el) { el.focus(); if (el.select && el.type !== 'date') el.select(); }
    }
  }

  /* ---------- правка ячеек ---------- */
  function rowOf(tr) {
    var rk = tr.dataset.rk.split(':'), kind = rk[0], id = rk[1];
    return {kind: kind, row: id === 'new' ? null : listOf(kind).filter(function (r) { return String(r.id) === id; })[0]};
  }
  function readVal(el) { return el.dataset.t === 'money' ? num(el.value) : el.value.trim(); }
  function commit(el) {
    var tr = el.closest('tr[data-rk]'); if (!tr) return;
    var view = $('[data-fin-view]'), r = rowOf(tr), f = el.dataset.f, val = readVal(el);
    if (el.dataset.t === 'date') el.toggleAttribute('data-empty', !el.value);
    if (el.dataset.t === 'money') el.value = fmt(val);
    if (r.row) {
      if (String(r.row[f] == null ? '' : r.row[f]) === String(val)) return;
      var ch = {}; ch[f] = val; update(r.kind, r.row, ch);
      if (f === 'kind') tr.classList.toggle('extra', val === 'extra');
      recalc(); return;
    }
    if (val === '' || val === 0 || (f === 'kind')) return;  // пустая новая строка
    var oid = view.dataset.object ? +view.dataset.object : null, row;
    if (r.kind === 'line') row = {object: tr.dataset.sec === 'debt' ? null : oid, section: tr.dataset.sec, name: '', plan: 0, pdate: '', fact: 0, fdate: '', note: ''};
    else if (r.kind === 'contract') row = {object: oid, kind: ($('[data-f="kind"]', tr) || {}).value || 'main', number: '', date: '', subject: '', amount: 0, note: ''};
    else row = {object: oid, work: '', amount: 0, date: '', note: ''};
    row[f] = val;
    if (r.kind === 'line' && f === 'fact' && !row.fdate) row.fdate = today();
    var before = overruns().map(function (x) { return x.key; });
    create(r.kind, row);
    warnNew(before);
    var cols = $$('[data-f]', tr).map(function (x) { return x.dataset.f; }), next = cols[cols.indexOf(f) + 1] || f;
    render({rk: r.kind + ':' + row.id, f: next});
  }
  app.addEventListener('change', function (e) { if (e.target.matches('.fc')) commit(e.target); });
  app.addEventListener('focusin', function (e) { if (e.target.matches('.fc')) e.target.dataset.orig = e.target.value; });
  app.addEventListener('keydown', function (e) {
    var el = e.target; if (!el.matches || !el.matches('.fc')) return;
    if (e.key === 'Escape') { el.value = el.dataset.orig || ''; el.blur(); return; }
    if (e.key === 'Enter') {
      e.preventDefault();
      var tr = el.closest('tr'), f = el.dataset.f, rk = tr.dataset.rk;
      commit(el);
      var cur = $('[data-rk="' + rk + '"]') || tr, nxt = cur.nextElementSibling;
      while (nxt && !$('[data-f="' + f + '"]', nxt)) nxt = nxt.nextElementSibling;
      var to = nxt && $('[data-f="' + f + '"]', nxt);
      if (to) { to.focus(); if (to.select && to.type !== 'date') to.select(); }
    }
  });
  // Удаление строки: два нажатия, без всплывающих окон
  app.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-del]'); if (!b) return;
    if (!b.classList.contains('sure')) {
      $$('.fg-del.sure').forEach(function (x) { x.classList.remove('sure'); x.textContent = '×'; });
      b.classList.add('sure'); b.textContent = 'Удалить?'; return;
    }
    var r = rowOf(b.closest('tr')); if (r.row) { remove(r.kind, r.row); render(); toast('Строка удалена'); }
  });

  /* ---------- «Доход / Расход» ---------- */
  var dlg = $('#finQuick');
  if (dlg) {
    var qf = $('form', dlg), q = qf.elements;
    var objSel = q.object;
    objSel.innerHTML = S.objects.map(function (o) { return '<option value="' + o.id + '">' + esc(o.name) + '</option>'; }).join('') + '<option value="debt">Общий долг компании</option>';
    function qSec() { var c = $('input[name=section]:checked', dlg); return objSel.value === 'debt' ? 'debt' : (c ? c.value : 'labor'); }
    function qSync() {
      var debt = objSel.value === 'debt', s = qSec();
      $('[data-q-secs]', dlg).hidden = debt;
      $('[data-q-name-l]', dlg).textContent = debt ? 'Кому (кредитор)' : s === 'income' ? 'От кого / за что' : 'Кому / за что';
      q.name.placeholder = debt ? 'Например: TOO HARD KZ' : s === 'income' ? 'Например: Поступление от заказчика' : s === 'labor' ? 'Например: Гулом — оплата за работу' : 'Например: Гипс белый';
      var oid = debt ? null : +objSel.value;
      var names = {}; lines(oid, s).forEach(function (l) { if (l.name) names[l.name] = l; });
      $('#finQuickNames').innerHTML = Object.keys(names).map(function (n) { return '<option value="' + esc(n) + '">'; }).join('');
      var m = names[q.name.value.trim()];
      $('[data-q-hint]', dlg).innerHTML = m ? 'Добавится к строке «' + esc(m.name) + '»: было ' + money(m.fact) + (num(m.plan) ? ' из плана ' + money(m.plan) : '') : (q.name.value.trim() ? 'Будет новая строка в блоке «' + SEC[s] + '»' : '');
      $('[data-q-submit]', dlg).textContent = s === 'income' ? 'Записать поступление' : debt ? 'Записать оплату долга' : 'Записать расход';
    }
    function openQuick(preset) {
      qf.reset(); q.date.value = today();
      var view = $('[data-fin-view]'), cur = (preset && preset.object) || (view && view.dataset.object) || (view && view.dataset.finView === 'debts' ? 'debt' : '');
      if (!cur) { try { cur = localStorage.getItem('pb:fin:lastobj') || (window.PBObj && PBObj.get()) || ''; } catch (e) { cur = ''; } }
      if (cur && $('option[value="' + cur + '"]', objSel)) objSel.value = cur;
      var s = (preset && preset.section) || 'labor', radio = $('input[name=section][value="' + s + '"]', dlg); if (radio) radio.checked = true;
      qSync();
      if (dlg.showModal) dlg.showModal(); else dlg.setAttribute('open', '');
      setTimeout(function () { q.amount.focus(); }, 40);
    }
    objSel.addEventListener('change', qSync); q.name.addEventListener('input', qSync);
    $$('input[name=section]', dlg).forEach(function (r) { r.addEventListener('change', qSync); });
    q.amount.addEventListener('blur', function () { if (q.amount.value.trim()) q.amount.value = fmt(num(q.amount.value)); });
    $$('[data-close]', dlg).forEach(function (b) { b.addEventListener('click', function () { dlg.close(); }); });
    dlg.addEventListener('click', function (e) { if (e.target === dlg) dlg.close(); });
    qf.addEventListener('submit', function (e) {
      e.preventDefault(); e.stopImmediatePropagation();
      var amount = num(q.amount.value), s = qSec(), debt = s === 'debt', oid = debt ? null : +objSel.value, name = q.name.value.trim();
      if (!(amount > 0)) { $('[data-q-hint]', dlg).innerHTML = '<span class="bad">Укажите сумму</span>'; q.amount.focus(); return; }
      var before = overruns().map(function (x) { return x.key; });
      var match = name && lines(oid, s).filter(function (l) { return l.name.trim().toLowerCase() === name.toLowerCase(); })[0];
      if (match) {
        var ch = {fact: num(match.fact) + amount, fdate: q.date.value || today()};
        if (q.note.value.trim()) ch.note = q.note.value.trim();
        Object.keys(ch).forEach(function (k) { match[k] = ch[k]; });
        send('line', match, 'save', ch);
      } else {
        create('line', {object: oid, section: s, name: name, plan: 0, pdate: '', fact: amount, fdate: q.date.value || today(), note: q.note.value.trim()});
      }
      try { localStorage.setItem('pb:fin:lastobj', objSel.value); } catch (x) { /* не важно */ }
      dlg.close();
      render();
      toast('Записано: ' + (debt ? 'Долг компании' : objName(oid)) + ' · ' + SHORT[s] + (name ? ' · ' + name : '') + ' — ' + money(amount));
      warnNew(before);
    }, true);
    document.addEventListener('click', function (e) {
      var b = e.target.closest && e.target.closest('[data-fin-quick]'); if (!b) return;
      e.preventDefault(); openQuick({object: b.dataset.object, section: b.dataset.section});
    });
  }

  /* ---------- вернуть данные из таблицы (только для сайта по ссылке) ---------- */
  $$('[data-fin-reset]').forEach(function (b) {
    b.addEventListener('click', function () {
      if (!b.classList.contains('sure')) { b.classList.add('sure'); b.textContent = 'Точно вернуть? Ваши правки удалятся'; return; }
      try { localStorage.removeItem(KEY); } catch (e) { /* ничего */ }
      S = load(); render(); b.classList.remove('sure'); b.textContent = 'Вернуть данные из таблицы'; toast('Данные из таблицы восстановлены');
    });
  });

  /* ---------- Excel по шаблону ---------- */
  window.PBFin = {state: function () { return S; }, calc: calc, total: total, lines: lines, sec: sec, overruns: overruns, num: num, SEC: SEC};
  $$('[data-fin-export]').forEach(function (b) {
    b.addEventListener('click', function () {
      if (!window.PBFinXlsx || !window.JSZip) { toast('Выгрузка ещё загружается, нажмите ещё раз', 'bad'); return; }
      b.disabled = true;
      PBFinXlsx.download(S).then(function () { toast('Файл Excel скачан'); }).catch(function (e) { toast('Не удалось собрать файл: ' + e.message, 'bad'); })
        .then(function () { b.disabled = false; });
    });
  });

  status('ok', LOCAL ? (S.saved ? 'Правки сохранены в этом браузере' : 'Правки сохраняются в этом браузере') : 'Все изменения сохраняются');
  render();
})();
