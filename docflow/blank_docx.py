"""DOCX на фирменном бланке: берём файл бланка (шапка, логотип, водяной знак, колонтитулы остаются как есть)
и подставляем в тело номер, дату, адресата, текст и подпись.

Работаем с word/document.xml как с текстом, чтобы не потерять разметку Word (mc:Ignorable, w14 и т. п.).
"""
import io
import re
import zipfile
from xml.sax.saxutils import escape

from .pdf import date_words

TOKEN = re.compile(r"<w:p(?:\s[^>]*)?/>|<w:p[\s>]|</w:p>")
TEXT_W = 9355 + 851  # ширина строки с учётом отрицательного отступа бланка (twips)


def _top_paragraphs(body):
    """Абзацы верхнего уровня тела документа: [(start, end, xml)]. Вложенные (в надписях) не делим."""
    out, depth, start = [], 0, 0
    for m in TOKEN.finditer(body):
        tok = m.group(0)
        if tok.endswith("/>"):
            if depth == 0:
                out.append((m.start(), m.end(), tok))
        elif tok.startswith("</"):
            depth -= 1
            if depth == 0:
                out.append((start, m.end(), body[start:m.end()]))
        else:
            if depth == 0:
                start = m.start()
            depth += 1
    return out


def _text(xml):
    return "".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", xml))


def _run(text, bold=False, size=24):
    rpr = (f'<w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>{"<w:b/><w:bCs/>" if bold else ""}'
           f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/></w:rPr>')
    parts = []
    for i, chunk in enumerate(text.split("\t")):
        if i:
            parts.append(f"<w:r>{rpr}<w:tab/></w:r>")
        if chunk:
            parts.append(f'<w:r>{rpr}<w:t xml:space="preserve">{escape(chunk)}</w:t></w:r>')
    return "".join(parts)


def _p(lines=("",), bold=False, size=24, jc=None, left=-851, first=None, tab_right=False, after=0):
    lines = [lines] if isinstance(lines, str) else list(lines)
    ppr = "<w:pPr>"
    if tab_right:
        ppr += f'<w:tabs><w:tab w:val="right" w:pos="{9355 - 200}"/></w:tabs>'
    ppr += f'<w:spacing w:after="{after}" w:line="276" w:lineRule="auto"/>'
    ppr += f'<w:ind w:left="{left}"' + (f' w:firstLine="{first}"' if first else "") + "/>"
    if jc:
        ppr += f'<w:jc w:val="{jc}"/>'
    ppr += "</w:pPr>"
    runs = []
    for i, line in enumerate(lines):
        if i:
            runs.append("<w:r><w:br/></w:r>")
        runs.append(_run(line, bold, size))
    return f"<w:p>{ppr}{''.join(runs)}</w:p>"


def _rebuild(blank_bytes, build):
    """Пересобрать DOCX: build(paragraphs) -> новое тело (без sectPr)."""
    src = zipfile.ZipFile(io.BytesIO(blank_bytes))
    xml = src.read("word/document.xml").decode("utf-8")
    b0 = xml.index("<w:body>") + len("<w:body>")
    sect = xml.rindex("<w:sectPr")
    body = build(_top_paragraphs(xml[b0:sect]))
    xml = xml[:b0] + body + xml[sect:]
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = xml.encode("utf-8") if item.filename == "word/document.xml" else src.read(item.filename)
            dst.writestr(item, data)
    return out.getvalue()


def _anchored(paras):
    """Абзацы с надписями и рисунками (номер бланка, «Исп.») — оставляем на месте."""
    return [x for _, _, x in paras if "<w:drawing" in x or "<w:pict" in x or "<mc:AlternateContent" in x]


def _number_date(number, date_text, size=24):
    return _p([f"№ {number or '___________________'}",
               date_words(date_text) if date_text else "«___» ___________ 20__ г."], size=size)


def _executor(xml, executor, phone):
    """В надписи «Исп: … Тел: …» подставляем исполнителя письма."""
    def repl(m):
        t = m.group(2)
        if re.fullmatch(r"\s*\d{4,}\s*", t):  # типографский номер бланка — не для сформированных писем
            t = ""
        elif t.startswith("Исп:"):
            t = f"Исп: {executor}" if executor else "Исп:"
        elif t.startswith("Тел:"):
            t = f"Тел: {phone}" if phone else "Тел:"
        return m.group(1) + escape(t) + m.group(3)
    return re.sub(r"(<w:t(?:\s[^>]*)?>)([^<]*)(</w:t>)", repl, xml)


def letter_docx(blank_bytes, *, number, date_text, addressee, subject, paragraphs, signer_pos="", signer_name="",
                attachments=(), executor="", executor_phone=""):
    def build(paras):
        keep = [_executor(x, executor, executor_phone) for x in _anchored(paras)]
        # надпись «Исп.» привязана к абзацу под номером — ставим её туда же, как на бланке
        out = [_number_date(number, date_text), *keep, _p()]
        out.append(_p(addressee.split("\n"), bold=True, left=4600))
        out += [_p(), _p(subject, bold=True, after=120)]
        out += [_p(t, jc="both", first=709, after=60) for t in paragraphs if t.strip()]
        if attachments:
            out += [_p(), _p("Приложения:", bold=True)]
            out += [_p(f"{i}. {a}") for i, a in enumerate(attachments, 1)]
        out += [_p(), _p(), _p(f"{signer_pos}\t{signer_name}", bold=True, tab_right=True)]
        return "".join(out)
    return _rebuild(blank_bytes, build)


def order_docx(blank_bytes, *, number, date_text, title, basis, points, signer_pos="", signer_name=""):
    def build(paras):
        head = next((x for _, _, x in paras if "БҰЙРЫҚ" in _text(x) or "ПРИКАЗ" in _text(x)), "")
        if not head:
            head = _p("БҰЙРЫҚ\tПРИКАЗ", bold=True, size=28, tab_right=True)
        out = [_p(), head, _number_date(number, date_text), _p()]
        out.append(_p(title.split("\n"), bold=True, size=28, left=-142))
        out.append(_p())
        if basis:
            out.append(_p(basis, size=28, jc="both", first=709))
        out.append(_p("ПРИКАЗЫВАЮ:", bold=True, size=28, first=709))
        out += [_p(f"{i}. {t}", size=28, jc="both", first=709) for i, t in enumerate(points, 1)]
        out += [_p(), _p(), _p(f"{signer_pos}\t{signer_name}", bold=True, size=28, left=-142, tab_right=True)]
        return "".join(out)
    return _rebuild(blank_bytes, build)
