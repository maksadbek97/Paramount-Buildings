/* Раздел «Объекты»: фильтры и поиск в списке, экспорт, подтверждение опасных действий,
   фильтры-чипы во вкладках карточки, предупреждение о несохранённых изменениях. */
(function () {
  'use strict';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var store = {
    get: function (k) { try { return JSON.parse(sessionStorage.getItem(k) || 'null'); } catch (e) { return null; } },
    set: function (k, v) { try { sessionStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* приватный режим */ } }
  };

  /* ---------- Подтверждение действий (приостановить, архив и т.п.) ---------- */
  var TEXTS = {
    pause: ['Приостановить объект?', 'Работы, заявки и задачи сохранятся. Объект можно будет возобновить в любой момент.', true, 'Приостановить'],
    resume: ['Возобновить объект?', 'Объект вернётся в прежний статус и снова появится в работе.', false, 'Возобновить'],
    archive: ['Отправить объект в архив?', 'Объект уйдёт из рабочих списков. Все данные и история сохранятся, редактирование будет ограничено.', false, 'В архив'],
    reopen: ['Открыть объект повторно?', 'Объект вернётся в статус «Завершение». Причина попадёт в журнал.', true, 'Открыть'],
    close: ['Закрыть объект?', 'Все обязательные пункты чек-листа выполнены. После закрытия данные переходят в режим ограниченного редактирования.', false, 'Закрыть объект'],
    activate: ['Перевести объект в работу?', 'Статус станет «Активный».', false, 'В работу']
  };
  var dlg = $('#obConfirm');
  if (dlg) {
    var form = $('form', dlg), reasonBox = $('[data-reason]', dlg), err = $('[data-err]', dlg);
    document.addEventListener('click', function (e) {
      var a = e.target.closest('[data-confirm]');
      if (!a) return;
      e.preventDefault();
      var t = TEXTS[a.getAttribute('data-confirm')];
      form.setAttribute('action', a.getAttribute('data-url'));
      form.elements.action.value = a.getAttribute('data-confirm');
      $('h3', dlg).textContent = t[0];
      $('[data-text]', dlg).textContent = (a.getAttribute('data-name') ? '«' + a.getAttribute('data-name') + '». ' : '') + t[1];
      reasonBox.hidden = !t[2];
      form.elements.reason.value = '';
      err.hidden = true;
      $('[data-ok]', dlg).textContent = t[3];
      $$('details[open]').forEach(function (d) { d.removeAttribute('open'); });
      if (dlg.showModal) dlg.showModal(); else dlg.setAttribute('open', '');
      if (t[2]) form.elements.reason.focus();
    });
    form.addEventListener('submit', function (e) {
      if (!reasonBox.hidden && !form.elements.reason.value.trim()) {
        e.preventDefault(); e.stopImmediatePropagation(); err.hidden = false; form.elements.reason.focus(); return;
      }
      setTimeout(function () { if (dlg.close) dlg.close(); else dlg.removeAttribute('open'); }, 0);
    }, true);
    $('[data-close]', dlg).addEventListener('click', function () { if (dlg.close) dlg.close(); else dlg.removeAttribute('open'); });
    dlg.addEventListener('click', function (e) { if (e.target === dlg && dlg.close) dlg.close(); });
  }

  /* Меню действий строки: показываем поверх таблицы (таблица может прокручиваться по горизонтали) */
  $$('.rowmenu').forEach(function (d) {
    d.addEventListener('toggle', function () {
      var m = $('.dd-menu', d);
      if (!d.open || window.matchMedia('(max-width: 899px)').matches) { m.classList.toggle('fixed', false); m.style.cssText = ''; return; }
      var r = $('summary', d).getBoundingClientRect();
      m.classList.add('fixed');
      var w = Math.max(m.offsetWidth, 220), h = m.offsetHeight;
      m.style.left = Math.max(8, r.right - w) + 'px';
      m.style.top = (r.bottom + 6 + h > window.innerHeight ? Math.max(8, r.top - h - 6) : r.bottom + 6) + 'px';
    });
  });
  window.addEventListener('scroll', function () {
    if (window.matchMedia('(max-width: 899px)').matches) return;
    $$('.rowmenu[open]').forEach(function (d) { d.open = false; });
  }, { passive: true });

  /* ---------- Список объектов ---------- */
  var list = $('#obList');
  if (list) {
    var rows = $$('tbody tr', list), q = $('#obQ'), more = $('#obMore'), toggle = $('#obFToggle');
    var state = store.get('ob-filters') || {};
    if (!state.status || location.search.indexOf('status=') >= 0) state.status = list.getAttribute('data-status');
    var selects = $$('[data-f]', more);

    function apply() {
      var text = (q.value || '').trim().toLowerCase(), n = 0, extra = 0, f = {};
      selects.forEach(function (s) { f[s.getAttribute('data-f')] = s.value; if (s.value) extra++; });
      rows.forEach(function (r) {
        var st = state.status, ok =
          (st === 'all' || (st === 'working' ? r.dataset.group === 'working' : r.dataset.st === st)) &&
          (!text || r.dataset.q.indexOf(text) >= 0) &&
          (!f.manager || r.dataset.manager === f.manager) && (!f.client || r.dataset.client === f.client) &&
          (!f.city || r.dataset.city === f.city) && (!f.kind || r.dataset.kind === f.kind) &&
          (!f.from || (r.dataset.start && r.dataset.start >= f.from)) &&
          (!f.to || (r.dataset.end && r.dataset.end <= f.to));
        r.hidden = !ok;
        if (ok) n++;
      });
      $$('.fchip', list).forEach(function (b) { b.classList.toggle('on', b.dataset.status === state.status); });
      $('#obNone').hidden = n > 0 || !rows.length;
      $('#obFCount').textContent = extra ? extra : '';
      $('#obFoot').textContent = rows.length ? 'Показано объектов: ' + n + ' из ' + rows.length : '';
      state.q = q.value; state.f = f;
      store.set('ob-filters', state);
    }
    $$('.fchip', list).forEach(function (b) {
      b.addEventListener('click', function () { state.status = b.dataset.status; apply(); });
    });
    q.addEventListener('input', apply);
    selects.forEach(function (s) { s.addEventListener('change', apply); });
    toggle.addEventListener('click', function () {
      more.hidden = !more.hidden; toggle.setAttribute('aria-expanded', String(!more.hidden));
    });
    function reset() { q.value = ''; selects.forEach(function (s) { s.value = ''; }); state.status = 'working'; apply(); }
    $('#obReset').addEventListener('click', reset);
    $$('[data-reset]', list).forEach(function (b) { b.addEventListener('click', reset); });
    // Восстановить фильтры после возврата из карточки объекта
    q.value = state.q || '';
    if (state.f) selects.forEach(function (s) { s.value = state.f[s.getAttribute('data-f')] || ''; });
    if (selects.some(function (s) { return s.value; })) { more.hidden = false; toggle.setAttribute('aria-expanded', 'true'); }
    apply();

    // Экспорт: то, что сейчас видно в списке (с учётом фильтров), все поля ТЗ п. 4.1
    $$('[data-export]').forEach(function (a) {
      a.addEventListener('click', function (e) {
        e.preventDefault();
        $('#exportMenu').removeAttribute('open');
        if (a.dataset.export === 'print') { window.print(); return; }
        var data = JSON.parse($('#obExport').textContent);
        var visible = {};
        rows.forEach(function (r) { if (!r.hidden) visible[r.dataset.id] = true; });
        data = data.filter(function (d) { return visible[d.id]; });
        if (!data.length) return;
        var cols = Object.keys(data[0]).filter(function (k) { return k !== 'id'; });
        var esc = function (v) { v = String(v === null || v === undefined ? '' : v); return /[";\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
        var csv = [cols.map(esc).join(';')].concat(data.map(function (d) { return cols.map(function (c) { return esc(d[c]); }).join(';'); })).join('\r\n');
        var blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
        var link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = 'objects-' + new Date().toISOString().slice(0, 10) + '.csv';
        document.body.appendChild(link); link.click();
        setTimeout(function () { URL.revokeObjectURL(link.href); link.remove(); }, 500);
      });
    });
  }

  /* ---------- Чипы-фильтры во вкладках (документы, фото, история, задачи) ---------- */
  $$('[data-chips]').forEach(function (set) {
    var target = $(set.getAttribute('data-chips'));
    if (!target) return;
    var items = $$('[data-cat]', target), none = $('[data-none]', target.parentNode);
    set.addEventListener('click', function (e) {
      var b = e.target.closest('button[data-v]');
      if (!b) return;
      $$('button', set).forEach(function (x) { x.classList.toggle('on', x === b); });
      var n = 0;
      items.forEach(function (i) {
        var ok = b.dataset.v === '' || (' ' + i.dataset.cat + ' ').indexOf(' ' + b.dataset.v + ' ') >= 0;
        i.hidden = !ok; if (ok) n++;
      });
      if (none) none.hidden = n > 0;
    });
  });

  /* ---------- Вкладки: «Ещё» на ПК, прокрутка к активной на телефоне ---------- */
  var tabs = $('.obtabs');
  if (tabs) {
    var act = $('a.active', tabs);
    if (act && window.matchMedia('(max-width: 1199px)').matches) act.scrollIntoView({ block: 'nearest', inline: 'center' });
  }

  /* ---------- Форма объекта: несохранённые изменения ---------- */
  var of = $('form.ob-form');
  if (of) {
    var dirty = false, submitting = false;
    of.addEventListener('input', function () { dirty = true; });
    of.addEventListener('change', function () { dirty = true; });
    of.addEventListener('submit', function () { submitting = true; });
    window.addEventListener('beforeunload', function (e) {
      if (dirty && !submitting) { e.preventDefault(); e.returnValue = ''; }
    });
    var leave = $('#obLeave');
    $$('[data-leave]').forEach(function (a) {
      a.addEventListener('click', function (e) {
        if (!dirty || !leave) return;
        e.preventDefault();
        $('[data-go]', leave).setAttribute('href', a.getAttribute('href'));
        leave.showModal ? leave.showModal() : leave.setAttribute('open', '');
      });
    });
    if (leave) {
      $('[data-stay]', leave).addEventListener('click', function () { leave.close ? leave.close() : leave.removeAttribute('open'); });
      $('[data-go]', leave).addEventListener('click', function () { submitting = true; });
    }
    // Подсказка кода: показываем, какой код присвоится, если поле пустое
    var city = of.elements.city, code = of.elements.code, hint = $('#codeHint');
    var PREF = JSON.parse(($('#cityPrefix') || { textContent: '{}' }).textContent);
    function codeHint() {
      if (!hint || !code) return;
      var p = PREF[city && city.value] || 'OBJ';
      hint.textContent = code.value.trim() ? '' : 'Оставьте пустым — система присвоит свободный код вида ' + p + '-NN.';
    }
    if (city) city.addEventListener('change', codeHint);
    if (code) code.addEventListener('input', codeHint);
    codeHint();
    // Первое поле с ошибкой — в фокус
    var bad = $('.field.has-err input, .field.has-err select, .field.has-err textarea', of);
    if (bad) { bad.focus({ preventScroll: true }); bad.closest('.field').scrollIntoView({ block: 'center' }); }
  }
})();
