"""
J.A.R.V.I.S. Headset Audio Listener
Continuously listens to headset/microphone and triggers speech detection.
"""
import asyncio
import logging
import threading
import time
import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)


class HeadsetListener:
    """Listens to audio device and triggers callback on speech detected."""
    
    # Audio parameters
    SAMPLE_RATE = 16000
    CHUNK_SIZE = 1024
    SILENCE_DB = 0.015  # Threshold for speech detection
    MIN_SPEECH_S = 0.5  # Minimum speech duration
    MAX_SPEECH_S = 10.0  # Maximum speech duration
    SILENCE_END_S = 1.2  # Silence duration before end of speech
    
    def __init__(self, device_index: int = None, on_audio=None, loop=None):
        """
        Initialize headset listener.
        
        Args:
            device_index: Audio device index (None = auto-detect)
            on_audio: Async callback(audio: np.ndarray) when speech detected
            loop: Asyncio event loop
        """
        self.device = device_index
        self.on_audio = on_audio
        self.loop = loop or asyncio.get_event_loop()
        self._running = False
        self._thread = None
    
    def _detect_device(self) -> int | None:
        """Auto-detect best audio input device."""
        if self.device is not None:
            return self.device
        
        devices = sd.query_devices()
        
        # Priority: headset devices
        for i, d in enumerate(devices):
            if d['max_input_channels'] > 0:
                name = d['name'].lower()
                if any(k in name for k in ['headset', 'headphone', 'usb', 'jabra',
                                            'logitech', 'sennheiser', 'sony', 'bose']):
                    log.info('[HEADSET] Detected: %s [%d]', d['name'], i)
                    return i
        
        # Fallback: default device
        default = sd.default.device[0]
        if default is not None:
            log.info('[HEADSET] Using default: %s',
                     sd.query_devices(default)['name'])
        return default
    
    def _listen_loop(self):
        """Main listening loop (runs in thread)."""
        device = self._detect_device()
        log.info('[HEADSET] Starting listener... device=%s', device)
        
        buffer = []
        recording = False
        silence_t = 0.0
        speech_t = 0.0
        
        def callback(indata, frames, time_info, status):
            nonlocal buffer, recording, silence_t, speech_t
            
            chunk = np.squeeze(indata).copy()
            level = float(np.abs(chunk).mean())
            is_speech = level > self.SILENCE_DB
            
            if is_speech:
                if not recording:
                    recording = True
                    speech_t = time.time()
                    log.debug('[HEADSET] Recording...')
                buffer.append(chunk)
                silence_t = 0.0
            else:
                if recording:
                    silence_t += frames / self.SAMPLE_RATE
                    buffer.append(chunk)
                    
                    # Check if speech ended
                    if silence_t >= self.SILENCE_END_S:
                        duration = time.time() - speech_t
                        if duration >= self.MIN_SPEECH_S:
                            audio = np.concatenate(buffer)
                            log.info('[HEADSET] Audio captured: %.1fs', duration)
                            # Trigger callback
                            if self.on_audio and self.loop:
                                asyncio.run_coroutine_threadsafe(
                                    self.on_audio(audio), self.loop
                                )
                        buffer = []
                        recording = False
                        silence_t = 0.0
                    
                    # Keep only recent samples in buffer
                    if len(buffer) > 300:
                        buffer = buffer[-150:]
        
        try:
            with sd.InputStream(
                device=device,
                samplerate=self.SAMPLE_RATE,
                channels=1,
                dtype='float32',
                blocksize=self.CHUNK_SIZE,
                callback=callback,
            ):
                log.info('[HEADSET] Listening — speak to JARVIS')
                while self._running:
                    time.sleep(0.1)
        except Exception as e:
            log.error('[HEADSET] Error: %s', e)
    
    def start(self):
        """Start listening in background thread."""
        self._running = True
        self._thread = threading.Thread(
            target=self._listen_loop,
            daemon=True,
            name='jarvis-headset'
        )
        self._thread.start()
        log.info('[HEADSET] Thread started')
    
    def stop(self):
        """Stop listening."""
        self._running = False
        log.info('[HEADSET] Stopped')
