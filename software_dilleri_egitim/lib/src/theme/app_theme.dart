import 'package:flutter/material.dart';

class AppColors {
  // Palette: https://coolors.co/palette/bee9e8-62b6cb-1b4965-cae9ff-5fa8d3
  static const mint = Color(0xFFBEE9E8);
  static const sky = Color(0xFF62B6CB);
  static const deep = Color(0xFF1B4965);
  static const ice = Color(0xFFCAE9FF);
  static const blue = Color(0xFF5FA8D3);

  // Dark surfaces (black-first UI)
  static const bg = Color(0xFF07090D);
  static const surface = Color(0xFF0B0F14);
  static const surface2 = Color(0xFF0F1620);
}

class AppTheme {
  static ThemeData dark() {
    final scheme = const ColorScheme.dark().copyWith(
      primary: AppColors.sky,
      onPrimary: Colors.black,
      secondary: AppColors.blue,
      onSecondary: Colors.black,
      tertiary: AppColors.mint,
      onTertiary: Colors.black,
      surface: AppColors.surface,
      onSurface: AppColors.ice,
      surfaceContainerHighest: AppColors.surface2,
      onSurfaceVariant: AppColors.ice,
      outline: AppColors.deep,
      outlineVariant: AppColors.deep,
      error: const Color(0xFFFF5C7A),
      onError: Colors.black,
    );

    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: scheme,
      scaffoldBackgroundColor: AppColors.bg,
      splashFactory: InkSparkle.splashFactory,
      appBarTheme: AppBarTheme(
        backgroundColor: Colors.transparent,
        foregroundColor: scheme.onSurface,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: false,
        surfaceTintColor: Colors.transparent,
        titleTextStyle: const TextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w700,
          letterSpacing: -0.2,
        ).copyWith(color: scheme.onSurface),
      ),
      textTheme: Typography.material2021(platform: TargetPlatform.android)
          .white
          .apply(
            bodyColor: scheme.onSurface,
            displayColor: scheme.onSurface,
          ),
      cardTheme: CardThemeData(
        color: scheme.surface,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(18),
          side: BorderSide(color: scheme.outline.withValues(alpha: 0.55)),
        ),
      ),
      listTileTheme: ListTileThemeData(
        iconColor: scheme.onSurface.withValues(alpha: 0.9),
        textColor: scheme.onSurface,
        titleTextStyle: const TextStyle(
          fontWeight: FontWeight.w700,
          letterSpacing: -0.1,
        ),
        subtitleTextStyle: TextStyle(
          color: scheme.onSurface.withValues(alpha: 0.72),
          height: 1.15,
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      ),
      dividerTheme: DividerThemeData(
        color: scheme.outline.withValues(alpha: 0.35),
        space: 1,
        thickness: 1,
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: scheme.primary,
          foregroundColor: scheme.onPrimary,
          disabledBackgroundColor: scheme.surfaceContainerHighest,
          disabledForegroundColor: scheme.onSurfaceVariant.withValues(alpha: 0.6),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          textStyle: const TextStyle(fontWeight: FontWeight.w800, letterSpacing: -0.1),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: scheme.onSurface,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          textStyle: const TextStyle(fontWeight: FontWeight.w800, letterSpacing: -0.1),
          side: BorderSide(color: scheme.outline.withValues(alpha: 0.7)),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: scheme.surface,
        hintStyle: TextStyle(color: scheme.onSurface.withValues(alpha: 0.55)),
        labelStyle: TextStyle(color: scheme.onSurface.withValues(alpha: 0.75)),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide(color: scheme.outline.withValues(alpha: 0.55)),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide(color: scheme.outline.withValues(alpha: 0.55)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide(color: scheme.primary.withValues(alpha: 0.95), width: 1.4),
        ),
      ),
    );
  }
}

