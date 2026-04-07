"""
main.py es el punto de entrada de la aplicación.

Este archivo se encarga de:
- cargar variables de entorno (.env)
- inicializar la terminal (colores)
- configurar el sistema de logs
- cargar la configuración del sistema
- crear la aplicación CLI
- ejecutar el programa principal

En resumen, aquí es donde todo empieza.
"""

from colorama import init
from dotenv import load_dotenv

# Importamos la clase principal de la aplicación CLI
from cli import ChatCLI

# Importamos la configuración central del sistema
from config import Config

# Importamos funciones para configurar y usar logging
from logging_setup import configurar_logging, obtener_logger


def main() -> None:
    """
    Este es el punto de entrada principal del programa.

    Es básicamente la función que arranca toda la aplicación.
    Aquí se inicializan todos los componentes necesarios
    antes de empezar a interactuar con el usuario.
    """

    # ==============================
    # INICIALIZACIÓN BÁSICA
    # ==============================

    # Carga variables de entorno desde un archivo .env
    # Esto permite tener configuraciones externas como API keys.
    load_dotenv()

    # Inicializa colorama para poder usar colores en la terminal.
    # autoreset=True hace que los colores se reinicien automáticamente.
    init(autoreset=True)

    # ==============================
    # CONFIGURACIÓN DE LOGGING
    # ==============================

    # Configura el sistema de logs y crea un archivo de log.
    ruta_log = configurar_logging()

    # Obtiene el logger principal del sistema.
    logger = obtener_logger()

    # Registra que la aplicación arrancó correctamente.
    logger.info("Boot de aplicación completado. Log activo: %s", ruta_log)

    try:
        # ==============================
        # CARGA DE CONFIGURACIÓN
        # ==============================

        # Crea un objeto Config leyendo variables de entorno.
        # Aquí se cargan cosas como:
        # - modelo a usar
        # - configuración de voz
        # - parámetros del sistema
        config = Config.from_env()

        logger.info(
            "Configuración cargada correctamente. modelo=%s voz_habilitada=%s",
            config.nombre_modelo,
            config.voz_habilitada,
        )

        # ==============================
        # INICIALIZACIÓN DE LA APP
        # ==============================

        # Se crea la aplicación CLI principal.
        # Esta clase se encarga de toda la interacción con el usuario.
        app = ChatCLI(config)

        logger.info("Aplicación CLI inicializada correctamente.")

        # ==============================
        # EJECUCIÓN
        # ==============================

        # Inicia el loop principal del programa (chat en terminal).
        app.run()

    except BaseException as error:
        # ==============================
        # MANEJO DE ERRORES FATALES
        # ==============================

        # Si ocurre cualquier error grave:
        # - se registra en el log
        # - se muestra en consola
        # - se relanza el error

        logger.exception(
            "Error fatal al iniciar o ejecutar la aplicación: %r",
            error,
        )

        # Se muestra el error en consola para el usuario
        print(f"Error fatal: {type(error).__name__}: {error}")

        # Se vuelve a lanzar el error (útil para debugging)
        raise


# ==============================
# PUNTO DE ENTRADA DEL SCRIPT
# ==============================

# Esto asegura que main() solo se ejecute
# si este archivo se corre directamente,
# y no cuando se importa como módulo.
if __name__ == "__main__":
    main()
