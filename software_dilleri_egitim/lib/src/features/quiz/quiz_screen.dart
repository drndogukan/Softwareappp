import 'package:flutter/material.dart';

import '../../data/progress_store.dart';
import '../../models/content_models.dart';
import 'quiz_result_screen.dart';

class QuizScreen extends StatefulWidget {
  final LanguageContent language;
  final TopicContent topic;
  final List<Question>? questions;
  final List<String>? subtopics;

  const QuizScreen({
    super.key,
    required this.language,
    required this.topic,
    this.questions,
    this.subtopics,
  });

  @override
  State<QuizScreen> createState() => _QuizScreenState();
}

class _QuizScreenState extends State<QuizScreen> {
  int _index = 0;
  final Map<String, dynamic> _answersById = {};
  late final List<Question> _questions;
  bool _completedThisSession = false;

  bool get _isLast => _index >= _questions.length - 1;

  Question get _q => _questions[_index];

  @override
  void initState() {
    super.initState();
    _questions = List.unmodifiable(widget.questions ?? widget.topic.questions);
    if (_questions.isEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _finish());
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) => _markInProgress());
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

  void _next() {
    if (_isLast) {
      _finish();
      return;
    }
    setState(() => _index += 1);
  }

  void _back() {
    if (_index == 0) return;
    setState(() => _index -= 1);
  }

  int _calcCorrect() {
    int correct = 0;
    for (final q in _questions) {
      final a = _answersById[q.id];
      final ok = switch (q.type) {
        QuestionType.mcq =>
          a is int && q.answerIndex != null && a == q.answerIndex,
        QuestionType.tf =>
          a is bool && q.answerBool != null && a == q.answerBool,
        QuestionType.fill => a is String &&
            q.answerText != null &&
            a.trim().toLowerCase() == q.answerText!.trim().toLowerCase(),
      };
      if (ok) correct += 1;
    }
    return correct;
  }

  Future<void> _finish() async {
    final total = _questions.length;
    final correct = _calcCorrect();
    final score = total == 0 ? 0 : ((correct / total) * 100).round();

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

    final solved = prev.quizSolvedIds.toSet()..addAll(_questions.map((q) => q.id));
    final updated = prev.copyWith(
      attempts: prev.attempts + 1,
      lastScore: score,
      bestScore: score > prev.bestScore ? score : prev.bestScore,
      lastCorrect: correct,
      lastTotal: total,
      lastAttemptAt: DateTime.now(),
      inProgress: false,
      quizSolvedIds: solved.toList(),
    );
    all[key] = updated;
    await store.saveAll(all);
    _completedThisSession = true;

    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(
        builder: (_) => QuizResultScreen(
          language: widget.language,
          topic: widget.topic,
          questions: _questions,
          answersById: Map.unmodifiable(_answersById),
          score: score,
          correctCount: correct,
          totalCount: total,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_questions.isEmpty) {
      return Scaffold(
        appBar: AppBar(title: Text('Test • ${widget.topic.title}')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }
    final q = _q;
    return Scaffold(
      appBar: AppBar(
        title: Text('Test • ${widget.topic.title}'),
      ),
      body: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (widget.subtopics != null && widget.subtopics!.isNotEmpty) ...[
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Alt başlıklar',
                        style: Theme.of(context).textTheme.titleSmall?.copyWith(
                              fontWeight: FontWeight.w900,
                            ),
                      ),
                      const SizedBox(height: 8),
                      for (final s in widget.subtopics!) ...[
                        Text('• $s'),
                      ],
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 8),
            ],
            Row(
              children: [
                Expanded(
                  child: Text(
                    'Soru ${_index + 1}/${_questions.length}',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                Text(_difficultyLabel(q.difficulty)),
              ],
            ),
            const SizedBox(height: 8),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Text(q.prompt),
              ),
            ),
            const SizedBox(height: 8),
            Expanded(child: _questionBody(q: q)),
            const SizedBox(height: 8),
            Row(
              children: [
                OutlinedButton.icon(
                  onPressed: _index == 0 ? null : _back,
                  icon: const Icon(Icons.chevron_left),
                  label: const Text('Geri'),
                ),
                const Spacer(),
                FilledButton.icon(
                  onPressed: () {
                    final hasAnswer = _answersById.containsKey(q.id) &&
                        _answersById[q.id] != null &&
                        (_answersById[q.id] is! String ||
                            (_answersById[q.id] as String).trim().isNotEmpty);
                    if (!hasAnswer) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('Once cevaplayin.')),
                      );
                      return;
                    }
                    _next();
                  },
                  icon: Icon(_isLast ? Icons.flag : Icons.chevron_right),
                  label: Text(_isLast ? 'Bitir' : 'Ileri'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  String _difficultyLabel(Difficulty d) => switch (d) {
        Difficulty.easy => 'Kolay',
        Difficulty.medium => 'Orta',
        Difficulty.hard => 'Zor',
      };

  Widget _questionBody({required Question q}) {
    return switch (q.type) {
      QuestionType.mcq => _Mcq(
          question: q,
          selected: _answersById[q.id] as int?,
          onChanged: (v) => setState(() => _answersById[q.id] = v),
        ),
      QuestionType.tf => _Tf(
          question: q,
          selected: _answersById[q.id] as bool?,
          onChanged: (v) => setState(() => _answersById[q.id] = v),
        ),
      QuestionType.fill => _Fill(
          question: q,
          value: _answersById[q.id] as String?,
          onChanged: (v) => _answersById[q.id] = v,
        ),
    };
  }
}

class _Mcq extends StatelessWidget {
  final Question question;
  final int? selected;
  final ValueChanged<int> onChanged;

  const _Mcq({
    required this.question,
    required this.selected,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return RadioGroup<int>(
      groupValue: selected,
      onChanged: (v) {
        if (v == null) return;
        onChanged(v);
      },
      child: ListView.separated(
        itemBuilder: (context, index) {
          final c = question.choices[index];
          return RadioListTile<int>(
            value: index,
            title: Text(c),
          );
        },
        separatorBuilder: (_, __) => const SizedBox(height: 4),
        itemCount: question.choices.length,
      ),
    );
  }
}

class _Tf extends StatelessWidget {
  final Question question;
  final bool? selected;
  final ValueChanged<bool> onChanged;

  const _Tf({
    required this.question,
    required this.selected,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return RadioGroup<bool>(
      groupValue: selected,
      onChanged: (v) {
        if (v == null) return;
        onChanged(v);
      },
      child: const Column(
        children: [
          RadioListTile<bool>(
            value: true,
            title: Text('Dogru'),
          ),
          RadioListTile<bool>(
            value: false,
            title: Text('Yanlis'),
          ),
        ],
      ),
    );
  }
}

class _Fill extends StatefulWidget {
  final Question question;
  final String? value;
  final ValueChanged<String> onChanged;

  const _Fill({
    required this.question,
    required this.value,
    required this.onChanged,
  });

  @override
  State<_Fill> createState() => _FillState();
}

class _FillState extends State<_Fill> {
  late final TextEditingController _c;

  @override
  void initState() {
    super.initState();
    _c = TextEditingController(text: widget.value ?? '');
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        TextField(
          controller: _c,
          onChanged: widget.onChanged,
          decoration: const InputDecoration(
            labelText: 'Cevap',
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 12),
        Text(
          'Buyuk/kucuk harf duyarsiz kontrol edilir.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
      ],
    );
  }
}
