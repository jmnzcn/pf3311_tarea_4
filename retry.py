import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional


# ==============================
# CONFIGURACIÓN DE REINTENTOS
# ==============================

@dataclass(frozen=True)
class RetryConfig:
    """
    Contiene la configuración necesaria para controlar la lógica de reintentos.

    Atributos:
        max_intentos: Número máximo total de intentos, incluyendo el primero.
        backoff_inicial: Tiempo base de espera antes del primer reintento.
        backoff_factor: Factor multiplicador que aumenta la espera en cada intento.
        jitter_ratio: Variación aleatoria adicional aplicada a la espera para
                      evitar que múltiples solicitudes fallen y reintenten
                      exactamente al mismo tiempo.
    """

    max_intentos: int = 3
    backoff_inicial: float = 1.0
    backoff_factor: float = 2.0
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
    Ejecuta una operación con lógica de reintentos automáticos.

    El flujo general es:
    1. Intenta ejecutar la operación.
    2. Si funciona, devuelve el resultado inmediatamente.
    3. Si falla, revisa si el error es reintentable.
    4. Si lo es, espera un tiempo calculado con backoff exponencial y jitter.
    5. Repite hasta alcanzar el máximo de intentos.
    6. Si al final sigue fallando, relanza el último error capturado.

    Args:
        operacion: Función sin argumentos que se desea ejecutar.
        retry_config: Configuración que controla cuántos intentos se harán
                      y cuánto se espera entre ellos.
        es_reintentable: Función que recibe una excepción y devuelve True
                         si el error amerita volver a intentar.
        logger: Logger opcional para registrar advertencias de reintentos.

    Returns:
        El resultado devuelto por la operación si alguno de los intentos tiene éxito.

    Raises:
        Exception: Relanza el último error si no se logra completar la operación.
        RuntimeError: Solo se usa como protección ante un caso inesperado donde
                      no exista resultado ni error capturado.
    """
    ultimo_error: Optional[Exception] = None

    # Se recorren todos los intentos posibles, incluyendo el primero.
    for intento in range(1, retry_config.max_intentos + 1):
        try:
            # Si la operación funciona en cualquier intento,
            # se devuelve el resultado de inmediato.
            return operacion()

        except Exception as error:
            # Se guarda el último error por si al final hay que relanzarlo.
            ultimo_error = error

            # Si el error no es reintentable, se relanza inmediatamente.
            # No tiene sentido seguir intentando.
            if not es_reintentable(error):
                raise

            # Si ya se agotó el número máximo de intentos, se sale del loop
            # para luego relanzar el último error.
            if intento >= retry_config.max_intentos:
                break

            # ==============================
            # CÁLCULO DE ESPERA
            # ==============================
            # Se usa backoff exponencial:
            # intento 1 -> backoff_inicial
            # intento 2 -> backoff_inicial * backoff_factor
            # intento 3 -> backoff_inicial * backoff_factor^2
            espera_base = retry_config.backoff_inicial * (
                retry_config.backoff_factor ** (intento - 1)
            )

            # El jitter agrega una pequeña variación aleatoria.
            # Esto ayuda a distribuir reintentos y evita que muchas solicitudes
            # fallen y se repitan al mismo tiempo de forma sincronizada.
            jitter = random.uniform(0, espera_base * retry_config.jitter_ratio)

            # Tiempo final que se espera antes de volver a intentar.
            espera = espera_base + jitter

            # Si se proporcionó logger, se registra el reintento.
            if logger is not None:
                logger.warning(
                    "Error reintentable. Intento %s/%s. Reintentando en %.2f s. Error: %s",
                    intento,
                    retry_config.max_intentos,
                    espera,
                    error,
                )

            # Pausa antes del siguiente intento.
            time.sleep(espera)

    # Si se agotaron los intentos y existe un error guardado,
    # se relanza ese último error.
    if ultimo_error is not None:
        raise ultimo_error

    # Este caso no debería ocurrir normalmente.
    raise RuntimeError("Fallo inesperado ejecutando operación con reintentos.")
