import 'package:flutter/material.dart';

import 'features/auth/auth_gate.dart';
import 'features/shell/app_shell.dart';
import 'theme/app_theme.dart';

class App extends StatelessWidget {
  const App({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Yazılım Dilleri Eğitim',
      theme: AppTheme.dark(),
      darkTheme: AppTheme.dark(),
      themeMode: ThemeMode.dark,
      home: const AuthGate(app: AppShell()),
    );
  }
}

