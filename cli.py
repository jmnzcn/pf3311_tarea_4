"""
cli.py es el archivo principal de la interfaz por terminal.

Aquí se organiza la comunicación entre el usuario y el bot.
El programa puede:
- recibir texto escrito
- reconocer comandos especiales
- escuchar voz desde el micrófono
- enviar mensajes al modelo de Gemini
- mostrar respuestas en pantalla
- leer respuestas en voz alta

La idea de este archivo es coordinar todo el flujo de la aplicación,
mientras otras partes del proyecto se encargan de tareas más específicas
como configuración, interfaz visual, voz, errores y conexión con Gemini.
"""


import os
import sys
import unicodedata
from typing import Callable

from colorama import Fore

# Importamos configuraciones generales del proyecto:
# - aliases de comandos
# - objeto de configuración
# - textos que se muestran en la interfaz
from config import ALIASES_COMANDOS, Config, TEXTOS_UI

# Importamos errores personalizados relacionados con la voz.
# Esto permite mostrar mensajes más claros según el problema ocurrido.
from errors import (
    VoiceMicrofonoError,
    VoiceNoEntendidaError,
    VoiceServicioError,
    VoiceTimeoutError,
)

# Importamos el contrato del servicio de chat y la implementación con Gemini.
from gemini_service import ChatService, GeminiChatService

# Logger principal del sistema.
from logging_setup import obtener_logger

# Componentes de la interfaz de terminal.
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

# Servicio de reconocimiento de voz.
from voice import VoiceManager, VoiceService

# Servicio de texto a voz.
from tts import TextToSpeechManager


# ==============================
# UTILIDADES
# ==============================

def _quitar_acentos(texto: str) -> str:
    """
    Esta función recibe un texto y devuelve ese mismo texto,
    pero sin acentos.

    Ejemplo:
    "canción" -> "cancion"

    Esto se usa para comparar palabras de forma más simple,
    sin que los acentos afecten la detección.
    """
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def detectar_idioma(texto: str, ultimo: str | None = None) -> str:
    """
    Esta función intenta adivinar si el mensaje está escrito
    en español o en inglés.

    La lógica es sencilla:
    - convierte el texto a minúsculas
    - le quita acentos
    - busca algunas palabras comunes en español
    - busca algunas palabras comunes en inglés

    Si encuentra más coincidencias en español, devuelve "es".
    Si encuentra más coincidencias en inglés, devuelve "en".
    Si no está claro, usa el último idioma detectado.
    Si tampoco existe uno anterior, devuelve "mixed".
    """
    texto = _quitar_acentos(texto.lower())

    es = {"hola", "gracias", "quiero", "puedo", "como", "porque"}
    en = {"hello", "thanks", "want", "can", "how", "because"}

    score_es = sum(1 for w in es if w in texto)
    score_en = sum(1 for w in en if w in texto)

    if score_es > score_en:
        return "es"
    if score_en > score_es:
        return "en"

    return ultimo or "mixed"


def quiere_voz(texto: str) -> bool:
    """
    Esta función revisa si el usuario está pidiendo explícitamente
    que la respuesta se diga en voz alta.

    Para eso busca ciertas frases clave como:
    - "léelo"
    - "dilo"
    - "read it"
    - "out loud"

    Si encuentra alguna, devuelve True.
    Si no, devuelve False.
    """
    texto = texto.lower()
    triggers = [
        "en voz",
        "léelo",
        "leelo",
        "dilo",
        "say it",
        "read it",
        "out loud",
    ]
    return any(t in texto for t in triggers)


# ==============================
# CONTROLADOR
# ==============================

