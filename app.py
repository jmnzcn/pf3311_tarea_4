from flask import Flask, request, render_template_string
from dotenv import load_dotenv
from colorama import init
import sys
import os

from config import Config
from logging_setup import configurar_logging
from cli import ChatController
from gemini_service import GeminiChatService
from ui import OutputManager, TerminalUI, ErrorPresenter

load_dotenv()
init(autoreset=True)
configurar_logging()

app = Flask(__name__)

config = Config.from_env()
output = OutputManager(stream=sys.stdout)
ui = TerminalUI(output, config)
error_presenter = ErrorPresenter(config, ui)
chat_service = GeminiChatService(config)

_api_key = os.getenv("GEMINI_API_KEY", "").strip()

if not _api_key:
    raise ValueError("Falta GEMINI_API_KEY en el entorno")

chat_service.inicializar(_api_key)

chat_controller = ChatController(
    config=config,
    output=output,
    ui=ui,
    chat_service=chat_service,
    error_presenter=error_presenter,
)

HTML = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>PF3311 Tarea 4</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 800px; margin: 40px auto; }
    textarea { width: 100%; padding: 10px; }
    button { margin-top: 10px; padding: 10px 16px; }
    .box { margin-top: 20px; padding: 16px; border: 1px solid #ccc; border-radius: 8px; }
  </style>
</head>
<body>
  <h1>Chat del proyecto</h1>
  <form method="post">
    <textarea name="mensaje" rows="6">{{ mensaje or "" }}</textarea><br>
    <button type="submit">Enviar</button>
  </form>

  {% if respuesta %}
    <div class="box">
      <strong>Respuesta:</strong>
      <p>{{ respuesta }}</p>
    </div>
  {% endif %}
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def home():
    mensaje = ""
    respuesta = ""

    if request.method == "POST":
        mensaje = request.form.get("mensaje", "").strip()
        if mensaje:
            respuesta = chat_controller.procesar_mensaje(mensaje)

    return render_template_string(HTML, mensaje=mensaje, respuesta=respuesta)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)