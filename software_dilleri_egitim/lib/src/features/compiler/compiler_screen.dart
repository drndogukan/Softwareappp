import 'package:flutter/material.dart';

import '../../models/content_models.dart';
import '../../data/progress_store.dart';
import 'coding_challenges.dart';

class CompilerScreen extends StatefulWidget {
  final LanguageContent language;
  final TopicContent topic;
  final List<CodingChallenge>? challenges;

  const CompilerScreen({
    super.key,
    required this.language,
    required this.topic,
    this.challenges,
  });

  @override
  State<CompilerScreen> createState() => _CompilerScreenState();
}

class _CompilerScreenState extends State<CompilerScreen> {
  late final TextEditingController _code;
  int _challengeIndex = 0;
  bool _checked = false;
  bool _correct = false;
  bool _completedThisSession = false;
  int _earnedPointsThisSession = 0;

  List<CodingChallenge> get _list =>
      widget.challenges ??
      challengesFor(language: widget.language, topic: widget.topic);

  @override
  void initState() {
    super.initState();
    final ch = _list.first;
    _code = TextEditingController(text: ch.starterCode);
    // Teste girildi: yarım bırakılırsa "Devam et" görünmeli.
    WidgetsBinding.instance.addPostFrameCallback((_) => _markInProgress());
  }

  @override
  void dispose() {
    // Doğru bitirildiyse inProgress zaten false'a çekildi.
    _code.dispose();
    super.dispose();
  }

  Future<void> _markInProgress() async {
    final store = ProgressStore();
    final key = store.topicKey(
        languageId: widget.language.id, topicId: widget.topic.id);
    final all = await store.loadAll();
    final prev = all[key] ??
        const TopicProgress(
          attempts: 0,
          bestScore: 0,
          lastScore: 0,
          lastCorrect: 0,
          lastTotal: 0,
          lastAttemptAt: null,
          inProgress: false,
          quizSolvedIds: [],
          compilerPoints: 0,
          compilerSolvedIds: [],
        );
    if (prev.inProgress || _completedThisSession) return;
    all[key] = prev.copyWith(inProgress: true, lastAttemptAt: DateTime.now());
    await store.saveAll(all);
  }

  void _loadChallenge(int nextIndex) {
    final list = _list;
    final i = nextIndex.clamp(0, list.length - 1);
    final ch = list[i];
    setState(() {
      _challengeIndex = i;
      _checked = false;
      _correct = false;
      _code.text = ch.starterCode;
    });
  }