class ChatController:
    """
    Esta clase se encarga del flujo principal cuando el usuario
    manda un mensaje al chat.

    Sus responsabilidades son:
    - detectar el idioma del mensaje
    - construir el prompt adecuado
    - enviar el mensaje al servicio de chat
    - mostrar la respuesta en pantalla
    - decidir si la respuesta también debe leerse en voz alta
    """

    def __init__(
        self,
        config: Config,
        output: OutputManager,
        ui: TerminalUI,
        chat_service: ChatService,
        error_presenter: ErrorPresenter,
        speech_output: TextToSpeechManager,
        get_hablar_una_vez: Callable[[], bool],
        set_hablar_una_vez: Callable[[bool], None],
        get_ultimo_idioma: Callable[[], str | None],
        set_ultimo_idioma: Callable[[str], None],
    ) -> None:
        # Guardamos todas las dependencias necesarias para que
        # esta clase pueda trabajar sin depender directamente
        # de variables globales.
        self.config = config
        self.output = output
        self.ui = ui
        self.chat_service = chat_service
        self.error_presenter = error_presenter
        self.speech_output = speech_output

        # Estas funciones permiten leer y cambiar estados externos,
        # como si la próxima respuesta debe hablarse o cuál fue
        # el último idioma usado.
        self.get_hablar_una_vez = get_hablar_una_vez
        self.set_hablar_una_vez = set_hablar_una_vez
        self.get_ultimo_idioma = get_ultimo_idioma
        self.set_ultimo_idioma = set_ultimo_idioma

        self.logger = obtener_logger()

    def _resumir_para_voz(self, texto: str, max_chars: int = 220) -> str:
        """
        Esta función acorta el texto para que el sistema de voz
        no lea respuestas demasiado largas.

        Primero limpia espacios extra.
        Si el texto es corto, lo devuelve completo.
        Si es muy largo, lo corta sin partir una palabra a la mitad
        y le agrega "..." al final.
        """
        texto = " ".join(texto.split()).strip()
        if len(texto) <= max_chars:
            return texto
        return texto[:max_chars].rsplit(" ", 1)[0] + "..."

    def procesar_mensaje(self, texto: str, desde_voz: bool = False) -> str | None:
        """
        Este es el método principal para procesar mensajes.

        Lo que hace es:
        1. Mostrar un indicador de "escribiendo"
        2. Detectar el idioma
        3. Preparar el prompt
        4. Enviar el mensaje al modelo
        5. Mostrar la respuesta
        6. Leerla en voz alta si corresponde
        """
        indicador = IndicadorEscritura(
            output=self.output,
            config=self.config,
            texto=f"{self.config.nombre_bot} está escribiendo",
        )

        # Detectamos el idioma del texto usando el último idioma
        # como respaldo si el mensaje actual no da una pista clara.
        idioma = detectar_idioma(texto, self.get_ultimo_idioma())

        # Según el idioma detectado, se le agrega una instrucción
        # al prompt para que Gemini responda en ese idioma.
        if idioma == "es":
            prompt = f"[Responde en español]\n{texto}"
        elif idioma == "en":
            prompt = f"[Respond in English]\n{texto}"
        else:
            prompt = texto

        try:
            # Inicia el indicador visual de que el bot está generando respuesta.
            indicador.iniciar()

            # Envía el mensaje al servicio de chat.
            respuesta = self.chat_service.enviar_mensaje(prompt)

        except Exception as error:
            # Si ocurre cualquier problema, se muestra un error amigable.
            self.error_presenter.mostrar("Error procesando mensaje", error)
            return None

        finally:
            # Siempre detenemos el indicador, aunque ocurra un error.
            indicador.detener()

        # Si se pudo detectar bien español o inglés,
        # guardamos ese idioma como referencia futura.
        if idioma in {"es", "en"}:
            self.set_ultimo_idioma(idioma)

        # Mostramos la respuesta del bot en la terminal.
        self.ui.imprimir_mensaje(self.config.nombre_bot, respuesta, Fore.CYAN)

        # Decidimos si la respuesta debe hablarse.
        # Se habla si:
        # - el mensaje vino desde el sistema de voz
        # - el usuario activó voz para la próxima respuesta
        # - el texto contiene una frase pidiéndolo explícitamente
        usar_voz = desde_voz or self.get_hablar_una_vez() or quiere_voz(texto)

        if usar_voz:
            try:
                # Se resume la respuesta para que el audio sea más práctico.
                respuesta_tts = self._resumir_para_voz(respuesta)
                self.speech_output.hablar(respuesta_tts, idioma)
            finally:
                # Después de usar la voz una vez, se apaga ese estado.
                self.set_hablar_una_vez(False)

        return respuesta


# ==============================
# ROUTER
# ==============================

class CommandRouter:
    """
    Esta clase se encarga de identificar y ejecutar comandos
    especiales escritos por el usuario.

    Por ejemplo:
    - ayuda
    - limpiar
    - reiniciar
    - salir

    También soporta aliases, o sea, distintas palabras que
    significan el mismo comando.
    """

    def __init__(
        self,
        aliases: dict[str, str],
        handlers: dict[str, Callable[[str], bool]],
    ) -> None:
        self.aliases = aliases
        self.handlers = handlers

    def detectar(self, texto: str) -> str | None:
        """
        Detecta si el primer término del texto corresponde
        a algún comando conocido.

        Primero normaliza el texto para que diferencias como
        mayúsculas, espacios o acentos no afecten el resultado.
        """
        texto = normalizar_texto(texto, quitar_acentos=True)
        return self.aliases.get(texto.split(" ")[0])

    def ejecutar(self, texto: str) -> bool:
        """
        Ejecuta el comando encontrado.

        Si no existe un handler para ese comando, devuelve False.
        Si existe, llama a la función asociada.
        """
        comando = normalizar_texto(texto, quitar_acentos=True).split(" ")[0]
        handler = self.handlers.get(comando)
        if not handler:
            return False
        return handler(texto)


