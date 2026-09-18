# Tsushin Desktop

Electron shell around the Tsushin web app. It does **not** bundle the frontend or
backend — it points at a Tsushin server (production, the local compose stack, or
`next dev`) and renders it in a native window with persistent cookies, so you stay
signed in between launches.

## Why a shell instead of a bundled app

The Next.js frontend is designed to be same-origin with the backend: `/api/*` and
`/ws/*` are rewritten to the backend inside the Docker network, and auth is an
httpOnly `tsushin_session` cookie. Bundling the frontend into the app would break
that origin model and force a second auth scheme. The shell keeps one deployment
and one session model; the desktop app is packaging, not a fork.

## Run it

```bash
cd desktop
npm install
npm start
```

First launch shows a **Connect to Tsushin** screen. Enter a server address
(`tsushin.archsec.io`, `localhost`, `http://localhost:3099`…) — bare hostnames
default to `https://`. Change it later from **Tsushin → Server…** (`Cmd+,`).

Config lives in `~/Library/Application Support/Tsushin/config.json`
(`%APPDATA%\Tsushin` on Windows). `Tsushin → Clear Session Data…` signs you out
locally without touching the server.

## What the shell does beyond "load a URL"

- **Session persistence** — the app cookie survives quits, so no daily re-login.
- **OAuth stays inside the window.** `loginWithGoogle()` does a top-level
  `window.location.href` to `accounts.google.com`; if that were pushed to the
  system browser, the callback would set the session cookie in the wrong browser.
  A host allowlist (`AUTH_HOSTS` in `src/main.js`) keeps identity providers in the
  shell. The user agent is also normalized to plain Chrome, because Google rejects
  OAuth from user agents advertising Electron.
- **Everything else opens externally.** Any other host, from `will-navigate` or
  `window.open`, goes to the system browser.
- **Local TLS.** Self-signed certificates are accepted for loopback hostnames
  only; remote hosts keep full TLS enforcement.
- **Locked-down renderer.** `contextIsolation` on, `nodeIntegration` off, sandbox
  on, `<webview>` blocked, and camera/mic/notification permissions granted only to
  the configured origin.
- Window bounds and zoom persist; a connection failure shows a Retry / Change
  server page instead of Chromium's error page.

The preload exposes `window.tsushinDesktop = { isDesktop: true, … }`, which the
web app can use to hide browser-only affordances.

## Build installers

```bash
npm run dist:mac     # dmg + zip, arm64 and x64
npm run dist:win     # NSIS installer, x64 and arm64
npm run dist:linux   # AppImage + deb
```

Output lands in `desktop/dist/`. Cross-building macOS artifacts requires macOS;
Windows/Linux targets are best produced on their own runners (or in Docker).

## Code signing and notarization

Unsigned builds run fine on the machine that built them (ad-hoc signature), but a
**downloaded** unsigned app is blocked by Gatekeeper on macOS and flagged by
SmartScreen on Windows.

### macOS — requires the Apple Developer Program ($99/year)

You need a *Developer ID Application* certificate, which only Apple Developer
Program members can create. With the certificate in the login keychain and an
app-specific password for notarization:

```bash
export APPLE_ID="you@example.com"
export APPLE_APP_SPECIFIC_PASSWORD="xxxx-xxxx-xxxx-xxxx"
export APPLE_TEAM_ID="XXXXXXXXXX"
npm run dist:mac
```

electron-builder signs with the Developer ID identity it finds, then notarizes and
staples when those variables are present. `resources/entitlements.mac.plist` already
carries the hardened-runtime entitlements Electron needs.

Without a certificate, users can still run it: right-click → Open once, or
`xattr -dr com.apple.quarantine /Applications/Tsushin.app`.

### Windows

An OV code-signing certificate (~$100-200/yr) removes most SmartScreen warnings;
an EV certificate (~$300-500/yr) removes them immediately. Set `CSC_LINK` and
`CSC_KEY_PASSWORD` for electron-builder to sign.

### Linux

No signing required for AppImage/deb.

## Regenerating icons

`resources/icon.png` (1024×1024) is derived from
`brand/logo/tsushin_smalllogo.png` padded onto Ink `#0B0F14`:

```bash
sips -s format png ../brand/logo/tsushin_smalllogo.png --resampleHeightWidthMax 760 --out /tmp/logo760.png
sips -p 1024 1024 --padColor 0B0F14 /tmp/logo760.png --out resources/icon.png
```

electron-builder derives the macOS `.icns` and the Windows `.ico` from that single PNG, so no other icon files are checked in.
