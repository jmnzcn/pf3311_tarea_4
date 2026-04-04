from colorama import init
from dotenv import load_dotenv

from cli import ChatCLI
from config import Config
from logging_setup import configurar_logging, obtener_logger


def main() -> None:
    load_dotenv()
    init(autoreset=True)

    ruta_log = configurar_logging()
    obtener_logger().info("Boot de aplicación completado. Log activo: %s", ruta_log)

    config = Config.from_env()
    app = ChatCLI(config)
    app.run()


if __name__ == "__main__":
    main()