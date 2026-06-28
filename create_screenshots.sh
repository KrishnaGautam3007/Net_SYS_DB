#!/bin/bash
# Create placeholder screenshot PNGs for the README

mkdir -p screenshots

# Minimal valid PNG files (1x1 white pixel)
PNG_HEADER="\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x19-\xbf\x00\x00\x00\x00IEND\xaeB\x60\x82"

# Create each screenshot file
for file in overview.png machine_detail.png query_console.png alerts.png; do
  echo -ne "$PNG_HEADER" > "screenshots/$file"
  echo "Created: screenshots/$file"
done

echo ""
echo "Placeholder screenshots created."
echo "You can now replace them with actual screenshots by running:"
echo "  python screenshot_capture.py"
