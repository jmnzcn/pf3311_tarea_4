# ChatGiPiTi 🤖💬

Aplicación de chat en terminal con soporte para:
- conversación con Gemini (IA)
- entrada por voz (speech-to-text)
- salida por voz (text-to-speech)
- manejo de errores robusto
- sistema de logging
- arquitectura modular

---

## 📌 Descripción

Este proyecto es una aplicación de línea de comandos (CLI) que permite interactuar con un modelo de inteligencia artificial (Gemini) de forma conversacional.

El sistema incluye funcionalidades avanzadas como:
- detección automática de idioma (español / inglés)
- reconocimiento de voz con fallback entre idiomas
- generación de audio usando ElevenLabs
- manejo inteligente de errores y reintentos
- interfaz de terminal con animaciones

El objetivo del proyecto es demostrar una arquitectura modular y mantenible, separando responsabilidades en distintos componentes.

---

## ⚙️ Tecnologías utilizadas

- Python 3.10+
- Google Gemini API (`google.genai`)
- SpeechRecognition (input de voz)
- ElevenLabs (output de voz)
- Colorama (UI en terminal)
- dotenv (variables de entorno)

---

## 🚀 Instalación

### 1. Clonar el repositorio

```bash
git clone <repo-url>
cd chatgipiti


#### 🧠 Arquitectura del sistema

El proyecto está dividido en módulos con responsabilidades claras:

🔹 main.py

Punto de entrada:

carga variables de entorno
configura logging
inicia la aplicación
🔹 cli.py

Controla el flujo principal:

recibe input
ejecuta comandos
conecta con servicios
🔹 gemini_service.py

Encapsula la comunicación con Gemini:

envío de mensajes
manejo de respuestas
reintentos
detección de respuestas incompletas
🔹 voice.py

Maneja reconocimiento de voz:

captura audio
lo convierte a texto
intenta múltiples idiomas
🔹 tts.py + tts_worker.py

Sistema de salida por voz:

tts.py: lanza el proceso
tts_worker.py: genera y reproduce audio
🔹 ui.py

Maneja la interfaz:

impresión de mensajes
colores
animación "escribiendo..."
🔹 errors.py

Manejo de errores:

errores personalizados
traducción a mensajes amigables
🔹 retry.py

Sistema de reintentos:

backoff exponencial
jitter
control de errores temporales
🔹 config.py

Configuración central:

variables de entorno
parámetros del sistema
prompt base

🔁 Flujo del sistema
Usuario escribe o habla
cli.py procesa entrada
gemini_service.py envía a Gemini
Se obtiene respuesta
ui.py muestra resultado
Opcional: tts.py reproduce audio

🧩 Características clave
✔ Manejo de errores
clasificación de errores
mensajes amigables
logging detallado
✔ Reintentos automáticos
backoff exponencial
jitter
resiliencia ante fallos
✔ Voz
reconocimiento multi-idioma
manejo de errores de micrófono
ejecución en proceso separado
✔ UI concurrente
animaciones con threads
output sincronizado