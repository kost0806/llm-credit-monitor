#!/usr/bin/env bash
# One-liner installer for Ubuntu 22.04 / 24.04
# Usage: curl -fsSL https://<your-host>/install.sh | bash
set -euo pipefail

VERSION="0.1.0"
ARCH="amd64"
DEB_URL="https://github.com/YOUR_USERNAME/llm-credit-monitor/releases/download/v${VERSION}/llmcreditmonitor_${VERSION}_${ARCH}.deb"
TMP_DEB="/tmp/llmcreditmonitor.deb"

echo "==> LLM Credit Monitor installer"
echo "    Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y libappindicator3-1 libayatana-appindicator3-1 || true

echo "    Downloading package..."
curl -fsSL -o "$TMP_DEB" "$DEB_URL"

echo "    Installing package..."
sudo dpkg -i "$TMP_DEB"
sudo apt-get install -f -y   # resolve any missing deps

rm -f "$TMP_DEB"

echo ""
echo "==> Installation complete!"
echo "    Launch with: llmcreditmonitor &"
echo "    Or find 'LLM Credit Monitor' in your application menu."
