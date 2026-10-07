# Práctica: Interfaz LLM · LogiSmart

Dos entregas en un mismo repositorio:

| Parte | Qué es | Cómo se ejecuta |
|---|---|---|
| 1 | **RutaSegura**: tutor con LLM, rol nuevo de asesor en seguridad vial y logística, GUI y resumen del historial | `streamlit run tutor_gui.py` (GUI) · `python p02primertutor_llm.py` (consola) |
| 2 | **LogiSmart**: control de acceso con lógica proposicional, MongoDB, clasificador híbrido reglas + LLM, asistente RAG y matriz de riesgos éticos | `streamlit run app.py` |

El informe técnico está en [docs/informe_tecnico.md](docs/informe_tecnico.md).

## Instalación

```bash
pip install -r requirements.txt
```

1. **Ollama** (LLM local): instálalo desde https://ollama.com y descarga el modelo:
   ```bash
   ollama pull llama3.2
   ```
   Sin Ollama la aplicación sigue funcionando: el clasificador usa reglas y el asistente responde con plantillas a partir de los datos.
2. **MongoDB**: copia `.env.example` como `.env` y llena las credenciales del clúster Atlas (o `MONGO_URI` para un MongoDB local o Compass).
   Si no hay conexión, la app arranca con una base temporal en memoria y lo indica en la barra lateral.
3. **Datos de demostración**: se cargan solos la primera vez. Para recargarlos:
   ```bash
   python -m logismart.demo --reiniciar
   ```

## Experimento de clasificación

```bash
python -m logismart.experimento            # usa llama3.2
python -m logismart.experimento qwen2.5    # otro modelo
```
También se puede ejecutar desde la GUI en **Reportes → Ejecutar experimento**. Los resultados se guardan en `reportes/experimento_*.json` y `.md`.

## Estructura

```
app.py                      GUI de LogiSmart (9 pantallas)
tutor_gui.py                GUI del tutor (parte 1)
p02primertutor_llm.py       Tutor en consola, con el nuevo rol y el comando 'resumen'
logismart/
  config.py                 credenciales (.env) y parámetros por defecto
  db.py                     persistencia MongoDB: CRUD, agregaciones y manejo de errores
  reglas.py                 motor de lógica proposicional, tablas de verdad, contradicciones
  llm.py                    cliente Ollama con latencia y bitácora en evaluaciones_llm
  clasificador.py           clasificador por reglas, LLM (pydantic) y fusión híbrida
  asistente.py              chat explicativo con RAG y citas de fuentes
  riesgos.py                matriz de riesgos éticos (inherente y residual)
  servicios.py              casos de uso: registrar acceso, guardar incidente, notificar
  reportes.py               exportación PDF, CSV y JSON
  experimento.py            evaluación de reglas, LLM e híbrido
  demo.py                   datos de demostración
data/correos_etiquetados.json   38 correos etiquetados a mano
codigo_original/            scripts originales de la práctica, sin cambios
docs/informe_tecnico.md     informe técnico
reportes/                   resultados del experimento y reportes generados
```
