import io
import logging
import socket
import struct
import threading
import time
import wave

import numpy as np
import soco

from ddss.config import SonosConfig

logger = logging.getLogger(__name__)


def _generate_siren_wav(duration_seconds: int, sample_rate: int = 44100) -> bytes:
    """Generate a two-tone siren WAV file in memory.

    Alternates between 800Hz and 1200Hz every 0.5 seconds.
    """
    t = np.linspace(0, duration_seconds, duration_seconds * sample_rate, dtype=np.float32)

    # Alternate between two frequencies every 0.5s
    cycle = 0.5
    freq = np.where((t % (cycle * 2)) < cycle, 800.0, 1200.0)

    # Generate sine wave
    phase = np.cumsum(freq / sample_rate) * 2 * np.pi
    samples = (np.sin(phase) * 0.9 * 32767).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())

    return buf.getvalue()


def _get_local_ip() -> str:
    """Get the local IP address that can reach the network."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


class _SirenHTTPHandler:
    """Minimal HTTP handler that serves the siren WAV file."""

    def __init__(self, wav_data: bytes):
        self.wav_data = wav_data


class _SirenServer(threading.Thread):
    """Background HTTP server that serves the siren WAV."""

    def __init__(self, wav_data: bytes):
        super().__init__(daemon=True)
        self.wav_data = wav_data
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind(("0.0.0.0", 0))
        self.port = self._server_socket.getsockname()[1]
        self._server_socket.listen(5)
        self._running = True

    def run(self):
        while self._running:
            try:
                self._server_socket.settimeout(1.0)
                conn, addr = self._server_socket.accept()
                self._handle(conn)
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logger.debug("Server error: %s", e)

    def _handle(self, conn: socket.socket):
        try:
            conn.recv(4096)  # consume the HTTP request
            header = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: audio/wav\r\n"
                f"Content-Length: {len(self.wav_data)}\r\n"
                "Connection: close\r\n"
                "\r\n"
            )
            conn.sendall(header.encode() + self.wav_data)
        except Exception as e:
            logger.debug("Connection error: %s", e)
        finally:
            conn.close()

    def stop(self):
        self._running = False
        self._server_socket.close()


class SonosAction:
    """Plays a siren on a Sonos speaker when triggered."""

    def __init__(self, config: SonosConfig):
        self.config = config

        # Generate siren WAV
        logger.info("Generating %ds siren audio...", config.siren_duration_seconds)
        self._wav_data = _generate_siren_wav(config.siren_duration_seconds)

        # Start HTTP server to serve the WAV
        self._server = _SirenServer(self._wav_data)
        self._server.start()
        self._local_ip = _get_local_ip()
        self._siren_url = f"http://{self._local_ip}:{self._server.port}/siren.wav"
        logger.info("Siren served at %s", self._siren_url)

        # Find the Sonos speaker
        logger.info("Discovering Sonos speaker '%s'...", config.speaker_name)
        self.speaker = self._find_speaker()
        if self.speaker:
            logger.info("Found Sonos speaker: %s (%s)", self.speaker.player_name, self.speaker.ip_address)
        else:
            logger.error(
                "Speaker '%s' not found. Available speakers: %s",
                config.speaker_name,
                [s.player_name for s in soco.discover() or []],
            )

    def _find_speaker(self) -> soco.SoCo | None:
        speakers = soco.discover()
        if not speakers:
            logger.error("No Sonos speakers found on the network")
            return None
        for speaker in speakers:
            if speaker.player_name == self.config.speaker_name:
                return speaker
        return None

    def trigger(self):
        if not self.speaker:
            logger.warning("No Sonos speaker available, skipping siren")
            return

        logger.info("Playing siren on '%s' at volume %d", self.speaker.player_name, self.config.volume)

        try:
            # Save current state
            prev_volume = self.speaker.volume
            prev_uri = self.speaker.get_current_transport_info().get("current_transport_state")

            # Set volume and play siren
            self.speaker.volume = self.config.volume
            self.speaker.play_uri(self._siren_url, title="DDSS SIREN - Niente olandese!")

            # Wait for siren to finish
            time.sleep(self.config.siren_duration_seconds + 1)

            # Restore previous volume
            self.speaker.volume = prev_volume
            self.speaker.stop()
            logger.info("Siren complete, volume restored to %d", prev_volume)

        except Exception as e:
            logger.error("Failed to play siren: %s", e)

    def shutdown(self):
        self._server.stop()