  Future<void> _check() async {
    final list = _list;
    final ch = list[_challengeIndex];
    final ok =
        isSolutionMatch(userCode: _code.text, solutionCode: ch.solutionCode);
    setState(() {
      _checked = true;
      _correct = ok;
    });

    final store = ProgressStore();
    final key = store.topicKey(
        languageId: widget.language.id, topicId: widget.topic.id);
    final all = await store.loadAll();
    final prev = all[key] ??
        const TopicProgress(
          attempts: 0,
          bestScore: 0,
          lastScore: 0,
          lastCorrect: 0,
          lastTotal: 0,
          lastAttemptAt: null,
          inProgress: false,
          quizSolvedIds: [],
          compilerPoints: 0,
          compilerSolvedIds: [],
        );

    const pointsPerQuestion = 10;
    final solved = prev.compilerSolvedIds.toSet();
    final wasSolved = solved.contains(ch.id);
    final nowSolved = ok && !wasSolved;
    if (nowSolved) solved.add(ch.id);

    final total = list.length;
    final idsInThisRun = list.map((e) => e.id).toSet();
    final correct = solved.intersection(idsInThisRun).length.clamp(0, total);
    final score = total == 0 ? 0 : ((correct / total) * 100).round();

    final updated = prev.copyWith(
      attempts: prev.attempts + 1,
      lastScore: score,
      bestScore: score > prev.bestScore ? score : prev.bestScore,
      lastCorrect: correct,
      lastTotal: total,
      lastAttemptAt: DateTime.now(),
      inProgress: correct < total, // hepsi çözülmediyse "Devam et"
      compilerPoints: prev.compilerPoints + (nowSolved ? pointsPerQuestion : 0),
      compilerSolvedIds: solved.toList()..sort(),
    );
    all[key] = updated;
    await store.saveAll(all);

    if (nowSolved) {
      setState(() => _earnedPointsThisSession += pointsPerQuestion);
    }
    if (correct >= total) _completedThisSession = true;
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final list = _list;
    final ch = list[_challengeIndex];
    final total = list.length;

    return Scaffold(
      appBar: AppBar(
        title: Text('Compiler • ${widget.language.name}'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      'Soru ${_challengeIndex + 1}/$total',
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(
                            fontWeight: FontWeight.w900,
                          ),
                    ),
                  ),
                  if (_earnedPointsThisSession > 0)
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 6),
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(999),
                        color: scheme.tertiary.withValues(alpha: 0.16),
                        border: Border.all(
                            color: scheme.outline.withValues(alpha: 0.30)),
                      ),
                      child: Text(
                        '+$_earnedPointsThisSession puan',
                        style: Theme.of(context).textTheme.labelLarge?.copyWith(
                              fontWeight: FontWeight.w900,
                              color: scheme.onSurface.withValues(alpha: 0.90),
                            ),
                      ),
                    ),
                ],
              ),
            ),
          ),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    ch.title,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w900,
                        ),
                  ),
                  const SizedBox(height: 8),
                  Text(ch.prompt),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        'Kod',
                        style: Theme.of(context).textTheme.titleSmall?.copyWith(
                              fontWeight: FontWeight.w900,
                            ),
                      ),
                      const Spacer(),
                      IconButton(
                        tooltip: 'Önceki',
                        onPressed: _challengeIndex == 0
                            ? null
                            : () => _loadChallenge(_challengeIndex - 1),
                        icon: const Icon(Icons.chevron_left_rounded),
                      ),
                      IconButton(
                        tooltip: 'Sonraki',
                        onPressed: _challengeIndex >= total - 1
                            ? null
                            : () => _loadChallenge(_challengeIndex + 1),
                        icon: const Icon(Icons.chevron_right_rounded),
                      ),
                      FilledButton.icon(
                        onPressed: _check,
                        icon: const Icon(Icons.check_rounded),
                        label: const Text('Kontrol Et'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: _code,
                    minLines: 10,
                    maxLines: 18,
                    decoration: const InputDecoration(
                      border: OutlineInputBorder(),
                      hintText: 'Kodunu buraya yaz…',
                    ),
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          fontFamily: 'monospace',
                          height: 1.2,
                        ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          if (_checked) ...[
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Row(
                      children: [
                        Icon(
                          _correct
                              ? Icons.verified_rounded
                              : Icons.cancel_rounded,
                          color:
                              _correct ? const Color(0xFF0FD108) : scheme.error,
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            _correct ? 'Doğru!' : 'Yanlış',
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
                    Text(
                      'Beklenen çıktı',
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(
                            fontWeight: FontWeight.w900,
                          ),
                    ),
                    const SizedBox(height: 8),
                    SelectableText(
                      ch.expectedOutput.isEmpty
                          ? '(çıktı tanımlı değil)'
                          : ch.expectedOutput,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            fontFamily: 'monospace',
                            height: 1.2,
                            color: scheme.onSurface.withValues(alpha: 0.88),
                          ),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      'Not: Bu sürümde kod gerçekten çalıştırılmıyor; doğruluk kontrolü (şimdilik) çözüm kodu ile eşleşmeye göre yapılıyor. İstersen gerçek çalıştırma (runner) ekleyebiliriz.',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: scheme.onSurface.withValues(alpha: 0.68),
                          ),
                    ),
                    if (!_correct) ...[
                      const SizedBox(height: 12),
                      Text(
                        'Doğru çözüm',
                        style: Theme.of(context).textTheme.titleSmall?.copyWith(
                              fontWeight: FontWeight.w900,
                            ),
                      ),
                      const SizedBox(height: 8),
                      SelectableText(
                        ch.solutionCode,
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              fontFamily: 'monospace',
                              height: 1.2,
                              color: scheme.onSurface.withValues(alpha: 0.88),
                            ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
