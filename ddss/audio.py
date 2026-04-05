import logging
import queue
import struct
from collections import deque

import numpy as np
import sounddevice as sd
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
        self._queue: queue.Queue[np.ndarray] = queue.Queue()

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status):
        if status:
            logger.warning("Audio status: %s", status)
        self._queue.put(indata[:, 0].copy())

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

        # Use a small block size for the callback; we'll accumulate into chunks
        block_samples = int(self.sample_rate * VAD_FRAME_MS / 1000)

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=block_samples,
            device=self.config.device,
            callback=self._audio_callback,
        ):
            buffer = deque()
            buffered_samples = 0

            while True:
                block = self._queue.get()
                buffer.append(block)
                buffered_samples += len(block)

                if buffered_samples >= self.chunk_samples:
                    chunk = np.concatenate(list(buffer))
                    # Keep last second as overlap for next chunk
                    overlap_samples = self.sample_rate
                    keep_from = max(0, len(buffer) - overlap_samples // block_samples)
                    buffer = deque(list(buffer)[keep_from:])
                    buffered_samples = sum(len(b) for b in buffer)

                    if self._has_speech(chunk):
                        logger.debug("Speech detected in chunk (%d samples)", len(chunk))
                        yield chunk
                    else:
                        logger.debug("Silence, skipping chunk")
