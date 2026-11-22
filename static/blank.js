/* Документ на фирменном бланке в браузере: предпросмотр, PDF и DOCX из того, что ввёл человек.
   Раскладка страницы повторяет docflow/pdf.py (A4 = 1240 × 1754 точек при 150 dpi), DOCX — docflow/blank_docx.py:
   берём файл утверждённого бланка (шапка, логотип, водяной знак) и подставляем в тело номер, дату и текст.
   Весь текст документа — Arial 12 pt. Работает и в статической демо-версии, без сервера. */
(function () {
  var W = 1240, H = 1754, M = 88, PT = 25, HEAD = 16, LH = 38;
  var INK = 'rgb(40,48,66)', SEAL = 'rgb(36,74,170)', LINE = 'rgb(47,74,110)', GRAY = 'rgb(110,120,140)';
  var FONT = 'Arial, "Liberation Sans", Helvetica, sans-serif';
  var MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
  var DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';

  function font(size, bold) { return (bold ? 'bold ' : '') + size + 'px ' + FONT; }

  function data() {
    var el = document.getElementById('pbBlankData');
    try { return el ? JSON.parse(el.textContent) : {}; } catch (e) { return {}; }
  }

  /* ---------- Текст ---------- */
  function dateWords(dt) {
    var p = String(dt || '').split('.');
    if (p.length !== 3 || !MONTHS[+p[1] - 1]) return dt || '';
    return '«' + p[0] + '» ' + MONTHS[+p[1] - 1] + ' ' + p[2] + ' г.';
  }
  function shortName(full) { // Балтаев Нурбек Шарипжанулы -> Балтаев Н. Ш.
    var p = String(full || '').trim().split(/\s+/).filter(Boolean);
    if (!p.length) return '';
    return p[0] + (p.length > 1 ? ' ' + p.slice(1, 3).map(function (x) { return x[0] + '.'; }).join(' ') : '');
  }
  function orderText(summary) { // как order_text() на сервере: основание и пункты «1. …»
    var basis = [], points = [];
    String(summary || '').split('\n').forEach(function (line) {
      line = line.trim();
      if (!line || ['ПРИКАЗЫВАЮ', 'БҰЙЫРАМЫН'].indexOf(line.replace(/:+$/, '').toUpperCase()) >= 0) return;
      var m = line.match(/^\d+[.)]\s*(.+)$/);
      if (m) points.push(m[1]); else if (points.length) points.push(line); else basis.push(line);
    });
    if (!points.length) { points = basis; basis = []; }
    return {basis: basis.join(' '), points: points};
  }
  function wrap(ctx, text, fnt, width) {
    ctx.font = fnt;
    var rows = [];
    String(text).split('\n').forEach(function (para) {
      var line = '';
      para.split(/\s+/).filter(Boolean).forEach(function (word) {
        var test = (line + ' ' + word).trim();
        if (ctx.measureText(test).width <= width) line = test;
        else { if (line) rows.push(line); line = word; }
      });
      rows.push(line);
    });
    return rows;
  }

  /* ---------- Картинки бланка ---------- */
  var cache = {};
  function img(id) {
    var el = document.getElementById(id);
    if (!el) return Promise.resolve(null);
    if (!cache[id]) cache[id] = new Promise(function (ok) {
      if (el.complete && el.naturalWidth) return ok(el);
      el.addEventListener('load', function () { ok(el); });
      el.addEventListener('error', function () { ok(null); });
    });
    return cache[id];
  }
  function fontsReady() { return document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve(); }

  /* ---------- Рисование страницы ---------- */
  function text(ctx, t, x, y, size, bold, align, color) {
    ctx.font = font(size, bold); ctx.fillStyle = color || INK; ctx.textAlign = align || 'left';
    ctx.fillText(t, x, y);
  }
  function letterhead(ctx, d, logo, mark) {
    if (mark) { var w = 1750; ctx.drawImage(mark, -128, 475, w, w * mark.naturalHeight / mark.naturalWidth); }
    if (logo) ctx.drawImage(logo, M - 8, 70, 590, 590 * logo.naturalHeight / logo.naturalWidth);
    (d.header || []).forEach(function (col) {
      var y = 240;
      col[1].forEach(function (t, i) { text(ctx, t, col[0], y, HEAD, i === 0 && col[0] !== 552, 'left', 'rgb(20,24,36)'); y += 25; });
    });
    ctx.strokeStyle = LINE; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(M, 366); ctx.lineTo(W - 40, 366); ctx.stroke();
    return 410;
  }
  function numberLine(ctx, x, y, number, dt) {
    text(ctx, '№ ' + (number || '___________________'), x, y, PT);
    text(ctx, dt ? dateWords(dt) : '«___» ___________ 20__ г.', x, y + LH, PT);
  }
  function body(ctx, y, paras, maxY) {
    for (var k = 0; k < paras.length; k++) {
      var para = paras[k]; if (!para) continue;
      var bold = para.indexOf('**') === 0, t = para.replace(/^\*+|\*+$/g, '');
      var rows = wrap(ctx, t, font(PT, bold), W - 2 * M);
      for (var i = 0; i < rows.length; i++) {
        if (y > maxY) { text(ctx, '…', M, y, PT); return y + 36; }
        text(ctx, rows[i], M + (i === 0 && !bold ? 40 : 0), y, PT, bold);
        y += Math.floor(PT * 1.5);
      }
      y += 16;
    }
    return y;
  }
  function signature(ctx, x, y) {
    ctx.strokeStyle = SEAL; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.lineWidth = 4; ctx.beginPath();
    for (var i = 0; i < 60; i++) {
      var t = i / 59, px = x + t * 210, py = y + 22 * Math.sin(t * 9) * (1 - t * .6) - t * 18;
      if (i) ctx.lineTo(px, py); else ctx.moveTo(px, py);
    }
    ctx.stroke(); ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(x + 40, y + 26); ctx.lineTo(x + 230, y - 8); ctx.stroke();
  }
  function seal(ctx, cx, cy, d) {
    var r = 118, col = 'rgba(36,74,170,.8)';
    ctx.save(); ctx.translate(cx, cy); ctx.rotate(12 * Math.PI / 180);
    ctx.strokeStyle = col; ctx.fillStyle = col;
    [[r, 6], [r - 16, 2], [52, 2]].forEach(function (c) { ctx.lineWidth = c[1]; ctx.beginPath(); ctx.arc(0, 0, c[0], 0, 2 * Math.PI); ctx.stroke(); });
    var s = String(d.company || '').toUpperCase() + ' · БИН ' + (d.bin || '') + ' · АСТАНА · ';
    ctx.font = font(17, true); ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    for (var i = 0; i < s.length; i++) {
      var a = 2 * Math.PI * i / s.length - Math.PI / 2;
      ctx.save(); ctx.translate((r - 32) * Math.cos(a), (r - 32) * Math.sin(a)); ctx.rotate(a + Math.PI / 2); ctx.fillText(s[i], 0, 0); ctx.restore();
    }
    ctx.font = font(18, true); ctx.fillText('PARAMOUNT', 0, -12); ctx.fillText('BUILDINGS', 0, 12);
    ctx.restore(); ctx.textBaseline = 'top';
  }
  function note(ctx, on) { if (on) text(ctx, 'Изображение подписи и печати не является ЭЦП', W - M, H - 66, PT, false, 'right', GRAY); }

  function drawLetter(ctx, d, doc) {
    var y = letterhead(ctx, d, doc._logo, doc._mark), ay = y;
    numberLine(ctx, M, y, doc.number, doc.date);
    wrap(ctx, doc.addressee || '', font(PT, true), 470).forEach(function (row) { text(ctx, row, W - M - 470, ay, PT, true); ay += LH; });
    y = Math.max(y + 120, ay + 30);
    wrap(ctx, doc.subject || '', font(PT, true), W - 2 * M).forEach(function (row) { text(ctx, row, M, y, PT, true); y += LH; });
    y = body(ctx, y + 22, doc.paragraphs || [], H - 470);
    var att = doc.attachments || [];
    if (att.length) {
      y += 6; text(ctx, 'Приложения:', M, y, PT, true); y += LH;
      att.forEach(function (a, i) { wrap(ctx, (i + 1) + '. ' + a, font(PT), W - 2 * M - 20).forEach(function (row) { text(ctx, row, M + 20, y, PT); y += LH; }); });
    }
    y = Math.max(y + 50, H - 450);
    text(ctx, doc.signerPos || '', M, y, PT, true);
    text(ctx, doc.signerName || '', W - M, y, PT, true, 'right');
    if (doc.seal) seal(ctx, M + 330, y + 10, d);
    if (doc.sign) signature(ctx, W - M - 560, y + 6);
    if (doc.executor) text(ctx, 'Исп: ' + doc.executor, M, H - 150, PT);
    if (doc.executorPhone) text(ctx, 'Тел: ' + doc.executorPhone.replace(/[\s-]/g, ''), M, H - 112, PT);
    note(ctx, doc.sign || doc.seal);
  }
  function drawOrder(ctx, d, doc) {
    var y = letterhead(ctx, d, doc._logo, doc._mark) + 30;
    text(ctx, 'БҰЙРЫҚ', M, y, PT, true); text(ctx, 'ПРИКАЗ', W - M, y, PT, true, 'right');
    numberLine(ctx, M, y + 58, doc.number, doc.date);
    y += 170;
    wrap(ctx, doc.title || '', font(PT, true), 760).forEach(function (row) { text(ctx, row, M + 60, y, PT, true); y += LH; });
    var paras = (doc.basis ? [doc.basis] : []).concat(['**ПРИКАЗЫВАЮ:'], (doc.points || []).map(function (p, i) { return (i + 1) + '. ' + p; }));
    y = body(ctx, y + 24, paras, H - 470);
    y = Math.max(y + 60, H - 430);
    text(ctx, doc.signerPos || '', M + 60, y, PT, true);
    text(ctx, doc.signerName || '', W - M, y, PT, true, 'right');
    if (doc.sign) signature(ctx, W - M - 560, y + 6);
    if (doc.seal) seal(ctx, M + 330, y + 10, d);
    note(ctx, doc.sign || doc.seal);
  }

  function draw(canvas, doc, scale) {
    var d = data();
    scale = scale || 1;
    return Promise.all([img('pbLogo'), img('pbMark'), fontsReady()]).then(function (r) {
      canvas.width = W * scale; canvas.height = H * scale;
      var ctx = canvas.getContext('2d');
      ctx.setTransform(scale, 0, 0, scale, 0, 0);
      ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, W, H); ctx.textBaseline = 'top';
      doc._logo = r[0]; doc._mark = r[1];
      (doc.kind === 'order' ? drawOrder : drawLetter)(ctx, d, doc);
      return canvas;
    });
  }

  /* ---------- PDF: страница A4 с картинкой листа ---------- */
  function pdfBlob(doc) {
    return draw(document.createElement('canvas'), doc, 2).then(function (c) {
      var bin = atob(c.toDataURL('image/jpeg', 0.9).split(',')[1]), jpg = new Uint8Array(bin.length);
      for (var i = 0; i < bin.length; i++) jpg[i] = bin.charCodeAt(i);
      var enc = function (s) { var u = new Uint8Array(s.length); for (var i = 0; i < s.length; i++) u[i] = s.charCodeAt(i) & 255; return u; };
      var stream = 'q 595.28 0 0 841.89 0 0 cm /Im0 Do Q';
      var objs = [
        '<< /Type /Catalog /Pages 2 0 R >>',
        '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.28 841.89] /Resources << /XObject << /Im0 5 0 R >> >> /Contents 4 0 R >>',
        '<< /Length ' + stream.length + ' >>\nstream\n' + stream + '\nendstream',
        null
      ];
      var parts = [enc('%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')], offs = [], pos = parts[0].length;
      objs.forEach(function (o, k) {
        offs.push(pos);
        var chunk = o === null
          ? [enc('5 0 obj\n<< /Type /XObject /Subtype /Image /Width ' + c.width + ' /Height ' + c.height + ' /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ' + jpg.length + ' >>\nstream\n'), jpg, enc('\nendstream\nendobj\n')]
          : [enc((k + 1) + ' 0 obj\n' + o + '\nendobj\n')];
        chunk.forEach(function (p) { parts.push(p); pos += p.length; });
      });
      var xref = 'xref\n0 6\n0000000000 65535 f \n' + offs.map(function (o) { return ('000000000' + o).slice(-10) + ' 00000 n \n'; }).join('');
      parts.push(enc(xref + 'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n' + pos + '\n%%EOF\n'));
      return new Blob(parts, {type: 'application/pdf'});
    });
  }

  /* ---------- DOCX: тот же бланк, тело документа заменяем (как blank_docx.py) ---------- */
  var TOKEN = /<w:p(?:\s[^>]*)?\/>|<w:p[\s>]|<\/w:p>/g;
  function xesc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
  function topParagraphs(b) {
    var out = [], depth = 0, start = 0, m; TOKEN.lastIndex = 0;
    while ((m = TOKEN.exec(b))) {
      var t = m[0];
      if (/\/>$/.test(t)) { if (!depth) out.push(t); }
      else if (t.indexOf('</') === 0) { depth--; if (!depth) out.push(b.slice(start, m.index + t.length)); }
      else { if (!depth) start = m.index; depth++; }
    }
    return out;
  }
  function run(t, bold) {
    var rpr = '<w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>' + (bold ? '<w:b/><w:bCs/>' : '') + '<w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>';
    return String(t).split('\t').map(function (chunk, i) {
      return (i ? '<w:r>' + rpr + '<w:tab/></w:r>' : '') + (chunk ? '<w:r>' + rpr + '<w:t xml:space="preserve">' + xesc(chunk) + '</w:t></w:r>' : '');
    }).join('');
  }
  function p(lines, o) {
    o = o || {}; lines = lines === undefined ? [''] : (typeof lines === 'string' ? [lines] : lines);
    var ppr = '<w:pPr>' + (o.tab ? '<w:tabs><w:tab w:val="right" w:pos="9155"/></w:tabs>' : '') +
      '<w:spacing w:after="' + (o.after || 0) + '" w:line="276" w:lineRule="auto"/>' +
      '<w:ind w:left="' + (o.left === undefined ? -851 : o.left) + '"' + (o.first ? ' w:firstLine="' + o.first + '"' : '') + '/>' +
      (o.jc ? '<w:jc w:val="' + o.jc + '"/>' : '') + '</w:pPr>';
    return '<w:p>' + ppr + lines.map(function (l, i) { return (i ? '<w:r><w:br/></w:r>' : '') + run(l, o.bold); }).join('') + '</w:p>';
  }
  function numberDate(doc) { return p(['№ ' + (doc.number || '___________________'), doc.date ? dateWords(doc.date) : '«___» ___________ 20__ г.']); }
  function executorBox(xml, ex, ph) {
    xml = xml.replace(/(<w:t(?:\s[^>]*)?>)([^<]*)(<\/w:t>)/g, function (all, a, t, b) {
      if (/^\s*\d{4,}\s*$/.test(t)) t = '';
      else if (t.indexOf('Исп:') === 0) t = ex ? 'Исп: ' + ex : 'Исп:';
      else if (t.indexOf('Тел:') === 0) t = ph ? 'Тел: ' + ph : 'Тел:';
      return a + xesc(t) + b;
    });
    return xml.indexOf('Исп:') >= 0 ? xml.replace(/(<w:sz(?:Cs)? w:val=")\d+(")/g, '$124$2') : xml;
  }
  function letterBody(paras, doc) {
    var keep = paras.filter(function (x) { return /<w:drawing|<w:pict|<mc:AlternateContent/.test(x); })
      .map(function (x) { return executorBox(x, doc.executor, (doc.executorPhone || '').replace(/[\s-]/g, '')); });
    var out = [numberDate(doc)].concat(keep, [p(), p(String(doc.addressee || '').split('\n'), {bold: true, left: 4600}), p(), p(doc.subject || '', {bold: true, after: 120})]);
    (doc.paragraphs || []).forEach(function (t) { if (t.trim()) out.push(p(t, {jc: 'both', first: 709, after: 60})); });
    if ((doc.attachments || []).length) {
      out.push(p(), p('Приложения:', {bold: true}));
      doc.attachments.forEach(function (a, i) { out.push(p((i + 1) + '. ' + a)); });
    }
    out.push(p(), p(), p((doc.signerPos || '') + '\t' + (doc.signerName || ''), {bold: true, tab: true}));
    return out.join('');
  }
  function orderBody(paras, doc) {
    var out = [p(), p('БҰЙРЫҚ\tПРИКАЗ', {bold: true, tab: true}), numberDate(doc), p(), p(String(doc.title || '').split('\n'), {bold: true, left: -142}), p()];
    if (doc.basis) out.push(p(doc.basis, {jc: 'both', first: 709}));
    out.push(p('ПРИКАЗЫВАЮ:', {bold: true, first: 709}));
    (doc.points || []).forEach(function (t, i) { out.push(p((i + 1) + '. ' + t, {jc: 'both', first: 709})); });
    out.push(p(), p(), p((doc.signerPos || '') + '\t' + (doc.signerName || ''), {bold: true, left: -142, tab: true}));
    return out.join('');
  }
  function docxBlob(doc, url) {
    if (!url) return Promise.reject(new Error('Нет файла бланка (DOCX)'));
    if (!window.JSZip) return Promise.reject(new Error('Не загрузилась библиотека DOCX'));
    var zip;
    return fetch(url).then(function (r) { if (!r.ok) throw new Error('Бланк не найден'); return r.arrayBuffer(); })
      .then(function (buf) { return window.JSZip.loadAsync(buf); })
      .then(function (z) { zip = z; return z.file('word/document.xml').async('string'); })
      .then(function (xml) {
        var b0 = xml.indexOf('<w:body>') + 8, sect = xml.lastIndexOf('<w:sectPr');
        var paras = topParagraphs(xml.slice(b0, sect));
        xml = xml.slice(0, b0) + (doc.kind === 'order' ? orderBody : letterBody)(paras, doc) + xml.slice(sect);
        zip.file('word/document.xml', xml);
        return zip.generateAsync({type: 'blob', compression: 'DEFLATE', mimeType: DOCX_MIME});
      });
  }

  window.PBBlank = {draw: draw, pdfBlob: pdfBlob, docxBlob: docxBlob, data: data, shortName: shortName,
                    orderText: orderText, dateWords: dateWords};

  /* ---------- Новый приказ: предпросмотр и скачивание того приказа, что заполнен в форме ---------- */
  var form = document.querySelector('form[data-blank="order"]');
  if (!form) return;
  var box = document.getElementById('pbOrder'), canvas = document.getElementById('pbOrderCanvas');
  var urls = [];
  function field(n) { var el = form.elements[n]; return el ? el.value : ''; }
  function orderDoc() {
    var d = data(), t = orderText(field('summary')), s = d.signers && d.signers[field('signer')] || d.director || ['Директор', ''];
    var iso = field('doc_date'), dt = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? iso.split('-').reverse().join('.') : iso;
    return {kind: 'order', number: '', date: dt, title: field('title').trim(), basis: t.basis, points: t.points,
            signerPos: s[0], signerName: s[1]};
  }
  function link(id, blob, name) {
    var a = document.getElementById(id); if (!a) return;
    var u = URL.createObjectURL(blob); urls.push(u);
    a.href = u; if (name) a.setAttribute('download', name);
  }
  function show() {
    var doc = orderDoc(), err = document.getElementById('pbOrderErr');
    if (!doc.title) { err.hidden = false; err.textContent = 'Заполните «Название / тема» — оно попадёт в приказ.'; box.hidden = false; box.scrollIntoView({behavior: 'smooth'}); return; }
    err.hidden = true; box.hidden = false;
    ['pbOrderPdf', 'pbOrderDocx', 'pbOrderPrint'].forEach(function (id) { var a = document.getElementById(id); a.removeAttribute('href'); a.hidden = false; });
    urls.forEach(function (u) { URL.revokeObjectURL(u); }); urls = [];
    var name = ('Приказ — ' + doc.title.slice(0, 60)).replace(/[\\/:*?"<>|]+/g, ' ');
    draw(canvas, doc, 1).then(function () { box.scrollIntoView({behavior: 'smooth', block: 'start'}); });
    pdfBlob(doc).then(function (b) { link('pbOrderPdf', b, name + '.pdf'); link('pbOrderPrint', b); });
    docxBlob(doc, (document.getElementById('pbAssets') || {getAttribute: function () { return ''; }}).getAttribute('data-docx-src')).then(function (b) { link('pbOrderDocx', b, name + '.docx'); })
      .catch(function (e) { var a = document.getElementById('pbOrderDocx'); if (a) a.hidden = true; });
  }
  var pv = document.getElementById('pbOrderPreview');
  if (pv) pv.addEventListener('click', show);
  form.addEventListener('submit', function (e) {
    if (!form.hasAttribute('data-demo')) return; // на сервере приказ сохраняется и собирается там же
    e.preventDefault(); show();
  });
})();
