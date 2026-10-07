# ============================================================
# MOTOR DE REGLAS (LÓGICA PROPOSICIONAL)
# ============================================================
#
# Premisas (variables proposicionales):
#   P = autorización previa del camión
#   Q = peso excedido (báscula > peso máximo + tolerancia)
#   R = transporta material peligroso
#   S = certificación del conductor vigente
#   H = ingreso en horario restringido (por defecto 22:00-06:00)   [NUEVA]
#   C = la certificación vence en <= N días (por defecto 30)        [NUEVA]
#
# Reglas originales (se conservan):
#   R1  A = P ∧ S ∧ ¬Q       acceso estándar
#   R2  E = P ∧ (R ∨ Q)      inspección especial
#
# Reglas nuevas:
#   R3  B = R ∧ H            bloqueo de material peligroso en horario
#                            restringido. Justificación: de noche hay
#                            menos personal de respuesta a emergencias y
#                            muchos reglamentos urbanos restringen el
#                            tránsito de materiales peligrosos; se
#                            reprograma la entrada.
#   R4  V = S ∧ C            alerta de renovación: el conductor puede
#                            entrar, pero se notifica que su certificación
#                            está por vencer, para evitar que al día
#                            siguiente quede sin certificación (¬S).
#
# Decisión final (precedencia: seguridad primero):
#   DENEGADO   = B ∨ (¬A ∧ ¬E)
#   INSPECCION = ¬B ∧ E
#   ACCESO     = ¬B ∧ ¬E ∧ A
# ============================================================

import ast
from datetime import date, datetime
from itertools import combinations, product

VARIABLES = {
    "P": "autorización previa",
    "Q": "peso excedido",
    "R": "material peligroso",
    "S": "certificación vigente",
    "H": "horario restringido",
    "C": "certificación por vencer",
}

REGLAS = {
    "A": {
        "nombre": "R1 · Acceso estándar",
        "formula": "P ∧ S ∧ ¬Q",
        "accion": "permitir",
        "variables": "PSQ",
        "f": lambda v: v["P"] and v["S"] and not v["Q"],
    },
    "E": {
        "nombre": "R2 · Inspección especial",
        "formula": "P ∧ (R ∨ Q)",
        "accion": "inspeccionar",
        "variables": "PRQ",
        "f": lambda v: v["P"] and (v["R"] or v["Q"]),
    },
    "B": {
        "nombre": "R3 · Bloqueo por horario (material peligroso)",
        "formula": "R ∧ H",
        "accion": "denegar",
        "variables": "RH",
        "f": lambda v: v["R"] and v["H"],
        "nueva": True,
    },
    "V": {
        "nombre": "R4 · Alerta de renovación de certificación",
        "formula": "S ∧ C",
        "accion": "avisar",
        "variables": "SC",
        "f": lambda v: v["S"] and v["C"],
        "nueva": True,
    },
}

DECISIONES = {
    "DENEGADO": {"color": "#d64545", "semaforo": "🔴", "formula": "B ∨ (¬A ∧ ¬E)"},
    "INSPECCION": {"color": "#e0a100", "semaforo": "🟡", "formula": "¬B ∧ E"},
    "ACCESO": {"color": "#2e9d5b", "semaforo": "🟢", "formula": "¬B ∧ ¬E ∧ A"},
}


def _vf(valor):
    return "V" if valor else "F"


def evaluar_reglas(premisas):
    """Devuelve el valor de cada regla para un conjunto de premisas."""
    valores = {k: bool(premisas.get(k, False)) for k in VARIABLES}
    return {clave: bool(regla["f"](valores)) for clave, regla in REGLAS.items()}


def decidir(resultados):
    if resultados["B"]:
        return "DENEGADO"
    if resultados["E"]:
        return "INSPECCION"
    if resultados["A"]:
        return "ACCESO"
    return "DENEGADO"


def premisas_determinantes(premisas):
    """Análisis contrafactual: premisas que, si cambiaran, cambiarían la decisión."""
    base = decidir(evaluar_reglas(premisas))
    causas = []
    for var in VARIABLES:
        invertidas = {**premisas, var: not premisas.get(var, False)}
        if decidir(evaluar_reglas(invertidas)) != base:
            causas.append(var if premisas.get(var) else f"¬{var}")
    return causas


