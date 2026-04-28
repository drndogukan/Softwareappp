import 'package:flutter/material.dart';

import '../../models/content_models.dart';
import '../quiz/quiz_screen.dart';

class TopicScreen extends StatelessWidget {
  final LanguageContent language;
  final TopicContent topic;

  const TopicScreen({super.key, required this.language, required this.topic});

  @override
  Widget build(BuildContext context) {
    final hasQuestions = topic.questions.isNotEmpty;
    return Scaffold(
      appBar: AppBar(title: Text(topic.title)),
      body: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: SelectableText(topic.contentMarkdown),
            ),
          ),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: hasQuestions
                ? () {
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) =>
                            QuizScreen(language: language, topic: topic),
                      ),
                    );
                  }
                : null,
            icon: const Icon(Icons.quiz),
            label: Text('Teste Basla (${topic.questions.length} soru)'),
          ),
          const SizedBox(height: 8),
          Text(
            'Not: Kod ornekleri ve bicimlendirme icin (isterseniz) sonraki adimda markdown renderer ekleyebiliriz.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}

