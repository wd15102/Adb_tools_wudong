#!/bin/bash

ICO_FILE="favicon.ico"
ICON_NAME="favicon"

if ! command -v magick &> /dev/null; then
    echo "[ERROR] ImageMagick not found, please install."
    exit 1
fi

rm -rf "$ICON_NAME.iconset"
mkdir "$ICON_NAME.iconset"

# 只取第0层图像，转成单张png
magick "$ICO_FILE"[-1] "$ICON_NAME.png"

magick "$ICON_NAME.png" -resize 16x16     "$ICON_NAME.iconset/icon_16x16.png"
magick "$ICON_NAME.png" -resize 32x32     "$ICON_NAME.iconset/icon_16x16@2x.png"
magick "$ICON_NAME.png" -resize 32x32     "$ICON_NAME.iconset/icon_32x32.png"
magick "$ICON_NAME.png" -resize 64x64     "$ICON_NAME.iconset/icon_32x32@2x.png"
magick "$ICON_NAME.png" -resize 128x128   "$ICON_NAME.iconset/icon_128x128.png"
magick "$ICON_NAME.png" -resize 256x256   "$ICON_NAME.iconset/icon_128x128@2x.png"
magick "$ICON_NAME.png" -resize 256x256   "$ICON_NAME.iconset/icon_256x256.png"
magick "$ICON_NAME.png" -resize 512x512   "$ICON_NAME.iconset/icon_256x256@2x.png"
magick "$ICON_NAME.png" -resize 512x512   "$ICON_NAME.iconset/icon_512x512.png"
magick "$ICON_NAME.png" -resize 1024x1024 "$ICON_NAME.iconset/icon_512x512@2x.png"

iconutil -c icns "$ICON_NAME.iconset"

if [ $? -eq 0 ]; then
    echo "[SUCCESS] Generated $ICON_NAME.icns successfully."
else
    echo "[FAIL] Failed to generate .icns file."
fi

# 可选：删除临时png
rm "$ICON_NAME.png"
