# NFC tag: tap the station to open the patient app

The tag replaces the QR scan in the pitch film. Tapping a phone on the tag opens the Vita app,
already connected to the station, with the arm's plan loaded and a single **Start** button.
Opening the link never starts the arm by itself: the patient presses Start.

## The URL on the tag

```
http://192.168.137.1:8000/app/?station=1&op=<operator token>
```

- `192.168.137.1`: the laptop's own address on its Windows mobile hotspot (check it, see below).
- `8000`: the server port (`python -m server.run ... --port 8000`, the default).
- `station=1`: the station number shown in the app ("Connected to Vita station 1").
- `op=<token>`: the operator token the server prints with `--lan`. Without it, starting a session is
  refused (403). The app stores it on the phone and removes it from the address bar.

## Setup on the station laptop

1. **Hotspot on:** Settings → Network & internet → Mobile hotspot → On. Connect the filming phone to it.
2. **Find the address:** run `ipconfig` and look under **"Wireless LAN adapter Local Area Connection\* …"**
   for the IPv4 address. It is normally `192.168.137.1` and stays the same between restarts.
3. **Start the server with a fixed token** so the tag stays valid after a restart:
   `python -m server.run --robot --lan --token <choose-one> --port 8000` (plus the usual robot flags).
   Without `--token`, a new random token is made at every start and the tag stops working.
   Note: the server banner prints the address of the laptop's main network (e.g. the venue Wi-Fi),
   not the hotspot address. Use the hotspot address from `ipconfig` on the tag.
4. **Firewall:** the first time the phone connects, Windows may ask whether Python may use the
   network. Allow it on both Private and Public networks (the hotspot can count as either).

## Writing the tag (NFC Tools, free on iPhone and Android)

1. Write → Add a record → **URL / URI**.
2. Enter the full URL above, starting with `http://`.
3. Write, then hold the phone on the tag until it confirms.

## Testing

1. Close the app and every browser tab on the phone.
2. Tap the phone on the tag. iPhone: a banner appears at the top; tap it.
3. Expected: the Vita app opens on **Today**, "Arm recovery (robot)", four exercises marked
   "on the arm", the button **Start forward reach** and "Connected to Vita station 1."
4. Tap Start: the arm session starts (the operator console shows it).

Checked in headless Chrome at phone size against `--mock --lan --token TESTTOKEN` (15 Nov): the screen
above appears straight after opening; the token is stored and sent; one tap on Start begins the
session (200); without the token the server answers 403; the address bar shows only `/app/`.

## When the tag must be rewritten

- The **token** changes (a server start without the same `--token`).
- The **address** changes (the server runs on another network, or `ipconfig` shows a different
  hotspot address).
- The **port** or **station number** changes.

## iPhone note

iPhone XS and later read tags with the screen on (unlocked) and show a banner to open the link.
Test on the exact phone used for filming. If it refuses a plain `http://` address, use an Android
phone or the QR code on the station instead.

## Keep the tag with the team

The tag carries the operator token, which lets any phone on the hotspot start the robot. Keep it
with the team, do not post photos where the URL can be read, and choose a new token after the event.
