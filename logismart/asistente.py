# ============================================================
# ASISTENTE EXPLICATIVO (RAG SENCILLO)
# ============================================================
#
#   pregunta ─► 1. RECUPERAR registros de MongoDB (consulta primero)
#            ─► 2. Si no hay registros: "No tengo información..." (sin LLM)
#            ─► 3. CONTEXTO con fuentes numeradas [F1], [F2]...
#            ─► 4. LLM responde SOLO con ese contexto y cita fuentes
#            ─► 5. Verificación de citas; si el LLM no está disponible,
#                  se responde con una plantilla a partir de los datos.
# ============================================================

import re
from datetime import datetime, timedelta

from .clasificador import RE_CAMION, RE_PLACA, normalizar
from .llm import ErrorLLM

SIN_INFORMACION = "No tengo información en la base de datos para responder eso."

PROMPT_SISTEMA_ASISTENTE = f"""Eres el asistente explicativo del centro de control LogiSmart.
Respondes preguntas de operadores sobre camiones, accesos, incidentes y riesgos.

Reglas estrictas:
1. Usa ÚNICAMENTE la información del bloque CONTEXTO. No uses conocimiento externo.
2. Cita la fuente de cada afirmación con su etiqueta, por ejemplo [F1].
3. Si el CONTEXTO no contiene la respuesta, responde exactamente: "{SIN_INFORMACION}"
4. No inventes placas, fechas, nombres, cifras ni razones.
5. Responde en español, en máximo 120 palabras, de forma clara para un operador.
6. Para explicar decisiones de acceso, menciona las premisas y la regla que las causó."""

_INTENCIONES = {
    "riesgos": ["riesgo", "etic", "mitigacion", "sesgo", "privacidad", "alucinacion"],
    "incidentes": ["incidente", "correo", "reporte", "abierto", "pendiente"],
    "denegados": ["denegad", "rechazad", "no entro", "bloquead"],
    "inspeccion": ["inspeccion", "revision", "inspeccionad"],
}


def extraer_identificadores(texto):
    camiones = sorted({f"CAM-{n}" for n in RE_CAMION.findall(texto)})
    placas = sorted({f"{a}-{b}-{c}" for a, b, c in RE_PLACA.findall(texto.upper()) if a != "CAM"})
    return camiones, placas


def _fecha(valor):
    return valor.strftime("%Y-%m-%d %H:%M") if isinstance(valor, datetime) else str(valor or "")


def _fuente_acceso(a):
    explicacion = " | ".join(a.get("explicacion", [])[-3:])
    return (f"Acceso del {_fecha(a.get('fecha'))}: camión {a.get('camion_id')} placa {a.get('placa')} "
            f"({a.get('empresa', 's/empresa')}); decisión {a.get('decision')}; operador {a.get('operador')}; "
            f"premisas {a.get('premisas')}; {explicacion}")


def _fuente_camion(c):
    cert = c.get("certificacion_conductor", {})
    return (f"Camión {c.get('camion_id')} placa {c.get('placa')} de {c.get('empresa')}; "
            f"autorización previa: {'sí' if c.get('autorizacion') else 'no'}; certificación del conductor "
            f"{'vigente' if cert.get('vigente') else 'no vigente'} hasta {cert.get('vencimiento')}; "
            f"peso máximo {c.get('peso_maximo_kg')} kg.")


def _fuente_incidente(i):
    cl = i.get("clasificacion", {})
    return (f"Incidente del {_fecha(i.get('fecha'))}: asunto «{i.get('asunto', '')}»; categoría {cl.get('categoria')}; "
            f"prioridad {cl.get('prioridad')}; estado {i.get('estado')}; resumen: {cl.get('resumen')}")


def _fuente_riesgo(r):
    return (f"Riesgo ético del módulo {r.get('modulo')}: {r.get('descripcion')} (categoría {r.get('categoria')}); "
            f"probabilidad {r.get('probabilidad')}, impacto {r.get('impacto')}, puntaje {r.get('probabilidad', 0) * r.get('impacto', 0)}; "
            f"residual {r.get('probabilidad_residual', 0) * r.get('impacto_residual', 0)}; mitigación: {r.get('mitigacion')}")


