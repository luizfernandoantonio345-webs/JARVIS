import logging
import asyncio
import tempfile
import os
import io
import importlib
from pathlib import Path

import winsound

log = logging.getLogger(__name__)

# ── pyttsx3 engine singleton ──────────────────────────────────────────────────
# Reutilizar a instância evita o overhead de init (~200ms) em cada chamada.
_pyttsx3_engine = None
_pyttsx3_lock = asyncio.Lock()


def _get_pyttsx3():
    global _pyttsx3_engine
    if _pyttsx3_engine is None:
        pyttsx3 = importlib.import_module("pyttsx3")
        _pyttsx3_engine = pyttsx3.init()
        _pyttsx3_engine.setProperty("rate", 165)
        _pyttsx3_engine.setProperty("volume", 0.95)
        # Voz pt-BR se disponível
        for v in _pyttsx3_engine.getProperty("voices"):
            if "pt" in (v.languages[0] if v.languages else "").lower() or "brazil" in v.name.lower():
                _pyttsx3_engine.setProperty("voice", v.id)
                break
    return _pyttsx3_engine


def _clean_text(text: str) -> str:
    clean = text[:400]
    for ch in ["**", "##", "```", "*", "_", "#"]:
        clean = clean.replace(ch, "")
    return clean.strip()


async def speak(text: str, voice: str = None) -> bool:
    """
    Converte texto em fala e reproduz com voz britânica JARVIS.

    Voz padrão: en-GB-RyanNeural (britânica, masculina, refinada)
    Fallback: pyttsx3 com vozes em inglês/português

    Estratégia:
      1. edge_tts com voz britânica, pitch/rate configurados
      2. Tocar via PowerShell (mais confiável no Windows)
      3. Fallback: pyttsx3 singleton
    """
    if not text or not text.strip():
        return False

    clean = _clean_text(text)
    if not clean:
        return False

    # Voz britânica JARVIS por padrão
    voice = voice or os.getenv('JARVIS_TTS_VOICE', 'en-GB-RyanNeural')
    rate = os.getenv('JARVIS_TTS_RATE', '-5%')
    pitch = os.getenv('JARVIS_TTS_PITCH', '-8Hz')

    # ── Estratégia 1: edge_tts com voz britânica ──────────────────────────────
    try:
        edge_tts = importlib.import_module("edge_tts")

        temp_path = tempfile.mktemp(suffix=".mp3")

        # Usar Communicate com rate/pitch
        communicate = edge_tts.Communicate(
            clean, voice, rate=rate, pitch=pitch
        )
        
        # Streaming para arquivo
        audio_buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_buf.write(chunk["data"])

        if audio_buf.tell() > 500:  # Arquivo válido
            audio_buf.seek(0)
            Path(temp_path).write_bytes(audio_buf.read())

            # Tocar via PowerShell (mais confiável)
            def _play_powershell():
                try:
                    import subprocess
                    # PowerShell: MediaPlayer
                    cmd = (
                        f'$p = New-Object System.Windows.Media.MediaPlayer;'
                        f'$p.Open([uri]"{temp_path}");'
                        f'$p.Play();'
                        f'Start-Sleep -Milliseconds 300;'
                        f'$d = $p.NaturalDuration.TimeSpan.TotalSeconds;'
                        f'if($d -gt 0){{Start-Sleep -Seconds ($d + 0.5)}} '
                        f'else{{Start-Sleep 4}};'
                        f'$p.Close();'
                    )
                    result = subprocess.run(
                        ['powershell', '-Command', cmd],
                        capture_output=True,
                        timeout=40
                    )
                    if result.returncode == 0:
                        return True
                except Exception as e:
                    log.warning("[TTS] PowerShell falhou: %s", e)
                return False

            success = await asyncio.to_thread(_play_powershell)
            
            try:
                os.unlink(temp_path)
            except:
                pass

            if success:
                log.info("[TTS] edge_tts (%s) OK: %s", voice, clean[:50])
                return True

    except Exception as e:
        log.warning("[TTS] edge_tts falhou: %s", e)

    # ── Estratégia 2: pyttsx3 singleton (fallback offline) ────────────────────
    try:
        async with _pyttsx3_lock:
            engine = await asyncio.to_thread(_get_pyttsx3)

            def _say():
                try:
                    # Tentar configurar voz em inglês
                    for v in engine.getProperty("voices"):
                        v_name = v.name.lower() if hasattr(v, 'name') else v.id.lower()
                        if any(k in v_name for k in ['david', 'english', 'us', 'uk']):
                            engine.setProperty("voice", v.id)
                            break
                    
                    engine.setProperty("rate", 145)
                    engine.setProperty("volume", 1.0)
                    engine.say(clean)
                    engine.runAndWait()
                    return True
                except Exception as e:
                    log.error("[TTS] pyttsx3 playback failed: %s", e)
                    return False

            success = await asyncio.to_thread(_say)
            if success:
                log.info("[TTS] pyttsx3 (fallback) OK: %s", clean[:50])
                return True

    except Exception as e:
        log.error("[TTS] pyttsx3 também falhou: %s", e)

    return False


async def speak_silent(text: str, voice: str = None) -> str:
    """Gera áudio TTS e salva em arquivo sem reproduzir (para resposta de API)."""
    voice = voice or os.getenv('JARVIS_TTS_VOICE', 'en-GB-RyanNeural')
    rate = os.getenv('JARVIS_TTS_RATE', '-5%')
    pitch = os.getenv('JARVIS_TTS_PITCH', '-8Hz')
    
    temp_path = tempfile.mktemp(suffix=".mp3")
    try:
        edge_tts = importlib.import_module("edge_tts")
        clean = _clean_text(text)
        
        communicate = edge_tts.Communicate(clean, voice, rate=rate, pitch=pitch)
        audio_buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_buf.write(chunk["data"])
        
        if audio_buf.tell() > 500:
            audio_buf.seek(0)
            Path(temp_path).write_bytes(audio_buf.read())
            log.info("[TTS] speak_silent saved: %s", temp_path)
            return temp_path
    except Exception as e:
        log.warning("[TTS] speak_silent edge_tts falhou: %s", e)
    return ""
