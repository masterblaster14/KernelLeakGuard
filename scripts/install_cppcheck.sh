#!/usr/bin/env bash
# Install cppcheck (baseline static analyser) into ~/klg-build/tools without
# root: download the Ubuntu packages and unpack them locally.
set -euo pipefail
DEST="${KLG_WORK:-$HOME/klg-build}/tools"
mkdir -p "$DEST/debs"
cd "$DEST/debs"
apt-get download cppcheck >/dev/null
# Shared libraries cppcheck links against that may not be installed system-wide.
for lib in $(apt-cache depends cppcheck | awk '/Depends: lib/ {print $2}'); do
    dpkg -s "$lib" >/dev/null 2>&1 || apt-get download "$lib" >/dev/null || true
done
for d in *.deb; do dpkg -x "$d" "$DEST/root"; done
# The binary looks for std.cfg in its compiled-in FILESDIR or in ./cfg next to
# itself; the latter works for an unpacked (non-root) installation.
CFG="$(dirname "$(find "$DEST/root" -name std.cfg | head -1)")"
mkdir -p "$DEST/root/usr/bin/cfg"
cp "$CFG"/*.cfg "$DEST/root/usr/bin/cfg/"
PLAT="$(dirname "$CFG")/platforms"
[[ -d "$PLAT" ]] && cp -r "$PLAT" "$DEST/root/usr/bin/" || true
cat > "$DEST/cppcheck" <<EOF
#!/usr/bin/env bash
export LD_LIBRARY_PATH="$DEST/root/usr/lib/x86_64-linux-gnu:\${LD_LIBRARY_PATH:-}"
exec "$DEST/root/usr/bin/cppcheck" "\$@"
EOF
chmod +x "$DEST/cppcheck"
"$DEST/cppcheck" --version
