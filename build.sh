#!/bin/bash
set -euo pipefail

PKG="openmower-cli"
VERSION="${1:-0.0.1}"
BUILD_DIR="build/${PKG}_${VERSION}"

echo "Building ${PKG} ${VERSION}..."

# Clean previous build
rm -rf "$BUILD_DIR"

# Create directory tree matching the target filesystem
mkdir -p "$BUILD_DIR"/{DEBIAN,opt/openmower-cli/openmower_cli,usr/local/bin,lib/systemd/system}

# Copy application source
cp src/openmower_cli/*.py "$BUILD_DIR/opt/openmower-cli/openmower_cli/"
cp requirements.txt "$BUILD_DIR/opt/openmower-cli/"

# Copy deb files
cp -p deb/openmower.wrapper "$BUILD_DIR/usr/local/bin/openmower"
cp deb/openmower.service "$BUILD_DIR/lib/systemd/system/"

# Copy and prepare DEBIAN control files
sed "s/__VERSION__/${VERSION}/" deb/control > "$BUILD_DIR/DEBIAN/control"
cp -p deb/postinst "$BUILD_DIR/DEBIAN/"
cp -p deb/prerm "$BUILD_DIR/DEBIAN/"
cp -p deb/postrm "$BUILD_DIR/DEBIAN/"

# Build the .deb
dpkg-deb --build "$BUILD_DIR"

echo ""
echo "Built: ${BUILD_DIR}.deb"
echo "Install with: sudo dpkg -i ${BUILD_DIR}.deb"
