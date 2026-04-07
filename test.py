from dotenv import load_dotenv
load_dotenv()

from elevenlabs.client import ElevenLabs
import os

api_key = os.getenv("ELEVEN_API_KEY")
print("API KEY:", api_key[:10] if api_key else None)

client = ElevenLabs(api_key=api_key)

audio = client.text_to_speech.convert(
    voice_id="EXAVITQu4vr4xnSDxMaL",
    model_id="eleven_multilingual_v2",
    text="Hola mae todo bien"
)

with open("test.mp3", "wb") as f:
    for chunk in audio:
        f.write(chunk)

print("Archivo generado")