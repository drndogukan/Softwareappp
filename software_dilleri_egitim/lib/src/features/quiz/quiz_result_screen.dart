import 'package:flutter/material.dart';

import '../../models/content_models.dart';

class QuizResultScreen extends StatelessWidget {
  final LanguageContent language;
  final TopicContent topic;
  final List<Question> questions;
  final Map<String, dynamic> answersById;
  final int score;
  final int correctCount;
  final int totalCount;

  const QuizResultScreen({
    super.key,
    required this.language,
    required this.topic,
    required this.questions,
    required this.answersById,
    required this.score,
    required this.correctCount,
    required this.totalCount,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Sonuc')),
      body: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(language.name, style: Theme.of(context).textTheme.titleLarge),
                  const SizedBox(height: 4),
                  Text(topic.title, style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 12),
                  Text('Skor: %$score'),
                  Text('Dogru: $correctCount / $totalCount'),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          Text(
            'Detay',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          ...questions
              .map((q) => _ResultItem(question: q, answer: answersById[q.id])),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: () => Navigator.of(context).pop(),
            icon: const Icon(Icons.home),
            label: const Text('Konuya Don'),
          ),
        ],
      ),
    );
  }
}

class _ResultItem extends StatelessWidget {
  final Question question;
  final dynamic answer;

  const _ResultItem({required this.question, required this.answer});

  @override
  Widget build(BuildContext context) {
    final ok = switch (question.type) {
      QuestionType.mcq => answer is int && question.answerIndex != null && answer == question.answerIndex,
      QuestionType.tf => answer is bool && question.answerBool != null && answer == question.answerBool,
      QuestionType.fill => answer is String &&
          question.answerText != null &&
          answer.trim().toLowerCase() == question.answerText!.trim().toLowerCase(),
    };

    final answerText = _answerToText(question, answer);
    final correctText = _correctToText(question);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(ok ? Icons.check_circle : Icons.cancel, color: ok ? Colors.green : Colors.red),
                const SizedBox(width: 8),
                Expanded(child: Text(question.prompt, style: Theme.of(context).textTheme.titleSmall)),
              ],
            ),
            const SizedBox(height: 8),
            Text('Senin cevabin: $answerText'),
            Text('Dogru cevap: $correctText'),
            if (question.explanation.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(
                question.explanation,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ],
        ),
      ),
    );
  }

  String _answerToText(Question q, dynamic a) {
    return switch (q.type) {
      QuestionType.mcq => (a is int && a >= 0 && a < q.choices.length) ? q.choices[a] : '-',
      QuestionType.tf => a == true ? 'Dogru' : (a == false ? 'Yanlis' : '-'),
      QuestionType.fill => (a is String && a.trim().isNotEmpty) ? a.trim() : '-',
    };
  }

  String _correctToText(Question q) {
    return switch (q.type) {
      QuestionType.mcq => (q.answerIndex != null && q.answerIndex! >= 0 && q.answerIndex! < q.choices.length)
          ? q.choices[q.answerIndex!]
          : '-',
      QuestionType.tf => q.answerBool == true ? 'Dogru' : 'Yanlis',
      QuestionType.fill => q.answerText ?? '-',
    };
  }
}

