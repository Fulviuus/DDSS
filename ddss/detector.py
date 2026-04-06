import logging
from collections import deque

import numpy as np
from faster_whisper import WhisperModel

from ddss.config import DetectionConfig

logger = logging.getLogger(__name__)

# Require N detections out of the last M chunks to trigger
CONSENSUS_REQUIRED = 2
CONSENSUS_WINDOW = 3


class LanguageDetector:
    """Detects spoken language using faster-whisper transcription."""

    def __init__(self, config: DetectionConfig):
        self.config = config
        self._recent_detections: deque[bool] = deque(maxlen=CONSENSUS_WINDOW)

        logger.info("Loading Whisper model '%s' (this may take a moment)...", config.model)
        self.model = WhisperModel(
            config.model,
            device="cpu",
            compute_type="int8",  # optimized for ARM/Pi
        )
        logger.info("Whisper model loaded")

    def detect(self, audio: np.ndarray) -> tuple[str, float, str]:
        """Detect the language of an audio chunk via transcription.

        Transcribing is much more accurate than detect_language() because
        Whisper commits to a language based on actual decoded words rather
        than just audio features.

        Args:
            audio: float32 numpy array at 16kHz

        Returns:
            (language_code, probability, transcript) e.g. ("nl", 0.87, "hoe gaat het")
        """
        segments, info = self.model.transcribe(
            audio,
            beam_size=1,          # fastest decoding
            best_of=1,
            vad_filter=True,      # skip non-speech within the chunk
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        # Consume segments to get the transcript
        text_parts = []
        for segment in segments:
            text_parts.append(segment.text)
        transcript = " ".join(text_parts).strip()

        language = info.language
        prob = info.language_probability

        logger.info(
            "Detected: %s (%.1f%%) | \"%s\"",
            language,
            prob * 100,
            transcript[:80] if transcript else "(silence)",
        )

        return language, prob, transcript

    def is_target_language(self, audio: np.ndarray) -> bool:
        """Check if audio contains the target language with consensus.

        Requires CONSENSUS_REQUIRED detections in the last CONSENSUS_WINDOW
        chunks to avoid false positives from single misdetections.
        """
        language, prob, transcript = self.detect(audio)

        is_target = (
            language == self.config.target_language
            and prob >= self.config.language_threshold
            and len(transcript) > 0  # ignore empty transcripts
        )
        self._recent_detections.append(is_target)

        target_count = sum(self._recent_detections)

        if is_target:
            logger.info(
                "Target language match (%d/%d in last %d chunks, need %d)",
                target_count,
                len(self._recent_detections),
                CONSENSUS_WINDOW,
                CONSENSUS_REQUIRED,
            )

        return target_count >= CONSENSUS_REQUIRED
