"""
Mobile skill: Flutter/Dart patterns for enterprise mobile apps.
Covers Riverpod state management, Freezed data classes, GoRouter navigation,
secure storage, and platform-specific considerations.
"""

FLUTTER_SCREEN_TEMPLATE = '''
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:freezed_annotation/freezed_annotation.dart';

part 'user_profile_screen.freezed.dart';

class UserProfileScreen extends ConsumerWidget {
  const UserProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // 1. Get route arguments
    final args = ModalRoute.of(context)?.settings.arguments as Map<String, dynamic>?;
    final userId = args?['userId'] as String?;

    if (userId == null) {
      return const Scaffold(
        body: Center(child: Text('User ID required')),
      );
    }

    // 2. Watch providers for reactive state
    final userAsync = ref.watch(userProvider(userId));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Profile'),
        actions: [
          if (userAsync.value != null)
            IconButton(
              icon: const Icon(Icons.edit),
              onPressed: () => _showEditDialog(context, ref, userAsync.value!),
            ),
        ],
      ),
      body: userAsync.when(
        data: (user) => _buildContent(user, ref),
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (err, stack) => _buildError(err),
      ),
    );
  }

  Widget _buildContent(User user, WidgetRef ref) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Avatar with cached network image
          CircleAvatar(
            radius: 50,
            backgroundImage: NetworkImage(user.avatarUrl),
            onBackgroundImageError: (exception, stackTrace) {
              // Fallback to placeholder
            },
          ),
          const SizedBox(height: 16),

          // Name
          Text(
            user.name,
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 8),

          // Email
          Text(
            user.email,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              color: Colors.grey[600],
            ),
          ),
          const SizedBox(height: 24),

          // Stats row
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              _buildStat('Projects', user.projectCount.toString()),
              _buildStat('Tasks', user.taskCount.toString()),
              _buildStat('Joined', _formatDate(user.createdAt)),
            ],
          ),

          const Divider(height: 32),

          // Actions
          _buildActionTile(
            icon: Icons.settings,
            label: 'Settings',
            onTap: () => Navigator.pushNamed(context, '/settings'),
          ),
          _buildActionTile(
            icon: Icons.notifications,
            label: 'Notifications',
            onTap: () {},
          ),
          _buildActionTile(
            icon: Icons.help,
            label: 'Help & Support',
            onTap: () {},
          ),
        ],
      ),
    );
  }

  Widget _buildError(Object err) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.error_outline, color: Colors.red, size: 48),
          const SizedBox(height: 16),
          Text(
            'Failed to load user',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          Text(
            err.toString(),
            style: Theme.of(context).textTheme.bodySmall,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 16),
          ElevatedButton(
            onPressed: () {},
            child: const Text('Retry'),
          ),
        ],
      ),
    );
  }

  Widget _buildStat(String label, String value) {
    return Column(
      children: [
        Text(
          value,
          style: Theme.of(context).textTheme.headlineMedium?.copyWith(
            fontWeight: FontWeight.bold,
          ),
        ),
        Text(
          label,
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
            color: Colors.grey[600],
          ),
        ),
      ],
    );
  }

  Widget _buildActionTile({
    required IconData icon,
    required String label,
    required VoidCallback onTap,
  }) {
    return ListTile(
      leading: Icon(icon),
      title: Text(label),
      trailing: const Icon(Icons.chevron_right),
      onTap: onTap,
    );
  }

  void _showEditDialog(BuildContext context, WidgetRef ref, User user) {
    final nameController = TextEditingController(text: user.name);

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Edit Profile'),
        content: TextField(
          controller: nameController,
          decoration: const InputDecoration(labelText: 'Name'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () async {
              final success = await ref.read(userProvider(userId).notifier).updateName(
                nameController.text,
              );
              if (context.mounted) {
                Navigator.pop(context);
                if (success) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Profile updated')),
                  );
                }
              }
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
  }

  String _formatDate(DateTime date) {
    return '${date.day}/${date.month}/${date.year}';
  }
}
'''

