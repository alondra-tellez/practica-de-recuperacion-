# ============================================================
# EXPERIMENTO: REGLAS vs LLM vs HÍBRIDO
# ============================================================
#
#   python -m logismart.experimento [modelo]
#
# Sobre el conjunto de correos etiquetados a mano (data/correos_etiquetados.json)
# mide para cada método:
#   - exactitud de categoría, de prioridad y de ambas;
#   - matriz de confusión de categoría;
#   - latencia media y p95;
#   - exactitud por estilo de redacción (formal / informal) -> evidencia de sesgo;
#   - subestimación de prioridad (casos peligrosos: predicción < etiqueta).
# Guarda el resultado en reportes/experimento_*.json y .md
# ============================================================

import json
import statistics
import sys
import time
from datetime import datetime

from . import config
from .clasificador import clasificar_con_llm, clasificar_por_reglas, fusionar
from .demo import EMPRESAS, cargar_correos

METODOS = ["reglas", "llm", "hibrido"]


def _matriz(etiquetas, predicciones, clases):
    matriz = {real: {pred: 0 for pred in clases} for real in clases}
    for real, pred in zip(etiquetas, predicciones):
        matriz[real][pred if pred in clases else "INVALIDO"] += 1
    return matriz


def _p95(valores):
    if not valores:
        return None
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, int(round(0.95 * (len(ordenados) - 1))))]


def ejecutar(cliente=None, reintentos=2, progreso=None):
    """
    cliente: ClienteLLM o None (en ese caso solo se evalúan reglas e híbrido
    degradado a reglas, y se reporta el LLM como no disponible).
    progreso: función opcional (i, total) para la barra de progreso de la GUI.
    """
    correos = cargar_correos()
    filas = []
    for i, c in enumerate(correos, start=1):
        r = clasificar_por_reglas(c["texto"], EMPRESAS)
        llm, info, lat_llm = None, {"error": "sin cliente LLM", "intentos": 0}, None
        if cliente is not None:
            inicio = time.perf_counter()
            llm, info = clasificar_con_llm(c["texto"], cliente, reintentos)
            lat_llm = (time.perf_counter() - inicio) * 1000
        llm_d = llm.model_dump() if llm else None
        inicio = time.perf_counter()
        h = fusionar(r, llm_d)
        lat_h = (lat_llm or 0) + r["latencia_ms"] + (time.perf_counter() - inicio) * 1000
        filas.append({
            "id": c["id"], "estilo": c["estilo"], "real_cat": c["categoria"], "real_prio": c["prioridad"],
            "reglas_cat": r["categoria"], "reglas_prio": r["prioridad"], "reglas_ms": r["latencia_ms"],
            "llm_cat": llm_d["categoria"] if llm_d else "INVALIDO",
            "llm_prio": llm_d["prioridad"] if llm_d else "INVALIDO",
            "llm_ms": lat_llm, "llm_intentos": info["intentos"], "llm_error": info["error"],
            "hibrido_cat": h["categoria"], "hibrido_prio": h["prioridad"], "hibrido_ms": lat_h,
            "revision_humana": h["requiere_revision_humana"],
        })
        if progreso:
            progreso(i, len(correos))

    clases = config.CATEGORIAS + ["INVALIDO"]
    rango = {p: n for n, p in enumerate(config.PRIORIDADES)}
    resumen = {}
    for m in METODOS:
        if m == "llm" and cliente is None:
            resumen[m] = {"disponible": False}
            continue
        n = len(filas)
        ok_cat = [f[f"{m}_cat"] == f["real_cat"] for f in filas]
        ok_prio = [f[f"{m}_prio"] == f["real_prio"] for f in filas]
        latencias = [f[f"{m}_ms"] for f in filas if f[f"{m}_ms"] is not None]
        por_estilo = {}
        for estilo in ("formal", "informal"):
            idx = [i for i, f in enumerate(filas) if f["estilo"] == estilo]
            por_estilo[estilo] = {
                "n": len(idx),
                "exactitud_categoria": round(sum(ok_cat[i] for i in idx) / len(idx), 3) if idx else None,
                "exactitud_prioridad": round(sum(ok_prio[i] for i in idx) / len(idx), 3) if idx else None,
            }
        subestimadas = [f["id"] for f in filas
                        if f[f"{m}_prio"] in rango and rango[f[f"{m}_prio"]] < rango[f["real_prio"]]]
        resumen[m] = {
            "disponible": True,
            "n": n,
            "exactitud_categoria": round(sum(ok_cat) / n, 3),
            "exactitud_prioridad": round(sum(ok_prio) / n, 3),
            "exactitud_ambas": round(sum(a and b for a, b in zip(ok_cat, ok_prio)) / n, 3),
            "latencia_media_ms": round(statistics.mean(latencias), 2) if latencias else None,
            "latencia_p95_ms": round(_p95(latencias), 2) if latencias else None,
            "prioridad_subestimada": subestimadas,
            "por_estilo": por_estilo,
            "matriz_confusion": _matriz([f["real_cat"] for f in filas], [f[f"{m}_cat"] for f in filas], clases),
        }
    if cliente is not None:
        resumen["llm"]["json_invalido_final"] = sum(1 for f in filas if f["llm_cat"] == "INVALIDO")
        resumen["llm"]["reintentos_usados"] = sum(max(0, f["llm_intentos"] - 1) for f in filas)
    resumen["hibrido"]["marcados_revision_humana"] = sum(f["revision_humana"] for f in filas)

    return {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "modelo": cliente.modelo if cliente else None,
        "n_correos": len(filas),
        "resumen": resumen,
        "filas": filas,
    }


