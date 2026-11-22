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


EMU = 6096  # одна точка листа при 150 dpi (914400 EMU в дюйме)
PAGE_W = 1240
# Центр и наибольший размер образцов, точки при 150 dpi — как в pdf.py (SEAL_BOX, SIGN_BOX)
PLACES = {"seal": (88 + 330, 10, 250, 250), "sign": (PAGE_W - 88 - 445, 0, 300, 130)}


def _png_size(data):
    from PIL import Image
    with Image.open(io.BytesIO(data)) as im:
        return im.size


def _anchor(key, rid, size, n):
    """Образец (PNG) поверх текста: по горизонтали от края листа, по вертикали от строки подписи."""
    cx, cy, max_w, max_h = PLACES[key]
    k = min(max_w / size[0], max_h / size[1])
    w, h = size[0] * k, size[1] * k
    x, y = int((cx - w / 2) * EMU), int((cy - h / 2) * EMU)
    w, h = int(w * EMU), int(h * EMU)
    return (f'<w:r><w:drawing><wp:anchor distT="0" distB="0" distL="0" distR="0" simplePos="0" '
            f'relativeHeight="{251700000 + n}" behindDoc="0" locked="0" layoutInCell="1" allowOverlap="1">'
            f'<wp:simplePos x="0" y="0"/><wp:positionH relativeFrom="page"><wp:posOffset>{x}</wp:posOffset>'
            f'</wp:positionH><wp:positionV relativeFrom="paragraph"><wp:posOffset>{y}</wp:posOffset></wp:positionV>'
            f'<wp:extent cx="{w}" cy="{h}"/><wp:effectExtent l="0" t="0" r="0" b="0"/><wp:wrapNone/>'
            f'<wp:docPr id="{9100 + n}" name="pb-{key}"/><wp:cNvGraphicFramePr/>'
            f'<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            f'<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:nvPicPr>'
            f'<pic:cNvPr id="{9100 + n}" name="pb-{key}.png"/><pic:cNvPicPr/></pic:nvPicPr><pic:blipFill>'
            f'<a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm>'
            f'<a:off x="0" y="0"/><a:ext cx="{w}" cy="{h}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/>'
            f'</a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:anchor></w:drawing></w:r>')


def _with_marks(paragraph, marks):
    """Вставить образцы подписи и печати в абзац строки подписи."""
    if not marks:
        return paragraph
    i = paragraph.index("</w:pPr>") + len("</w:pPr>")
    return paragraph[:i] + marks + paragraph[i:]


def _blank_no(number):
    """Регистрационный номер бланка внизу справа (рамка текста, привязанная к листу)."""
    if not number:
        return ""
    return (f'<w:p><w:pPr><w:framePr w:w="2268" w:h="397" w:hRule="exact" w:hAnchor="page" w:vAnchor="page" '
            f'w:x="{11906 - 850 - 2268}" w:y="{16838 - 1134 + 120}"/><w:jc w:val="right"/></w:pPr>'
            f'{_run(number)}</w:p>')


def _rebuild(blank_bytes, build, images=None):
    """Пересобрать DOCX: build(paragraphs, marks) -> новое тело (без sectPr).
    images: {"sign": png, "seal": png} — образцы, marks: готовые вставки для строки подписи."""
    src = zipfile.ZipFile(io.BytesIO(blank_bytes))
    xml = src.read("word/document.xml").decode("utf-8")
    rels = src.read("word/_rels/document.xml.rels").decode("utf-8")
    types = src.read("[Content_Types].xml").decode("utf-8")
    extra, marks = {}, ""
    for n, (key, data) in enumerate((k, v) for k, v in (images or {}).items() if v):
        rid, target = f"rIdPb{key.title()}", f"media/pb-{key}.png"
        rels = rels.replace("</Relationships>", f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/'
                                                f'officeDocument/2006/relationships/image" Target="{target}"/>'
                                                "</Relationships>")
        extra["word/" + target] = data
        marks += _anchor(key, rid, _png_size(data), n)
    if extra and 'Extension="png"' not in types:
        i = types.index(">", types.index("<Types")) + 1
        types = types[:i] + '<Default Extension="png" ContentType="image/png"/>' + types[i:]
    b0 = xml.index("<w:body>") + len("<w:body>")
    sect = xml.rindex("<w:sectPr")
    body = build(_top_paragraphs(xml[b0:sect]), marks)
    xml = xml[:b0] + body + xml[sect:]
    changed = {"word/document.xml": xml, "word/_rels/document.xml.rels": rels, "[Content_Types].xml": types}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = changed[item.filename].encode("utf-8") if item.filename in changed else src.read(item.filename)
            dst.writestr(item, data)
        for name, data in extra.items():
            dst.writestr(name, data)
    return out.getvalue()


