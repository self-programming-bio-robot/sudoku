# Sudoku Ink

Game is for onyx book series. 
Support pen.

## Build for BOOX

Use JDK 11 for Gradle, Android SDK Platform 28, and Build Tools 30.0.2.
Install the SDK packages with Android Studio's SDK Manager or run
`sdkmanager "platforms;android-28" "build-tools;30.0.2"` with the JDK
required by your version of the Android command-line tools.

Set `JAVA_HOME` to JDK 11 and `ANDROID_HOME` to the Android SDK directory,
then run the project's Gradle wrapper.

```sh
./gradlew testDebugUnitTest assembleDebug
```

On Windows, run `.\gradlew.bat testDebugUnitTest assembleDebug` in PowerShell.
The APK is written to `app/build/outputs/apk/debug/app-debug.apk`.

The app uses Onyx Device SDK 1.1.11, Pen SDK 1.2.1, Android Support 28, and
the `armeabi-v7a` ABI. The build fetches the Onyx SDK and its legacy
commonsIO, EasyPermissions, and MMKV dependencies from BOOX's HTTPS Maven
repositories. Use a physical BOOX device with stylus support to test raw pen
input and e-ink refresh.

To Do:
1. Refactoring logs
2. Limit drawable field by game field
3. Research algorithm of generation sudoku(smarter)
4. Add learning to recognize digit in process game
