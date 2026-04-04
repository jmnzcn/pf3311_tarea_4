import os
import sys
from typing import Callable, Optional

from colorama import Fore, Style

from config import ALIASES_COMANDOS, Config, TEXTOS_UI
from errors import (
    VoiceMicrofonoError,
    VoiceNoEntendidaError,
    VoiceServicioError,
    VoiceTimeoutError,
)
from gemini_service import ChatService, GeminiChatService
from logging_setup import obtener_logger
from ui import (
    AnsiScreenController,
    ErrorPresenter,
    IndicadorEscritura,
    OutputManager,
    ScreenController,
    TerminalUI,
    hora_actual,
    normalizar_texto,
)
from voice import VoiceManager, VoiceService


class ChatController:
    """
    Controla el procesamiento de mensajes de texto dentro de la aplicación.

    Esta clase concentra la lógica necesaria para tomar un mensaje del usuario,
    enviarlo al servicio de chat, manejar errores del proceso y mostrar la
    respuesta final en la interfaz de terminal.

    Su objetivo es separar la responsabilidad de "procesar mensajes" del flujo
    principal de la CLI, manteniendo el código más organizado y fácil de mantener.
    """

    def __init__(
        self,
        config: Config,
        output: OutputManager,
        ui: TerminalUI,
        chat_service: ChatService,
        error_presenter: ErrorPresenter,
    ) -> None:
        """
        Inicializa el controlador de mensajes.

        Args:
            config: Configuración general de la aplicación.
            output: Manejador responsable de escribir en la terminal.
            ui: Componente de interfaz encargado de mostrar mensajes al usuario.
            chat_service: Servicio que envía mensajes al modelo conversacional.
            error_presenter: Componente encargado de mostrar errores de forma clara.
        """
        self.config = config
        self.output = output
        self.ui = ui
        self.chat_service = chat_service
        self.error_presenter = error_presenter


    def procesar_mensaje(self, texto: str) -> str:
        indicador = IndicadorEscritura(
            output=self.output,
            config=self.config,
            texto=f"{self.config.nombre_bot} está escribiendo",
        )

        logger = obtener_logger()
        logger.info("Procesando mensaje del usuario. Longitud=%s caracteres.", len(texto))

        try:
            indicador.iniciar()
            respuesta = self.chat_service.enviar_mensaje(texto)
            logger.info(
                "Respuesta generada correctamente. Longitud=%s caracteres.",
                len(respuesta),
            )

        except Exception as error:
            self.error_presenter.mostrar("Error procesando mensaje", error)
            return "Ocurrió un error procesando el mensaje."

        finally:
            indicador.detener()

        self.ui.imprimir_mensaje(self.config.nombre_bot, respuesta, Fore.CYAN)
        return respuesta


class CommandRouter:
    """
    Detecta y ejecuta comandos escritos por el usuario.

    Esta clase recibe un texto, lo normaliza y revisa si corresponde
    a un comando conocido. Si existe un handler asociado, lo ejecuta.

    Ejemplo:
        "ayuda"   -> ejecuta el handler del comando ayuda
        "clear"   -> se traduce a "limpiar"
        "exit"    -> se traduce a "salir"

    Esto permite mantener separada la lógica de comandos del loop principal.
    """

    def __init__(
        self,
        aliases: dict[str, str],
        handlers: dict[str, Callable[[], bool]],
    ) -> None:
        """
        Inicializa el router de comandos.

        Args:
            aliases: Diccionario que mapea aliases al nombre real del comando.
            handlers: Diccionario que mapea cada comando a su función ejecutora.
        """
        self.aliases = aliases
        self.handlers = handlers

    def detectar(self, texto: str) -> Optional[str]:
        """
        Determina si el texto recibido corresponde a un comando conocido.

        Antes de buscar el comando, el texto se normaliza:
        - se convierte a minúsculas
        - se eliminan espacios extra
        - se pueden remover acentos

        Args:
            texto: Texto ingresado por el usuario.

        Returns:
            El nombre canónico del comando si fue reconocido,
            o None si el texto no corresponde a ningún comando.
        """
        texto_normalizado = normalizar_texto(texto, quitar_acentos=True)
        return self.aliases.get(texto_normalizado)

    def ejecutar(self, texto: str) -> Optional[bool]:
        """
        Intenta ejecutar el comando correspondiente al texto dado.

        Convención de retorno:
            None  -> el texto no era un comando
            False -> sí era comando, pero la aplicación debe continuar
            True  -> sí era comando y la aplicación debe finalizar

        Args:
            texto: Texto ingresado por el usuario.

        Returns:
            Resultado de la ejecución del comando o None si no aplica.
        """
        cmd = self.detectar(texto)
        if cmd is None:
            return None

        handler = self.handlers.get(cmd)
        if handler is None:
            return False

        return handler()


