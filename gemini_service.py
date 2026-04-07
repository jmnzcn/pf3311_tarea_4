"""
gemini_service.py se encarga de manejar toda la comunicación con Gemini.

Este archivo:
- define el contrato que debe cumplir cualquier servicio de chat
- implementa una clase concreta para trabajar con Gemini
- inicializa el cliente con API key
- crea y reinicia sesiones de chat
- envía mensajes al modelo
- usa reintentos automáticos cuando hay errores temporales
- detecta si una respuesta quedó truncada
- intenta continuar la respuesta si hace falta

La idea principal de este archivo es aislar toda la lógica del SDK de Gemini,
para que el resto del proyecto trabaje con una interfaz más limpia y simple.
"""

from typing import Any, Optional, Protocol  # Tipos para mejorar claridad y definir contratos entre clases

# SDK oficial de Gemini
from google import genai
from google.genai import types

# Configuración general del proyecto y textos de apoyo para la UI
from config import Config, TEXTOS_UI

# Helper que analiza errores y decide si se pueden reintentar
from errors import GeminiSDKErrorHelper

# Logger principal del sistema
from logging_setup import obtener_logger

# Sistema de reintentos automáticos
from retry import RetryConfig, ejecutar_con_reintentos


# ==============================
# CONTRATOS (INTERFACES)
# ==============================

class ChatService(Protocol):
    """
    Este protocolo define qué debe poder hacer cualquier servicio de chat.

    La idea es que el resto del sistema no dependa directamente de Gemini.
    Si en el futuro se quisiera usar otro proveedor, bastaría con crear
    otra clase que cumpla este mismo contrato.

    En otras palabras:
    este protocolo funciona como una "regla" que dice qué métodos
    debe tener un servicio de chat.
    """

    def inicializar(self, api_key: str) -> None:
        """
        Inicializa el servicio usando una API key.
        """
        ...

    def reiniciar_chat(self) -> None:
        """
        Reinicia la conversación actual.
        """
        ...

    def enviar_mensaje(self, texto: str, max_intentos: Optional[int] = None) -> str:
        """
        Envía un mensaje al modelo y devuelve la respuesta en texto.
        """
        ...


class GeminiResponseProtocol(Protocol):
    """
    Este protocolo representa la parte mínima de una respuesta
    que a este sistema le interesa.

    En este caso, lo importante es que exista una propiedad .text
    con el contenido generado.
    """

    @property
    def text(self) -> Optional[str]:
        """
        Texto generado por el modelo.
        """
        ...


class ChatSessionProtocol(Protocol):
    """
    Este protocolo representa una sesión de chat activa.

    Básicamente describe un objeto capaz de recibir mensajes
    dentro de una conversación ya iniciada.
    """

    def send_message(self, texto: str) -> GeminiResponseProtocol:
        """
        Envía un mensaje en la sesión actual y devuelve la respuesta.
        """
        ...


# ==============================
# IMPLEMENTACIÓN GEMINI
# ==============================