FLUTTER_PROVIDER_PATTERN = '''
import 'package:riverpod/riverpod.dart';
import 'package:dio/dio.dart';
import 'package:freezed_annotation/freezed_annotation.dart';

part 'user_provider.freezed.dart';

// 1. State definition with Freezed
@freezed
class UserState with _$UserState {
  const factory UserState.initial() = _Initial;
  const factory UserState.loading() = _Loading;
  const factory UserState.data(User user) = _Data;
  const factory UserState.error(String message) = _Error;
}

// 2. StateNotifier for business logic
class UserNotifier extends StateNotifier<UserState> {
  final Dio _dio;
  final String? _userId;

  UserNotifier(this._dio, this._userId) : super(const UserState.initial()) {
    if (_userId != null) {
      fetchUser();
    }
  }

  Future<void> fetchUser() async {
    if (_userId == null) return;

    state = const UserState.loading();
    try {
      final response = await _dio.get('/users/${_userId}');
      final user = User.fromJson(response.data);
      state = UserState.data(user);
    } catch (e, stack) {
      state = UserState.error(e.toString());
    }
  }

  Future<bool> updateName(String name) async {
    final currentState = state;
    if (currentState is! _Data) return false;

    try {
      await _dio.patch('/users/${_userId}', data: {'name': name});
      final updated = (currentState.user).copyWith(name: name);
      state = UserState.data(updated);
      return true;
    } catch (e) {
      state = UserState.error(e.toString());
      return false;
    }
  }
}

// 3. Provider definition
final userProvider = StateNotifierProvider.autoDispose<
  UserNotifier,
  UserState
>((ref) {
  final dio = ref.watch(dioProvider);
  final userId = ref.watch(selectedUserIdProvider).value;
  return UserNotifier(dio, userId);
});

// 4. Dio provider with interceptors
final dioProvider = Provider<Dio>((ref) {
  final dio = Dio(
    BaseOptions(
      baseUrl: const String.fromEnvironment('API_BASE_URL', defaultValue: 'http://localhost:8000'),
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 30),
    ),
  );

  // Auth interceptor
  dio.interceptors.add(
    InterceptorsWrapper(
      onRequest: (options, handler) async {
        final prefs = await SharedPreferences.getInstance();
        final token = prefs.getString('access_token');
        if (token != null) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        return handler.next(options);
      },
      onError: (error, handler) async {
        if (error.response?.statusCode == 401) {
          // Refresh token logic
          final newToken = await _refreshToken();
          if (newToken != null) {
            error.requestOptions.headers['Authorization'] = 'Bearer $newToken';
            final retry = Dio().fetch(error.requestOptions);
            return handler.resolve(retry);
          }
        }
        return handler.next(error);
      },
    ),
  );

  return dio;
});
'''

FLUTTER_DATA_MODELS = '''
import 'package:freezed_annotation/freezed_annotation.dart';

part 'user_model.freezed.dart';
part 'user_model.g.dart';

@freezed
class User with _$User {
  const factory User({
    required String id,
    required String email,
    required String name,
    @Default('') String avatarUrl,
    @Default(0) int projectCount,
    @Default(0) int taskCount,
    @JsonKey(name: 'created_at') required DateTime createdAt,
    @JsonKey(name: 'updated_at') DateTime? updatedAt,
  }) = _User;

  factory User.fromJson(Map<String, dynamic> json) => _$UserFromJson(json);
}

// Usage: final user = User.fromJson(jsonMap);
// Copy with: final updated = user.copyWith(name: 'New Name');
'''

FLUTTER_SECURE_STORAGE = '''
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SecureStorage {
  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(
      encryptedSharedPreferences: true,  // Android 6+ hardware-backed
    ),
    iOptions: IOSOptions(
      accessibility: KeychainAccessibility.first_unlock,  // Available after device unlock
    ),
  );

  static Future<void> saveToken(String accessToken, String refreshToken) async {
    await _storage.write(key: 'access_token', value: accessToken);
    await _storage.write(key: 'refresh_token', value: refreshToken);
  }

  static Future<String?> getAccessToken() async {
    return await _storage.read(key: 'access_token');
  }

  static Future<void> clearAll() async {
    await _storage.deleteAll();
  }
}

// NEVER use SharedPreferences for tokens — they are plaintext on disk!
'''

