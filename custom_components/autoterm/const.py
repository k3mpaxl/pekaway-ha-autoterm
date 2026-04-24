"""Konstanten für die Autoterm Air 2D Integration."""

DOMAIN = "autoterm"
DEFAULT_PORT = "/dev/ttyUSB0"
DEFAULT_SCAN_INTERVAL = 10  # Sekunden

# Serielle Verbindungsparameter
BAUD_RATE = 9600
SERIAL_TIMEOUT = 2.0

# Protokoll-Bytes
PREAMBLE = 0xAA
MSG_REQUEST = 0x03
MSG_RESPONSE = 0x04

# Befehle
CMD_TURN_ON = 0x01
CMD_SETTINGS = 0x02
CMD_TURN_OFF = 0x03
CMD_GET_VERSION = 0x06
CMD_GET_STATUS = 0x0F
CMD_SET_TEMP = 0x11
CMD_FAN_ONLY = 0x23

# Temperaturquelle
TEMP_SOURCE_INTERNAL = 1
TEMP_SOURCE_PANEL = 2
TEMP_SOURCE_EXTERNAL = 3
TEMP_SOURCE_NONE = 4

# Status-Codes: (byte0, byte1) -> Beschreibung
STATUS_CODES = {
    (0, 1): "Standby",
    (1, 0): "Kühlt Flammsensor",
    (1, 1): "Lüftet",
    (2, 0): "Vorbereitung Zündung",
    (2, 1): "Heizt Glühkerze",
    (2, 2): "Zündung 1",
    (2, 3): "Zündung 2",
    (2, 4): "Heizt Brennkammer",
    (3, 0): "Heizt",
    (3, 35): "Nur Lüfter",
    (3, 4): "Kühlt ab",
    (4, 0): "Fährt herunter",
}

# Zustände in denen die Heizung aktiv heizt
HEATING_STATES = {(2, 1), (2, 2), (2, 3), (2, 4), (3, 0)}
FAN_ONLY_STATE = (3, 35)
STANDBY_STATES = {(0, 1), (4, 0)}

# Temperatur-Grenzen
TEMP_MIN = 8
TEMP_MAX = 35

# Lüftergeschwindigkeiten 1-9
FAN_MODES = [str(i) for i in range(1, 10)]
DEFAULT_FAN_LEVEL = 5
DEFAULT_TARGET_TEMP = 20

# Betriebsmodi (Preset-Modes)
# - "temperature": Heizung regelt auf eine Zieltemperatur. Lüfter wird von
#   der Heizung automatisch angepasst (Temperaturquelle = Panel).
# - "power": Heizung läuft auf fester Leistungs-/Lüfterstufe 1–9
#   (Temperaturquelle = keine). Der Lüfter-Wert steuert hier die Heizleistung.
PRESET_TEMPERATURE = "temperature"
PRESET_POWER = "power"
PRESET_MODES = [PRESET_TEMPERATURE, PRESET_POWER]
DEFAULT_PRESET_MODE = PRESET_TEMPERATURE

# Freibrennschutz: Mindestlaufzeit nach dem Einschalten (in Sekunden)
# Die Heizung darf in dieser Zeit nicht ausgeschaltet werden
MIN_RUN_TIME_SECONDS = 240  # 4 Minuten

# Konfigurations-Keys
CONF_PORT = "port"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_EXTERNAL_TEMP_SENSOR = "external_temp_sensor"
CONF_HYSTERESIS = "hysteresis"
CONF_HEATER_TEMP_SOURCE = "heater_temp_source"

# Externer Temperaturfühler (HA-Entity als Thermostat)
DEFAULT_HYSTERESIS = 1.0  # °C (laut Autoterm-Doku Standardwert)

# Temperaturquelle der Heizungs-Firmware (unabhängig vom HA-Sensor).
# Werte passen zu TEMP_SOURCE_* weiter oben.
HEATER_TEMP_SOURCE_PANEL = "panel"
HEATER_TEMP_SOURCE_INTERNAL = "internal"
HEATER_TEMP_SOURCE_EXTERNAL = "external"
HEATER_TEMP_SOURCES = [
    HEATER_TEMP_SOURCE_PANEL,
    HEATER_TEMP_SOURCE_INTERNAL,
    HEATER_TEMP_SOURCE_EXTERNAL,
]
DEFAULT_HEATER_TEMP_SOURCE = HEATER_TEMP_SOURCE_PANEL

HEATER_TEMP_SOURCE_MAP = {
    HEATER_TEMP_SOURCE_PANEL: TEMP_SOURCE_PANEL,
    HEATER_TEMP_SOURCE_INTERNAL: TEMP_SOURCE_INTERNAL,
    HEATER_TEMP_SOURCE_EXTERNAL: TEMP_SOURCE_EXTERNAL,
}

# Geräte-Infos
DEVICE_MANUFACTURER = "Autoterm"
DEVICE_MODEL = "Air 2D"
