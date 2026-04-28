import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:software_dilleri_egitim/src/app.dart';

void main() {
  testWidgets('MaterialApp yuklenir', (WidgetTester tester) async {
    await tester.pumpWidget(const App());
    await tester.pump();
    expect(find.byType(MaterialApp), findsOneWidget);
  });
}
