"""
voice.py se encarga de manejar el reconocimiento de voz.

Este archivo:
- captura audio desde el micrófono
- lo convierte a texto usando speech_recognition
- intenta reconocer en múltiples idiomas
- maneja errores específicos (timeout, no entendido, etc.)

La idea es separar toda la lógica de voz del resto del sistema,
para que sea más fácil de mantener y extender.

También incluye un mecanismo de fallback entre idiomas,
lo que mejora la precisión del reconocimiento.
"""

from typing import Any, Callable, ContextManager, Optional, Protocol

import speech_recognition as sr  # Librería para reconocimiento de voz

from config import Config
from errors import (
    VoiceMicrofonoError,
    VoiceNoEntendidaError,
    VoiceServicioError,
    VoiceTimeoutError,
)
from logging_setup import obtener_logger


# ==============================
# CONTRATO DEL SERVICIO DE VOZ
# ==============================

class VoiceService(Protocol):
    """
    Este protocolo define qué debe hacer cualquier servicio de voz.

    Básicamente obliga a que exista un método escuchar()
    que devuelva texto.
    """

    def escuchar(self) -> str:
        ...


# Tipo para crear micrófonos (permite inyección para testing)
MicrophoneFactory = Callable[[], ContextManager[Any]]


# ==============================
# IMPLEMENTACIÓN CONCRETA
# ==============================

class VoiceManager:
    """
    Esta clase implementa el reconocimiento de voz usando speech_recognition.

    Funcionalidad principal:
    - escucha audio desde el micrófono
    - lo convierte a texto
    - intenta reconocer en varios idiomas

    Mejora importante:
    Si falla en un idioma, intenta con otros (ej: español → inglés).
    """

    def __init__(
        self,
        config: Config,
        recognizer: Optional[sr.Recognizer] = None,
        microphone_factory: Optional[MicrophoneFactory] = None,
    ) -> None:

        # Configuración general del sistema
        self.config = config

        # Objeto que hace el reconocimiento de voz
        self.recognizer = recognizer or sr.Recognizer()

        # Forma de crear el micrófono (se puede cambiar para testing)
        self.microphone_factory = microphone_factory or sr.Microphone

        # Logger para registrar eventos
        self.logger = obtener_logger()

        # Configura parámetros del recognizer
        self._configurar_recognizer()

    def escuchar(self) -> str:
        """
        Método principal.

        Flujo:
        1. captura audio desde el micrófono
        2. intenta convertirlo a texto
        3. maneja errores específicos y los traduce
        """

        try:
            audio = self._capturar_audio()
            return self._reconocer_audio(audio)

        # Si no se detecta voz a tiempo
        except sr.WaitTimeoutError as error:
            raise VoiceTimeoutError() from error

        # Si se escuchó algo pero no se entendió
        except sr.UnknownValueError as error:
            raise VoiceNoEntendidaError() from error

        # Si falla el servicio de reconocimiento
        except sr.RequestError as error:
            raise VoiceServicioError(str(error)) from error

        # Si hay problemas con el micrófono
        except OSError as error:
            raise VoiceMicrofonoError(str(error)) from error

    def _configurar_recognizer(self) -> None:
        """
        Configura parámetros internos del reconocimiento de voz.

        - pausa entre palabras
        - cuánto silencio se permite
        """
        self.recognizer.pause_threshold = self.config.voz_umbral_pausa
        self.recognizer.non_speaking_duration = self.config.voz_duracion_no_habla

    def _capturar_audio(self) -> sr.AudioData:
        """
        Captura audio desde el micrófono.

        Pasos:
        1. abre el micrófono
        2. ajusta al ruido ambiente
        3. escucha al usuario
        """

        with self.microphone_factory() as source:

            # Ajusta el micrófono al ruido ambiente
            self.recognizer.adjust_for_ambient_noise(
                source,
                duration=self.config.voz_duracion_ajuste_ruido,
            )

            # Parámetros de escucha
            listen_kwargs = {
                "timeout": self.config.voz_timeout,
            }

            # Si hay límite de duración de frase, se agrega
            if self.config.voz_phrase_time_limit is not None:
                listen_kwargs["phrase_time_limit"] = self.config.voz_phrase_time_limit

            # Escucha el audio
            return self.recognizer.listen(
                source,
                **listen_kwargs,
            )

    def _reconocer_audio(self, audio: sr.AudioData) -> str:
        """
        Convierte el audio capturado a texto.

        Estrategia:
        - intenta reconocer en varios idiomas
        - si falla en uno, prueba con otro
        """

        # Lista de idiomas a intentar
        idiomas = self.config.voz_idiomas or [self.config.voz_idioma]

        ultimo_unknown_value_error: sr.UnknownValueError | None = None

        # Intenta con cada idioma
        for idioma in idiomas:
            try:
                self.logger.info(
                    "Intentando reconocimiento de voz con idioma=%s",
                    idioma,
                )

                # Llama al servicio de Google para reconocer el audio
                texto = self.recognizer.recognize_google(
                    audio,
                    language=idioma,
                ).strip()

                # Si se obtuvo texto válido, lo devuelve
                if texto:
                    self.logger.info(
                        "Reconocimiento exitoso con idioma=%s longitud=%s",
                        idioma,
                        len(texto),
                    )
                    return texto

            except sr.UnknownValueError as error:
                # No se entendió el audio en este idioma
                ultimo_unknown_value_error = error

                self.logger.info(
                    "No se pudo interpretar el audio con idioma=%s. Se intentará otro idioma si existe.",
                    idioma,
                )
                continue

            except sr.RequestError:
                # Error real del servicio (internet/API)
                # No tiene sentido probar otros idiomas
                raise

        # Si ningún idioma funcionó, lanza el error final
        if ultimo_unknown_value_error is not None:
            raise ultimo_unknown_value_error

        # Caso fallback
        raise sr.UnknownValueError()
    