"""
tts.py se encarga de manejar la funcionalidad de texto a voz (TTS).

No genera audio directamente, sino que:
- recibe el texto
- lo guarda en un archivo temporal
- ejecuta un script externo (tts_worker.py)

Esto permite que la generación de audio se haga en un proceso separado,
evitando que el programa principal se bloquee.

También valida si existe la API key necesaria para usar ElevenLabs,
y desactiva automáticamente el TTS si no está configurada.
"""

from dotenv import load_dotenv
load_dotenv()  # Carga variables de entorno desde .env

import os
import subprocess  # Permite ejecutar otros programas (como el worker de TTS)
import sys
import tempfile  # Permite crear archivos temporales
from pathlib import Path  # Manejo de rutas de archivos

from logging_setup import obtener_logger


class TextToSpeechManager:
    """
    Esta clase se encarga de manejar la funcionalidad de texto a voz (TTS).

    No genera el audio directamente, sino que:
    - prepara el texto
    - crea un archivo temporal
    - lanza un proceso separado (tts_worker.py)

    Esto evita bloquear el programa principal mientras se genera el audio.
    """

    def __init__(self, enabled: bool = True):
        # Indica si el sistema de voz está activado o no
        self.enabled = enabled

        # Logger para registrar eventos y errores
        self.logger = obtener_logger()

        # Se verifica si existe la API key necesaria para TTS
        api_key = os.getenv("ELEVEN_API_KEY")

        # Si no hay API key, se desactiva automáticamente el TTS
        if not api_key:
            self.enabled = False
            self.logger.warning("No ELEVEN_API_KEY -> TTS deshabilitado")

    def hablar(self, texto: str, idioma: str | None = None):
        """
        Método principal para convertir texto en voz.

        Lo que hace:
        1. valida que TTS esté habilitado
        2. limpia el texto
        3. crea un archivo temporal con el texto
        4. ejecuta el worker (tts_worker.py) como proceso separado
        """

        # Si TTS está deshabilitado, no hace nada
        if not self.enabled:
            return

        # Limpia el texto (evita None o espacios vacíos)
        texto = (texto or "").strip()

        # Si no hay texto, no se hace nada
        if not texto:
            return

        try:
            # ==============================
            # UBICAR EL WORKER
            # ==============================

            # Busca el archivo tts_worker.py en el mismo directorio
            worker_path = Path(__file__).with_name("tts_worker.py")

            # ==============================
            # CREAR ARCHIVO TEMPORAL
            # ==============================

            # Se crea un archivo temporal para guardar el texto
            # delete=False permite que el worker lo pueda leer después
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                delete=False,
                suffix=".txt",
            ) as f:
                f.write(texto)
                temp_text_path = f.name  # ruta del archivo temporal

            # ==============================
            # EJECUTAR WORKER
            # ==============================

            # Se lanza el worker como un proceso separado
            subprocess.run(
                [
                    sys.executable,      # ejecuta con el mismo Python
                    str(worker_path),    # archivo worker
                    temp_text_path,      # archivo con el texto
                    idioma or "",        # idioma opcional
                ],
                check=False,  # no lanza excepción si el proceso falla
            )

        except Exception as e:
            # Si ocurre algún error al lanzar el worker:
            # - se registra en logs
            # - se muestra en consola
            self.logger.exception("Error lanzando TTS worker")
            print(f"\n[TTS] Error: {e}")
