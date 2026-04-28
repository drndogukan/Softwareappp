import 'package:flutter/material.dart';

import '../../data/progress_store.dart';
import '../../models/content_models.dart';
import '../../theme/app_theme.dart';
import '../../widgets/language_logo.dart';
import '../quiz/quiz_screen.dart';
import '../topic/topic_lesson_screen.dart';
import 'dart:math' as math;

class LanguageScreen extends StatefulWidget {
  final LanguageContent language;

  const LanguageScreen({super.key, required this.language});

  @override
  State<LanguageScreen> createState() => _LanguageScreenState();
}

class _LanguageScreenState extends State<LanguageScreen> {
  final _store = ProgressStore();
  Map<String, TopicProgress> _progress = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final all = await _store.loadAll();
    if (!mounted) return;
    setState(() => _progress = all);
  }

  int _topicBestScore(TopicContent t) {
    final key = _store.topicKey(languageId: widget.language.id, topicId: t.id);
    return _progress[key]?.bestScore ?? 0;
  }

  TopicProgress? _topicProgress(TopicContent t) {
    final key = _store.topicKey(languageId: widget.language.id, topicId: t.id);
    return _progress[key];
  }

  int _completedTopics(LanguageContent lang) {
    int completed = 0;
    for (final t in lang.topics) {
      if (_topicBestScore(t) >= 60) completed += 1;
    }
    return completed;
  }

  int _avgBest(LanguageContent lang) {
    if (lang.topics.isEmpty) return 0;
    int sum = 0;
    for (final t in lang.topics) {
      sum += _topicBestScore(t);
    }
    return (sum / lang.topics.length).round();
  }

  Future<void> _openLesson(LanguageContent lang, TopicContent t) async {
    await Navigator.of(context).push(
      MaterialPageRoute(
          builder: (_) => TopicLessonScreen(language: lang, topic: t)),
    );
  }

  Future<void> _openTest(LanguageContent lang, TopicContent t) async {
    final selected = await _pickDifficulty(
      title: '${t.title} • Test',
      easyCount:
          t.questions.where((q) => q.difficulty == Difficulty.easy).length,
      mediumCount:
          t.questions.where((q) => q.difficulty == Difficulty.medium).length,
      hardCount:
          t.questions.where((q) => q.difficulty == Difficulty.hard).length,
    );
    if (!mounted) return;
    if (selected == null) return;

    final pool = t.questions.where((q) => q.difficulty == selected).toList();
    if (pool.isEmpty) return;

    // Exclude already completed questions for this topic.
    final key = _store.topicKey(languageId: lang.id, topicId: t.id);
    final all = await _store.loadAll();
    if (!mounted) return;
    final prev = all[key];
    final solved = (prev?.quizSolvedIds ?? const <String>[]).toSet();
    final remaining = pool.where((q) => !solved.contains(q.id)).toList();

    if (remaining.isEmpty) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Bu konuda yeni soru kalmadı.')),
      );
      return;
    }

    // Random 20 questions (or fewer if not enough left).
    remaining.shuffle(math.Random());
    final qs = remaining.take(20).toList();

    final subtopics = _extractSubtopics(t.contentMarkdown);

    if (!mounted) return;
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => QuizScreen(
          language: lang,
          topic: t,
          questions: qs,
          subtopics: subtopics,
        ),
      ),
    );
    await _load();
  }

  List<String> _extractSubtopics(String md) {
    // Roadmap markdown uses "#### <id>. <title>" lines.
    final lines = md.split('\n');
    final out = <String>[];
    final seen = <String>{};
    for (final line in lines) {
      final trimmed = line.trimLeft();
      if (!trimmed.startsWith('#### ')) continue;
      var t = trimmed.substring(5).trim();
      // Drop leading "1.1." etc.
      t = t.replaceFirst(RegExp(r'^\d+(\.\d+)*\.\s*'), '');
      if (t.isEmpty) continue;
      if (seen.add(t)) out.add(t);
    }
    return out;
  }

  Future<Difficulty?> _pickDifficulty({
    required String title,
    required int easyCount,
    required int mediumCount,
    required int hardCount,
  }) async {
    return showModalBottomSheet<Difficulty>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (context) {
        final scheme = Theme.of(context).colorScheme;
        final bottom = MediaQuery.of(context).padding.bottom;

        Widget pane({
          required Difficulty d,
          required String label,
          required int count,
          required IconData icon,
        }) {
          final enabled = count > 0;
          return Padding(
            padding: EdgeInsets.fromLTRB(16, 12, 16, 16 + bottom),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  title,
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w900,
                      ),
                ),
                const SizedBox(height: 10),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(18),
                    color:
                        scheme.surfaceContainerHighest.withValues(alpha: 0.45),
                    border: Border.all(
                        color: scheme.outline.withValues(alpha: 0.25)),
                  ),
                  child: Row(
                    children: [
                      Icon(icon, color: scheme.primary),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          '$label • $count soru',
                          style:
                              Theme.of(context).textTheme.bodyMedium?.copyWith(
                                    fontWeight: FontWeight.w800,
                                  ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 12),
                FilledButton.icon(
                  onPressed:
                      enabled ? () => Navigator.of(context).pop(d) : null,
                  icon: const Icon(Icons.play_arrow_rounded),
                  label: Text(enabled ? 'Başla' : 'Soru yok'),
                ),
              ],
            ),
          );
        }

        return DefaultTabController(
          length: 3,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Material(
                color: scheme.surface,
                child: TabBar(
                  tabs: [
                    Tab(text: 'Kolay ($easyCount)'),
                    Tab(text: 'Orta ($mediumCount)'),
                    Tab(text: 'Zor ($hardCount)'),
                  ],
                ),
              ),
              Flexible(
                child: TabBarView(
                  children: [
                    pane(
                      d: Difficulty.easy,
                      label: 'Kolay',
                      count: easyCount,
                      icon: Icons.sentiment_satisfied_rounded,
                    ),
                    pane(
                      d: Difficulty.medium,
                      label: 'Orta',
                      count: mediumCount,
                      icon: Icons.sentiment_neutral_rounded,
                    ),
                    pane(
                      d: Difficulty.hard,
                      label: 'Zor',
                      count: hardCount,
                      icon: Icons.sentiment_very_dissatisfied_rounded,
                    ),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final lang = widget.language;
    final scheme = Theme.of(context).colorScheme;
    final completed = _completedTopics(lang);
    final avg = _avgBest(lang);

    return Scaffold(
      body: DefaultTabController(
        length: 2,
        child: NestedScrollView(
          headerSliverBuilder: (context, inner) {
            return [
              SliverAppBar(
                pinned: true,
                expandedHeight: 240,
                title: Text(lang.name),
                bottom: const TabBar(
                  tabs: [
                    Tab(
                        icon: Icon(Icons.menu_book_rounded),
                        text: 'Konu Anlatım'),
                    Tab(icon: Icon(Icons.quiz_rounded), text: 'Test'),
                  ],
                ),
                flexibleSpace: FlexibleSpaceBar(
                  background: Container(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                        colors: [
                          AppColors.deep.withValues(alpha: 0.70),
                          AppColors.bg,
                          scheme.primary.withValues(alpha: 0.16),
                        ],
                        stops: const [0.0, 0.58, 1.0],
                      ),
                    ),
                    child: SafeArea(
                      bottom: false,
                      child: Padding(
                        padding: const EdgeInsets.fromLTRB(16, 72, 16, 16),
                        child: LayoutBuilder(
                          builder: (context, c) {
                            return FittedBox(
                              fit: BoxFit.scaleDown,
                              alignment: Alignment.topLeft,
                              child: SizedBox(
                                width: c.maxWidth,
                                child: Column(
                                  mainAxisSize: MainAxisSize.min,
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Row(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        const SizedBox(width: 2),
                                        LanguageLogo(
                                            languageName: lang.name, size: 64),
                                        const SizedBox(width: 14),
                                        Expanded(
                                          child: Text(
                                            lang.description,
                                            maxLines: 4,
                                            overflow: TextOverflow.ellipsis,
                                            style: Theme.of(context)
                                                .textTheme
                                                .bodyMedium
                                                ?.copyWith(
                                                  color: scheme.onSurface
                                                      .withValues(alpha: 0.86),
                                                  height: 1.15,
                                                ),
                                          ),
                                        ),
                                      ],
                                    ),
                                    const SizedBox(height: 12),
                                    Wrap(
                                      spacing: 10,
                                      runSpacing: 10,
                                      children: [
                                        _StatChip(
                                          icon: Icons.topic_rounded,
                                          label: '${lang.topics.length} konu',
                                        ),
                                        _StatChip(
                                          icon: Icons.verified_rounded,
                                          label: '$completed tamam',
                                          tone: scheme.tertiary,
                                        ),
                                        _StatChip(
                                          icon: Icons.stars_rounded,
                                          label: 'Ort. %$avg',
                                          tone: scheme.primary,
                                        ),
                                      ],
                                    ),
                                  ],
                                ),
                              ),
                            );
                          },
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ];
          },
          body: TabBarView(
            children: [
              // Konu Anlatım: her konu ayrı ayrı
              GridView.builder(
                padding: const EdgeInsets.fromLTRB(12, 12, 12, 24),
                physics: const BouncingScrollPhysics(),
                gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                  maxCrossAxisExtent: 420,
                  mainAxisSpacing: 10,
                  crossAxisSpacing: 10,
                  childAspectRatio: 2.35,
                ),
                itemCount: lang.topics.length,
                itemBuilder: (context, index) {
                  final t = lang.topics[index];
                  return _SimpleTopicCard(
                    title: t.title,
                    subtitle: 'Konu anlatım + öğrenme sonuçları',
                    badgeIcon: Icons.menu_book_rounded,
                    onTap: () => _openLesson(lang, t),
                  );
                },
              ),

              // Test: her konu ayrı ayrı (sorusu olanlar aktif)
              GridView.builder(
                padding: const EdgeInsets.fromLTRB(12, 12, 12, 24),
                physics: const BouncingScrollPhysics(),
                gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                  maxCrossAxisExtent: 420,
                  mainAxisSpacing: 10,
                  crossAxisSpacing: 10,
                  childAspectRatio: 2.25,
                ),
                itemCount: lang.topics.length,
                itemBuilder: (context, index) {
                  final t = lang.topics[index];
                  final best = _topicBestScore(t);
                  final p = _topicProgress(t);
                  final hasQuestions = t.questions.isNotEmpty;
                  return _TopicCard(
                    title: t.title,
                    best: best,
                    questionCount: t.questions.length,
                    lastCorrect: p?.lastCorrect,
                    lastTotal: p?.lastTotal,
                    lastScore: p?.lastScore,
                    attempts: p?.attempts,
                    inProgress: p?.inProgress ?? false,
                    enabled: hasQuestions,
                    onTap: () => _openTest(lang, t),
                    badgeIcon: Icons.quiz_rounded,
                  );
                },
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _StatChip extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color? tone;

  const _StatChip({required this.icon, required this.label, this.tone});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final c = tone ?? scheme.onSurface;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(999),
        color: scheme.surface.withValues(alpha: 0.65),
        border: Border.all(color: scheme.outline.withValues(alpha: 0.35)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 18, color: c.withValues(alpha: 0.90)),
          const SizedBox(width: 8),
          Text(
            label,
            style: Theme.of(context).textTheme.labelLarge?.copyWith(
                  fontWeight: FontWeight.w900,
                  color: scheme.onSurface.withValues(alpha: 0.90),
                ),
          ),
        ],
      ),
    );
  }
}

class _SimpleTopicCard extends StatelessWidget {
  final String title;
  final String subtitle;
  final IconData badgeIcon;
  final VoidCallback onTap;

  const _SimpleTopicCard({
    required this.title,
    required this.subtitle,
    required this.badgeIcon,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.all(14),
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
          child: Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(14),
                  color: scheme.primary.withValues(alpha: 0.12),
                  border:
                      Border.all(color: scheme.outline.withValues(alpha: 0.45)),
                ),
                child: Icon(badgeIcon,
                    color: scheme.onSurface.withValues(alpha: 0.92)),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(
                            fontWeight: FontWeight.w900,
                            height: 1.1,
                          ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      subtitle,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: scheme.onSurface.withValues(alpha: 0.70),
                            fontWeight: FontWeight.w700,
                          ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 10),
              Icon(
                Icons.chevron_right_rounded,
                color: scheme.onSurface.withValues(alpha: 0.78),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _TopicCard extends StatelessWidget {
  final String title;
  final int best;
  final int questionCount;
  final int? lastCorrect;
  final int? lastTotal;
  final int? lastScore;
  final int? attempts;
  final bool inProgress;
  final bool enabled;
  final VoidCallback onTap;
  final IconData badgeIcon;

  const _TopicCard({
    required this.title,
    required this.best,
    required this.questionCount,
    required this.lastCorrect,
    required this.lastTotal,
    required this.lastScore,
    required this.attempts,
    required this.inProgress,
    required this.enabled,
    required this.onTap,
    required this.badgeIcon,
  });

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: enabled ? onTap : null,
        child: Container(
          padding: const EdgeInsets.all(14),
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
          child: Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(14),
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [
                      scheme.primary.withValues(alpha: 0.18),
                      scheme.secondary.withValues(alpha: 0.12),
                      scheme.surfaceContainerHighest.withValues(alpha: 0.30),
                    ],
                  ),
                  border:
                      Border.all(color: scheme.outline.withValues(alpha: 0.45)),
                ),
                child: Icon(badgeIcon,
                    color: scheme.onSurface.withValues(alpha: 0.92)),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(
                            fontWeight: FontWeight.w900,
                            height: 1.1,
                          ),
                    ),
                    const SizedBox(height: 6),
                    SingleChildScrollView(
                      scrollDirection: Axis.horizontal,
                      physics: const BouncingScrollPhysics(),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          _Pill(
                            text: '$questionCount soru',
                            tone: scheme.primary,
                          ),
                          if (inProgress) ...[
                            const SizedBox(width: 8),
                            _Pill(
                              text: 'Devam et',
                              tone: scheme.tertiary,
                            ),
                          ],
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 10),
              Icon(
                Icons.chevron_right_rounded,
                color: scheme.onSurface.withValues(alpha: 0.78),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Pill extends StatelessWidget {
  final String text;
  final Color tone;

  const _Pill({required this.text, required this.tone});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(999),
        color: tone.withValues(alpha: 0.14),
        border: Border.all(color: scheme.outline.withValues(alpha: 0.30)),
      ),
      child: Text(
        text,
        style: Theme.of(context).textTheme.labelLarge?.copyWith(
              fontWeight: FontWeight.w900,
              color: scheme.onSurface.withValues(alpha: 0.88),
            ),
      ),
    );
  }
}
