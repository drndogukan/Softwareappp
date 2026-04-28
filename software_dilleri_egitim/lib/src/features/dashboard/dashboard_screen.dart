import 'package:flutter/material.dart';

import 'dart:math' as math;

import '../../data/content_repository.dart';
import '../../data/progress_store.dart';
import '../../models/content_models.dart';
import 'package:firebase_auth/firebase_auth.dart';

enum _DashRange { daily, weekly, monthly }

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  _DashRange _range = _DashRange.weekly;

  String _displayName({required User? user}) {
    final name = (user?.displayName ?? '').trim();
    if (name.isNotEmpty) return name;
    final email = (user?.email ?? '').trim();
    if (email.isEmpty) return 'Kullanıcı';
    final at = email.indexOf('@');
    final raw = (at > 0 ? email.substring(0, at) : email)
        .replaceAll('.', ' ')
        .replaceAll('_', ' ');
    if (raw.trim().isEmpty) return 'Kullanıcı';
    return raw
        .split(RegExp(r'\s+'))
        .where((p) => p.isNotEmpty)
        .map((p) => p.substring(0, 1).toUpperCase() + p.substring(1))
        .join(' ');
  }

  DateTime _startOfDay(DateTime d) => DateTime(d.year, d.month, d.day);

  DateTime _startOfWeek(DateTime d) {
    // Monday-based week start.
    final day = DateTime(d.year, d.month, d.day);
    final delta = (day.weekday - DateTime.monday) % 7;
    return day.subtract(Duration(days: delta));
  }

  DateTime _startOfMonth(DateTime d) => DateTime(d.year, d.month);

  List<DateTime> _bucketStarts(DateTime now) {
    final today = _startOfDay(now);
    return switch (_range) {
      _DashRange.daily => List.generate(7, (i) => today.subtract(Duration(days: 6 - i))),
      _DashRange.weekly => List.generate(6, (i) => _startOfWeek(today).subtract(Duration(days: 7 * (5 - i)))),
      _DashRange.monthly => List.generate(
          6,
          (i) => _startOfMonth(DateTime(today.year, today.month - (5 - i), 1)),
        ),
    };
  }

  String _bucketLabel(DateTime start) {
    return switch (_range) {
      _DashRange.daily => '${start.day}/${start.month}',
      _DashRange.weekly => 'Hf ${start.day}/${start.month}',
      _DashRange.monthly => '${start.month}/${start.year % 100}',
    };
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    const brandGreen = Color(0xFF0FD108);
    final repo = ContentRepository();
    final store = ProgressStore();
    final user = FirebaseAuth.instance.currentUser;

    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: ValueListenableBuilder<int>(
          valueListenable: ProgressStore.revision,
          builder: (context, _, __) {
            return FutureBuilder(
              future: Future.wait([repo.loadCatalog(), store.loadAll()]),
              builder: (context, snap) {
                if (snap.connectionState != ConnectionState.done) {
                  return const Center(child: CircularProgressIndicator());
                }
            final data = snap.data;
            final catalog = data?[0] as ContentCatalog?;
            final progress = (data?[1] as Map<String, TopicProgress>?) ?? {};
            if (catalog == null) {
              return const Center(child: Text('Veriler yüklenemedi.'));
            }

            int totalTopicsWithTests = 0;
            int attemptedTopics = 0;
            int completedTopics = 0;
            int sumCorrect = 0;
            int sumTotal = 0;

            final now = DateTime.now();
            final buckets = _bucketStarts(now);
            final bucketCorrect = List<int>.filled(buckets.length, 0);
            final bucketTotal = List<int>.filled(buckets.length, 0);
            final bucketAny = List<bool>.filled(buckets.length, false);

            int bucketIndexFor(DateTime d) {
              final s = switch (_range) {
                _DashRange.daily => _startOfDay(d),
                _DashRange.weekly => _startOfWeek(d),
                _DashRange.monthly => _startOfMonth(d),
              };
              return buckets.indexWhere((b) => b == s);
            }

            for (final lang in catalog.languages) {
              for (final t in lang.topics) {
                if (t.questions.isEmpty) continue;
                totalTopicsWithTests += 1;
                final key = store.topicKey(languageId: lang.id, topicId: t.id);
                final p = progress[key];
                if (p == null || p.attempts <= 0) continue;
                attemptedTopics += 1;

                // Backward compatible: lastTotal might be 0 for older saves.
                final total = p.lastTotal > 0 ? p.lastTotal : t.questions.length;
                final correct = p.lastTotal > 0
                    ? p.lastCorrect
                    : (((p.lastScore) / 100) * total).round();

                sumTotal += total;
                sumCorrect += correct.clamp(0, total);
                if (p.bestScore >= 60) completedTopics += 1;

                final at = p.lastAttemptAt;
                if (at != null) {
                  final idx = bucketIndexFor(at);
                  if (idx >= 0) {
                    bucketTotal[idx] += total;
                    bucketCorrect[idx] += correct.clamp(0, total);
                    bucketAny[idx] = true;
                  }
                }
              }
            }

            final accuracyPct =
                sumTotal == 0 ? 0 : ((sumCorrect / sumTotal) * 100).round();
            final completionPct = totalTopicsWithTests == 0
                ? 0
                : ((completedTopics / totalTopicsWithTests) * 100).round();

            Widget miniStat({
              required IconData icon,
              required String title,
              required String value,
              Color? tone,
            }) {
              final c = tone ?? scheme.primary;
              return Card(
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Container(
                            width: 40,
                            height: 40,
                            decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(14),
                              color: c.withValues(alpha: 0.14),
                              border: Border.all(color: scheme.outline.withValues(alpha: 0.28)),
                            ),
                            child: Icon(icon, color: c),
                          ),
                          const Spacer(),
                          Text(
                            value,
                            style: Theme.of(context).textTheme.titleLarge?.copyWith(
                                  fontWeight: FontWeight.w900,
                                  letterSpacing: -0.3,
                                ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Text(
                        title,
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: scheme.onSurface.withValues(alpha: 0.70),
                            ),
                      ),
                    ],
                  ),
                ),
              );
            }

            return ListView(
              padding: const EdgeInsets.fromLTRB(12, 10, 12, 24),
              children: [
                _PremiumHeader(
                  title: 'Hoşgeldin',
                  name: _displayName(user: user),
                ),
                const SizedBox(height: 12),
                Text('Genel Durum', style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(
                      child: miniStat(
                        icon: Icons.topic_rounded,
                        title: 'Testli konu',
                        value: '$totalTopicsWithTests',
                        tone: scheme.primary,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: miniStat(
                        icon: Icons.playlist_add_check_circle_rounded,
                        title: 'Çözülen',
                        value: '$attemptedTopics',
                        tone: brandGreen,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: miniStat(
                        icon: Icons.verified_rounded,
                        title: 'Tamamlanan',
                        value: '$completedTopics',
                        tone: scheme.tertiary,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: miniStat(
                        icon: Icons.percent_rounded,
                        title: 'Başarı',
                        value: '%$accuracyPct',
                        tone: accuracyPct >= 60 ? brandGreen : scheme.error,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                _PremiumPerformanceCard(
                  range: _range,
                  onRangeChanged: (v) => setState(() => _range = v),
                  labels: buckets.map(_bucketLabel).toList(),
                  correct: bucketCorrect,
                  total: bucketTotal,
                  completionPct: completionPct,
                  brandGreen: brandGreen,
                  red: scheme.error,
                ),
              ],
            );
              },
            );
          },
        ),
      ),
    );
  }
}

