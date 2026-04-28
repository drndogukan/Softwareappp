import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown/flutter_markdown.dart';

import '../../data/video_store.dart';
import '../../models/content_models.dart';
import '../../theme/app_theme.dart';
import '../../widgets/language_logo.dart';
import '../quiz/quiz_screen.dart';

class TopicLessonScreen extends StatefulWidget {
  final LanguageContent language;
  final TopicContent topic;

  const TopicLessonScreen(
      {super.key, required this.language, required this.topic});

  @override
  State<TopicLessonScreen> createState() => _TopicLessonScreenState();
}

class _TopicLessonScreenState extends State<TopicLessonScreen> {
  final _videoStore = VideoStore();

  Future<String?> _videoUrl() => _videoStore.getUrl(
      languageId: widget.language.id, topicId: widget.topic.id);

  List<String> _extractLearningOutcomes(String md,
      {required String topicTitle}) {
    final lines = md.split(RegExp(r'\r?\n')).map((e) => e.trim()).toList();
    bool inOutcomesSection = false;
    final outcomes = <String>[];

    bool isHeading(String s) => s.startsWith('#');
    bool isBullet(String s) =>
        s.startsWith('- ') || s.startsWith('* ') || s.startsWith('• ');

    for (final raw in lines) {
      final s = raw.trim();
      if (s.isEmpty) continue;

      if (isHeading(s)) {
        final h = s.replaceFirst(RegExp(r'^#+\s*'), '').toLowerCase();
        inOutcomesSection = h.contains('öğren') ||
            h.contains('ogren') ||
            h.contains('kazan') ||
            h.contains('hedef') ||
            h.contains('sonuc');
        continue;
      }

      if (inOutcomesSection && isBullet(s)) {
        final item = s.replaceFirst(RegExp(r'^(-|\*|•)\s+'), '').trim();
        if (item.isNotEmpty) outcomes.add(item);
        if (outcomes.length >= 6) break;
      }
    }

    if (outcomes.isEmpty) {
      for (final raw in lines) {
        final s = raw.trim();
        if (!isBullet(s)) continue;
        final item = s.replaceFirst(RegExp(r'^(-|\*|•)\s+'), '').trim();
        if (item.isNotEmpty) outcomes.add(item);
        if (outcomes.length >= 4) break;
      }
    }

    if (outcomes.isEmpty) {
      return [
        '$topicTitle kavramlarını açıklayabilme',
        '$topicTitle ile ilgili örnekleri yorumlayabilme',
        '$topicTitle bilgisini küçük alıştırmalarla pekiştirebilme',
      ];
    }

    return outcomes;
  }

