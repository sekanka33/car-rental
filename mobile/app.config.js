/**
 * Adds settings that must not be committed to app.json. Google Maps keys are only needed for
 * development or store builds: Expo Go already includes its own keys, iOS uses Apple Maps by
 * default, and the web build shows a link instead of a map. Restrict each key to its app
 * (Android package + SHA-1, iOS bundle id) in the Google Cloud console.
 */
module.exports = ({ config }) => ({
  ...config,
  plugins: [
    ...config.plugins,
    [
      'react-native-maps',
      {
        androidGoogleMapsApiKey: process.env.GOOGLE_MAPS_ANDROID_API_KEY,
        iosGoogleMapsApiKey: process.env.GOOGLE_MAPS_IOS_API_KEY,
      },
    ],
  ],
});
