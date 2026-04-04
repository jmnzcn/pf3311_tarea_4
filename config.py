from dataclasses import dataclass
import os


# ==============================
# COMANDOS Y ALIASES
# ==============================

# Lista oficial de comandos disponibles en la aplicación.
# Se usa principalmente para mostrarlos al usuario.
COMANDOS_DISPONIBLES = ("ayuda", "limpiar", "reiniciar", "voz", "salir")


# Permite que el usuario use diferentes palabras para el mismo comando.
# Ejemplo:
#   "help" -> "ayuda"
#   "exit" -> "salir"
ALIASES_COMANDOS = {
    "salir": "salir",
    "exit": "salir",
    "quit": "salir",
    "ayuda": "ayuda",
    "help": "ayuda",
    "limpiar": "limpiar",
    "clear": "limpiar",
    "reiniciar": "reiniciar",
    "reset": "reiniciar",
    "voz": "voz",
    "hablar": "voz",
    "escuchar": "voz",
}


# ==============================
# TEXTOS DE INTERFAZ (UI)
# ==============================

# Todos los mensajes visibles para el usuario.
# Tenerlos centralizados permite:
# - mantener consistencia
# - modificarlos fácilmente
# - facilitar internacionalización en el futuro
TEXTOS_UI = {
    "error_falta_api_key": "Falta GEMINI_API_KEY en el entorno o en el archivo .env.",
    "fin": "Fin.",
    "hasta_luego": "Hasta luego.",
    "comandos": f"Comandos: {', '.join(COMANDOS_DISPONIBLES)}",
    "conversacion_reiniciada": "Conversación reiniciada.",
    "voz_deshabilitada": "La entrada por voz está deshabilitada.",
    "escuchando": "Escuchando...",
    "voz_sin_texto": "No se recibió texto por voz.",
    "voz_timeout": "No detecté voz a tiempo.",
    "voz_no_entendida": "No pude entender lo que dijiste.",
    "voz_error_servicio": "Hubo un problema con el servicio de reconocimiento de voz.",
    "voz_error_microfono": "No se pudo acceder al micrófono. Revisa permisos o el dispositivo de audio.",
    "sin_respuesta": "No pude generar respuesta.",
}


# ==============================
# FUNCIONES DE LECTURA DE ENTORNO
# ==============================

def env_str(name: str, default: str) -> str:
    """
    Obtiene una variable de entorno como string.

    Si la variable no existe, devuelve el valor por defecto.
    """
    value = os.getenv(name)
    return value if value is not None else default


def env_bool(name: str, default: bool) -> bool:
    """
    Convierte una variable de entorno en booleano.

    Valores verdaderos:
        "1", "true", "yes", "on", "si", "sí"

    Valores falsos:
        "0", "false", "no", "off"

    Si el valor no es válido, retorna el default.
    """
    value = os.getenv(name)
    if value is None:
        return default

    normalized = value.strip().lower()

    if normalized in {"1", "true", "yes", "on", "si", "sí"}:
        return True

    if normalized in {"0", "false", "no", "off"}:
        return False

    return default


def env_int(name: str, default: int) -> int:
    """
    Convierte una variable de entorno en entero.

    Si falla la conversión, retorna el default.
    """
    value = os.getenv(name)
    if value is None:
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def env_float(name: str, default: float) -> float:
    """
    Convierte una variable de entorno en float.

    Si falla la conversión, retorna el default.
    """
    value = os.getenv(name)
    if value is None:
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ==============================
# CONFIGURACIÓN CENTRAL
# ==============================

@dataclass
class Config:
    """
    Contiene toda la configuración de la aplicación.

    Esta clase agrupa parámetros como:
    - modelo de IA
    - comportamiento del chat
    - configuración de voz
    - ajustes de interfaz
    - opciones internas del sistema

    Se construye principalmente desde variables de entorno.
    """

    nombre_bot: str
    nombre_modelo: str
    temperatura: float
    max_tokens: int
    voz_habilitada: bool
    voz_timeout: float
    voz_phrase_time_limit: float
    voz_idioma: str
    voz_duracion_ajuste_ruido: float
    voz_umbral_pausa: float
    voz_duracion_no_habla: float
    ui_ancho: int
    ui_ancho_limpieza_linea: int
    ui_intervalo_indicador: float
    max_intentos_api: int
    mostrar_traza_error: bool
    system_prompt: str

    @classmethod
    def from_env(cls) -> "Config":
        """
        Crea una instancia de configuración usando variables de entorno.

        Centraliza toda la lógica de configuración en un solo lugar,
        evitando que otras partes del código accedan directamente a os.getenv.
        """
        return cls(
            nombre_bot=env_str("BOT_NAME", "ChatGiPiTi"),
            nombre_modelo=env_str("MODEL_NAME", "gemini-2.5-flash"),
            temperatura=env_float("TEMPERATURE", 0.8),
            max_tokens=env_int("MAX_TOKENS", 1000),
            voz_habilitada=env_bool("VOZ_HABILITADA", True),
            voz_timeout=env_float("VOZ_TIMEOUT", 5.0),
            voz_phrase_time_limit=env_float("VOZ_PHRASE_TIME_LIMIT", 8.0),
            voz_idioma=env_str("VOZ_IDIOMA", "es-ES"),
            voz_duracion_ajuste_ruido=env_float("VOZ_AJUSTE_RUIDO", 0.8),
            voz_umbral_pausa=env_float("VOZ_UMBRAL_PAUSA", 0.8),
            voz_duracion_no_habla=env_float("VOZ_DURACION_NO_HABLA", 0.5),
            ui_ancho=env_int("UI_ANCHO", 60),
            ui_ancho_limpieza_linea=env_int("UI_ANCHO_LIMPIEZA_LINEA", 120),
            ui_intervalo_indicador=env_float("UI_INTERVALO_INDICADOR", 0.45),
            max_intentos_api=env_int("API_MAX_INTENTOS", 3),
            mostrar_traza_error=env_bool("MOSTRAR_TRAZA_ERROR", False),
            system_prompt=env_str(
                "SYSTEM_PROMPT",
                (
                    "Sos un compa conversacional dentro de una aplicación de terminal.\n"
                    "Responde en español de forma natural, cercana, clara y útil.\n"
                    "Tu tono debe sentirse humano y relajado.\n"
                ),
            ),
        )

    def __post_init__(self) -> None:
        """
        Normaliza y valida los valores después de crear la configuración.

        Evita:
        - valores vacíos
        - valores fuera de rango
        - configuraciones inválidas que podrían romper la app
        """

        # Limpieza de strings
        self.nombre_bot = self.nombre_bot.strip() or "ChatGiPiTi"
        self.nombre_modelo = self.nombre_modelo.strip() or "gemini-2.5-flash"
        self.voz_idioma = self.voz_idioma.strip() or "es-ES"
        self.system_prompt = self.system_prompt.strip() or "Responde claro."

        # Validaciones numéricas
        self.temperatura = max(0.0, min(self.temperatura, 2.0))
        self.max_tokens = max(1, self.max_tokens)
        self.voz_timeout = max(0.1, self.voz_timeout)
        self.voz_phrase_time_limit = max(0.1, self.voz_phrase_time_limit)
        self.ui_ancho = max(20, self.ui_ancho)
        self.max_intentos_api = max(1, self.max_intentos_api)