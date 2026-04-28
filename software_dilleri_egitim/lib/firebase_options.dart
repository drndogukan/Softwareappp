import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart' show defaultTargetPlatform, kIsWeb, TargetPlatform;

/// Firebase options sourced from compile-time defines.
///
/// Recommended: generate this file via `flutterfire configure`.
/// This fallback expects values via `--dart-define` so secrets aren't committed.
class DefaultFirebaseOptions {
  static FirebaseOptions get currentPlatform {
    if (kIsWeb) return web;

    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return android;
      case TargetPlatform.iOS:
        return ios;
      case TargetPlatform.macOS:
        return macos;
      case TargetPlatform.windows:
        return windows;
      case TargetPlatform.linux:
        return linux;
      default:
        throw UnsupportedError(
          'DefaultFirebaseOptions are not supported for this platform.',
        );
    }
  }

  static void _requireNotEmpty(String keyName, String value) {
    if (value.isNotEmpty) return;
    throw StateError(
      'Missing Firebase config: $keyName. '
      'Run `flutterfire configure` or pass --dart-define=$keyName=... to flutter run/build.',
    );
  }

  // Web requires explicit options. Values can be provided with:
  // flutter run -d chrome --dart-define=FIREBASE_API_KEY=... etc.
  static FirebaseOptions get web {
    const apiKey = String.fromEnvironment('FIREBASE_API_KEY');
    const appId = String.fromEnvironment('FIREBASE_APP_ID');
    const messagingSenderId = String.fromEnvironment('FIREBASE_MESSAGING_SENDER_ID');
    const projectId = String.fromEnvironment('FIREBASE_PROJECT_ID');
    const authDomain = String.fromEnvironment('FIREBASE_AUTH_DOMAIN');
    const storageBucket = String.fromEnvironment('FIREBASE_STORAGE_BUCKET');
    const measurementId = String.fromEnvironment('FIREBASE_MEASUREMENT_ID');

    _requireNotEmpty('FIREBASE_API_KEY', apiKey);
    _requireNotEmpty('FIREBASE_APP_ID', appId);
    _requireNotEmpty('FIREBASE_MESSAGING_SENDER_ID', messagingSenderId);
    _requireNotEmpty('FIREBASE_PROJECT_ID', projectId);

    return FirebaseOptions(
      apiKey: apiKey,
      appId: appId,
      messagingSenderId: messagingSenderId,
      projectId: projectId,
      authDomain: authDomain,
      storageBucket: storageBucket,
      measurementId: measurementId,
    );
  }

  // If you target these platforms, prefer `flutterfire configure` to generate
  // the correct per-platform options. This fallback uses dart-defines too.
  static FirebaseOptions get android {
    const apiKey = String.fromEnvironment('FIREBASE_ANDROID_API_KEY');
    const appId = String.fromEnvironment('FIREBASE_ANDROID_APP_ID');
    const messagingSenderId = String.fromEnvironment('FIREBASE_MESSAGING_SENDER_ID');
    const projectId = String.fromEnvironment('FIREBASE_PROJECT_ID');
    const storageBucket = String.fromEnvironment('FIREBASE_STORAGE_BUCKET');

    _requireNotEmpty('FIREBASE_ANDROID_API_KEY', apiKey);
    _requireNotEmpty('FIREBASE_ANDROID_APP_ID', appId);
    _requireNotEmpty('FIREBASE_MESSAGING_SENDER_ID', messagingSenderId);
    _requireNotEmpty('FIREBASE_PROJECT_ID', projectId);

    return FirebaseOptions(
      apiKey: apiKey,
      appId: appId,
      messagingSenderId: messagingSenderId,
      projectId: projectId,
      storageBucket: storageBucket,
    );
  }

  static FirebaseOptions get ios {
    const apiKey = String.fromEnvironment('FIREBASE_IOS_API_KEY');
    const appId = String.fromEnvironment('FIREBASE_IOS_APP_ID');
    const messagingSenderId = String.fromEnvironment('FIREBASE_MESSAGING_SENDER_ID');
    const projectId = String.fromEnvironment('FIREBASE_PROJECT_ID');
    const iosBundleId = String.fromEnvironment('FIREBASE_IOS_BUNDLE_ID');
    const storageBucket = String.fromEnvironment('FIREBASE_STORAGE_BUCKET');

    _requireNotEmpty('FIREBASE_IOS_API_KEY', apiKey);
    _requireNotEmpty('FIREBASE_IOS_APP_ID', appId);
    _requireNotEmpty('FIREBASE_MESSAGING_SENDER_ID', messagingSenderId);
    _requireNotEmpty('FIREBASE_PROJECT_ID', projectId);

    return FirebaseOptions(
      apiKey: apiKey,
      appId: appId,
      messagingSenderId: messagingSenderId,
      projectId: projectId,
      iosBundleId: iosBundleId,
      storageBucket: storageBucket,
    );
  }

  static FirebaseOptions get macos {
    const apiKey = String.fromEnvironment('FIREBASE_MACOS_API_KEY');
    const appId = String.fromEnvironment('FIREBASE_MACOS_APP_ID');
    const messagingSenderId = String.fromEnvironment('FIREBASE_MESSAGING_SENDER_ID');
    const projectId = String.fromEnvironment('FIREBASE_PROJECT_ID');
    const iosBundleId = String.fromEnvironment('FIREBASE_MACOS_BUNDLE_ID');
    const storageBucket = String.fromEnvironment('FIREBASE_STORAGE_BUCKET');

    _requireNotEmpty('FIREBASE_MACOS_API_KEY', apiKey);
    _requireNotEmpty('FIREBASE_MACOS_APP_ID', appId);
    _requireNotEmpty('FIREBASE_MESSAGING_SENDER_ID', messagingSenderId);
    _requireNotEmpty('FIREBASE_PROJECT_ID', projectId);

    return FirebaseOptions(
      apiKey: apiKey,
      appId: appId,
      messagingSenderId: messagingSenderId,
      projectId: projectId,
      iosBundleId: iosBundleId,
      storageBucket: storageBucket,
    );
  }

  static FirebaseOptions get windows {
    const apiKey = String.fromEnvironment('FIREBASE_WINDOWS_API_KEY');
    const appId = String.fromEnvironment('FIREBASE_WINDOWS_APP_ID');
    const messagingSenderId = String.fromEnvironment('FIREBASE_MESSAGING_SENDER_ID');
    const projectId = String.fromEnvironment('FIREBASE_PROJECT_ID');
    const storageBucket = String.fromEnvironment('FIREBASE_STORAGE_BUCKET');

    _requireNotEmpty('FIREBASE_WINDOWS_API_KEY', apiKey);
    _requireNotEmpty('FIREBASE_WINDOWS_APP_ID', appId);
    _requireNotEmpty('FIREBASE_MESSAGING_SENDER_ID', messagingSenderId);
    _requireNotEmpty('FIREBASE_PROJECT_ID', projectId);

    return FirebaseOptions(
      apiKey: apiKey,
      appId: appId,
      messagingSenderId: messagingSenderId,
      projectId: projectId,
      storageBucket: storageBucket,
    );
  }

  static FirebaseOptions get linux {
    const apiKey = String.fromEnvironment('FIREBASE_LINUX_API_KEY');
    const appId = String.fromEnvironment('FIREBASE_LINUX_APP_ID');
    const messagingSenderId = String.fromEnvironment('FIREBASE_MESSAGING_SENDER_ID');
    const projectId = String.fromEnvironment('FIREBASE_PROJECT_ID');
    const storageBucket = String.fromEnvironment('FIREBASE_STORAGE_BUCKET');

    _requireNotEmpty('FIREBASE_LINUX_API_KEY', apiKey);
    _requireNotEmpty('FIREBASE_LINUX_APP_ID', appId);
    _requireNotEmpty('FIREBASE_MESSAGING_SENDER_ID', messagingSenderId);
    _requireNotEmpty('FIREBASE_PROJECT_ID', projectId);

    return FirebaseOptions(
      apiKey: apiKey,
      appId: appId,
      messagingSenderId: messagingSenderId,
      projectId: projectId,
      storageBucket: storageBucket,
    );
  }
}

