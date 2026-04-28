import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:sign_in_with_apple/sign_in_with_apple.dart';
import 'package:flutter/foundation.dart';

import 'forgot_password_screen.dart';
import 'signup_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();

  bool _busy = false;
  bool _hide = true;

  Future<void> _upsertUserDoc(User user) async {
    final ref = FirebaseFirestore.instance.collection('users').doc(user.uid);
    await ref.set(
      {
        'uid': user.uid,
        'email': user.email,
        'displayName': user.displayName,
        'photoURL': user.photoURL,
        'providerIds': user.providerData.map((p) => p.providerId).toList(),
        'lastSignInAt': FieldValue.serverTimestamp(),
      },
      SetOptions(merge: true),
    );
  }

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _signIn() async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final cred = await FirebaseAuth.instance.signInWithEmailAndPassword(
        email: _email.text.trim(),
        password: _password.text,
      );
      final user = cred.user;
      if (user != null) await _upsertUserDoc(user);
    } on FirebaseAuthException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.message ?? 'Giriş başarısız.')),
      );
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Giriş başarısız.')),
      );
    }
    if (!mounted) return;
    setState(() => _busy = false);
  }

  Future<void> _google() async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final googleUser = await GoogleSignIn().signIn();
      if (googleUser == null) {
        setState(() => _busy = false);
        return;
      }
      final googleAuth = await googleUser.authentication;
      final credential = GoogleAuthProvider.credential(
        accessToken: googleAuth.accessToken,
        idToken: googleAuth.idToken,
      );
      final cred = await FirebaseAuth.instance.signInWithCredential(credential);
      final user = cred.user;
      if (user != null) await _upsertUserDoc(user);
    } on FirebaseAuthException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.message ?? 'Google ile giriş başarısız.')),
      );
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Google ile giriş başarısız.')),
      );
    }
    if (!mounted) return;
    setState(() => _busy = false);
  }

  Future<void> _apple() async {
    final isApplePlatform =
        defaultTargetPlatform == TargetPlatform.iOS ||
        defaultTargetPlatform == TargetPlatform.macOS;
    if (!isApplePlatform) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Apple ile giriş iOS/macOS için aktif.')),
      );
      return;
    }
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final appleCred = await SignInWithApple.getAppleIDCredential(
        scopes: [
          AppleIDAuthorizationScopes.email,
          AppleIDAuthorizationScopes.fullName,
        ],
      );
      final oauth = OAuthProvider('apple.com').credential(
        idToken: appleCred.identityToken,
        accessToken: appleCred.authorizationCode,
      );
      final cred = await FirebaseAuth.instance.signInWithCredential(oauth);
      final user = cred.user;
      if (user != null) await _upsertUserDoc(user);
    } on FirebaseAuthException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.message ?? 'Apple ile giriş başarısız.')),
      );
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Apple ile giriş başarısız.')),
      );
    }
    if (!mounted) return;
    setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520),
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                const SizedBox(height: 12),
                Text(
                  'Giriş Yap',
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                        fontWeight: FontWeight.w900,
                      ),
                ),
                const SizedBox(height: 6),
                Text(
                  'Devam etmek için hesabınla giriş yap.',
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: scheme.onSurface.withValues(alpha: 0.70),
                      ),
                ),
                const SizedBox(height: 16),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(14),
                    child: Column(
                      children: [
                        TextField(
                          controller: _email,
                          keyboardType: TextInputType.emailAddress,
                          autofillHints: const [AutofillHints.email],
                          decoration: const InputDecoration(
                            labelText: 'E-posta',
                            border: OutlineInputBorder(),
                          ),
                        ),
                        const SizedBox(height: 10),
                        TextField(
                          controller: _password,
                          obscureText: _hide,
                          autofillHints: const [AutofillHints.password],
                          decoration: InputDecoration(
                            labelText: 'Şifre',
                            border: const OutlineInputBorder(),
                            suffixIcon: IconButton(
                              onPressed: () => setState(() => _hide = !_hide),
                              icon: Icon(_hide ? Icons.visibility : Icons.visibility_off),
                            ),
                          ),
                        ),
                        const SizedBox(height: 8),
                        SizedBox(
                          width: double.infinity,
                          child: FilledButton(
                            onPressed: _busy ? null : _signIn,
                            child: _busy
                                ? const SizedBox(
                                    height: 18,
                                    width: 18,
                                    child: CircularProgressIndicator(strokeWidth: 2),
                                  )
                                : const Text('Giriş Yap'),
                          ),
                        ),
                        const SizedBox(height: 6),
                        Row(
                          children: [
                            TextButton(
                              onPressed: _busy
                                  ? null
                                  : () {
                                      Navigator.of(context).push(
                                        MaterialPageRoute(
                                          builder: (_) => const ForgotPasswordScreen(),
                                        ),
                                      );
                                    },
                              child: const Text('Şifremi unuttum'),
                            ),
                            const Spacer(),
                            TextButton(
                              onPressed: _busy
                                  ? null
                                  : () async {
                                      final changed = await Navigator.of(context).push<bool>(
                                        MaterialPageRoute(
                                          builder: (_) => const SignupScreen(),
                                        ),
                                      );
                                      if (!context.mounted) return;
                                      if (changed == true) Navigator.of(context).pop();
                                    },
                              child: const Text('Kayıt Ol'),
                            ),
                          ],
                        ),
                        const Divider(height: 22),
                        SizedBox(
                          width: double.infinity,
                          child: OutlinedButton.icon(
                            onPressed: _busy ? null : _google,
                            icon: const FaIcon(FontAwesomeIcons.google),
                            label: const Text('Google ile giriş'),
                          ),
                        ),
                        const SizedBox(height: 10),
                        SizedBox(
                          width: double.infinity,
                          child: OutlinedButton.icon(
                            onPressed: _busy ? null : _apple,
                            icon: const FaIcon(FontAwesomeIcons.apple),
                            label: const Text('Apple ile giriş'),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 12),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

