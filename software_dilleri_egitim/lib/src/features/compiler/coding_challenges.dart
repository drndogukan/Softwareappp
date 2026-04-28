import '../../models/content_models.dart';

class CodingChallenge {
  final String id;
  final String title;
  final Difficulty difficulty;
  final String prompt;
  final String starterCode;
  final String solutionCode;
  final String expectedOutput;

  const CodingChallenge({
    required this.id,
    required this.title,
    required this.difficulty,
    required this.prompt,
    required this.starterCode,
    required this.solutionCode,
    required this.expectedOutput,
  });
}

String _norm(String s) => s.replaceAll(RegExp(r'\s+'), '');

bool isSolutionMatch({required String userCode, required String solutionCode}) {
  // MVP: whitespace-insensitive exact match.
  return _norm(userCode) == _norm(solutionCode);
}

CodingChallenge challengeFor({
  required LanguageContent language,
  required TopicContent topic,
}) {
  return challengesFor(language: language, topic: topic).first;
}

List<CodingChallenge> challengesFor({
  required LanguageContent language,
  required TopicContent topic,
}) {
  // Preferred: author-controlled challenges coming from catalog.json
  if (topic.compilerChallenges.isNotEmpty) {
    return topic.compilerChallenges
        .map(
          (c) => CodingChallenge(
            id: c.id,
            title: c.title,
            difficulty: c.difficulty,
            prompt: c.prompt,
            starterCode: c.starterCode,
            solutionCode: c.solutionCode,
            expectedOutput: c.expectedOutput,
          ),
        )
        .toList();
  }

  final langId = language.id;
  final topicId = topic.id.isEmpty ? 'topic' : topic.id;

  // MVP: 2 küçük görev / konu. Offline olduğumuz için "expectedOutput" sabit.
  // (İstersen sonraki adımda gerçek çalıştırma için server/runner bağlarız.)
  List<CodingChallenge> mk({
    required CodingChallenge a,
    required CodingChallenge b,
  }) =>
      [a, b];

  return switch (langId) {
    'python' => mk(
        a: CodingChallenge(
          id: 'py-$topicId-1',
          title: '${topic.title} • Yazdır',
          difficulty: Difficulty.easy,
          prompt: "Ekrana 'Merhaba!' yazdır.",
          starterCode: "def main():\n    # TODO: buraya yaz\n\nmain()\n",
          solutionCode: "def main():\n    print('Merhaba!')\n\nmain()\n",
          expectedOutput: "Merhaba!\n",
        ),
        b: CodingChallenge(
          id: 'py-$topicId-2',
          title: '${topic.title} • Topla',
          difficulty: Difficulty.easy,
          prompt: "a=2 ve b=3 için a+b sonucunu yazdır.",
          starterCode:
              "def main():\n    a = 2\n    b = 3\n    # TODO\n\nmain()\n",
          solutionCode:
              "def main():\n    a = 2\n    b = 3\n    print(a + b)\n\nmain()\n",
          expectedOutput: "5\n",
        ),
      ),
    'javascript' => mk(
        a: CodingChallenge(
          id: 'js-$topicId-1',
          title: '${topic.title} • Yazdır',
          difficulty: Difficulty.easy,
          prompt: "Konsola 'Merhaba!' yazdır.",
          starterCode: "// TODO\n",
          solutionCode: "console.log('Merhaba!');\n",
          expectedOutput: "Merhaba!\n",
        ),
        b: CodingChallenge(
          id: 'js-$topicId-2',
          title: '${topic.title} • Topla',
          difficulty: Difficulty.easy,
          prompt: "2+3 sonucunu yazdır.",
          starterCode: "const a = 2;\nconst b = 3;\n// TODO\n",
          solutionCode: "const a = 2;\nconst b = 3;\nconsole.log(a + b);\n",
          expectedOutput: "5\n",
        ),
      ),
    'dart' => mk(
        a: CodingChallenge(
          id: 'dart-$topicId-1',
          title: '${topic.title} • Yazdır',
          difficulty: Difficulty.easy,
          prompt: "Ekrana 'Merhaba!' yazdır.",
          starterCode: "void main() {\n  // TODO\n}\n",
          solutionCode: "void main() {\n  print('Merhaba!');\n}\n",
          expectedOutput: "Merhaba!\n",
        ),
        b: CodingChallenge(
          id: 'dart-$topicId-2',
          title: '${topic.title} • Topla',
          difficulty: Difficulty.easy,
          prompt: "2+3 sonucunu yazdır.",
          starterCode:
              "void main() {\n  final a = 2;\n  final b = 3;\n  // TODO\n}\n",
          solutionCode:
              "void main() {\n  final a = 2;\n  final b = 3;\n  print(a + b);\n}\n",
          expectedOutput: "5\n",
        ),
      ),
    'java' => mk(
        a: CodingChallenge(
          id: 'java-$topicId-1',
          title: '${topic.title} • Yazdır',
          difficulty: Difficulty.easy,
          prompt: "Ekrana 'Merhaba!' yazdır.",
          starterCode:
              "public class Main {\n  public static void main(String[] args) {\n    // TODO\n  }\n}\n",
          solutionCode:
              "public class Main {\n  public static void main(String[] args) {\n    System.out.println(\"Merhaba!\");\n  }\n}\n",
          expectedOutput: "Merhaba!\n",
        ),
        b: CodingChallenge(
          id: 'java-$topicId-2',
          title: '${topic.title} • Topla',
          difficulty: Difficulty.easy,
          prompt: "2+3 sonucunu yazdır.",
          starterCode:
              "public class Main {\n  public static void main(String[] args) {\n    int a = 2;\n    int b = 3;\n    // TODO\n  }\n}\n",
          solutionCode:
              "public class Main {\n  public static void main(String[] args) {\n    int a = 2;\n    int b = 3;\n    System.out.println(a + b);\n  }\n}\n",
          expectedOutput: "5\n",
        ),
      ),
    _ => mk(
        a: CodingChallenge(
          id: 'generic-$topicId-1',
          title: '${topic.title} • Görev 1',
          difficulty: Difficulty.easy,
          prompt: 'Kodu tamamla.',
          starterCode: '// TODO\n',
          solutionCode: '// TODO\n',
          expectedOutput: '',
        ),
        b: CodingChallenge(
          id: 'generic-$topicId-2',
          title: '${topic.title} • Görev 2',
          difficulty: Difficulty.easy,
          prompt: 'Kodu tamamla.',
          starterCode: '// TODO\n',
          solutionCode: '// TODO\n',
          expectedOutput: '',
        ),
      ),
  };
}
