import 'package:shared_preferences/shared_preferences.dart';

class VideoStore {
  static const _prefix = 'video_url::';

  String _key({required String languageId, required String topicId}) {
    return '$_prefix$languageId::$topicId';
  }

  Future<String?> getUrl({required String languageId, required String topicId}) async {
    final prefs = await SharedPreferences.getInstance();
    final v = prefs.getString(_key(languageId: languageId, topicId: topicId));
    if (v == null) return null;
    final trimmed = v.trim();
    return trimmed.isEmpty ? null : trimmed;
  }

  Future<void> setUrl({
    required String languageId,
    required String topicId,
    required String? url,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    final k = _key(languageId: languageId, topicId: topicId);
    final v = url?.trim() ?? '';
    if (v.isEmpty) {
      await prefs.remove(k);
    } else {
      await prefs.setString(k, v);
    }
  }
}

