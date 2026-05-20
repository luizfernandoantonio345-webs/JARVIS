"""
J.A.R.V.I.S. Complete Voice Pipeline v3
Headset → STT → Orchestrator → TTS
"""
import asyncio
import logging
import numpy as np
import io
import wave

log = logging.getLogger(__name__)


class VoicePipelineV3:
    """Complete voice pipeline: capture → transcribe → process → speak."""
    
    def __init__(self, ws_manager=None, orchestrator=None):
        """
        Initialize voice pipeline.
        
        Args:
            ws_manager: WebSocket manager for broadcasting state
            orchestrator: Master orchestrator for processing messages
        """
        self.manager = ws_manager
        self.orchestrator = orchestrator
        self.stt = None
        self.listener = None
        self.active = False
        self._processing = False
    
    async def initialize(self):
        """Initialize STT model and start headset listener."""
        # Load Whisper STT model
        try:
            from faster_whisper import WhisperModel
            self.stt = WhisperModel(
                'small',
                device='cpu',
                compute_type='int8',
                download_root='models/whisper'
            )
            log.info('[VOICE_V3] Whisper small model loaded')
        except Exception as e:
            log.warning('[VOICE_V3] Whisper load failed: %s', e)
        
        # Start headset listener
        loop = asyncio.get_event_loop()
        from voice_v2.headset_listener import HeadsetListener
        self.listener = HeadsetListener(
            on_audio=self._on_audio,
            loop=loop
        )
        self.listener.start()
        self.active = True
        log.info('[VOICE_V3] Pipeline active — listening to headset')
    
    async def _on_audio(self, audio: np.ndarray):
        """Callback when audio is captured from headset."""
        if self._processing:
            log.debug('[VOICE_V3] Still processing — ignoring')
            return
        self._processing = True
        try:
            await self._process(audio)
        finally:
            self._processing = False
    
    async def _process(self, audio: np.ndarray):
        """Process audio: STT → Orchestrator → TTS."""
        # 1. TRANSCRIBE
        text = await self._transcribe(audio)
        if not text or len(text.strip()) < 2:
            log.debug('[VOICE_V3] Audio empty or too short')
            return
        
        log.info('[VOICE_V3] Transcription: %s', text)
        
        # Notify frontend
        if self.manager:
            await self.manager.broadcast({
                'event': 'voice_state',
                'state': 'PROCESSING',
                'text': text
            })
        
        # 2. PROCESS MESSAGE
        try:
            if self.orchestrator:
                response = await self.orchestrator.execute(
                    text, 'voice', on_token=None
                )
            else:
                # Fallback to simple chat service
                from services.chat_service import process_message
                response = await asyncio.get_event_loop().run_in_executor(
                    None, process_message, text, 'voice'
                )
        except Exception as e:
            log.error('[VOICE_V3] Orchestrator failed: %s', e)
            response = "I apologize, Sir. An error has occurred."
        
        log.info('[VOICE_V3] Response: %s', response[:80])
        
        # 3. SPEAK
        if self.manager:
            await self.manager.broadcast({
                'event': 'voice_state',
                'state': 'SPEAKING',
                'text': response
            })
        
        from voice_v2.output import speak
        await speak(response)
        
        # 4. DONE
        if self.manager:
            await self.manager.broadcast({
                'event': 'voice_state',
                'state': 'IDLE'
            })
    
    async def _transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio to text using Whisper."""
        if self.stt is None:
            log.debug('[VOICE_V3] Whisper not loaded')
            return ""
        
        try:
            import soundfile as sf
            
            # Convert numpy array to WAV in memory
            buf = io.BytesIO()
            sf.write(buf, audio, 16000, format='WAV')
            buf.seek(0)
            
            # Run Whisper transcription in executor
            segments, _ = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.stt.transcribe(
                    buf,
                    language='pt',
                    task='transcribe',
                    vad_filter=True
                )
            )
            
            text = " ".join(s.text for s in segments).strip()
            return text
        except Exception as e:
            log.error('[VOICE_V3] Transcription failed: %s', e)
            return ""
    
    def status(self) -> dict:
        """Return current pipeline status."""
        return {
            "active": self.active,
            "processing": self._processing,
            "stt_loaded": self.stt is not None,
            "listener_ok": self.listener is not None,
        }


# Global pipeline instance
_pipeline = None

def get_voice_pipeline() -> VoicePipelineV3:
    """Get or create global voice pipeline."""
    global _pipeline
    if _pipeline is None:
        _pipeline = VoicePipelineV3()
    return _pipeline
