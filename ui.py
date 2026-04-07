"""
ui.py se encarga de todo lo relacionado con la interfaz en la terminal.

Incluye:
- utilidades para manejar texto y tiempo
- un sistema seguro de escritura en consola (OutputManager)
- control de pantalla (limpiar terminal)
- la interfaz principal (TerminalUI)
- una animación de "escribiendo"
- manejo y presentación de errores amigables

La idea es separar completamente la lógica de presentación
del resto del sistema, para que el código sea más ordenado y mantenible.
"""

import sys  # Permite escribir en la consola (stdout)
import threading  # Permite usar hilos (para animaciones)
import unicodedata  # Permite manipular texto (acentos, etc.)
from datetime import datetime  # Para obtener fecha y hora
from typing import Any, Callable, ContextManager, Optional, Protocol, TextIO

# Librería para colores en terminal
from colorama import Fore, Style

# Configuración global del sistema
from config import COMANDOS_DISPONIBLES, Config

# Función que convierte errores técnicos en mensajes amigables
from errors import traducir_error

# Logger del sistema
from logging_setup import obtener_logger


# ==============================
# UTILIDADES DE TEXTO Y TIEMPO
# ==============================

def normalizar_texto(texto: str, quitar_acentos: bool = False) -> str:
    """
    Esta función sirve para limpiar texto y facilitar comparaciones.

    Lo que hace:
    - convierte todo a minúsculas
    - elimina espacios extra
    - opcionalmente quita acentos

    Esto es útil para comparar comandos escritos por el usuario.
    """

    texto = " ".join(texto.strip().lower().split())

    if not quitar_acentos:
        return texto

    # Elimina acentos usando Unicode
    return "".join(
        c
        for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


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
    Esta clase se encarga de escribir en consola de forma segura.

    Problema:
    Si varios hilos escriben al mismo tiempo, el texto se mezcla.

    Solución:
    Usa un lock para que solo un hilo escriba a la vez.
    """

    def __init__(self, stream: Optional[TextIO] = None) -> None:
        self._stream = stream or sys.stdout  # salida estándar
        self._lock = threading.Lock()  # evita conflictos entre hilos

    def write(self, text: str = "", end: str = "\n", flush: bool = True) -> None:
        """
        Escribe una línea completa en consola.
        """
        with self._lock:
            self._stream.write(text + end)
            if flush:
                self._stream.flush()

    def write_inline(self, text: str, flush: bool = True) -> None:
        """
        Escribe texto sin salto de línea.
        Útil para animaciones.
        """
        with self._lock:
            self._stream.write(text)
            if flush:
                self._stream.flush()

    def clear_current_line(self, width: int) -> None:
        """
        Limpia la línea actual en la consola.

        Se usa para borrar animaciones.
        """
        with self._lock:
            self._stream.write("\r" + (" " * width) + "\r")
            self._stream.flush()


# ==============================
# CONTROL DE PANTALLA
# ==============================

class ScreenController(Protocol):
    """
    Define una interfaz para limpiar la pantalla.

    Esto permite cambiar la implementación sin romper el código.
    """

    def clear(self) -> None:
        ...


class AnsiScreenController:
    """
    Implementación que usa códigos ANSI para limpiar la terminal.
    """

    def __init__(self, stream: Optional[TextIO] = None) -> None:
        self._stream = stream or sys.stdout

    def clear(self) -> None:
        """
        Limpia la pantalla usando códigos ANSI.
        """
        self._stream.write("\033[2J\033[H")
        self._stream.flush()


# ==============================
# INTERFAZ DE USUARIO
# ==============================

class TerminalUI:
    """
    Esta clase se encarga de mostrar todo en la terminal.

    Centraliza:
    - encabezado
    - mensajes
    - errores
    - información
    """

    def __init__(self, output: OutputManager, config: Config) -> None:
        self._output = output
        self._config = config
        self._nombre_bot = config.nombre_bot

    def linea(self, char: str = "=", largo: Optional[int] = None, color: str = Fore.WHITE) -> None:
        """
        Dibuja una línea decorativa.
        """
        ancho = largo or self._config.ui_ancho
        self._output.write(color + (char * ancho))

    def encabezado(self) -> None:
        """
        Muestra la pantalla inicial del programa.
        """
        ancho = self._config.ui_ancho

        self.linea("=", ancho, Fore.CYAN)
        self._output.write(Style.BRIGHT + Fore.CYAN + self._nombre_bot.center(ancho))
        self.linea("=", ancho, Fore.CYAN)

        self._output.write(Fore.WHITE + f"Sesión iniciada: {timestamp_actual()}")

        # Lista de comandos disponibles
        self._output.write(Fore.YELLOW + "Comandos:")
        for comando in COMANDOS_DISPONIBLES:
            self._output.write(Fore.YELLOW + f"  {comando}")

        self.linea("-", ancho, Fore.BLUE)
        self._output.write()

    def imprimir_mensaje(self, autor: str, texto: str, color: str = Fore.WHITE) -> None:
        """
        Imprime un mensaje con formato:

        [hora] Autor:
        mensaje
        """
        self._output.write()
        self._output.write(f"{Style.BRIGHT}{color}[{hora_actual()}] {autor}:")
        self._output.write(f"{color}{texto}")
        self._output.write()

    def imprimir_error(self, texto: str) -> None:
        """
        Muestra errores en rojo.
        """
        self.imprimir_mensaje("Error", texto, Fore.RED)

    def imprimir_info(self, texto: str) -> None:
        """
        Muestra información en magenta.
        """
        self.imprimir_mensaje("Info", texto, Fore.MAGENTA)


# ==============================
# INDICADOR DE ESCRITURA
# ==============================

class IndicadorEscritura:
    """
    Muestra una animación tipo:
    "Escribiendo..."
    """

    def __init__(self, output: OutputManager, config: Config, texto: str = "Escribiendo") -> None:
        self._output = output
        self._config = config
        self._texto = texto

        self._stop_event = threading.Event()  # controla cuándo detener la animación
        self._thread: Optional[threading.Thread] = None  # hilo de animación

    def iniciar(self) -> None:
        """
        Inicia la animación en un hilo separado.
        """
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._animar, daemon=True)
        self._thread.start()

    def detener(self) -> None:
        """
        Detiene la animación.
        """
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.2)

        # Limpia la línea de animación
        self._output.clear_current_line(self._config.ui_ancho_limpieza_linea)

    def _animar(self) -> None:
        """
        Loop que actualiza la animación.
        """
        while not self._stop_event.is_set():
            for puntos in (".", "..", "..."):
                if self._stop_event.is_set():
                    break

                texto = f"\r{self._texto}{puntos}".ljust(self._config.ui_ancho_limpieza_linea)
                self._output.write_inline(texto)

                if self._stop_event.wait(self._config.ui_intervalo_indicador):
                    break


# ==============================
# PRESENTACIÓN DE ERRORES
# ==============================

class ErrorPresenter:
    """
    Maneja errores separando:

    - logs técnicos (para desarrolladores)
    - mensajes amigables (para usuario)
    """

    def __init__(self, config: Config, ui: TerminalUI) -> None:
        self._config = config
        self._ui = ui
        self._logger = obtener_logger()

    def mostrar(self, mensaje_log: str, error: Exception) -> None:
        """
        Maneja un error completo.
        """

        # Guarda el error en logs
        if self._config.mostrar_traza_error:
            self._logger.exception("%s", mensaje_log)
        else:
            self._logger.error("%s: %s", mensaje_log, error)

        # Traduce el error a algo entendible
        mensaje_usuario = traducir_error(error)

        # Lo muestra en la interfaz
        self._ui.imprimir_error(mensaje_usuario)