def _anchored(paras):
    """Абзацы с надписями и рисунками (номер бланка, «Исп.») — оставляем на месте."""
    return [x for _, _, x in paras if "<w:drawing" in x or "<w:pict" in x or "<mc:AlternateContent" in x]


def _number_date(number, date_text, size=24):
    return _p([f"№ {number or '___________________'}",
               date_words(date_text) if date_text else "«___» ___________ 20__ г."], size=size)


def _executor(xml, executor, phone, blank_number=""):
    """В надписи «Исп: … Тел: …» подставляем исполнителя письма, в надпись «000001» — номер бланка."""
    def repl(m):
        t = m.group(2)
        if re.fullmatch(r"\s*\d{4,}\s*", t):  # типографский номер бланка -> регистрационный номер этого бланка
            t = blank_number
        elif t.startswith("Исп:"):
            t = f"Исп: {executor}" if executor else "Исп:"
        elif t.startswith("Тел:"):
            t = f"Тел: {phone}" if phone else "Тел:"
        return m.group(1) + escape(t) + m.group(3)
    xml = re.sub(r"(<w:t(?:\s[^>]*)?>)([^<]*)(</w:t>)", repl, xml)
    return _pt12(xml) if "Исп:" in xml else xml


def _pt12(xml):
    """Весь текст документа — 12 pt (w:sz в полупунктах)."""
    return re.sub(r'(<w:sz(?:Cs)? w:val=")\d+(")', r"\g<1>24\2", xml)


def letter_docx(blank_bytes, *, number, date_text, addressee, subject, paragraphs, signer_pos="", signer_name="",
                attachments=(), executor="", executor_phone="", sign_png=None, seal_png=None, blank_number=""):
    def build(paras, marks):
        keep = [_executor(x, executor, executor_phone, blank_number) for x in _anchored(paras)]
        # надпись «Исп.» привязана к абзацу под номером — ставим её туда же, как на бланке
        out = [_number_date(number, date_text), *keep, _p()]
        out.append(_p(addressee.split("\n"), bold=True, left=4600))
        out += [_p(), _p(subject, bold=True, after=120)]
        out += [_p(t, jc="both", first=709, after=60) for t in paragraphs if t.strip()]
        if attachments:
            out += [_p(), _p("Приложения:", bold=True)]
            out += [_p(f"{i}. {a}") for i, a in enumerate(attachments, 1)]
        out += [_p(), _p(), _with_marks(_p(f"{signer_pos}\t{signer_name}", bold=True, tab_right=True), marks)]
        if blank_number and not any(re.search(r">\s*\d{4,}\s*<", x) for x in _anchored(paras)):
            out.append(_blank_no(blank_number))
        return "".join(out)
    return _rebuild(blank_bytes, build, {"sign": sign_png, "seal": seal_png})


def order_docx(blank_bytes, *, number, date_text, title, basis, points, signer_pos="", signer_name="",
               sign_png=None, seal_png=None, blank_number=""):
    def build(paras, marks):
        out = [_p(), _p("БҰЙРЫҚ\tПРИКАЗ", bold=True, tab_right=True), _number_date(number, date_text), _p()]
        out.append(_p(title.split("\n"), bold=True, left=-142))
        out.append(_p())
        if basis:
            out.append(_p(basis, jc="both", first=709))
        out.append(_p("ПРИКАЗЫВАЮ:", bold=True, first=709))
        out += [_p(f"{i}. {t}", jc="both", first=709) for i, t in enumerate(points, 1)]
        out += [_p(), _p(), _with_marks(_p(f"{signer_pos}\t{signer_name}", bold=True, left=-142, tab_right=True),
                                        marks)]
        out.append(_blank_no(blank_number))
        return "".join(out)
    return _rebuild(blank_bytes, build, {"sign": sign_png, "seal": seal_png})
