"""
tts_worker.py es un script encargado de convertir texto a voz y reproducirlo.

Funciona como un proceso separado del programa principal.

Flujo general:
1. recibe un archivo con texto como argumento
2. lee el contenido
3. lo recorta si es muy largo
4. usa la API de ElevenLabs para generar audio
5. reproduce el audio en la computadora

La idea de separarlo en un archivo independiente es evitar que
el proceso principal se bloquee mientras se genera el audio.
"""

from dotenv import load_dotenv
load_dotenv()  # Carga variables de entorno desde el archivo .env

import os
import sys

import simpleaudio as sa  # Librería para reproducir audio en la computadora
from elevenlabs.client import ElevenLabs  # Cliente para usar la API de ElevenLabs (TTS)


def recortar_para_voz(texto: str, max_chars: int = 220) -> str:
    """
    Esta función se encarga de acortar el texto para que
    no sea demasiado largo al momento de convertirlo a voz.

    Lo que hace:
    - elimina espacios extra
    - si el texto es corto, lo deja igual
    - si es largo, lo corta sin partir palabras y agrega "..."
    """

    texto = " ".join(texto.split()).strip()

    if len(texto) <= max_chars:
        return texto

    # Corta el texto sin dejar una palabra incompleta
    return texto[:max_chars].rsplit(" ", 1)[0] + "..."


def main():
    """
    Función principal del script.

    Este archivo funciona como un "worker" independiente,
    es decir, se ejecuta como un proceso separado
    para encargarse únicamente de generar y reproducir audio.
    """

    # ==============================
    # LECTURA DE ARGUMENTOS
    # ==============================

    # Se espera que el programa reciba al menos un argumento:
    # la ruta de un archivo de texto con el contenido a leer.
    if len(sys.argv) < 2:
        return

    # Primer argumento: archivo con el texto
    text_file = sys.argv[1]

    # Segundo argumento (opcional): idioma
    idioma = sys.argv[2] if len(sys.argv) > 2 else ""

    # ==============================
    # VALIDACIÓN DE API KEY
    # ==============================

    # Se obtiene la API key de ElevenLabs desde variables de entorno
    api_key = os.getenv("ELEVEN_API_KEY")

    if not api_key:
        print("[TTS] ELEVEN_API_KEY no configurada.")
        return

    # ==============================
    # LECTURA DEL TEXTO
    # ==============================

    # Se abre el archivo recibido y se lee su contenido
    with open(text_file, "r", encoding="utf-8") as f:
        texto = f.read().strip()

    # Si el archivo está vacío, no se hace nada
    if not texto:
        return

    # Se recorta el texto para evitar audios demasiado largos
    texto = recortar_para_voz(texto, max_chars=220)

    # ==============================
    # CONFIGURACIÓN DEL CLIENTE TTS
    # ==============================

    # Se crea el cliente de ElevenLabs usando la API key
    client = ElevenLabs(api_key=api_key)

    # ID de la voz que se va a usar
    # (es una voz predefinida en ElevenLabs)
    voice_id = "pNInz6obpgDQGcFmaJgB"

    try:
        # ==============================
        # GENERACIÓN DE AUDIO
        # ==============================

        # Se envía el texto a ElevenLabs para convertirlo en audio
        audio_stream = client.text_to_speech.convert(
            voice_id=voice_id,
            model_id="eleven_multilingual_v2",
            text=texto,
            output_format="pcm_24000",  # formato de audio sin comprimir
        )

        # Se combinan los fragmentos de audio en un solo bloque de bytes
        pcm_bytes = b"".join(audio_stream)

        # ==============================
        # REPRODUCCIÓN DE AUDIO
        # ==============================

        # Se reproduce el audio directamente en la computadora
        play_obj = sa.play_buffer(
            pcm_bytes,
            num_channels=1,      # audio mono
            bytes_per_sample=2,  # 16 bits
            sample_rate=24000,   # frecuencia de muestreo
        )

        # Espera a que el audio termine antes de continuar
        play_obj.wait_done()

    except Exception as e:
        # Si ocurre algún error, se muestra en consola
        print(f"[TTS] No se pudo generar audio: {e}")
        return


# ==============================
# PUNTO DE ENTRADA
# ==============================

# Esto permite ejecutar este archivo directamente desde la terminal
# o desde otro script (como el TTS manager)
if __name__ == "__main__":
    main()