def evaluar_camion(P, Q, R, S, H=False, C=False, origen=None):
    """
    Evalúa un camión y genera la explicación paso a paso.

    'origen' (opcional) describe de dónde salió cada premisa,
    por ejemplo {"Q": "báscula 41,200 kg > máximo 40,000 kg"}.
    """
    premisas = {"P": bool(P), "Q": bool(Q), "R": bool(R), "S": bool(S), "H": bool(H), "C": bool(C)}
    origen = origen or {}
    resultados = evaluar_reglas(premisas)
    decision = decidir(resultados)

    pasos = ["Premisas:"]
    for var, desc in VARIABLES.items():
        detalle = f" — {origen[var]}" if var in origen else ""
        pasos.append(f"  {var} ({desc}) = {_vf(premisas[var])}{detalle}")

    pasos.append("Evaluación de reglas:")
    sustituciones = {
        "A": f"{_vf(premisas['P'])} ∧ {_vf(premisas['S'])} ∧ ¬{_vf(premisas['Q'])}",
        "E": f"{_vf(premisas['P'])} ∧ ({_vf(premisas['R'])} ∨ {_vf(premisas['Q'])})",
        "B": f"{_vf(premisas['R'])} ∧ {_vf(premisas['H'])}",
        "V": f"{_vf(premisas['S'])} ∧ {_vf(premisas['C'])}",
    }
    for clave, regla in REGLAS.items():
        pasos.append(
            f"  {regla['nombre']}: {clave} = {regla['formula']} = {sustituciones[clave]} = {_vf(resultados[clave])}"
        )

    if resultados["B"]:
        motivo = "R3 (B) está activa: material peligroso en horario restringido; tiene precedencia sobre las demás reglas."
    elif resultados["E"]:
        motivo = "R2 (E) está activa: " + (
            "peso excedido" if premisas["Q"] and not premisas["R"]
            else "material peligroso" if premisas["R"] and not premisas["Q"]
            else "material peligroso y peso excedido"
        ) + " con autorización previa; se envía a inspección aunque A sea verdadera."
    elif resultados["A"]:
        motivo = "R1 (A) está activa y no hay inspección ni bloqueo pendientes."
    else:
        faltantes = [d for v, d in (("P", "sin autorización previa"), ("S", "certificación no vigente")) if not premisas[v]]
        if premisas["Q"]:
            faltantes.append("peso excedido")
        motivo = "Ninguna regla de acceso se cumple (" + ", ".join(faltantes or ["sin condiciones de acceso"]) + ")."

    determinantes = premisas_determinantes(premisas)
    pasos.append(f"Decisión: {decision} ({DECISIONES[decision]['formula']}). {motivo}")
    pasos.append("Premisas determinantes: " + (", ".join(determinantes) or "ninguna premisa individual cambia la decisión"))
    if resultados["V"] and decision != "DENEGADO":
        pasos.append("Aviso: R4 (V) activa — la certificación del conductor vence pronto; notificar renovación.")

    return {
        "premisas": premisas,
        "resultados": resultados,
        "decision": decision,
        "premisas_determinantes": determinantes,
        "explicacion": pasos,
        # Compatibilidad con el código original
        "acceso_estandar": resultados["A"],
        "inspeccion_especial": resultados["E"],
    }


def premisas_desde_camion(camion, peso_kg, material_peligroso, momento, cfg):
    """Deriva P, Q, R, S, H y C a partir del catálogo, la báscula y la hora de llegada."""
    momento = momento or datetime.now()
    cert = camion.get("certificacion_conductor", {})
    try:
        vencimiento = date.fromisoformat(str(cert.get("vencimiento")))
    except ValueError:
        vencimiento = None
    dias = (vencimiento - momento.date()).days if vencimiento else None

    P = bool(camion.get("autorizacion"))
    S = bool(cert.get("vigente", True)) and dias is not None and dias >= 0
    C = S and dias is not None and dias <= cfg["dias_alerta_certificacion"]
    maximo = float(camion.get("peso_maximo_kg", 0) or 0)
    limite = maximo * (1 + cfg["tolerancia_peso_pct"] / 100)
    Q = maximo > 0 and float(peso_kg) > limite
    R = bool(material_peligroso)
    ini, fin = cfg["hora_inicio_restriccion"], cfg["hora_fin_restriccion"]
    h = momento.hour
    H = (ini <= h or h < fin) if ini > fin else (ini <= h < fin)

    origen = {
        "P": f"catálogo: autorización {'registrada' if P else 'no registrada'}",
        "Q": f"báscula {peso_kg:,.0f} kg {'>' if Q else '≤'} límite {limite:,.0f} kg",
        "R": "declarado por el operador" + (" (material peligroso)" if R else ""),
        "S": f"vence {vencimiento.isoformat()} ({dias} días)" if vencimiento else "sin fecha de vencimiento registrada",
        "H": f"llegada {momento:%H:%M}; restricción {ini:02d}:00–{fin:02d}:00",
        "C": f"alerta si faltan ≤ {cfg['dias_alerta_certificacion']} días",
    }
    return {"P": P, "Q": Q, "R": R, "S": S, "H": H, "C": C}, origen


# ------------------------------------------------------------
# TABLAS DE VERDAD
# ------------------------------------------------------------

def tabla_verdad(variables="PQRSHC"):
    """Tabla de verdad completa (2^n filas) de las reglas y la decisión."""
    filas = []
    for valores in product([False, True], repeat=len(variables)):
        premisas = dict(zip(variables, valores))
        res = evaluar_reglas(premisas)
        filas.append({**{k: int(v) for k, v in premisas.items()}, **{k: int(v) for k, v in res.items()},
                      "Decisión": decidir(res)})
    return filas