class _PremiumHeader extends StatelessWidget {
  final String title;
  final String name;

  const _PremiumHeader({required this.title, required this.name});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(18),
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              scheme.primary.withValues(alpha: 0.22),
              scheme.surface,
              scheme.surfaceContainerHighest.withValues(alpha: 0.55),
            ],
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Container(
                width: 54,
                height: 54,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(18),
                  color: scheme.onSurface.withValues(alpha: 0.06),
                  border: Border.all(color: scheme.outline.withValues(alpha: 0.30)),
                ),
                child: Icon(Icons.person_rounded, color: scheme.onSurface.withValues(alpha: 0.85)),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                            color: scheme.onSurface.withValues(alpha: 0.75),
                          ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      name,
                      style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                            fontWeight: FontWeight.w900,
                            letterSpacing: -0.3,
                          ),
                    ),
                  ],
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(999),
                  color: scheme.primary.withValues(alpha: 0.12),
                  border: Border.all(color: scheme.outline.withValues(alpha: 0.26)),
                ),
                child: Text(
                  'Premium',
                  style: Theme.of(context).textTheme.labelLarge?.copyWith(
                        fontWeight: FontWeight.w900,
                      ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _RangeTabs extends StatelessWidget {
  final _DashRange value;
  final ValueChanged<_DashRange> onChanged;

  const _RangeTabs({required this.value, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    Widget chip(_DashRange v, String label) {
      final selected = v == value;
      return Expanded(
        child: InkWell(
          borderRadius: BorderRadius.circular(999),
          onTap: () => onChanged(v),
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 10),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(999),
              color: selected ? scheme.primary.withValues(alpha: 0.16) : scheme.surface,
              border: Border.all(
                color: selected
                    ? scheme.primary.withValues(alpha: 0.60)
                    : scheme.outline.withValues(alpha: 0.30),
              ),
            ),
            child: Text(
              label,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.labelLarge?.copyWith(
                    fontWeight: FontWeight.w900,
                    color: scheme.onSurface.withValues(alpha: selected ? 0.95 : 0.75),
                  ),
            ),
          ),
        ),
      );
    }

    return Row(
      children: [
        chip(_DashRange.daily, 'Günlük'),
        const SizedBox(width: 10),
        chip(_DashRange.weekly, 'Haftalık'),
        const SizedBox(width: 10),
        chip(_DashRange.monthly, 'Aylık'),
      ],
    );
  }
}

