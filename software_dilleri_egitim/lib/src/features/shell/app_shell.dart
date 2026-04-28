import 'package:flutter/material.dart';

import '../dashboard/dashboard_screen.dart';
import '../home/home_screen.dart';
import '../quiz/quiz_hub_screen.dart';
import '../../theme/app_theme.dart';
import '../../data/progress_cloud_sync.dart';

class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int _index = 0;

  final _navKeys = List.generate(3, (_) => GlobalKey<NavigatorState>());

  @override
  void initState() {
    super.initState();
    ProgressCloudSync.instance.ensureStarted();
  }

  Future<bool> _onBackPressed() async {
    final nav = _navKeys[_index].currentState;
    if (nav == null) return true;
    if (nav.canPop()) {
      nav.pop();
      return false;
    }
    return true;
  }

  void _setTab(int next) {
    if (next == _index) {
      _navKeys[next].currentState?.popUntil((r) => r.isFirst);
      return;
    }
    setState(() => _index = next);
  }

  Widget _tabNavigator({
    required GlobalKey<NavigatorState> key,
    required Widget root,
  }) {
    return Navigator(
      key: key,
      onGenerateRoute: (settings) {
        return MaterialPageRoute(builder: (_) => root);
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (_, __) async {
        final shouldPop = await _onBackPressed();
        if (!shouldPop && context.mounted) return;
        if (context.mounted) Navigator.of(context).maybePop();
      },
      child: Scaffold(
        body: IndexedStack(
          index: _index,
          children: [
            _tabNavigator(
              key: _navKeys[0],
              root: const DashboardScreen(),
            ),
            _tabNavigator(
              key: _navKeys[1],
              root: const QuizHubScreen(),
            ),
            _tabNavigator(
              key: _navKeys[2],
              root: HomeScreen(
                onGoQuiz: () => _setTab(1),
              ),
            ),
          ],
        ),
        bottomNavigationBar: Container(
          decoration: BoxDecoration(
            color: AppColors.surface,
            border: Border(
              top: BorderSide(color: scheme.outline.withValues(alpha: 0.35)),
            ),
          ),
          child: SafeArea(
            top: false,
            child: NavigationBar(
              backgroundColor: AppColors.surface,
              indicatorColor: scheme.primary.withValues(alpha: 0.18),
              elevation: 0,
              height: 72,
              selectedIndex: _index,
              onDestinationSelected: _setTab,
              destinations: const [
                NavigationDestination(
                  icon: Icon(Icons.home_outlined),
                  selectedIcon: Icon(Icons.home_rounded),
                  label: 'Ana Sayfa',
                ),
                NavigationDestination(
                  icon: Icon(Icons.terminal_outlined),
                  selectedIcon: Icon(Icons.terminal_rounded),
                  label: 'Compiler',
                ),
                NavigationDestination(
                  icon: Icon(Icons.library_books_outlined),
                  selectedIcon: Icon(Icons.library_books_rounded),
                  label: 'Kütüphane',
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
