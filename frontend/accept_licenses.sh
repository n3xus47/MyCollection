#!/bin/bash
# Skrypt do akceptacji licencji Android SDK

echo "Tworzenie katalogu licenses..."
sudo mkdir -p /usr/lib/android-sdk/licenses

echo "Akceptowanie licencji Android SDK..."
# Licencje dla różnych komponentów Android SDK
echo "24333f8a63b6825ea9c5514f83c2829b004d1fee" | sudo tee /usr/lib/android-sdk/licenses/android-sdk-license > /dev/null
echo "84831b9409646a918e30573bab4c9c91346d8abd" | sudo tee /usr/lib/android-sdk/licenses/android-sdk-preview-license > /dev/null
echo "8403addf88ab4874007e1c1e80a0025de956b170" | sudo tee /usr/lib/android-sdk/licenses/android-sdk-arm-dbt-license > /dev/null
echo "d975f751698a77b662f1254ddbeed3901e976f5a" | sudo tee /usr/lib/android-sdk/licenses/android-googletv-license > /dev/null
echo "33b6a2b64607f4b5e52bffd2416c8d3b9f92e313" | sudo tee /usr/lib/android-sdk/licenses/android-sdk-license > /dev/null
echo "601085b94cd77f0b54ff86406957099ebe79c4d6" | sudo tee /usr/lib/android-sdk/licenses/intel-android-extra-license > /dev/null
echo "e9acab5b5fbb56a1d83613d9518d884aa66df958" | sudo tee /usr/lib/android-sdk/licenses/google-gdk-license > /dev/null

# Licencje dla NDK (wszystkie możliwe wersje)
NDK_LICENSE="e9acab5b5fbb56a1d83613d9518d884aa66df958"
for version in "" r23c r24 r25 r26 r27 r28; do
    if [ -z "$version" ]; then
        echo "$NDK_LICENSE" | sudo tee /usr/lib/android-sdk/licenses/android-ndk-license > /dev/null
    else
        echo "$NDK_LICENSE" | sudo tee /usr/lib/android-sdk/licenses/android-ndk-${version}-license > /dev/null
    fi
done

echo "Sprawdzanie utworzonych licencji..."
sudo ls -la /usr/lib/android-sdk/licenses/

echo ""
echo "Licencje zostały zaakceptowane!"
echo "Teraz możesz uruchomić: flutter run"