class _LegendDot extends StatelessWidget {
  final Color color;
  final String label;

  const _LegendDot({required this.color, required this.label});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 10,
          height: 10,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: color,
            border: Border.all(color: scheme.outline.withValues(alpha: 0.25)),
          ),
        ),
        const SizedBox(width: 6),
        Text(
          label,
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: scheme.onSurface.withValues(alpha: 0.75),
              ),
        ),
      ],
    );
  }
}

class _PremiumPerformanceCard extends StatelessWidget {
  final _DashRange range;
  final ValueChanged<_DashRange> onRangeChanged;
  final List<String> labels;
  final List<int> correct;
  final List<int> total;
  final int completionPct;
  final Color brandGreen;
  final Color red;

  const _PremiumPerformanceCard({
    required this.range,
    required this.onRangeChanged,
    required this.labels,
    required this.correct,
    required this.total,
    required this.completionPct,
    required this.brandGreen,
    required this.red,
  });

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final totalPeriods = total.where((t) => t > 0).length;
    int hit = 0;
    int sumC = 0;
    int sumT = 0;
    for (int i = 0; i < total.length; i++) {
      final t = total[i];
      if (t <= 0) continue;
      final c = correct[i].clamp(0, t);
      sumT += t;
      sumC += c;
      final pct = (c / t) * 100;
      if (pct >= 60) hit += 1;
    }
    final avg = sumT == 0 ? 0 : ((sumC / sumT) * 100).round();

