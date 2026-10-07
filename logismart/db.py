# ============================================================
# CAPA DE PERSISTENCIA (MongoDB)
# ============================================================
#
# Orden de conexión:
#   1. MONGO_URI del .env (p. ej. MongoDB local / Compass).
#   2. Clúster Atlas con Mongo_User, Mongo_Password y Mongo_Cluster.
#   3. Si nada responde, base en memoria (mongomock) para que la
#      aplicación siga funcionando en modo demostración. La GUI
#      muestra claramente este estado.
#
# Todas las operaciones convierten los errores de pymongo en
# ErrorBaseDatos, con un mensaje entendible para el usuario.
# ============================================================

from datetime import datetime
from functools import wraps
from urllib.parse import quote_plus

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError

from . import config

COLECCIONES = [
    "camiones",
    "accesos",
    "incidentes",
    "riesgos_eticos",
    "evaluaciones_llm",
    "notificaciones",
    "configuracion",
]


class ErrorBaseDatos(Exception):
    """Error de base de datos con mensaje apto para mostrarse al usuario."""


def _amigable(accion):
    def decorador(funcion):
        @wraps(funcion)
        def envoltura(*args, **kwargs):
            try:
                return funcion(*args, **kwargs)
            except ErrorBaseDatos:
                raise
            except DuplicateKeyError as e:
                campo = ", ".join((e.details or {}).get("keyValue", {}).keys()) or "clave"
                raise ErrorBaseDatos(f"No se pudo {accion}: ya existe un registro con ese valor de {campo}.") from e
            except InvalidId as e:
                raise ErrorBaseDatos(f"No se pudo {accion}: identificador inválido.") from e
            except PyMongoError as e:
                raise ErrorBaseDatos(
                    f"No se pudo {accion}: falló la comunicación con MongoDB. "
                    f"Revisa tu conexión a internet o la configuración del .env. (Detalle: {e})"
                ) from e
        return envoltura
    return decorador


def _uri_atlas():
    if config.MONGO_URI:
        return config.MONGO_URI
    if config.MONGO_USER and config.MONGO_PASSWORD and config.MONGO_CLUSTER:
        return (
            f"mongodb+srv://{quote_plus(config.MONGO_USER)}:{quote_plus(config.MONGO_PASSWORD)}"
            f"@{config.MONGO_CLUSTER}/?retryWrites=true&w=majority&appName=LogiSmart"
        )
    return None


def _serializar(doc):
    if doc is None:
        return None
    doc = dict(doc)
    doc["_id"] = str(doc["_id"])
    return doc


