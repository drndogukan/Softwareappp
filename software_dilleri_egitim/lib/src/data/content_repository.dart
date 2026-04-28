import 'dart:convert';

import 'package:flutter/services.dart';

import '../models/content_models.dart';

class ContentRepository {
  Future<ContentCatalog> loadCatalog() async {
    final raw = await rootBundle.loadString('assets/content/catalog.json');
    final decoded = jsonDecode(raw) as Map<String, dynamic>;
    final catalog = ContentCatalog.fromJson(decoded);

    final pythonTopics = await _loadPythonRoadmapTopics();
    if (pythonTopics.isEmpty) return catalog;

    final updatedLanguages = catalog.languages.map((l) {
      if (l.id != 'python') return l;
      return LanguageContent(
        id: l.id,
        name: l.name,
        description: l.description,
        topics: pythonTopics,
      );
    }).toList();

    return ContentCatalog(version: catalog.version, languages: updatedLanguages);
  }

  Future<List<TopicContent>> _loadPythonRoadmapTopics() async {
    final paths = <String>[
      'assets/python/1_fundamentals.json',
      'assets/python/2_control_flow.json',
      'assets/python/3_data_structures.json',
      'assets/python/4_functions.json',
      'assets/python/5_exceptions_files.json',
      'assets/python/6_oop.json',
      'assets/python/7_modules_packages.json',
      'assets/python/8_advanced_topics.json',
      'assets/python/9_specialization.json',
    ];

    final out = <TopicContent>[];
    for (final p in paths) {
      try {
        final raw = await rootBundle.loadString(p);
        final m = jsonDecode(raw) as Map<String, dynamic>;
        final id = (m['id'] as String?) ?? p;
        final title = (m['title'] as String?) ?? id;
        final contentPath = (m['contentPath'] as String?)?.trim();
        final subtopics = (m['subtopics'] as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>();
        final questionsJson = (m['questions'] as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>();

        final md = (contentPath != null && contentPath.isNotEmpty)
            ? await rootBundle.loadString(contentPath)
            : _roadmapToMarkdown(title, subtopics);

        out.add(
          TopicContent(
            id: id,
            title: title,
            contentMarkdown: md,
            questions: questionsJson.map(Question.fromJson).toList(),
            libraryQuestions: const [],
            compilerChallenges: const [],
          ),
        );
      } catch (_) {
        // If any file is missing or malformed, we just skip it.
      }
    }
    return out;
  }

  String _roadmapToMarkdown(
    String title,
    List<Map<String, dynamic>> subtopics,
  ) {
    final b = StringBuffer()
      ..writeln('### $title')
      ..writeln();

    for (final s in subtopics) {
      final sid = (s['id'] as String?) ?? '';
      final st = (s['title'] as String?) ?? '';
      final items = (s['items'] as List<dynamic>? ?? const [])
          .map((e) => e.toString())
          .toList();

      if (st.isNotEmpty) {
        b.writeln('#### ${sid.isEmpty ? '' : '$sid. '}$st');
      }
      for (final it in items) {
        b.writeln('- $it');
      }
      b.writeln();
    }

    return b.toString().trimRight();
  }
}

