"""
logging_setup.py se encarga de configurar todo el sistema de logs del proyecto.

Aquí se define:
- dónde se guardan los logs (archivo)
- si también se muestran en consola
- el formato de los logs
- el nivel de detalle (INFO, DEBUG, ERROR, etc.)
- reducción de ruido de librerías externas

La idea es tener un sistema centralizado para registrar lo que pasa en la aplicación,
lo cual ayuda a depurar errores y entender el comportamiento del programa.
"""

import logging  # Módulo estándar de Python para registrar eventos (logs)
import sys  # Permite acceder a stderr (salida de errores en consola)
from datetime import datetime  # Se usa para generar timestamps únicos
from pathlib import Path  # Facilita trabajar con rutas de archivos

# Funciones para leer variables de entorno
from config import env_bool, env_str


# Nombre único del logger principal.
# Esto permite que siempre se use la misma instancia en todo el proyecto.
LOGGER_NAME = "chatgipiti"


def crear_ruta_log_sesion() -> Path:
    """
    Crea la ruta del archivo de log para esta ejecución del programa.

    Lo que hace:
    - crea (si no existe) una carpeta llamada "logs"
    - genera un nombre de archivo único usando fecha y hora
    - devuelve la ruta completa del archivo
    """

    # Carpeta "logs" dentro del proyecto actual
    logs_dir = Path.cwd() / "logs"

    # Crea la carpeta si no existe
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Genera un nombre único basado en fecha y hora
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")

    # Devuelve la ruta final del archivo
    return logs_dir / f"chatgipiti_{timestamp}.log"


def obtener_logger() -> logging.Logger:
    """
    Devuelve el logger principal de la aplicación.

    Importante:
    logging.getLogger(nombre) siempre devuelve la misma instancia
    si ya fue creada antes.
    """
    return logging.getLogger(LOGGER_NAME)


def configurar_logging() -> Path:
    """
    Configura todo el sistema de logging de la aplicación.

    Este método es clave porque:
    - define cómo se guardan los logs
    - decide si se muestran en consola
    - controla el nivel de detalle (INFO, DEBUG, ERROR, etc.)

    Pasos que realiza:
    1. Lee configuración desde variables de entorno
    2. Crea el archivo de log
    3. Configura el logger principal
    4. Agrega handlers (archivo y opcional consola)
    5. Reduce ruido de librerías externas
    6. Registra información inicial

    Devuelve:
        La ruta del archivo de log generado
    """

    # ==============================
    # CONFIGURACIÓN DESDE ENTORNO
    # ==============================

    # Nivel de logging (INFO, DEBUG, ERROR, etc.)
    # Si no está definido, usa INFO por defecto.
    nivel_str = env_str("LOG_LEVEL", "INFO").upper()

    # Convierte el texto a valor real de logging
    # Ejemplo: "INFO" -> logging.INFO
    nivel = getattr(logging, nivel_str, logging.INFO)

    # Indica si también se deben mostrar logs en consola
    mostrar_consola = env_bool("MOSTRAR_LOGS_EN_CONSOLA", False)

    # ==============================
    # CREACIÓN DEL ARCHIVO DE LOG
    # ==============================

    ruta_log = crear_ruta_log_sesion()

    # ==============================
    # CONFIGURACIÓN DEL LOGGER
    # ==============================

    logger = obtener_logger()

    # Se pone en DEBUG para que no filtre mensajes aquí.
    # El filtrado real lo hacen los handlers.
    logger.setLevel(logging.DEBUG)

    # Elimina handlers anteriores (evita duplicados)
    logger.handlers.clear()

    # Evita que los logs se propaguen al logger raíz de Python
    # (esto previene duplicaciones)
    logger.propagate = False

    # ==============================
    # FORMATO DE LOS LOGS
    # ==============================

    # Define cómo se verá cada línea de log
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(filename)s:%(lineno)d - %(message)s"
    )

    # ==============================
    # HANDLER DE ARCHIVO
    # ==============================

    # Este handler escribe logs en un archivo
    file_handler = logging.FileHandler(ruta_log, encoding="utf-8")

    # Nivel mínimo de logs que se guardan en archivo
    file_handler.setLevel(nivel)

    # Aplica el formato definido
    file_handler.setFormatter(formatter)

    # Se agrega al logger principal
    logger.addHandler(file_handler)

    # ==============================
    # HANDLER DE CONSOLA (OPCIONAL)
    # ==============================

    if mostrar_consola:
        # Este handler imprime logs en consola (stderr)
        console_handler = logging.StreamHandler(sys.stderr)

        # Mismo nivel que el archivo
        console_handler.setLevel(nivel)

        # Mismo formato
        console_handler.setFormatter(formatter)

        # Se agrega al logger
        logger.addHandler(console_handler)

    # ==============================
    # SILENCIAR LIBRERÍAS EXTERNAS
    # ==============================

    # Algunas librerías generan muchos logs innecesarios.
    # Aquí se limita su nivel a ERROR para evitar ruido.
    for logger_name in (
        "google",
        "google.genai",
        "google.genai._api_client",
        "httpx",
        "httpcore",
        "urllib3",
    ):
        ext_logger = logging.getLogger(logger_name)

        # Solo muestra errores graves
        ext_logger.setLevel(logging.ERROR)

        # Evita que se propaguen a otros loggers
        ext_logger.propagate = False

    # ==============================
    # LOG INICIAL
    # ==============================

    # Se registran datos importantes al inicio
    logger.info("============================================================")
    logger.info("Inicio de sesión de aplicación")
    logger.info("Archivo de log creado en: %s", ruta_log)
    logger.info("Directorio de trabajo actual: %s", Path.cwd())
    logger.info("Nivel de logging configurado: %s", nivel_str)
    logger.info("Logs en consola habilitados: %s", mostrar_consola)
    logger.info("============================================================")

    # Devuelve la ruta del archivo de log
    return ruta_log