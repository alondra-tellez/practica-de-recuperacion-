# ============================================================
# PRACTICA 2
# TUTOR INTELIGENTE CON LLM  (versión modificada)
# ============================================================
#
# Objetivo:
# Crear un asistente especializado utilizando un modelo de
# lenguaje LLM ejecutado mediante Ollama.
#
# Cambios respecto al ejercicio original:
#
# 1. Nueva configuración del sistema: el asistente ya no es un
#    profesor de IA, ahora es un ASESOR EN SEGURIDAD VIAL Y
#    LOGÍSTICA DE TRANSPORTE DE CARGA.
# 2. Interfaz gráfica: ver tutor_gui.py
#        streamlit run tutor_gui.py
# 3. Resumen del historial: comando 'resumen' en consola y botón
#    "Resumen del historial" en la interfaz gráfica.
#
# Modelo:
# llama3.2
#
# ============================================================


# ------------------------------------------------------------
# 1. IMPORTAR LAS BIBLIOTECAS
# ------------------------------------------------------------

import os
from datetime import datetime

import ollama


# ------------------------------------------------------------
# 2. CONFIGURACIÓN DEL MODELO
# ------------------------------------------------------------

MODELO = os.getenv("OLLAMA_MODEL", "llama3.2")


# ------------------------------------------------------------
# 3. CONFIGURACIÓN DEL SISTEMA (NUEVA)
# ------------------------------------------------------------
#
# El mensaje "system" establece el comportamiento general
# que queremos que tenga nuestro asistente.
#
# ------------------------------------------------------------

mensaje_sistema = """
Eres "RutaSegura", un asesor experto en seguridad vial y
logística de transporte de carga en México.

Tu función es orientar a operadores de tractocamiones,
despachadores y estudiantes de logística.

Debes:

1. Responder siempre en español, de forma clara y amable.
2. Explicar los procedimientos paso a paso (por ejemplo:
   revisión previa al viaje, estiba de carga, manejo de
   materiales peligrosos, descanso del conductor).
3. Dar ejemplos prácticos tomados de situaciones reales de
   carretera, patios de maniobra y centros de distribución.
4. Cuando menciones normas, indica que el usuario debe
   verificar la versión vigente (por ejemplo, las NOM de la
   SCT) porque pueden cambiar.
5. Priorizar SIEMPRE la seguridad de las personas por encima
   de los tiempos de entrega.
6. Si la pregunta implica una emergencia (accidente, fuga,
   incendio, persona herida), indicar primero que llame al
   911 y luego dar recomendaciones generales.
7. Si no sabes algo, dilo con honestidad; no inventes datos,
   cifras ni normas.
8. Mantener las respuestas breves (máximo 250 palabras),
   salvo que el usuario pida más detalle.
"""


# ------------------------------------------------------------
# 4. PROMPT PARA RESUMIR EL HISTORIAL
# ------------------------------------------------------------

mensaje_resumen = """
Resume la conversación anterior para el usuario en español.
Usa este formato:

- Temas consultados: (lista breve)
- Recomendaciones clave: (máximo 5 viñetas)
- Pendientes o dudas abiertas: (si las hay)

No agregues información que no se haya mencionado.
"""


def crear_historial():
    """Crea el historial inicial con el mensaje del sistema."""
    return [{"role": "system", "content": mensaje_sistema}]


def preguntar(mensajes, modelo=MODELO, temperatura=0.4):
    """Envía el historial completo al LLM y devuelve la respuesta."""
    respuesta = ollama.chat(
        model=modelo,
        messages=mensajes,
        options={"temperature": temperatura},
    )
    return respuesta["message"]["content"]


def estadisticas_historial(mensajes):
    """Resumen local (sin LLM) del historial: siempre está disponible."""
    preguntas = [m["content"] for m in mensajes if m["role"] == "user"]
    respuestas = [m["content"] for m in mensajes if m["role"] == "assistant"]
    return {
        "preguntas": len(preguntas),
        "respuestas": len(respuestas),
        "palabras_usuario": sum(len(p.split()) for p in preguntas),
        "palabras_asistente": sum(len(r.split()) for r in respuestas),
        "ultimas_preguntas": preguntas[-5:],
    }


def resumir_historial(mensajes, modelo=MODELO):
    """Pide al LLM un resumen de la conversación (sin guardarlo en el historial)."""
    conversacion = [m for m in mensajes if m["role"] != "system"]
    if not conversacion:
        return "Todavía no hay conversación que resumir."
    texto = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in conversacion)
    return preguntar(
        [
            {"role": "system", "content": "Eres un asistente que resume conversaciones."},
            {"role": "user", "content": f"{mensaje_resumen}\n\nCONVERSACIÓN:\n{texto}"},
        ],
        modelo=modelo,
        temperatura=0.1,
    )


# ------------------------------------------------------------
# 5. PROGRAMA DE CONSOLA
# ------------------------------------------------------------

def main():
    mensajes = crear_historial()
    inicio = datetime.now()

    print("=" * 50)
    print("     RUTASEGURA - ASESOR DE SEGURIDAD VIAL (LLM)")
    print("=" * 50)
    print("Modelo utilizado:", MODELO)
    print()
    print("Escribe 'resumen' para ver un resumen del historial.")
    print("Escribe 'salir' para terminar.")
    print()

    while True:
        pregunta = input("Usuario: ").strip()
        if not pregunta:
            continue

        if pregunta.lower() in ("salir", "resumen"):
            datos = estadisticas_historial(mensajes)
            print()
            print("RESUMEN DEL HISTORIAL")
            print("-" * 50)
            print(f"Duración: {datetime.now() - inicio}".split(".")[0])
            print("Preguntas realizadas:", datos["preguntas"])
            try:
                print(resumir_historial(mensajes))
            except Exception as error:
                print("(No se pudo generar el resumen con el LLM:", error, ")")
                for p in datos["ultimas_preguntas"]:
                    print(" -", p)
            print("-" * 50)
            if pregunta.lower() == "salir":
                print("Sesión finalizada.")
                break
            continue

        mensajes.append({"role": "user", "content": pregunta})

        try:
            contenido = preguntar(mensajes)
        except Exception as error:
            print()
            print("ERROR AL CONECTARSE CON EL LLM")
            print("--------------------------------")
            print(error)
            print()
            print("Verifica que Ollama esté ejecutándose.")
            # Eliminamos la pregunta del historial porque no pudo ser procesada.
            mensajes.pop()
            continue

        mensajes.append({"role": "assistant", "content": contenido})

        print()
        print("RUTASEGURA:")
        print()
        print(contenido)
        print()
        print("-" * 50)


if __name__ == "__main__":
    main()


# python -m py_compile p02primertutor_llm.py (comprueba que la sintaxis de python es correcta)

        #       SYSTEM
        #         │
        #         ▼
        #    Comportamiento
        #         │
        #         ▼
# USER ────────► LLM
        #         │
        #         ▼
        #      ASSISTANT
