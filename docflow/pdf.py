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

W, H, M = 1240, 1754, 110
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


def _logo():
    for d in settings.STATICFILES_DIRS:
        p = Path(d) / "img" / "logo.png"
        if p.exists():
            return Image.open(p).convert("RGBA")
    return None


def _letterhead(img, d, company):
    d.rectangle([0, 0, W, 12], fill=NAVY)
    logo = _logo()
    if logo:
        logo = logo.resize((300, int(300 * logo.height / logo.width)))
        img.paste(logo, (M, 56), logo)
    right = [company.name, company.legal_address or "", " · ".join(x for x in [
        f"БИН {company.bin}" if company.bin else "", company.phone or ""] if x), company.email or ""]
    y = 52
    for i, t in enumerate(x for x in right if x):
        f = font(20, i == 0)
        d.text((W - M, y), t, font=f, fill=NAVY if i == 0 else GRAY, anchor="ra")
        y += 28
    d.line([M, 180, W - M, 180], fill=ACCENT, width=3)
    return 220


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
    d.text((W // 2, H - 118), note, font=font(19), fill=GRAY, anchor="mm")


def _body(d, y, paragraphs, size=24, gap=16, indent=True, max_y=H - 470):
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


def letter_pdf(company, number, date_text, addressee, subject, paragraphs, signer_pos="", signer_name="",
               sign=False, seal=False, attachments=(), executor=""):
    """Исходящее письмо на фирменном бланке."""
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    y = _letterhead(img, d, company)
    d.text((M, y + 10), f"Исх. № {number or '— (присвоится при регистрации)'}", font=font(22), fill=NAVY)
    d.text((M, y + 44), f"от {date_text}", font=font(22), fill=NAVY)
    ay = y + 10
    for row in wrap(addressee, font(23, True), 470):
        d.text((W - M - 470, ay), row, font=font(23, True), fill=NAVY)
        ay += 34
    y = max(y + 120, ay + 30)
    for row in wrap(subject, font(25, True), W - 2 * M):
        d.text((M, y), row, font=font(25, True), fill=NAVY)
        y += 38
    y += 22
    y = _body(d, y, paragraphs)
    if attachments:
        y += 6
        d.text((M, y), "Приложения:", font=font(22, True), fill=INK)
        y += 34
        for i, a in enumerate(attachments, 1):
            d.text((M + 20, y), f"{i}. {a}", font=font(22), fill=INK)
            y += 32
    y = max(y + 50, H - 450)
    d.text((M, y), signer_pos, font=font(24), fill=NAVY)
    d.text((W - M, y), signer_name, font=font(24, True), fill=NAVY, anchor="ra")
    if seal:
        _seal(img, M + 330, y + 10, company)
    if sign:
        _signature(d, W - M - 560, y + 6)
    if executor:
        d.text((M, H - 210), f"Исп.: {executor}", font=font(18), fill=GRAY)
    _footer(d, "Изображение подписи и печати не является ЭЦП · образец, демо-версия" if (sign or seal) else
            "Образец документа · демо-версия Smart Building")
    return _save(img)


def order_pdf(company, number, date_text, title, basis, points, signer_pos, signer_name, sign=True, seal=False):
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    y = _letterhead(img, d, company)
    d.text((W // 2, y + 20), "ПРИКАЗ", font=font(34, True), fill=NAVY, anchor="mm")
    d.text((M, y + 70), "г. Астана", font=font(22), fill=INK)
    d.text((W - M, y + 70), f"№ {number or '—'} от {date_text}", font=font(22), fill=INK, anchor="ra")
    y += 130
    for row in wrap(title, font(26, True), W - 2 * M):
        d.text((M, y), row, font=font(26, True), fill=NAVY)
        y += 38
    y += 20
    y = _body(d, y, [basis, "**ПРИКАЗЫВАЮ:"] + [f"{i}. {p}" for i, p in enumerate(points, 1)])
    y = max(y + 60, H - 430)
    d.text((M, y), signer_pos, font=font(24), fill=NAVY)
    d.text((W - M, y), signer_name, font=font(24, True), fill=NAVY, anchor="ra")
    if sign:
        _signature(d, W - M - 560, y + 6)
    if seal:
        _seal(img, M + 330, y + 10, company)
    _footer(d)
    return _save(img)


def contract_pdf(company, number, date_text, title, counterparty, subject, amount_text, terms, signer_name):
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    y = _letterhead(img, d, company)
    d.text((W // 2, y + 20), f"ДОГОВОР № {number or '—'}", font=font(32, True), fill=NAVY, anchor="mm")
    d.text((W // 2, y + 60), title[:80], font=font(22), fill=GRAY, anchor="mm")
    d.text((M, y + 104), "г. Астана", font=font(22), fill=INK)
    d.text((W - M, y + 104), date_text, font=font(22), fill=INK, anchor="ra")
    y += 160
    paras = [f"{company.name}, в лице директора {signer_name}, действующего на основании Устава, и {counterparty}, "
             f"далее совместно «Стороны», заключили настоящий договор о нижеследующем.",
             "**1. Предмет договора", subject,
             "**2. Цена и порядок оплаты", amount_text,
             "**3. Сроки и обязательства", *terms]
    y = _body(d, y, paras, size=22, gap=10, max_y=H - 520)
    y = max(y + 30, H - 470)
    d.text((M, y), "Исполнитель / Сторона 1", font=font(20, True), fill=NAVY)
    d.text((W // 2 + 20, y), "Сторона 2", font=font(20, True), fill=NAVY)
    for i, row in enumerate(wrap(company.name, font(20), 470)):
        d.text((M, y + 34 + i * 28), row, font=font(20), fill=INK)
    for i, row in enumerate(wrap(counterparty, font(20), 470)):
        d.text((W // 2 + 20, y + 34 + i * 28), row, font=font(20), fill=INK)
    d.line([M, y + 160, M + 380, y + 160], fill=GRAY, width=2)
    d.line([W // 2 + 20, y + 160, W // 2 + 400, y + 160], fill=GRAY, width=2)
    d.text((M, y + 168), signer_name, font=font(18), fill=GRAY)
    _footer(d)
    return _save(img)


def external_pdf(org, org_sub, number, date_text, addressee, subject, paragraphs, signer):
    """Письмо от контрагента (входящее) — на условном бланке отправителя."""
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 10], fill=(90, 100, 120))
    d.text((M, 60), org, font=font(30, True), fill=(50, 58, 80))
    d.text((M, 104), org_sub, font=font(19), fill=GRAY)
    d.line([M, 150, W - M, 150], fill=(200, 206, 216), width=2)
    y = 190
    d.text((M, y), f"Исх. № {number}", font=font(22), fill=INK)
    d.text((M, y + 32), f"от {date_text}", font=font(22), fill=INK)
    ay = y
    for row in wrap(addressee, font(22, True), 470):
        d.text((W - M - 470, ay), row, font=font(22, True), fill=INK)
        ay += 32
    y = max(y + 110, ay + 30)
    for row in wrap(subject, font(24, True), W - 2 * M):
        d.text((M, y), row, font=font(24, True), fill=INK)
        y += 36
    y += 18
    y = _body(d, y, paragraphs)
    y = max(y + 60, H - 420)
    d.text((M, y), signer, font=font(23), fill=INK)
    d.line([W - M - 320, y + 28, W - M, y + 28], fill=GRAY, width=2)
    # штамп входящей регистрации
    _footer(d, "Скан входящего письма · образец, демо-версия")
    return _save(img)


def _save(img):
    buf = io.BytesIO()
    img.save(buf, "PDF", resolution=150.0, quality=70)
    return buf.getvalue()
