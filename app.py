# ============================================================
# LOGISMART · INTERFAZ GRÁFICA (Streamlit)
# ============================================================
#
#   streamlit run app.py
#
# Capa de presentación: solo llama a los módulos de logismart/
#   db.py           persistencia (MongoDB Atlas / local / memoria)
#   reglas.py       motor de lógica proposicional
#   clasificador.py clasificador híbrido reglas + LLM
#   asistente.py    chat explicativo con RAG
#   riesgos.py      matriz de riesgos éticos
#   reportes.py     exportación PDF / CSV / JSON
#   experimento.py  evaluación reglas vs LLM vs híbrido
# ============================================================

import json
import random
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from logismart import config, demo, experimento, reportes
from logismart.asistente import responder
from logismart.clasificador import clasificar_hibrido
from logismart.db import BaseDatos, ErrorBaseDatos
from logismart.llm import ClienteLLM, ErrorLLM
from logismart.reglas import (DECISIONES, REGLAS, VARIABLES, analizar_reglas, compilar_expresion,
                              evaluar_camion, evaluar_reglas, decidir, tabla_regla, tabla_verdad)
from logismart.riesgos import CATEGORIAS_RIESGO, ESCALA, nivel, nuevo_riesgo, puntaje, validar
from logismart.servicios import guardar_incidente, notificar, registrar_acceso, validar_camion

st.set_page_config(page_title="LogiSmart · Sala de control", page_icon="🛰️", layout="wide",
                   initial_sidebar_state="collapsed")

# Paleta validada (guía dataviz), pasos para superficie oscura: categóricos en orden fijo
# y colores de estado reservados (siempre acompañados de ícono y texto).
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
COLOR_CATEGORIA = dict(zip(config.CATEGORIAS, SERIES))
ESTADO = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
COLOR_DECISION = {"ACCESO": ESTADO["good"], "INSPECCION": ESTADO["warning"], "DENEGADO": ESTADO["critical"]}
COLOR_NIVEL = {"BAJO": ESTADO["good"], "MEDIO": ESTADO["warning"], "ALTO": ESTADO["serious"], "CRÍTICO": ESTADO["critical"]}
ICONO_NIVEL = {"BAJO": "▲", "MEDIO": "▲▲", "ALTO": "▲▲▲", "CRÍTICO": "⛔"}
ICONO_PRIORIDAD = {"BAJA": "◽", "MEDIA": "◼", "ALTA": "◆", "CRITICA": "⛔"}
SECUENCIAL = ["#1a1f26", "#184f95", "#256abf", "#3987e5", "#86b6ef"]

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono&display=swap');
html, body, [class*="css"], .stMarkdown, p, label, input, textarea {font-family: 'IBM Plex Sans', sans-serif;}
h1, h2, h3, h4 {font-family: 'Space Grotesk', sans-serif !important; letter-spacing: -.01em;}
code, pre {font-family: 'IBM Plex Mono', monospace !important;}
.block-container {padding-top: 1.4rem; max-width: 1400px;}
[data-testid="stSidebar"], [data-testid="collapsedControl"] {display: none;}

