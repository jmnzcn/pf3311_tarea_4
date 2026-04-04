from typing import Any, Optional, Protocol

from google import genai
from google.genai import types

from config import Config, TEXTOS_UI
from errors import GeminiSDKErrorHelper
from logging_setup import obtener_logger
from retry import RetryConfig, ejecutar_con_reintentos


# ==============================
# PROTOCOLOS / CONTRATOS
# ==============================

class ChatService(Protocol):
    """
    Define el contrato esperado para un servicio de chat.

    Cualquier implementación que quiera funcionar como servicio conversacional
    debe poder:
    - inicializarse con una API key
    - reiniciar la conversación
    - enviar mensajes y devolver una respuesta en texto
    """

    def inicializar(self, api_key: str) -> None:
        """
        Inicializa el servicio con la API key correspondiente.
        """
        ...

    def reiniciar_chat(self) -> None:
        """
        Reinicia la sesión de conversación actual.
        """
        ...

    def enviar_mensaje(self, texto: str, max_intentos: Optional[int] = None) -> str:
        """
        Envía un mensaje al modelo y devuelve la respuesta como texto.
        """
        ...


class GeminiResponseProtocol(Protocol):
    """
    Describe la parte mínima de una respuesta de Gemini que esta aplicación usa.

    En este caso, solo interesa la propiedad `text`, que representa
    la respuesta textual principal del modelo.
    """

    @property
    def text(self) -> Optional[str]:
        """
        Texto principal devuelto por el modelo.
        """
        ...


class ChatSessionProtocol(Protocol):
    """
    Describe la interfaz mínima de una sesión de chat.

    Este protocolo permite trabajar con una abstracción del chat activo
    sin depender completamente del tipo concreto del SDK.
    """

    def send_message(self, texto: str) -> GeminiResponseProtocol:
        """
        Envía un mensaje dentro de la sesión activa y devuelve la respuesta.
        """
        ...


# ==============================
# IMPLEMENTACIÓN CON GEMINI
# ==============================

