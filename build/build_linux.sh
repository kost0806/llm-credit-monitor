#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
VERSION="${1:-0.0.0}"
ARCH="amd64"

echo "[1/4] Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y \
    python3-pip \
    libappindicator3-1 \
    libayatana-appindicator3-1 \
    dpkg-dev \
    fakeroot \
    || true   # ayatana may not exist on 22.04; ignore errors for individual pkgs

echo "[2/4] Installing Python dependencies..."
pip install -r requirements.txt pyinstaller

echo "[3/4] Building executable with PyInstaller..."
pyinstaller --clean --noconfirm build/llmcreditmonitor.spec

echo "[4/4] Building .deb package..."
PKG="llmcreditmonitor_${VERSION}_${ARCH}"
rm -rf "/tmp/${PKG}"
mkdir -p "/tmp/${PKG}/usr/bin"
mkdir -p "/tmp/${PKG}/usr/share/applications"
mkdir -p "/tmp/${PKG}/DEBIAN"

cp "dist/LLMCreditMonitor" "/tmp/${PKG}/usr/bin/llmcreditmonitor"
chmod 755 "/tmp/${PKG}/usr/bin/llmcreditmonitor"

cat > "/tmp/${PKG}/usr/share/applications/llmcreditmonitor.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=LLM Credit Monitor
Exec=/usr/bin/llmcreditmonitor
Categories=Utility;
EOF

cat > "/tmp/${PKG}/DEBIAN/control" <<EOF
Package: llmcreditmonitor
Version: ${VERSION}
Architecture: ${ARCH}
Maintainer: LLM Credit Monitor
Depends: libappindicator3-1 | libayatana-appindicator3-1
Description: LLM API credit usage system tray monitor
 Monitors Claude and ChatGPT API credit usage in real time.
EOF

cat > "/tmp/${PKG}/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
echo "LLM Credit Monitor installed. Run: llmcreditmonitor &"
EOF
chmod 755 "/tmp/${PKG}/DEBIAN/postinst"

fakeroot dpkg-deb --build "/tmp/${PKG}" "dist/${PKG}.deb"
echo "Done. Package: dist/${PKG}.deb"
