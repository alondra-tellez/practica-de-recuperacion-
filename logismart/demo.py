# ============================================================
# DATOS DE DEMOSTRACIÓN
# ============================================================
#
#   python -m logismart.demo            carga datos si las colecciones están vacías
#   python -m logismart.demo --reiniciar  borra las colecciones de LogiSmart y recarga
# ============================================================

import json
import random
import sys
from datetime import date, datetime, timedelta

from . import config
from .clasificador import extraer_entidades
from .riesgos import RIESGOS_DEMO
from .servicios import registrar_acceso

EMPRESAS = ["Transportes del Norte", "Transportes Bajío", "Fletes Rápidos del Golfo",
            "Logística Querétaro", "Carga Segura Express"]

# (camion_id, placa, empresa, autorizacion, días para vencer certificación, peso máx, tipo de carga)
_CAMIONES = [
    ("CAM-101", "TXA-482-B", "Transportes del Norte", True, 400, 40000, "general"),
    ("CAM-102", "JLM-215-C", "Transportes Bajío", True, 250, 36000, "material_peligroso"),
    ("CAM-103", "NLE-903-A", "Fletes Rápidos del Golfo", False, 300, 40000, "general"),
    ("CAM-104", "SON-118-D", "Transportes del Norte", True, -35, 40000, "general"),
    ("CAM-105", "QRO-660-F", "Logística Querétaro", True, 15, 30000, "general"),
    ("CAM-106", "PUE-307-K", "Transportes Bajío", True, 500, 40000, "general"),
    ("CAM-107", "GTO-845-M", "Fletes Rápidos del Golfo", True, 120, 42000, "general"),
    ("CAM-108", "MEX-532-R", "Carga Segura Express", True, 90, 40000, "valores"),
    ("CAM-109", "JAL-274-T", "Carga Segura Express", True, 200, 38000, "general"),
    ("CAM-110", "CHH-991-V", "Logística Querétaro", True, 25, 36000, "material_peligroso"),
    ("CAM-111", "VER-410-W", "Transportes del Norte", True, 330, 42000, "general"),
    ("CAM-112", "YUC-076-Z", "Transportes Bajío", True, 180, 36000, "material_peligroso"),
]


def camiones_demo():
    hoy = date.today()
    return [
        {
            "camion_id": cid, "placa": placa, "empresa": empresa, "autorizacion": aut,
            "certificacion_conductor": {
                # Privacidad: solo un alias, nunca el nombre real del conductor.
                "conductor_alias": f"Conductor {cid[-3:]}",
                "vigente": dias >= 0,
                "vencimiento": (hoy + timedelta(days=dias)).isoformat(),
            },
            "peso_maximo_kg": peso, "tipo_carga": carga, "fecha": datetime.now(),
        }
        for cid, placa, empresa, aut, dias, peso, carga in _CAMIONES
    ]


def cargar_correos():
    with open(config.RUTA_CORREOS, encoding="utf-8") as f:
        return json.load(f)


def _incidentes_demo():
    ahora = datetime.now()
    docs = []
    for c in cargar_correos():
        fecha = ahora - timedelta(days=c["dias_atras"], hours=random.Random(c["id"]).randint(0, 8))
        estado = "cerrado" if c["dias_atras"] > 14 else "en_atencion" if c["dias_atras"] > 6 else "nuevo"
        docs.append({
            "fecha": fecha, "asunto": c["asunto"], "remitente": c["remitente"], "correo_original": c["texto"],
            "clasificacion": {"categoria": c["categoria"], "prioridad": c["prioridad"],
                              "entidades": extraer_entidades(c["texto"], EMPRESAS),
                              "resumen": c["texto"].split(". ")[0][:200]},
            "fuente_clasificacion": "demo (etiqueta manual)", "requiere_revision_humana": False,
            "estado": estado,
            "historial": [{"fecha": fecha, "accion": "creado", "operador": "demo", "detalle": "dato de demostración"}]
            + ([{"fecha": fecha + timedelta(hours=2), "accion": f"estado → {estado}", "operador": "demo"}]
               if estado != "nuevo" else []),
        })
    return docs


def _accesos_demo(db, cfg):
    rng = random.Random(7)
    camiones = db.listar("camiones", orden=None)
    ahora = datetime.now()
    for _ in range(60):
        cam = rng.choice(camiones)
        momento = (ahora - timedelta(days=rng.randint(0, 34))).replace(hour=rng.randint(0, 23), minute=rng.randint(0, 59))
        momento = min(momento, ahora)
        peso = cam["peso_maximo_kg"] * rng.uniform(0.75, 1.12)
        registrar_acceso(db, cfg, rng.choice(["Operador A", "Operador B", "Operador C"]), camion=cam,
                         peso_kg=round(peso), material_peligroso=cam["tipo_carga"] == "material_peligroso",
                         momento=momento)
    # Caso de la pregunta de ejemplo: CAM-102 enviado a inspección hoy.
    cam102 = db.buscar_uno("camiones", {"camion_id": "CAM-102"})
    registrar_acceso(db, cfg, "Operador A", camion=cam102, peso_kg=34100, material_peligroso=True,
                     momento=ahora.replace(hour=10, minute=15) if ahora.hour >= 10 else ahora)


def colecciones_vacias(db):
    return all(db.contar(c) == 0 for c in ("camiones", "accesos", "incidentes", "riesgos_eticos"))


def reiniciar(db):
    for c in ("camiones", "accesos", "incidentes", "riesgos_eticos", "evaluaciones_llm", "notificaciones"):
        db.db[c].delete_many({})


def cargar_demo(db, cfg=None, forzar=False):
    """Carga los datos de demostración. Devuelve True si cargó algo."""
    cfg = cfg or db.leer_config()
    if forzar:
        reiniciar(db)
    elif not colecciones_vacias(db):
        return False
    if db.contar("camiones") == 0:
        db.insertar_varios("camiones", camiones_demo())
    if db.contar("riesgos_eticos") == 0:
        db.insertar_varios("riesgos_eticos", RIESGOS_DEMO)
    if db.contar("incidentes") == 0:
        db.insertar_varios("incidentes", _incidentes_demo())
    if db.contar("accesos") == 0:
        _accesos_demo(db, cfg)
    return True


if __name__ == "__main__":
    from .db import BaseDatos

    base = BaseDatos()
    print("Conexión:", base.descripcion, "|", base.error_conexion or "OK")
    cargado = cargar_demo(base, forzar="--reiniciar" in sys.argv)
    print("Datos de demostración cargados." if cargado else "Las colecciones ya tenían datos; no se cargó nada "
          "(usa --reiniciar para recargar).")
    for c in ("camiones", "accesos", "incidentes", "riesgos_eticos"):
        print(f"  {c}: {base.contar(c)}")
