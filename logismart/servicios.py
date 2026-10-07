# ============================================================
# SERVICIOS DE APLICACIÓN
# ============================================================
#
# Une la lógica de negocio (reglas, clasificador) con la
# persistencia. La GUI solo llama a estas funciones.
# ============================================================

import re
from datetime import datetime

from .reglas import evaluar_camion, premisas_desde_camion

RE_PLACA_VALIDA = re.compile(r"^[A-Z]{3}-\d{3}-[A-Z]$")
RE_CAMION_VALIDO = re.compile(r"^CAM-\d{3}$")


def validar_camion(c):
    errores = []
    if not RE_PLACA_VALIDA.match(c.get("placa", "")):
        errores.append("La placa debe tener el formato ABC-123-D.")
    if not RE_CAMION_VALIDO.match(c.get("camion_id", "")):
        errores.append("El identificador debe tener el formato CAM-123.")
    if not str(c.get("empresa", "")).strip():
        errores.append("La empresa es obligatoria.")
    if float(c.get("peso_maximo_kg", 0) or 0) <= 0:
        errores.append("El peso máximo debe ser mayor que cero.")
    return errores


def registrar_acceso(db, cfg, operador, premisas=None, origen=None, camion=None, peso_kg=None,
                     material_peligroso=False, momento=None):
    """
    Evalúa y guarda un acceso en la bitácora.
    - Con 'camion' se derivan las premisas del catálogo y la báscula.
    - Sin 'camion' se usan las premisas P/Q/R/S/H/C capturadas manualmente.
    """
    if not (operador or "").strip():
        raise ValueError("Indica el nombre del operador en la barra lateral antes de registrar accesos.")
    momento = momento or datetime.now()
    if camion is not None:
        premisas, origen = premisas_desde_camion(camion, peso_kg, material_peligroso, momento, cfg)
    resultado = evaluar_camion(**premisas, origen=origen)
    registro = {
        "fecha": momento,
        "operador": operador.strip(),
        "camion_id": camion.get("camion_id") if camion else "manual",
        "placa": camion.get("placa") if camion else "manual",
        "empresa": camion.get("empresa") if camion else None,
        "peso_kg": peso_kg,
        "premisas": resultado["premisas"],
        "resultados": resultado["resultados"],
        "A": resultado["resultados"]["A"],
        "E": resultado["resultados"]["E"],
        "decision": resultado["decision"],
        "premisas_determinantes": resultado["premisas_determinantes"],
        "explicacion": resultado["explicacion"],
        "origen_premisas": origen or {},
    }
    registro["_id"] = db.insertar("accesos", registro)
    return registro


def guardar_incidente(db, cfg, correo, asunto, remitente, clasificacion, operador, editado=False):
    doc = {
        "fecha": datetime.now(),
        "asunto": asunto.strip() or "(sin asunto)",
        "remitente": remitente.strip(),
        "correo_original": correo,
        "clasificacion": {k: clasificacion[k] for k in ("categoria", "prioridad", "entidades", "resumen")},
        "fuente_clasificacion": clasificacion.get("fuente"),
        "requiere_revision_humana": clasificacion.get("requiere_revision_humana", False),
        "motivo_revision": clasificacion.get("motivo_revision", ""),
        "detalle_clasificadores": {"reglas": clasificacion.get("reglas"), "llm": clasificacion.get("llm"),
                                   "llm_error": clasificacion.get("llm_error")},
        "estado": "nuevo",
        "historial": [{"fecha": datetime.now(), "accion": "creado", "operador": operador,
                       "detalle": "clasificación editada por el operador" if editado else "clasificación automática"}],
    }
    doc["_id"] = db.insertar("incidentes", doc)
    if doc["clasificacion"]["prioridad"] in ("ALTA", "CRITICA"):
        notificar(db, cfg, f"[{doc['clasificacion']['prioridad']}] {doc['asunto']}",
                  f"Incidente {doc['_id']}: {doc['clasificacion']['resumen']}")
    return doc


def notificar(db, cfg, asunto, mensaje):
    """
    Envío de correo a soporte. En modo simulación (por defecto) solo se
    registra en la colección 'notificaciones', como en el código original.
    """
    registro = {"fecha": datetime.now(), "para": cfg["correo_soporte"], "asunto": asunto, "mensaje": mensaje,
                "simulado": cfg["modo_simulacion_correo"]}
    if not cfg["modo_simulacion_correo"]:
        # Aquí iría el envío real por SMTP o API de correo; no se implementa para no
        # mandar correos por accidente durante la práctica.
        registro["nota"] = "Envío real no configurado; se registró sin enviar."
    db.insertar("notificaciones", registro)
    return registro
