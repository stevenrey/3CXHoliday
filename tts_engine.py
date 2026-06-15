import os
import subprocess
import audioop
from pathlib import Path
import wave


def normalize_wav_for_3cx(filepath: str):
    path = Path(filepath)
    data = path.read_bytes()
    if not data:
        raise ValueError(f"TTS hat eine leere WAV-Datei erzeugt: {path}")

    with wave.open(str(path), "rb") as source:
        channels = source.getnchannels()
        sample_width = source.getsampwidth()
        frame_rate = source.getframerate()
        frames = source.readframes(source.getnframes())

    if channels > 1:
        frames = audioop.tomono(frames, sample_width, 0.5, 0.5)
        channels = 1
    if sample_width != 2:
        frames = audioop.lin2lin(frames, sample_width, 2)
        sample_width = 2
    if frame_rate != 8000:
        frames, _ = audioop.ratecv(frames, sample_width, channels, frame_rate, 8000, None)
        frame_rate = 8000

    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(frame_rate)
        target.writeframes(frames)

    if path.stat().st_size <= 44:
        raise ValueError(f"3CX WAV-Normalisierung hat keine Audiodaten erzeugt: {path}")


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
        normalize_wav_for_3cx(filepath)
        return filepath
    raise ValueError(f"TTS Engine nicht unterstuetzt: {engine}")
