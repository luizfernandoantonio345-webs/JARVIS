import numpy as np
import scipy.io.wavfile as wav
from faster_whisper import WhisperModel

# ?? QUALITY GATE ??????????????????????????????????????
def avaliar_audio(data: np.ndarray, sr: int) -> dict:
    chunk = sr // 2
    chunks_rms = [
        np.sqrt(np.mean(data[i:i+chunk].astype(np.float32)**2))
        for i in range(0, len(data) - chunk, chunk)
    ]
    silencio_pct = sum(1 for r in chunks_rms if r < 200) / len(chunks_rms)
    std = np.std(chunks_rms)
    rms_global = np.sqrt(np.mean(data.astype(np.float32)**2))
    
    ok = std > 200 and rms_global > 300 and silencio_pct < 0.6
    return {
        "ok": ok,
        "std": round(std, 1),
        "rms": round(rms_global, 1),
        "silencio_pct": round(silencio_pct * 100, 1),
        "motivo": None if ok else (
            "ruido_constante" if std < 200 else
            "volume_baixo"    if rms_global < 300 else
            "muito_silencio"
        )
    }

# ?? NORMALIZA??O ??????????????????????????????????????
def normalizar(data: np.ndarray) -> np.ndarray:
    peak = np.max(np.abs(data))
    if peak < 100:
        return data
    return (data / peak * 0.8 * 32767).astype(np.int16)

# ?? PIPELINE COMPLETO ?????????????????????????????????
def transcrever(caminho_wav: str) -> str:
    sr, data = wav.read(caminho_wav)
    
    gate = avaliar_audio(data, sr)
    print(f"Quality gate: {gate}")
    
    if not gate["ok"]:
        print(f"[JARVIS] ?udio rejeitado: {gate['motivo']}")
        print("[JARVIS] Pe?a para o usu?rio repetir o comando.")
        return ""
    
    data = normalizar(data)
    wav.write("_tmp_norm.wav", sr, data)
    
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segs, info = model.transcribe(
        "_tmp_norm.wav",
        language="pt",
        vad_filter=False,
        beam_size=5,
        temperature=0.0,
    )
    text = " ".join(s.text.strip() for s in segs).strip()
    print(f"[JARVIS] Transcrito: '{text}'")
    return text

# ?? TESTE ?????????????????????????????????????????????
print("=== comando_real.wav ===")
transcrever("comando_real.wav")

import os, glob
for f in sorted(glob.glob("minha_voz*.wav"))[:2]:
    print(f"\n=== {f} ===")
    transcrever(f)
