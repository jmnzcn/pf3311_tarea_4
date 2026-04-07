"""
retry.py implementa un sistema de reintentos automáticos.

Sirve para ejecutar una operación (por ejemplo, una llamada a una API)
y, si falla por un error temporal, volver a intentarlo automáticamente.

Incluye:
- configuración de reintentos (RetryConfig)
- lógica de ejecución con múltiples intentos
- backoff exponencial (cada intento espera más)
- jitter (pequeña variación aleatoria)
- registro de intentos en logs

La idea es hacer el sistema más robusto frente a errores temporales
como fallos de red o saturación del servicio.
"""

import logging  # Se usa para registrar mensajes (logs)
import random  # Permite generar valores aleatorios (para jitter)
import time  # Permite pausar la ejecución (sleep)
from dataclasses import dataclass  # Para crear clases simples de configuración
from typing import Any, Callable, Optional  # Tipos para mayor claridad


# ==============================
# CONFIGURACIÓN DE REINTENTOS
# ==============================

@dataclass(frozen=True)
class RetryConfig:
    """
    Esta clase guarda todos los parámetros necesarios
    para controlar cómo se hacen los reintentos.

    frozen=True significa que una vez creada,
    no se puede modificar (es inmutable).
    """

    # Cantidad máxima de intentos.
    # Incluye el intento original + reintentos.
    max_intentos: int = 3

    # Tiempo base de espera antes del primer reintento.
    backoff_inicial: float = 1.0

    # Factor de crecimiento del tiempo de espera.
    # Hace que cada intento espere más que el anterior.
    backoff_factor: float = 2.0

    # Jitter: pequeño valor aleatorio para evitar
    # que múltiples procesos reintenten al mismo tiempo.
    jitter_ratio: float = 0.25


# ==============================
# EJECUCIÓN CON REINTENTOS
# ==============================

def ejecutar_con_reintentos(
    operacion: Callable[[], Any],
    retry_config: RetryConfig,
    es_reintentable: Callable[[Exception], bool],
    logger: Optional[logging.Logger] = None,
) -> Any:
    """
    Esta función ejecuta una operación y, si falla,
    la vuelve a intentar automáticamente.

    Parámetros:
    - operacion: función que se quiere ejecutar
    - retry_config: configuración de reintentos
    - es_reintentable: función que indica si un error permite reintento
    - logger: opcional, para registrar lo que está pasando

    Flujo general:
    1. intenta ejecutar la operación
    2. si falla, revisa si vale la pena reintentar
    3. espera un tiempo (backoff + jitter)
    4. vuelve a intentar
    5. si todos fallan, lanza el error final
    """

    # Guarda el último error ocurrido
    # para poder lanzarlo si todo falla
    ultimo_error: Optional[Exception] = None

    # Loop de intentos
    for intento in range(1, retry_config.max_intentos + 1):
        try:
            # Intenta ejecutar la operación
            return operacion()

        except Exception as error:
            # Guarda el error actual
            ultimo_error = error

            # Si el error NO es reintentable,
            # no tiene sentido seguir intentando
            if not es_reintentable(error):
                raise

            # Si ya es el último intento, se sale del loop
            if _es_ultimo_intento(intento, retry_config):
                break

            # Calcula cuánto tiempo esperar antes del siguiente intento
            espera = _calcular_espera(intento, retry_config)

            # Registra en logs lo que está pasando (si hay logger)
            _registrar_reintento(
                logger=logger,
                intento=intento,
                max_intentos=retry_config.max_intentos,
                espera=espera,
                error=error,
            )

            # Espera el tiempo calculado
            time.sleep(espera)

    # Si todos los intentos fallaron, lanza el último error
    if ultimo_error is not None:
        raise ultimo_error

    # Este caso no debería ocurrir normalmente
    raise RuntimeError("Fallo inesperado ejecutando operación con reintentos.")


def _es_ultimo_intento(intento: int, retry_config: RetryConfig) -> bool:
    """
    Devuelve True si el intento actual ya es el último permitido.
    """
    return intento >= retry_config.max_intentos


def _calcular_espera(intento: int, retry_config: RetryConfig) -> float:
    """
    Calcula cuánto tiempo esperar antes de reintentar.

    Usa dos ideas importantes:

    1. Backoff exponencial:
       cada intento espera más tiempo que el anterior

    2. Jitter:
       agrega un pequeño valor aleatorio para evitar
       que muchos procesos reintenten al mismo tiempo
    """

    # Backoff exponencial:
    # Ejemplo:
    # intento 1 -> 1
    # intento 2 -> 2
    # intento 3 -> 4
    espera_base = retry_config.backoff_inicial * (
        retry_config.backoff_factor ** (intento - 1)
    )

    # Jitter: valor aleatorio pequeño
    jitter = random.uniform(0, espera_base * retry_config.jitter_ratio)

    # Tiempo final = base + aleatorio
    return espera_base + jitter


def _registrar_reintento(
    logger: Optional[logging.Logger],
    intento: int,
    max_intentos: int,
    espera: float,
    error: Exception,
) -> None:
    """
    Registra en logs que se va a hacer un reintento.

    Esto es útil para debugging y monitoreo.
    """

    # Si no hay logger, no hace nada
    if logger is None:
        return

    # Registra un warning con información útil
    logger.warning(
        "Error reintentable. Intento %s/%s. Reintentando en %.2f s. Error: %s",
        intento,
        max_intentos,
        espera,
        error,
    )
