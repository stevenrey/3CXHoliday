import os
import subprocess
import wave
from pathlib import Path


def check_piper_available(config: dict):
    binary = config.get("piper_binary", "/opt/piper/piper")
    model = config.get("piper_model", "")
    return {
        "binary": binary,
        "model": model,
        "binary_exists": os.path.exists(binary),
        "model_exists": bool(model) and os.path.exists(model),
        "available": os.path.exists(binary) and bool(model) and os.path.exists(model),
    }


def _write_dummy_wav(filepath: str):
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(filepath, "w") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 16000)


def generate_tts(text: str, filepath: str, config: dict):
    engine = (config.get("tts_engine") or "piper").lower()
    if engine == "piper":
        binary = config.get("piper_binary", "/opt/piper/piper")
        model = config.get("piper_model", "")
        if os.path.exists(binary) and os.path.exists(model):
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            cmd = [binary, "--model", model, "--output_file", filepath]
            subprocess.run(cmd, input=text.encode("utf-8"), check=True)
            return filepath
    _write_dummy_wav(filepath)
    return filepath