FLUTTER_OFFLINE_SUPPORT = '''
import 'package:hive/hive.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:riverpod/riverpod.dart';

// 1. Hive setup (local NoSQL storage)
Future<void> initHive() async {
  await Hive.initFlutter();
  Hive.registerAdapter(UserAdapter());  // Generated from @HiveType
  await Hive.openBox<User>('users_cache');
}

// 2. Offline queue for mutations
class OfflineQueue {
  static const _queueBox = 'offline_queue';

  static Future<void> enqueue(OfflineAction action) async {
    final box = await Hive.openBox(_queueBox);
    await box.add(action.toJson());
  }

  static Future<List<OfflineAction>> getPending() async {
    final box = await Hive.openBox(_queueBox);
    return box.values.map((json) => OfflineAction.fromJson(json)).toList();
  }

  static Future<void> clear() async {
    final box = await Hive.openBox(_queueBox);
    await box.clear();
  }
}

// 3. Sync service
class SyncService {
  final Dio dio;
  final Box offlineBox;

  SyncService(this.dio, this.offlineBox);

  Future<void> syncPendingActions() async {
    final actions = await OfflineQueue.getPending();

    for (final action in actions) {
      try {
        await dio.post('/sync/${action.type}', data: action.payload);
        await OfflineQueue.clear();  // Remove after successful sync
      } catch (e) {
        // Keep in queue, will retry later
        break;  // Stop on first failure to preserve order
      }
    }
  }
}

// 4. Connectivity detection
final connectivityProvider = StreamProvider<ConnectivityResult>((ref) async* {
  final connectivity = Connectivity();
  yield* connectivity.onConnectivityChanged.map((results) => results.first);
});
'''

FLUTTER_PUBSPEC_ESSENTIALS = '''
name: myapp
description: Enterprise Flutter App
publish_to: 'none'
version: 1.0.0+1

environment:
  sdk: '>=3.3.0 <4.0.0'

dependencies:
  flutter:
    sdk: flutter

  # State management
  flutter_riverpod: ^2.4.9
  riverpod_annotation: ^2.3.0

  # Networking
  dio: ^5.3.3
  retrofit: ^4.0.1

  # Local storage
  flutter_secure_storage: ^9.0.0
  hive: ^2.2.3
  hive_flutter: ^1.1.0
  shared_preferences: ^2.2.2

  # UI components
  flutter_screenutil: ^5.9.0  # Responsive sizing
  cached_network_image: ^3.3.0
  shimmer: ^2.0.0  # Loading skeletons

  # Form validation
  freezed: ^2.4.5
  json_annotation: ^4.8.1

  # Navigation
  go_router: ^12.1.3

  # Utils
  intl: ^0.18.1
  connectivity_plus: ^5.0.2

dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: ^3.0.0
  build_runner: ^2.4.7
  freezed: ^2.4.5
  riverpod_generator: ^2.3.9
  hive_generator: ^2.0.1

flutter:
  uses-material-design: true
'''

FLUTTER_ERROR_HANDLING = '''
// Error boundary widget
class ErrorBoundary extends StatefulWidget {
  final Widget child;
  const ErrorBoundary({super.key, required this.child});

  @override
  State<ErrorBoundary> createState() => _ErrorBoundaryState();
}

class _ErrorBoundaryState extends State<ErrorBoundary> {
  Object? _error;
  StackTrace? _stackTrace;

  @override
  void initState() {
    super.initState();
    FlutterError.onError = (details) {
      setState(() {
        _error = details.exception;
        _stackTrace = details.stack;
      });
      // Report to Sentry
      // Sentry.captureException(details.exception, stackTrace: details.stack);
    };
  }

  @override
  Widget build(BuildContext context) {
    if (_error != null) {
      return ErrorScreen(
        error: _error!.toString(),
        onRetry: () => setState(() {
          _error = null;
          _stackTrace = null;
        }),
      );
    }
    return widget.child;
  }
}

// Global error handler
void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runZonedGuarded(
    () => runApp(
      const ProviderScope(
        child: ErrorBoundary(
          child: MyApp(),
        ),
      ),
    ),
    (error, stack) {
      // Catch unhandled async errors
      // Log to Sentry
    },
  );
}
'''

