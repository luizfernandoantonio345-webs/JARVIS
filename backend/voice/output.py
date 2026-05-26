import logging
import asyncio
import tempfile
import os
import io
import importlib
import hashlib
from pathlib import Path
from functools import lru_cache
import time

import winsound

log = logging.getLogger(__name__)

# ── TTS Cache for instant responses ──────────────────────────────────────────
_tts_cache = {}  # {text_hash: (file_path, timestamp)}
_tts_cache_dir = Path(tempfile.gettempdir()) / "jarvis_tts_cache"
_tts_cache_dir.mkdir(exist_ok=True)
_tts_cache_max_age = 86400 * 7  # 7 days

def _get_cache_key(text: str) -> str:
    """Generate cache key from text."""
    return hashlib.md5(text.encode()).hexdigest()[:16]

def _get_cached_path(text: str) -> str | None:
    """Get cached TTS audio file if exists and valid."""
    key = _get_cache_key(text)
    cache_file = _tts_cache_dir / f"tts_{key}.mp3"
    
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < _tts_cache_max_age:
            log.debug(f"[TTS] Cache HIT: {text[:30]}...")
            return str(cache_file)
    return None

def _save_to_cache(text: str, file_path: Path | str) -> None:
    """Save TTS audio to cache."""
    key = _get_cache_key(text)
    cache_file = _tts_cache_dir / f"tts_{key}.mp3"
    try:
        if isinstance(file_path, str):
            file_path = Path(file_path)
        if file_path.exists():
            cache_file.write_bytes(file_path.read_bytes())
            log.debug(f"[TTS] Cached: {text[:30]}...")
    except Exception as e:
        log.debug(f"[TTS] Cache save failed: {e}")

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


async def speak(text: str, voice: str = None) -> str:
    """
    Converte texto em fala e reproduz com voz britânica JARVIS.

    Voz padrão: en-GB-RyanNeural (britânica, masculina, refinada)
    Fallback: pyttsx3 com vozes em inglês/português

    Estratégia:
      1. Check cache (0ms hit)
      2. edge_tts com voz britânica, pitch/rate configurados
      3. Tocar via PowerShell (mais confiável no Windows)
      4. Fallback: pyttsx3 singleton
    """
    if not text or not text.strip():
        return ""

    clean = _clean_text(text)
    if not clean:
        return False

    # ── Check cache first ────────────────────────────────────────────────────
    cached_file = _get_cached_path(clean)
    if cached_file:
        # Play cached file
        def _play_powershell_cached():
            try:
                import subprocess
                cmd = (
                    f'$p = New-Object System.Windows.Media.MediaPlayer;'
                    f'$p.Open([uri]"{cached_file}");'
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
                return result.returncode == 0
            except Exception as e:
                log.warning("[TTS] Cached playback failed: %s", e)
                return False
        
        success = await asyncio.to_thread(_play_powershell_cached)
        if success:
            log.info("[TTS] Cache playback OK: %s", clean[:50])
            return cached_file
        # Fallback to re-generate if cache playback fails

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

            # Do not delete immediately: return the path to caller for further handling.
            if success:
                _save_to_cache(clean, temp_path)  # Cache for next time
                log.info("[TTS] edge_tts (%s) OK: %s", voice, clean[:50])
                return temp_path
            else:
                log.warning("[TTS] edge_tts produced audio but playback failed")
                return temp_path

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
                # No file generated for pyttsx3; return empty string to indicate playback done
                return ""

    except Exception as e:
        log.error("[TTS] pyttsx3 também falhou: %s", e)

    return ""


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
