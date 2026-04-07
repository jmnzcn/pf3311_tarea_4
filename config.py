"""
config.py se encarga de centralizar toda la configuración del sistema.

Aquí se definen:
- los comandos disponibles y sus aliases
- los textos que se muestran en la interfaz
- funciones para leer variables de entorno
- el prompt base del asistente
- la clase Config, que agrupa toda la configuración

La idea es que el resto del proyecto no tenga valores "hardcodeados",
sino que todo venga de este archivo o de variables de entorno (.env).
"""

from dataclasses import dataclass
import os
from typing import Optional


# ==============================
# COMANDOS Y ALIASES
# ==============================

# Lista de comandos disponibles en la aplicación.
# Estos son los comandos que el usuario puede escribir directamente.
COMANDOS_DISPONIBLES = ("ayuda", "limpiar", "reiniciar", "voz", "escuchar", "salir")

# Diccionario de aliases (sinónimos).
# Permite que diferentes palabras ejecuten el mismo comando.
# Ejemplo: "exit" y "quit" hacen lo mismo que "salir".
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
    "escuchar": "escuchar",
}


# ==============================
# TEXTOS DE INTERFAZ (UI)
# ==============================

# Este diccionario contiene todos los textos que se muestran al usuario.
# La idea es centralizar los mensajes en un solo lugar para que
# sean fáciles de cambiar o traducir.
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
    "idioma_actual": "Modo de idioma actual: {modo}.",
    "idioma_actualizado": "Modo de idioma actualizado a: {modo}.",
    "idioma_modos": "Modos disponibles: auto, es, en, mix.",
    "idioma_uso": "Usa: idioma auto | idioma es | idioma en | idioma mix",
}


# ==============================
# FUNCIONES DE ENTORNO
# ==============================

# Estas funciones sirven para leer variables de entorno
# y convertirlas al tipo correcto (string, bool, int, etc).

def env_str(name: str, default: str) -> str:
    """
    Lee una variable de entorno como string.

    Si no existe, devuelve un valor por defecto.
    """
    value = os.getenv(name)
    return value if value is not None else default


def env_bool(name: str, default: bool) -> bool:
    """
    Lee una variable de entorno y la interpreta como booleano.

    Acepta valores como:
    "true", "1", "yes", "on", "si", etc.

    Si no reconoce el valor, devuelve el valor por defecto.
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
    Lee una variable de entorno y la convierte a entero.

    Si falla la conversión, devuelve el valor por defecto.
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
    Lee una variable de entorno y la convierte a float.

    Si falla la conversión, devuelve el valor por defecto.
    """
    value = os.getenv(name)
    if value is None:
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def env_csv(name: str, default: str) -> list[str]:
    """
    Lee una variable de entorno como lista separada por comas.

    Ejemplo:
    "es-ES,en-US" -> ["es-ES", "en-US"]
    """
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


# ==============================
# PROMPT BILINGÜE
# ==============================

def construir_system_prompt_bilingue() -> str:
    """
    Construye el prompt base que se le envía al modelo (Gemini).

    Este prompt define cómo debe comportarse el asistente:
    - tono amigable
    - respuestas cortas
    - uso del idioma del usuario
    - estilo conversacional

    Básicamente es la "personalidad" del bot.
    """
    return (
    "Sos un asistente conversacional en una app de terminal. Actuá como un amigo cercano.\n"
    "Nunca menciones limitaciones técnicas ni cómo funciona el sistema.\n"
    "Si el usuario pide que hables o leas algo, respondé normalmente (el sistema se encarga del audio).\n"
    "\n"
    "Reglas:\n"
    "- Respondé en el idioma del usuario.\n"
    "- Sé natural, amigable, estilo Costa Rica.\n"
    "- Mantené respuestas cortas y claras (máximo 3-4 oraciones).\n"
    "- Si mezcla idiomas, respondé de forma natural.\n"
    "- No traduzcas automáticamente a menos que el usuario lo pida.\n"
    "- Conservá el contexto de la conversación.\n"
    "- Sé útil, directo y natural.\n"
    "- Preferí respuestas concisas incluso si el tema es largo.\n"
)


