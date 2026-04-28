import 'dart:async';
import 'dart:convert';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';

import 'progress_store.dart';

/// Syncs local progress (SharedPreferences) <-> Firebase Cloud Firestore per user.
///
/// - Pulls once on sign-in (merge strategy: remote wins if it has more keys).
/// - Pushes on every local revision (debounced).
class ProgressCloudSync {
  ProgressCloudSync._();
  static final instance = ProgressCloudSync._();

  final _store = ProgressStore();
  StreamSubscription<User?>? _authSub;
  VoidCallback? _revListener;
  Timer? _debounce;

  String? _activeUid;
  bool _pulling = false;
  bool _pushing = false;

  void ensureStarted() {
    _authSub ??=
        FirebaseAuth.instance.authStateChanges().listen((user) async {
      final uid = user?.uid;
      if (uid == null) {
        _stopForUser();
        return;
      }
      if (_activeUid == uid) return;
      await _startForUser(uid);
    });
  }

  void dispose() {
    _stopForUser();
    _authSub?.cancel();
    _authSub = null;
  }

  DocumentReference<Map<String, dynamic>> _doc(String uid) {
    // Keep the raw JSON string to avoid map-field-name restrictions.
    return FirebaseFirestore.instance
        .collection('users')
        .doc(uid)
        .collection('app')
        .doc('progress_v1');
  }

  Future<void> _startForUser(String uid) async {
    _stopForUser();
    _activeUid = uid;

    // Pull once (best effort).
    await _pullFromCloud(uid);

    // Push on local changes (debounced).
    _revListener = () {
      _debounce?.cancel();
      _debounce = Timer(const Duration(milliseconds: 600), () {
        final currentUid = _activeUid;
        if (currentUid == null) return;
        _pushToCloud(currentUid);
      });
    };
    ProgressStore.revision.addListener(_revListener!);
  }

  void _stopForUser() {
    _debounce?.cancel();
    _debounce = null;
    if (_revListener != null) {
      ProgressStore.revision.removeListener(_revListener!);
      _revListener = null;
    }
    _activeUid = null;
  }

  Future<void> _pullFromCloud(String uid) async {
    if (_pulling) return;
    _pulling = true;
    try {
      final snap = await _doc(uid).get();
      final data = snap.data();
      final raw = (data?['progressJson'] as String?) ?? '';
      if (raw.trim().isEmpty) return;

      final decoded = jsonDecode(raw) as Map<String, dynamic>;
      final remote = decoded.map(
        (k, v) => MapEntry(
          k,
          TopicProgress.fromJson((v as Map).cast<String, dynamic>()),
        ),
      );

      final local = await _store.loadAll();
      // Simple merge: pick whichever side has more keys; union to be safe.
      final merged = <String, TopicProgress>{}..addAll(local);
      for (final e in remote.entries) {
        merged[e.key] = e.value;
      }

      if (_shouldReplaceLocal(local: local, merged: merged)) {
        await _store.saveAll(merged);
      }
    } catch (_) {
      // Best effort: ignore pull failures (offline / permission / etc.).
    } finally {
      _pulling = false;
    }
  }

  bool _shouldReplaceLocal({
    required Map<String, TopicProgress> local,
    required Map<String, TopicProgress> merged,
  }) {
    if (merged.length != local.length) return true;
    // If same length, keep local to avoid extra writes.
    return false;
  }

  Future<void> _pushToCloud(String uid) async {
    if (_pushing) return;
    _pushing = true;
    try {
      final progress = await _store.loadAll();
      final raw = jsonEncode(progress.map((k, v) => MapEntry(k, v.toJson())));
      await _doc(uid).set(
        {
          'progressJson': raw,
          'updatedAt': FieldValue.serverTimestamp(),
        },
        SetOptions(merge: true),
      );
    } catch (_) {
      // Best effort: ignore push failures (offline / permission / etc.).
    } finally {
      _pushing = false;
    }
  }
}

