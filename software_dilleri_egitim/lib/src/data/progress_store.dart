import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class TopicProgress {
  final int attempts;
  final int bestScore; // 0..100
  final int lastScore; // 0..100
  final int lastCorrect;
  final int lastTotal;
  final DateTime? lastAttemptAt;
  final bool inProgress;
  final List<String> quizSolvedIds;
  final int compilerPoints;
  final List<String> compilerSolvedIds;

  const TopicProgress({
    required this.attempts,
    required this.bestScore,
    required this.lastScore,
    required this.lastCorrect,
    required this.lastTotal,
    required this.lastAttemptAt,
    required this.inProgress,
    required this.quizSolvedIds,
    required this.compilerPoints,
    required this.compilerSolvedIds,
  });

  TopicProgress copyWith({
    int? attempts,
    int? bestScore,
    int? lastScore,
    int? lastCorrect,
    int? lastTotal,
    DateTime? lastAttemptAt,
    bool? inProgress,
    List<String>? quizSolvedIds,
    int? compilerPoints,
    List<String>? compilerSolvedIds,
  }) {
    return TopicProgress(
      attempts: attempts ?? this.attempts,
      bestScore: bestScore ?? this.bestScore,
      lastScore: lastScore ?? this.lastScore,
      lastCorrect: lastCorrect ?? this.lastCorrect,
      lastTotal: lastTotal ?? this.lastTotal,
      lastAttemptAt: lastAttemptAt ?? this.lastAttemptAt,
      inProgress: inProgress ?? this.inProgress,
      quizSolvedIds: quizSolvedIds ?? this.quizSolvedIds,
      compilerPoints: compilerPoints ?? this.compilerPoints,
      compilerSolvedIds: compilerSolvedIds ?? this.compilerSolvedIds,
    );
  }

  Map<String, dynamic> toJson() => {
        'attempts': attempts,
        'bestScore': bestScore,
        'lastScore': lastScore,
        'lastCorrect': lastCorrect,
        'lastTotal': lastTotal,
        'lastAttemptAt': lastAttemptAt?.toIso8601String(),
        'inProgress': inProgress,
        'quizSolvedIds': quizSolvedIds,
        'compilerPoints': compilerPoints,
        'compilerSolvedIds': compilerSolvedIds,
      };

  factory TopicProgress.fromJson(Map<String, dynamic> json) => TopicProgress(
        attempts: (json['attempts'] as num?)?.toInt() ?? 0,
        bestScore: (json['bestScore'] as num?)?.toInt() ?? 0,
        lastScore: (json['lastScore'] as num?)?.toInt() ?? 0,
        lastCorrect: (json['lastCorrect'] as num?)?.toInt() ?? 0,
        lastTotal: (json['lastTotal'] as num?)?.toInt() ?? 0,
        lastAttemptAt: (json['lastAttemptAt'] as String?) == null
            ? null
            : DateTime.tryParse(json['lastAttemptAt'] as String),
        inProgress: (json['inProgress'] as bool?) ?? false,
        quizSolvedIds: (json['quizSolvedIds'] as List<dynamic>? ?? const [])
            .map((e) => e.toString())
            .toList(),
        compilerPoints: (json['compilerPoints'] as num?)?.toInt() ?? 0,
        compilerSolvedIds:
            (json['compilerSolvedIds'] as List<dynamic>? ?? const [])
                .map((e) => e.toString())
                .toList(),
      );
}

class ProgressStore {
  static const _key = 'progress_v1';
  static final ValueNotifier<int> revision = ValueNotifier<int>(0);

  Future<Map<String, TopicProgress>> loadAll() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_key);
    if (raw == null || raw.isEmpty) return {};
    final decoded = jsonDecode(raw) as Map<String, dynamic>;
    return decoded.map((k, v) => MapEntry(
        k, TopicProgress.fromJson((v as Map).cast<String, dynamic>())));
  }

  Future<void> saveAll(Map<String, TopicProgress> progress) async {
    final prefs = await SharedPreferences.getInstance();
    final raw = jsonEncode(progress.map((k, v) => MapEntry(k, v.toJson())));
    await prefs.setString(_key, raw);
    revision.value = revision.value + 1;
  }

  String topicKey({required String languageId, required String topicId}) =>
      '$languageId::$topicId';
}