class ChatCLI:
    """
    Representa la interfaz principal de línea de comandos de la aplicación.

    Esta clase coordina el flujo completo del programa:
    - inicialización del servicio de chat
    - lectura de entradas del usuario
    - ejecución de comandos
    - procesamiento de mensajes normales
    - captura de voz
    - control de finalización del programa

    En otras palabras, es el punto central que conecta todos los componentes.
    """

    def __init__(
        self,
        config: Config,
        input_fn: Callable[[str], str] = input,
        voice_service: Optional[VoiceService] = None,
        chat_service: Optional[ChatService] = None,
        screen_controller: Optional[ScreenController] = None,
        output: Optional[OutputManager] = None,
    ) -> None:
        """
        Inicializa la interfaz CLI y sus dependencias.

        Args:
            config: Configuración general de la aplicación.
            input_fn: Función utilizada para leer la entrada del usuario.
                      Se deja inyectable para facilitar pruebas.
            voice_service: Servicio de captura de voz opcional.
            chat_service: Servicio de chat opcional.
            screen_controller: Controlador opcional para limpiar pantalla.
            output: Manejador opcional de salida en terminal.

        Si algún componente no se proporciona, se crea una implementación
        por defecto.
        """
        self.config = config
        self.input_fn = input_fn

        # Manejador de salida sincronizada hacia la terminal.
        self.output = output or OutputManager(stream=sys.stdout)

        # Interfaz encargada de mostrar textos y mensajes formateados.
        self.ui = TerminalUI(self.output, config)

        # Controlador para operaciones de pantalla, como limpiar la terminal.
        self.screen = screen_controller or AnsiScreenController(stream=sys.stdout)

        # Servicio que permite capturar y transcribir voz.
        self.voice = voice_service or VoiceManager(config)

        # Servicio conversacional principal.
        self.chat_service = chat_service or GeminiChatService(config)

        # Encargado de mostrar errores de forma entendible al usuario.
        self.error_presenter = ErrorPresenter(config, self.ui)

        # Controlador dedicado al procesamiento de mensajes de texto.
        self.chat_controller = ChatController(
            config=config,
            output=self.output,
            ui=self.ui,
            chat_service=self.chat_service,
            error_presenter=self.error_presenter,
        )

        # Router encargado de traducir texto ingresado en comandos ejecutables.
        self.command_router = CommandRouter(
            aliases=ALIASES_COMANDOS.copy(),
            handlers={
                "salir": self._cmd_salir,
                "ayuda": self._cmd_ayuda,
                "limpiar": self._cmd_limpiar,
                "reiniciar": self._cmd_reiniciar,
                "voz": self._cmd_voz,
            },
        )

    def procesar_voz(self) -> None:
        """
        Ejecuta el flujo de entrada por voz.

        Este método:
        1. Verifica si la funcionalidad de voz está habilitada.
        2. Muestra al usuario que el sistema está escuchando.
        3. Captura y transcribe la voz.
        4. Si se reconoce texto, lo procesa como un mensaje normal.
        5. Si ocurre un error, muestra un mensaje apropiado.

        La captura de voz se trata como una entrada alternativa al texto escrito.
        """
        if not self.config.voz_habilitada:
            self.ui.imprimir_info(TEXTOS_UI["voz_deshabilitada"])
            obtener_logger().info("Intento de voz con entrada por voz deshabilitada.")
            return

        try:
            self.ui.imprimir_info(TEXTOS_UI["escuchando"])
            obtener_logger().info("Inicio de captura de voz.")

            texto = self.voice.escuchar()

            if not texto:
                self.ui.imprimir_info(TEXTOS_UI["voz_sin_texto"])
                obtener_logger().info("No se recibió texto desde la entrada por voz.")
                return

            obtener_logger().info("Texto reconocido por voz correctamente.")
            self.ui.imprimir_info(f"Reconocido: {texto}")

            # Una vez transcrito, el texto se procesa igual que cualquier
            # otro mensaje ingresado desde teclado.
            self.chat_controller.procesar_mensaje(texto)

        except VoiceTimeoutError:
            obtener_logger().warning("Timeout esperando voz del usuario.")
            self.ui.imprimir_info(TEXTOS_UI["voz_timeout"])

        except VoiceNoEntendidaError:
            obtener_logger().warning("No se pudo entender la voz del usuario.")
            self.ui.imprimir_info(TEXTOS_UI["voz_no_entendida"])

        except VoiceServicioError as error:
            obtener_logger().error("Error del reconocimiento de voz: %s", error)
            self.ui.imprimir_error(TEXTOS_UI["voz_error_servicio"])

        except VoiceMicrofonoError as error:
            obtener_logger().error("No se pudo acceder al micrófono: %s", error)
            self.ui.imprimir_error(TEXTOS_UI["voz_error_microfono"])

        except Exception as error:
            self.error_presenter.mostrar("Error inesperado con la voz", error)

    def inicializar(self) -> bool:
        """
        Inicializa el servicio de chat antes de arrancar la aplicación.

        Este método valida que la API key exista en el entorno y, si todo está
        correcto, inicializa el servicio conversacional.

        Returns:
            True si la inicialización fue exitosa.
            False si ocurrió algún problema.
        """
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key or not api_key.strip():
            self.ui.imprimir_error(TEXTOS_UI["error_falta_api_key"])
            obtener_logger().error(
                "No se encontró GEMINI_API_KEY en el entorno o está vacía."
            )
            return False

        try:
            self.chat_service.inicializar(api_key.strip())
            obtener_logger().info(
                "Servicio de chat inicializado correctamente con el modelo: %s",
                self.config.nombre_modelo,
            )
            return True

        except Exception as error:
            self.error_presenter.mostrar("Error inicializando Gemini", error)
            return False

    def run(self) -> None:
        """
        Ejecuta el loop principal de la aplicación.

        Flujo general:
        1. Inicializa el servicio conversacional.
        2. Muestra el encabezado de la interfaz.
        3. Espera entradas del usuario en un ciclo continuo.
        4. Si la entrada es un comando, lo ejecuta.
        5. Si no es un comando, la procesa como mensaje normal.
        6. Finaliza si el usuario interrumpe el proceso o ejecuta 'salir'.
        """
        if not self.inicializar():
            obtener_logger().warning(
                "La aplicación terminó porque no pudo inicializarse."
            )
            return

        self.ui.encabezado()
        obtener_logger().info("Loop principal iniciado.")

        while True:
            try:
                # Se agrega una línea en blanco para mejorar la separación visual
                # entre interacciones consecutivas.
                self.output.write()

                # Prompt visible para el usuario.
                prompt = Style.BRIGHT + Fore.GREEN + f"[{hora_actual()}] Tú: "

                # Se lee el texto escrito y se eliminan espacios sobrantes.
                texto = self.input_fn(prompt).strip()

            except (KeyboardInterrupt, EOFError):
                # Permite cerrar la aplicación de forma ordenada si el usuario
                # interrumpe manualmente la ejecución.
                self.output.write()
                self.ui.imprimir_info(TEXTOS_UI["fin"])
                obtener_logger().info("Salida por KeyboardInterrupt/EOF.")
                break

            # Si no se escribió nada, se ignora esta iteración.
            if not texto:
                continue

            obtener_logger().info("Entrada recibida del usuario.")

            # Primero se revisa si el texto corresponde a un comando.
            resultado_comando = self.command_router.ejecutar(texto)
            if resultado_comando is not None:
                obtener_logger().info(
                    "Comando ejecutado: %s",
                    self.command_router.detectar(texto),
                )

                # Si el comando devuelve True, se debe finalizar la aplicación.
                if resultado_comando:
                    obtener_logger().info(
                        "La aplicación finalizó por comando del usuario."
                    )
                    break

                # Si era comando pero no era de salida, se continúa el loop.
                continue

            # Si no era comando, se trata como mensaje normal.
            self.chat_controller.procesar_mensaje(texto)

        obtener_logger().info("Fin de la sesión.")

    def _cmd_salir(self) -> bool:
        """
        Ejecuta el comando 'salir'.

        Returns:
            True, indicando que la aplicación debe finalizar.
        """
        self.ui.imprimir_info(TEXTOS_UI["hasta_luego"])
        return True

    def _cmd_ayuda(self) -> bool:
        """
        Ejecuta el comando 'ayuda'.

        Muestra al usuario la lista de comandos disponibles.

        Returns:
            False, indicando que la aplicación debe continuar.
        """
        self.ui.imprimir_info(TEXTOS_UI["comandos"])
        return False

    def _cmd_limpiar(self) -> bool:
        """
        Ejecuta el comando 'limpiar'.

        Limpia la pantalla actual y vuelve a mostrar el encabezado principal.

        Returns:
            False, indicando que la aplicación debe continuar.
        """
        self.screen.clear()
        self.ui.encabezado()
        return False

    def _cmd_reiniciar(self) -> bool:
        """
        Ejecuta el comando 'reiniciar'.

        Reinicia la conversación actual del servicio de chat para empezar
        una nueva sesión sin contexto previo.

        Returns:
            False, indicando que la aplicación debe continuar.
        """
        try:
            self.chat_service.reiniciar_chat()
            obtener_logger().info("Conversación reiniciada por el usuario.")
            self.ui.imprimir_info(TEXTOS_UI["conversacion_reiniciada"])

        except Exception as error:
            self.error_presenter.mostrar("Error reiniciando conversación", error)

        return False

    def _cmd_voz(self) -> bool:
        """
        Ejecuta el comando 'voz'.

        Activa el flujo de captura por micrófono y procesa la transcripción
        como un mensaje del usuario.

        Returns:
            False, indicando que la aplicación debe continuar.
        """
        obtener_logger().info("Comando de voz ejecutado.")
        self.procesar_voz()
        return False
    