#!/bin/bash
# Autoterm Air 2D – Installations-Skript für Home Assistant
# Führe dieses Skript auf dem Raspberry Pi aus (via SSH)

set -e

HA_CONFIG_DIR="/homeassistant"  # Standard-Pfad bei HA OS / Supervised
CUSTOM_COMPONENTS_DIR="$HA_CONFIG_DIR/custom_components"

echo "=== Autoterm Air 2D Integration installieren ==="
echo ""

# Prüfen ob custom_components Verzeichnis existiert
if [ ! -d "$CUSTOM_COMPONENTS_DIR" ]; then
    echo "Erstelle custom_components Verzeichnis..."
    mkdir -p "$CUSTOM_COMPONENTS_DIR"
fi

# Integrationsdateien kopieren
echo "Kopiere Integration nach $CUSTOM_COMPONENTS_DIR/autoterm ..."
cp -r "$(dirname "$0")/custom_components/autoterm" "$CUSTOM_COMPONENTS_DIR/"

echo ""
echo "Prüfe verfügbare USB-Seriell-Ports:"
ls -la /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || echo "(Keine USB-Ports gefunden – bitte Kabel prüfen)"

echo ""
echo "=== Installation abgeschlossen ==="
echo ""
echo "Nächste Schritte:"
echo "1. Home Assistant neu starten"
echo "2. Einstellungen → Integrationen → + Hinzufügen → 'Autoterm Air 2D' suchen"
echo "3. Port eingeben (meist /dev/ttyUSB0)"
echo ""
echo "Hinweis: Falls der Port nicht gefunden wird, prüfe mit 'ls /dev/ttyUSB*'"
