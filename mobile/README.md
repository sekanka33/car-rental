# Mobile app (Expo)

Renter and owner app for the car rental platform. See the root
[README.md](../README.md) for the project overview and stage tracker.

## Configuration

Copy `.env.example` to `.env` (git-ignored) and set `EXPO_PUBLIC_API_URL` to the backend:

| Where the app runs | `EXPO_PUBLIC_API_URL` |
|--------------------|-----------------------|
| Web / iOS simulator on this computer | `http://localhost:8000` (default) |
| Android emulator | `http://10.0.2.2:8000` |
| Physical phone (Expo Go) | `http://<computer LAN IP>:8000`; start the backend with `--host 0.0.0.0` |

`EXPO_PUBLIC_*` values are compiled into the app, so never put secrets in them.

Maps: Expo Go and iOS need no key (Expo Go ships its own; iOS uses Apple Maps). For a
development or store build on Android, set `GOOGLE_MAPS_ANDROID_API_KEY` (and
`GOOGLE_MAPS_IOS_API_KEY` only if switching iOS to Google Maps); `app.config.js` passes them to
the `react-native-maps` plugin at build time. Restrict each key to the app (package name and
SHA-1 / bundle ID). On web the map is replaced by a link to Google Maps.

## Sign-in and sessions

Login and registration call the backend (`src/services/auth.ts`, `src/context/auth.tsx`).
Tokens are stored with **expo-secure-store** (iOS Keychain / Android Keystore). On the
**web** build, SecureStore is unavailable, so tokens fall back to `localStorage`, which is
acceptable for the development web preview only. The API client refreshes an expired
access token once (concurrent requests share one refresh) and signs the user out if the
session cannot be renewed. Logging out revokes the session on the server. Restart
`npm start` after changing `.env`. The backend's `CORS_ORIGINS` must include the web
origin (e.g. `http://localhost:8081`) for the web build.

## Payments

Booking detail shows **Pay** while the hold is live. The app asks the backend to start
checkout, opens the returned Paystack page with **expo-web-browser**, and afterwards asks
the backend to verify (`POST /payments/{id}/refresh`). It never decides that a payment
succeeded by itself. `src/app/payments/return.tsx` is the page checkout returns to
(`?payment_id=`). On the web it completes the popup; opened directly, it shows the
verified result. Set the backend's `PAYMENT_CALLBACK_URL` to
`http://localhost:8081/payments/return` for the web preview. On a phone the in-app
browser is closed by the renter, and the app verifies the payment then.

## Delivery

Once a booking is paid, booking detail shows its delivery (`src/components/delivery-section.tsx`):
who delivers and when, updates from the owner, and the handover and return records. The
renter confirms receipt with **"I have the car"** (optionally noting anything that does
not match the handover record), then taps **"I'm ready to return the car"** when done.

**Live tracking** (`src/components/live-tracking.tsx`, `src/hooks/use-delivery-tracking.ts`):
while the delivery is scheduled or on its way, the renter's booking screen keeps a WebSocket
open. It shows the car on a map with the ETA and "Updated … ago", warns when no position has
arrived for a minute, reconnects with backoff (up to 30 s) after a network drop, refreshes the
session once if the server closes with 4401, and stops when tracking ends.

**Owners** open **Profile → My deliveries** (`src/app/deliveries/`). On a scheduled delivery
they tap **Set off now**, then **Share my location** (`src/hooks/use-location-sharing.ts`):
the app asks for foreground location permission and sends a position at most every 10 s while
the screen is open, and stops by itself when the server says the delivery is no longer on its
way. Background sharing needs a development build and is not enabled. The other owner screens
(scheduling, handover, return) arrive in Stage 14; until then owners use the API for those.

## Commands

```bash
npm install              # install dependencies
npm start                # Expo dev server (scan QR with Expo Go, or press a / i / w)
npm run web              # run in the browser
npm run typecheck        # tsc --noEmit
npm run lint             # expo lint (ESLint)
npm test                 # Jest (jest-expo) + React Native Testing Library
npx expo-doctor          # check SDK/dependency compatibility
```

Always add packages with `npx expo install <package>` so versions match the Expo SDK.

## Structure

```
src/
├── app/              # Expo Router routes (every file is a screen)
│   ├── index.tsx     # Welcome (redirects signed-in users)
│   ├── (auth)/       # Login, Registration (real backend accounts)
│   ├── (tabs)/       # Home (marketplace), Bookings, Profile
│   ├── vehicles/[id]/  # index (details), book (dates, quote, reserve)
│   ├── bookings/[id].tsx  # Booking detail, hold countdown, cancel, live tracking
│   └── deliveries/   # Owner: my deliveries, set off, share location
├── context/          # AuthProvider / useAuth
├── components/       # Reusable UI (ui/) and domain components
├── constants/        # Branding placeholders and colour constants
├── hooks/            # Shared hooks
├── lib/              # Formatting and client-side validation helpers
├── services/         # Backend API calls (marketplace: /api/v1/vehicles)
├── lib/api.ts        # HTTP client: base URL, timeouts, error envelope → ApiError
└── types/            # Shared TypeScript types
```

Styling uses NativeWind 4 (Tailwind CSS 3). Theme tokens are in `tailwind.config.js`.

Tests live in `__tests__/` (outside `src/app`, because every file there is a route).
Testing Library v14 renders asynchronously: always `await render(...)` and
`await fireEvent...`. `jest.setup.ts` replaces icon fonts with plain elements.
