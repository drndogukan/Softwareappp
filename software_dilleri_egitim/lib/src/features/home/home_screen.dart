import 'package:flutter/material.dart';

import '../../data/content_repository.dart';
import '../../data/progress_store.dart';
import '../../models/content_models.dart';
import '../language/language_screen.dart';
import '../../widgets/language_logo.dart';
import 'dart:math' as math;

class HomeScreen extends StatefulWidget {
  final VoidCallback? onGoQuiz;

  const HomeScreen({super.key, this.onGoQuiz});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _repo = ContentRepository();
  final _store = ProgressStore();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: FutureBuilder<ContentCatalog>(
          future: _repo.loadCatalog(),
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snapshot.hasError) {
              return Center(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text('Icerik yuklenemedi: ${snapshot.error}'),
                ),
              );
            }

            final catalog = snapshot.data!;
            final items = catalog.languages;

            return ValueListenableBuilder<int>(
              valueListenable: ProgressStore.revision,
              builder: (context, _, __) {
                return FutureBuilder<Map<String, TopicProgress>>(
                  future: _store.loadAll(),
                  builder: (context, snapProgress) {
                    if (snapProgress.connectionState != ConnectionState.done) {
                      return const Center(child: CircularProgressIndicator());
                    }
                    final progress = snapProgress.data ?? {};

                    int totalTests(LanguageContent lang) =>
                        lang.topics.where((t) => t.questions.isNotEmpty).length;

                    int completedTests(LanguageContent lang) {
                      int completed = 0;
                      for (final t in lang.topics) {
                        if (t.questions.isEmpty) continue;
                        final key =
                            _store.topicKey(languageId: lang.id, topicId: t.id);
                        final p = progress[key];
                        // "Çözüldü" = hedefi geçti (yarım kalan denemeler %100 sayılmasın).
                        if (p != null && p.bestScore >= 60) completed += 1;
                      }
                      return completed;
                    }

                    int attemptedTests(LanguageContent lang) {
                      int attempted = 0;
                      for (final t in lang.topics) {
                        if (t.questions.isEmpty) continue;
                        final key =
                            _store.topicKey(languageId: lang.id, topicId: t.id);
                        final p = progress[key];
                        if (p != null && p.attempts > 0) attempted += 1;
                      }
                      return attempted;
                    }

                    bool hasInProgress(LanguageContent lang) {
                      for (final t in lang.topics) {
                        if (t.questions.isEmpty) continue;
                        final key =
                            _store.topicKey(languageId: lang.id, topicId: t.id);
                        final p = progress[key];
                        if (p != null && p.inProgress) return true;
                      }
                      return false;
                    }

                    return CustomScrollView(
                      physics: const BouncingScrollPhysics(),
                      slivers: [
                        const SliverAppBar(
                          pinned: true,
                          title: Text('Yazilim Dilleri'),
                        ),
                        SliverPadding(
                          padding: const EdgeInsets.fromLTRB(12, 0, 12, 24),
                          sliver: SliverList.separated(
                            itemCount: items.length,
                            separatorBuilder: (_, __) =>
                                const SizedBox(height: 10),
                            itemBuilder: (context, index) {
                              final lang = items[index];
                              final total = totalTests(lang);
                              final completed = completedTests(lang);
                              final attempted = attemptedTests(lang);
                              final inProg = hasInProgress(lang);
                              return _LanguageCard(
                                language: lang,
                                totalTests: total,
                                solvedTests: completed,
                                attemptedTests: attempted,
                                hasInProgress: inProg,
                                forceGreenRing: index == 0,
                                onTap: () async {
                                  await Navigator.of(context).push(
                                    MaterialPageRoute(
                                      builder: (_) =>
                                          LanguageScreen(language: lang),
                                    ),
                                  );
                                  if (!mounted) return;
                                  setState(() {});
                                },
                              );
                            },
                          ),
                        ),
                      ],
                    );
                  },
                );
              },
            );
          },
        ),
      ),
    );
  }
}

class _LanguageCard extends StatelessWidget {
  final LanguageContent language;
  final int totalTests;
  final int solvedTests;
  final int attemptedTests;
  final bool forceGreenRing;
  final VoidCallback onTap;
  final bool hasInProgress;

  const _LanguageCard({
    required this.language,
    required this.totalTests,
    required this.solvedTests,
    required this.attemptedTests,
    required this.forceGreenRing,
    required this.onTap,
    required this.hasInProgress,
  });

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final computedPct =
        totalTests == 0 ? 0 : ((solvedTests / totalTests) * 100).round();
    final needsContinue = hasInProgress ||
        (attemptedTests > solvedTests && solvedTests < totalTests);
    // Yarım kalan iş varken %100 göstermeyelim.
    final pct = (needsContinue && computedPct >= 100) ? 99 : computedPct;
    const brandGreen = Color(0xFF0FD108);
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Container(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                scheme.surface,
                scheme.surfaceContainerHighest.withValues(alpha: 0.55),
              ],
            ),
          ),
          child: ListTile(
            leading: LanguageLogo(languageName: language.name, size: 44),
            title: Text(language.name),
            subtitle: needsContinue
                ? Text(
                    'Devam et',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          fontWeight: FontWeight.w800,
                          color: scheme.primary.withValues(alpha: 0.95),
                        ),
                  )
                : null,
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                _MiniStatRing(
                  percent: pct,
                  value: totalTests == 0 ? 0 : solvedTests / totalTests,
                  size: 38,
                  forceGreen: forceGreenRing,
                  activeColor: language.id == 'matlab' ? brandGreen : null,
                ),
                const SizedBox(width: 8),
                Icon(
                  Icons.chevron_right_rounded,
                  color: scheme.onSurface.withValues(alpha: 0.85),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _MiniStatRing extends StatelessWidget {
  final int percent;
  final double value; // 0..1
  final double size;
  final bool forceGreen;
  final Color? activeColor;

  const _MiniStatRing({
    required this.percent,
    required this.value,
    required this.size,
    required this.forceGreen,
    required this.activeColor,
  });

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    const brandGreen = Color(0xFF0FD108);
    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          SizedBox(
            width: size,
            height: size,
            child: CircularProgressIndicator(
              value: value.clamp(0, 1),
              strokeWidth: math.max(4.0, size * 0.12),
              backgroundColor: scheme.outline.withValues(alpha: 0.22),
              valueColor: AlwaysStoppedAnimation<Color>(
                activeColor ??
                    ((forceGreen || percent >= 100)
                        ? brandGreen
                        : scheme.primary),
              ),
            ),
          ),
          Text(
            '%$percent',
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  fontWeight: FontWeight.w900,
                  color: scheme.onSurface.withValues(alpha: 0.90),
                ),
          ),
        ],
      ),
    );
  }
}
