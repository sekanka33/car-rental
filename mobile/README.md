# Mobile app (Expo)

Renter and owner app for the car rental platform. See the root
[README.md](../README.md) for the project overview and stage tracker.

## Commands

```bash
npm install              # install dependencies
npm start                # Expo dev server (scan QR with Expo Go, or press a / i / w)
npm run web              # run in the browser
npm run typecheck        # tsc --noEmit
npm run lint             # expo lint (ESLint)
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
├── data/             # PROTOTYPE sample data (removed in Stage 09)
├── hooks/            # Shared hooks
├── lib/              # Formatting and client-side validation helpers
├── services/         # Data access (sample data now, backend API from Stage 09)
└── types/            # Shared TypeScript types
```

Styling uses NativeWind 4 (Tailwind CSS 3). Theme tokens are in `tailwind.config.js`.
