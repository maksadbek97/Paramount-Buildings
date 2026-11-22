/* Раздел «Документы»: фильтры, сортировка, колонки, экспорт, вкладки карточки, генератор писем.
   Всё работает и в статической демо-версии (без сервера). */
(function () {
  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function store(k, v) { try { if (v === undefined) return JSON.parse(localStorage.getItem('df:' + k) || 'null'); localStorage.setItem('df:' + k, JSON.stringify(v)); } catch (e) { return null; } }

  // Активная вкладка раздела видна и на телефоне
  $$('.df-tabs, .df-ctabs, .df-gsteps').forEach(function (nav) {
    var a = $('.active, .on', nav);
    if (a && nav.scrollWidth > nav.clientWidth) nav.scrollLeft = a.offsetLeft - nav.clientWidth / 2 + a.offsetWidth / 2;
  });

  /* ---------- Реестр и списки ---------- */
  $$('.df-list').forEach(function (box) {
    var key = box.getAttribute('data-key') || 'list';
    var rows = $$('tbody tr', box), tbody = $('tbody', box);
    var chipVal = {}, q = $('[data-q]', box), more = $('[data-more]', box), toggle = $('[data-ftoggle]', box);
    var limit = 25, shown = limit, moreB = $('[data-moreb]', box), info = $('[data-shown]', box);
    var overdue = rows.filter(function (r) { return r.dataset.due === 'overdue'; }).length;
    var od = $('[data-chip="due"] span', box); if (od) od.textContent = overdue;
    if (!overdue && od) od.parentNode.hidden = true;

    function fval(name) { var el = $('[data-f="' + name + '"]', box); if (!el) return ''; return el.type === 'checkbox' ? (el.checked ? '1' : '') : el.value; }
    function apply(keepPage) {
      if (!keepPage) shown = limit;
      var text = (q.value || '').trim().toLowerCase(), n = 0, vis = 0, active = 0;
      ['st', 'resp', 'obj', 'cp', 'dep', 'case', 'due', 'from', 'to', 'miss'].forEach(function (f) { if (fval(f)) active++; });
      var fc = $('[data-fcount]', box); if (fc) fc.textContent = active || '';
      rows.forEach(function (r) {
        var d = r.dataset, ok = true;
        Object.keys(chipVal).forEach(function (k) { if (chipVal[k] && d[k] !== chipVal[k]) ok = false; });
        if (text && d.q.indexOf(text) < 0) ok = false;
        ['st', 'resp', 'obj', 'cp', 'dep', 'case', 'miss'].forEach(function (f) { var v = fval(f); if (v && d[f] !== v) ok = false; });
        var due = fval('due'); if (due && (due === 'has' ? !d.due : d.due !== due)) ok = false;
        var from = fval('from'), to = fval('to');
        if (from && d.date < from) ok = false; if (to && d.date > to) ok = false;
        if (ok) n++;
        var show = ok && n <= shown; r.hidden = !show; if (show) vis++;
      });
      var none = $('[data-none]', box); if (none) none.hidden = n > 0 || !rows.length;
      if (moreB) moreB.hidden = n <= shown;
      if (info) info.textContent = rows.length ? 'Показано ' + vis + ' из ' + n : '';
      store('f:' + key, {chips: chipVal, q: q.value, f: $$('[data-f]', box).map(function (el) { return [el.dataset.f, el.type === 'checkbox' ? el.checked : el.value]; })});
    }
    $$('[data-chip]', box).forEach(function (b) {
      b.addEventListener('click', function () {
        var f = b.dataset.chip, same = b.classList.contains('on') && b.dataset.v;
        $$('[data-chip]', box).forEach(function (x) { x.classList.remove('on'); });
        chipVal = {};
        if (same) { $('[data-chip][data-v=""]', box).classList.add('on'); }
        else { b.classList.add('on'); if (b.dataset.v) chipVal[f] = b.dataset.v; }
        apply();
      });
    });
    q.addEventListener('input', function () { apply(); });
    $$('[data-f]', box).forEach(function (el) { el.addEventListener('change', function () { apply(); }); });
    if (toggle) toggle.addEventListener('click', function () { more.hidden = !more.hidden; toggle.setAttribute('aria-expanded', !more.hidden); });
    $$('[data-reset]', box).forEach(function (b) {
      b.addEventListener('click', function () {
        $$('[data-f]', box).forEach(function (el) { if (el.type === 'checkbox') el.checked = false; else el.value = ''; });
        q.value = ''; chipVal = {}; $$('[data-chip]', box).forEach(function (x) { x.classList.toggle('on', !x.dataset.v); }); apply();
      });
    });
    if (moreB) moreB.addEventListener('click', function () { shown += limit; apply(true); });

    // Сортировка по клику на заголовок
    $$('th[data-sort]', box).forEach(function (th) {
      th.addEventListener('click', function () {
        var k = th.dataset.sort, dir = th.classList.contains('asc') ? -1 : 1;
        $$('th[data-sort]', box).forEach(function (x) { x.classList.remove('asc', 'desc'); });
        th.classList.add(dir > 0 ? 'asc' : 'desc');
        var attr = {title: 'title', date: 'date', due: 'duev', amount: 'amount', left: 'left'}[k];
        rows.sort(function (a, b) {
          var x = a.dataset[attr], y = b.dataset[attr];
          if (k === 'amount' || k === 'left') { x = +x; y = +y; }
          return (x > y ? 1 : x < y ? -1 : 0) * dir;
        });
        rows.forEach(function (r) { tbody.appendChild(r); }); apply(true);
      });
    });

    // Настройка колонок (запоминается в браузере)
    var menu = $('[data-colmenu]', box), hiddenCols = store('cols:' + key);
    if (menu) {
      var ths = $$('th[data-col]', box);
      if (!hiddenCols) hiddenCols = ths.filter(function (t) { return t.hasAttribute('data-off'); }).map(function (t) { return t.dataset.col; });
      ths.forEach(function (th) {
        var c = th.dataset.col, l = document.createElement('label');
        l.innerHTML = '<input type="checkbox"> ' + th.textContent;
        var cb = l.firstChild; cb.checked = hiddenCols.indexOf(c) < 0; cb.disabled = c === 'doc';
        cb.addEventListener('change', function () {
          hiddenCols = hiddenCols.filter(function (x) { return x !== c; }); if (!cb.checked) hiddenCols.push(c);
          store('cols:' + key, hiddenCols); cols();
        });
        menu.appendChild(l);
      });
    }
    function cols() { $$('[data-col]', box).forEach(function (el) { el.style.display = (hiddenCols || []).indexOf(el.dataset.col) >= 0 ? 'none' : ''; }); }
    cols();

    // Восстановить сохранённые фильтры; #g=approval с обзора важнее
    var saved = store('f:' + key), hash = (location.hash.match(/g=([\w-]+)/) || [])[1];
    if (hash) saved = {chips: {g: hash}, q: '', f: []};
    if (saved) {
      q.value = saved.q || '';
      (saved.f || []).forEach(function (p) { var el = $('[data-f="' + p[0] + '"]', box); if (el) { if (el.type === 'checkbox') el.checked = p[1]; else el.value = p[1]; } });
      chipVal = saved.chips || {};
      var hk = Object.keys(chipVal)[0];
      if (hk) {
        var btn = $('[data-chip="' + hk + '"][data-v="' + chipVal[hk] + '"]', box);
        if (btn) { $$('[data-chip]', box).forEach(function (x) { x.classList.remove('on'); }); btn.classList.add('on'); btn.hidden = false; }
        else if (hk === 'g') { // группы нет в чипах — фильтруем по статусу
          chipVal = {g: chipVal[hk]};
        }
      }
    }
    // Объект, выбранный в шапке, важнее сохранённого фильтра списка
    var objSel = $('[data-f="obj"]', box);
    function useObj(v) {
      if (!objSel) return;
      if (v && !$('option[value="' + v + '"]', objSel)) {  // у объекта нет документов в этом списке
        var o = document.createElement('option'); o.value = v; o.textContent = window.PBObj ? PBObj.name(v) : v; objSel.appendChild(o);
      }
      objSel.value = v;
    }
    if (window.PBObj) useObj(PBObj.get());
    if (objSel) objSel.addEventListener('change', function () { if (window.PBObj) PBObj.set(objSel.value); });
    document.addEventListener('pb:obj', function (e) { useObj(e.detail); apply(); });
    apply();
  });

  /* ---------- Экспорт видимых строк в CSV (Excel) ---------- */
  $$('[data-export]').forEach(function (b) {
    b.addEventListener('click', function () {
      var table = b.dataset.target ? $(b.dataset.target) : $('table', b.closest('.df-list'));
      if (!table) return;
      var heads = $$('thead th', table).filter(function (th) { return th.style.display !== 'none'; });
      var idx = heads.map(function (th) { return th.cellIndex; });
      var lines = [heads.map(function (th) { return th.textContent.trim(); }).filter(Boolean).join(';')];
      $$('tbody tr', table).forEach(function (tr) {
        if (tr.hidden) return;
        lines.push(idx.filter(function (i) { return heads[idx.indexOf(i)].textContent.trim(); }).map(function (i) {
          var td = tr.cells[i]; return td ? '"' + td.innerText.replace(/\s+/g, ' ').replace(/Скачать/g, '').trim().replace(/"/g, '""') + '"' : '';
        }).join(';'));
      });
      var a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob(['﻿' + lines.join('\n')], {type: 'text/csv;charset=utf-8'}));
      a.download = (b.dataset.export || 'dokumenty') + '.csv'; document.body.appendChild(a); a.click(); a.remove();
    });
  });

  /* ---------- Печать PDF ---------- */
  $$('[data-print]').forEach(function (a) {
    a.addEventListener('click', function (e) {
      e.preventDefault(); var w = window.open(a.href, '_blank');
      if (w) w.addEventListener('load', function () { try { w.print(); } catch (x) {} });
    });
  });

  /* ---------- Вкладки карточки документа ---------- */
  var ctabs = $$('.df-ctabs [data-tab]');
  function openTab(name) {
    if (!$('[data-panel="' + name + '"]')) name = 'main';
    ctabs.forEach(function (t) { t.classList.toggle('active', t.dataset.tab === name); });
    $$('[data-panel]').forEach(function (p) { p.hidden = p.dataset.panel !== name; });
  }
  ctabs.forEach(function (t) { t.addEventListener('click', function (e) { e.preventDefault(); openTab(t.dataset.tab); history.replaceState(null, '', '#' + t.dataset.tab); }); });
  if (ctabs.length && location.hash) openTab(location.hash.slice(1));

  /* ---------- Причина для отклонения, возврата, отмены ---------- */
  var dlg = $('#dfReason');
  $$('button[data-reason]').forEach(function (b) {
    b.addEventListener('click', function (e) {
      if (!dlg || !dlg.showModal) return;
      e.preventDefault();
      var form = b.closest('form'), ta = $('[data-text]', dlg);
      $('[data-title]', dlg).textContent = b.dataset.reason;
      ta.value = ''; dlg.showModal(); ta.focus();
      dlg.onclose = function () {
        if (dlg.returnValue !== 'ok' || !ta.value.trim()) return;
        form.querySelector('[name=reason]').value = ta.value.trim();
        if (form.requestSubmit) form.requestSubmit(); else form.submit();
      };
    });
  });

  /* ---------- Поручения: поиск и исполнитель ---------- */
  var tq = $('#tQ'), tw = $('#tWho');
  function tasksFilter() {
    var s = (tq.value || '').toLowerCase(), w = tw.value;
    $$('.df-task').forEach(function (t) { t.hidden = (s && t.dataset.q.indexOf(s) < 0) || (w && t.dataset.who !== w); });
  }
  if (tq) { tq.addEventListener('input', tasksFilter); tw.addEventListener('change', tasksFilter); }

  /* ---------- Архив: поиск и год ---------- */
  var aq = $('#aQ'), ay = $('#aYear');
  function archFilter() {
    var s = (aq.value || '').toLowerCase(), y = ay.value, n = 0;
    $$('#aTable tbody tr[data-q]').forEach(function (r) { var ok = (!s || r.dataset.q.indexOf(s) >= 0) && (!y || r.dataset.year === y); r.hidden = !ok; if (ok) n++; });
    $('#aNone').hidden = n > 0;
  }
  if (aq) { aq.addEventListener('input', archFilter); ay.addEventListener('change', archFilter); }

  /* ---------- Генератор писем на бланке ---------- */
  var gen = $('#dfGen');
  if (!gen) return;
  var step = 1, last = 7, steps = $$('#gSteps li'), err = $('#gErr');
  var paper = $('#gPaper'), home = $('#gPvHome'), slot = $('#gPvSlot');
  function val(n) { var el = gen.elements[n]; if (!el) return ''; if (el.length && !el.tagName) { for (var i = 0; i < el.length; i++) if (el[i].checked) return el[i].value; return ''; } return el.value; }
  function esc(s) { return s.replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); }
  function tpl() { return $('input[name=template]:checked', gen); }
  function letterDoc() {
    var s = $('#gSigner'), o = s && s.options[s.selectedIndex], mode = val('sign_mode'), t = tpl();
    var d = window.PBBlank ? window.PBBlank.data() : {}, sealSel = $('#gSeal');
    if (t && t.dataset.rule === 'none') mode = 'none';
    return {kind: 'letter', number: paper.dataset.number, date: paper.dataset.date,
      addressee: val('addressee').trim(), subject: val('subject').trim(),
      paragraphs: val('body').split('\n').map(function (x) { return x.trim(); }).filter(Boolean),
      attachments: val('attachments').split('\n').map(function (x) { return x.trim(); }).filter(Boolean),
      signerPos: o ? (o.dataset.pos || 'Директор') : 'Директор', signerName: o && window.PBBlank ? window.PBBlank.shortName(o.dataset.name) : '',
      sign: mode === 'sign' || mode === 'both', seal: (mode === 'seal' || mode === 'both') && !!(sealSel && sealSel.options.length),
      executor: d.executor || '', executorPhone: d.executor_phone || ''};
  }
  var drawing = 0;
  function render() {
    var s = $('#gSigner'), o = s && s.options[s.selectedIndex];
    if (o) $('#gSignImg').value = o.dataset.name + ' — утверждённый образ';
    $('#gSealBox').style.display = val('sign_mode') === 'none' ? 'none' : '';
    if (drawing || !window.PBBlank) return;
    drawing = requestAnimationFrame(function () { drawing = 0; window.PBBlank.draw($('#gCanvas'), letterDoc(), 1); });
  }
  function rule() {
    var t = tpl(), r = t ? t.dataset.rule : 'ask', box = $('#gRule');
    var radios = $$('input[name=sign_mode]', gen);
    radios.forEach(function (x) { x.disabled = false; });
    var force = {sign: 'sign', seal: 'seal', both: 'both', none: 'none'}[r];
    box.hidden = !force;
    if (force) {
      radios.forEach(function (x) { x.disabled = x.value !== force; x.checked = x.value === force; });
      box.textContent = 'Правило бланка: ' + {sign: 'подпись обязательна', seal: 'печать обязательна', both: 'подпись и печать обязательны', none: 'без подписи и печати'}[r] + '.';
    }
  }
  function problems(upTo) {
    var p = [];
    if (upTo >= 1 && !tpl()) p.push('Выберите фирменный бланк.');
    if (upTo >= 2 && !val('addressee').trim()) p.push('Укажите адресата.');
    if (upTo >= 3 && !val('subject').trim()) p.push('Укажите тему письма.');
    if (upTo >= 3 && !val('body').trim()) p.push('Напишите текст письма.');
    if (upTo >= 5 && !val('sign_mode')) p.push('Ответьте на вопрос «Добавить подпись и печать на документ?».');
    return p;
  }
  function show(n) {
    var p = n > step ? problems(Math.min(n - 1, 5)) : [];
    if (p.length) { err.innerHTML = p.join('<br>'); err.hidden = false; return; }
    err.hidden = true; step = n;
    $$('fieldset[data-step]', gen).forEach(function (f) { f.hidden = +f.dataset.step !== n; });
    steps.forEach(function (li) { var k = +li.dataset.go; li.classList.toggle('on', k === n); li.classList.toggle('done', k < n); });
    $('#gPrev').style.visibility = n === 1 ? 'hidden' : '';
    $('#gNext').hidden = n === last;
    $('.df-gwrap').classList.toggle('pv', n === 6);
    if (n === 6) slot.appendChild(home); else if (home.parentNode !== $('.df-gside')) $('.df-gside').appendChild(home);
    if (n === 7) {
      var t = tpl(), mode = val('sign_mode'), s = $('#gSigner'), labels = {both: 'подпись и печать', sign: 'только подпись', seal: 'только печать', none: 'без подписи и печати'};
      $('#gCheck').innerHTML = [['Бланк', t ? t.dataset.name : '—'], ['Адресат', val('addressee')], ['Тема', val('subject')],
        ['Подписант', s ? s.options[s.selectedIndex].text : '—'], ['Подпись и печать', labels[mode] || 'не выбрано'],
        ['Приложений', val('attachments').trim() ? val('attachments').trim().split(/\n+/).length : 'нет']].map(function (r) {
        return '<li><span>' + r[0] + '</span><b>' + esc(String(r[1])) + '</b></li>'; }).join('');
    }
    var top = $('.df-gsteps'); if (top && window.scrollY > top.offsetTop) window.scrollTo({top: top.offsetTop - 70, behavior: 'smooth'});
  }
  steps.forEach(function (li) { li.addEventListener('click', function () { show(+li.dataset.go); }); });
  $('#gNext').addEventListener('click', function () { show(Math.min(step + 1, last)); });
  $('#gPrev').addEventListener('click', function () { show(Math.max(step - 1, 1)); });
  gen.addEventListener('input', render);
  gen.addEventListener('change', function (e) { if (e.target.name === 'template') rule(); render(); });
  $$('[data-ins]', gen).forEach(function (b) {
    b.addEventListener('click', function () {
      var ta = $('#gBody'), s = ta.selectionStart || ta.value.length, ins = b.dataset.ins;
      if (s && ta.value[s - 1] !== '\n') ins = '\n' + ins;
      ta.value = ta.value.slice(0, s) + ins + ta.value.slice(s); ta.focus(); render();
    });
  });
  var par = $('#gPar');
  if (par) par.addEventListener('change', function () {
    var o = par.options[par.selectedIndex];
    if (o.dataset.to && !val('addressee')) gen.elements.addressee.value = o.dataset.to;
    if (o.dataset.subj && !val('subject')) gen.elements.subject.value = 'Ответ: ' + o.dataset.subj;
    render();
  });
  var files = $('#gFiles'), dz = $('.df-dropz', gen);
  function listFiles(fl) { $('#gFList').innerHTML = Array.prototype.map.call(fl, function (f) { return '<span>' + esc(f.name) + '</span>'; }).join(''); }
  files.addEventListener('change', function () { listFiles(files.files); });
  ['dragover', 'dragenter'].forEach(function (ev) { dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.add('over'); }); });
  ['dragleave', 'drop'].forEach(function (ev) { dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.remove('over'); }); });
  dz.addEventListener('drop', function (e) { if (e.dataTransfer.files.length) { try { files.files = e.dataTransfer.files; } catch (x) {} listFiles(e.dataTransfer.files); } });
  gen.addEventListener('submit', function (e) {
    var p = problems(5);
    if (p.length) { e.preventDefault(); err.innerHTML = p.join('<br>'); err.hidden = false; return; }
    if (gen.dataset.demo) {
      e.preventDefault();
      // Демо без сервера: PDF и Word собираем в браузере из того, что введено, на выбранном бланке
      var doc = letterDoc(), t = tpl(), num = doc.number || 'b-n';
      ['#gPdf', '#gDocx', '#gPrint'].forEach(function (id) { var a = $(id); a.removeAttribute('href'); a.hidden = false; });
      window.PBBlank.pdfBlob(doc).then(function (b) {
        var u = URL.createObjectURL(b); $('#gPdf').href = u; $('#gPrint').href = u;
        $('#gPdf').setAttribute('download', 'Письмо ' + num + '.pdf');
      });
      window.PBBlank.docxBlob(doc, t && t.dataset.docxSrc).then(function (b) {
        $('#gDocx').href = URL.createObjectURL(b); $('#gDocx').setAttribute('download', 'Письмо ' + num + '.docx');
      }).catch(function () { $('#gDocx').hidden = true; });
      $$('fieldset[data-step]', gen).forEach(function (f) { f.hidden = true; });
      $('#gNav').hidden = true; $('#gDone').hidden = false;
      steps.forEach(function (li) { li.classList.remove('on'); li.classList.add('done'); });
      $('#gWa').href = 'https://wa.me/?text=' + encodeURIComponent('Письмо № ' + $('#gDoneNum').textContent + ': ' + val('subject'));
      window.scrollTo({top: 0, behavior: 'smooth'});
    }
  });
  rule(); render(); show(1);
})();
