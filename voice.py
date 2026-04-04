from typing import Any, Callable, ContextManager, Optional, Protocol

import speech_recognition as sr

from config import Config
from errors import (
    VoiceMicrofonoError,
    VoiceNoEntendidaError,
    VoiceServicioError,
    VoiceTimeoutError,
)


# ==============================
# CONTRATO DEL SERVICIO DE VOZ
# ==============================

class VoiceService(Protocol):
    """
    Define el comportamiento esperado para cualquier servicio de voz.

    Permite que diferentes implementaciones (por ejemplo, otro proveedor)
    puedan ser usadas sin cambiar el resto del sistema.
    """

    def escuchar(self) -> str:
        """
        Captura audio y lo convierte en texto.
        """
        ...


# Tipo que representa una fábrica de micrófonos.
# Se usa para permitir inyección de dependencias (por ejemplo en tests).
MicrophoneFactory = Callable[[], ContextManager[Any]]


# ==============================
# IMPLEMENTACIÓN CON speech_recognition
# ==============================

class VoiceManager:
    """
    Implementación concreta del servicio de voz usando speech_recognition.

    Responsabilidades:
    - capturar audio desde el micrófono
    - ajustar ruido ambiente
    - convertir audio a texto usando Google Speech API
    - traducir errores técnicos a errores del dominio
    """

    def __init__(
        self,
        config: Config,
        recognizer: Optional[sr.Recognizer] = None,
        microphone_factory: Optional[MicrophoneFactory] = None,
    ) -> None:
        """
        Inicializa el servicio de voz.

        Args:
            config: Configuración general (timeouts, idioma, etc.).
            recognizer: Instancia opcional de Recognizer (útil para testing).
            microphone_factory: Fábrica opcional para crear micrófonos.
        """
        self.config = config

        # Recognizer de speech_recognition (procesa audio)
        self.recognizer = recognizer or sr.Recognizer()

        # Permite reemplazar el micrófono (ej: tests)
        self.microphone_factory = microphone_factory or sr.Microphone

        # Configuración de pausas al hablar
        self.recognizer.pause_threshold = self.config.voz_umbral_pausa
        self.recognizer.non_speaking_duration = self.config.voz_duracion_no_habla

    def escuchar(self) -> str:
        """
        Captura audio desde el micrófono y lo convierte en texto.

        Flujo:
        1. Abre el micrófono.
        2. Ajusta el ruido ambiente.
        3. Escucha al usuario.
        4. Envía el audio a Google para reconocimiento.
        5. Devuelve el texto reconocido.

        Returns:
            Texto reconocido a partir de la voz del usuario.

        Raises:
            VoiceTimeoutError: No se detectó voz a tiempo.
            VoiceNoEntendidaError: No se pudo interpretar el audio.
            VoiceServicioError: Falló el servicio de reconocimiento.
            VoiceMicrofonoError: Problema con el micrófono.
        """
        try:
            # ==============================
            # CAPTURA DE AUDIO
            # ==============================

            with self.microphone_factory() as source:
                # Ajusta el ruido ambiente (importante para mejorar precisión)
                self.recognizer.adjust_for_ambient_noise(
                    source,
                    duration=self.config.voz_duracion_ajuste_ruido,
                )

                # Escucha al usuario
                audio = self.recognizer.listen(
                    source,
                    timeout=self.config.voz_timeout,
                    phrase_time_limit=self.config.voz_phrase_time_limit,
                )

            # ==============================
            # RECONOCIMIENTO DE VOZ
            # ==============================

            texto = self.recognizer.recognize_google(
                audio,
                language=self.config.voz_idioma,
            ).strip()

            return texto

        # ==============================
        # MANEJO DE ERRORES
        # ==============================

        except sr.WaitTimeoutError as error:
            # No se detectó voz dentro del tiempo límite
            raise VoiceTimeoutError() from error

        except sr.UnknownValueError as error:
            # Se detectó audio pero no se pudo entender
            raise VoiceNoEntendidaError() from error

        except sr.RequestError as error:
            # Fallo del servicio externo (Google)
            raise VoiceServicioError(str(error)) from error

        except OSError as error:
            # Problema con el micrófono o dispositivo de audio
            raise VoiceMicrofonoError(str(error)) from error
        