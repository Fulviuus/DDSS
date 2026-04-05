import logging

import numpy as np
from faster_whisper import WhisperModel

from ddss.config import DetectionConfig

logger = logging.getLogger(__name__)


class LanguageDetector:
    """Detects spoken language using faster-whisper."""

    def __init__(self, config: DetectionConfig):
        self.config = config
        logger.info("Loading Whisper model '%s' (this may take a moment)...", config.model)
        self.model = WhisperModel(
            config.model,
            device="cpu",
            compute_type="int8",  # optimized for ARM/Pi
        )
        logger.info("Whisper model loaded")

    def detect(self, audio: np.ndarray) -> tuple[str, float]:
        """Detect the language of an audio chunk.

        Args:
            audio: float32 numpy array at 16kHz

        Returns:
            (language_code, probability) e.g. ("nl", 0.87)
        """
        # faster-whisper's detect_language_multi_segment is more robust
        # but detect_language is faster — we use it for speed on Pi
        language, prob, all_probs = self.model.detect_language(audio)

        logger.info(
            "Detected language: %s (%.1f%%) | target '%s' threshold %.0f%%",
            language,
            prob * 100,
            self.config.target_language,
            self.config.language_threshold * 100,
        )

        # Log top 3 languages for debugging
        top3 = sorted(all_probs, key=lambda x: x[1], reverse=True)[:3]
        logger.debug("Top languages: %s", ", ".join(f"{l}={p:.1%}" for l, p in top3))

        return language, prob

    def is_target_language(self, audio: np.ndarray) -> bool:
        """Check if audio contains the target language above threshold."""
        language, prob = self.detect(audio)
        return language == self.config.target_language and prob >= self.config.language_threshold