# ==============================
# CLI
# ==============================

class ChatCLI:
    """
    Esta clase representa la aplicación principal en terminal.

    Aquí se conectan todos los componentes:
    - interfaz de usuario
    - entrada por teclado
    - voz
    - chat con Gemini
    - texto a voz
    - comandos especiales

    En otras palabras, esta es la clase que coordina todo.
    """

    def __init__(
        self,
        config: Config,
        input_fn: Callable[[str], str] = input,
        voice_service: VoiceService | None = None,
        chat_service: ChatService | None = None,
        screen_controller: ScreenController | None = None,
        output: OutputManager | None = None,
    ) -> None:
        self.config = config
        self.input_fn = input_fn
        self.logger = obtener_logger()

        # Si no se pasa un manejador de salida, usamos stdout por defecto.
        self.output = output or OutputManager(stream=sys.stdout)

        # Creamos la interfaz visual de terminal.
        self.ui = TerminalUI(self.output, config)

        # Controlador para limpiar pantalla.
        self.screen = screen_controller or AnsiScreenController(stream=sys.stdout)

        # Si no se inyectan servicios externos, se usan las implementaciones reales.
        self.voice = voice_service or VoiceManager(config)
        self.chat_service = chat_service or GeminiChatService(config)

        # Servicio encargado de leer respuestas en voz alta.
        self.speech_output = TextToSpeechManager(enabled=True)

        # Estado para indicar si la próxima respuesta debe hablarse.
        self.hablar_una_vez = False

        # Guarda el último idioma detectado para mejorar continuidad.
        self.ultimo_idioma = None

        # Encargado de presentar errores de forma amigable.
        self.error_presenter = ErrorPresenter(config, self.ui)

        # Controlador principal del flujo de mensajes.
        self.chat_controller = ChatController(
            config=config,
            output=self.output,
            ui=self.ui,
            chat_service=self.chat_service,
            error_presenter=self.error_presenter,
            speech_output=self.speech_output,
            get_hablar_una_vez=self._get_hablar_una_vez,
            set_hablar_una_vez=self._set_hablar_una_vez,
            get_ultimo_idioma=self._get_ultimo_idioma,
            set_ultimo_idioma=self._set_ultimo_idioma,
        )

        # Router de comandos disponibles en la terminal.
        self.router = CommandRouter(
            aliases=ALIASES_COMANDOS.copy(),
            handlers={
                "salir": self._cmd_salir,
                "ayuda": self._cmd_ayuda,
                "limpiar": self._cmd_limpiar,
                "reiniciar": self._cmd_reiniciar,
                "voz": self._cmd_voz,
                "escuchar": self._cmd_escuchar,
            },
        )

    # ==============================
    # ESTADO
    # ==============================

    def _get_hablar_una_vez(self) -> bool:
        """
        Devuelve si la próxima respuesta debe decirse en voz alta.
        """
        return self.hablar_una_vez

    def _set_hablar_una_vez(self, valor: bool):
        """
        Cambia el estado de hablar una sola vez.
        """
        self.hablar_una_vez = valor

    def _get_ultimo_idioma(self) -> str | None:
        """
        Devuelve el último idioma detectado.
        """
        return self.ultimo_idioma

    def _set_ultimo_idioma(self, idioma: str):
        """
        Guarda el último idioma detectado.
        """
        self.ultimo_idioma = idioma

    # ==============================
    # COMANDOS
    # ==============================

    def _cmd_voz(self, texto: str) -> bool:
        """
        Maneja el comando relacionado con la voz.

        Casos:
        - "voz"      -> muestra si está ON u OFF
        - "voz on"   -> activa voz para la próxima respuesta
        - "voz off"  -> desactiva voz
        """
        partes = texto.lower().split()

        if len(partes) == 1:
            estado = "ON" if self.hablar_una_vez else "OFF"
            self.ui.imprimir_info(f"Voz siguiente respuesta: {estado}")
            return False

        if partes[1] == "on":
            self.hablar_una_vez = True
            self.ui.imprimir_info("La próxima respuesta se dirá en voz.")
        elif partes[1] == "off":
            self.hablar_una_vez = False
            self.ui.imprimir_info("Voz desactivada.")

        return False

    def _cmd_escuchar(self, _: str) -> bool:
        """
        Activa el flujo de entrada por voz.

        Si la voz no está habilitada en la configuración,
        informa al usuario y no hace nada más.

        Si sí está habilitada:
        - marca que la próxima respuesta será hablada
        - inicia el proceso de escuchar por micrófono
        """
        if not self.config.voz_habilitada:
            self.ui.imprimir_info(TEXTOS_UI["voz_deshabilitada"])
            return False

        self.hablar_una_vez = True
        self.procesar_voz()
        return False

    def _cmd_salir(self, _: str) -> bool:
        """
        Devuelve True para indicar que el programa debe cerrar.
        """
        return True

    def _cmd_ayuda(self, _: str) -> bool:
        """
        Muestra la lista de comandos disponibles.
        """
        self.ui.imprimir_info(TEXTOS_UI["comandos"])
        return False

    def _cmd_limpiar(self, _: str) -> bool:
        """
        Limpia la pantalla de la terminal.
        """
        self.screen.clear()
        return False

    def _cmd_reiniciar(self, _: str) -> bool:
        """
        Reinicia la conversación actual con el modelo.
        Esto sirve para empezar un chat nuevo sin cerrar la aplicación.
        """
        self.chat_service.reiniciar_chat()
        self.ui.imprimir_info(TEXTOS_UI["conversacion_reiniciada"])
        return False

    # ==============================
    # VOZ INPUT
    # ==============================

    def procesar_voz(self):
        """
        Este método maneja todo el flujo de entrada por voz.

        Proceso general:
        1. Muestra mensaje de "escuchando"
        2. Intenta captar voz desde el micrófono
        3. Si reconoce texto, lo manda al chat
        4. Si ocurre un error, muestra un mensaje adecuado
        """
        try:
            self.ui.imprimir_info(TEXTOS_UI["escuchando"])
            texto = self.voice.escuchar()

            if texto:
                # Si sí se reconoció texto, se informa al usuario
                # y se procesa como si fuera un mensaje normal.
                self.ui.imprimir_info(f"Reconocido: {texto}")
                self.chat_controller.procesar_mensaje(texto, desde_voz=True)
            else:
                # Si no hubo texto reconocido, se avisa y se apaga
                # el modo de voz para la siguiente respuesta.
                self.ui.imprimir_info(TEXTOS_UI["voz_sin_texto"])
                self.hablar_una_vez = False

        except VoiceTimeoutError:
            # No se escuchó nada dentro del tiempo esperado.
            self.ui.imprimir_info(TEXTOS_UI["voz_timeout"])
            self.hablar_una_vez = False

        except VoiceNoEntendidaError:
            # Se escuchó algo, pero no se pudo entender.
            self.ui.imprimir_info(TEXTOS_UI["voz_no_entendida"])
            self.hablar_una_vez = False

        except VoiceServicioError:
            # Falló el servicio de reconocimiento.
            self.ui.imprimir_error(TEXTOS_UI["voz_error_servicio"])
            self.hablar_una_vez = False

        except VoiceMicrofonoError:
            # Hubo un problema con el micrófono o permisos.
            self.ui.imprimir_error(TEXTOS_UI["voz_error_microfono"])
            self.hablar_una_vez = False

    # ==============================
    # MAIN LOOP
    # ==============================

    def run(self):
        """
        Este método arranca la aplicación y mantiene el ciclo principal.

        Flujo general:
        1. Verifica que exista la API key de Gemini
        2. Inicializa el servicio de chat
        3. Muestra el encabezado de la app
        4. Entra en un loop infinito esperando mensajes del usuario
        5. Si el texto es un comando, lo ejecuta
        6. Si no es comando, lo manda al chat
        """
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            self.ui.imprimir_error(TEXTOS_UI["error_falta_api_key"])
            return

        # Inicializa el servicio de chat con la API key.
        self.chat_service.inicializar(api_key)

        # Muestra el encabezado inicial en la terminal.
        self.ui.encabezado()

        # Loop principal del programa.
        while True:
            texto = self.input_fn(f"[{hora_actual()}] Tú: ").strip()

            # Si el usuario no escribió nada, simplemente vuelve a pedir entrada.
            if not texto:
                continue

            # Revisa si el texto ingresado es un comando.
            comando = self.router.detectar(texto)

            if comando:
                # Si ejecutar devuelve True, significa que el programa debe salir.
                if self.router.ejecutar(texto):
                    break
                continue

            # Si no es comando, se procesa como un mensaje normal del chat.
            self.chat_controller.procesar_mensaje(texto)
            