import 'package:flutter/material.dart';

class LanguageLogo extends StatelessWidget {
  final String languageName;
  final double size;

  const LanguageLogo({
    super.key,
    required this.languageName,
    this.size = 44,
  });

  Color _brandColorFor(String name) {
    final n = name.toLowerCase().trim();
    if (n == 'c') return const Color(0xFF5C6BC0);
    if (n.contains('c++') || n.contains('cpp')) return const Color(0xFF00599C);
    if (n.contains('c#') || n.contains('csharp')) return const Color(0xFF7B1FA2);
    if (n.contains('python')) return const Color(0xFF3776AB);
    if (n.contains('javascript') || n == 'js') return const Color(0xFFF7DF1E);
    if (n.contains('typescript') || n == 'ts') return const Color(0xFF3178C6);
    if (n.contains('java')) return const Color(0xFFE76F00);
    if (n.contains('kotlin')) return const Color(0xFF7F52FF);
    if (n.contains('swift')) return const Color(0xFFF05138);
    if (n.contains('dart')) return const Color(0xFF0175C2);
    if (n.contains('go') || n == 'golang') return const Color(0xFF00ADD8);
    if (n.contains('rust')) return const Color(0xFFB7410E);
    if (n.contains('php')) return const Color(0xFF777BB4);
    if (n.contains('ruby')) return const Color(0xFFCC342D);
    if (n == 'r' || n.contains(' r ')) return const Color(0xFF276DC3);
    if (n.contains('matlab')) return const Color(0xFFFF7A00);
    if (n.contains('sql')) return const Color(0xFF2E7D32);
    if (n.contains('html')) return const Color(0xFFE34F26);
    if (n.contains('css')) return const Color(0xFF1572B6);
    return const Color(0xFF90A4AE);
  }

  String _assetFor(String name) {
    final n = name.toLowerCase().trim();
    if (n == 'c') return 'assets/logos/c.png';
    if (n.contains('c++') || n.contains('cpp')) return 'assets/logos/cpp.png';
    if (n.contains('c#') || n.contains('csharp')) return 'assets/logos/csharp.png';
    if (n.contains('python')) return 'assets/logos/python.png';
    if (n.contains('javascript') || n == 'js') return 'assets/logos/javascript.png';
    if (n.contains('typescript') || n == 'ts') return 'assets/logos/typescript.png';
    if (n.contains('java')) return 'assets/logos/java.png';
    if (n.contains('kotlin')) return 'assets/logos/kotlin.png';
    if (n.contains('swift')) return 'assets/logos/swift.png';
    if (n.contains('dart')) return 'assets/logos/dart.png';
    if (n.contains('go') || n == 'golang') return 'assets/logos/go.png';
    if (n.contains('rust')) return 'assets/logos/rust.png';
    if (n.contains('php')) return 'assets/logos/php.png';
    if (n.contains('ruby')) return 'assets/logos/ruby.png';
    if (n == 'r') return 'assets/logos/r.png';
    if (n.contains('matlab')) return 'assets/logos/matlab.png';
    if (n.contains('sql')) return 'assets/logos/sql.png';
    if (n.contains('html')) return 'assets/logos/html.png';
    if (n.contains('css')) return 'assets/logos/css.png';
    return 'assets/logos/${n.replaceAll(' ', '_')}.png';
  }

  String _monogram(String name) {
    final trimmed = name.trim();
    if (trimmed.isEmpty) return '?';
    final lower = trimmed.toLowerCase();
    if (lower.contains('c++')) return 'C++';
    if (lower.contains('c#')) return 'C#';
    if (lower == 'matlab') return 'M';
    if (lower == 'sql') return 'SQL';
    if (lower == 'r') return 'R';
    if (trimmed.length <= 3) return trimmed.toUpperCase();
    return trimmed.characters.first.toUpperCase();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final asset = _assetFor(languageName);
    final brand = _brandColorFor(languageName);
    final onBrand = ThemeData.estimateBrightnessForColor(brand) == Brightness.dark
        ? Colors.white
        : Colors.black;

    return ClipRRect(
      borderRadius: BorderRadius.circular(size * 0.32),
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              brand.withValues(alpha: 0.55),
              scheme.surfaceContainerHighest.withValues(alpha: 0.22),
              scheme.surface.withValues(alpha: 0.70),
            ],
          ),
          border: Border.all(color: scheme.outline.withValues(alpha: 0.45)),
        ),
        child: Image.asset(
          asset,
          fit: BoxFit.contain,
          errorBuilder: (context, _, __) {
            return Center(
              child: Text(
                _monogram(languageName),
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w900,
                      letterSpacing: -0.2,
                      color: onBrand.withValues(alpha: 0.95),
                    ),
              ),
            );
          },
        ),
      ),
    );
  }
}

