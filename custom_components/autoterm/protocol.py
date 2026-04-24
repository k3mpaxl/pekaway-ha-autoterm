"""Serielles Protokoll für die Autoterm Air 2D Standheizung."""

import logging
import threading
import serial

from .const import (
    PREAMBLE,
    MSG_REQUEST,
    MSG_RESPONSE,
    CMD_TURN_ON,
    CMD_TURN_OFF,
    CMD_GET_STATUS,
    CMD_SET_TEMP,
    CMD_FAN_ONLY,
    STATUS_CODES,
    HEATING_STATES,
    FAN_ONLY_STATE,
    STANDBY_STATES,
    BAUD_RATE,
    SERIAL_TIMEOUT,
    TEMP_SOURCE_PANEL,
    TEMP_SOURCE_NONE,
)

_LOGGER = logging.getLogger(__name__)


def crc16(data: bytes) -> bytes:
    """CRC-16 Prüfsumme berechnen (Polynom 0xA001).

    Basierend auf der Referenzimplementierung aus:
    https://github.com/schroeder-robert/autoterm-air-2d-serial-control
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            odd = crc & 0x0001
            crc >>= 1
            if odd:
                crc ^= 0xA001
    # High-Byte zuerst, dann Low-Byte (laut Referenz-Implementierung)
    return bytes([(crc >> 8) & 0xFF, crc & 0xFF])


def build_request(cmd: int, payload: bytes = b"") -> bytes:
    """Nachricht mit Header, Payload und CRC-Prüfsumme aufbauen."""
    header = bytes([PREAMBLE, MSG_REQUEST, len(payload), 0x00, cmd])
    data = header + payload
    return data + crc16(data)


class AutotermProtocol:
    """Implementiert das Kommunikationsprotokoll mit der Autoterm Air 2D."""

    def __init__(self, port: str) -> None:
        self.port = port
        self._serial: serial.Serial | None = None
        self._lock = threading.Lock()

    def connect(self) -> None:
        """Serielle Verbindung öffnen."""
        self._serial = serial.Serial(
            port=self.port,
            baudrate=BAUD_RATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=SERIAL_TIMEOUT,
        )
        _LOGGER.info("Autoterm verbunden auf Port %s", self.port)

    def disconnect(self) -> None:
        """Serielle Verbindung schließen."""
        if self._serial and self._serial.is_open:
            self._serial.close()
            _LOGGER.info("Autoterm Verbindung getrennt")

    @property
    def is_connected(self) -> bool:
        """Gibt an ob die serielle Verbindung offen ist."""
        return self._serial is not None and self._serial.is_open

    def _send_command(self, cmd: int, payload: bytes = b"") -> bytes | None:
        """Befehl senden und Antwort lesen.

        Returns:
            Antwort-Payload oder None bei Fehler/Timeout.
        """
        if not self.is_connected:
            raise ConnectionError("Serielle Verbindung nicht geöffnet")

        request = build_request(cmd, payload)
        _LOGGER.debug("TX [0x%02X]: %s", cmd, request.hex(" ").upper())

        try:
            self._serial.reset_input_buffer()
            self._serial.write(request)

            # Antwort-Header lesen (5 Bytes)
            header = self._serial.read(5)
            if len(header) < 5:
                _LOGGER.warning(
                    "Timeout beim Lesen des Antwort-Headers für Befehl 0x%02X", cmd
                )
                return None

            if header[0] != PREAMBLE:
                _LOGGER.warning("Ungültige Präambel: 0x%02X", header[0])
                return None

            if header[1] != MSG_RESPONSE:
                _LOGGER.warning(
                    "Keine Antwort-Nachricht (erwartet 0x%02X, erhalten 0x%02X)",
                    MSG_RESPONSE,
                    header[1],
                )
                return None

            payload_len = header[2]

            # Payload + 2 Prüfsummen-Bytes lesen
            remainder = self._serial.read(payload_len + 2)
            if len(remainder) < payload_len + 2:
                _LOGGER.warning(
                    "Timeout beim Lesen der Antwort-Payload (erwartet %d Bytes, erhalten %d)",
                    payload_len + 2,
                    len(remainder),
                )
                return None

            response_payload = remainder[:payload_len]
            checksum_received = remainder[payload_len:]

            # Prüfsumme validieren
            full_response = header + response_payload
            checksum_expected = crc16(full_response)

            _LOGGER.debug("RX [0x%02X]: %s", cmd, (header + remainder).hex(" ").upper())

            if checksum_received != checksum_expected:
                _LOGGER.warning(
                    "CRC-Fehler: erhalten %s, erwartet %s",
                    checksum_received.hex().upper(),
                    checksum_expected.hex().upper(),
                )
                return None

            return response_payload

        except serial.SerialException as err:
            _LOGGER.error("Serieller Kommunikationsfehler: %s", err)
            return None

    def get_status(self) -> dict:
        """Aktuellen Heizungsstatus abrufen."""
        with self._lock:
            payload = self._send_command(CMD_GET_STATUS)

        if payload is None or len(payload) < 19:
            _LOGGER.debug("Keine oder unvollständige Status-Antwort erhalten")
            return {}

        return self._parse_status(payload)

    def _parse_status(self, payload: bytes) -> dict:
        """Status-Payload parsen und in lesbare Werte umwandeln."""
        status_key = (payload[0], payload[1])
        status_text = STATUS_CODES.get(status_key, f"Unbekannt ({payload[0]}.{payload[1]})")

        # Temperaturen: Werte > 127 sind negative Temperaturen
        # 0x7F (127) = Sentinel-Wert: Sensor nicht angeschlossen → None
        raw_internal = payload[3]
        raw_external = payload[4]
        temp_internal = (
            None if raw_internal == 0x7F
            else raw_internal - 255 if raw_internal > 127
            else int(raw_internal)
        )
        temp_external = (
            None if raw_external == 0x7F
            else raw_external - 255 if raw_external > 127
            else int(raw_external)
        )

        # Spannung: Wert / 10
        voltage = round(payload[6] / 10, 1)

        # Heizungstemperatur: Wert - 15
        temp_heater = int(payload[8]) - 15

        # Lüfter RPM: Wert * 60
        fan_rpm_set = int(payload[11]) * 60
        fan_rpm_actual = int(payload[12]) * 60

        # Kraftstoffpumpen-Frequenz: Wert / 100
        fuel_pump_freq = round(payload[14] / 100, 2)

        is_heating = status_key in HEATING_STATES
        is_fan_only = status_key == FAN_ONLY_STATE
        is_off = status_key in STANDBY_STATES

        return {
            "status_key": status_key,
            "status_text": status_text,
            "temp_internal": temp_internal,
            "temp_external": temp_external,
            "temp_heater": temp_heater,
            "voltage": voltage,
            "fan_rpm_set": fan_rpm_set,
            "fan_rpm_actual": fan_rpm_actual,
            "fuel_pump_freq": fuel_pump_freq,
            "is_heating": is_heating,
            "is_fan_only": is_fan_only,
            "is_off": is_off,
        }

    def turn_on(
        self,
        target_temp: int = 20,
        fan_level: int = 5,
        power_mode: bool = False,
        temp_source: int | None = None,
    ) -> bool:
        """Heizung einschalten.

        Args:
            target_temp: Zieltemperatur in °C (8-35). Im Leistungsmodus
                wird dieser Wert von der Heizung ignoriert, aber der
                Vollständigkeit halber mitgesendet.
            fan_level: Lüfter-/Leistungsstufe (1-9). Im Temperaturmodus
                wird der Lüfter von der Heizung automatisch angepasst –
                der gesetzte Wert ist eine Vorgabe. Im Leistungsmodus
                steuert dieser Wert die tatsächliche Heizleistung.
            power_mode: ``True`` → Leistungsmodus (``temp_source=NONE``),
                ``False`` → Temperaturmodus.
            temp_source: Optional, nur im Temperaturmodus relevant. Einer
                der ``TEMP_SOURCE_*``-Werte. Default (None) entspricht
                ``TEMP_SOURCE_PANEL``. Wird von ``power_mode=True``
                überschrieben (dann immer ``TEMP_SOURCE_NONE``).

        Returns:
            True bei Erfolg, False bei Fehler.
        """
        target_temp = max(8, min(35, target_temp))
        fan_level = max(1, min(9, fan_level))

        if power_mode:
            effective_source = TEMP_SOURCE_NONE
        elif temp_source is None:
            effective_source = TEMP_SOURCE_PANEL
        else:
            effective_source = temp_source

        # Payload: work_time_disable=1, work_time=0, temp_source,
        # temp, wait_mode=0, fan/level
        payload = bytes(
            [0x01, 0x00, effective_source, target_temp, 0x00, fan_level]
        )
        _LOGGER.info(
            "Heizung einschalten: Modus=%s, Quelle=%d, Temp=%d°C, Stufe=%d",
            "Leistung" if power_mode else "Temperatur",
            effective_source,
            target_temp,
            fan_level,
        )
        with self._lock:
            response = self._send_command(CMD_TURN_ON, payload)
        return response is not None

    def turn_off(self) -> bool:
        """Heizung ausschalten.

        Returns:
            True bei Erfolg, False bei Fehler.
        """
        _LOGGER.info("Heizung ausschalten")
        with self._lock:
            response = self._send_command(CMD_TURN_OFF)
        return response is not None

    def set_temperature(self, temp: int) -> bool:
        """Zieltemperatur setzen (nur bei laufender Heizung).

        Args:
            temp: Zieltemperatur in °C (8-35)

        Returns:
            True bei Erfolg, False bei Fehler.
        """
        temp = max(8, min(35, temp))
        _LOGGER.info("Zieltemperatur setzen: %d°C", temp)
        payload = bytes([temp])
        with self._lock:
            response = self._send_command(CMD_SET_TEMP, payload)
        return response is not None

    def fan_only(self, fan_level: int = 5) -> bool:
        """Nur Lüfter einschalten (ohne Heizung).

        Args:
            fan_level: Lüfterstufe (1-9)

        Returns:
            True bei Erfolg, False bei Fehler.
        """
        fan_level = max(1, min(9, fan_level))
        _LOGGER.info("Nur Lüfter einschalten: Stufe=%d", fan_level)
        # Payload: FF FF [level] FF
        payload = bytes([0xFF, 0xFF, fan_level, 0xFF])
        with self._lock:
            response = self._send_command(CMD_FAN_ONLY, payload)
        return response is not None

    def get_version(self) -> dict:
        """Firmware-Version abrufen."""
        with self._lock:
            payload = self._send_command(0x06)

        if payload is None or len(payload) < 5:
            return {}

        return {
            "version": f"{payload[0]}.{payload[1]}.{payload[2]}.{payload[3]}",
            "blackbox_version": payload[4],
        }