class GeminiChatService:
    """
    Esta clase es la implementación concreta del servicio de chat usando Gemini.

    Su objetivo principal es encapsular toda la lógica relacionada con el SDK,
    para que el resto del proyecto no tenga que preocuparse por detalles técnicos
    de Gemini.

    En resumen, esta clase:
    - inicializa el cliente
    - crea el chat
    - envía mensajes
    - maneja reintentos
    - detecta respuestas truncadas
    - intenta continuarlas si hace falta
    """

    def __init__(self, config: Config) -> None:
        # Guardamos la configuración general del sistema.
        # Aquí vienen cosas como:
        # - modelo a usar
        # - temperatura
        # - cantidad máxima de tokens
        self.config = config

        # Cliente del SDK.
        # Arranca en None porque todavía no se ha inicializado con la API key.
        self.client: Optional[genai.Client] = None

        # Sesión de chat activa.
        # También empieza en None hasta que se cree el chat.
        self.chat: Optional[ChatSessionProtocol] = None

        # Logger para registrar eventos, advertencias y errores.
        self.logger = obtener_logger()

    def inicializar(self, api_key: str) -> None:
        """
        Inicializa el cliente de Gemini.

        Este método:
        1. limpia la API key
        2. valida que no esté vacía
        3. crea el cliente oficial del SDK
        4. crea una nueva sesión de chat
        """

        # Quitamos espacios accidentales al inicio o final.
        api_key = api_key.strip()

        # Si la key está vacía, no tiene sentido continuar.
        if not api_key:
            raise ValueError("API key vacía")

        # Se crea el cliente de Gemini.
        self.client = genai.Client(api_key=api_key)

        # Después de crear el cliente, se crea una conversación nueva.
        self.chat = self._crear_chat()

    def reiniciar_chat(self) -> None:
        """
        Reinicia la conversación actual.

        En vez de borrar manualmente el historial, simplemente
        crea una nueva sesión de chat desde cero.
        """
        self.chat = self._crear_chat()

    def enviar_mensaje(self, texto: str, max_intentos: Optional[int] = None) -> str:
        """
        Este es el método principal de la clase.

        Su flujo general es:
        1. verificar que el chat esté listo
        2. crear configuración de reintentos
        3. enviar el mensaje al modelo
        4. extraer el texto útil de la respuesta
        5. revisar por qué terminó la generación
        6. si la respuesta quedó incompleta, intentar continuarla

        Al final, devuelve el texto final listo para usar.
        """

        # Verifica que exista una sesión de chat creada.
        self._asegurar_chat_inicializado()

        # Construye la configuración de reintentos.
        retry_config = self._crear_retry_config(max_intentos)

        # Envía el mensaje usando el sistema de reintentos automáticos.
        respuesta = self._enviar_con_reintentos(texto, retry_config)

        # Extrae el texto útil desde la respuesta del SDK.
        texto_final = self._extraer_texto_respuesta(respuesta)

        # Obtiene la razón por la que Gemini terminó de generar.
        finish_reason = self._finish_reason_normalizado(respuesta)

        # Si el modelo detuvo la respuesta por seguridad o por recitación,
        # no se intenta continuar.
        if self._bloquea_continuacion(finish_reason):
            self._log_bloqueo_continuacion(finish_reason)
            return texto_final

        # Si no hubo bloqueo, intenta completar la respuesta
        # en caso de que parezca truncada.
        return self._completar_respuesta_si_hace_falta(
            texto_final=texto_final,
            finish_reason=finish_reason,
            retry_config=retry_config,
        )

    def _asegurar_chat_inicializado(self) -> None:
        """
        Verifica que el chat ya haya sido creado.

        Si no existe, significa que alguien intentó usar el servicio
        antes de inicializarlo correctamente.
        """
        if self.chat is None:
            raise RuntimeError("Chat no inicializado")

    def _crear_retry_config(self, max_intentos: Optional[int]) -> RetryConfig:
        """
        Construye la configuración de reintentos.

        Si el usuario del método no pasa un valor específico,
        se usa el configurado globalmente en el proyecto.
        """
        return RetryConfig(
            max_intentos=max(1, max_intentos or self.config.max_intentos_api),
            backoff_inicial=1.0,
            backoff_factor=2.0,
            jitter_ratio=0.25,
        )

    def _crear_chat(self) -> ChatSessionProtocol:
        """
        Crea una nueva sesión de chat en Gemini.

        Aquí se aplica la configuración principal del modelo:
        - nombre del modelo
        - system prompt
        - temperatura
        - límite de tokens
        """
        if self.client is None:
            raise RuntimeError("Cliente no inicializado")

        return self.client.chats.create(
            model=self.config.nombre_modelo,
            config=types.GenerateContentConfig(
                system_instruction=self.config.system_prompt,
                temperature=self.config.temperatura,
                max_output_tokens=self.config.max_tokens,
            ),
        )

    def _enviar_con_reintentos(self, prompt: str, retry_config: RetryConfig) -> Any:
        """
        Envía un mensaje al modelo usando reintentos automáticos.

        Si ocurre un error temporal, el sistema puede volver a intentar
        la operación según la política definida en retry_config.
        """
        return ejecutar_con_reintentos(
            operacion=lambda: self.chat.send_message(prompt),  # llamada real al modelo
            retry_config=retry_config,
            es_reintentable=GeminiSDKErrorHelper.es_reintentable,
            logger=self.logger,
        )

    def _extraer_texto_respuesta(self, respuesta: GeminiResponseProtocol) -> str:
        """
        Extrae el texto útil desde la respuesta del modelo.

        Si la respuesta trae texto válido, lo limpia.
        Si no trae texto, devuelve un mensaje fallback.
        """
        texto = respuesta.text

        # Si el texto existe y no está vacío, se devuelve limpio.
        if isinstance(texto, str) and texto.strip():
            return texto.strip()

        # Si no vino nada útil, se usa un mensaje por defecto.
        return TEXTOS_UI["sin_respuesta"]

    def _obtener_finish_reason(self, respuesta: Any) -> Optional[str]:
        """
        Intenta averiguar por qué terminó la generación del modelo.

        Esto es importante porque permite saber si:
        - terminó normalmente
        - llegó al límite de tokens
        - fue bloqueado por seguridad
        - etc.

        Como el SDK puede traer esta información con distintos nombres,
        aquí se revisan varias posibilidades.
        """
        candidates = getattr(respuesta, "candidates", None)
        if not candidates:
            return None

        candidate = candidates[0]

        # Algunos SDKs usan finish_reason y otros finishReason.
        for attr in ("finish_reason", "finishReason"):
            value = getattr(candidate, attr, None)
            if value is not None:
                return str(value)

        # También se contempla el caso donde la respuesta venga como dict.
        if isinstance(candidate, dict):
            value = candidate.get("finish_reason") or candidate.get("finishReason")
            if value is not None:
                return str(value)

        return None

    def _finish_reason_normalizado(self, respuesta: Any) -> Optional[str]:
        """
        Normaliza el finish_reason para poder compararlo fácilmente.

        Por ejemplo:
        - lo pasa a mayúsculas
        - elimina espacios
        - toma la parte importante si viene con prefijo
        """
        finish_reason = self._obtener_finish_reason(respuesta)

        if finish_reason is None:
            return None

        return str(finish_reason).strip().upper().split(".")[-1]

    def _bloquea_continuacion(self, finish_reason: Optional[str]) -> bool:
        """
        Determina si NO se debe continuar la respuesta.

        Por ejemplo, si el modelo detuvo la salida por:
        - SAFETY
        - RECITATION

        En esos casos no conviene pedir continuación.
        """
        return finish_reason in {"SAFETY", "RECITATION"}

    def _debe_continuar(self, texto: str, finish_reason: Optional[str]) -> bool:
        """
        Decide si vale la pena pedir una continuación al modelo.

        Casos donde sí:
        - si el modelo terminó por MAX_TOKENS
        - si no hay finish_reason claro, pero el texto parece incompleto
        """

        # Caso explícito: el modelo se quedó sin espacio.
        if finish_reason == "MAX_TOKENS":
            return True

        # Caso heurístico: no hay razón clara, pero el texto "suena cortado".
        if finish_reason is None and self._parece_incompleta(texto):
            return True

        return False

    def _parece_incompleta(self, texto: str) -> bool:
        """
        Heurística simple para detectar si una respuesta
        parece haber quedado incompleta.

        No es una regla perfecta, pero ayuda bastante.

        La idea es revisar si el texto:
        - termina con signos que sugieren continuación
        - o no termina como normalmente terminaría una frase
        """
        texto = texto.strip()

        # Si está vacío o es demasiado corto, no se considera truncado.
        if not texto or len(texto) < 20:
            return False

        return (
            texto.endswith(("(", ",", ":", ";", "-"))
            or not texto.endswith((".", "!", "?", "\"", "”", ")", "]"))
        )

    def _completar_respuesta_si_hace_falta(
        self,
        texto_final: str,
        finish_reason: Optional[str],
        retry_config: RetryConfig,
    ) -> str:
        """
        Intenta completar respuestas truncadas.

        Si detecta que la salida parece incompleta,
        le pide al modelo que continúe exactamente donde se quedó.

        Para evitar loops infinitos, solo permite un número limitado
        de continuaciones.
        """
        max_continuaciones = 2
        intentos_continuacion = 0

        while intentos_continuacion < max_continuaciones:
            # Si ya no hace falta continuar, se sale del loop.
            if not self._debe_continuar(texto_final, finish_reason):
                break

            self.logger.warning(
                "Respuesta posiblemente truncada. finish_reason=%r. Solicitando continuación.",
                finish_reason,
            )

            # Se le pide al modelo continuar sin repetir lo anterior.
            respuesta_extra = self._enviar_con_reintentos(
                "Continuá exactamente donde te quedaste, sin repetir nada de lo anterior.",
                retry_config,
            )

            extra_texto = self._extraer_texto_respuesta(respuesta_extra).strip()

            # Si no vino texto útil, se detiene.
            if not extra_texto or extra_texto == TEXTOS_UI["sin_respuesta"]:
                break

            # Se agrega la continuación al texto original.
            texto_final += "\n" + extra_texto

            # Se actualiza la nueva razón de finalización.
            finish_reason = self._finish_reason_normalizado(respuesta_extra)
            intentos_continuacion += 1

            # Si el modelo ahora bloquea la continuación, se corta.
            if self._bloquea_continuacion(finish_reason):
                break

        return texto_final

    def _log_bloqueo_continuacion(self, finish_reason: Optional[str]) -> None:
        """
        Registra en logs cuando Gemini detiene una respuesta
        por motivos que no permiten continuar.
        """
        self.logger.warning(
            "Respuesta detenida por finish_reason=%s. No se intentará continuación.",
            finish_reason,
        )
