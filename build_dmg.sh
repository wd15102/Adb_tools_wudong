#!/bin/bash

APP_NAME="adbtool"
APP_DISPLAY_NAME="adbtool"
PYINSTALLER_SPEC="adbtool-macos.spec"
APP_DIR="dist/${APP_NAME}.app"
DMG_NAME="${APP_DISPLAY_NAME}.dmg"
VOLUME_NAME="${APP_DISPLAY_NAME} Installer"
STAGING_DIR="dmg-tmp"

echo "[1] Cleaning..."
rm -rf build dist "$DMG_NAME" "$STAGING_DIR"
mkdir "$STAGING_DIR"

echo "[2] Building app with PyInstaller..."
pyinstaller "$PYINSTALLER_SPEC"

echo "[3] Removing quarantine..."
xattr -rd com.apple.quarantine "$APP_DIR"

echo "[3.1] Adding .VolumeIcon.icns..."
cp tools/favicon.icns "$STAGING_DIR/.VolumeIcon.icns"
SetFile -c icnC "$STAGING_DIR/.VolumeIcon.icns"
SetFile -a C "$STAGING_DIR"

echo "[4] Copying app and Applications link..."
cp -R "$APP_DIR" "$STAGING_DIR/"
ln -s /Applications "$STAGING_DIR/Applications"

echo "[5] Creating DMG..."
hdiutil create -volname "$VOLUME_NAME" -srcfolder "$STAGING_DIR" -ov -format UDZO "$DMG_NAME"

echo "[6] Done: $DMG_NAME"
