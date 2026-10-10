#!/bin/sh
# Setu Keygen phone app (vendor ka activation key tool) — bina Android Studio ke.
# Chahiye: Java 17+, python3 + cryptography, aapt2, dalvik-dx.jar, android-all (Robolectric) jar.
#   AAPT2=... DX=... ANDROID_JAR=... KEYSTORE=setu-library-release.p12 KSPASS=... sh build-apk.sh
set -e
cd "$(dirname "$0")"
B=build; rm -rf "$B"; mkdir -p "$B/classes" "$B/assets"
cp keygen.html "$B/assets/"
cp AndroidManifest.xml "$B/AndroidManifest.xml"
"$AAPT2" compile --dir res -o "$B/res.zip"
"$AAPT2" link -o "$B/base.apk" -I "$ANDROID_JAR" --manifest "$B/AndroidManifest.xml" -A "$B/assets" "$B/res.zip" --java "$B/gen"
javac --release 8 -nowarn -cp "$ANDROID_JAR" -d "$B/classes" $(find src "$B/gen" -name '*.java')
java -cp "$DX" com.android.dx.command.Main --dex --min-sdk-version=24 --output="$B/classes.dex" "$B/classes"
cp "$B/base.apk" "$B/unsigned.apk"; (cd "$B" && zip -q -9 unsigned.apk classes.dex)
jarsigner -keystore "$KEYSTORE" -storepass "$KSPASS" -sigalg SHA256withRSA -digestalg SHA-256 -signedjar "$B/v1.apk" "$B/unsigned.apk" setu >/dev/null
python3 ../android/apksign.py "$B/v1.apk" SetuKeygen.apk "$KEYSTORE" "$KSPASS"
echo "Ready: $(pwd)/SetuKeygen.apk"
