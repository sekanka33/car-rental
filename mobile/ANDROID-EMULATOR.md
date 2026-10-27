# Run the mobile app on an Android emulator

Run these commands from the `mobile` directory. The command is `expo`, not `expose`.

## Start with Expo Go

Start the backend separately on port `8000` (see [backend setup](../backend/README.md#run)),
then start Expo with a clean Metro cache:

```bash
cd mobile
npx expo start --clear
```

When the Expo menu appears, press `a` to open the app in the running Android emulator.
You can also start it directly with:

```bash
npx expo start --android --clear
```

The app automatically uses `http://10.0.2.2:8000` for Android, which routes to your
computer from the emulator. No API URL setting is needed unless you want to override it.
If you do, set this in `mobile/.env`:

```dotenv
EXPO_PUBLIC_API_URL=http://10.0.2.2:8000
```

Restart Expo after changing `.env`. Expo Go can run the app, but push notifications
are unavailable there; the app skips native push setup in Expo Go so the rest of the
app can still be used.

## Use a development build

Push notifications and other native functionality that Expo Go does not include
require an Android development build. Build and install it on the running emulator:

```bash
cd mobile
npx expo run:android
```

Then start Metro in development-client mode:

```bash
npx expo start --dev-client --clear
```

If needed, press `a` to open the installed development build. After changing native
dependencies or Expo config plugins, run `npx expo run:android` again to rebuild it.
