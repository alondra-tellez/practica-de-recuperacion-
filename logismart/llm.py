# ============================================================
# CLIENTE DEL LLM LOCAL (Ollama)
# ============================================================
#
# Envoltura mínima sobre la biblioteca ollama que:
#   - mide la latencia de cada llamada;
#   - permite pedir salida estructurada (JSON Schema);
#   - registra prompt, respuesta, modelo y latencia en la
#     colección evaluaciones_llm.
# ============================================================

import json
import time
from datetime import datetime

import ollama

from . import config


class ErrorLLM(Exception):
    """El LLM no está disponible o no respondió."""


class ClienteLLM:
    def __init__(self, modelo, host=config.OLLAMA_HOST, timeout_s=90, temperatura=0.0, db=None):
        self.modelo = modelo
        self.temperatura = temperatura
        self.db = db
        self._cliente = ollama.Client(host=host, timeout=timeout_s)
        self._host = host

    def estado(self):
        """(disponible, modelos_instalados, mensaje)."""
        try:
            modelos = [m.model for m in ollama.Client(host=self._host, timeout=3).list().models]
        except Exception as e:  # noqa: BLE001
            return False, [], f"Ollama no responde en {self._host} ({type(e).__name__})."
        if not any(m == self.modelo or m.split(":")[0] == self.modelo for m in modelos):
            return False, modelos, f"El modelo '{self.modelo}' no está instalado. Ejecuta: ollama pull {self.modelo}"
        return True, modelos, f"Ollama listo con {self.modelo}"

    def chat(self, mensajes, formato=None):
        """Devuelve (texto, latencia_ms). Lanza ErrorLLM si falla."""
        inicio = time.perf_counter()
        try:
            respuesta = self._cliente.chat(
                model=self.modelo,
                messages=mensajes,
                format=formato,
                options={"temperature": self.temperatura},
            )
        except Exception as e:  # noqa: BLE001
            raise ErrorLLM(f"No se pudo consultar el modelo {self.modelo}: {e}") from e
        latencia = (time.perf_counter() - inicio) * 1000
        return respuesta["message"]["content"], latencia

    def registrar(self, tarea, prompt, respuesta, latencia_ms, valido=None, coincide_reglas=None, extra=None):
        """Guarda la interacción en evaluaciones_llm (si hay base de datos)."""
        if self.db is None:
            return
        try:
            self.db.insertar("evaluaciones_llm", {
                "fecha": datetime.now(),
                "tarea": tarea,
                "modelo": self.modelo,
                "prompt": prompt if isinstance(prompt, str) else json.dumps(prompt, ensure_ascii=False),
                "respuesta": respuesta,
                "latencia_ms": round(latencia_ms, 1),
                "json_valido": valido,
                "coincide_reglas": coincide_reglas,
                **(extra or {}),
            })
        except Exception:  # noqa: BLE001 - el registro nunca debe tumbar la operación principal
            pass
