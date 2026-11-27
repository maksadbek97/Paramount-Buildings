/* «Скачать Excel»: файл в формате таблицы компании «Paramount Фин план до 2026 года».
   Те же листы (Сводная таблица, листы объектов, Лист1 с АВР, Долги), те же стили, цвета, ширины столбцов,
   закреплённые строки и формулы — в Excel файл можно дальше править как обычно, итоги пересчитаются сами.
   Стили и тема взяты из присланного шаблона (static/finance-xlsx-base.js). */
(function () {
  'use strict';
  var SEC_NAMES = {income: 'Поступления', labor: 'Оплата работ', material: 'Материальные расходы', overhead: 'Накладные расходы'};
  var ACT_NAME = {Arna: 'Арна', Daryn: 'Дарын', Atlant: 'Атлант', Zerde: 'Зерде', 'Nexpo Global': 'Глобал'};
  var NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"';
  var HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n';

  function x(s) { return String(s).replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); }
  function col(n) { var s = ''; n++; while (n > 0) { var m = (n - 1) % 26; s = String.fromCharCode(65 + m) + s; n = Math.floor((n - 1) / 26); } return s; }
  function serial(iso) { var p = iso.split('-'); return (Date.UTC(+p[0], +p[1] - 1, +p[2]) - Date.UTC(1899, 11, 30)) / 86400000; }
  function n(v) { return typeof v === 'number' ? v : (parseFloat(v) || 0); }

  /* Лист: строки → XML. Ячейка: {s: стиль, v: число|строка|null, f: формула, d: дата ISO} */
  function Sheet(name) { this.name = name; this.rows = {}; this.heights = {}; this.merges = []; }
  Sheet.prototype.set = function (r, c, cell) { (this.rows[r] = this.rows[r] || {})[c] = cell; };
  Sheet.prototype.row = function (r, styles, values, height) {
    for (var c = 0; c < styles.length; c++) {
      var v = values ? values[c] : null, cell = {s: styles[c]};
      if (v && typeof v === 'object') { for (var k in v) cell[k] = v[k]; } else cell.v = v;
      this.set(r, c, cell);
    }
    if (height) this.heights[r] = height;
  };
  Sheet.prototype.xml = function (opt) {
    var out = [HEAD, '<worksheet ' + NS + '>'];
    if (opt.fit) out.push('<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>');
    out.push('<sheetViews><sheetView ' + (opt.grid === false ? 'showGridLines="0" ' : '') + (opt.selected ? 'tabSelected="1" ' : '') + 'zoomScale="' + (opt.zoom || 100) + '" workbookViewId="0">');
    if (opt.pane) out.push('<pane xSplit="' + opt.pane[0] + '" ySplit="' + opt.pane[1] + '" topLeftCell="' + col(opt.pane[0]) + (opt.pane[1] + 1) + '" activePane="bottomRight" state="frozen"/><selection pane="topRight"/><selection pane="bottomLeft"/><selection pane="bottomRight"/>');
    out.push('</sheetView></sheetViews><sheetFormatPr defaultRowHeight="14.4"/>');
    if (opt.cols) out.push('<cols>' + opt.cols.map(function (c, i) { return '<col min="' + (i + 1) + '" max="' + (i + 1) + '" width="' + c[0] + '"' + (c[1] != null ? ' style="' + c[1] + '"' : '') + ' customWidth="1"/>'; }).join('') + '</cols>');
    out.push('<sheetData>');
    var self = this;
    Object.keys(this.rows).map(Number).sort(function (a, b) { return a - b; }).forEach(function (r) {
      var cells = self.rows[r], h = self.heights[r];
      out.push('<row r="' + r + '"' + (h ? ' ht="' + h + '" customHeight="1"' : '') + '>');
      Object.keys(cells).map(Number).sort(function (a, b) { return a - b; }).forEach(function (c) {
        var cl = cells[c], ref = col(c) + r, s = cl.s != null ? ' s="' + cl.s + '"' : '';
        if (cl.f) out.push('<c r="' + ref + '"' + s + (typeof cl.cv === 'string' ? ' t="str"' : '') + '><f>' + x(cl.f) + '</f>' + (cl.cv != null && cl.cv !== '' ? '<v>' + x(cl.cv) + '</v>' : '') + '</c>');
        else if (cl.d) out.push('<c r="' + ref + '"' + s + '><v>' + serial(cl.d) + '</v></c>');
        else if (typeof cl.v === 'number') out.push('<c r="' + ref + '"' + s + '><v>' + cl.v + '</v></c>');
        else if (cl.v != null && cl.v !== '') out.push('<c r="' + ref + '"' + s + ' t="inlineStr"><is><t xml:space="preserve">' + x(cl.v) + '</t></is></c>');
        else out.push('<c r="' + ref + '"' + s + '/>');
      });
      out.push('</row>');
    });
    out.push('</sheetData>');
    if (this.merges.length) out.push('<mergeCells count="' + this.merges.length + '">' + this.merges.map(function (m) { return '<mergeCell ref="' + m + '"/>'; }).join('') + '</mergeCells>');
    out.push('<pageMargins left="0.75" right="0.75" top="1" bottom="1" header="0.5" footer="0.5"/>');
    if (opt.fit) out.push('<pageSetup paperSize="9" orientation="landscape" fitToHeight="0"/>');
    out.push('</worksheet>');
    return out.join('');
  };

  function sheetName(name, used) {
    var s = String(name || 'Объект').replace(/[\[\]:*?\/\\]/g, ' ').trim().slice(0, 31) || 'Объект', base = s, i = 2;
    while (used[s.toLowerCase()]) s = base.slice(0, 28) + ' ' + (i++);
    used[s.toLowerCase()] = 1;
    return s;
  }
  function ref(name) { return /^[A-Za-z0-9_]+$/.test(name) ? name : "'" + name.replace(/'/g, "''") + "'"; }
  function num(v) { v = n(v); return v ? v : null; }
  function dt(v) { return v ? {d: v} : null; }

  var OBJ_COLS = [[6, 23], [36, 23], [17, 23], [14, 23], [17, 23], [14, 23], [17, 23], [38, 23]];

  /* Лист объекта: «DARYN — ДЕТАЛИЗАЦИЯ ПЛАН / ФАКТ» */
  function objectSheet(name, o, F) {
    var sh = new Sheet(name), at = {}, r = 5;
    sh.row(1, [63, 64, 64, 64, 64, 64, 64, 55], [o.name.toUpperCase() + ' — ДЕТАЛИЗАЦИЯ ПЛАН / ФАКТ'], 28.05);
    sh.row(2, [60, 51, 51, 51, 51, 51, 51, 51], ['Период: до 31.12.2026']);
    sh.row(4, [33, 1, 27, 27, 27, 27, 27, 8], ['№', 'Наименование / получатель', 'План', 'Плановая дата', 'Факт', 'Дата факта', 'Остаток', 'Статус / примечание'], 27.6);
    sh.merges.push('A1:H1', 'A2:H2');
    ['income', 'labor', 'material', 'overhead'].forEach(function (s) {
      var ls = F.lines(o.id, s), first = r + 1, slots = Math.max(ls.length, 6), last = r + slots, inc = s === 'income';
      var sp = F.sec(o.id, s);
      sh.row(r, inc ? [66, 55, 9, 25, 9, 25, 9, 25] : [65, 55, 15, 24, 15, 24, 15, 24],
        [SEC_NAMES[s], null, {f: 'SUM(C' + first + ':C' + last + ')', cv: sp.plan}, null, {f: 'SUM(E' + first + ':E' + last + ')', cv: sp.fact}, null, {f: 'C' + r + '-E' + r, cv: sp.plan - sp.fact}, null]);
      sh.merges.push('A' + r + ':B' + r);
      at[s] = r;
      var run = 0;
      for (var i = 0; i < slots; i++) {
        var rr = first + i, l = ls[i] || null, p = l ? n(l.plan) : 0, f = l ? n(l.fact) : 0, g;
        run += p - f;
        if (inc) g = i === 0 ? null : {f: 'IF(AND(C' + rr + '="",E' + rr + '=""),"",SUM(C$' + first + ':C' + rr + ')-SUM(E$' + first + ':E' + rr + '))', cv: (p || f) ? run : ''};
        else g = {f: 'C' + rr + '-E' + rr, cv: p - f};
        sh.row(rr, inc ? [10, 11, 4, 12, 5, 13, 6, 14] : [10, 11, 6, 12, 7, 16, 6, 14],
          [i + 1, l ? l.name || null : null, l ? num(l.plan) : null, l ? dt(l.pdate) : null, l ? num(l.fact) : null, l ? dt(l.fdate) : null, g, l ? l.note || null : null]);
      }
      r = last + 2;
    });
    var c = F.calc(o.id);
    sh.row(r, [67, 55, 17, 26, 17, 26, 17, 26], ['ИТОГО РАСХОДЫ', null,
      {f: 'C' + at.labor + '+C' + at.material + '+C' + at.overhead, cv: c.exp.plan}, null,
      {f: 'E' + at.labor + '+E' + at.material + '+E' + at.overhead, cv: c.exp.fact}, null,
      {f: 'G' + at.labor + '+G' + at.material + '+G' + at.overhead, cv: c.exp.plan - c.exp.fact}, null]);
    sh.merges.push('A' + r + ':B' + r);
    at.exp = r;
    sh.row(r + 1, [66, 55, 9, 25, 9, 25, 25, 25], ['ОСТАТОК: ПОСТУПЛЕНИЯ − РАСХОДЫ', null,
      {f: 'C' + at.income + '-C' + r, cv: c.bal.plan}, null, {f: 'E' + at.income + '-E' + r, cv: c.bal.fact}, null, null, null], 27.6);
    sh.merges.push('A' + (r + 1) + ':B' + (r + 1));
    return {sheet: sh, at: at, xml: function () { return sh.xml({grid: false, zoom: 74, pane: [2, 4], cols: OBJ_COLS}); }};
  }

  /* «Долги»: реестр кредиторов */
  function debtSheet(F) {
    var sh = new Sheet('Долги'), ls = F.lines(null, 'debt'), slots = Math.max(ls.length, 6), last = 5 + slots, d = F.sec(null, 'debt');
    sh.row(1, [74, 74, 74, 74, 74, 74, 74, 74], ['ОБЩИЙ ДОЛГ КОМПАНИИ — РЕЕСТР'], 28.05);
    sh.row(2, [73, 73, 73, 73, 73, 73, 73, 73], ['Долги не распределяются по объектам | Факт — сколько уже оплатили; остаток считается автоматически']);
    sh.row(4, [33, 1, 33, 33, 33, 33, 33, 1], ['№', 'Кому должны', 'Сумма долга', 'Срок оплаты', 'Факт оплаты', 'Дата оплаты', 'Остаток долга', 'Статус / примечание'], 27.6);
    sh.row(5, [65, 55, 15, 24, 15, 24, 15, 24], ['Кредиторы', null, {f: 'SUM(C6:C' + last + ')', cv: d.plan}, null, {f: 'SUM(E6:E' + last + ')', cv: d.fact}, null, {f: 'SUM(G6:G' + last + ')', cv: d.plan - d.fact}, null]);
    sh.merges.push('A1:H1', 'A2:H2', 'A5:B5');
    for (var i = 0; i < slots; i++) {
      var rr = 6 + i, l = ls[i] || null;
      sh.row(rr, [10, 11, 6, 12, 7, 16, 6, 14], [i + 1, l ? l.name || null : null, l ? num(l.plan) : null, l ? dt(l.pdate) : null,
        l ? num(l.fact) : null, l ? dt(l.fdate) : null, {f: 'C' + rr + '-E' + rr, cv: l ? n(l.plan) - n(l.fact) : 0}, l ? l.note || null : null]);
    }
    var t = last + 1;
    sh.row(t, [67, 55, 17, 26, 17, 26, 17, 26], ['ИТОГО ДОЛГ', null, {f: 'C5', cv: d.plan}, null, {f: 'E5', cv: d.fact}, null, {f: 'G5', cv: d.plan - d.fact}, null]);
    sh.merges.push('A' + t + ':B' + t);
    return {sheet: sh, xml: function () { return sh.xml({grid: false, zoom: 74, pane: [2, 4], cols: OBJ_COLS}); }};
  }

  /* «Лист1»: АВР — сумма | объект и вид работ */
  function actsSheet(S) {
    var sh = new Sheet('Лист1'), r = 2;
    sh.set(1, 0, {s: 87, v: 'АВР'});
    S.acts.slice().sort(function (a, b) { return (a.pos - b.pos) || (a.id - b.id); }).forEach(function (a) {
      var o = S.objects.filter(function (x) { return x.id === a.object; })[0];
      var label = o ? (ACT_NAME[o.name] || o.name) + ' ' + (a.work || '') : (a.work || '');
      sh.set(r, 0, {s: 87, v: n(a.amount)}); sh.set(r, 1, {v: label.trim()});
      if (a.date) sh.set(r, 2, {s: 16, d: a.date});
      if (a.note) sh.set(r, 3, {v: a.note});
      r++;
    });
    return {sheet: sh, xml: function () { return sh.xml({cols: [[13.78, 87], [28], [12], [30]]}); }};
  }

  /* «Сводная таблица» */
  var HEAD_COLORS = [61, 54, 57, 56, 58, 59];
  function summarySheet(objs, F) {
    var sh = new Sheet('Сводная таблица'), N = objs.length, tc = 1 + N * 2, last = tc + 1;
    sh.row(1, [50], [' ТОО "PARAMOUNT BUILDINGS" — СВОДНЫЙ ФИНАНСОВЫЙ']);
    sh.row(2, [60], ['Период: до 31.12.2026 ']);
    sh.merges.push('A1:' + col(Math.max(last - 2, 0)) + '1', 'A2:' + col(Math.max(last - 2, 0)) + '2', 'A4:A5');
    sh.set(4, 0, {s: 52, v: 'Статья'}); sh.set(5, 0, {s: 53});
    objs.forEach(function (o, i) {
      var c = 1 + i * 2;
      sh.set(4, c, {s: HEAD_COLORS[i % 6], v: o.o.name}); sh.set(4, c + 1, {s: 55});
      sh.set(5, c, {s: 37, v: 'План'}); sh.set(5, c + 1, {s: 37, v: 'Факт'});
      sh.merges.push(col(c) + '4:' + col(c + 1) + '4');
    });
    sh.set(4, tc, {s: 62, v: 'ВСЕ ОБЪЕКТЫ'}); sh.set(4, tc + 1, {s: 55});
    sh.set(5, tc, {s: 37, v: 'План'}); sh.set(5, tc + 1, {s: 37, v: 'Факт'});
    sh.merges.push(col(tc) + '4:' + col(tc + 1) + '4');
    function sumAcross(r, off) { return objs.map(function (o, i) { return col(1 + i * 2 + off) + r; }).join('+') || '0'; }
    var T = F.total(), keys = [['income', 6, 'Поступления'], ['labor', 7, 'Оплата работ'], ['material', 8, 'Материальные расходы'], ['overhead', 9, 'Накладные расходы']];
    keys.forEach(function (k) {
      var key = k[0], r = k[1], inc = key === 'income';
      sh.set(r, 0, {s: inc ? 38 : 40, v: k[2]});
      objs.forEach(function (o, i) {
        var c = 1 + i * 2, row = o.at[key], cc = F.calc(o.o.id)[key];
        sh.set(r, c, {s: inc ? 4 : 41, f: ref(o.name) + '!C' + row, cv: cc.plan});
        sh.set(r, c + 1, {s: inc ? 5 : 42, f: ref(o.name) + '!E' + row, cv: cc.fact});
      });
      sh.set(r, tc, {s: inc ? 3 : 43, f: sumAcross(r, 0), cv: T[key].plan});
      sh.set(r, tc + 1, {s: 39, f: sumAcross(r, 1), cv: T[key].fact});
    });
    sh.set(10, 0, {s: 35, v: 'ОБЩИЙ ДОЛГ КОМПАНИИ'});
    for (var c = 1; c < tc; c++) sh.set(10, c, {s: 44});
    sh.set(10, tc, {s: 36, f: 'Долги!C5', cv: T.debt.plan}); sh.set(10, tc + 1, {s: 47, f: 'Долги!E5', cv: T.debt.fact});
    sh.set(11, 0, {s: 34, v: 'ИТОГО РАСХОДЫ'});
    sh.set(12, 0, {s: 38, v: 'ИТОГ ОСТАТОК'}); sh.heights[12] = 27.6;
    objs.forEach(function (o, i) {
      var cc = F.calc(o.o.id);
      [0, 1].forEach(function (off) {
        var L = col(1 + i * 2 + off), pf = off ? 'fact' : 'plan';
        sh.set(11, 1 + i * 2 + off, {s: 45, f: 'SUM(' + L + '7:' + L + '10)', cv: cc.exp[pf]});
        sh.set(12, 1 + i * 2 + off, {s: 46, f: L + '6-' + L + '11', cv: cc.bal[pf]});
      });
    });
    [0, 1].forEach(function (off) {
      var L = col(tc + off), pf = off ? 'fact' : 'plan';
      sh.set(11, tc + off, {s: 45, f: sumAcross(11, off) + '+' + L + '10', cv: T.expAll[pf]});
      sh.set(12, tc + off, {s: 46, f: L + '6-' + L + '11', cv: T.bal[pf]});
    });
    var cols = [[34, 23]]; for (var k = 1; k <= last; k++) cols.push([16, 23]);
    return {sheet: sh, xml: function () { return sh.xml({grid: false, zoom: 74, pane: [1, 5], cols: cols, fit: true, selected: true}); }};
  }

  function build(S) {
    var F = window.PBFin, used = {'сводная таблица': 1, 'долги': 1, 'лист1': 1};
    var objs = S.objects.map(function (o) { var name = sheetName(o.name, used), s = objectSheet(name, o, F); return {o: o, name: name, at: s.at, sheet: s}; });
    var summary = summarySheet(objs, F);
    var list = [{name: 'Сводная таблица', xml: summary.xml()}];
    objs.forEach(function (o, i) {
      list.push({name: o.name, xml: o.sheet.xml()});
      if (i === 0) list.push({name: 'Лист1', xml: actsSheet(S).xml()});
    });
    if (!objs.length) list.push({name: 'Лист1', xml: actsSheet(S).xml()});
    list.push({name: 'Долги', xml: debtSheet(F).xml()});

    var zip = new JSZip();
    zip.file('[Content_Types].xml', HEAD + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>' +
      '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' +
      list.map(function (s, i) { return '<Override PartName="/xl/worksheets/sheet' + (i + 1) + '.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'; }).join('') +
      '<Override PartName="/xl/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' +
      '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>');
    zip.file('_rels/.rels', HEAD + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>');
    var now = new Date().toISOString().replace(/\.\d+Z$/, 'Z');
    zip.file('docProps/core.xml', HEAD + '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>Paramount Фин план до 2026 года</dc:title><dc:creator>Paramount Buildings</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">' + now + '</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">' + now + '</dcterms:modified></cp:coreProperties>');
    zip.file('docProps/app.xml', HEAD + '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Microsoft Excel</Application></Properties>');
    zip.file('xl/workbook.xml', HEAD + '<workbook ' + NS + '><workbookPr/><bookViews><workbookView xWindow="0" yWindow="0" windowWidth="23256" windowHeight="12576"/></bookViews><sheets>' +
      list.map(function (s, i) { return '<sheet name="' + x(s.name) + '" sheetId="' + (i + 1) + '" r:id="rId' + (i + 1) + '"/>'; }).join('') + '</sheets><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>');
    zip.file('xl/_rels/workbook.xml.rels', HEAD + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
      list.map(function (s, i) { return '<Relationship Id="rId' + (i + 1) + '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet' + (i + 1) + '.xml"/>'; }).join('') +
      '<Relationship Id="rId' + (list.length + 1) + '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/><Relationship Id="rId' + (list.length + 2) + '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>');
    zip.file('xl/styles.xml', window.PB_XLSX_BASE.styles);
    zip.file('xl/theme/theme1.xml', window.PB_XLSX_BASE.theme);
    list.forEach(function (s, i) { zip.file('xl/worksheets/sheet' + (i + 1) + '.xml', s.xml); });
    return zip;
  }

  window.PBFinXlsx = {
    build: build,
    download: function (S) {
      return build(S).generateAsync({type: 'blob', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', compression: 'DEFLATE'}).then(function (blob) {
        var a = document.createElement('a'), d = new Date();
        a.href = URL.createObjectURL(blob);
        a.download = 'Paramount Фин план до 2026 года (' + ('0' + d.getDate()).slice(-2) + '.' + ('0' + (d.getMonth() + 1)).slice(-2) + '.' + d.getFullYear() + ').xlsx';
        document.body.appendChild(a); a.click();
        setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
      });
    }
  };
})();