  MarkdownStyleSheet _mdStyle(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final base = Theme.of(context).textTheme.bodyMedium ??
        const TextStyle(fontSize: 14, height: 1.25);
    return MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
      p: base.copyWith(
        height: 1.30,
        color: scheme.onSurface.withValues(alpha: 0.90),
      ),
      h3: Theme.of(context).textTheme.titleSmall?.copyWith(
            fontWeight: FontWeight.w900,
            color: scheme.onSurface.withValues(alpha: 0.94),
          ),
      h2: Theme.of(context).textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.w900,
            color: scheme.onSurface.withValues(alpha: 0.94),
          ),
      code: (Theme.of(context).textTheme.bodySmall ??
              const TextStyle(fontSize: 12))
          .copyWith(
        fontFamily: 'monospace',
        color: scheme.onSurface.withValues(alpha: 0.92),
      ),
      codeblockDecoration: BoxDecoration(
        color: scheme.surfaceContainerHighest.withValues(alpha: 0.45),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: scheme.outline.withValues(alpha: 0.22)),
      ),
    );
  }

  Future<void> _editVideoUrl(BuildContext context, String? currentUrl) async {
    final controller = TextEditingController(text: currentUrl ?? '');
    final messenger = ScaffoldMessenger.of(context);
    final saved = await showModalBottomSheet<String?>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      builder: (context) {
        final scheme = Theme.of(context).colorScheme;
        final bottom = MediaQuery.of(context).viewInsets.bottom;
        return Padding(
          padding: EdgeInsets.fromLTRB(16, 6, 16, 16 + bottom),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  LanguageLogo(languageName: widget.language.name, size: 40),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(widget.language.name,
                            style: Theme.of(context).textTheme.titleMedium),
                        Text(
                          widget.topic.title,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: Theme.of(context)
                              .textTheme
                              .bodySmall
                              ?.copyWith(
                                color: scheme.onSurface.withValues(alpha: 0.78),
                              ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              TextField(
                controller: controller,
                keyboardType: TextInputType.url,
                textInputAction: TextInputAction.done,
                decoration: const InputDecoration(
                  labelText: 'Konu anlatım videosu linki',
                  hintText: 'https://...',
                ),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  OutlinedButton.icon(
                    onPressed: () => Navigator.of(context).pop(null),
                    icon: const Icon(Icons.close_rounded),
                    label: const Text('İptal'),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: FilledButton.icon(
                      onPressed: () =>
                          Navigator.of(context).pop(controller.text),
                      icon: const Icon(Icons.save_rounded),
                      label: const Text('Kaydet'),
                    ),
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );

    if (!mounted) return;
    if (saved == null) return;
    final url = saved.trim().isEmpty ? null : saved.trim();
    await _videoStore.setUrl(
        languageId: widget.language.id, topicId: widget.topic.id, url: url);
    if (!mounted) return;
    setState(() {});
    messenger.showSnackBar(
      SnackBar(
        content: Text(
            url == null ? 'Video linki temizlendi' : 'Video linki kaydedildi'),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  Future<void> _copyUrl(BuildContext context, String url) async {
    await Clipboard.setData(ClipboardData(text: url));
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Link kopyalandı'),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final lang = widget.language;
    final topic = widget.topic;
    final outcomes = _extractLearningOutcomes(topic.contentMarkdown,
        topicTitle: topic.title);
    // Yazılı anlatım doğrudan contentMarkdown üzerinden gösterilir.
    final libQs = topic.libraryQuestions;

    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: CustomScrollView(
          physics: const BouncingScrollPhysics(),
          slivers: [
            SliverAppBar(
              pinned: true,
              expandedHeight: 190,
              title: Text(topic.title),
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
                      stops: const [0.0, 0.6, 1.0],
                    ),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 78, 16, 16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            LanguageLogo(languageName: lang.name, size: 54),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Text(
                                lang.name,
                                style: Theme.of(context)
                                    .textTheme
                                    .titleMedium
                                    ?.copyWith(
                                      fontWeight: FontWeight.w900,
                                    ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 10),
                        Text(
                          'Konu anlatımı • Özet + video + içerik',
                          style: Theme.of(context)
                              .textTheme
                              .bodySmall
                              ?.copyWith(
                                color: scheme.onSurface.withValues(alpha: 0.72),
                                fontWeight: FontWeight.w700,
                              ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(12, 12, 12, 24),
              sliver: SliverList(
                delegate: SliverChildListDelegate(
                  [
                    if (libQs.isNotEmpty) ...[
                      Card(
                        clipBehavior: Clip.antiAlias,
                        child: Padding(
                          padding: const EdgeInsets.all(14),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Container(
                                    width: 40,
                                    height: 40,
                                    decoration: BoxDecoration(
                                      borderRadius: BorderRadius.circular(14),
                                      color: scheme.secondary
                                          .withValues(alpha: 0.14),
                                      border: Border.all(
                                          color: scheme.outline
                                              .withValues(alpha: 0.30)),
                                    ),
                                    child: Icon(Icons.quiz_rounded,
                                        color: scheme.secondary),
                                  ),
                                  const SizedBox(width: 12),
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          'Kütüphane soruları',
                                          style: Theme.of(context)
                                              .textTheme
                                              .titleSmall
                                              ?.copyWith(
                                                fontWeight: FontWeight.w900,
                                              ),
                                        ),
                                        const SizedBox(height: 2),
                                        Text(
                                          'Konu anlatımını pekiştir (kolay/orta/zor)',
                                          style: Theme.of(context)
                                              .textTheme
                                              .bodySmall
                                              ?.copyWith(
                                                color: scheme.onSurface
                                                    .withValues(alpha: 0.72),
                                              ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 12),
                              Wrap(
                                spacing: 10,
                                runSpacing: 10,
                                children: [
                                  _difficultyChip(
                                    context,
                                    d: Difficulty.easy,
                                    label: 'Kolay',
                                    count: libQs
                                        .where((q) =>
                                            q.difficulty == Difficulty.easy)
                                        .length,
                                    icon: Icons.sentiment_satisfied_rounded,
                                  ),
                                  _difficultyChip(
                                    context,
                                    d: Difficulty.medium,
                                    label: 'Orta',
                                    count: libQs
                                        .where((q) =>
                                            q.difficulty == Difficulty.medium)
                                        .length,
                                    icon: Icons.sentiment_neutral_rounded,
                                  ),
                                  _difficultyChip(
                                    context,
                                    d: Difficulty.hard,
                                    label: 'Zor',
                                    count: libQs
                                        .where((q) =>
                                            q.difficulty == Difficulty.hard)
                                        .length,
                                    icon: Icons.sentiment_very_dissatisfied_rounded,
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(height: 10),
                    ],
                    // Video alanı
                    FutureBuilder<String?>(
                      future: _videoUrl(),
                      builder: (context, snap) {
                        final url = snap.data;
                        return Card(
                          clipBehavior: Clip.antiAlias,
                          child: Padding(
                            padding: const EdgeInsets.all(14),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Container(
                                      width: 40,
                                      height: 40,
                                      decoration: BoxDecoration(
                                        borderRadius: BorderRadius.circular(14),
                                        color: scheme.primary
                                            .withValues(alpha: 0.12),
                                        border: Border.all(
                                          color: scheme.outline
                                              .withValues(alpha: 0.30),
                                        ),
                                      ),
                                      child: Icon(Icons.play_circle_rounded,
                                          color: scheme.primary),
                                    ),
                                    const SizedBox(width: 12),
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            'Konu anlatım videoları',
                                            style: Theme.of(context)
                                                .textTheme
                                                .titleSmall
                                                ?.copyWith(
                                                  fontWeight: FontWeight.w900,
                                                ),
                                          ),
                                          const SizedBox(height: 2),
                                          Text(
                                            url == null
                                                ? 'Henüz video eklenmedi'
                                                : 'Video linki kaydedildi',
                                            style: Theme.of(context)
                                                .textTheme
                                                .bodySmall
                                                ?.copyWith(
                                                  color: scheme.onSurface
                                                      .withValues(alpha: 0.72),
                                                ),
                                          ),
                                        ],
                                      ),
                                    ),
                                    if (url != null)
                                      IconButton(
                                        tooltip: 'Kopyala',
                                        onPressed: () => _copyUrl(context, url),
                                        icon: const Icon(
                                            Icons.content_copy_rounded),
                                      ),
                                    IconButton(
                                      tooltip: url == null ? 'Ekle' : 'Düzenle',
                                      onPressed: () =>
                                          _editVideoUrl(context, url),
                                      icon: Icon(
                                        url == null
                                            ? Icons.add_link_rounded
                                            : Icons.edit_rounded,
                                      ),
                                    ),
                                  ],
                                ),
                                if (url != null) ...[
                                  const SizedBox(height: 10),
                                  SelectableText(
                                    url,
                                    style: Theme.of(context)
                                        .textTheme
                                        .bodySmall
                                        ?.copyWith(
                                          color: scheme.onSurface
                                              .withValues(alpha: 0.86),
                                        ),
                                  ),
                                ],
                              ],
                            ),
                          ),
                        );
                      },
                    ),
                    const SizedBox(height: 10),

                    // Öğrenme sonuçları
                    Card(
                      clipBehavior: Clip.antiAlias,
                      child: Container(
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.topLeft,
                            end: Alignment.bottomRight,
                            colors: [
                              scheme.surface,
                              scheme.surfaceContainerHighest
                                  .withValues(alpha: 0.55),
                            ],
                          ),
                        ),
                        child: Padding(
                          padding: const EdgeInsets.all(14),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Container(
                                    width: 40,
                                    height: 40,
                                    decoration: BoxDecoration(
                                      borderRadius: BorderRadius.circular(14),
                                      color: scheme.tertiary
                                          .withValues(alpha: 0.14),
                                      border: Border.all(
                                          color: scheme.outline
                                              .withValues(alpha: 0.30)),
                                    ),
                                    child: Icon(Icons.flag_rounded,
                                        color: scheme.tertiary),
                                  ),
                                  const SizedBox(width: 12),
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          'Öğrenme sonuçları',
                                          style: Theme.of(context)
                                              .textTheme
                                              .titleSmall
                                              ?.copyWith(
                                                fontWeight: FontWeight.w900,
                                              ),
                                        ),
                                        const SizedBox(height: 2),
                                        Text(
                                          'Bu konuyu bitirince neleri yapabilmelisin?',
                                          style: Theme.of(context)
                                              .textTheme
                                              .bodySmall
                                              ?.copyWith(
                                                color: scheme.onSurface
                                                    .withValues(alpha: 0.72),
                                              ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 12),
                              for (final item in outcomes)
                                Padding(
                                  padding:
                                      const EdgeInsets.symmetric(vertical: 5),
                                  child: Row(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Padding(
                                        padding: const EdgeInsets.only(top: 3),
                                        child: Icon(
                                          Icons.check_circle_rounded,
                                          size: 16,
                                          color: scheme.tertiary,
                                        ),
                                      ),
                                      const SizedBox(width: 10),
                                      Expanded(
                                        child: Text(
                                          item,
                                          style: Theme.of(context)
                                              .textTheme
                                              .bodyMedium
                                              ?.copyWith(height: 1.22),
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                            ],
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 10),

                    // Konu anlatımı (yazılı)
                    Card(
                      clipBehavior: Clip.antiAlias,
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Container(
                                  width: 40,
                                  height: 40,
                                  decoration: BoxDecoration(
                                    borderRadius: BorderRadius.circular(14),
                                    color:
                                        scheme.primary.withValues(alpha: 0.10),
                                    border: Border.all(
                                        color: scheme.outline
                                            .withValues(alpha: 0.30)),
                                  ),
                                  child: Icon(
                                    Icons.menu_book_rounded,
                                    color: scheme.primary,
                                  ),
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: Text(
                                    'Konu anlatımı (yazılı)',
                                    style: Theme.of(context)
                                        .textTheme
                                        .titleSmall
                                        ?.copyWith(
                                          fontWeight: FontWeight.w900,
                                        ),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 12),
                            MarkdownBody(
                              data: topic.contentMarkdown,
                              selectable: true,
                              styleSheet: _mdStyle(context),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

Widget _difficultyChip(
  BuildContext context, {
  required Difficulty d,
  required String label,
  required int count,
  required IconData icon,
}) {
  final scheme = Theme.of(context).colorScheme;
  final enabled = count > 0;
  return ActionChip(
    avatar: Icon(icon, size: 18, color: scheme.primary),
    label: Text('$label ($count)'),
    onPressed: enabled
        ? () {
            final st = context.findAncestorStateOfType<_TopicLessonScreenState>();
            if (st == null) return;
            final lang = st.widget.language;
            final topic = st.widget.topic;
            final qs = topic.libraryQuestions
                .where((q) => q.difficulty == d)
                .toList();
            if (qs.isEmpty) return;
            Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => QuizScreen(language: lang, topic: topic, questions: qs),
              ),
            );
          }
        : null,
    backgroundColor: scheme.surfaceContainerHighest.withValues(alpha: 0.40),
    side: BorderSide(color: scheme.outline.withValues(alpha: 0.30)),
  );
}
