from typing import Optional


# ==============================
# EXCEPCIONES PERSONALIZADAS
# ==============================

# Estas excepciones representan errores específicos relacionados con Gemini.
# Tener errores propios hace que el resto del código sea más claro, porque
# permite trabajar con conceptos del dominio en lugar de depender directamente
# de mensajes crudos del SDK o de la API.


class GeminiAuthError(Exception):
    """
    Error de autenticación con Gemini.

    Se usa cuando la API key es inválida, falta, o no tiene permisos
    suficientes para realizar la solicitud.
    """
    pass


class GeminiQuotaError(Exception):
    """
    Error relacionado con cuota o límite de uso.

    Se usa cuando la cuenta alcanzó el límite permitido de solicitudes
    o cuando la API devuelve una señal de rate limit / quota exceeded.
    """
    pass


class GeminiRetryableError(Exception):
    """
    Error temporal del servicio.

    Representa fallos que podrían resolverse si se intenta nuevamente,
    por ejemplo errores internos del servidor o indisponibilidad temporal.
    """
    pass


class GeminiConnectionError(Exception):
    """
    Error de conexión de red.

    Se usa cuando la solicitud no pudo completarse por problemas
    de red, conexión interrumpida o fallas similares.
    """
    pass


# Estas excepciones representan errores del sistema de entrada por voz.
# Separarlas del resto permite que la interfaz maneje cada caso de forma
# más clara y con mensajes específicos para el usuario.


class VoiceTimeoutError(Exception):
    """
    Error lanzado cuando no se detecta voz dentro del tiempo esperado.
    """
    pass


class VoiceNoEntendidaError(Exception):
    """
    Error lanzado cuando se detecta audio, pero no se logra interpretar
    correctamente lo que la persona dijo.
    """
    pass


class VoiceServicioError(Exception):
    """
    Error relacionado con el servicio de reconocimiento de voz.

    Suele ocurrir cuando el proveedor externo falla o no responde
    correctamente.
    """
    pass


class VoiceMicrofonoError(Exception):
    """
    Error relacionado con el acceso al micrófono.

    Se usa cuando el dispositivo no está disponible, no tiene permisos,
    o existe un problema físico o del sistema operativo.
    """
    pass


# ==============================
# HELPER DE CLASIFICACIÓN DE ERRORES DE GEMINI
# ==============================

class GeminiSDKErrorHelper:
    """
    Utilidad encargada de interpretar errores provenientes del SDK de Gemini.

    Su responsabilidad es:
    - inspeccionar excepciones
    - clasificarlas en categorías más útiles para la aplicación
    - decidir si el error es reintentable
    - traducir el error a un mensaje comprensible para el usuario

    Esto evita que el resto del proyecto tenga que lidiar directamente con
    mensajes ambiguos o estructuras variables del SDK.
    """

    # Palabras clave que sugieren que el error podría resolverse reintentando.
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

    # Palabras clave asociadas a problemas de autenticación.
    ERRORES_API_KEY = (
        "api_key_invalid",
        "api key not valid",
        "api_key",
        "authentication",
        "unauthorized",
        "forbidden",
    )

    # Palabras clave asociadas a límites de uso o cuota.
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
        Intenta extraer un código numérico de estado desde la excepción.

        Algunos SDKs o clientes HTTP exponen el código bajo nombres distintos,
        como:
        - status_code
        - code
        - http_status

        Si no encuentra un entero válido, devuelve None.

        Args:
            error: Excepción original.

        Returns:
            Código numérico si existe, o None en caso contrario.
        """
        for attr in ("status_code", "code", "http_status"):
            value = getattr(error, attr, None)
            if isinstance(value, int):
                return value
        return None

    @staticmethod
    def obtener_mensaje(error: Exception) -> str:
        """
        Convierte la excepción en un mensaje normalizado.

        Se pasa todo a minúscula y se eliminan espacios sobrantes para facilitar
        las comparaciones por palabras clave.

        Args:
            error: Excepción original.

        Returns:
            Mensaje del error en formato normalizado.
        """
        return str(error).lower().strip()

    @classmethod
    def clasificar(cls, error: Exception) -> Exception:
        """
        Clasifica una excepción original dentro de una categoría más específica.

        La clasificación se basa en:
        - códigos HTTP conocidos
        - palabras clave encontradas en el mensaje del error

        Reglas principales:
        - 401 / 403 o mensajes de auth -> GeminiAuthError
        - 429 o mensajes de cuota      -> GeminiQuotaError
        - 500-504                      -> GeminiRetryableError
        - errores de red               -> GeminiConnectionError
        - otros errores temporales     -> GeminiRetryableError

        Si no logra identificar el caso, devuelve el error original.

        Args:
            error: Excepción original.

        Returns:
            Una excepción clasificada o el error original si no hubo match claro.
        """
        code = cls.obtener_codigo(error)
        mensaje = cls.obtener_mensaje(error)

        if code in {401, 403} or any(clave in mensaje for clave in cls.ERRORES_API_KEY):
            return GeminiAuthError(str(error))

        if code == 429 or any(clave in mensaje for clave in cls.ERRORES_CUOTA):
            return GeminiQuotaError(str(error))

        if code in {500, 502, 503, 504}:
            return GeminiRetryableError(str(error))

        if "connection" in mensaje or "network" in mensaje:
            return GeminiConnectionError(str(error))

        if any(clave in mensaje for clave in cls.ERRORES_REINTENTABLES):
            return GeminiRetryableError(str(error))

        return error

    @classmethod
    def es_reintentable(cls, error: Exception) -> bool:
        """
        Determina si un error vale la pena reintentarlo.

        Se considera reintentable si, luego de clasificarlo, resulta ser:
        - GeminiRetryableError
        - GeminiConnectionError

        Esto suele usarse para decidir si el sistema debe aplicar lógica
        de reintentos automáticos.

        Args:
            error: Excepción original.

        Returns:
            True si el error es reintentable, False en caso contrario.
        """
        clasificado = cls.clasificar(error)
        return isinstance(clasificado, (GeminiRetryableError, GeminiConnectionError))

    @classmethod
    def traducir(cls, error: Exception) -> str:
        """
        Traduce un error técnico a un mensaje simple y entendible para el usuario.

        Primero clasifica la excepción, y luego devuelve un texto claro según
        el tipo detectado.

        Si no se reconoce una categoría concreta, usa un mensaje genérico.

        Args:
            error: Excepción original.

        Returns:
            Mensaje amigable para mostrar en la interfaz.
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

        mensaje = cls.obtener_mensaje(error)
        if "timeout" in mensaje or "timed out" in mensaje or "deadline exceeded" in mensaje:
            return "La solicitud tardó demasiado. Intenta nuevamente."

        return "Ocurrió un error inesperado al comunicarse con Gemini."


def traducir_error(error: Exception) -> str:
    """
    Función de conveniencia para traducir errores de Gemini a texto legible.

    Esta función actúa como una fachada simple sobre GeminiSDKErrorHelper,
    para que otras partes del sistema no necesiten llamar directamente
    a la clase helper.

    Args:
        error: Excepción original.

    Returns:
        Mensaje entendible para el usuario.
    """
    return GeminiSDKErrorHelper.traducir(error)
