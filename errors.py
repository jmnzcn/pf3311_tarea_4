"""
errors.py se encarga de definir y manejar los errores del sistema.

Incluye:
- errores personalizados para Gemini (API, cuota, conexión, etc.)
- errores relacionados con voz (micrófono, reconocimiento, etc.)
- una clase helper que interpreta errores técnicos
- funciones para traducir errores a mensajes entendibles

La idea es separar la lógica de errores del resto del sistema,
para que el código sea más claro y fácil de mantener.
"""

from typing import Optional  # Permite indicar que un valor puede ser None


# ==============================
# EXCEPCIONES PERSONALIZADAS
# ==============================

# En esta sección se definen errores personalizados del sistema.
# En lugar de usar Exception genérico, se crean clases específicas
# para poder identificar mejor qué tipo de error ocurrió.

# Esto ayuda a:
# - manejar errores de forma más clara
# - mostrar mensajes más amigables al usuario
# - tomar decisiones (por ejemplo, reintentar o no)


class GeminiAuthError(Exception):
    """
    Error relacionado con autenticación en Gemini.

    Ejemplo:
    - API key inválida
    - falta de permisos
    """
    pass


class GeminiQuotaError(Exception):
    """
    Error relacionado con límites de uso (cuota).

    Ejemplo:
    - rate limit
    - quota exceeded
    """
    pass


class GeminiRetryableError(Exception):
    """
    Error temporal.

    Este tipo de error puede resolverse intentando nuevamente.
    """
    pass


class GeminiConnectionError(Exception):
    """
    Error de conexión.

    Ejemplo:
    - problemas de red
    - caída del servicio
    """
    pass


# ==============================
# ERRORES DE VOZ
# ==============================

# Estos errores son independientes de Gemini.
# Se usan para manejar problemas relacionados con el micrófono
# o el reconocimiento de voz.


class VoiceTimeoutError(Exception):
    """
    No se detectó voz dentro del tiempo esperado.
    """
    pass


class VoiceNoEntendidaError(Exception):
    """
    Se escuchó audio, pero no se pudo interpretar.
    """
    pass


class VoiceServicioError(Exception):
    """
    Falló el servicio de reconocimiento de voz.
    """
    pass


class VoiceMicrofonoError(Exception):
    """
    Problema con el micrófono o permisos del sistema.
    """
    pass


# ==============================
# HELPER DE ERRORES GEMINI
# ==============================

