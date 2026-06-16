Assets required for LLM Credit Monitor
=======================================

1. DejaVuSansMono-Bold.ttf  (REQUIRED for crisp icon text)
   License: DejaVu License (free/open)
   Download: https://dejavu-fonts.github.io/
   → Extract DejaVuSansMono-Bold.ttf from the zip and place it here.

   If absent, the app falls back to PIL's built-in bitmap font (lower quality).

2. tray_icon.ico  (REQUIRED for Windows installer exe icon)
   A 256×256 Windows .ico file used by PyInstaller and Inno Setup.
   You can create one from any 256×256 PNG with:
     magick convert icon.png -define icon:auto-resize="256,128,64,48,32,16" tray_icon.ico
   Or use any online ICO converter.

   If absent on Linux (no .ico needed), the PyInstaller build still succeeds.