def a_markdown(res):
    lineas = [f"# Experimento de clasificación — {res['fecha']}", "",
              f"Correos etiquetados: **{res['n_correos']}** · Modelo LLM: **{res['modelo'] or 'no disponible'}**", "",
              "| Método | Exactitud categoría | Exactitud prioridad | Ambas | Latencia media (ms) | p95 (ms) | Prioridad subestimada |",
              "|---|---|---|---|---|---|---|"]
    for m in METODOS:
        r = res["resumen"][m]
        if not r.get("disponible"):
            lineas.append(f"| {m} | — | — | — | — | — | LLM no disponible |")
            continue
        lineas.append(f"| {m} | {r['exactitud_categoria']:.1%} | {r['exactitud_prioridad']:.1%} | {r['exactitud_ambas']:.1%} "
                      f"| {r['latencia_media_ms']} | {r['latencia_p95_ms']} | {len(r['prioridad_subestimada'])} |")
    lineas += ["", "## Exactitud de categoría por estilo de redacción", "", "| Método | Formal | Informal |", "|---|---|---|"]
    for m in METODOS:
        r = res["resumen"][m]
        if r.get("disponible"):
            pe = r["por_estilo"]
            lineas.append(f"| {m} | {pe['formal']['exactitud_categoria']:.1%} (n={pe['formal']['n']}) | "
                          f"{pe['informal']['exactitud_categoria']:.1%} (n={pe['informal']['n']}) |")
    for m in METODOS:
        r = res["resumen"][m]
        if not r.get("disponible"):
            continue
        clases = [c for c in r["matriz_confusion"] if any(r["matriz_confusion"][c].values())
                  or any(r["matriz_confusion"][x][c] for x in r["matriz_confusion"])]
        lineas += ["", f"## Matriz de confusión — {m} (filas = real, columnas = predicción)", "",
                   "| real \\ pred | " + " | ".join(clases) + " |", "|---" * (len(clases) + 1) + "|"]
        for real in clases:
            lineas.append(f"| **{real}** | " + " | ".join(str(r["matriz_confusion"][real][p]) for p in clases) + " |")
    errores = [f for f in res["filas"] if f["reglas_cat"] != f["real_cat"] or f["reglas_prio"] != f["real_prio"]]
    lineas += ["", "## Errores del clasificador por reglas", "", "| id | estilo | real | reglas |", "|---|---|---|---|"]
    lineas += [f"| {f['id']} | {f['estilo']} | {f['real_cat']}/{f['real_prio']} | {f['reglas_cat']}/{f['reglas_prio']} |"
               for f in errores]
    return "\n".join(lineas) + "\n"


def guardar(res):
    config.RUTA_REPORTES.mkdir(exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta = config.RUTA_REPORTES / f"experimento_{marca}"
    ruta.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    ruta.with_suffix(".md").write_text(a_markdown(res), encoding="utf-8")
    return ruta


if __name__ == "__main__":
    from .db import BaseDatos
    from .llm import ClienteLLM

    modelo = sys.argv[1] if len(sys.argv) > 1 else config.CONFIG_DEFECTO["modelo_ollama"]
    base = BaseDatos()
    cliente = ClienteLLM(modelo, db=base)
    disponible, _, mensaje = cliente.estado()
    print(mensaje)
    res = ejecutar(cliente if disponible else None,
                   progreso=lambda i, n: print(f"\r  {i}/{n}", end="", flush=True))
    print()
    ruta = guardar(res)
    print(a_markdown(res))
    print(f"Resultados guardados en {ruta}.json / .md")
