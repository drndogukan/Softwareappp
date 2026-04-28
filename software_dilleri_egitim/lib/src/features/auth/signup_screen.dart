import 'package:flutter/material.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:cloud_firestore/cloud_firestore.dart';

class SignupScreen extends StatefulWidget {
  const SignupScreen({super.key});

  @override
  State<SignupScreen> createState() => _SignupScreenState();
}

class _SignupScreenState extends State<SignupScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _password2 = TextEditingController();

  bool _busy = false;
  bool _hide = true;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _password2.dispose();
    super.dispose();
  }

  Future<void> _signUp() async {
    if (_busy) return;
    final p1 = _password.text.trim();
    final p2 = _password2.text.trim();
    if (p1.isEmpty || p2.isEmpty || p1 != p2) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Şifreler aynı olmalı.')),
      );
      return;
    }

    setState(() => _busy = true);
    try {
      final cred = await FirebaseAuth.instance.createUserWithEmailAndPassword(
        email: _email.text.trim(),
        password: p1,
      );
      final user = cred.user;
      if (user != null) {
        await FirebaseFirestore.instance.collection('users').doc(user.uid).set(
          {
            'uid': user.uid,
            'email': user.email,
            'displayName': user.displayName,
            'photoURL': user.photoURL,
            'providerIds': user.providerData.map((p) => p.providerId).toList(),
            'createdAt': FieldValue.serverTimestamp(),
            'lastSignInAt': FieldValue.serverTimestamp(),
          },
          SetOptions(merge: true),
        );
      }
    } on FirebaseAuthException catch (e) {
      if (!mounted) return;
      setState(() => _busy = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.message ?? 'Kayıt başarısız.')),
      );
      return;
    } catch (_) {
      if (!mounted) return;
      setState(() => _busy = false);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Kayıt başarısız.')),
      );
      return;
    }
    if (!mounted) return;
    setState(() => _busy = false);
    Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Kayıt Ol')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                children: [
                  TextField(
                    controller: _email,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(
                      labelText: 'E-posta',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: _password,
                    obscureText: _hide,
                    decoration: InputDecoration(
                      labelText: 'Şifre',
                      border: const OutlineInputBorder(),
                      suffixIcon: IconButton(
                        onPressed: () => setState(() => _hide = !_hide),
                        icon: Icon(_hide ? Icons.visibility : Icons.visibility_off),
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: _password2,
                    obscureText: _hide,
                    decoration: const InputDecoration(
                      labelText: 'Şifre (tekrar)',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton(
                      onPressed: _busy ? null : _signUp,
                      child: _busy
                          ? const SizedBox(
                              height: 18,
                              width: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('Kayıt Ol'),
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 10),
        ],
      ),
    );
  }
}