.marca {display:flex; align-items:center; gap:12px;}
.marca .logo {width:42px; height:42px; border-radius:10px; display:grid; place-items:center; font-size:22px;
              background: linear-gradient(135deg, #1fbf8f, #3987e5);}
.marca h1 {font-size:1.45rem; margin:0; padding:0;}
.marca small {color:#9a9890; text-transform:uppercase; letter-spacing:.12em; font-size:.68rem;}
.chip {display:inline-flex; align-items:center; gap:6px; padding:5px 12px; border-radius:8px; font-size:.82rem;
       background:#1a1f26; border:1px solid #2a3038; margin:2px 6px 2px 0; color:#e6e4df;}
.chip .punto {width:8px; height:8px; border-radius:50%;}

.kpi {background:#1a1f26; border:1px solid #2a3038; border-left:4px solid var(--acento); border-radius:10px;
      padding:14px 16px; height:100%;}
.kpi .etq {color:#9a9890; font-size:.72rem; text-transform:uppercase; letter-spacing:.1em;}
.kpi .val {font-family:'Space Grotesk',sans-serif; font-size:2.1rem; font-weight:700; line-height:1.1; margin-top:4px;}
.kpi .det {color:#c3c2b7; font-size:.8rem; margin-top:2px;}

.tl-wrap {display:flex; gap:20px; align-items:center; background:#1a1f26; border:1px solid #2a3038;
          border-radius:14px; padding:16px 20px; margin-bottom:10px;}
.tl {background:#0b0d10; border-radius:14px; padding:10px 9px; display:flex; flex-direction:column; gap:8px;
     border:2px solid #2a3038;}
.luz {width:30px; height:30px; border-radius:50%; background:#2a3038; opacity:.45;}
.luz.on {opacity:1; box-shadow:0 0 18px 4px var(--brillo);}
.tl-titulo {font-family:'Space Grotesk',sans-serif; font-size:1.7rem; font-weight:700;}
.tl-sub {color:#c3c2b7; font-family:'IBM Plex Mono',monospace; font-size:.85rem;}

.pastilla {display:inline-block; padding:4px 11px; border-radius:6px; margin:2px 5px 2px 0;
           font-family:'IBM Plex Mono',monospace; font-size:.85rem; border:1px solid #2a3038; background:#1a1f26;}
.pastilla.v {border-color:#1fbf8f; color:#7ee0bf;} .pastilla.f {color:#8a887f;}
div[data-testid="stPills"] button {font-family:'Space Grotesk',sans-serif;}
</style>
""", unsafe_allow_html=True)


def kpi(columna, etiqueta, valor, detalle="", acento="#1fbf8f"):
    columna.markdown(f"<div class='kpi' style='--acento:{acento}'><div class='etq'>{etiqueta}</div>"
                     f"<div class='val'>{valor}</div><div class='det'>{detalle}</div></div>", unsafe_allow_html=True)


def figura(fig, alto=340):
    """Estilo común de las gráficas: fondo transparente, rejilla discreta, leyenda arriba."""
    fig.update_layout(height=alto, margin=dict(l=0, r=0, t=30, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(family="IBM Plex Sans", color="#c3c2b7"),
                      legend=dict(orientation="h", y=1.12, x=0, title_text=""))
    fig.update_xaxes(gridcolor="#2a3038", zeroline=False)
    fig.update_yaxes(gridcolor="#2a3038", zeroline=False)
    return fig


# ------------------------------------------------------------
# RECURSOS COMPARTIDOS
# ------------------------------------------------------------

@st.cache_resource(show_spinner="Conectando con MongoDB...")
def obtener_db():
    base = BaseDatos()
    if demo.colecciones_vacias(base):
        demo.cargar_demo(base)
    return base


@st.cache_data(ttl=30, show_spinner=False)
def estado_ollama(modelo):
    return ClienteLLM(modelo).estado()


@contextmanager
def manejo_errores(contexto="la operación"):
    """Muestra errores de forma amigable sin detener toda la aplicación."""
    try:
        yield
    except (ErrorBaseDatos, ValueError, ErrorLLM) as e:
        st.error(f"⚠️ {e}")
    except Exception as e:  # noqa: BLE001
        if type(e).__name__ in ("RerunException", "StopException"):
            raise
        st.error(f"⚠️ Ocurrió un error inesperado durante {contexto}. Intenta de nuevo; si persiste, revisa la consola.")
        with st.expander("Detalle técnico"):
            st.exception(e)


def rango_fechas(clave, dias=30):
    hoy = date.today()
    valor = st.date_input("Periodo", (hoy - timedelta(days=dias), hoy), max_value=hoy, key=clave, format="DD/MM/YYYY")
    if isinstance(valor, (tuple, list)) and len(valor) == 2:
        return datetime.combine(valor[0], time.min), datetime.combine(valor[1], time.max)
    st.caption("Selecciona fecha inicial y final.")
    return None, None


def fmt_fecha(v):
    return v.strftime("%d/%m/%Y %H:%M") if isinstance(v, datetime) else str(v or "")


def semaforo(decision, subtitulo=""):
    d = DECISIONES[decision]
    texto = {"ACCESO": "Acceso permitido", "INSPECCION": "Enviar a inspección", "DENEGADO": "Acceso denegado"}[decision]
    luces = "".join(
        f"<span class='luz{' on' if decision == dec else ''}' style='background:{COLOR_DECISION[dec]};"
        f"--brillo:{COLOR_DECISION[dec]}88'></span>" for dec in ("DENEGADO", "INSPECCION", "ACCESO"))
    st.markdown(f"<div class='tl-wrap'><div class='tl'>{luces}</div><div><div class='tl-titulo' "
                f"style='color:{COLOR_DECISION[decision]}'>{d['semaforo']} {texto}</div>"
                f"<div class='tl-sub'>{subtitulo}</div></div></div>", unsafe_allow_html=True)


def mostrar_resultado_acceso(res):
    semaforo(res["decision"], f"Decisión = {DECISIONES[res['decision']]['formula']}")
    pastillas = "".join(
        f"<span class='pastilla {'v' if res['resultados'][k] else 'f'}'>{k} = {'V' if res['resultados'][k] else 'F'}</span>"
        for k in REGLAS)
    st.markdown(pastillas, unsafe_allow_html=True)
    st.markdown("**Explicación paso a paso**")
    st.code("\n".join(res["explicacion"]), language=None)


db = obtener_db()
if "cfg" not in st.session_state:
    st.session_state.cfg = db.leer_config()
cfg = st.session_state.cfg
ollama_ok, modelos_instalados, ollama_msg = estado_ollama(cfg["modelo_ollama"])
cliente_llm = (ClienteLLM(cfg["modelo_ollama"], timeout_s=cfg["timeout_llm_s"], temperatura=cfg["temperatura"], db=db)
               if cfg["usar_llm"] and ollama_ok else None)

# ------------------------------------------------------------
# BARRA SUPERIOR (marca, estado, operador y navegación)
# ------------------------------------------------------------

PAGINAS = ["📊 Panel de control", "🚦 Control de acceso", "🔀 Tablas de verdad", "📥 Incidentes",
           "💬 Asistente", "⚖️ Riesgos éticos", "📄 Reportes", "🚛 Camiones y datos", "⚙️ Configuración"]

marca, estado_col, operador_col = st.columns([2.2, 3, 1.4], vertical_alignment="center")
marca.markdown("<div class='marca'><div class='logo'>🛰️</div><div><small>Sala de control</small>"
               "<h1>LogiSmart</h1></div></div>", unsafe_allow_html=True)
color_db = ESTADO["critical"] if db.modo == "memoria" else ESTADO["good"]
if not cfg["usar_llm"]:
    color_llm, texto_llm = "#8a887f", "LLM desactivado · solo reglas"
elif ollama_ok:
    color_llm, texto_llm = ESTADO["good"], ollama_msg
else:
    color_llm, texto_llm = ESTADO["warning"], "LLM no disponible · respaldo por reglas"
estado_col.markdown(
    f"<span class='chip'><span class='punto' style='background:{color_db}'></span>🗄️ {db.descripcion}</span>"
    f"<span class='chip'><span class='punto' style='background:{color_llm}'></span>🤖 {texto_llm}</span>",
    unsafe_allow_html=True)
operador = operador_col.text_input("Operador", st.session_state.get("operador", ""), placeholder="👤 Tu nombre",
                                   label_visibility="collapsed")
st.session_state.operador = operador
if db.modo == "memoria":
    a, b = st.columns([5, 1])
    a.error(f"Sin conexión a MongoDB ({db.error_conexion or 'sin detalle'}). Los cambios se perderán al cerrar.")
    if b.button("🔄 Reintentar conexión"):
        obtener_db.clear()
        st.rerun()
elif cfg["usar_llm"] and not ollama_ok:
    st.caption(f"🤖 {ollama_msg}")

pagina = st.pills("Navegación", PAGINAS, default=PAGINAS[0], key="nav", label_visibility="collapsed") or PAGINAS[0]
st.divider()

# ============================================================
# 1. PANEL DE CONTROL
# ============================================================

if pagina == PAGINAS[0]:
    st.header("📊 Panel de control")
    with manejo_errores("la carga del panel"):
        desde, hasta = rango_fechas("panel_fechas")
        if desde:
            filtro = {"fecha": {"$gte": desde, "$lte": hasta}}
            accesos = db.listar("accesos", filtro)
            incidentes = db.listar("incidentes", filtro)
            riesgos = db.listar("riesgos_eticos", orden=None)
            abiertos = [i for i in incidentes if i.get("estado") != "cerrado"]
            criticos = [r for r in riesgos if puntaje(r, True) >= cfg["umbral_riesgo_critico"]]
            criticos_inh = [r for r in riesgos if puntaje(r) >= cfg["umbral_riesgo_critico"]]

            inspecciones = sum(a["decision"] == "INSPECCION" for a in accesos)
            c = st.columns(5)
            kpi(c[0], "Camiones atendidos", len({a["camion_id"] for a in accesos}), "unidades distintas", "#3987e5")
            kpi(c[1], "Accesos registrados", len(accesos),
                f"{sum(a['decision'] == 'ACCESO' for a in accesos)} permitidos", ESTADO["good"])
            kpi(c[2], "Enviados a inspección", inspecciones,
                f"{inspecciones / len(accesos):.0%} del total" if accesos else "sin accesos", ESTADO["warning"])
            kpi(c[3], "Incidentes abiertos", len(abiertos),
                f"{sum(i.get('requiere_revision_humana', False) for i in abiertos)} con revisión humana", ESTADO["serious"])
            kpi(c[4], "Riesgos críticos", len(criticos),
                f"{len(criticos_inh)} antes de mitigar · residual ≥ {cfg['umbral_riesgo_critico']}", ESTADO["critical"])
            st.write("")

            g1, g2 = st.columns(2)
            with g1:
                st.subheader("Flujo diario de accesos")
                datos = pd.DataFrame(db.accesos_por_decision_dia(desde, hasta))
                if datos.empty:
                    st.info("No hay accesos en el periodo.")
                else:
                    datos = (datos.pivot_table(index="dia", columns="decision", values="total", fill_value=0)
                             .reindex(columns=["ACCESO", "INSPECCION", "DENEGADO"], fill_value=0).reset_index()
                             .melt(id_vars="dia", var_name="decision", value_name="total"))
                    fig = px.area(datos, x="dia", y="total", color="decision", color_discrete_map=COLOR_DECISION,
                                  labels={"dia": "", "total": "Accesos", "decision": "Decisión"})
                    fig.update_traces(line=dict(width=2))
                    st.plotly_chart(figura(fig), width="stretch")
            with g2:
                st.subheader("Mapa semanal de incidentes")
                st.caption("Agregación $group por categoría y semana ISO en MongoDB")
                datos = pd.DataFrame(db.incidentes_por_categoria_semana(desde, hasta))
                if datos.empty:
                    st.info("No hay incidentes en el periodo.")
                else:
                    matriz = datos.pivot_table(index="categoria", columns="etiqueta_semana", values="total",
                                               aggfunc="sum", fill_value=0)
                    matriz = matriz.reindex([c for c in config.CATEGORIAS if c in matriz.index])
                    fig = px.imshow(matriz, text_auto=True, color_continuous_scale=SECUENCIAL, aspect="auto",
                                    labels=dict(x="", y="", color="Incidentes"))
                    fig.update_xaxes(side="top")
                    fig = figura(fig)
                    fig.update_layout(coloraxis_showscale=False)
                    st.plotly_chart(fig, width="stretch")
                    with st.expander("Ver tabla de la agregación"):
                        st.dataframe(datos, hide_index=True, width="stretch")

            st.subheader("Incidentes abiertos de prioridad alta o crítica")
            urgentes = [i for i in abiertos if i["clasificacion"]["prioridad"] in ("ALTA", "CRITICA")]
            if urgentes:
                st.dataframe(pd.DataFrame([{
                    "Prioridad": f"{ICONO_PRIORIDAD[i['clasificacion']['prioridad']]} {i['clasificacion']['prioridad']}",
                    "Fecha": fmt_fecha(i["fecha"]), "Asunto": i["asunto"], "Categoría": i["clasificacion"]["categoria"],
                    "Estado": i["estado"], "Revisión humana": "⚠️ sí" if i.get("requiere_revision_humana") else "",
                } for i in urgentes]), hide_index=True, width="stretch")
            else:
                st.success("Sin incidentes urgentes abiertos en el periodo. ✅")

# ============================================================
# 2. CONTROL DE ACCESO
# ============================================================

elif pagina == PAGINAS[1]:
    st.header("🚦 Control de acceso")
    tab_placa, tab_manual, tab_bitacora = st.tabs(["🔎 Búsqueda por placa", "✍️ Formulario P/Q/R/S", "📒 Bitácora"])

    with tab_placa:
        with manejo_errores("la búsqueda del camión"):
            camiones = db.listar("camiones", orden=("camion_id", 1))
            opciones = {f"{c['placa']} · {c['camion_id']} · {c['empresa']}": c for c in camiones}
            izq, der = st.columns([1, 1])
            with izq:
                texto = st.text_input("Placa o identificador", placeholder="Ej. JLM-215-C o CAM-102").strip().upper()
                candidatos = [k for k in opciones if texto and texto in k.upper()] if texto else list(opciones)
                if texto and not candidatos:
                    st.warning("No se encontró ningún camión con esa placa o identificador. Revisa el formato ABC-123-D / CAM-123 "
                               "o regístralo en «Camiones y datos».")
                elegido = st.selectbox("Camión", candidatos, index=0 if candidatos else None,
                                       placeholder="Sin coincidencias") if candidatos else None
            if elegido:
                cam = opciones[elegido]
                cert = cam["certificacion_conductor"]
                with der, st.container(border=True):
                    st.markdown(f"**{cam['camion_id']}** · placa **{cam['placa']}** · {cam['empresa']}")
                    st.markdown(f"Autorización previa: {'✅ sí' if cam['autorizacion'] else '❌ no'}  \n"
                                f"Certificación ({cert.get('conductor_alias', 'conductor')}): "
                                f"{'✅ vigente' if cert.get('vigente') else '❌ no vigente'} · vence {cert.get('vencimiento')}  \n"
                                f"Peso máximo: {cam['peso_maximo_kg']:,} kg · Carga habitual: {cam.get('tipo_carga', 'general')}")
                with st.form("form_placa"):
                    a, b, c = st.columns(3)
                    peso = a.number_input("Peso en báscula (kg)", min_value=0, max_value=80000, step=100,
                                          value=int(cam["peso_maximo_kg"] * 0.9))
                    llegada = b.time_input("Hora de llegada", datetime.now().time().replace(second=0, microsecond=0))
                    peligroso = c.checkbox("Transporta material peligroso", cam.get("tipo_carga") == "material_peligroso")
                    enviar = st.form_submit_button("Evaluar y registrar acceso", type="primary")
                if enviar:
                    if peso <= 0:
                        st.error("Captura el peso registrado por la báscula (mayor que cero).")
                    else:
                        with manejo_errores("el registro del acceso"):
                            res = registrar_acceso(db, cfg, operador, camion=cam, peso_kg=peso, material_peligroso=peligroso,
                                                   momento=datetime.combine(date.today(), llegada))
                            st.toast(f"Acceso registrado en la bitácora ({res['decision']})", icon="✅")
                            mostrar_resultado_acceso(res)

    with tab_manual:
        st.caption("Captura directa de premisas, útil cuando no hay lectura automática de sensores.")
        with st.form("form_manual"):
            cols = st.columns(3)
            valores = {var: cols[i % 3].checkbox(f"{var} · {desc}", key=f"man_{var}") for i, (var, desc) in enumerate(VARIABLES.items())}
            enviar = st.form_submit_button("Evaluar y registrar", type="primary")
        if enviar:
            with manejo_errores("el registro del acceso"):
                res = registrar_acceso(db, cfg, operador, premisas=valores,
                                       origen={k: "captura manual" for k in valores})
                st.toast("Acceso registrado en la bitácora", icon="✅")
                mostrar_resultado_acceso(res)

    with tab_bitacora:
        with manejo_errores("la consulta de la bitácora"):
            f1, f2, f3 = st.columns([2, 1, 1])
            with f1:
                desde, hasta = rango_fechas("bitacora_fechas", 7)
            decision = f2.selectbox("Decisión", ["Todas", "ACCESO", "INSPECCION", "DENEGADO"])
            placa = f3.text_input("Placa / camión").strip().upper()
            filtro = {}
            if desde:
                filtro["fecha"] = {"$gte": desde, "$lte": hasta}
            if decision != "Todas":
                filtro["decision"] = decision
            if placa:
                filtro["$or"] = [{"placa": {"$regex": placa}}, {"camion_id": {"$regex": placa}}]
            accesos = db.listar("accesos", filtro, limite=300)
            st.caption(f"{len(accesos)} registros")
            if accesos:
                st.dataframe(pd.DataFrame([{
                    "Fecha": fmt_fecha(a["fecha"]), "Camión": a["camion_id"], "Placa": a["placa"],
                    "Decisión": f"{DECISIONES[a['decision']]['semaforo']} {a['decision']}",
                    **{k: "V" if a["premisas"][k] else "F" for k in VARIABLES},
                    "Determinantes": ", ".join(a.get("premisas_determinantes", [])), "Operador": a["operador"],
                    "Nota": a.get("nota", ""),
                } for a in accesos]), hide_index=True, width="stretch", height=320)
                etiquetas = {f"{fmt_fecha(a['fecha'])} · {a['camion_id']} · {a['decision']}": a for a in accesos}
                sel = etiquetas[st.selectbox("Ver detalle de un registro", list(etiquetas))]
                with st.container(border=True):
                    st.markdown(f"**{DECISIONES[sel['decision']]['semaforo']} {sel['decision']}** · `accesos/{sel['_id']}`")
                    st.code("\n".join(sel["explicacion"]), language=None)
                    nota = st.text_input("Nota del supervisor", sel.get("nota", ""), key=f"nota_{sel['_id']}")
                    b1, b2, b3 = st.columns([1, 1, 2])
                    if b1.button("Guardar nota", key=f"gn_{sel['_id']}"):
                        with manejo_errores("la actualización"):
                            db.actualizar("accesos", sel["_id"], {"nota": nota}, {"accion": "nota", "operador": operador})
                            st.toast("Nota guardada", icon="📝")
                    confirmar = b3.checkbox("Confirmo que quiero eliminar este registro", key=f"ce_{sel['_id']}")
                    if b2.button("🗑️ Eliminar", key=f"el_{sel['_id']}", disabled=not confirmar):
                        with manejo_errores("la eliminación"):
                            db.eliminar("accesos", sel["_id"])
                            st.toast("Registro eliminado", icon="🗑️")
                            st.rerun()

# ============================================================
# 3. SIMULADOR DE TABLAS DE VERDAD
# ============================================================

elif pagina == PAGINAS[2]:
    st.header("🔀 Simulador de tablas de verdad")
    st.caption("Activa los interruptores y observa cómo cambian A, E y las reglas nuevas en vivo.")
    izq, der = st.columns([1, 1.3])
    with izq, st.container(border=True):
        valores = {var: st.toggle(f"**{var}** · {desc}", key=f"sim_{var}", value=var in ("P", "S")) for var, desc in VARIABLES.items()}
    resultados = evaluar_reglas(valores)
    with der:
        res = evaluar_camion(**valores)
        semaforo(res["decision"], "Determinantes: " + (", ".join(res["premisas_determinantes"]) or "—"))
        for clave, regla in REGLAS.items():
            v = resultados[clave]
            st.markdown(f"<span class='pastilla {'v' if v else 'f'}'>{'✅' if v else '⬜'} {clave} = {regla['formula']} → "
                        f"{'Verdadero' if v else 'Falso'}</span> {regla['nombre']}{' · *nueva*' if regla.get('nueva') else ''}",
                        unsafe_allow_html=True)

    st.subheader("Tabla de verdad completa (2⁶ = 64 combinaciones)")
    tabla = pd.DataFrame(tabla_verdad())
    actual = tuple(int(valores[v]) for v in VARIABLES)
    solo = st.radio("Mostrar", ["Todas", "Solo ACCESO", "Solo INSPECCION", "Solo DENEGADO"], horizontal=True)
    if solo != "Todas":
        tabla = tabla[tabla["Decisión"] == solo.split()[-1]]
    st.dataframe(
        tabla.style.apply(lambda fila: ["background-color: rgba(42,120,214,.25)" if tuple(fila[list(VARIABLES)]) == actual
                                        else "" for _ in fila], axis=1),
        hide_index=True, width="stretch", height=330)
    st.caption("La fila resaltada corresponde a los interruptores actuales.")

    cols = st.columns(len(REGLAS))
    for col, clave in zip(cols, REGLAS):
        with col:
            st.markdown(f"**{REGLAS[clave]['nombre']}**")
            st.dataframe(pd.DataFrame(tabla_regla(clave)), hide_index=True, width="stretch")

    st.subheader("Reto: contradicciones y reglas redundantes")
    with st.expander("Probar una regla personalizada", expanded=False):
        st.caption("Escribe una regla con P Q R S H C y and/or/not (o ∧ ∨ ¬) para ver si contradice o repite a las existentes.")
        e1, e2, e3 = st.columns([3, 1, 1])
        expr = e1.text_input("Expresión", "P and S and not Q and not R")
        accion = e2.selectbox("Acción", ["permitir", "inspeccionar", "denegar", "avisar"])
        nombre = e3.text_input("Nombre", "X")
    reglas_analisis = dict(REGLAS)
    if expr.strip():
        try:
            funcion, usadas = compilar_expresion(expr)
            if not nombre.strip() or nombre.strip() in REGLAS:
                st.warning("Usa un nombre distinto de A, E, B y V para la regla personalizada.")
            else:
                reglas_analisis[nombre.strip()] = {"nombre": nombre, "formula": expr, "accion": accion,
                                                   "variables": usadas or "P", "f": funcion}
        except ValueError as e:
            st.error(f"⚠️ {e}")
    hallazgos = analizar_reglas(reglas_analisis)
    iconos = {"conflicto": "⚔️", "redundancia": "♻️", "observación": "🔎", "insatisfacible": "🚫", "tautología": "♾️"}
    for h in hallazgos:
        st.markdown(f"{iconos.get(h['tipo'], '•')} **{h['tipo'].capitalize()}** ({h['reglas']}): {h['detalle']}")
    if not hallazgos:
        st.success("No se encontraron contradicciones ni redundancias.")

# ============================================================
# 4. BANDEJA DE INCIDENTES
# ============================================================

elif pagina == PAGINAS[3]:
    st.header("📥 Bandeja de incidentes")
    tab_nuevo, tab_bandeja = st.tabs(["✉️ Nuevo correo", "🗂️ Bandeja"])

    with tab_nuevo:
        if st.button("🎲 Simular correo entrante", help="Toma un correo de ejemplo del conjunto de demostración"):
            c = random.choice(demo.cargar_correos())
            st.session_state.update(inc_texto=c["texto"], inc_asunto=c["asunto"], inc_remitente=c["remitente"])
            st.session_state.pop("clasificacion", None)
        a, b = st.columns(2)
        remitente = a.text_input("Remitente", key="inc_remitente", placeholder="caseta1@logismart.com")
        asunto = b.text_input("Asunto", key="inc_asunto")
        texto = st.text_area("Pega aquí el correo", key="inc_texto", height=150)
        if st.button("🏷️ Clasificar", type="primary"):
            if len(texto.strip()) < 10:
                st.error("El correo es demasiado corto para clasificarlo (mínimo 10 caracteres).")
            else:
                with st.spinner("Clasificando con reglas" + (f" y {cfg['modelo_ollama']}..." if cliente_llm else "...")):
                    with manejo_errores("la clasificación"):
                        empresas = sorted({c["empresa"] for c in db.listar("camiones", orden=None)})
                        st.session_state.clasificacion = clasificar_hibrido(texto, cliente_llm, cfg["reintentos_llm"], empresas)

        cl = st.session_state.get("clasificacion")
        if cl:
            with st.container(border=True):
                st.markdown(f"**Resultado** · fuente: `{cl['fuente']}`")
                if cl["requiere_revision_humana"]:
                    st.warning(f"⚠️ Requiere revisión humana. {cl['motivo_revision']}")
                if cl["llm_error"]:
                    st.info(f"🤖 LLM: {cl['llm_error']} — se usó el clasificador por reglas.")
                m1, m2, m3 = st.columns(3)
                m1.markdown(f"**Reglas**  \n{cl['reglas']['categoria']} · {ICONO_PRIORIDAD[cl['reglas']['prioridad']]} "
                            f"{cl['reglas']['prioridad']}  \nconfianza {cl['reglas']['confianza']} · {cl['reglas']['latencia_ms']} ms")
                if cl["llm"]:
                    m2.markdown(f"**LLM**  \n{cl['llm']['categoria']} · {ICONO_PRIORIDAD[cl['llm']['prioridad']]} "
                                f"{cl['llm']['prioridad']}  \n{cl['llm_intentos']} intento(s) · {cl['llm_latencia_ms']:,.0f} ms")
                else:
                    m2.markdown("**LLM**  \nno disponible")
                m3.markdown(f"**Final (híbrido)**  \n{cl['categoria']} · {ICONO_PRIORIDAD[cl['prioridad']]} {cl['prioridad']}")
                if cl["llm_respuestas_crudas"]:
                    with st.expander("JSON devuelto por el LLM"):
                        for r in cl["llm_respuestas_crudas"]:
                            st.code(r, language="json")

                st.markdown("**Revisa y edita antes de guardar**")
                with st.form("form_guardar_incidente"):
                    e1, e2 = st.columns(2)
                    cat = e1.selectbox("Categoría", config.CATEGORIAS, index=config.CATEGORIAS.index(cl["categoria"]))
                    prio = e2.selectbox("Prioridad", config.PRIORIDADES, index=config.PRIORIDADES.index(cl["prioridad"]))
                    resumen = st.text_input("Resumen", cl["resumen"])
                    ent = cl["entidades"]
                    e3, e4 = st.columns(2)
                    placas = e3.text_input("Placas", ", ".join(ent["placas"]))
                    camiones_txt = e4.text_input("Camiones", ", ".join(ent["camiones"]))
                    empresas_txt = e3.text_input("Empresas", ", ".join(ent["empresas"]))
                    ubic = e4.text_input("Ubicaciones", ", ".join(ent["ubicaciones"]))
                    guardar = st.form_submit_button("💾 Guardar incidente", type="primary")
                if guardar:
                    if not operador.strip():
                        st.error("Indica tu nombre de operador en la barra lateral.")
                    elif len(resumen.strip()) < 5:
                        st.error("El resumen debe tener al menos 5 caracteres.")
                    else:
                        lista = lambda s: [x.strip() for x in s.split(",") if x.strip()]  # noqa: E731
                        final = {**cl, "categoria": cat, "prioridad": prio, "resumen": resumen.strip(),
                                 "entidades": {"placas": lista(placas), "camiones": lista(camiones_txt),
                                               "empresas": lista(empresas_txt), "ubicaciones": lista(ubic)}}
                        editado = (cat, prio) != (cl["categoria"], cl["prioridad"])
                        with manejo_errores("el guardado del incidente"):
                            doc = guardar_incidente(db, cfg, texto, asunto, remitente, final, operador, editado)
                            st.success(f"Incidente guardado (`incidentes/{doc['_id']}`)."
                                       + (" Se notificó a soporte (simulado)." if prio in ("ALTA", "CRITICA") and cfg["modo_simulacion_correo"] else ""))
                            st.session_state.pop("clasificacion", None)

    with tab_bandeja:
        with manejo_errores("la consulta de incidentes"):
            f1, f2, f3, f4 = st.columns(4)
            estados = f1.multiselect("Estado", config.ESTADOS_INCIDENTE, default=["nuevo", "en_atencion"])
            categorias = f2.multiselect("Categoría", config.CATEGORIAS)
            prioridades = f3.multiselect("Prioridad", config.PRIORIDADES)
            solo_revision = f4.checkbox("Solo con revisión humana")
            filtro = {}
            if estados:
                filtro["estado"] = {"$in": estados}
            if categorias:
                filtro["clasificacion.categoria"] = {"$in": categorias}
            if prioridades:
                filtro["clasificacion.prioridad"] = {"$in": prioridades}
            if solo_revision:
                filtro["requiere_revision_humana"] = True
            incidentes = db.listar("incidentes", filtro)
            st.caption(f"{len(incidentes)} incidentes")
            if incidentes:
                st.dataframe(pd.DataFrame([{
                    "Fecha": fmt_fecha(i["fecha"]), "Asunto": i["asunto"],
                    "Prioridad": f"{ICONO_PRIORIDAD[i['clasificacion']['prioridad']]} {i['clasificacion']['prioridad']}",
                    "Categoría": i["clasificacion"]["categoria"], "Estado": i["estado"],
                    "Revisión": "⚠️" if i.get("requiere_revision_humana") else "",
                    "Fuente": i.get("fuente_clasificacion", ""),
                } for i in incidentes]), hide_index=True, width="stretch", height=280)
                etiquetas = {f"{fmt_fecha(i['fecha'])} · {i['asunto']}": i for i in incidentes}
                inc = etiquetas[st.selectbox("Abrir incidente", list(etiquetas))]
                with st.container(border=True):
                    st.markdown(f"**{inc['asunto']}** · de {inc.get('remitente') or 'N/D'} · `incidentes/{inc['_id']}`")
                    st.text(inc["correo_original"])
                    if inc.get("requiere_revision_humana"):
                        st.warning(f"⚠️ {inc.get('motivo_revision') or 'Requiere revisión humana'}")
                    with st.form(f"edit_{inc['_id']}"):
                        e1, e2, e3 = st.columns(3)
                        cl = inc["clasificacion"]
                        cat = e1.selectbox("Categoría", config.CATEGORIAS, index=config.CATEGORIAS.index(cl["categoria"]))
                        prio = e2.selectbox("Prioridad", config.PRIORIDADES, index=config.PRIORIDADES.index(cl["prioridad"]))
                        est = e3.selectbox("Estado", config.ESTADOS_INCIDENTE, index=config.ESTADOS_INCIDENTE.index(inc["estado"]))
                        resumen = st.text_input("Resumen", cl.get("resumen", ""))
                        comentario = st.text_input("Comentario para el historial")
                        revisado = st.checkbox("Revisión humana completada", value=not inc.get("requiere_revision_humana"))
                        if st.form_submit_button("💾 Guardar cambios", type="primary"):
                            cambios = {"clasificacion.categoria": cat, "clasificacion.prioridad": prio, "estado": est,
                                       "clasificacion.resumen": resumen, "requiere_revision_humana": not revisado}
                            detalle = [f"{k.split('.')[-1]}: {v0} → {v1}" for k, v0, v1 in (
                                ("categoria", cl["categoria"], cat), ("prioridad", cl["prioridad"], prio), ("estado", inc["estado"], est))
                                if v0 != v1]
                            with manejo_errores("la actualización del incidente"):
                                db.actualizar("incidentes", inc["_id"], cambios,
                                              {"accion": "edición", "operador": operador or "sin nombre",
                                               "detalle": "; ".join(detalle + ([comentario] if comentario else [])) or "sin cambios"})
                                st.toast("Incidente actualizado", icon="✅")
                                st.rerun()
                    st.markdown("**Historial**")
                    st.dataframe(pd.DataFrame([{"Fecha": fmt_fecha(h["fecha"]), "Acción": h.get("accion"),
                                                "Operador": h.get("operador"), "Detalle": h.get("detalle", "")}
                                               for h in inc.get("historial", [])]), hide_index=True, width="stretch")
                    confirmar = st.checkbox("Confirmo que quiero eliminar este incidente", key=f"ci_{inc['_id']}")
                    if st.button("🗑️ Eliminar incidente", disabled=not confirmar, key=f"ei_{inc['_id']}"):
                        with manejo_errores("la eliminación"):
                            db.eliminar("incidentes", inc["_id"])
                            st.toast("Incidente eliminado", icon="🗑️")
                            st.rerun()

# ============================================================
# 5. ASISTENTE (CHAT LLM CON RAG)
# ============================================================

elif pagina == PAGINAS[4]:
    st.header("💬 Asistente explicativo")
    st.caption("Responde solo con datos recuperados de MongoDB y cita el registro de origen. "
               "Si no hay datos, responde «no tengo información».")
    st.session_state.setdefault("chat", [])
    st.session_state.setdefault("chat_ids", ((), ()))

    ejemplos = ["¿Por qué CAM-102 fue enviado a inspección?", "¿Qué camiones fueron denegados esta semana?",
                "¿Qué incidentes siguen abiertos?", "¿Cuáles son los riesgos éticos más altos?",
                "¿Qué pasó con el camión CAM-999?"]
    cols = st.columns(len(ejemplos))
    pregunta_boton = None
    for col, ej in zip(cols, ejemplos):
        if col.button(ej, width="stretch"):
            pregunta_boton = ej

    for m in st.session_state.chat:
        with st.chat_message(m["rol"]):
            st.markdown(m["texto"])
            if m.get("fuentes"):
                with st.expander(f"📚 Fuentes consultadas ({len(m['fuentes'])})"):
                    for f in m["fuentes"]:
                        st.markdown(f"**[{f['etiqueta']}]** `{f['coleccion']}/{f['id']}`  \n{f['texto']}")
            for adv in m.get("advertencias", []):
                st.caption(f"⚠️ {adv}")
            if m.get("modo"):
                st.caption({"llm": f"🤖 Respuesta del LLM · {m.get('latencia_ms', 0):,} ms", "plantilla": "📋 Respuesta por plantilla (sin LLM)",
                            "sin_datos": "🔍 Sin registros relevantes: no se consultó al LLM"}[m["modo"]])

    pregunta = st.chat_input("Pregunta sobre camiones, accesos, incidentes o riesgos...") or pregunta_boton
    if pregunta:
        st.session_state.chat.append({"rol": "user", "texto": pregunta})
        with st.spinner("Consultando MongoDB" + (" y el LLM..." if cliente_llm else "...")):
            with manejo_errores("la consulta del asistente"):
                r = responder(db, cliente_llm, pregunta, st.session_state.chat_ids)
                st.session_state.chat_ids = r["ids"]
                st.session_state.chat.append({"rol": "assistant", "texto": r["respuesta"], "fuentes": r["fuentes"],
                                              "advertencias": r["advertencias"], "modo": r["modo"],
                                              "latencia_ms": r.get("latencia_ms", 0)})
        st.rerun()
    if st.session_state.chat and st.button("🗑️ Limpiar conversación"):
        st.session_state.chat, st.session_state.chat_ids = [], ((), ())
        st.rerun()

# ============================================================
# 6. RIESGOS ÉTICOS
# ============================================================

elif pagina == PAGINAS[5]:
    st.header("⚖️ Matriz de riesgos éticos")
    with manejo_errores("la carga de riesgos"):
        riesgos = db.listar("riesgos_eticos", orden=None)
        if riesgos:
            df = pd.DataFrame([{
                "id": r["_id"], "Código": f"R{n}", "Módulo": r["modulo"], "Descripción": r["descripcion"],
                "Categoría": r.get("categoria", ""), "P": r["probabilidad"], "I": r["impacto"],
                "Inherente": puntaje(r), "P res.": r["probabilidad_residual"], "I res.": r["impacto_residual"],
                "Residual": puntaje(r, True), "Nivel residual": nivel(puntaje(r, True), cfg),
            } for n, r in enumerate(riesgos, start=1)])

            g1, g2 = st.columns([1.1, 1])
            with g1:
                st.subheader("Matriz probabilidad × impacto")
                st.caption("Contorno: riesgo inherente · relleno: riesgo residual · flecha: efecto de la mitigación")
                fig = go.Figure()
                # Celdas de la matriz 5x5 coloreadas por nivel (bandas de estado).
                for p in range(1, 6):
                    for i in range(1, 6):
                        fig.add_shape(type="rect", x0=p - .48, x1=p + .48, y0=i - .48, y1=i + .48, line_width=0,
                                      fillcolor=COLOR_NIVEL[nivel(p * i, cfg)], opacity=0.16, layer="below")
                jit = {i: ((i % 3) - 1) * 0.14 for i in range(len(df))}
                for i, fila in df.iterrows():
                    fig.add_annotation(x=fila["P res."] + jit[i], y=fila["I res."] + jit[i], ax=fila["P"] + jit[i],
                                       ay=fila["I"] + jit[i], xref="x", yref="y", axref="x", ayref="y", arrowhead=3,
                                       arrowwidth=1.5, arrowcolor="rgba(230,228,223,.45)", showarrow=True, text="")
                fig.add_trace(go.Scatter(x=df["P"] + pd.Series(jit), y=df["I"] + pd.Series(jit), mode="markers+text",
                                         text=df["Código"], textposition="top center", name="Inherente",
                                         textfont=dict(color="#e6e4df"),
                                         marker=dict(size=14, color="rgba(0,0,0,0)", line=dict(width=2, color="#d95926")),
                                         customdata=df[["Descripción", "Inherente"]],
                                         hovertemplate="%{text}: %{customdata[0]}<br>Inherente %{customdata[1]}<extra></extra>"))
                fig.add_trace(go.Scatter(x=df["P res."] + pd.Series(jit), y=df["I res."] + pd.Series(jit), mode="markers",
                                         name="Residual", marker=dict(size=11, color="#3987e5", line=dict(width=2, color="#0f1216")),
                                         customdata=df[["Código", "Residual"]],
                                         hovertemplate="%{customdata[0]} residual %{customdata[1]}<extra></extra>"))
                fig = figura(fig, 440)
                fig.update_xaxes(title="Probabilidad", dtick=1, range=[0.5, 5.5], showgrid=False)
                fig.update_yaxes(title="Impacto", dtick=1, range=[0.5, 5.5], showgrid=False)
                st.plotly_chart(fig, width="stretch")
            with g2:
                st.subheader("Reducción por mitigación")
                st.caption("Cada línea va del puntaje inherente (○) al residual (●)")
                orden = df.sort_values("Inherente")
                fig = go.Figure()
                for _, fila in orden.iterrows():
                    fig.add_trace(go.Scatter(x=[fila["Residual"], fila["Inherente"]], y=[fila["Código"]] * 2, mode="lines",
                                             line=dict(color="#4a525c", width=3), showlegend=False, hoverinfo="skip"))
                fig.add_trace(go.Scatter(x=orden["Inherente"], y=orden["Código"], mode="markers", name="Inherente",
                                         marker=dict(size=13, color="#0f1216", line=dict(width=2, color="#d95926")),
                                         customdata=orden[["Módulo"]], hovertemplate="%{y} · %{customdata[0]}<br>Inherente %{x}<extra></extra>"))
                fig.add_trace(go.Scatter(x=orden["Residual"], y=orden["Código"], mode="markers+text", name="Residual",
                                         text=orden["Residual"], textposition="middle left", textfont=dict(color="#c3c2b7"),
                                         marker=dict(size=12, color="#3987e5"),
                                         customdata=orden[["Módulo"]], hovertemplate="%{y} · %{customdata[0]}<br>Residual %{x}<extra></extra>"))
                fig.add_vline(x=cfg["umbral_riesgo_critico"], line_dash="dot", line_color=ESTADO["critical"],
                              annotation_text=f"⛔ crítico ≥ {cfg['umbral_riesgo_critico']}", annotation_font_color="#e6e4df")
                fig = figura(fig, 440)
                fig.update_xaxes(range=[0, 26], title="Puntaje (probabilidad × impacto)")
                st.plotly_chart(fig, width="stretch")

            vista = df.drop(columns=["id"]).copy()
            vista["Nivel residual"] = vista["Nivel residual"].map(lambda n: f"{ICONO_NIVEL[n]} {n}")
            st.dataframe(vista, hide_index=True, width="stretch")
        else:
            st.info("No hay riesgos registrados. Agrega el primero abajo.")

    def formulario_riesgo(clave, base=None):
        base = base or {}
        with st.form(clave):
            a, b, c = st.columns([1.2, 2, 1])
            modulo = a.text_input("Módulo*", base.get("modulo", ""))
            descripcion = b.text_input("Descripción*", base.get("descripcion", ""))
            idx = CATEGORIAS_RIESGO.index(base["categoria"]) if base.get("categoria") in CATEGORIAS_RIESGO else 0
            categoria = c.selectbox("Categoría", CATEGORIAS_RIESGO, index=idx)
            s = st.columns(4)
            fmt = lambda v: f"{v} · {ESCALA[v]}"  # noqa: E731
            prob = s[0].select_slider("Probabilidad", [1, 2, 3, 4, 5], base.get("probabilidad", 3), format_func=fmt)
            imp = s[1].select_slider("Impacto", [1, 2, 3, 4, 5], base.get("impacto", 3), format_func=fmt)
            prob_r = s[2].select_slider("Probabilidad residual", [1, 2, 3, 4, 5], base.get("probabilidad_residual", 2), format_func=fmt)
            imp_r = s[3].select_slider("Impacto residual", [1, 2, 3, 4, 5], base.get("impacto_residual", 2), format_func=fmt)
            mitigacion = st.text_area("Mitigación*", base.get("mitigacion", ""), height=70)
            evidencia = st.text_input("Evidencia", base.get("evidencia", ""))
            enviado = st.form_submit_button("💾 Guardar", type="primary")
        datos = dict(modulo=modulo.strip(), descripcion=descripcion.strip(), categoria=categoria, probabilidad=prob,
                     impacto=imp, mitigacion=mitigacion.strip(), probabilidad_residual=prob_r, impacto_residual=imp_r,
                     evidencia=evidencia.strip())
        if enviado:
            errores = validar(datos)
            for e in errores:
                st.error(f"⚠️ {e}")
            return None if errores else datos
        return None

    t_alta, t_editar = st.tabs(["➕ Alta de riesgo", "✏️ Edición / baja"])
    with t_alta:
        datos = formulario_riesgo("alta_riesgo")
        if datos:
            with manejo_errores("el alta del riesgo"):
                db.insertar("riesgos_eticos", nuevo_riesgo(**datos, operador=operador or "sin nombre"))
                st.toast("Riesgo registrado", icon="✅")
                st.rerun()
    with t_editar:
        if riesgos:
            etiquetas = {f"R{n} · {r['modulo']} · {r['descripcion'][:60]}": r for n, r in enumerate(riesgos, start=1)}
            r = etiquetas[st.selectbox("Riesgo", list(etiquetas))]
            datos = formulario_riesgo(f"edit_riesgo_{r['_id']}", r)
            if datos:
                with manejo_errores("la edición del riesgo"):
                    db.actualizar("riesgos_eticos", r["_id"], datos, {
                        "accion": "edición", "operador": operador or "sin nombre",
                        "puntaje": datos["probabilidad"] * datos["impacto"],
                        "residual": datos["probabilidad_residual"] * datos["impacto_residual"]})
                    st.toast("Riesgo actualizado", icon="✅")
                    st.rerun()
            with st.expander("📜 Histórico del riesgo"):
                st.dataframe(pd.DataFrame([{"Fecha": fmt_fecha(h["fecha"]), "Acción": h.get("accion"),
                                            "Operador": h.get("operador"), "Inherente": h.get("puntaje"),
                                            "Residual": h.get("residual")} for h in r.get("historial", [])]),
                             hide_index=True, width="stretch")
            confirmar = st.checkbox("Confirmo que quiero dar de baja este riesgo", key=f"cr_{r['_id']}")
            if st.button("🗑️ Dar de baja", disabled=not confirmar, key=f"br_{r['_id']}"):
                with manejo_errores("la baja del riesgo"):
                    db.eliminar("riesgos_eticos", r["_id"])
                    st.toast("Riesgo eliminado", icon="🗑️")
                    st.rerun()

# ============================================================
# 7. REPORTES
# ============================================================

elif pagina == PAGINAS[6]:
    st.header("📄 Reportes")
    with manejo_errores("la generación de reportes"):
        desde, hasta = rango_fechas("rep_fechas", 30)
        st.subheader("Reporte ejecutivo (PDF)")
        if st.button("Generar PDF", type="primary"):
            with st.spinner("Generando PDF..."):
                st.session_state.pdf = reportes.pdf_reporte(db, cfg, desde, hasta, operador)
        if st.session_state.get("pdf"):
            st.download_button("⬇️ Descargar reporte PDF", st.session_state.pdf,
                               file_name=f"reporte_logismart_{date.today():%Y%m%d}.pdf", mime="application/pdf")

        st.subheader("Exportar colecciones (CSV / JSON)")
        filtro = {"fecha": {"$gte": desde, "$lte": hasta}} if desde else {}
        for nombre in ["accesos", "incidentes", "riesgos_eticos", "camiones", "evaluaciones_llm"]:
            registros = db.listar(nombre, filtro if nombre in ("accesos", "incidentes", "evaluaciones_llm") else None)
            c1, c2, c3 = st.columns([2, 1, 1])
            c1.markdown(f"**{nombre}** · {len(registros)} registros")
            c2.download_button("CSV", reportes.a_csv(registros), f"{nombre}.csv", "text/csv", key=f"csv_{nombre}",
                               width="stretch")
            c3.download_button("JSON", reportes.a_json(registros), f"{nombre}.json", "application/json",
                               key=f"json_{nombre}", width="stretch")

    st.subheader("Experimento de clasificación: reglas vs LLM vs híbrido")
    st.caption(f"Conjunto de {len(demo.cargar_correos())} correos etiquetados a mano (data/correos_etiquetados.json).")
    if not cliente_llm:
        st.info("El LLM no está disponible: el experimento evaluará solo las reglas (y el híbrido degradado a reglas).")
    if st.button("▶️ Ejecutar experimento"):
        barra = st.progress(0.0, "Clasificando correos...")
        with manejo_errores("el experimento"):
            res = experimento.ejecutar(cliente_llm, cfg["reintentos_llm"],
                                       progreso=lambda i, n: barra.progress(i / n, f"Correo {i} de {n}"))
            ruta = experimento.guardar(res)
            st.session_state.experimento = res
            st.toast(f"Resultados guardados en {ruta.name}.json", icon="💾")
        barra.empty()
    if "experimento" not in st.session_state:
        previos = sorted(config.RUTA_REPORTES.glob("experimento_*.json"))
        if previos:
            st.session_state.experimento = json.loads(previos[-1].read_text(encoding="utf-8"))
    res = st.session_state.get("experimento")
    if res:
        st.caption(f"Resultado del {res['fecha']} · modelo: {res['modelo'] or 'sin LLM'}")
        filas = []
        for m in experimento.METODOS:
            r = res["resumen"][m]
            if r.get("disponible"):
                filas.append({"Método": m, "Exactitud categoría": r["exactitud_categoria"],
                              "Exactitud prioridad": r["exactitud_prioridad"], "Ambas": r["exactitud_ambas"],
                              "Formal (cat.)": r["por_estilo"]["formal"]["exactitud_categoria"],
                              "Informal (cat.)": r["por_estilo"]["informal"]["exactitud_categoria"],
                              "Latencia media (ms)": r["latencia_media_ms"], "p95 (ms)": r["latencia_p95_ms"],
                              "Prioridad subestimada": len(r["prioridad_subestimada"])})
        st.dataframe(pd.DataFrame(filas).style.format({c: "{:.1%}" for c in ["Exactitud categoría", "Exactitud prioridad", "Ambas",
                                                                              "Formal (cat.)", "Informal (cat.)"]}),
                     hide_index=True, width="stretch")
        disponibles = [m for m in experimento.METODOS if res["resumen"][m].get("disponible")]
        cols = st.columns(len(disponibles))
        for col, m in zip(cols, disponibles):
            matriz = pd.DataFrame(res["resumen"][m]["matriz_confusion"]).T
            matriz = matriz.loc[[c for c in matriz.index if matriz.loc[c].sum() > 0 or matriz[c].sum() > 0],
                                [c for c in matriz.columns if matriz[c].sum() > 0 or (c in matriz.index and matriz.loc[c].sum() > 0)]]
            fig = px.imshow(matriz, text_auto=True, color_continuous_scale=SECUENCIAL,
                            labels=dict(x="Predicción", y="Real", color="Correos"), aspect="auto")
            fig.update_layout(height=380, margin=dict(l=0, r=0, t=30, b=0), title=f"Matriz de confusión · {m}",
                              coloraxis_showscale=False)
            col.plotly_chart(fig, width="stretch")
        st.download_button("⬇️ Descargar resultados (JSON)", json.dumps(res, ensure_ascii=False, indent=2),
                           "experimento.json", "application/json")
        with st.expander("Detalle por correo"):
            st.dataframe(pd.DataFrame(res["filas"]), hide_index=True, width="stretch")

# ============================================================
# 8. CAMIONES Y DATOS (CRUD)
# ============================================================

elif pagina == PAGINAS[7]:
    st.header("🚛 Camiones y datos")
    t_cam, t_eval, t_admin = st.tabs(["Catálogo de camiones", "Evaluaciones del LLM", "Administración"])

    def formulario_camion(clave, base=None):
        base = base or {"certificacion_conductor": {}}
        cert = base.get("certificacion_conductor", {})
        with st.form(clave):
            a, b, c = st.columns(3)
            camion_id = a.text_input("Identificador* (CAM-123)", base.get("camion_id", "")).strip().upper()
            placa = b.text_input("Placa* (ABC-123-D)", base.get("placa", "")).strip().upper()
            empresa = c.text_input("Empresa*", base.get("empresa", ""))
            d, e, f = st.columns(3)
            autorizacion = d.checkbox("Autorización previa", base.get("autorizacion", True))
            peso = e.number_input("Peso máximo (kg)", 1000, 80000, int(base.get("peso_maximo_kg", 40000)), 500)
            tipos = ["general", "material_peligroso", "refrigerada", "valores"]
            tipo = f.selectbox("Carga habitual", tipos, index=tipos.index(base.get("tipo_carga", "general")))
            g, h, i = st.columns(3)
            alias = g.text_input("Alias del conductor", cert.get("conductor_alias", ""),
                                 help="Por privacidad no se guarda el nombre real del conductor.")
            vigente = h.checkbox("Certificación vigente", cert.get("vigente", True))
            venc = i.date_input("Vencimiento de la certificación",
                                date.fromisoformat(cert["vencimiento"]) if cert.get("vencimiento") else date.today() + timedelta(days=365))
            enviado = st.form_submit_button("💾 Guardar", type="primary")
        if not enviado:
            return None
        datos = {"camion_id": camion_id, "placa": placa, "empresa": empresa.strip(), "autorizacion": autorizacion,
                 "peso_maximo_kg": peso, "tipo_carga": tipo,
                 "certificacion_conductor": {"conductor_alias": alias.strip(), "vigente": vigente and venc >= date.today(),
                                             "vencimiento": venc.isoformat()}}
        errores = validar_camion(datos)
        for err in errores:
            st.error(f"⚠️ {err}")
        return None if errores else datos

    with t_cam:
        with manejo_errores("el catálogo de camiones"):
            camiones = db.listar("camiones", orden=("camion_id", 1))
            st.dataframe(pd.DataFrame([{
                "Camión": c["camion_id"], "Placa": c["placa"], "Empresa": c["empresa"],
                "Autorización": "✅" if c["autorizacion"] else "❌",
                "Certificación": ("✅ " if c["certificacion_conductor"].get("vigente") else "❌ ") + str(c["certificacion_conductor"].get("vencimiento")),
                "Peso máx. (kg)": c["peso_maximo_kg"], "Carga": c.get("tipo_carga"),
            } for c in camiones]), hide_index=True, width="stretch")
            a1, a2 = st.tabs(["➕ Alta", "✏️ Edición / baja"])
            with a1:
                datos = formulario_camion("alta_camion")
                if datos:
                    with manejo_errores("el alta del camión"):
                        db.insertar("camiones", datos)
                        st.toast("Camión registrado", icon="✅")
                        st.rerun()
            with a2:
                if camiones:
                    opciones = {f"{c['camion_id']} · {c['placa']}": c for c in camiones}
                    cam = opciones[st.selectbox("Camión a editar", list(opciones))]
                    datos = formulario_camion(f"edit_cam_{cam['_id']}", cam)
                    if datos:
                        with manejo_errores("la edición del camión"):
                            db.actualizar("camiones", cam["_id"], datos)
                            st.toast("Camión actualizado", icon="✅")
                            st.rerun()
                    confirmar = st.checkbox("Confirmo la baja de este camión", key=f"cb_{cam['_id']}")
                    if st.button("🗑️ Dar de baja", disabled=not confirmar, key=f"bc_{cam['_id']}"):
                        with manejo_errores("la baja del camión"):
                            db.eliminar("camiones", cam["_id"])
                            st.toast("Camión eliminado", icon="🗑️")
                            st.rerun()

    with t_eval:
        with manejo_errores("la consulta de evaluaciones"):
            evals = db.listar("evaluaciones_llm", limite=500)
            if not evals:
                st.info("Aún no hay evaluaciones del LLM. Se registran automáticamente al clasificar correos o usar el asistente.")
            else:
                df = pd.DataFrame(evals)
                c = st.columns(4)
                c[0].metric("Llamadas registradas", len(df))
                c[1].metric("JSON válido", f"{df['json_valido'].dropna().astype(bool).mean():.0%}" if df["json_valido"].notna().any() else "—")
                c[2].metric("Coincide con reglas", f"{df['coincide_reglas'].dropna().astype(bool).mean():.0%}" if df["coincide_reglas"].notna().any() else "—")
                c[3].metric("Latencia media", f"{df['latencia_ms'].mean():,.0f} ms")
                columnas = [col for col in ["fecha", "tarea", "modelo", "latencia_ms", "json_valido", "coincide_reglas", "prompt", "respuesta"] if col in df]
                st.dataframe(df[columnas], hide_index=True, width="stretch", height=320)

    with t_admin:
        st.markdown("**Explorador de colecciones**")
        nombre = st.selectbox("Colección", ["camiones", "accesos", "incidentes", "riesgos_eticos", "evaluaciones_llm", "notificaciones"])
        with manejo_errores("el explorador"):
            docs = db.listar(nombre, limite=50, orden=None if nombre == "camiones" else ("fecha", -1))
            st.caption(f"{db.contar(nombre)} documentos (se muestran hasta 50)")
            if docs:
                ids = {f"{d['_id']} · {str(d.get('placa') or d.get('asunto') or d.get('descripcion') or d.get('tarea') or '')[:50]}": d for d in docs}
                d = ids[st.selectbox("Documento", list(ids))]
                st.json(json.loads(json.dumps(d, default=str, ensure_ascii=False)), expanded=False)
        st.divider()
        st.markdown("**Datos de demostración**")
        st.caption("Borra solo las colecciones de LogiSmart (camiones, accesos, incidentes, riesgos_eticos, evaluaciones_llm, "
                   "notificaciones) y vuelve a cargar los datos de ejemplo.")
        confirmar = st.checkbox("Entiendo que se borrarán los datos actuales de estas colecciones")
        if st.button("♻️ Reiniciar datos de demostración", disabled=not confirmar):
            with st.spinner("Recargando datos..."), manejo_errores("la recarga de datos"):
                demo.cargar_demo(db, cfg, forzar=True)
                st.toast("Datos de demostración recargados", icon="♻️")

# ============================================================
# 9. CONFIGURACIÓN
# ============================================================

elif pagina == PAGINAS[8]:
    st.header("⚙️ Configuración")
    with st.form("form_config"):
        st.subheader("🤖 Modelo de Ollama")
        a, b, c, d = st.columns(4)
        if modelos_instalados:
            idx = next((i for i, m in enumerate(modelos_instalados) if m.split(":")[0] == cfg["modelo_ollama"].split(":")[0]), 0)
            modelo = a.selectbox("Modelo", modelos_instalados, index=idx)
        else:
            modelo = a.text_input("Modelo", cfg["modelo_ollama"], help="Ollama no respondió; escribe el nombre del modelo.")
        temperatura = b.slider("Temperatura", 0.0, 1.0, float(cfg["temperatura"]), 0.1)
        reintentos = c.number_input("Reintentos si el JSON es inválido", 0, 5, int(cfg["reintentos_llm"]))
        timeout = d.number_input("Tiempo máximo (s)", 10, 600, int(cfg["timeout_llm_s"]), 10)
        usar_llm = st.toggle("Usar LLM (si se desactiva, todo funciona con reglas)", cfg["usar_llm"])

        st.subheader("🚦 Umbrales del motor de reglas")
        a, b, c, d = st.columns(4)
        tolerancia = a.number_input("Tolerancia de peso (%)", 0.0, 20.0, float(cfg["tolerancia_peso_pct"]), 0.5)
        h_ini = b.number_input("Inicio horario restringido (h)", 0, 23, int(cfg["hora_inicio_restriccion"]))
        h_fin = c.number_input("Fin horario restringido (h)", 0, 23, int(cfg["hora_fin_restriccion"]))
        dias = d.number_input("Días de alerta de certificación", 1, 180, int(cfg["dias_alerta_certificacion"]))

        st.subheader("⚖️ Umbrales de riesgo (puntaje 1-25)")
        a, b = st.columns(2)
        u_crit = a.number_input("Crítico desde", 2, 25, int(cfg["umbral_riesgo_critico"]))
        u_alto = b.number_input("Alto desde", 1, 24, int(cfg["umbral_riesgo_alto"]))

        st.subheader("✉️ Correo de soporte")
        a, b = st.columns(2)
        simulacion = a.toggle("Modo simulación de correo (no se envía, solo se registra)", cfg["modo_simulacion_correo"])
        correo = b.text_input("Correo de soporte", cfg["correo_soporte"])
        guardar = st.form_submit_button("💾 Guardar configuración", type="primary")

    if guardar:
        errores = []
        if u_alto >= u_crit:
            errores.append("El umbral «alto» debe ser menor que el «crítico».")
        if h_ini == h_fin:
            errores.append("El horario restringido debe tener inicio y fin distintos.")
        if "@" not in correo:
            errores.append("El correo de soporte no es válido.")
        if not modelo.strip():
            errores.append("Indica el nombre del modelo.")
        for e in errores:
            st.error(f"⚠️ {e}")
        if not errores:
            nueva = {**cfg, "modelo_ollama": modelo.strip(), "temperatura": temperatura, "reintentos_llm": int(reintentos),
                     "timeout_llm_s": int(timeout), "usar_llm": usar_llm, "tolerancia_peso_pct": tolerancia,
                     "hora_inicio_restriccion": int(h_ini), "hora_fin_restriccion": int(h_fin),
                     "dias_alerta_certificacion": int(dias), "umbral_riesgo_critico": int(u_crit),
                     "umbral_riesgo_alto": int(u_alto), "modo_simulacion_correo": simulacion, "correo_soporte": correo.strip()}
            with manejo_errores("el guardado de la configuración"):
                db.guardar_config(nueva)
                st.session_state.cfg = nueva
                estado_ollama.clear()
                st.toast("Configuración guardada", icon="✅")
                st.rerun()

    st.subheader("📬 Correos de soporte (bandeja simulada)")
    with manejo_errores("la consulta de notificaciones"):
        if st.button("Enviar correo de prueba"):
            notificar(db, cfg, "Prueba de notificación", f"Correo de prueba enviado por {operador or 'operador'}")
            st.toast("Notificación registrada", icon="📨")
        notis = db.listar("notificaciones", limite=20)
        if notis:
            st.dataframe(pd.DataFrame([{"Fecha": fmt_fecha(n["fecha"]), "Para": n["para"], "Asunto": n["asunto"],
                                        "Mensaje": n["mensaje"], "Simulado": "✅" if n.get("simulado") else "❌"} for n in notis]),
                         hide_index=True, width="stretch")
        else:
            st.caption("Sin notificaciones todavía. Se generan al guardar incidentes de prioridad ALTA o CRÍTICA.")
