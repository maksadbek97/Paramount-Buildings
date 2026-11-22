"""PDF документов: фирменный бланк Paramount Buildings, приказ, договор, письмо контрагента.

Страница рисуется через Pillow и сохраняется в PDF (как примерные документы «Моей компании»).
Подпись и печать — визуальные изображения, не ЭЦП (ТЗ п. 35.3).
"""
import io
import math
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageDraw

from core.demo_pdf import font

W, H, M = 1240, 1754, 88
PT = 25  # 12 pt при 150 dpi: весь текст документа — Arial 12 pt
HEAD = 16  # реквизиты в шапке — как на утверждённом бланке
NAVY, GRAY, INK, ACCENT, SEAL = (11, 31, 77), (110, 120, 140), (40, 48, 66), (0, 160, 230), (36, 74, 170)


def wrap(text, fnt, width):
    rows = []
    for para in str(text).split("\n"):
        line = ""
        for word in para.split():
            test = f"{line} {word}".strip()
            if fnt.getlength(test) <= width:
                line = test
            else:
                if line:
                    rows.append(line)
                line = word
        rows.append(line)
    return rows


def _static_img(name):
    for d in settings.STATICFILES_DIRS:
        p = Path(d) / "img" / name
        if p.exists():
            return Image.open(p).convert("RGBA")
    return None


# Казахская колонка шапки — как на утверждённом бланке (docflow/blanks/*.docx)
KZ_ADDRESS = ["010000, ҚР, Астана қаласы,", "Сарыарқа ауданы, Қосшығұлұлы к-і, 19-үй"]
LINE = (47, 74, 110)


def _bin(value):
    v = (value or "").replace(" ", "")
    return " ".join(v[i:i + 3] for i in range(0, len(v), 3)) if len(v) == 12 else v


def _phone(value):
    return (value or "").replace(" ", "").replace("-", "")


def _by_commas(text, fnt, width):
    """Перенос адреса по запятым, как на бланке: «010000, РК, г. Астана, р-н Сарыарка,» / «ул. …, дом 19»."""
    rows, line = [], ""
    for part in [p.strip() for p in text.split(",") if p.strip()]:
        test = f"{line}, {part}" if line else part
        if line and fnt.getlength(test + ",") > width:
            rows.append(line + ",")
            line = part
        else:
            line = test
    if line:
        rows.append(line)
    return [r for row in rows for r in (wrap(row, fnt, width) if fnt.getlength(row) > width else [row])]


def letterhead_columns(company):
    """Три колонки шапки бланка: [(x, [строки])]. Те же строки рисует предпросмотр в браузере (blank.js)."""
    short = company.short_name or company.name.replace("ТОО", "").strip(" «»") or "Paramount Buildings"
    bin_ = _bin(company.bin)
    address = company.actual_address or company.legal_address or ""
    cols = [
        (M, [f"«{short}» ЖШС", *KZ_ADDRESS, f"БСН {bin_}" if bin_ else ""]),
        (552, [f"Тел: {_phone(company.phone)}" if company.phone else "",
               f"e-mail: {company.email}" if company.email else "",
               f"www. {company.website}" if company.website else ""]),
        (880, [company.name, *_by_commas(address, font(HEAD), W - 880 - 30), f"БИН {bin_}" if bin_ else ""]),
    ]
    return [(x, [r for r in rows if r]) for x, rows in cols]


def _letterhead(img, d, company):
    """Шапка фирменного бланка Paramount: логотип, три колонки (ҚАЗ · контакты · РУС), линия, водяной знак."""
    mark = _static_img("blank/watermark.png")
    if mark:
        w = 1750
        mark = mark.resize((w, int(w * mark.height / mark.width)))
        img.paste(mark, (-128, 475), mark)
    logo = _static_img("blank/header-logo.png")
    if logo:
        logo = logo.resize((590, int(590 * logo.height / logo.width)))
        img.paste(logo, (M - 8, 70), logo)
    for x, rows in letterhead_columns(company):
        y = 240
        for i, t in enumerate(rows):
            bold = i == 0 and x != 552
            d.text((x, y), t, font=font(HEAD, bold), fill=(20, 24, 36))
            y += 25
    d.line([M, 366, W - 40, 366], fill=LINE, width=2)
    return 410


def _executor(d, executor, phone=""):
    if executor:
        d.text((M, H - 150), f"Исп: {executor}", font=font(PT), fill=INK)
    if phone:
        d.text((M, H - 112), f"Тел: {_phone(phone)}", font=font(PT), fill=INK)


def _signature(d, x, y):
    """Росчерк подписи (визуальный образ)."""
    pts = []
    for i in range(60):
        t = i / 59
        pts.append((x + t * 210, y + 22 * math.sin(t * 9) * (1 - t * .6) - t * 18))
    d.line(pts, fill=SEAL, width=4, joint="curve")
    d.line([(x + 40, y + 26), (x + 230, y - 8)], fill=SEAL, width=3)


