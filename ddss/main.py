"""DDSS - Dutch Detection & Suppression System

Continuously listens to ambient speech and triggers Philips Hue actions
when Dutch is detected.
"""

import argparse
import logging
import signal
import sys
import time

from ddss.actions import HueAction
from ddss.audio import AudioRecorder
from ddss.config import load_config
from ddss.detector import LanguageDetector

logger = logging.getLogger("ddss")


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main():
    parser = argparse.ArgumentParser(description="Dutch Detection & Suppression System")
    parser.add_argument("-c", "--config", default="config.yaml", help="Path to config file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect language but don't trigger Hue actions",
    )
    args = parser.parse_args()

    setup_logging(args.verbose)
    logger.info("DDSS - Dutch Detection & Suppression System")
    logger.info("Niente olandese in questa casa!")

    config = load_config(args.config)

    # Initialize components
    recorder = AudioRecorder(config.audio)
    detector = LanguageDetector(config.detection)

    hue = None
    if not args.dry_run:
        try:
            hue = HueAction(config.hue)
        except Exception as e:
            logger.error("Failed to connect to Hue bridge: %s", e)
            logger.info("Continuing in detection-only mode")
    else:
        logger.info("Dry-run mode: Hue actions disabled")

    # Graceful shutdown
    running = True

    def shutdown(signum, frame):
        nonlocal running
        logger.info("Shutting down...")
        running = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Main loop
    last_trigger = 0.0
    cooldown = config.detection.cooldown_seconds
    dutch_count = 0

    logger.info("Listening... (cooldown=%ds, threshold=%.0f%%)", cooldown, config.detection.language_threshold * 100)

    try:
        for chunk in recorder.stream():
            if not running:
                break

            if detector.is_target_language(chunk):
                dutch_count += 1
                now = time.time()
                elapsed = now - last_trigger

                if elapsed >= cooldown:
                    logger.warning(
                        "DUTCH DETECTED! (occurrence #%d) — triggering action",
                        dutch_count,
                    )
                    if hue:
                        hue.trigger()
                    last_trigger = now
                else:
                    remaining = cooldown - elapsed
                    logger.info(
                        "Dutch detected but in cooldown (%.0fs remaining)",
                        remaining,
                    )
    except KeyboardInterrupt:
        pass

    logger.info("DDSS stopped. Total Dutch detections: %d", dutch_count)


if __name__ == "__main__":
    main()