def tabla_regla(clave):
    """Tabla de verdad de una sola regla, solo con sus variables."""
    regla = REGLAS[clave]
    filas = []
    for valores in product([False, True], repeat=len(regla["variables"])):
        premisas = dict(zip(regla["variables"], valores))
        completo = {k: premisas.get(k, False) for k in VARIABLES}
        filas.append({**{k: int(v) for k, v in premisas.items()}, f"{clave} = {regla['formula']}": int(regla["f"](completo))})
    return filas


# ------------------------------------------------------------
# RETO OPCIONAL: CONTRADICCIONES Y REDUNDANCIAS
# ------------------------------------------------------------

_ACCIONES_OPUESTAS = {frozenset({"permitir", "denegar"}), frozenset({"permitir", "inspeccionar"}),
                      frozenset({"inspeccionar", "denegar"})}


def analizar_reglas(reglas=None):
    """
    Recorre las 2^6 combinaciones y reporta:
      - reglas insatisfacibles (nunca se activan) o tautológicas;
      - conflictos: dos reglas con acciones opuestas activas a la vez
        (se resuelven con la precedencia de la decisión final);
      - redundancias: una regla equivalente a otra o que implica a otra
        con la misma acción.
    """
    reglas = reglas or REGLAS
    filas = [dict(zip(VARIABLES, v)) for v in product([False, True], repeat=len(VARIABLES))]
    valores = {k: [bool(r["f"](f)) for f in filas] for k, r in reglas.items()}
    hallazgos = []

    for k, vals in valores.items():
        if not any(vals):
            hallazgos.append({"tipo": "insatisfacible", "reglas": k, "detalle": f"{k} nunca se activa."})
        elif all(vals):
            hallazgos.append({"tipo": "tautología", "reglas": k, "detalle": f"{k} siempre se activa."})

    for a, b in combinations(reglas, 2):
        va, vb = valores[a], valores[b]
        ambas = [f for f, x, y in zip(filas, va, vb) if x and y]
        acciones = frozenset({reglas[a]["accion"], reglas[b]["accion"]})
        if va == vb:
            hallazgos.append({"tipo": "redundancia", "reglas": f"{a}, {b}",
                              "detalle": f"{a} y {b} son lógicamente equivalentes."})
        elif reglas[a]["accion"] == reglas[b]["accion"] and (
            all(y for x, y in zip(va, vb) if x) or all(x for x, y in zip(va, vb) if y)
        ):
            hallazgos.append({"tipo": "redundancia", "reglas": f"{a}, {b}",
                              "detalle": f"Una de las reglas implica a la otra con la misma acción ({reglas[a]['accion']})."})
        if ambas and acciones in _ACCIONES_OPUESTAS:
            ejemplo = "".join(k if v else f"¬{k}" for k, v in ambas[0].items())
            hallazgos.append({
                "tipo": "conflicto",
                "reglas": f"{a}, {b}",
                "detalle": (f"{a} ({reglas[a]['accion']}) y {b} ({reglas[b]['accion']}) se activan juntas en "
                            f"{len(ambas)} de {len(filas)} combinaciones (p. ej. {ejemplo}). "
                            "Se resuelve por precedencia: denegar > inspeccionar > permitir."),
            })

    # Observación de diseño: E se activa aunque el conductor no esté certificado.
    sin_cert = [f for f, x in zip(filas, valores.get("E", [])) if x and not f["S"]]
    if sin_cert:
        hallazgos.append({"tipo": "observación", "reglas": "E",
                          "detalle": "E puede activarse con S falso: se envía a inspección a un conductor sin "
                                     "certificación vigente; la inspección debe verificar la certificación."})
    return hallazgos


# ------------------------------------------------------------
# REGLAS PERSONALIZADAS (simulador)
# ------------------------------------------------------------

_NODOS_PERMITIDOS = (ast.Expression, ast.BoolOp, ast.UnaryOp, ast.And, ast.Or, ast.Not, ast.Name, ast.Load)


def compilar_expresion(texto):
    """
    Convierte una expresión como 'P and not Q or (R and H)' (también acepta
    ∧ ∨ ¬) en una función segura. Lanza ValueError con un mensaje claro.
    """
    limpio = (texto or "").replace("∧", " and ").replace("∨", " or ").replace("¬", " not ")
    if not limpio.strip():
        raise ValueError("Escribe una expresión, por ejemplo: P and not Q")
    try:
        arbol = ast.parse(limpio, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Expresión mal formada: {e.msg}") from e
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, _NODOS_PERMITIDOS):
            raise ValueError("Solo se permiten las variables P Q R S H C y los operadores and, or, not, ∧, ∨, ¬.")
        if isinstance(nodo, ast.Name) and nodo.id not in VARIABLES:
            raise ValueError(f"Variable desconocida: {nodo.id}. Usa {', '.join(VARIABLES)}.")
    codigo = compile(arbol, "<regla>", "eval")
    usadas = "".join(sorted({n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}, key="PQRSHC".index))
    return (lambda v: bool(eval(codigo, {"__builtins__": {}}, dict(v)))), usadas
