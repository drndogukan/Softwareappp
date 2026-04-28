import 'package:flutter/material.dart';

import '../../data/content_repository.dart';
import '../../models/content_models.dart';
import '../../theme/app_theme.dart';
import '../../widgets/language_logo.dart';
import '../compiler/compiler_screen.dart';
import '../compiler/coding_challenges.dart';

class QuizHubScreen extends StatefulWidget {
  const QuizHubScreen({super.key});

  @override
  State<QuizHubScreen> createState() => _QuizHubScreenState();
}

class _QuizHubScreenState extends State<QuizHubScreen> {
  final _repo = ContentRepository();

  String? _languageId;
  String? _lastTopicId;

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

  Future<void> _startCompiler({
    required LanguageContent lang,
    required TopicContent topic,
  }) async {
    final all = challengesFor(language: lang, topic: topic);
    final selected = await _pickDifficulty(
      title: '${topic.title} • Compiler',
      easyCount: all.where((c) => c.difficulty == Difficulty.easy).length,
      mediumCount: all.where((c) => c.difficulty == Difficulty.medium).length,
      hardCount: all.where((c) => c.difficulty == Difficulty.hard).length,
    );
    if (!mounted) return;
    if (selected == null) return;
    final filtered = all.where((c) => c.difficulty == selected).toList();
    if (filtered.isEmpty) return;

    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => CompilerScreen(
          language: lang,
          topic: topic,
          challenges: filtered,
        ),
      ),
    );
  }

  Future<void> _pickTopicAndStart(LanguageContent lang) async {
    setState(() => _languageId = lang.id);
    final topic = await showModalBottomSheet<TopicContent>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (context) {
        final scheme = Theme.of(context).colorScheme;
        final initial = _lastTopicId;
        return SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  children: [
                    LanguageLogo(languageName: lang.name, size: 44),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(lang.name,
                              style: Theme.of(context).textTheme.titleMedium),
                          Text(
                            'Konu seç',
                            style: Theme.of(context)
                                .textTheme
                                .bodySmall
                                ?.copyWith(
                                  color:
                                      scheme.onSurface.withValues(alpha: 0.72),
                                ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Flexible(
                  child: ListView.separated(
                    shrinkWrap: true,
                    itemCount: lang.topics.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 8),
                    itemBuilder: (context, i) {
                      final t = lang.topics[i];
                      final cCount =
                          challengesFor(language: lang, topic: t).length;
                      final enabled = cCount > 0;
                      final isLast = initial != null && t.id == initial;
                      return ListTile(
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(16)),
                        tileColor: scheme.surfaceContainerHighest
                            .withValues(alpha: 0.55),
                        leading: Icon(
                          enabled
                              ? Icons.play_circle_rounded
                              : Icons.lock_rounded,
                          color: enabled
                              ? scheme.primary.withValues(alpha: 0.95)
                              : scheme.onSurface.withValues(alpha: 0.50),
                        ),
                        title: Text(t.title),
                        subtitle: Text(isLast
                            ? '$cCount soru • Son seçilen'
                            : '$cCount soru'),
                        onTap:
                            enabled ? () => Navigator.of(context).pop(t) : null,
                      );
                    },
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );

    if (!mounted) return;
    if (topic == null) return;
    setState(() => _lastTopicId = topic.id);
    await _startCompiler(lang: lang, topic: topic);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: FutureBuilder<ContentCatalog>(
          future: _repo.loadCatalog(),
          builder: (context, snap) {
            if (snap.connectionState != ConnectionState.done) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snap.hasError) {
              return Center(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text('İçerik yüklenemedi: ${snap.error}'),
                ),
              );
            }

            final catalog = snap.data!;
            final languages = catalog.languages;

            return CustomScrollView(
              physics: const BouncingScrollPhysics(),
              slivers: [
                const SliverAppBar(
                  pinned: true,
                  title: Text('Compiler'),
                ),
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(12, 10, 12, 24),
                  sliver: SliverList.separated(
                    itemCount: 1,
                    separatorBuilder: (_, __) => const SizedBox(height: 12),
                    itemBuilder: (context, index) {
                      return _SectionCard(
                        child: _LanguageGrid(
                          languages: languages,
                          selectedId: _languageId,
                          onSelect: (id) {
                            final lang =
                                languages.firstWhere((l) => l.id == id);
                            _pickTopicAndStart(lang);
                          },
                        ),
                      );
                    },
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _SectionCard extends StatelessWidget {
  final Widget child;

  const _SectionCard({required this.child});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(18),
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              scheme.surface,
              scheme.surfaceContainerHighest.withValues(alpha: 0.55),
            ],
          ),
        ),
        child: child,
      ),
    );
  }
}

class _LanguageGrid extends StatelessWidget {
  final List<LanguageContent> languages;
  final String? selectedId;
  final ValueChanged<String> onSelect;

  const _LanguageGrid({
    required this.languages,
    required this.selectedId,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final groups = <List<LanguageContent>>[];
    for (var i = 0; i < languages.length; i += 3) {
      groups.add(languages.sublist(i, (i + 3).clamp(0, languages.length)));
    }

    Widget tile(LanguageContent l, {required double width}) {
      final selected = l.id == selectedId;
      return SizedBox(
        width: width,
        child: Tooltip(
          message: l.name,
          child: Semantics(
            label: l.name,
            button: true,
            selected: selected,
            child: InkWell(
              borderRadius: BorderRadius.circular(18),
              onTap: () => onSelect(l.id),
              child: Ink(
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(
                    color: selected
                        ? scheme.primary.withValues(alpha: 0.95)
                        : scheme.outline.withValues(alpha: 0.45),
                    width: selected ? 1.6 : 1,
                  ),
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: selected
                        ? [
                            AppColors.sky.withValues(alpha: 0.22),
                            AppColors.blue.withValues(alpha: 0.14),
                            scheme.surface,
                          ]
                        : [
                            scheme.surface,
                            scheme.surfaceContainerHighest
                                .withValues(alpha: 0.45),
                          ],
                  ),
                ),
                child: Padding(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      LanguageLogo(languageName: l.name, size: 46),
                      const SizedBox(height: 8),
                      Text(
                        l.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.labelLarge?.copyWith(
                              fontWeight: FontWeight.w900,
                              color: scheme.onSurface.withValues(alpha: 0.90),
                            ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      );
    }

    return LayoutBuilder(
      builder: (context, c) {
        const gap = 10.0;
        const minTileWidth = 110.0;
        final maxW = c.maxWidth;

        // 3 tile + 2 gap
        final idealWidth = (maxW - (gap * 2)) / 3;
        final shouldScroll = idealWidth < minTileWidth;
        final tileWidth = shouldScroll ? minTileWidth : idealWidth;

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final group in groups) ...[
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: shouldScroll
                    ? SingleChildScrollView(
                        scrollDirection: Axis.horizontal,
                        child: Row(
                          children: [
                            for (var i = 0; i < group.length; i++) ...[
                              if (i != 0) const SizedBox(width: gap),
                              tile(group[i], width: tileWidth),
                            ],
                          ],
                        ),
                      )
                    : Row(
                        children: [
                          for (var i = 0; i < group.length; i++) ...[
                            if (i != 0) const SizedBox(width: gap),
                            Expanded(
                              child: tile(group[i], width: double.infinity),
                            ),
                          ],
                          // son grupta 1-2 eleman varsa 3'lü görünüm bozulmasın
                          for (var i = group.length; i < 3; i++) ...[
                            const SizedBox(width: gap),
                            const Expanded(child: SizedBox.shrink()),
                          ],
                        ],
                      ),
              ),
            ],
          ],
        );
      },
    );
  }
}