def recuperar(db, pregunta, ids_previos=((), ())):
    """Consulta MongoDB y devuelve la lista de fuentes relevantes."""
    camiones, placas = extraer_identificadores(pregunta)
    bajo = normalizar(pregunta)
    intenciones = {k for k, palabras in _INTENCIONES.items() if any(p in bajo for p in palabras)}
    if not camiones and not placas and not intenciones:
        camiones, placas = ids_previos  # preguntas de seguimiento ("¿y cuándo entró?")

    fuentes = []

    def agregar(coleccion, doc, texto):
        if not any(f["id"] == doc["_id"] for f in fuentes):
            fuentes.append({"coleccion": coleccion, "id": doc["_id"], "texto": texto})

    for cam in db.listar("camiones", {"$or": [{"camion_id": {"$in": list(camiones)}}, {"placa": {"$in": list(placas)}}]},
                         orden=None) if (camiones or placas) else []:
        agregar("camiones", cam, _fuente_camion(cam))
        camiones = sorted(set(camiones) | {cam["camion_id"]})
        placas = sorted(set(placas) | {cam["placa"]})

    if camiones or placas:
        filtro = {"$or": [{"camion_id": {"$in": list(camiones)}}, {"placa": {"$in": list(placas)}}]}
        if "denegados" in intenciones:
            filtro = {"$and": [filtro, {"decision": "DENEGADO"}]}
        elif "inspeccion" in intenciones:
            filtro = {"$and": [filtro, {"decision": "INSPECCION"}]}
        for a in db.listar("accesos", filtro, limite=4):
            agregar("accesos", a, _fuente_acceso(a))
        for i in db.listar("incidentes", {"$or": [
            {"clasificacion.entidades.camiones": {"$in": list(camiones)}},
            {"clasificacion.entidades.placas": {"$in": list(placas)}},
        ]}, limite=3):
            agregar("incidentes", i, _fuente_incidente(i))
    else:
        desde = datetime.now() - timedelta(days=7)
        if "denegados" in intenciones:
            for a in db.listar("accesos", {"decision": "DENEGADO", "fecha": {"$gte": desde}}, limite=6):
                agregar("accesos", a, _fuente_acceso(a))
        if "inspeccion" in intenciones:
            for a in db.listar("accesos", {"decision": "INSPECCION", "fecha": {"$gte": desde}}, limite=6):
                agregar("accesos", a, _fuente_acceso(a))
        if "incidentes" in intenciones:
            for i in db.listar("incidentes", {"estado": {"$ne": "cerrado"}}, limite=6):
                agregar("incidentes", i, _fuente_incidente(i))

    if "riesgos" in intenciones:
        riesgos = db.listar("riesgos_eticos", orden=None)
        riesgos.sort(key=lambda r: r.get("probabilidad", 0) * r.get("impacto", 0), reverse=True)
        for r in riesgos[:5]:
            agregar("riesgos_eticos", r, _fuente_riesgo(r))

    for n, f in enumerate(fuentes, start=1):
        f["etiqueta"] = f"F{n}"
    return fuentes, (tuple(camiones), tuple(placas))


def _respuesta_plantilla(pregunta, fuentes):
    """Respuesta determinista (sin LLM) construida solo con los registros recuperados."""
    lineas = []
    accesos = [f for f in fuentes if f["coleccion"] == "accesos"]
    if accesos:
        a = accesos[0]
        decision = re.search(r"decisión (\w+)", a["texto"])
        motivo = re.search(r"Decisión: \w+ \([^)]*\)\. ([^|]+)", a["texto"])
        lineas.append(f"El registro más reciente [{a['etiqueta']}] muestra la decisión "
                      f"**{decision.group(1) if decision else '?'}**"
                      + (f": {motivo.group(1).strip()}" if motivo else "."))
    for f in fuentes[: 4 if not accesos else 3]:
        if f is not (accesos[0] if accesos else None):
            lineas.append(f"- [{f['etiqueta']}] {f['texto'][:220]}")
    return "\n".join(lineas) if lineas else SIN_INFORMACION


def responder(db, cliente, pregunta, ids_previos=((), ())):
    """Devuelve dict con respuesta, fuentes, modo y advertencias."""
    pregunta = (pregunta or "").strip()
    if not pregunta:
        raise ValueError("Escribe una pregunta.")
    fuentes, ids = recuperar(db, pregunta, ids_previos)
    if not fuentes:
        return {"respuesta": SIN_INFORMACION, "fuentes": [], "modo": "sin_datos", "ids": ids, "advertencias": []}

    contexto = "\n".join(f"[{f['etiqueta']}] ({f['coleccion']}/{f['id']}) {f['texto']}" for f in fuentes)
    if cliente is None:
        return {"respuesta": _respuesta_plantilla(pregunta, fuentes), "fuentes": fuentes, "modo": "plantilla",
                "ids": ids, "advertencias": ["LLM desactivado: respuesta generada con plantilla a partir de los datos."]}

    mensajes = [
        {"role": "system", "content": PROMPT_SISTEMA_ASISTENTE},
        {"role": "user", "content": f"CONTEXTO:\n{contexto}\n\nPREGUNTA: {pregunta}"},
    ]
    try:
        texto, latencia = cliente.chat(mensajes)
    except ErrorLLM as e:
        return {"respuesta": _respuesta_plantilla(pregunta, fuentes), "fuentes": fuentes, "modo": "plantilla",
                "ids": ids, "advertencias": [f"El LLM no respondió ({e}); se usó una plantilla con los datos."]}

    advertencias = []
    citadas = set(re.findall(r"\[(F\d+)\]", texto))
    validas = {f["etiqueta"] for f in fuentes}
    if citadas - validas:
        advertencias.append(f"El modelo citó fuentes inexistentes: {', '.join(sorted(citadas - validas))}. Verifica la respuesta.")
    if not citadas and SIN_INFORMACION not in texto:
        advertencias.append("El modelo no citó fuentes; contrasta la respuesta con los registros mostrados.")
    cliente.registrar("asistente", mensajes[-1]["content"], texto, latencia,
                      extra={"citas": sorted(citadas), "advertencias": advertencias})
    return {"respuesta": texto, "fuentes": fuentes, "modo": "llm", "latencia_ms": round(latencia),
            "ids": ids, "advertencias": advertencias}
