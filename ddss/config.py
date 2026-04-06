import yaml
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

DEFAULTS = {
    "audio": {
        "device": None,
        "chunk_seconds": 5,
        "sample_rate": 16000,
    },
    "detection": {
        "model": "small",
        "language_threshold": 0.5,
        "target_language": "nl",
        "cooldown_seconds": 30,
    },
    "sonos": {
        "speaker_name": "Living Room",
        "volume": 50,
        "siren_duration_seconds": 5,
    },
}


@dataclass
class AudioConfig:
    device: Union[None, int, str] = None  # None=default, int=PortAudio index, str=ALSA device name
    chunk_seconds: int = 5
    sample_rate: int = 16000


@dataclass
class DetectionConfig:
    model: str = "small"
    language_threshold: float = 0.5
    target_language: str = "nl"
    cooldown_seconds: int = 30


@dataclass
class SonosConfig:
    speaker_name: str = "Living Room"
    volume: int = 50
    siren_duration_seconds: int = 5


@dataclass
class Config:
    audio: AudioConfig = field(default_factory=AudioConfig)
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    sonos: SonosConfig = field(default_factory=SonosConfig)


def _merge(defaults: dict, overrides: dict) -> dict:
    result = dict(defaults)
    for key, value in overrides.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: str | Path = "config.yaml") -> Config:
    path = Path(path)
    if path.exists():
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        logger.info("Loaded config from %s", path)
    else:
        logger.warning("Config file %s not found, using defaults", path)
        raw = {}

    merged = _merge(DEFAULTS, raw)

    return Config(
        audio=AudioConfig(**merged["audio"]),
        detection=DetectionConfig(**merged["detection"]),
        sonos=SonosConfig(**merged["sonos"]),
    )
