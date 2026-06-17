"""TTS output — edge-tts (async, sem dependências pesadas)."""
import asyncio
import logging
import os
import subprocess
import sys
import tempfile

log = logging.getLogger(__name__)


async def speak(text: str) -> bool:
    """Gera e reproduz áudio TTS. Retorna True se sucesso."""
    if not text or not text.strip():
        return False

    path = await generate_tts_file(text)
    if path is None:
        return False

    try:
        await asyncio.get_event_loop().run_in_executor(None, _play_audio, path)
        return True
    except Exception as e:
        log.warning("[TTS] Playback falhou: %s", e)
        return False
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


async def generate_tts_file(text: str, output_path: str | None = None) -> str | None:
    """Gera arquivo MP3 com TTS. Retorna o caminho ou None em falha."""
    try:
        import edge_tts
    except ImportError:
        log.warning("[TTS] edge-tts não instalado. Execute: pip install edge-tts")
        return None

    try:
        from config import get_config
        cfg = get_config()
        voice = cfg.tts_voice
        rate  = cfg.tts_rate
        pitch = cfg.tts_pitch
    except Exception:
        voice = "en-GB-RyanNeural"
        rate  = "-5%"
        pitch = "-8Hz"

    if output_path is None:
        output_path = tempfile.mktemp(suffix=".mp3")

    try:
        communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
        await communicate.save(output_path)
        return output_path
    except Exception as e:
        log.warning("[TTS] Falha ao gerar áudio: %s", e)
        return None


def _play_audio(path: str) -> None:
    """Reproduz arquivo de áudio. Tenta múltiplos backends."""
    # 1) pygame (mais confiável no Windows com MP3)
    try:
        import pygame
        pygame.mixer.init()
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(80)
        pygame.mixer.music.stop()
        pygame.mixer.quit()
        return
    except Exception:
        pass

    # 2) playsound
    try:
        import playsound
        playsound.playsound(path, block=True)
        return
    except Exception:
        pass

    if sys.platform == "win32":
        # 3) Windows Media Player via PowerShell (sem dependências extras)
        try:
            ps_cmd = (
                f'$player = New-Object System.Media.SoundPlayer; '
                f'Add-Type -AssemblyName presentationCore; '
                f'$media = New-Object System.Windows.Media.MediaPlayer; '
                f'$media.Open("{path}"); '
                f'$media.Play(); '
                f'Start-Sleep -Seconds 10; '
                f'$media.Stop()'
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                timeout=30,
                check=False,
                capture_output=True,
            )
            return
        except Exception:
            pass

        # 4) Windows: converter para WAV e usar SoundPlayer (sync)
        try:
            wav_path = path.replace(".mp3", ".wav")
            subprocess.run(
                ["ffmpeg", "-y", "-i", path, wav_path],
                timeout=15,
                check=True,
                capture_output=True,
            )
            ps_cmd = f'(New-Object System.Media.SoundPlayer "{wav_path}").PlaySync()'
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                timeout=30,
                check=False,
                capture_output=True,
            )
            try:
                os.unlink(wav_path)
            except Exception:
                pass
            return
        except Exception:
            pass
    else:
        # Linux/Mac
        for cmd in [
            ["mpg123", "-q", path],
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path],
            ["aplay", path],
        ]:
            try:
                subprocess.run(cmd, timeout=30, check=True, capture_output=True)
                return
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue

    log.warning("[TTS] Nenhum player disponível. Instale: pip install pygame")
