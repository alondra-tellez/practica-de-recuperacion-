# ============================================================
# REPORTES: CSV, JSON y PDF
# ============================================================

import io
import json
from collections import Counter
from datetime import datetime

import pandas as pd
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .riesgos import nivel, puntaje


def a_json(registros):
    return json.dumps(registros, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def a_csv(registros):
    if not registros:
        return "sin registros\n".encode("utf-8-sig")
    df = pd.json_normalize(registros, sep=".")
    for col in df.columns:  # listas (historial, explicación) en una sola celda legible
        if df[col].map(lambda v: isinstance(v, (list, dict))).any():
            df[col] = df[col].map(lambda v: json.dumps(v, ensure_ascii=False, default=str)
                                  if isinstance(v, (list, dict)) else v)
    return df.to_csv(index=False).encode("utf-8-sig")  # BOM para que Excel respete acentos


def _tabla(datos, anchos=None):
    t = Table(datos, colWidths=anchos, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3b57")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c8d0d8")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f5f8")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _grafica_riesgos(riesgos):
    d = Drawing(16 * cm, 6 * cm)
    g = VerticalBarChart()
    g.x, g.y, g.width, g.height = 1 * cm, 1 * cm, 14.5 * cm, 4.5 * cm
    g.data = [[puntaje(r) for r in riesgos], [puntaje(r, True) for r in riesgos]]
    g.categoryAxis.categoryNames = [f"R{i}" for i in range(1, len(riesgos) + 1)]
    g.valueAxis.valueMin, g.valueAxis.valueMax, g.valueAxis.valueStep = 0, 25, 5
    g.bars[0].fillColor = colors.HexColor("#d64545")
    g.bars[1].fillColor = colors.HexColor("#2e7dba")
    d.add(g)
    d.add(String(1 * cm, 5.7 * cm, "Rojo: puntaje inherente   Azul: puntaje residual", fontSize=8))
    return d


def pdf_reporte(db, cfg, desde=None, hasta=None, operador=""):
    estilos = getSampleStyleSheet()
    rango = {}
    if desde:
        rango["$gte"] = desde
    if hasta:
        rango["$lte"] = hasta
    filtro = {"fecha": rango} if rango else {}
    accesos = db.listar("accesos", filtro)
    incidentes = db.listar("incidentes", filtro)
    riesgos = db.listar("riesgos_eticos", orden=None)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, title="Reporte LogiSmart",
                            leftMargin=1.6 * cm, rightMargin=1.6 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    h = []
    h.append(Paragraph("LogiSmart · Reporte del centro de control", estilos["Title"]))
    periodo = f"{desde:%Y-%m-%d} a {hasta:%Y-%m-%d}" if desde and hasta else "todo el historial"
    h.append(Paragraph(f"Periodo: {periodo} · Generado: {datetime.now():%Y-%m-%d %H:%M} · Operador: {operador or 'N/D'}",
                       estilos["Normal"]))
    h.append(Spacer(1, 10))

    decisiones = Counter(a["decision"] for a in accesos)
    abiertos = sum(1 for i in incidentes if i.get("estado") != "cerrado")
    criticos = sum(1 for r in riesgos if puntaje(r, True) >= cfg["umbral_riesgo_critico"])
    h.append(Paragraph("Indicadores", estilos["Heading2"]))
    h.append(_tabla([
        ["Camiones atendidos", "Accesos", "Acceso / Inspección / Denegado", "Incidentes abiertos", "Riesgos críticos (residual)"],
        [len({a["camion_id"] for a in accesos}), len(accesos),
         f"{decisiones['ACCESO']} / {decisiones['INSPECCION']} / {decisiones['DENEGADO']}", abiertos, criticos],
    ]))

    h.append(Paragraph("Incidentes por categoría y prioridad", estilos["Heading2"]))
    conteo = Counter((i["clasificacion"]["categoria"], i["clasificacion"]["prioridad"]) for i in incidentes)
    categorias = sorted({c for c, _ in conteo})
    h.append(_tabla([["Categoría", "BAJA", "MEDIA", "ALTA", "CRITICA", "Total"]] + [
        [c] + [conteo[(c, p)] for p in ("BAJA", "MEDIA", "ALTA", "CRITICA")]
        + [sum(conteo[(c, p)] for p in ("BAJA", "MEDIA", "ALTA", "CRITICA"))] for c in categorias
    ]))

    h.append(Paragraph("Matriz de riesgos éticos", estilos["Heading2"]))
    if riesgos:
        h.append(_grafica_riesgos(riesgos))
        celda = estilos["BodyText"].clone("celda", fontSize=7, leading=8)
        h.append(_tabla([["#", "Módulo", "Descripción", "Inherente", "Residual", "Nivel residual"]] + [
            [f"R{n}", Paragraph(r["modulo"], celda), Paragraph(r["descripcion"], celda), puntaje(r), puntaje(r, True),
             nivel(puntaje(r, True), cfg)] for n, r in enumerate(riesgos, start=1)
        ], anchos=[1 * cm, 3.2 * cm, 8.3 * cm, 1.6 * cm, 1.6 * cm, 2.2 * cm]))

    h.append(Paragraph("Últimos accesos", estilos["Heading2"]))
    h.append(_tabla([["Fecha", "Camión", "Placa", "Decisión", "Determinantes", "Operador"]] + [
        [f"{a['fecha']:%Y-%m-%d %H:%M}" if isinstance(a["fecha"], datetime) else a["fecha"], a["camion_id"], a["placa"],
         a["decision"], ", ".join(a.get("premisas_determinantes", [])).replace("¬", "no "), a["operador"]]
        for a in accesos[:25]
    ]))
    doc.build(h)
    return buf.getvalue()