FLUTTER_PERFORMANCE_OPTIMIZATION = [
    "Use const constructors for static widgets (reduces rebuild cost)",
    "Avoid rebuilds: use const, Consumer with isolated scope, select() for granular updates",
    "List performance: use ListView.builder (not Column with children) for >20 items",
    "Image optimization: cache_network_image with placeholder, resize on server",
    "Reduce widget tree depth: flatten, use const where possible",
    "Avoid anonymous functions in build() — extract to methods or use callbacks",
    "Use RepaintBoundary for complex animations to isolate repaints",
    "Debounce/throttle search inputs (300-500ms delay)",
    "Lazy-load heavy screens: use AutoRoute/GoRouter with lazy: true",
    "Profile with Flutter DevTools: check widget rebuild count, GPU thread time",
]

FLUTTER_TESTING_STRATEGY = {
    "unit_tests": "Test business logic, providers, utilities (no WidgetTester)",
    "widget_tests": "Test single widget rendering, user interactions",
    "integration_tests": "Test full screens, navigation, API mocks",
    "golden_tests": "Visual regression testing for UI components",
    "tools": [
        "flutter_test (built-in)",
        "flutter_gherkin (BDD)",
        "integration_test (full app tests)",
        "mocktail/mockito for mocking",
    ],
}

FLUTTER_BUILD_CONFIGURATIONS = {
    "dev": {
        "dart-define": "--dart-define=ENVIRONMENT=development",
        "flavor": "development",
        "api_url": "https://dev-api.example.com",
    },
    "staging": {
        "dart-define": "--dart-define=ENVIRONMENT=staging",
        "flavor": "staging",
        "api_url": "https://staging-api.example.com",
    },
    "prod": {
        "dart-define": "--dart-define=ENVIRONMENT=production",
        "flavor": "production",
        "api_url": "https://api.example.com",
        "obfuscate": True,
        "split_debug_info": True,
    },
}

FLUTTER_APP_STORE_SUBMISSION = {
    "ios": {
        "证书管理": "Apple Developer Program, distribution certificate, App Store Connect API key",
        "config": "Update ios/Runner/Info.plist: bundle version, display name, permissions",
        "build": "flutter build ios --release --no-codesign (then Xcode archive)",
        "testflight": "Upload to TestFlight for beta testing (100 external testers)",
        "app_store": "Submit via App Store Connect, fill screenshots (6.7`, 5.5`, iPad), keywords",
    },
    "android": {
        "keystore": "Generate keystore: keytool -genkey -v -keystore upload.jks",
        "config": "android/app/build.gradle: versionCode, versionName, keystore config",
        "build": "flutter build appbundle --release",
        "play_console": "Upload AAB, complete store listing, content rating, pricing",
        "internal_test": "Internal testing track (up to 100 testers)",
    },
}

FLUTTER_SECURITY_BEST_PRACTICES = [
    "Use HTTPS only — ATS configuration in Info.plist, network security config in Android",
    "Certificate pinning for sensitive API calls (dio certificatePinner)",
    "Never store tokens in SharedPreferences — use flutter_secure_storage",
    "Root/jailbreak detection for high-security apps (jailbreak_monitor)",
    "Obfuscate Dart code in production: flutter build --obfuscate --split-debug-info",
    "Validate all user input (even from API) before rendering",
    "Code signing verification: prevent tampering with package signature",
    "Use ProGuard/R8 for Android native code shrinking and obfuscation",
    "Encrypt local databases (SQLCipher for Hive if needed)",
    "Enable Android API level 23+ (runtime permissions)",
]

FLUTTER_ACCESSIBILITY = [
    "Semantics widget for screen readers (semantic label on buttons)",
    "Minimum target size 44x44 logical pixels for touch targets",
    "Dynamic type support: use TextTheme, not hardcoded font sizes",
    "Color contrast ratio >= 4.5:1 for normal text, 3:1 for large",
    "Focus order: logical tab order, focusable widgets visible",
    "Screen reader navigation: group related elements with Semantics",
    "High contrast mode: test with accessibility inspector",
    "Reduce motion: respect system settings for animations",
]
