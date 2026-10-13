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

`EXPO_PUBLIC_*` values are compiled into the app, so never put secrets in them. Restart
`npm start` after changing `.env`. The backend's `CORS_ORIGINS` must include the web
origin (e.g. `http://localhost:8081`) for the web build.

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
│   ├── index.tsx     # Welcome
│   ├── (auth)/       # Login, Registration
│   ├── (tabs)/       # Home (vehicle list), Profile
│   └── vehicles/[id].tsx
├── components/       # Reusable UI (ui/) and domain components
├── constants/        # Branding placeholders and colour constants
├── data/             # PROTOTYPE profile placeholder only (until Stage 14)
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
