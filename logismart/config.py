# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================
#
# Las credenciales se leen del archivo .env (nunca se suben a Git).
# Los parámetros operativos (modelo, umbrales, modo simulación)
# tienen valores por defecto aquí y se pueden cambiar desde la GUI;
# los cambios se guardan en la colección "configuracion".
# ============================================================

import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

# Algunas instalaciones de Windows dejan variables de certificados
# apuntando a rutas que ya no existen; eso rompe las conexiones TLS.
for _var in ("CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"):
    if os.environ.get(_var) and not os.path.exists(os.environ[_var]):
        os.environ.pop(_var)


def _env(clave, defecto=""):
    return (os.getenv(clave) or defecto).strip()


MONGO_USER = _env("Mongo_User")
MONGO_PASSWORD = _env("Mongo_Password")
MONGO_CLUSTER = _env("Mongo_Cluster")
MONGO_DB = _env("LOGISMART_DB", _env("Mongo_BD", "logismart"))
MONGO_URI = _env("MONGO_URI")  # opcional: p. ej. mongodb://localhost:27017 para Compass local

OLLAMA_HOST = _env("OLLAMA_HOST", "http://localhost:11434")

RUTA_CORREOS = RAIZ / "data" / "correos_etiquetados.json"
RUTA_REPORTES = RAIZ / "reportes"

CATEGORIAS = [
    "accidente",
    "material_peligroso",
    "sobrepeso",
    "seguridad",
    "falla_equipo",
    "documentacion",
    "otro",
]
PRIORIDADES = ["BAJA", "MEDIA", "ALTA", "CRITICA"]
ESTADOS_INCIDENTE = ["nuevo", "en_atencion", "cerrado"]

CONFIG_DEFECTO = {
    "modelo_ollama": _env("OLLAMA_MODEL", "llama3.2"),
    "temperatura": 0.0,
    "reintentos_llm": 2,
    "timeout_llm_s": 90,
    "usar_llm": True,
    # Motor de reglas
    "tolerancia_peso_pct": 0.0,
    "hora_inicio_restriccion": 22,
    "hora_fin_restriccion": 6,
    "dias_alerta_certificacion": 30,
    # Riesgos éticos (puntaje = probabilidad x impacto, escala 1-25)
    "umbral_riesgo_critico": 15,
    "umbral_riesgo_alto": 8,
    # Correo
    "modo_simulacion_correo": True,
    "correo_soporte": "soporte@logismart.com",
}