class BaseDatos:
    def __init__(self, uri=None, forzar_local=False, timeout_ms=6000):
        self.error_conexion = None
        uri = uri or _uri_atlas()
        cliente = None
        if uri and not forzar_local:
            try:
                cliente = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)
                cliente.admin.command("ping")
                self.modo = "atlas" if uri.startswith("mongodb+srv") else "mongodb"
            except Exception as e:  # noqa: BLE001 - cualquier fallo nos manda al respaldo
                self.error_conexion = str(e).split(",")[0][:300]
                cliente = None
        if cliente is None:
            import mongomock

            cliente = mongomock.MongoClient()
            self.modo = "memoria"
            if not uri and not forzar_local:
                self.error_conexion = "No hay credenciales de MongoDB en el archivo .env."
        self.cliente = cliente
        self.db = cliente[config.MONGO_DB]
        self._crear_indices()

    @property
    def descripcion(self):
        return {
            "atlas": f"MongoDB Atlas · base {config.MONGO_DB}",
            "mongodb": f"MongoDB · base {config.MONGO_DB}",
            "memoria": "Base temporal en memoria (sin conexión a MongoDB)",
        }[self.modo]

    def _crear_indices(self):
        try:
            self.db.camiones.create_index([("placa", ASCENDING)], unique=True)
            self.db.camiones.create_index([("camion_id", ASCENDING)], unique=True)
            self.db.accesos.create_index([("fecha", DESCENDING)])
            self.db.accesos.create_index([("camion_id", ASCENDING)])
            self.db.incidentes.create_index([("fecha", DESCENDING)])
            self.db.evaluaciones_llm.create_index([("fecha", DESCENDING)])
        except PyMongoError:
            pass  # Los índices son una optimización; no bloquean el arranque.

    # --------------------------------------------------------
    # CRUD genérico
    # --------------------------------------------------------

    @_amigable("consultar los registros")
    def listar(self, coleccion, filtro=None, orden=("fecha", DESCENDING), limite=0):
        cursor = self.db[coleccion].find(filtro or {})
        if orden:
            cursor = cursor.sort(*orden)
        if limite:
            cursor = cursor.limit(limite)
        return [_serializar(d) for d in cursor]

    @_amigable("consultar el registro")
    def obtener(self, coleccion, id_):
        return _serializar(self.db[coleccion].find_one({"_id": ObjectId(id_)}))

    @_amigable("buscar el registro")
    def buscar_uno(self, coleccion, filtro):
        return _serializar(self.db[coleccion].find_one(filtro))

    @_amigable("contar los registros")
    def contar(self, coleccion, filtro=None):
        return self.db[coleccion].count_documents(filtro or {})

    @_amigable("guardar el registro")
    def insertar(self, coleccion, documento):
        documento = {k: v for k, v in documento.items() if k != "_id"}
        documento.setdefault("fecha", datetime.now())
        return str(self.db[coleccion].insert_one(documento).inserted_id)

    @_amigable("guardar los registros")
    def insertar_varios(self, coleccion, documentos):
        if documentos:
            self.db[coleccion].insert_many([dict(d) for d in documentos])

    @_amigable("actualizar el registro")
    def actualizar(self, coleccion, id_, cambios, evento_historial=None):
        operacion = {}
        cambios = {k: v for k, v in cambios.items() if k != "_id"}
        if cambios:
            operacion["$set"] = cambios
        if evento_historial:
            operacion["$push"] = {"historial": {"fecha": datetime.now(), **evento_historial}}
        if not operacion:
            return False
        resultado = self.db[coleccion].update_one({"_id": ObjectId(id_)}, operacion)
        if resultado.matched_count == 0:
            raise ErrorBaseDatos("No se encontró el registro; quizá otro usuario lo eliminó.")
        return True

    @_amigable("eliminar el registro")
    def eliminar(self, coleccion, id_):
        return self.db[coleccion].delete_one({"_id": ObjectId(id_)}).deleted_count == 1

    # --------------------------------------------------------
    # Agregaciones
    # --------------------------------------------------------

    @_amigable("calcular la agregación de incidentes")
    def incidentes_por_categoria_semana(self, desde=None, hasta=None):
        """Incidentes agrupados por categoría y semana ISO (pipeline de agregación)."""
        rango = {}
        if desde:
            rango["$gte"] = desde
        if hasta:
            rango["$lte"] = hasta
        pipeline = []
        if rango:
            pipeline.append({"$match": {"fecha": rango}})
        pipeline += [
            {
                "$group": {
                    "_id": {
                        "categoria": "$clasificacion.categoria",
                        "anio": {"$isoWeekYear": "$fecha"},
                        "semana": {"$isoWeek": "$fecha"},
                    },
                    "total": {"$sum": 1},
                    "criticos": {"$sum": {"$cond": [{"$eq": ["$clasificacion.prioridad", "CRITICA"]}, 1, 0]}},
                }
            },
            {"$sort": {"_id.anio": 1, "_id.semana": 1, "_id.categoria": 1}},
        ]
        try:
            resultados = list(self.db.incidentes.aggregate(pipeline))
        except NotImplementedError:
            # mongomock (modo memoria) no implementa $isoWeek; mismo cálculo en Python.
            grupos = {}
            for d in self.db.incidentes.find({"fecha": rango} if rango else {}):
                anio, semana, _ = d["fecha"].isocalendar()
                clave = (anio, semana, d.get("clasificacion", {}).get("categoria"))
                g = grupos.setdefault(clave, {"total": 0, "criticos": 0})
                g["total"] += 1
                g["criticos"] += d.get("clasificacion", {}).get("prioridad") == "CRITICA"
            resultados = [{"_id": {"anio": a, "semana": s, "categoria": c}, **v}
                          for (a, s, c), v in sorted(grupos.items(), key=lambda x: (x[0][0], x[0][1], x[0][2] or ""))]
        return [
            {
                "anio": r["_id"]["anio"],
                "semana": r["_id"]["semana"],
                "etiqueta_semana": f"{r['_id']['anio']}-S{r['_id']['semana']:02d}",
                "categoria": r["_id"]["categoria"] or "sin_categoria",
                "total": r["total"],
                "criticos": r["criticos"],
            }
            for r in resultados
        ]

    @_amigable("calcular la agregación de accesos")
    def accesos_por_decision_dia(self, desde=None, hasta=None):
        rango = {}
        if desde:
            rango["$gte"] = desde
        if hasta:
            rango["$lte"] = hasta
        pipeline = ([{"$match": {"fecha": rango}}] if rango else []) + [
            {
                "$group": {
                    "_id": {
                        "decision": "$decision",
                        "dia": {"$dateToString": {"format": "%Y-%m-%d", "date": "$fecha"}},
                    },
                    "total": {"$sum": 1},
                }
            },
            {"$sort": {"_id.dia": 1}},
        ]
        try:
            return [
                {"dia": r["_id"]["dia"], "decision": r["_id"]["decision"], "total": r["total"]}
                for r in self.db.accesos.aggregate(pipeline)
            ]
        except NotImplementedError:
            conteo = {}
            for d in self.db.accesos.find({"fecha": rango} if rango else {}):
                clave = (d["fecha"].strftime("%Y-%m-%d"), d.get("decision"))
                conteo[clave] = conteo.get(clave, 0) + 1
            return [{"dia": dia, "decision": dec, "total": n} for (dia, dec), n in sorted(conteo.items())]

    # --------------------------------------------------------
    # Configuración persistente
    # --------------------------------------------------------

    def leer_config(self):
        try:
            guardada = self.db.configuracion.find_one({"_id": "app"}) or {}
        except PyMongoError:
            guardada = {}
        guardada.pop("_id", None)
        return {**config.CONFIG_DEFECTO, **{k: v for k, v in guardada.items() if k in config.CONFIG_DEFECTO}}

    @_amigable("guardar la configuración")
    def guardar_config(self, valores):
        self.db.configuracion.replace_one({"_id": "app"}, {"_id": "app", **valores}, upsert=True)
