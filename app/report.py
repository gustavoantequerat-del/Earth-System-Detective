"""Ficha descargable en PDF de un cuerpo de agua: veredicto, motivos, pruebas, sospechosos, proteccion e imagenes."""
from __future__ import annotations

import datetime
import io
from pathlib import Path

from fpdf import FPDF

STATE_RGB = {"Huella humana": (220, 70, 70), "Alerta temprana": (140, 90, 210), "Incalculable": (200, 150, 20),
             "Aguas arriba": (60, 120, 220), "Causa climatica": (230, 120, 50), "Intacto": (40, 160, 110)}
TEST_NAMES = {"clima": "1. Lo que el clima no explica", "control": "2. Gemela de control",
              "coincidencia": "3. Coincidencia en el tiempo"}
SOURCES = ("Landsat 5/7/8/9 (NASA/USGS), JRC Global Surface Water, MapBiomas Bolivia y MapBiomas Agua, NASA POWER, "
           "CHIRPS, ERA5-Land, NOAA ONI, Hansen GFC, MODIS MCD64A1 y MOD16, NASA FIRMS, WDPA (UNEP-WCMC), "
           "OpenStreetMap.")


def _t(s) -> str:
    """fpdf con fuentes base solo admite latin-1."""
    s = str(s).replace("—", "-").replace("–", "-").replace("·", "-").replace("²", "2").replace("≥", ">=")
    return s.encode("latin-1", "replace").decode("latin-1")


