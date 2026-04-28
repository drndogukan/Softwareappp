enum QuestionType { mcq, tf, fill }

enum Difficulty { easy, medium, hard }

class ContentCatalog {
  final int version;
  final List<LanguageContent> languages;

  ContentCatalog({required this.version, required this.languages});

  factory ContentCatalog.fromJson(Map<String, dynamic> json) {
    final languagesJson = (json['languages'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>();
    return ContentCatalog(
      version: (json['version'] as num?)?.toInt() ?? 1,
      languages: languagesJson.map(LanguageContent.fromJson).toList(),
    );
  }
}

class LanguageContent {
  final String id;
  final String name;
  final String description;
  final List<TopicContent> topics;

  LanguageContent({
    required this.id,
    required this.name,
    required this.description,
    required this.topics,
  });

  factory LanguageContent.fromJson(Map<String, dynamic> json) {
    final topicsJson = (json['topics'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>();
    return LanguageContent(
      id: (json['id'] as String?) ?? '',
      name: (json['name'] as String?) ?? '',
      description: (json['description'] as String?) ?? '',
      topics: topicsJson.map(TopicContent.fromJson).toList(),
    );
  }
}

class TopicContent {
  final String id;
  final String title;
  final String contentMarkdown;
  final List<Question> questions;
  final List<Question> libraryQuestions;
  final List<CompilerChallengeContent> compilerChallenges;

  TopicContent({
    required this.id,
    required this.title,
    required this.contentMarkdown,
    required this.questions,
    required this.libraryQuestions,
    required this.compilerChallenges,
  });

  factory TopicContent.fromJson(Map<String, dynamic> json) {
    final questionsJson = (json['questions'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>();
    final libQuestionsJson =
        (json['libraryQuestions'] as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>();
    final compilerJson =
        (json['compilerChallenges'] as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>();
    return TopicContent(
      id: (json['id'] as String?) ?? '',
      title: (json['title'] as String?) ?? '',
      contentMarkdown: (json['contentMarkdown'] as String?) ?? '',
      questions: questionsJson.map(Question.fromJson).toList(),
      libraryQuestions: libQuestionsJson.map(Question.fromJson).toList(),
      compilerChallenges:
          compilerJson.map(CompilerChallengeContent.fromJson).toList(),
    );
  }
}

class CompilerChallengeContent {
  final String id;
  final String title;
  final Difficulty difficulty;
  final String prompt;
  final String starterCode;
  final String solutionCode;
  final String expectedOutput;

  const CompilerChallengeContent({
    required this.id,
    required this.title,
    required this.difficulty,
    required this.prompt,
    required this.starterCode,
    required this.solutionCode,
    required this.expectedOutput,
  });

  factory CompilerChallengeContent.fromJson(Map<String, dynamic> json) {
    final diffStr = (json['difficulty'] as String?) ?? 'easy';
    final difficulty = switch (diffStr) {
      'medium' => Difficulty.medium,
      'hard' => Difficulty.hard,
      _ => Difficulty.easy,
    };
    return CompilerChallengeContent(
      id: (json['id'] as String?) ?? '',
      title: (json['title'] as String?) ?? '',
      difficulty: difficulty,
      prompt: (json['prompt'] as String?) ?? '',
      starterCode: (json['starterCode'] as String?) ?? '',
      solutionCode: (json['solutionCode'] as String?) ?? '',
      expectedOutput: (json['expectedOutput'] as String?) ?? '',
    );
  }
}

class Question {
  final String id;
  final QuestionType type;
  final Difficulty difficulty;
  final String prompt;

  // MCQ
  final List<String> choices;
  final int? answerIndex;

  // True/False
  final bool? answerBool;

  // Fill
  final String? answerText;

  final String explanation;

  Question({
    required this.id,
    required this.type,
    required this.difficulty,
    required this.prompt,
    required this.choices,
    required this.answerIndex,
    required this.answerBool,
    required this.answerText,
    required this.explanation,
  });

  factory Question.fromJson(Map<String, dynamic> json) {
    final typeStr = (json['type'] as String?) ?? 'mcq';
    final diffStr = (json['difficulty'] as String?) ?? 'easy';

    final type = switch (typeStr) {
      'tf' => QuestionType.tf,
      'fill' => QuestionType.fill,
      _ => QuestionType.mcq,
    };

    final difficulty = switch (diffStr) {
      'medium' => Difficulty.medium,
      'hard' => Difficulty.hard,
      _ => Difficulty.easy,
    };

    final choices = (json['choices'] as List<dynamic>? ?? const [])
        .map((e) => e.toString())
        .toList();

    return Question(
      id: (json['id'] as String?) ?? '',
      type: type,
      difficulty: difficulty,
      prompt: (json['prompt'] as String?) ?? '',
      choices: choices,
      answerIndex: (json['answerIndex'] as num?)?.toInt(),
      answerBool: json['answerBool'] as bool?,
      answerText: (json['answerText'] as String?),
      explanation: (json['explanation'] as String?) ?? '',
    );
  }
}
