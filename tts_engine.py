import os
import subprocess
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


def generate_tts(text: str, filepath: str, config: dict):
    engine = (config.get("tts_engine") or "piper").lower()
    if engine == "piper":
        binary = config.get("piper_binary", "/opt/piper/piper")
        model = config.get("piper_model", "")
        if not os.path.exists(binary):
            raise FileNotFoundError(f"Piper Binary nicht gefunden: {binary}")
        if not model or not os.path.exists(model):
            raise FileNotFoundError(f"Piper Modell nicht gefunden: {model}")
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        cmd = [binary, "--model", model, "--output_file", filepath]
        subprocess.run(cmd, input=text.encode("utf-8"), check=True)
        return filepath
    raise ValueError(f"TTS Engine nicht unterstuetzt: {engine}")
