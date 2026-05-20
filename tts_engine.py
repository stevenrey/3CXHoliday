"""
TTS Engine – Piper (lokal/offline) oder Google Cloud TTS.
"""
import subprocess
import os
import logging
import base64
import requests

logger = logging.getLogger(__name__)


def generate_tts(text: str, output_path: str, config: dict):
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    engine = config.get("ttsengine", "piper")
    if engine == "piper":
        piper_tts(text, output_path, config)
    elif engine == "google":
        google_tts(text, output_path, config)
    else:
        raise ValueError(f"Unbekannte TTS Engine: {engine}")


def piper_tts(text: str, output_path: str, config: dict):
    piper_bin = config.get("piperbinary", "/opt/piper/piper")
    model = config.get("pipermodel", "/opt/piper/de_DE-thorsten-high.onnx")

    if not os.path.exists(piper_bin):
        raise FileNotFoundError(f"Piper Binary nicht gefunden: {piper_bin}")
    if not os.path.exists(model):
        raise FileNotFoundError(f"Piper Modell nicht gefunden: {model}")

    cmd = [piper_bin, "--model", model, "--output_file", output_path]
    result = subprocess.run(cmd, input=text, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Piper Fehler: {result.stderr}")
    logger.info(f"Piper TTS erfolgreich: {output_path}")


def google_tts(text: str, output_path: str, config: dict):
    api_key = config.get("googleapikey")
    if not api_key:
        raise ValueError("Google API Key fehlt in der Konfiguration")

    url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"
    payload = {
        "input": {"text": text},
        "voice": {
            "languageCode": "de-CH",
            "name": "de-DE-Neural2-B",
        },
        "audioConfig": {
            "audioEncoding": "LINEAR16",
            "sampleRateHertz": 8000,
        },
    }
    resp = requests.post(url, json=payload, timeout=20)
    resp.raise_for_status()
    audio_data = base64.b64decode(resp.json()["audioContent"])
    with open(output_path, "wb") as f:
        f.write(audio_data)
    logger.info(f"Google TTS erfolgreich: {output_path}")


def check_piper_available(config: dict) -> dict:
    """Check if piper binary and model exist."""
    piper_bin = config.get("piperbinary", "/opt/piper/piper")
    model = config.get("pipermodel", "/opt/piper/de_DE-thorsten-high.onnx")
    return {
        "binary_exists": os.path.exists(piper_bin),
        "model_exists": os.path.exists(model),
        "binary_path": piper_bin,
        "model_path": model,
    }
