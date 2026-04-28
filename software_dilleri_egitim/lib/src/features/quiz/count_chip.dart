import 'package:flutter/material.dart';

class CountChip extends StatelessWidget {
  final String label;
  final bool enabled;
  final VoidCallback onTap;

  const CountChip({
    super.key,
    required this.label,
    required this.enabled,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return ActionChip(
      label: Text(label),
      onPressed: enabled ? onTap : null,
    );
  }
}

