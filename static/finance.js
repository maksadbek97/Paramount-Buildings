/* Раздел «Финансы»: добавить, изменить, отметить оплату, удалить — прямо в списке, в одном окне.
   Сохраняет сервер; в статической демо-версии окно открывается, но данные не сохраняются. */
(function () {
  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  var line = $('#fnLine'), pay = $('#fnPay');
  if (!line) return;

  function num(v) { v = String(v || '').replace(/[\s ]/g, '').replace('−', '-').replace(',', '.'); var n = parseFloat(v); return isNaN(n) ? 0 : n; }
  function fmt(n) {
    var neg = n < 0; n = Math.abs(Math.round(n * 100) / 100);
    var p = String(n).split('.'), i = p[0].replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
    return (neg ? '−' : '') + i + (p[1] ? ',' + p[1] : '');
  }
  function show(d) { if (d.showModal) d.showModal(); else d.setAttribute('open', ''); }
  $$('[data-close]').forEach(function (b) { b.addEventListener('click', function () { b.closest('dialog').close(); }); });
  $$('dialog.fn-dialog').forEach(function (d) {
    d.addEventListener('click', function (e) { if (e.target === d) d.close(); });  // клик по фону закрывает
  });
  // Суммы показываем с пробелами: 1 500 000
  $$('[data-money]').forEach(function (el) {
    el.addEventListener('blur', function () { if (el.value.trim()) el.value = fmt(num(el.value)).replace('−', '-'); });
  });

  /* ---------- Окно строки ---------- */
  var form = $('form', line), f = form.elements, del = $('[data-del]', line), delForm = $('#fnDel');
  var LABELS = {
    debt: ['Кому должны', 'Сумма долга, ₸', 'Срок оплаты', 'Факт оплаты, ₸'],
    income: ['Наименование / от кого', 'План, ₸', 'Плановая дата', 'Получено (факт), ₸'],
    other: ['Наименование / получатель', 'План, ₸', 'Плановая дата', 'Оплачено (факт), ₸']
  };
  function sync() {
    var s = f.section.value, debt = s === 'debt', L = LABELS[debt ? 'debt' : (s === 'income' ? 'income' : 'other')];
    $('[data-objfield]', line).hidden = debt;
    $('[data-name-l]', line).textContent = L[0]; $('[data-plan-l]', line).textContent = L[1];
    $('[data-pdate-l]', line).textContent = L[2]; $('[data-fact-l]', line).textContent = L[3];
    var left = num(f.plan_amount.value) - num(f.fact_amount.value);
    $('[data-left]', line).innerHTML = (f.plan_amount.value || f.fact_amount.value) ? 'Остаток: <b>' + fmt(left) + ' ₸</b>' : '';
  }
  f.section.addEventListener('change', sync);
  f.plan_amount.addEventListener('input', sync); f.fact_amount.addEventListener('input', sync);

  function resetDel() { del.textContent = 'Удалить'; del.classList.remove('sure'); del.dataset.sure = ''; }
  function openNew(btn) {
    form.reset();
    form.action = form.dataset.new;
    f.section.value = btn.dataset.section || 'income';
    f.construction_object.value = btn.dataset.object || '';
    $('[data-title]', line).textContent = 'Новая запись';
    $('[data-submit]', line).textContent = 'Добавить';
    del.hidden = true; resetDel(); sync(); show(line);
    setTimeout(function () { (f.construction_object.value || f.section.value === 'debt' ? f.name : f.construction_object).focus(); }, 30);
  }
  function openEdit(row) {
    var d = row.dataset;
    form.action = form.dataset.edit.replace('/0/', '/' + d.id + '/');
    delForm.action = delForm.dataset.url.replace('/0/', '/' + d.id + '/');
    f.section.value = d.section; f.construction_object.value = d.object || '';
    f.name.value = d.name; f.note.value = d.note || '';
    f.plan_amount.value = num(d.plan) ? fmt(num(d.plan)) : ''; f.fact_amount.value = num(d.fact) ? fmt(num(d.fact)) : '';
    f.plan_date.value = d.pdate || ''; f.fact_date.value = d.fdate || '';
    $('[data-title]', line).textContent = 'Изменить строку';
    $('[data-submit]', line).textContent = 'Сохранить';
    del.hidden = false; resetDel(); sync(); show(line);
  }
  // Удаление в два нажатия, без всплывающих окон браузера
  del.addEventListener('click', function (e) {
    if (!del.dataset.sure) { e.preventDefault(); del.dataset.sure = '1'; del.classList.add('sure'); del.textContent = 'Точно удалить?'; }
  });
  form.addEventListener('submit', function (e) {
    if (!f.name.value.trim() || (f.section.value !== 'debt' && !f.construction_object.value)) {
      e.preventDefault(); e.stopImmediatePropagation();
      (f.name.value.trim() ? f.construction_object : f.name).focus();
      $('[data-left]', line).innerHTML = '<span class="bad">Заполните ' + (f.name.value.trim() ? 'объект' : 'наименование') + '</span>';
    }
  }, true);

  /* ---------- Окно оплаты ---------- */
  var pform = pay && $('form', pay);
  function payLeft() {
    var a = pform.elements.amount, rest = num(a.dataset.left) - num(a.value);
    $('[data-left]', pay).innerHTML = rest > 0 ? 'После записи останется <b>' + fmt(rest) + ' ₸</b>' :
      (rest < 0 ? '<span class="warn-t">Больше плана на ' + fmt(-rest) + ' ₸</span>' : 'Строка будет закрыта полностью');
  }
  function openPay(row) {
    var d = row.dataset, inc = d.income === '1', left = num(d.left);
    pform.action = pform.dataset.url.replace('/0/', '/' + d.id + '/');
    $('[data-title]', pay).textContent = inc ? 'Записать поступление' : 'Записать оплату';
    $('[data-what]', pay).textContent = d.name + ' · остаток ' + fmt(left) + ' ₸';
    pform.elements.amount.value = fmt(left);
    pform.elements.amount.dataset.left = left;
    payLeft(); show(pay);
    setTimeout(function () { pform.elements.amount.select(); }, 30);
  }
  if (pform) pform.elements.amount.addEventListener('input', payLeft);

  document.addEventListener('click', function (e) {
    var t = e.target.closest && e.target.closest('[data-fn-add],[data-fn-edit],[data-fn-pay],tr.fn-link');
    if (!t) return;
    if (t.hasAttribute('data-fn-add')) { e.preventDefault(); openNew(t); }
    else if (t.hasAttribute('data-fn-edit')) { e.preventDefault(); openEdit(t.closest('tr')); }
    else if (t.hasAttribute('data-fn-pay')) { e.preventDefault(); openPay(t.closest('tr')); }
    else if (!e.target.closest('a,button')) { location.href = t.dataset.href; }
  });
  // В демо сохранение отключено: окно закрываем, чтобы было видно сообщение
  $$('dialog.fn-dialog form[method=post]').forEach(function (fm) {
    fm.addEventListener('submit', function (e) { if (e.defaultPrevented) { var d = fm.closest('dialog'); if (d.open) d.close(); } });
  });
})();
