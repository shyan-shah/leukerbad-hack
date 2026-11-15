# Vita iPhone app

The patient app from the Vita design, as a native SwiftUI app (iOS 17+).

Tabs: Home, Exercises, **Scan** (the raised button in the middle), Progress, Me.
Scan reads the QR code on the rehab arm and unlocks that arm for a session.

## Run it on your iPhone

1. Open `Vita.xcodeproj` in Xcode.
2. Select the **Vita** target › **Signing & Capabilities** › pick your Team (a free Apple ID works).
   If Xcode says the bundle id is taken, change `app.vita.patient` to something unique, e.g. `app.vita.patient.<yourname>`.
3. Plug in the iPhone (or pick it over Wi-Fi), choose it as the run destination, press **Run** (⌘R).
4. First run on a device with a free account: on the iPhone open
   Settings › General › VPN & Device Management and trust your developer certificate.

The project is generated from `project.yml` with [XcodeGen](https://github.com/yonaskolb/XcodeGen).
After adding or removing files, run `xcodegen generate` in this folder (the `.xcodeproj` is committed, so you only need XcodeGen when the file list changes).

Tests: ⌘U in Xcode, or
`xcodebuild test -project Vita.xcodeproj -scheme Vita -destination 'platform=iOS Simulator,name=iPhone 17' CODE_SIGNING_ALLOWED=NO`

## Connecting a server and API key

Me › **Connection**: enter the server address and paste the API key, then **Save and test connection**.

- The API key is stored in the iOS Keychain on the phone (this device only); the server address in app settings.
- The address must be `https://…`. Plain `http://` is accepted only for a host on the local network
  (`*.local`, `192.168.x.x`, `10.x.x.x`, `172.16–31.x.x`, `localhost`), e.g. the robot on the home Wi-Fi,
  so the key never crosses the internet unencrypted.
- Without a server the app runs in **demo mode**: any valid Vita code unlocks a pretend arm.

The app expects this API (every request carries `Authorization: Bearer <API key>`):

| Request | Meaning |
|---|---|
| `GET  {server}/v1/health` | 2xx: the key is accepted (used by "test connection") |
| `POST {server}/v1/robots/{robot}/activate` with JSON `{"code": "8F3K2Q"}` | 2xx: the arm is unlocked for this patient. 401/403: key refused. 404: unknown arm. |

## QR code on the arm

The sticker can carry any of these (robot: letters, digits and `-`; code: 4–64 letters or digits):

```
vita://activate?robot=R-01&code=8F3K2Q
https://<your host>/activate?robot=R-01&code=8F3K2Q
VITA:R-01:8F3K2Q
```

Print the robot number and code under the QR too: the app has "Type the code instead" for when the camera is not available.
`test-codes/R-01.png` is a test sticker (`vita://activate?robot=R-01&code=8F3K2Q`): show it on your laptop screen and scan it with the phone.

## What is still pretend

- Patient data (Anna, her numbers, exercises, Lukas, Lea) is sample data from the design, adapted to an arm programme.
- In a session the lift count goes up on a timer (one lift every 2.2 s); it is not read from the robot yet.
- Fonts: the design's Bricolage Grotesque is replaced by SF Rounded.
