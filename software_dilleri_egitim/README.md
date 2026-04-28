## Yazilim Dilleri Egitim (Flutter)

Bu proje: **offline icerik (JSON) + konu anlatimi + test + sonuc + ilerleme takibi** iceren bir Flutter uygulamasidir.

### Premium notlar (projede var)
- **Videolar sekmesi**: Dil → Konu bazli video linki ekleme / duzenleme / kopyalama (cihazda kayitli).
- **Logo sistemi**: `assets/logos/` altindan logo gosterir, yoksa fallback monogram kullanir.

### 1) Gereksinimler (Windows)
- Flutter SDK (stable)
- Android Studio (Android SDK icin) veya sadece Android SDK
- Bir emulator ya da USB ile Android cihaz

### 2) Flutter kurulumu (kisa)
1. Flutter SDK indir (stable zip) ve bir klasore cikart. Ornek: `C:\src\flutter`
2. `C:\src\flutter\bin` yolunu **PATH** ortam degiskenine ekle
3. Yeni bir PowerShell acip kontrol et:

```bash
flutter --version
flutter doctor
```

> `flutter doctor` ciktisinda Android toolchain eksikse Android Studio kurup SDK'yi tamamlayin.

### 3) Projeyi calistirma
Bu klasorun icinde:

```bash
flutter pub get
flutter run
```

### 4) Icerik ekleme / dilleri cogaltma
`assets/content/catalog.json` dosyasina yeni dil ve konu ekleyebilirsiniz.
Her topic icin `questions` listesi uygulamada otomatik test ekranina yansir.

### 5) Ikon & splash uretimi
Projede otomatik ikon/splash ayarlari vardir.

```bash
flutter pub get
python tools\gen_branding_assets.py
dart run flutter_launcher_icons
dart run flutter_native_splash:create
```

### 6) Play Store / App Store hazirlik checklist (ozet)
- **Paket adi / Bundle ID**: su anda `com.example...` (magaza icin degistirilmeli)
  - Android: `android/app/build.gradle.kts` -> `applicationId`
  - iOS: `ios/Runner.xcodeproj/project.pbxproj` -> `PRODUCT_BUNDLE_IDENTIFIER`
- **Android signing (release)**:
  - `android/app/build.gradle.kts` icindeki release signing debug. Play Store icin keystore ile degistirin.
- **Surumleme**:
  - `pubspec.yaml` -> `version: x.y.z+build`
- **Magaza metinleri**:
  - Kisa aciklama, uzun aciklama, ekran goruntuleri, gizlilik politikasi (uygulama video linklerini cihazda saklar).

### 7) Gizlilik politikasi (taslak)
Uygulama icinde video linkleri ve ilerleme bilgisi **yalnizca cihazda** saklanir (SharedPreferences).
Sunucuya gonderim yoktur (varsayilan).

> Magazaya cikmadan once, gizlilik metnini kendi durumunuza gore guncelleyin.
