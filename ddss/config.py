import yaml
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

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
    "hue": {
        "bridge_ip": "192.168.1.1",
        "lights": [],
        "action": "flash_then_off",
        "flash_color": {"hue": 0, "saturation": 254, "brightness": 254},
        "restore_after_seconds": 60,
    },
}


@dataclass
class AudioConfig:
    device: Optional[int] = None
    chunk_seconds: int = 5
    sample_rate: int = 16000


@dataclass
class DetectionConfig:
    model: str = "small"
    language_threshold: float = 0.5
    target_language: str = "nl"
    cooldown_seconds: int = 30


@dataclass
class FlashColor:
    hue: int = 0
    saturation: int = 254
    brightness: int = 254


@dataclass
class HueConfig:
    bridge_ip: str = "192.168.1.1"
    lights: list[str] = field(default_factory=list)
    action: str = "flash_then_off"
    flash_color: FlashColor = field(default_factory=FlashColor)
    restore_after_seconds: int = 60


@dataclass
class Config:
    audio: AudioConfig = field(default_factory=AudioConfig)
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    hue: HueConfig = field(default_factory=HueConfig)


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

    flash_color = FlashColor(**merged["hue"].pop("flash_color"))
    return Config(
        audio=AudioConfig(**merged["audio"]),
        detection=DetectionConfig(**merged["detection"]),
        hue=HueConfig(flash_color=flash_color, **merged["hue"]),
    )
