import logging
import threading
import time

from phue import Bridge

from ddss.config import HueConfig

logger = logging.getLogger(__name__)


class HueAction:
    """Controls Philips Hue lights in response to Dutch detection."""

    def __init__(self, config: HueConfig):
        self.config = config
        self._saved_states: dict[int, dict] = {}
        self._restore_timers: list[threading.Timer] = []

        logger.info("Connecting to Hue bridge at %s...", config.bridge_ip)
        self.bridge = Bridge(config.bridge_ip)
        self.bridge.connect()
        logger.info("Connected to Hue bridge")

        self.light_ids = self._resolve_lights()
        if not self.light_ids:
            logger.warning("No matching lights found! Check config.hue.lights")

    def _resolve_lights(self) -> list[int]:
        """Resolve light names to IDs."""
        all_lights = self.bridge.get_light_objects("name")
        ids = []
        for name in self.config.lights:
            if name in all_lights:
                light = all_lights[name]
                ids.append(light.light_id)
                logger.info("Resolved light '%s' -> ID %d", name, light.light_id)
            else:
                logger.warning(
                    "Light '%s' not found. Available: %s",
                    name,
                    list(all_lights.keys()),
                )
        return ids

    def _save_states(self):
        """Save current light states for later restoration."""
        for lid in self.light_ids:
            state = self.bridge.get_light(lid)["state"]
            self._saved_states[lid] = {
                "on": state["on"],
                "bri": state.get("bri", 254),
                "hue": state.get("hue", 0),
                "sat": state.get("sat", 0),
            }

    def _restore_states(self):
        """Restore lights to their saved states."""
        logger.info("Restoring light states")
        for lid, state in self._saved_states.items():
            try:
                self.bridge.set_light(lid, state)
            except Exception as e:
                logger.error("Failed to restore light %d: %s", lid, e)
        self._saved_states.clear()

    def _schedule_restore(self):
        """Schedule light state restoration after configured delay."""
        if self.config.restore_after_seconds > 0:
            timer = threading.Timer(self.config.restore_after_seconds, self._restore_states)
            timer.daemon = True
            timer.start()
            self._restore_timers.append(timer)
            logger.info("Will restore lights in %ds", self.config.restore_after_seconds)

    def _action_off(self):
        """Turn off all configured lights."""
        logger.info("Turning off %d light(s)", len(self.light_ids))
        for lid in self.light_ids:
            self.bridge.set_light(lid, "on", False)

    def _action_flash(self):
        """Flash lights with configured color."""
        color = self.config.flash_color
        logger.info("Flashing %d light(s)", len(self.light_ids))
        for lid in self.light_ids:
            self.bridge.set_light(
                lid,
                {
                    "on": True,
                    "hue": color.hue,
                    "sat": color.saturation,
                    "bri": color.brightness,
                    "alert": "lselect",  # 15-second flash cycle
                },
            )

    def _action_flash_then_off(self):
        """Flash lights, then turn them off after a brief delay."""
        self._action_flash()
        time.sleep(3)
        self._action_off()

    def _action_color_alert(self):
        """Set lights to alert color (stays on)."""
        color = self.config.flash_color
        logger.info("Setting %d light(s) to alert color", len(self.light_ids))
        for lid in self.light_ids:
            self.bridge.set_light(
                lid,
                {
                    "on": True,
                    "hue": color.hue,
                    "sat": color.saturation,
                    "bri": color.brightness,
                },
            )

    def trigger(self):
        """Execute the configured action."""
        if not self.light_ids:
            logger.warning("No lights configured, skipping action")
            return

        self._save_states()

        actions = {
            "off": self._action_off,
            "flash": self._action_flash,
            "flash_then_off": self._action_flash_then_off,
            "color_alert": self._action_color_alert,
        }

        action_fn = actions.get(self.config.action)
        if action_fn is None:
            logger.error(
                "Unknown action '%s'. Available: %s",
                self.config.action,
                list(actions.keys()),
            )
            return

        logger.info("Executing action: %s", self.config.action)
        try:
            action_fn()
        except Exception as e:
            logger.error("Action failed: %s", e)
            return

        self._schedule_restore()
