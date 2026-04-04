import logging
import sys
from datetime import datetime
from pathlib import Path

from config import env_bool, env_str


# ==============================
# RUTA DEL ARCHIVO DE LOG
# ==============================

def crear_ruta_log_sesion() -> Path:
    """
    Crea la ruta del archivo de log para la sesión actual.

    - Se asegura de que exista la carpeta 'logs'.
    - Genera un nombre único basado en timestamp para evitar sobrescrituras.

    Returns:
        Ruta completa del archivo de log.
    """
    logs_dir = Path.cwd() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Se usa fecha + hora + microsegundos para asegurar unicidad.
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")

    return logs_dir / f"chatgipiti_{timestamp}.log"


# ==============================
# LOGGER PRINCIPAL
# ==============================

def obtener_logger() -> logging.Logger:
    """
    Devuelve el logger principal de la aplicación.

    Se utiliza un nombre fijo ("chatgipiti") para que todo el sistema
    comparta el mismo logger y configuración.

    Returns:
        Instancia del logger principal.
    """
    return logging.getLogger("chatgipiti")


# ==============================
# CONFIGURACIÓN DE LOGGING
# ==============================

def configurar_logging() -> Path:
    """
    Configura el sistema de logging de la aplicación.

    Esta función:
    - define el nivel de logging (INFO, DEBUG, etc.)
    - crea un archivo de log por sesión
    - opcionalmente activa logs en consola
    - reduce el ruido de librerías externas
    - registra información inicial de la sesión

    Returns:
        Ruta del archivo de log generado.
    """

    # ==============================
    # NIVEL DE LOG
    # ==============================

    # Se obtiene desde variables de entorno (ej: DEBUG, INFO, ERROR).
    nivel_str = env_str("LOG_LEVEL", "INFO").upper()
    nivel = getattr(logging, nivel_str, logging.INFO)

    # ==============================
    # CREACIÓN DE ARCHIVO
    # ==============================

    ruta_log = crear_ruta_log_sesion()

    # ==============================
    # CONFIGURACIÓN DEL LOGGER
    # ==============================

    logger = obtener_logger()

    # Nivel global del logger
    logger.setLevel(nivel)

    # Se limpian handlers previos para evitar duplicación de logs
    logger.handlers.clear()

    # Evita que los logs se propaguen a otros loggers del sistema
    logger.propagate = False

    # ==============================
    # HANDLER: ARCHIVO
    # ==============================

    # Todo se guarda en archivo de log
    file_handler = logging.FileHandler(ruta_log, encoding="utf-8")
    file_handler.setLevel(nivel)

    # Formato estándar: fecha + nivel + mensaje
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )

    logger.addHandler(file_handler)

    # ==============================
    # HANDLER: CONSOLA (OPCIONAL)
    # ==============================

    # Permite ver logs en tiempo real en la terminal
    if env_bool("MOSTRAR_LOGS_EN_CONSOLA", False):
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(nivel)

        console_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        )

        logger.addHandler(console_handler)

    # ==============================
    # REDUCCIÓN DE RUIDO EXTERNO
    # ==============================

    # Se bajan los logs de librerías externas para evitar saturación.
    # Solo se mostrarán errores críticos de estas dependencias.
    for logger_name in (
        "google",
        "google.genai",
        "google.genai._api_client",
        "httpx",
        "httpcore",
        "urllib3",
    ):
        ext_logger = logging.getLogger(logger_name)
        ext_logger.setLevel(logging.ERROR)
        ext_logger.propagate = False

    # ==============================
    # LOG INICIAL DE SESIÓN
    # ==============================

    logger.info("============================================================")
    logger.info("Inicio de sesión de aplicación")
    logger.info("Archivo de log creado en: %s", ruta_log)
    logger.info("Directorio de trabajo actual: %s", Path.cwd())
    logger.info("============================================================")

    return ruta_log