def _seal(img, cx, cy, company):
    r = 118
    layer = Image.new("RGBA", (r * 2 + 10, r * 2 + 10), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    c = r + 5
    col = SEAL + (205,)
    ld.ellipse([c - r, c - r, c + r, c + r], outline=col, width=6)
    ld.ellipse([c - r + 16, c - r + 16, c + r - 16, c + r - 16], outline=col, width=2)
    ld.ellipse([c - 52, c - 52, c + 52, c + 52], outline=col, width=2)
    text = f"{company.name.upper()} · БИН {company.bin} · АСТАНА · "
    f = font(17, True)
    n = len(text)
    for i, ch in enumerate(text):
        a = 2 * math.pi * i / n - math.pi / 2
        rr = r - 32
        ch_img = Image.new("RGBA", (30, 30), (0, 0, 0, 0))
        ImageDraw.Draw(ch_img).text((15, 15), ch, font=f, fill=col, anchor="mm")
        ch_img = ch_img.rotate(-math.degrees(a) - 90, resample=Image.BICUBIC)
        layer.alpha_composite(ch_img, (int(c + rr * math.cos(a) - 15), int(c + rr * math.sin(a) - 15)))
    ld.text((c, c - 12), "PARAMOUNT", font=font(18, True), fill=col, anchor="mm")
    ld.text((c, c + 12), "BUILDINGS", font=font(18, True), fill=col, anchor="mm")
    layer = layer.rotate(-12, resample=Image.BICUBIC)
    img.paste(layer, (cx - c, cy - c), layer)


def _footer(d, note="Образец документа · демо-версия Smart Building"):
    d.line([M, H - 150, W - M, H - 150], fill=(230, 236, 245), width=2)
    d.text((W // 2, H - 118), note, font=font(PT), fill=GRAY, anchor="mm")


def _blank_note(d, note):
    """Мелкая пометка внизу бланка (например, что изображение подписи — не ЭЦП)."""
    if note:
        d.text((W - M, H - 66), note, font=font(PT), fill=GRAY, anchor="ra")


def _body(d, y, paragraphs, size=PT, gap=16, indent=True, max_y=H - 470):
    f = font(size)
    for para in paragraphs:
        if not para:
            continue
        bold = para.startswith("**")
        text = para.strip("*")
        fnt = font(size, True) if bold else f
        for i, row in enumerate(wrap(text, fnt, W - 2 * M - (0 if not indent else 0))):
            if y > max_y:
                d.text((M, y), "…", font=f, fill=INK)
                return y + 36
            d.text((M + (40 if indent and i == 0 and not bold else 0), y), row, font=fnt, fill=INK)
            y += int(size * 1.5)
        y += gap
    return y


RU_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
             "ноября", "декабря"]


def date_words(date_text):
    """«22» ноября 2026 г. — как в строке даты на бланке. Принимает ДД.ММ.ГГГГ."""
    try:
        dd, mm, yy = date_text.split(".")
        return f"«{dd}» {RU_MONTHS[int(mm) - 1]} {yy} г."
    except (ValueError, IndexError):
        return date_text


def _number_line(d, x, y, number, date_text):
    d.text((x, y), f"№ {number or '___________________'}", font=font(PT), fill=INK)
    d.text((x, y + 38), date_words(date_text) if date_text else "«___» ___________ 20__ г.", font=font(PT),
           fill=INK)


def letter_pdf(company, number, date_text, addressee, subject, paragraphs, signer_pos="", signer_name="",
               sign=False, seal=False, attachments=(), executor="", executor_phone=""):
    """Исходящее письмо на фирменном бланке Paramount (как «бланк для ПИСЬМА»)."""
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    y = _letterhead(img, d, company)
    _number_line(d, M, y, number, date_text)
    ay = y
    for row in wrap(addressee, font(PT, True), 470):
        d.text((W - M - 470, ay), row, font=font(PT, True), fill=INK)
        ay += 38
    y = max(y + 120, ay + 30)
    for row in wrap(subject, font(PT, True), W - 2 * M):
        d.text((M, y), row, font=font(PT, True), fill=INK)
        y += 38
    y += 22
    y = _body(d, y, paragraphs)
    if attachments:
        y += 6
        d.text((M, y), "Приложения:", font=font(PT, True), fill=INK)
        y += 38
        for i, a in enumerate(attachments, 1):
            for j, row in enumerate(wrap(f"{i}. {a}", font(PT), W - 2 * M - 20)):
                d.text((M + 20, y), row, font=font(PT), fill=INK)
                y += 38
    y = max(y + 50, H - 450)
    d.text((M, y), signer_pos, font=font(PT, True), fill=INK)
    d.text((W - M, y), signer_name, font=font(PT, True), fill=INK, anchor="ra")
    if seal:
        _seal(img, M + 330, y + 10, company)
    if sign:
        _signature(d, W - M - 560, y + 6)
    _executor(d, executor, executor_phone)
    _blank_note(d, "Изображение подписи и печати не является ЭЦП" if (sign or seal) else "")
    return _save(img)


def order_pdf(company, number, date_text, title, basis, points, signer_pos, signer_name, sign=True, seal=False):
    """Приказ на фирменном бланке Paramount (как «бланк для ПРИКАЗА»): БҰЙРЫҚ — ПРИКАЗ."""
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    y = _letterhead(img, d, company) + 30
    d.text((M, y), "БҰЙРЫҚ", font=font(PT, True), fill=INK)
    d.text((W - M, y), "ПРИКАЗ", font=font(PT, True), fill=INK, anchor="ra")
    _number_line(d, M, y + 58, number, date_text)
    y += 170
    for row in wrap(title, font(PT, True), 760):
        d.text((M + 60, y), row, font=font(PT, True), fill=INK)
        y += 38
    y += 24
    y = _body(d, y, ([basis] if basis else []) + ["**ПРИКАЗЫВАЮ:"] + [f"{i}. {p}" for i, p in enumerate(points, 1)])
    y = max(y + 60, H - 430)
    d.text((M + 60, y), signer_pos, font=font(PT, True), fill=INK)
    d.text((W - M, y), signer_name, font=font(PT, True), fill=INK, anchor="ra")
    if sign:
        _signature(d, W - M - 560, y + 6)
    if seal:
        _seal(img, M + 330, y + 10, company)
    _blank_note(d, "Изображение подписи и печати не является ЭЦП" if (sign or seal) else "")
    return _save(img)


def contract_pdf(company, number, date_text, title, counterparty, subject, amount_text, terms, signer_name):
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    y = _letterhead(img, d, company)
    d.text((W // 2, y + 20), f"ДОГОВОР № {number or '—'}", font=font(PT, True), fill=NAVY, anchor="mm")
    d.text((W // 2, y + 60), title[:80], font=font(PT), fill=GRAY, anchor="mm")
    d.text((M, y + 104), "г. Астана", font=font(PT), fill=INK)
    d.text((W - M, y + 104), date_text, font=font(PT), fill=INK, anchor="ra")
    y += 160
    paras = [f"{company.name}, в лице директора {signer_name}, действующего на основании Устава, и {counterparty}, "
             f"далее совместно «Стороны», заключили настоящий договор о нижеследующем.",
             "**1. Предмет договора", subject,
             "**2. Цена и порядок оплаты", amount_text,
             "**3. Сроки и обязательства", *terms]
    y = _body(d, y, paras, gap=10, max_y=H - 520)
    y = max(y + 30, H - 470)
    d.text((M, y), "Исполнитель / Сторона 1", font=font(PT, True), fill=NAVY)
    d.text((W // 2 + 20, y), "Сторона 2", font=font(PT, True), fill=NAVY)
    for i, row in enumerate(wrap(company.name, font(PT), 470)):
        d.text((M, y + 34 + i * 34), row, font=font(PT), fill=INK)
    for i, row in enumerate(wrap(counterparty, font(PT), 470)):
        d.text((W // 2 + 20, y + 34 + i * 34), row, font=font(PT), fill=INK)
    d.line([M, y + 160, M + 380, y + 160], fill=GRAY, width=2)
    d.line([W // 2 + 20, y + 160, W // 2 + 400, y + 160], fill=GRAY, width=2)
    d.text((M, y + 168), signer_name, font=font(PT), fill=GRAY)
    _footer(d)
    return _save(img)


def external_pdf(org, org_sub, number, date_text, addressee, subject, paragraphs, signer):
    """Письмо от контрагента (входящее) — на условном бланке отправителя."""
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 10], fill=(90, 100, 120))
    d.text((M, 60), org, font=font(PT, True), fill=(50, 58, 80))
    d.text((M, 104), org_sub, font=font(PT), fill=GRAY)
    d.line([M, 150, W - M, 150], fill=(200, 206, 216), width=2)
    y = 190
    d.text((M, y), f"Исх. № {number}", font=font(PT), fill=INK)
    d.text((M, y + 32), f"от {date_text}", font=font(PT), fill=INK)
    ay = y
    for row in wrap(addressee, font(PT, True), 470):
        d.text((W - M - 470, ay), row, font=font(PT, True), fill=INK)
        ay += 38
    y = max(y + 110, ay + 30)
    for row in wrap(subject, font(PT, True), W - 2 * M):
        d.text((M, y), row, font=font(PT, True), fill=INK)
        y += 38
    y += 18
    y = _body(d, y, paragraphs)
    y = max(y + 60, H - 420)
    d.text((M, y), signer, font=font(PT), fill=INK)
    d.line([W - M - 320, y + 28, W - M, y + 28], fill=GRAY, width=2)
    # штамп входящей регистрации
    _footer(d, "Скан входящего письма · образец, демо-версия")
    return _save(img)


def _save(img):
    buf = io.BytesIO()
    img.save(buf, "PDF", resolution=150.0, quality=70)
    return buf.getvalue()
