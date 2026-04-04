import sys
import threading
import unicodedata
from datetime import datetime
from typing import Optional, Protocol, TextIO

from colorama import Fore, Style

from config import COMANDOS_DISPONIBLES, Config
from errors import traducir_error
from logging_setup import obtener_logger


# ==============================
# UTILIDADES DE TEXTO Y TIEMPO
# ==============================

def normalizar_texto(texto: str, quitar_acentos: bool = False) -> str:
    """
    Normaliza un texto para facilitar comparaciones.

    Hace:
    - minúsculas
    - elimina espacios extra
    - opcionalmente elimina acentos

    Útil para comparar comandos como:
    "  AyÚda  " -> "ayuda"
    """
    texto = " ".join(texto.strip().lower().split())

    if quitar_acentos:
        texto = "".join(
            c
            for c in unicodedata.normalize("NFD", texto)
            if unicodedata.category(c) != "Mn"
        )

    return texto


def hora_actual() -> str:
    """
    Devuelve la hora actual en formato HH:MM.
    """
    return datetime.now().strftime("%H:%M")


def timestamp_actual() -> str:
    """
    Devuelve fecha y hora completa.
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ==============================
# SALIDA SEGURA EN TERMINAL
# ==============================

class OutputManager:
    """
    Maneja la escritura en consola de forma segura.

    Usa un lock para evitar que múltiples hilos escriban al mismo tiempo,
    lo cual es importante porque hay animaciones (indicador de escritura).
    """

    def __init__(self, stream: Optional[TextIO] = None) -> None:
        self.stream = stream or sys.stdout
        self.lock = threading.Lock()

    def write(self, text: str = "", end: str = "\n", flush: bool = True) -> None:
        """
        Escribe una línea completa en consola.
        """
        with self.lock:
            self.stream.write(text + end)
            if flush:
                self.stream.flush()

    def write_inline(self, text: str, flush: bool = True) -> None:
        """
        Escribe sin salto de línea (útil para animaciones).
        """
        with self.lock:
            self.stream.write(text)
            if flush:
                self.stream.flush()

    def clear_current_line(self, width: int) -> None:
        """
        Limpia la línea actual en consola.
        """
        with self.lock:
            self.stream.write("\r" + " " * width + "\r")
            self.stream.flush()


# ==============================
# CONTROL DE PANTALLA
# ==============================

class ScreenController(Protocol):
    """
    Define el comportamiento esperado para limpiar la pantalla.
    """

    def clear(self) -> None:
        ...


class AnsiScreenController:
    """
    Implementación usando códigos ANSI para limpiar la terminal.
    """

    def __init__(self, stream: Optional[TextIO] = None) -> None:
        self.stream = stream or sys.stdout

    def clear(self) -> None:
        """
        Limpia completamente la pantalla y posiciona el cursor arriba.
        """
        self.stream.write("\033[2J\033[H")
        self.stream.flush()


# ==============================
# INTERFAZ DE USUARIO (UI)
# ==============================

class TerminalUI:
    """
    Encargado de mostrar todo en la terminal.

    Centraliza:
    - encabezado
    - mensajes del bot
    - mensajes informativos
    - errores
    """

    def __init__(self, output: OutputManager, config: Config) -> None:
        self.output = output
        self.config = config
        self.nombre_bot = config.nombre_bot

    def linea(self, char: str = "=", largo: Optional[int] = None, color: str = Fore.WHITE) -> None:
        """
        Dibuja una línea horizontal decorativa.
        """
        largo = largo or self.config.ui_ancho
        self.output.write(color + char * largo)

    def encabezado(self) -> None:
        """
        Muestra el encabezado inicial de la aplicación.
        """
        ancho = self.config.ui_ancho

        self.linea("=", ancho, Fore.CYAN)
        self.output.write(Style.BRIGHT + Fore.CYAN + f"{self.nombre_bot.center(ancho)}")
        self.linea("=", ancho, Fore.CYAN)

        self.output.write(Fore.WHITE + f"Sesión iniciada: {timestamp_actual()}")

        self.output.write(Fore.YELLOW + "Comandos:")
        for comando in COMANDOS_DISPONIBLES:
            self.output.write(Fore.YELLOW + f"  {comando}")

        self.linea("-", ancho, Fore.BLUE)
        self.output.write()

    def imprimir_mensaje(self, autor: str, texto: str, color: str = Fore.WHITE) -> None:
        """
        Imprime un mensaje con formato (hora + autor).
        """
        self.output.write()
        self.output.write(f"{Style.BRIGHT}{color}[{hora_actual()}] {autor}:")
        self.output.write(f"{color}{texto}")
        self.output.write()

    def imprimir_error(self, texto: str) -> None:
        """
        Muestra un mensaje de error en rojo.
        """
        self.imprimir_mensaje("Error", texto, Fore.RED)

    def imprimir_info(self, texto: str) -> None:
        """
        Muestra un mensaje informativo en color magenta.
        """
        self.imprimir_mensaje("Info", texto, Fore.MAGENTA)


# ==============================
# INDICADOR DE ESCRITURA
# ==============================

class IndicadorEscritura:
    """
    Muestra una animación tipo:
    "Escribiendo..."
    
    Se ejecuta en un hilo separado para no bloquear el programa principal.
    """

    def __init__(self, output: OutputManager, config: Config, texto: str = "Escribiendo") -> None:
        self.output = output
        self.config = config
        self.texto = texto
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def iniciar(self) -> None:
        """
        Inicia la animación en un hilo.
        """
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._animar, daemon=True)
        self._thread.start()

    def detener(self) -> None:
        """
        Detiene la animación y limpia la línea.
        """
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.2)

        self.output.clear_current_line(self.config.ui_ancho_limpieza_linea)

    def _animar(self) -> None:
        """
        Loop interno que actualiza la animación.
        """
        while not self._stop_event.is_set():
            for puntos in (".", "..", "..."):
                if self._stop_event.is_set():
                    break

                texto = f"\r{self.texto}{puntos}".ljust(self.config.ui_ancho_limpieza_linea)
                self.output.write_inline(texto)

                if self._stop_event.wait(self.config.ui_intervalo_indicador):
                    break


# ==============================
# PRESENTACIÓN DE ERRORES
# ==============================

class ErrorPresenter:
    """
    Encargado de mostrar errores al usuario de forma clara.

    Separa:
    - logging técnico
    - mensaje amigable al usuario
    """

    def __init__(self, config: Config, ui: TerminalUI) -> None:
        self.config = config
        self.ui = ui
        self.logger = obtener_logger()

    def mostrar(self, mensaje_log: str, error: Exception) -> None:
        """
        Muestra un error:

        - lo registra en logs
        - lo traduce a un mensaje entendible
        - lo imprime en la UI
        """

        # Logging técnico (con o sin stack trace)
        if self.config.mostrar_traza_error:
            self.logger.exception("%s", mensaje_log)
        else:
            self.logger.error("%s: %s", mensaje_log, error)

        # Mensaje amigable para el usuario
        mensaje_usuario = traducir_error(error)
        self.ui.imprimir_error(mensaje_usuario)
        