class GeminiSDKErrorHelper:
    """
    Esta clase se encarga de analizar errores que vienen del SDK de Gemini
    y convertirlos en algo más útil para el sistema.

    Hace varias cosas:
    - intenta entender qué tipo de error ocurrió
    - lo clasifica en una categoría (auth, cuota, conexión, etc.)
    - decide si se puede reintentar
    - genera un mensaje amigable para el usuario
    """

    # Lista de palabras clave que indican errores temporales.
    # Estos suelen ser errores que se pueden reintentar.
    ERRORES_REINTENTABLES = (
        "rate limit",
        "timeout",
        "timed out",
        "connection",
        "connection reset",
        "reset by peer",
        "broken pipe",
        "resource exhausted",
        "temporarily unavailable",
        "deadline exceeded",
        "service unavailable",
        "internal",
        "unavailable",
        "server error",
    )

    # Palabras clave que indican problemas con la API key o autenticación.
    ERRORES_API_KEY = (
        "api_key_invalid",
        "api key not valid",
        "api_key",
        "authentication",
        "unauthorized",
        "forbidden",
    )

    # Palabras clave relacionadas con límites de uso.
    ERRORES_CUOTA = (
        "resource_exhausted",
        "quota exceeded",
        "quota",
        "rate limit",
        "resource exhausted",
    )

    @staticmethod
    def obtener_codigo(error: Exception) -> Optional[int]:
        """
        Intenta obtener un código HTTP desde la excepción.

        Algunos SDKs usan diferentes nombres, por eso revisa varios:
        - status_code
        - code
        - http_status

        Si no encuentra nada, devuelve None.
        """
        for attr in ("status_code", "code", "http_status"):
            value = getattr(error, attr, None)

            if isinstance(value, int):
                return value

        return None

    @staticmethod
    def obtener_mensaje(error: Exception) -> str:
        """
        Convierte el error a texto limpio.

        - lo pasa a minúsculas
        - elimina espacios extra
        """
        return str(error).lower().strip()

    @classmethod
    def clasificar(cls, error: Exception) -> Exception:
        """
        Clasifica un error en una categoría específica del sistema.

        Orden importante:
        primero se revisan los casos más específicos,
        luego los más generales.
        """

        codigo = cls.obtener_codigo(error)
        mensaje = cls.obtener_mensaje(error)

        # 1. Error de autenticación
        if cls._es_error_auth(codigo, mensaje):
            return GeminiAuthError(str(error))

        # 2. Error de cuota
        if cls._es_error_cuota(codigo, mensaje):
            return GeminiQuotaError(str(error))

        # 3. Error del servidor (5xx)
        if cls._es_error_servidor(codigo):
            return GeminiRetryableError(str(error))

        # 4. Error de conexión
        if cls._es_error_conexion(mensaje):
            return GeminiConnectionError(str(error))

        # 5. Error temporal basado en texto
        if cls._es_error_reintentable_por_mensaje(mensaje):
            return GeminiRetryableError(str(error))

        # Si no se reconoce, se devuelve el error original
        return error

    @classmethod
    def es_reintentable(cls, error: Exception) -> bool:
        """
        Determina si el error vale la pena reintentar.

        Solo se reintenta si es:
        - error temporal
        - error de conexión
        """
        clasificado = cls.clasificar(error)

        return isinstance(
            clasificado,
            (GeminiRetryableError, GeminiConnectionError),
        )

    @classmethod
    def traducir(cls, error: Exception) -> str:
        """
        Convierte un error técnico en un mensaje entendible
        para el usuario.
        """

        clasificado = cls.clasificar(error)

        if isinstance(clasificado, GeminiAuthError):
            return "Hubo un problema de autenticación con Gemini. Revisa GEMINI_API_KEY."

        if isinstance(clasificado, GeminiQuotaError):
            return "Se alcanzó el límite o la cuota de la API de Gemini. Intenta más tarde."

        if isinstance(clasificado, GeminiConnectionError):
            return "Hubo un problema de conexión con el servicio."

        if isinstance(clasificado, GeminiRetryableError):
            return "El servicio de Gemini no está disponible en este momento."

        # Caso especial: timeout detectado por texto
        if cls._parece_timeout(error):
            return "La solicitud tardó demasiado. Intenta nuevamente."

        # Mensaje genérico si no se reconoce el error
        return "Ocurrió un error inesperado al comunicarse con Gemini."

    # ==============================
    # MÉTODOS PRIVADOS (REGLAS)
    # ==============================

    @classmethod
    def _es_error_auth(cls, codigo: Optional[int], mensaje: str) -> bool:
        """
        Detecta errores de autenticación.
        """
        return codigo in {401, 403} or any(
            clave in mensaje for clave in cls.ERRORES_API_KEY
        )

    @classmethod
    def _es_error_cuota(cls, codigo: Optional[int], mensaje: str) -> bool:
        """
        Detecta errores de cuota.
        """
        return codigo == 429 or any(
            clave in mensaje for clave in cls.ERRORES_CUOTA
        )

    @staticmethod
    def _es_error_servidor(codigo: Optional[int]) -> bool:
        """
        Detecta errores del servidor (códigos 5xx).
        """
        return codigo in {500, 502, 503, 504}

    @staticmethod
    def _es_error_conexion(mensaje: str) -> bool:
        """
        Detecta errores de red.
        """
        return "connection" in mensaje or "network" in mensaje

    @classmethod
    def _es_error_reintentable_por_mensaje(cls, mensaje: str) -> bool:
        """
        Detecta errores temporales basándose en el texto.
        """
        return any(clave in mensaje for clave in cls.ERRORES_REINTENTABLES)

    @classmethod
    def _parece_timeout(cls, error: Exception) -> bool:
        """
        Detecta timeouts usando palabras clave.
        """
        mensaje = cls.obtener_mensaje(error)

        return any(
            texto in mensaje
            for texto in ("timeout", "timed out", "deadline exceeded")
        )


# ==============================
# FUNCIÓN DE CONVENIENCIA
# ==============================

def traducir_error(error: Exception) -> str:
    """
    Función simplificada para traducir errores.

    Sirve para que otras partes del código no tengan que usar
    directamente la clase GeminiSDKErrorHelper.

    Es como un "atajo".
    """
    return GeminiSDKErrorHelper.traducir(error)