# ==============================
# CONFIGURACIÓN CENTRAL
# ==============================

@dataclass
class Config:
    """
    Esta clase agrupa TODA la configuración de la aplicación.

    En lugar de tener variables sueltas por todo el código,
    se centraliza todo aquí.

    Esto facilita:
    - mantener el código
    - cambiar configuraciones
    - probar el sistema
    """

    # Configuración del modelo
    nombre_bot: str
    nombre_modelo: str
    temperatura: float
    max_tokens: int

    # Configuración de voz
    voz_habilitada: bool
    voz_timeout: float
    voz_phrase_time_limit: Optional[float]
    voz_idioma: str
    voz_idiomas: list[str]
    voz_duracion_ajuste_ruido: float
    voz_umbral_pausa: float
    voz_duracion_no_habla: float

    # Configuración de la interfaz
    ui_ancho: int
    ui_ancho_limpieza_linea: int
    ui_intervalo_indicador: float

    # Configuración de API
    max_intentos_api: int
    mostrar_traza_error: bool

    # Configuración de idioma
    idioma_modo_inicial: str

    # Prompt del sistema (personalidad del bot)
    system_prompt: str

    @classmethod
    def from_env(cls) -> "Config":
        """
        Este método construye un objeto Config leyendo variables
        de entorno (por ejemplo desde un archivo .env).

        Es básicamente el punto donde se carga toda la configuración
        de la aplicación al iniciar.
        """

        # Si el límite de duración de frase es 0 o menor,
        # se interpreta como "sin límite" (None).
        phrase_time_limit = env_float("VOZ_PHRASE_TIME_LIMIT", 0.0)
        if phrase_time_limit <= 0:
            phrase_time_limit = None

        # Se obtiene el modo de idioma y se valida.
        idioma_modo = env_str("IDIOMA_MODO", "auto").strip().lower()
        if idioma_modo not in {"auto", "es", "en", "mix"}:
            idioma_modo = "auto"

        # Idioma principal de voz.
        voz_idioma_principal = env_str("VOZ_IDIOMA", "es-ES")

        # Lista de idiomas soportados.
        voz_idiomas = env_csv("VOZ_IDIOMAS", f"{voz_idioma_principal},en-US")

        # Se eliminan duplicados manteniendo el orden.
        voz_idiomas_unicos = []
        for idioma in voz_idiomas:
            if idioma not in voz_idiomas_unicos:
                voz_idiomas_unicos.append(idioma)

        # Finalmente se crea el objeto Config con todos los valores.
        return cls(
            nombre_bot=env_str("BOT_NAME", "ChatGiPiTi"),
            nombre_modelo=env_str("MODEL_NAME", "models/gemini-2.5-flash"),
            temperatura=env_float("TEMPERATURE", 0.8),
            max_tokens=env_int("MAX_TOKENS", 4096),

            voz_habilitada=env_bool("VOZ_HABILITADA", True),
            voz_timeout=env_float("VOZ_TIMEOUT", 6.0),
            voz_phrase_time_limit=phrase_time_limit,
            voz_idioma=voz_idioma_principal,
            voz_idiomas=voz_idiomas_unicos,
            voz_duracion_ajuste_ruido=env_float("VOZ_AJUSTE_RUIDO", 0.8),
            voz_umbral_pausa=env_float("VOZ_UMBRAL_PAUSA", 1.1),
            voz_duracion_no_habla=env_float("VOZ_DURACION_NO_HABLA", 0.5),

            ui_ancho=env_int("UI_ANCHO", 60),
            ui_ancho_limpieza_linea=env_int("UI_ANCHO_LIMPIEZA_LINEA", 120),
            ui_intervalo_indicador=env_float("UI_INTERVALO_INDICADOR", 0.45),

            max_intentos_api=env_int("API_MAX_INTENTOS", 3),
            mostrar_traza_error=env_bool("MOSTRAR_TRAZA_ERROR", False),

            idioma_modo_inicial=idioma_modo,

            # Si no hay prompt personalizado, usa el prompt bilingüe por defecto.
            system_prompt=env_str(
                "SYSTEM_PROMPT",
                construir_system_prompt_bilingue(),
            ),
        )