class _Doc(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(110, 110, 130)
        self.cell(0, 6, _t("Detector de huella humana - NASA Space Apps 2026 - Bolivia"), align="L")
        self.cell(0, 6, datetime.date.today().isoformat(), align="R", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(130, 130, 140)
        self.cell(0, 6, _t(f"El detector prueba coincidencia y consistencia, no causalidad estricta. Pagina {self.page_no()}"),
                  align="C")


def _section(pdf: FPDF, title: str) -> None:
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(30, 40, 80)
    pdf.cell(0, 7, _t(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(94, 234, 212)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(30, 30, 40)


def _para(pdf: FPDF, text: str, bullet: bool = False) -> None:
    pdf.multi_cell(0, 5, _t(("- " if bullet else "") + text), new_x="LMARGIN", new_y="NEXT")


def _chart(pdf: FPDF, r: dict, h: float = 55) -> None:
    """Agua observada vs esperada por el clima, dibujada con lineas."""
    obs = [v for v in r["observed"]]
    exp = r.get("expected") or []
    years = r["years"]
    vals = [v for v in obs + exp if v is not None]
    if not vals:
        return
    x0, y0, w = pdf.l_margin + 12, pdf.get_y() + 2, pdf.w - pdf.l_margin - pdf.r_margin - 14
    lo, hi = 0.0, max(vals) * 1.05 or 1

    def px(i, v):
        return x0 + w * i / max(len(years) - 1, 1), y0 + h - h * (v - lo) / (hi - lo)

    pdf.set_draw_color(210, 210, 220)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(120, 120, 130)
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        _, y = px(0, v)
        pdf.line(x0, y, x0 + w, y)
        pdf.set_xy(pdf.l_margin - 2, y - 2)
        pdf.cell(14, 4, f"{v:,.0f}", align="R")
    for i, yr in enumerate(years):
        if yr % 5 == 0:
            x, _ = px(i, lo)
            pdf.set_xy(x - 5, y0 + h + 1)
            pdf.cell(10, 4, str(yr), align="C")
    for series, color, width in ((exp, (150, 150, 170), 0.5), (obs, (37, 99, 235), 0.9)):
        pdf.set_draw_color(*color)
        pdf.set_line_width(width)
        pts = [px(i, v) for i, v in enumerate(series) if v is not None]
        for a, b in zip(pts, pts[1:]):
            pdf.line(*a, *b)
    pdf.set_line_width(0.2)
    pdf.set_xy(pdf.l_margin, y0 + h + 6)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(37, 99, 235)
    pdf.cell(45, 4, _t("Azul: agua observada (ha)"))
    pdf.set_text_color(120, 120, 140)
    pdf.cell(0, 4, _t("Gris: lo que el clima solo explicaria"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(30, 30, 40)


def _images(pdf: FPDF, pairs: list[tuple[Path, str]]) -> None:
    pairs = [(p, lab) for p, lab in pairs if p and p.exists()]
    if not pairs:
        return
    if pdf.get_y() > pdf.h - 95:
        pdf.add_page()
    w = (pdf.w - pdf.l_margin - pdf.r_margin - 6 * (len(pairs) - 1)) / len(pairs)
    from PIL import Image
    y = pdf.get_y()
    hmax = 0.0
    for i, (p, lab) in enumerate(pairs):
        with Image.open(p) as im:
            ratio = im.height / im.width
            flat = Image.new("RGB", im.size, (255, 255, 255))
            flat.paste(im.convert("RGBA"), mask=im.convert("RGBA"))
            flat.thumbnail((700, 700))
            buf = io.BytesIO()
            flat.save(buf, "JPEG", quality=80)
        pdf.image(buf, x=pdf.l_margin + i * (w + 6), y=y, w=w)
        hmax = max(hmax, w * ratio)
    pdf.set_y(y + hmax + 2)
    pdf.set_font("Helvetica", "B", 9)
    for i, (_, lab) in enumerate(pairs):
        pdf.set_xy(pdf.l_margin + i * (w + 6), pdf.get_y())
        pdf.cell(w, 5, _t(lab), align="C")
    pdf.ln(7)
    pdf.set_font("Helvetica", "", 10)


def build(r: dict, protection: dict, ctx_dir: Path, img_dir: Path, meta: dict | None, fires: dict | None,
          action: str) -> bytes:
    pdf = _Doc(format="A4")
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(20, 25, 50)
    pdf.multi_cell(0, 9, _t(r["name"]), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(90, 90, 110)
    pdf.cell(0, 6, _t(f"{r.get('department', '')}  -  {r['lat']:.3f}, {r['lon']:.3f}  -  agua 1985-2024"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    col = STATE_RGB.get(r["state"], (90, 90, 90))
    pdf.set_fill_color(*col)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(70, 10, _t(f"  {r['state']}"), fill=True)
    pdf.set_text_color(30, 30, 40)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 10, _t(f"   Pruebas superadas {r['n_pass']}/3  -  confianza {r['confidence'].lower()}  -  "
                       f"cambio del agua {r['trend']['change_pct']:+.0f}%"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    _para(pdf, f"Que hacer: {action}")

    if protection.get("ramsar") or protection.get("areas"):
        _section(pdf, "Proteccion legal")
        if protection.get("ramsar"):
            _para(pdf, f"Sitio Ramsar (humedal de importancia internacional): {protection['ramsar']}"
                       + (" (ubicacion aproximada)" if protection.get("ramsar_aprox") else ""), True)
        for a in protection.get("areas", []):
            _para(pdf, f"Area protegida: {a}", True)

    if r.get("why"):
        _section(pdf, "Por que es incalculable" if r["state"] == "Incalculable" else "Lo que hay que saber")
        for w in r["why"]:
            _para(pdf, w, True)

    _section(pdf, "Agua observada y lo que explicaria el clima")
    _chart(pdf, r)
    dec = r.get("decomposition_ha") or {}
    if dec:
        _para(pdf, "Reparto del cambio (ha): " + ", ".join(f"{k}: {v:+,.0f}" for k, v in dec.items()))

    _section(pdf, "Las tres pruebas")
    for k, t in r["tests"].items():
        mark = "No evaluable" if t["pass"] is None else "Si" if t["pass"] else "No"
        _para(pdf, f"{TEST_NAMES.get(k, k)} [{mark}]: {t['detail']}", True)

    if r["suspects"]:
        _section(pdf, "Sospechosos auditados")
        pdf.set_font("Helvetica", "B", 9)
        widths = [70, 22, 22, 30, 30]
        for wd, h in zip(widths, ["Sospechoso", "Tipo", "Evidencia", "Crece desde", "Antecede la caida"]):
            pdf.cell(wd, 6, _t(h), border="B")
        pdf.ln()
        pdf.set_font("Helvetica", "", 9)
        for s in r["suspects"][:10]:
            row = [s["label"], "indirecto" if s.get("indirect") else "directo", s["evidence"], s.get("onset") or "-",
                   "si" if s.get("precedes") else "no"]
            for wd, v in zip(widths, row):
                pdf.cell(wd, 6, _t(v))
            pdf.ln()

    if fires:
        _section(pdf, "Vigilancia de incendios (NASA FIRMS)")
        for nm, a in fires["areas"].items():
            _para(pdf, f"{nm}: {a['focos']} focos en la semana {fires['window']} (normal {a['normal']})"
                       + ("  ALERTA" if a["alerta"] else ""), True)

    if pdf.get_y() > pdf.h - 100:  # titulo e imagenes en la misma pagina
        pdf.add_page()
    _section(pdf, "Antes y despues")
    if meta:
        ya, yb = meta["years"]
        _images(pdf, [(ctx_dir / f"{r['body_id']}_antes.png", str(ya)),
                      (ctx_dir / f"{r['body_id']}_despues.png", str(yb)),
                      (ctx_dir / f"{r['body_id']}_cambios.png", "Lo que aparecio")])
        ch = [f"{meta['legend'][k]['label']}: {v:,} ha" for k, v in meta.get("changes_ha", {}).items()
              if v and k in meta.get("legend", {})]
        if ch:
            _para(pdf, f"Cambios en {meta['window_km']:.0f} km alrededor ({ya}-{yb}): " + "; ".join(ch))
    else:
        yrs = sorted({int(p.stem.split("_")[-1]) for p in img_dir.glob(f"{r['body_id']}_*.png")
                      if p.stem.split("_")[-1].isdigit()}) if img_dir.exists() else []
        if len(yrs) >= 2:
            _images(pdf, [(img_dir / f"{r['body_id']}_{yrs[0]}.png", str(yrs[0])),
                          (img_dir / f"{r['body_id']}_{yrs[-1]}.png", str(yrs[-1]))])

    _section(pdf, "Fuentes y metodo")
    _para(pdf, SOURCES)
    _para(pdf, "Metodo: tendencia Mann-Kendall y pendiente de Sen; modelo de clima (lluvia menos evaporacion y El Nino) "
               "entrenado en 1985-2000; gemela de control estable; un sospechoso directo debe crecer antes de la caida "
               "y ser al menos el 10% del agua perdida. Codigo abierto: "
               "github.com/gustavoantequerat-del/Earth-System-Detective")
    return bytes(pdf.output())
