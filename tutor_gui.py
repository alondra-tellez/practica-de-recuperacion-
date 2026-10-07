# ============================================================
# PRACTICA 2 - INTERFAZ GRÁFICA DEL TUTOR (Streamlit) · v2
# ============================================================
#
# Ejecutar con:
#     python -m streamlit run tutor_gui.py
#
# Misma lógica que p02primertutor_llm.py, con otra presentación:
#   - Tema oscuro y encabezado tipo tarjeta.
#   - Ajustes en un panel desplegable superior (sin barra lateral).
#   - Chat a la izquierda y panel de historial/resumen a la derecha.
# ============================================================

import json
from datetime import datetime

import ollama
import streamlit as st

from p02primertutor_llm import (
    MODELO,
    crear_historial,
    estadisticas_historial,
    mensaje_sistema,
    preguntar,
    resumir_historial,
)

st.set_page_config(page_title="RutaSegura · Asesor LLM", page_icon="🛣️", layout="wide",
                   initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=IBM+Plex+Sans:wght@400;600&display=swap');
html, body, p, label, input, textarea {font-family: 'IBM Plex Sans', sans-serif;}
h1, h2, h3 {font-family: 'Space Grotesk', sans-serif !important;}
[data-testid="stSidebar"], [data-testid="collapsedControl"] {display: none;}
.block-container {padding-top: 1.4rem; max-width: 1250px;}
.portada {background: linear-gradient(120deg, #13221d 0%, #16202c 100%); border: 1px solid #2a3038;
          border-radius: 16px; padding: 22px 26px; margin-bottom: 14px; display:flex; gap:18px; align-items:center;}
.portada .icono {font-size: 42px; background:#1fbf8f22; border-radius:14px; width:68px; height:68px;
                 display:grid; place-items:center;}
.portada h1 {margin:0; padding:0; font-size:1.9rem;}
.portada p {margin:2px 0 0 0; color:#c3c2b7;}
.dato {background:#1a1f26; border:1px solid #2a3038; border-radius:10px; padding:10px 14px; margin-bottom:8px;}
.dato .n {font-family:'Space Grotesk',sans-serif; font-size:1.6rem; font-weight:700; color:#1fbf8f;}
.dato .t {color:#9a9890; font-size:.75rem; text-transform:uppercase; letter-spacing:.1em;}
.ejemplo {color:#9a9890; font-size:.9rem;}
</style>
""", unsafe_allow_html=True)


def modelos_disponibles():
    """Lista los modelos instalados en Ollama; None si Ollama no responde."""
    try:
        return [m.model for m in ollama.list().models]
    except Exception:
        return None


if "mensajes" not in st.session_state:
    st.session_state.mensajes = crear_historial()
    st.session_state.inicio = datetime.now()
    st.session_state.resumen = None

modelos = modelos_disponibles()

st.markdown("<div class='portada'><div class='icono'>🛣️</div><div><h1>RutaSegura</h1>"
            "<p>Asesor de seguridad vial y logística de transporte de carga · LLM local con Ollama</p></div></div>",
            unsafe_allow_html=True)

# ------------------------------------------------------------
# AJUSTES (panel superior)
# ------------------------------------------------------------

with st.expander("⚙️ Ajustes del modelo", expanded=modelos is None or not modelos):
    a, b = st.columns(2)
    if modelos is None:
        a.error("Ollama no responde. Instálalo desde ollama.com y ejecuta `ollama pull llama3.2`.")
        modelo = a.text_input("Modelo", MODELO)
    elif not modelos:
        a.warning("Ollama funciona pero no hay modelos. Ejecuta `ollama pull llama3.2`.")
        modelo = a.text_input("Modelo", MODELO)
    else:
        indice = next((i for i, m in enumerate(modelos) if m.startswith(MODELO)), 0)
        modelo = a.selectbox("Modelo", modelos, index=indice)
    temperatura = b.slider("Creatividad (temperatura)", 0.0, 1.0, 0.4, 0.1)
    st.code(mensaje_sistema.strip(), language="markdown")

datos = estadisticas_historial(st.session_state.mensajes)
conversacion = [m for m in st.session_state.mensajes if m["role"] != "system"]
chat, panel = st.columns([2.3, 1], gap="large")

# ------------------------------------------------------------
# PANEL DE HISTORIAL Y RESUMEN
# ------------------------------------------------------------

with panel:
    st.markdown("### 🧾 Tu historial")
    minutos = int((datetime.now() - st.session_state.inicio).total_seconds() // 60)
    c1, c2 = st.columns(2)
    c1.markdown(f"<div class='dato'><div class='n'>{datos['preguntas']}</div><div class='t'>Preguntas</div></div>",
                unsafe_allow_html=True)
    c2.markdown(f"<div class='dato'><div class='n'>{minutos}</div><div class='t'>Minutos</div></div>",
                unsafe_allow_html=True)

    if st.button("📋 Generar resumen", width="stretch", type="primary", disabled=datos["preguntas"] == 0):
        with st.spinner("Generando resumen..."):
            try:
                st.session_state.resumen = resumir_historial(st.session_state.mensajes, modelo)
            except Exception as error:
                st.session_state.resumen = (
                    f"_No se pudo usar el LLM ({error}). Resumen local:_\n\n"
                    + "\n".join(f"- {p}" for p in datos["ultimas_preguntas"])
                )
    if st.session_state.resumen:
        with st.container(border=True):
            st.markdown(st.session_state.resumen)
            st.caption(f"{datos['palabras_usuario']} palabras tuyas · {datos['palabras_asistente']} del asesor")
    elif datos["ultimas_preguntas"]:
        st.caption("Últimas preguntas:")
        for p in datos["ultimas_preguntas"]:
            st.markdown(f"<div class='ejemplo'>• {p}</div>", unsafe_allow_html=True)

    st.download_button(
        "⬇️ Descargar conversación",
        json.dumps(conversacion, ensure_ascii=False, indent=2),
        file_name=f"conversacion_{datetime.now():%Y%m%d_%H%M}.json",
        mime="application/json",
        width="stretch",
        disabled=not conversacion,
    )
    if st.button("🗑️ Nueva conversación", width="stretch"):
        st.session_state.clear()
        st.rerun()

# ------------------------------------------------------------
# CHAT
# ------------------------------------------------------------

with chat:
    if not conversacion:
        st.markdown("<div class='ejemplo'>Prueba con: <i>¿Qué reviso antes de un viaje largo?</i> · "
                    "<i>¿Cómo transporto gas LP de forma segura?</i> · <i>¿Cuántas horas debo descansar?</i></div>",
                    unsafe_allow_html=True)
    for m in conversacion:
        with st.chat_message(m["role"], avatar="🧑‍✈️" if m["role"] == "user" else "🛣️"):
            st.markdown(m["content"])

pregunta = st.chat_input("Escribe tu pregunta...")
if pregunta:
    st.session_state.mensajes.append({"role": "user", "content": pregunta})
    with chat:
        with st.chat_message("user", avatar="🧑‍✈️"):
            st.markdown(pregunta)
        with st.chat_message("assistant", avatar="🛣️"):
            with st.spinner("Pensando..."):
                try:
                    contenido = preguntar(st.session_state.mensajes, modelo, temperatura)
                except Exception as error:
                    # Igual que en consola: quitamos la pregunta que no se pudo procesar.
                    st.session_state.mensajes.pop()
                    st.error(f"No pude conectarme con el LLM: {error}\n\nVerifica que Ollama esté ejecutándose.")
                    st.stop()
            st.markdown(contenido)
    st.session_state.mensajes.append({"role": "assistant", "content": contenido})
    st.rerun()