    Widget kpi(String label, String value, {Color? tone}) {
      final c = tone ?? scheme.primary;
      return Expanded(
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            color: scheme.surfaceContainerHighest.withValues(alpha: 0.30),
            border: Border.all(color: scheme.outline.withValues(alpha: 0.22)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                label,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: scheme.onSurface.withValues(alpha: 0.70),
                    ),
              ),
              const SizedBox(height: 2),
              Text(
                value,
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w900,
                      color: c,
                    ),
              ),
            ],
          ),
        ),
      );
    }

    return Card(
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(18),
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              scheme.surface,
              scheme.surfaceContainerHighest.withValues(alpha: 0.45),
              scheme.primary.withValues(alpha: 0.10),
            ],
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    width: 40,
                    height: 40,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(14),
                      color: scheme.primary.withValues(alpha: 0.14),
                      border: Border.all(color: scheme.outline.withValues(alpha: 0.26)),
                    ),
                    child: Icon(Icons.auto_graph_rounded, color: scheme.primary),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Performans',
                          style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                fontWeight: FontWeight.w900,
                              ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          'Hedef: %60+',
                          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                color: scheme.onSurface.withValues(alpha: 0.70),
                              ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              _RangeTabs(value: range, onChanged: onRangeChanged),
              const SizedBox(height: 12),
              _BarChart(
                labels: labels,
                correct: correct,
                total: total,
                brandGreen: brandGreen,
                red: red,
                track: scheme.outline.withValues(alpha: 0.18),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  kpi('Ortalama', '%$avg', tone: avg >= 60 ? brandGreen : red),
                  const SizedBox(width: 10),
                  kpi('Hedef tutan', '$hit / $totalPeriods', tone: hit > 0 ? brandGreen : red),
                ],
              ),
              const SizedBox(height: 12),
              _PremiumPerfTable(
                labels: labels,
                correct: correct,
                total: total,
                green: brandGreen,
                red: red,
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 12,
                runSpacing: 10,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  const _LegendDot(
                    color: Color(0xFF0FD108),
                    label: 'Hedef üstü (≥ %60)',
                  ),
                  _LegendDot(color: red, label: 'Hedef altı'),
                  Text(
                    'Tamamlama: %$completionPct',
                    style: Theme.of(context).textTheme.labelLarge?.copyWith(
                          fontWeight: FontWeight.w900,
                          color: scheme.onSurface.withValues(alpha: 0.85),
                        ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _BarChart extends StatelessWidget {
  final List<String> labels;
  final List<int> correct;
  final List<int> total;
  final Color brandGreen;
  final Color red;
  final Color track;

  const _BarChart({
    required this.labels,
    required this.correct,
    required this.total,
    required this.brandGreen,
    required this.red,
    required this.track,
  });

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return LayoutBuilder(
      builder: (context, c) {
        final w = c.maxWidth.isFinite ? c.maxWidth : 0.0;
        return SizedBox(
          width: w <= 0 ? double.infinity : w,
          height: 160,
          child: CustomPaint(
            size: Size(w <= 0 ? 320 : w, 160),
            painter: _BarChartPainter(
              labels: labels,
              correct: correct,
              total: total,
              green: brandGreen,
              red: red,
              track: track,
              labelColor: scheme.onSurface.withValues(alpha: 0.72),
            ),
          ),
        );
      },
    );
  }
}

class _PremiumPerfTable extends StatelessWidget {
  final List<String> labels;
  final List<int> correct;
  final List<int> total;
  final Color green;
  final Color red;

  const _PremiumPerfTable({
    required this.labels,
    required this.correct,
    required this.total,
    required this.green,
    required this.red,
  });

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    final rows = <({String label, int c, int t, int pct})>[];
    for (int i = 0; i < labels.length; i++) {
      final t = total[i];
      final c = correct[i].clamp(0, t == 0 ? 0 : t);
      final pct = t == 0 ? 0 : ((c / t) * 100).round();
      rows.add((label: labels[i], c: c, t: t, pct: pct));
    }

    Widget headerCell(String text, {TextAlign align = TextAlign.left}) {
      return Text(
        text,
        textAlign: align,
        style: Theme.of(context).textTheme.labelLarge?.copyWith(
              fontWeight: FontWeight.w900,
              color: scheme.onSurface.withValues(alpha: 0.70),
            ),
      );
    }

    Widget statusChip(int pct) {
      final ok = pct >= 60;
      final tone = ok ? green : red;
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(999),
          color: tone.withValues(alpha: 0.14),
          border: Border.all(color: scheme.outline.withValues(alpha: 0.24)),
        ),
        child: Text(
          ok ? 'İyi' : 'Geliştir',
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
                fontWeight: FontWeight.w900,
                color: scheme.onSurface.withValues(alpha: 0.88),
              ),
        ),
      );
    }

    Widget rowCell(String text, {TextAlign align = TextAlign.left, bool strong = false}) {
      return Text(
        text,
        textAlign: align,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              fontWeight: strong ? FontWeight.w900 : FontWeight.w700,
              color: scheme.onSurface.withValues(alpha: 0.88),
            ),
      );
    }

    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(18),
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            scheme.surfaceContainerHighest.withValues(alpha: 0.26),
            scheme.surface.withValues(alpha: 0.92),
          ],
        ),
        border: Border.all(color: scheme.outline.withValues(alpha: 0.22)),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(18),
        child: Column(
          children: [
            Container(
              padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
              decoration: BoxDecoration(
                color: scheme.surfaceContainerHighest.withValues(alpha: 0.22),
                border: Border(
                  bottom: BorderSide(color: scheme.outline.withValues(alpha: 0.18)),
                ),
              ),
              child: Row(
                children: [
                  Expanded(flex: 3, child: headerCell('Periyot')),
                  Expanded(flex: 2, child: headerCell('Doğru', align: TextAlign.center)),
                  Expanded(flex: 2, child: headerCell('%', align: TextAlign.center)),
                  const SizedBox(width: 6),
                  headerCell('Durum', align: TextAlign.right),
                ],
              ),
            ),
            for (int i = 0; i < rows.length; i++)
              Container(
                padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
                decoration: BoxDecoration(
                  color: i.isEven
                      ? scheme.surface.withValues(alpha: 0.35)
                      : scheme.surface.withValues(alpha: 0.12),
                  border: Border(
                    bottom: BorderSide(
                      color: scheme.outline.withValues(alpha: i == rows.length - 1 ? 0 : 0.16),
                    ),
                  ),
                ),
                child: Row(
                  children: [
                    Expanded(flex: 3, child: rowCell(rows[i].label, strong: true)),
                    Expanded(
                      flex: 2,
                      child: rowCell('${rows[i].c}/${rows[i].t}', align: TextAlign.center),
                    ),
                    Expanded(
                      flex: 2,
                      child: rowCell('%${rows[i].pct}', align: TextAlign.center),
                    ),
                    const SizedBox(width: 6),
                    statusChip(rows[i].pct),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _BarChartPainter extends CustomPainter {
  final List<String> labels;
  final List<int> correct;
  final List<int> total;
  final Color green;
  final Color red;
  final Color track;
  final Color labelColor;

  _BarChartPainter({
    required this.labels,
    required this.correct,
    required this.total,
    required this.green,
    required this.red,
    required this.track,
    required this.labelColor,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final n = labels.length;
    if (n == 0) return;

    const padTop = 14.0;
    const padBottom = 28.0;
    const padH = 10.0;
    final chartH = math.max(1.0, size.height - padTop - padBottom);
    final w = size.width;
    final slot = (w - padH * 2) / n;
    final barW = math.min(18.0, slot * 0.55);

    final trackPaint = Paint()
      ..color = track
      ..style = PaintingStyle.fill;
    final greenPaint = Paint()..color = green;
    final redPaint = Paint()..color = red;

    final labelStyle = TextStyle(
      fontSize: 11,
      fontWeight: FontWeight.w800,
      color: labelColor,
    );
    final valueStyle = TextStyle(
      fontSize: 11,
      fontWeight: FontWeight.w900,
      color: labelColor.withValues(alpha: 0.95),
    );

    // Subtle grid lines (0%, 50%, 100%).
    final gridPaint = Paint()
      ..color = track.withValues(alpha: 0.55)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;
    for (final frac in const [0.0, 0.5, 1.0]) {
      final y = padTop + chartH * (1 - frac);
      canvas.drawLine(Offset(padH, y), Offset(w - padH, y), gridPaint);
    }

    for (int i = 0; i < n; i++) {
      final t = total[i];
      final c = correct[i].clamp(0, t == 0 ? 0 : t);
      final pct = t == 0 ? 0.0 : (c / t);
      final valueH = chartH * pct;

      final left = padH + i * slot + (slot - barW) / 2;

      final rTrack = RRect.fromRectAndRadius(
        Rect.fromLTWH(left, padTop, barW, chartH),
        const Radius.circular(999),
      );
      canvas.drawRRect(rTrack, trackPaint);

      if (t > 0) {
        final rValue = RRect.fromRectAndRadius(
          Rect.fromLTWH(left, (padTop + chartH) - valueH, barW, valueH),
          const Radius.circular(999),
        );
        final ok = (pct * 100) >= 60;
        canvas.drawRRect(rValue, ok ? greenPaint : redPaint);

        // Value label on top
        final valueTp = TextPainter(
          text: TextSpan(text: '%${(pct * 100).round()}', style: valueStyle),
          textDirection: TextDirection.ltr,
        )..layout(maxWidth: slot);
        valueTp.paint(
          canvas,
          Offset(
            padH + i * slot + (slot - valueTp.width) / 2,
            (padTop + chartH) - valueH - 16,
          ),
        );
      }

      final tp = TextPainter(
        text: TextSpan(text: labels[i], style: labelStyle),
        textDirection: TextDirection.ltr,
      )..layout(maxWidth: slot);
      tp.paint(canvas, Offset(padH + i * slot + (slot - tp.width) / 2, size.height - padBottom + 6));
    }
  }

  @override
  bool shouldRepaint(covariant _BarChartPainter oldDelegate) {
    return oldDelegate.labels != labels ||
        oldDelegate.correct != correct ||
        oldDelegate.total != total ||
        oldDelegate.green != green ||
        oldDelegate.red != red ||
        oldDelegate.track != track ||
        oldDelegate.labelColor != labelColor;
  }
}