class GeminiChatService:
    """
    Implementación concreta del servicio de chat usando Google Gemini.

    Esta clase encapsula toda la lógica necesaria para:
    - crear el cliente de Gemini
    - abrir una sesión de chat
    - enviar mensajes al modelo
    - manejar reintentos automáticos
    - detectar respuestas incompletas y continuarlas si hace falta

    Su propósito es que el resto del sistema no tenga que interactuar
    directamente con los detalles del SDK.
    """

    def __init__(self, config: Config) -> None:
        """
        Inicializa el servicio con la configuración general de la aplicación.

        Args:
            config: Objeto de configuración con modelo, temperatura,
                    límite de tokens y demás opciones necesarias.
        """
        self.config = config
        self.client: Optional[genai.Client] = None
        self.chat: Optional[ChatSessionProtocol] = None
        self.logger = obtener_logger()

    def inicializar(self, api_key: str) -> None:
        """
        Inicializa el cliente de Gemini y crea una sesión de chat.

        Antes de hacerlo, valida que la API key no esté vacía.

        Args:
            api_key: Clave de acceso a la API de Gemini.

        Raises:
            ValueError: Si la API key está vacía.
        """
        api_key = api_key.strip()
        if not api_key:
            raise ValueError("API key vacía")

        self.client = genai.Client(api_key=api_key)
        self.chat = self._crear_chat()

    def _crear_chat(self) -> ChatSessionProtocol:
        """
        Crea una nueva sesión de chat con Gemini usando la configuración actual.

        Usa:
        - modelo configurado
        - system prompt
        - temperatura
        - máximo de tokens de salida

        Returns:
            Una nueva sesión activa de chat.

        Raises:
            RuntimeError: Si el cliente todavía no ha sido inicializado.
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

    def _extraer_texto_respuesta(self, respuesta: GeminiResponseProtocol) -> str:
        """
        Extrae el texto útil de una respuesta del modelo.

        Si la respuesta contiene texto válido, lo limpia y lo devuelve.
        Si no, devuelve un mensaje por defecto definido en TEXTOS_UI.

        Args:
            respuesta: Respuesta generada por Gemini.

        Returns:
            Texto listo para mostrar al usuario.
        """
        texto = respuesta.text
        if isinstance(texto, str) and texto.strip():
            return texto.strip()

        return TEXTOS_UI["sin_respuesta"]

    def _obtener_finish_reason(self, respuesta: Any) -> Optional[str]:
        """
        Intenta obtener la razón por la cual Gemini terminó de generar la respuesta.

        El SDK puede exponer este dato con distintos nombres o estructuras,
        por lo que este método intenta leerlo de forma flexible.

        Busca:
        - finish_reason
        - finishReason

        Returns:
            La razón de finalización como string, o None si no está disponible.
        """
        candidates = getattr(respuesta, "candidates", None)
        if not candidates:
            return None

        candidate = candidates[0]

        for attr in ("finish_reason", "finishReason"):
            value = getattr(candidate, attr, None)
            if value is not None:
                return str(value)

        if isinstance(candidate, dict):
            value = candidate.get("finish_reason") or candidate.get("finishReason")
            if value is not None:
                return str(value)

        return None

    def _normalizar_finish_reason(self, finish_reason: Optional[str]) -> Optional[str]:
        """
        Normaliza el valor de finish_reason para facilitar comparaciones.

        Convierte el valor a string, elimina espacios sobrantes,
        lo pasa a mayúscula y se queda con la última parte si viene
        en un formato más largo como 'FinishReason.MAX_TOKENS'.

        Args:
            finish_reason: Valor original obtenido de la respuesta.

        Returns:
            Valor normalizado o None si no había dato.
        """
        if finish_reason is None:
            return None

        return str(finish_reason).strip().upper().split(".")[-1]

    def _parece_incompleta(self, texto: str) -> bool:
        """
        Evalúa heurísticamente si una respuesta parece haber quedado cortada.

        Esta validación sirve como respaldo cuando el SDK no devuelve
        un finish_reason claro.

        Criterios usados:
        - no evaluar textos demasiado cortos
        - considerar sospechoso si termina en ciertos signos de corte
        - considerar sospechoso si no termina con puntuación esperada

        Args:
            texto: Respuesta generada por el modelo.

        Returns:
            True si parece incompleta, False en caso contrario.
        """
        texto = texto.strip()
        if not texto:
            return False

        # Si el texto es muy corto, no vale la pena suponer truncamiento.
        if len(texto) < 20:
            return False

        return (
            texto.endswith(("(", ",", ":", ";", "-"))
            or not texto.endswith((".", "!", "?", "\"", "”", ")", "]"))
        )

    def reiniciar_chat(self) -> None:
        """
        Reinicia la conversación actual creando una nueva sesión de chat.

        Esto permite comenzar una conversación limpia, sin arrastrar
        el contexto previo acumulado.
        """
        self.chat = self._crear_chat()

    def enviar_mensaje(self, texto: str, max_intentos: Optional[int] = None) -> str:
        """
        Envía un mensaje al modelo y devuelve la respuesta final en texto.

        Este método también:
        - aplica reintentos automáticos si el error lo amerita
        - revisa si la respuesta pudo quedar truncada
        - pide continuación automática cuando corresponde

        Args:
            texto: Mensaje del usuario.
            max_intentos: Número máximo de reintentos para la solicitud.
                          Si no se indica, se usa el valor de la configuración.

        Returns:
            Respuesta final lista para mostrar.

        Raises:
            RuntimeError: Si todavía no existe una sesión de chat activa.
        """
        if self.chat is None:
            raise RuntimeError("Chat no inicializado")

        # Configuración de reintentos para solicitudes a Gemini.
        retry_config = RetryConfig(
            max_intentos=max(1, max_intentos or self.config.max_intentos_api),
            backoff_inicial=1.0,
            backoff_factor=2.0,
            jitter_ratio=0.25,
        )

        def enviar(prompt: str) -> Any:
            """
            Función interna que encapsula el envío de un mensaje con lógica
            de reintentos automáticos.
            """
            return ejecutar_con_reintentos(
                operacion=lambda: self.chat.send_message(prompt),
                retry_config=retry_config,
                es_reintentable=GeminiSDKErrorHelper.es_reintentable,
                logger=self.logger,
            )

        # Se envía el mensaje original del usuario.
        respuesta = enviar(texto)
        texto_final = self._extraer_texto_respuesta(respuesta)
        finish_reason = self._normalizar_finish_reason(
            self._obtener_finish_reason(respuesta)
        )

        # Si Gemini frenó por seguridad o recitación,
        # no se intenta continuación automática.
        if finish_reason in {"SAFETY", "RECITATION"}:
            self.logger.warning(
                "Respuesta detenida por finish_reason=%s. No se intentará continuación.",
                finish_reason,
            )
            return texto_final

        # Se permiten hasta dos continuaciones automáticas
        # en caso de truncamiento.
        intentos_continuacion = 0
        max_continuaciones = 2

        while intentos_continuacion < max_continuaciones:
            continuar = False

            # Caso 1: Gemini indicó explícitamente que se cortó por límite de tokens.
            if finish_reason == "MAX_TOKENS":
                continuar = True

            # Caso 2: no hay finish_reason claro, pero el texto parece incompleto.
            elif finish_reason is None and self._parece_incompleta(texto_final):
                continuar = True

            # Si no hay razón válida para continuar, se termina el ciclo.
            if not continuar:
                break

            self.logger.warning(
                "Respuesta posiblemente truncada. finish_reason=%r. Solicitando continuación.",
                finish_reason,
            )

            # Se le pide al modelo que continúe exactamente desde donde quedó.
            respuesta_extra = enviar(
                "Continuá exactamente donde te quedaste, sin repetir nada de lo anterior."
            )
            extra_texto = self._extraer_texto_respuesta(respuesta_extra).strip()

            # Si no se obtuvo texto útil adicional, se deja de continuar.
            if not extra_texto or extra_texto == TEXTOS_UI["sin_respuesta"]:
                break

            # Se agrega la continuación al texto acumulado.
            texto_final += "\n" + extra_texto
            finish_reason = self._normalizar_finish_reason(
                self._obtener_finish_reason(respuesta_extra)
            )
            intentos_continuacion += 1

            # Si la continuación se frenó por seguridad o recitación,
            # también se corta el proceso.
            if finish_reason in {"SAFETY", "RECITATION"}:
                break

        return texto_final
    