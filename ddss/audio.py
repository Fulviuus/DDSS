import logging
import struct
import sys

import numpy as np
import webrtcvad

from ddss.config import AudioConfig

logger = logging.getLogger(__name__)

# webrtcvad requires 16-bit PCM at 16kHz in 10/20/30ms frames
VAD_FRAME_MS = 30
VAD_AGGRESSIVENESS = 2  # 0-3, higher = more aggressive filtering


class AudioRecorder:
    """Continuously captures audio from the mic and yields speech chunks."""

    def __init__(self, config: AudioConfig):
        self.config = config
        self.sample_rate = config.sample_rate
        self.chunk_samples = config.chunk_seconds * self.sample_rate
        self.vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)

    def _has_speech(self, audio: np.ndarray) -> bool:
        """Check if audio chunk contains speech using webrtcvad."""
        pcm_16bit = (audio * 32767).astype(np.int16)
        frame_size = int(self.sample_rate * VAD_FRAME_MS / 1000)
        num_frames = len(pcm_16bit) // frame_size
        if num_frames == 0:
            return False

        voiced_frames = 0
        for i in range(num_frames):
            start = i * frame_size
            frame_bytes = struct.pack(f"{frame_size}h", *pcm_16bit[start : start + frame_size])
            try:
                if self.vad.is_speech(frame_bytes, self.sample_rate):
                    voiced_frames += 1
            except Exception:
                continue

        ratio = voiced_frames / num_frames if num_frames > 0 else 0
        return ratio > 0.15  # at least 15% of frames have speech

    def _open_stream(self):
        """Open an audio input stream using the best available backend."""
        device = self.config.device

        # Try alsaaudio first (direct ALSA, works reliably on Pi)
        try:
            import alsaaudio

            alsa_device = device if isinstance(device, str) else "default"
            pcm = alsaaudio.PCM(
                alsaaudio.PCM_CAPTURE,
                channels=1,
                rate=self.sample_rate,
                format=alsaaudio.PCM_FORMAT_S16_LE,
                periodsize=int(self.sample_rate * VAD_FRAME_MS / 1000),
                device=alsa_device,
            )
            logger.info("Using ALSA backend (device=%s)", alsa_device)
            return ("alsa", pcm)
        except ImportError:
            pass
        except Exception as e:
            logger.warning("ALSA failed: %s, trying sounddevice", e)

        # Fall back to sounddevice/PortAudio (works on Windows/Mac)
        import sounddevice as sd

        block_samples = int(self.sample_rate * VAD_FRAME_MS / 1000)
        stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=block_samples,
            device=device if isinstance(device, int) else None,
        )
        stream.start()
        logger.info("Using PortAudio/sounddevice backend (device=%s)", device)
        return ("sounddevice", stream)

    def stream(self):
        """Yield audio chunks (numpy float32 arrays) that contain speech.

        Each chunk is ~chunk_seconds long. Silent chunks are skipped.
        """
        logger.info(
            "Starting audio capture (device=%s, rate=%d, chunk=%ds)",
            self.config.device,
            self.sample_rate,
            self.config.chunk_seconds,
        )

        backend, handle = self._open_stream()
        overlap_samples = self.sample_rate  # 1 second overlap
        buffer = []
        buffered_samples = 0

        try:
            while True:
                if backend == "alsa":
                    length, data = handle.read()
                    if length <= 0:
                        continue
                    block = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32767.0
                else:
                    # sounddevice
                    block_size = int(self.sample_rate * VAD_FRAME_MS / 1000)
                    data, overflowed = handle.read(block_size)
                    if overflowed:
                        logger.warning("Audio buffer overflow")
                    block = data[:, 0]

                buffer.append(block)
                buffered_samples += len(block)

                if buffered_samples >= self.chunk_samples:
                    chunk = np.concatenate(buffer)

                    # Keep last second as overlap
                    keep_samples = 0
                    kept = []
                    for b in reversed(buffer):
                        keep_samples += len(b)
                        kept.append(b)
                        if keep_samples >= overlap_samples:
                            break
                    buffer = list(reversed(kept))
                    buffered_samples = sum(len(b) for b in buffer)

                    if self._has_speech(chunk):
                        logger.debug("Speech detected in chunk (%d samples)", len(chunk))
                        yield chunk
                    else:
                        logger.debug("Silence, skipping chunk")
        finally:
            if backend == "alsa":
                handle.close()
            else:
                handle.stop()
                handle.close()
