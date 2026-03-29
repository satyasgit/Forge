"""
Mobile skill: Kotlin patterns for Android development (Jetpack Compose + Coroutines).
Covers modern Android architecture, Material Design 3, Hilt DI, and Play Store submission.
"""

KOTLIN_COMPOSE_SCREEN_TEMPLATE = '''
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import org.koin.androidx.compose.get

@Composable
fun UserProfileScreen(
  viewModel: UserProfileViewModel = get(),
  userId: String,
  onNavigateBack: () -> Unit,
) {
  val state by viewModel.uiState.collectAsStateWithLifecycle()

  Scaffold(
    topBar = {
      TopAppBar(
        title = { Text("Profile") },
        actions = {
          if (state is UserState.Success) {
            IconButton(onClick = { viewModel.showEditSheet = true }) {
              Icon(Icons.Default.Edit, contentDescription = "Edit")
            }
          }
        },
      )
    }
  ) { paddingValues ->
    Box(
      modifier = Modifier
        .fillMaxSize()
        .padding(paddingValues)
    ) {
      when (val s = state) {
        is UserState.Loading -> {
          CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
        }
        is UserState.Error -> {
          ErrorContent(
            message = s.message,
            onRetry = { viewModel.loadUser(userId) }
          )
        }
        is UserState.Success -> {
          UserContent(
            user = s.user,
            onUpdateName = { newName ->
              viewModel.updateName(newName)
            }
          )
        }
        else -> {}
      }
    }
  }

  if (viewModel.showEditSheet) {
    EditProfileBottomSheet(
      viewModel = viewModel,
      onDismiss = { viewModel.showEditSheet = false }
    )
  }
}

@Composable
fun UserContent(user: User, onUpdateName: (String) -> Unit) {
  Column(
    modifier = Modifier
      .fillMaxWidth()
      .padding(16.dp),
    horizontalAlignment = Alignment.CenterHorizontally,
  ) {
    // Avatar with Coil image loading
    AsyncImage(
      model = user.avatarUrl,
      contentDescription = "Profile picture",
      modifier = Modifier
        .size(100.dp)
        .clip(CircleShape),
      error = painterResource(id = R.drawable.ic_avatar_placeholder),
    )

    Spacer(modifier = Modifier.height(16.dp))

    Text(
      text = user.name,
      style = MaterialTheme.typography.headlineMedium,
    )

    Text(
      text = user.email,
      style = MaterialTheme.typography.bodyMedium,
      color = MaterialTheme.colorScheme.onSurfaceVariant,
    )

    Spacer(modifier = Modifier.height(24.dp))

    // Stats
    Row(
      modifier = Modifier.fillMaxWidth(),
      horizontalArrangement = Arrangement.SpaceEvenly,
    ) {
      StatColumn(label = "Projects", value = user.projectCount.toString())
      StatColumn(label = "Tasks", value = user.taskCount.toString())
      StatColumn(label = "Joined", value = formatDate(user.createdAt))
    }

    Spacer(modifier = Modifier.height(32.dp))

    // Actions list
    ActionList(
      actions = listOf(
        ActionItem(
          icon = Icons.Default.Settings,
          label = "Settings",
          onClick = { /* navigate to settings */ }
        ),
        ActionItem(
          icon = Icons.Default.Notifications,
          label = "Notifications",
          onClick = { /* open notifications */ }
        ),
        ActionItem(
          icon = Icons.Default.Logout,
          label = "Sign Out",
          onClick = { viewModel.signOut() },
          destructive = true
        ),
      )
    )
  }
}

@Composable
fun StatColumn(label: String, value: String) {
  Column(horizontalAlignment = Alignment.CenterHorizontally) {
    Text(
      text = value,
      style = MaterialTheme.typography.titleLarge,
      fontWeight = FontWeight.Bold,
    )
    Text(
      text = label,
      style = MaterialTheme.typography.bodySmall,
      color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
  }
}

@Composable
fun ActionItem(
  icon: ImageVector,
  label: String,
  onClick: () -> Unit,
  destructive: Boolean = false,
) {
  ListItem(
    headlineContent = { Text(label) },
    leadingContent = {
      Icon(
        icon,
        contentDescription = null,
        tint = if (destructive) MaterialTheme.colorScheme.error
               else MaterialTheme.colorScheme.primary
      )
    },
    trailingContent = {
      Icon(Icons.Default.ChevronRight, contentDescription = null)
    },
    colors = ListItemDefaults.colors(
      headlineColor = if (destructive) MaterialTheme.colorScheme.error
                     else MaterialTheme.colorScheme.onSurface,
    ),
    modifier = Modifier.fillMaxWidth().clickable(onClick = onClick)
  )
}

@Composable
fun ErrorContent(message: String, onRetry: () -> Unit) {
  Column(
    modifier = Modifier.fillMaxSize(),
    horizontalAlignment = Alignment.CenterHorizontally,
    verticalArrangement = Arrangement.Center,
  ) {
    Icon(
      Icons.Default.ErrorOutline,
      contentDescription = null,
      modifier = Modifier.size(64.dp),
      tint = MaterialTheme.colorScheme.error,
    )
    Spacer(modifier = Modifier.height(16.dp))
    Text("Something went wrong", style = MaterialTheme.typography.titleMedium)
    Spacer(modifier = Modifier.height(8.dp))
    Text(message, style = MaterialTheme.typography.bodyMedium)
    Spacer(modifier = Modifier.height(16.dp))
    Button(onClick = onRetry) {
      Text("Retry")
    }
  }
}
'''

KOTLIN_VIEWMODEL_PATTERN = '''
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import javax.inject.Inject
import dagger.hilt.android.lifecycle.HiltViewModel

@HiltViewModel
class UserProfileViewModel @Inject constructor(
  private val userRepository: UserRepository,
  private val authRepository: AuthRepository,
) : ViewModel() {

  // 1. UI state sealed class
  private val _uiState = MutableStateFlow<UserState>(UserState.Initial)
  val uiState: StateFlow<UserState> = _uiState.asStateFlow()

  // 2. Side effects (events) via SharedFlow
  private val _event = MutableSharedFlow<UserEvent>()
  val event: SharedFlow<UserEvent> = _event.asSharedFlow()

  // 3. Derived state (computed)
  val isFormValid: StateFlow<Boolean> = _uiState
    .filterIsInstance<UserState.Success>()
    .map { state ->
      state.user.name.isNotBlank() && state.user.email.contains("@")
    }
    .stateIn(
      scope = viewModelScope,
      started = SharingStarted.WhileSubscribed(5000),
      initialValue = false
    )

  var showEditSheet by mutableStateOf(false)
    private set

  // 4. Public methods
  fun loadUser(userId: String) {
    viewModelScope.launch {
      _uiState.value = UserState.Loading
      try {
        val user = userRepository.getUser(userId)
        _uiState.value = UserState.Success(user)
      } catch (e: Exception) {
        _uiState.value = UserState.Error(e.message ?: "Unknown error")
      }
    }
  }

  fun updateName(newName: String) {
    val currentState = _uiState.value
    if (currentState !is UserState.Success) return

    viewModelScope.launch {
      try {
        val updated = userRepository.updateUser(currentState.user.id, mapOf("name" to newName))
        _uiState.value = UserState.Success(updated)
        showEditSheet = false
        _event.emit(UserEvent.ShowSnackbar("Profile updated"))
      } catch (e: Exception) {
        _event.emit(UserEvent.ShowSnackbar("Failed to update: ${e.message}"))
      }
    }
  }

  fun signOut() {
    viewModelScope.launch {
      authRepository.signOut()
      // Navigate to login screen handled by navigation layer
    }
  }

  fun formatDate(date: Instant): String {
    return DateTimeFormatter.ofPattern("MMM d, yyyy")
      .withZone(ZoneId.systemDefault())
      .format(date)
  }

  fun onEditSheetDismissed() {
    showEditSheet = false
  }
}

// 5. State sealed class
sealed class UserState {
  object Initial : UserState()
  object Loading : UserState()
  data class Success(val user: User) : UserState()
  data class Error(val message: String) : UserState()
}

// 6. One-off events
sealed class UserEvent {
  data class ShowSnackbar(val message: String) : UserEvent()
  data class Navigate(val route: String) : UserEvent()
}

// 7. Domain model
data class User(
  val id: String,
  val email: String,
  val name: String,
  val avatarUrl: String?,
  val projectCount: Int,
  val taskCount: Int,
  val createdAt: Instant,
)
'''

KOTLIN_REPOSITORY_PATTERN = '''
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Singleton
class UserRepository @Inject constructor(
  private val api: ApiService,
  private val cache: CacheClient,
  private val db: AppDatabase,
) {

  private val USER_CACHE_KEY = "user_"

  suspend fun getUser(userId: String): User = withContext(Dispatchers.IO) {
    // 1. Check cache first (Redis or in-memory)
    cache.get<User>("$USER_CACHE_KEY$userId")?.let { cached ->
      return@withContext cached
    }

    // 2. Try local DB (offline-first)
    val local = db.userDao().getUser(userId)
    if (local != null) {
      return@withContext local.toDomain()
    }

    // 3. Network fetch
    val remote = api.getUser(userId)
    db.userDao().insert(remote.toEntity())

    // 4. Cache result
    cache.set("$USER_CACHE_KEY$userId", remote, ttl = 3600)

    remote
  }

  suspend fun updateUser(userId: String, updates: Map<String, Any>): User {
    val updated = api.updateUser(userId, updates)
    // Update cache
    cache.set("$USER_CACHE_KEY$userId", updated, ttl = 3600)
    // Update DB
    db.userDao().insert(updated.toEntity())
    // Invalidate list cache
    cache.delete("users_list")
    return updated
  }

  suspend fun getUsers(page: Int, limit: Int): List<User> = withContext(Dispatchers.IO) {
    val cacheKey = "users_list:page=$page:limit=$limit"
    cache.get<List<User>>(cacheKey)?.let { return@withContext it }

    val users = api.getUsers(page, limit)
    cache.set(cacheKey, users, ttl = 300)  // 5 min
    users
  }
}

// Local database with Room
@Database(entities = [UserEntity::class], version = 1)
abstract class AppDatabase : RoomDatabase() {
  abstract fun userDao(): UserDao
}

@Dao
interface UserDao {
  @Query("SELECT * FROM users WHERE id = :userId")
  suspend fun getUser(userId: String): UserEntity?

  @Insert(onConflict = OnConflictStrategy.REPLACE)
  suspend fun insert(user: UserEntity)

  @Query("DELETE FROM users WHERE id = :userId")
  suspend fun delete(userId: String)
}

@Entity(tableName = "users")
data class UserEntity(
  @PrimaryKey val id: String,
  val email: String,
  val name: String,
  val avatarUrl: String?,
  val projectCount: Int,
  val taskCount: Int,
  val createdAt: Instant,
) {
  fun toDomain() = User(
    id = id,
    email = email,
    name = name,
    avatarUrl = avatarUrl,
    projectCount = projectCount,
    taskCount = taskCount,
    createdAt = createdAt,
  )
}
'''

KOTLIN_DEPENDENCY_INJECTION = '''
// build.gradle.kts (app level)
dependencies {
  implementation("com.google.dagger:hilt-android:2.48")
  kapt("com.google.dagger:hilt-android-compiler:2.48")
  implementation("androidx.hilt:hilt-navigation-compose:1.1.0")
}

// AppModule.kt
@Module
@InstallIn(SingletonComponent::class)
object AppModule {

  @Provides
  @Singleton
  fun provideApiService(): ApiService {
    return Retrofit.Builder()
      .baseUrl(BuildConfig.API_BASE_URL)
      .addConverterFactory(MoshiConverterFactory.create())
      .addCallAdapterFactory(CoroutineCallAdapterFactory())
      .build()
      .create(ApiService::class.java)
  }

  @Provides
  @Singleton
  fun provideCacheClient(@ApplicationContext context: Context): CacheClient {
    return CacheClient.Builder(context)
      .defaultExpiration(1, TimeUnit.HOURS)
      .build()
  }

  @Provides
  @Singleton
  fun provideAppDatabase(@ApplicationContext context: Context): AppDatabase {
    return Room.databaseBuilder(
      context,
      AppDatabase::class.java,
      "myapp.db"
    ).build()
  }
}

// Application class
@HiltAndroidApp
class MyApp : Application()

// ViewModel injection (already using @HiltViewModel)
@HiltViewModel
class ProfileViewModel @Inject constructor(
  private val repository: UserRepository,
) : ViewModel() { ... }
'''

KOTLIN_NAVIGATION_PATTERNS = '''
// build.gradle.kts
dependencies {
  implementation("androidx.navigation:navigation-compose:2.7.4")
}

// NavGraph.kt
@Composable
fun NavGraph(
  navController: NavHostController = rememberNavController(),
) {
  NavHost(
    navController = navController,
    startDestination = "profile/{userId}",
  ) {
    // With argument
    composable(
      route = "profile/{userId}",
      arguments = listOf(navArgument("userId") { type = NavType.StringType })
    ) { backStackEntry ->
      val userId = backStackEntry.arguments?.getString("userId") ?: return@composable
      UserProfileScreen(
        viewModel = hiltViewModel<UserProfileViewModel>(),
        userId = userId,
        onNavigateBack = { navController.popBackStack() },
      )
    }

    // Without argument
    composable("settings") {
      SettingsScreen()
    }

    // Nested graph
    navigation(startDestination = "home", route = "main") {
      composable("home") { HomeScreen() }
      composable("dashboard") { DashboardScreen() }
    }
  }
}

// Type-safe navigation with sealed classes
sealed class Screen(val route: String) {
  object Profile : Screen("profile/{userId}") {
    fun createRoute(userId: String) = "profile/$userId"
  }
  object Settings : Screen("settings")
}

// Usage:
navController.navigate(Screen.Profile.createRoute(userId))
'''

KOTLIN_ANDROID_MANIFEST = '''
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
  package="com.example.myapp">

  <!-- Permissions -->
  <uses-permission android:name="android.permission.INTERNET" />
  <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
  <uses-permission android:name="android.permission.CAMERA" />
  <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE"
    android:maxSdkVersion="32" />
  <uses-permission android:name="android.permission.READ_MEDIA_IMAGES" />

  <!-- API level requirements -->
  <uses-sdk
    android:minSdkVersion="24"  // Android 7.0 (87%+ coverage)
    android:targetSdkVersion="34" />  // Always target latest

  <application
    android:name=".MyApp"
    android:label="@string/app_name"
    android:icon="@mipmap/ic_launcher"
    android:roundIcon="@mipmap/ic_launcher_round"
    android:theme="@style/Theme.MyApp"
    android:allowBackup="true"
    android:networkSecurityConfig="@xml/network_security_config">

    <!-- Main activity -->
    <activity
      android:name=".MainActivity"
      android:exported="true"
      android:windowSoftInputMode="adjustResize"
      android:launchMode="singleTop">
      <intent-filter>
        <action android:name="android.intent.action.MAIN" />
        <category android:name="android.intent.category.LAUNCHER" />
      </intent-filter>

      <!-- Deep links -->
      <intent-filter android:autoVerify="true">
        <action android:name="android.intent.action.VIEW" />
        <category android:name="android.intent.category.DEFAULT" />
        <category android:name="android.intent.category.BROWSABLE" />
        <data android:scheme="https" android:host="myapp.com" />
      </intent-filter>
    </activity>

  </application>
</manifest>
'''

KOTLIN_MATERIAL_DESIGN_3 = '''
import androidx.compose.material3.*

@Composable
fun MyAppTheme(content: @Composable () -> Unit) {
  MaterialTheme(
    colorScheme = lightColorScheme(
      primary = md_theme_light_primary,
      onPrimary = md_theme_light_onPrimary,
      secondary = md_theme_light_secondary,
      background = md_theme_light_background,
      surface = md_theme_light_surface,
      onSurface = md_theme_light_onSurface,
    ),
    typography = Typography(
      displayLarge = TextStyle(fontSize = 57.sp, lineHeight = 64.sp),
      headlineMedium = TextStyle(fontSize = 28.sp, lineHeight = 36.sp),
      bodyMedium = TextStyle(fontSize = 16.sp, lineHeight = 24.sp),
    ),
    shapes = Shapes(
      small = RoundedCornerShape(4.dp),
      medium = RoundedCornerShape(8.dp),
      large = RoundedCornerShape(12.dp),
    ),
    content = content,
  )
}

// Dynamic color (Android 12+)
if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
  val dynamicColors = DynamicColors()
  if (dynamicColors.isDynamicColorAvailable()) {
    val palette = dynamicColors.getDynamicColors(context)
    // Use dynamic palette for your color scheme
  }
}

// Dark theme support
val darkColorScheme = darkColorScheme(
  primary = md_theme_dark_primary,
  background = md_theme_dark_background,
  surface = md_theme_dark_surface,
)
'''

KOTLIN_PERFORMANCE_BEST_PRACTICES = [
    "Use Compose compiler metrics to identify unstable composables",
    "Avoid lambda allocations in recomposition — move lambda to remember",
    "Use derivedStateOf for expensive calculations from State",
    "LazyColumn/Grid for lists — not Column with items()",
    "remember() for expensive operations, rememberUpdatedState for closure stability",
    "key parameter in lazy lists for stable identity (not position)",
    "Avoid nested scrolling: use NestedScrollConnection properly",
    "Profile with Android Studio Profiler: CPU, Memory, Network",
    "Reduce overdraw: inspection tool, remove unnecessary backgrounds",
    "Use Baseline Profiles for critical user journeys (perf boost on first launch)",
]

KOTLIN_TESTING_STRATEGY = {
    "unit_tests": "Test ViewModels, Repository, Use Cases with JUnit + MockK",
    "instrumented_tests": "Run on device/emulator with AndroidJUnitRunner",
    "compose_tests": "createAndroidComposeRule, createComposeRule for UI testing",
    "ui_automator": "Cross-app UI testing (permissions dialog, settings)",
    "tools": [
        "JUnit4/5",
        "MockK (mockito alternative for Kotlin)",
        "Turbine (Flow testing)",
        "Compose Testing Library",
    ],
}

KOTLIN_PLAY_STORE_SUBMISSION = {
    "app_bundle": {
        "build_type": "Release with minifyEnabled true (R8/ProGuard)",
        "signing": "Upload keystore (not debug), keep secure",
        "versioning": "versionCode (int, increment), versionName (user-facing: 1.2.3)",
        "bundle_size": "Enable resource shrinking, use R8 full mode, compress PNGs",
    },
    "play_console": {
        "store_listing": "App name (30 char), short description (80), full description (4000)",
        "graphics": "Feature graphic (1024x500), app icon (512x512), screenshots (minimum 2)",
        "content_rating": "Complete questionnaire, age rating",
        "privacy_policy": "URL required for data collection apps",
        "target_audience": "Declare if children's privacy act applies",
        "data_safety": "Disclose data collection, encryption, sharing practices",
    },
    "testing_tracks": {
        "internal": "Up to 100 testers (email or Google Group)",
        "closed": "Up to 2000 testers, email list required",
        "open": "Anyone with link (max 10,000 testers)",
        "production": "After closed testing, staged rollout (1% → 100%)",
    },
    "review_process": {
        "policies": "Check against Developer Program Policies before submission",
        "content": "No placeholder content, no inappropriate content",
        "functionality": "Must not crash, must have core features working",
        "ads": "If showing ads, comply with Ads Policy",
        "common_rejections": [
            "Privacy policy missing",
            "Permissions not justified in privacy policy",
            "Malware or spyware behavior",
            "Intellectual property violation",
        ],
    },
}

KOTLIN_COROUTINES_BEST_PRACTICES = '''
// 1. Use structured concurrency (viewModelScope, lifecycleScope)
// ✅ Good:
viewModelScope.launch {
  val user = repository.getUser()
  // Use user
}

// ❌ Bad:
GlobalScope.launch {  // Unstructured, leaks
  val user = repository.getUser()
}

// 2. Dispatchers
withContext(Dispatchers.IO) {
  // Network or disk I/O
}

withContext(Dispatchers.Default) {
  // CPU-intensive work
}

// Main thread only for UI updates
@MainExecutor
class MyPresenter {
  fun updateUI() {
    // Runs on main thread
  }
}

// 3. Error handling
viewModelScope.launch {
  try {
    val result = repository.getData()
    _uiState.value = Success(result)
  } catch (e: IOException) {
    _uiState.value = Error("Network error")
  } catch (e: HttpException) {
    _uiState.value = Error("Server error: ${e.code()}")
  }
}

// 4. Cancellation
viewModelScope.launch {
  // Long-running operation
  repository.syncAllData()
}.invokeOnCancellation {
  // Cleanup resources
  logger.d("Sync cancelled")
}

// 5. Concurrency (parallel operations)
val (user, posts) = awaitAll(
  async { repository.getUser(userId) },
  async { repository.getPosts(userId) },
)

// 6. Flow operators
repository.userUpdates()
  .filter { it.isActive }
  .map { it.toDomain() }
  .debounce(300)  // Wait for 300ms of no updates
  .distinctUntilChanged()
  .onEach { user ->
    _uiState.value = Success(user)
  }
  .launchIn(viewModelScope)
'''

KOTLIN_SECURITY_PRACTICES = [
    "Never hardcode secrets in source — use BuildConfig fields or NDK",
    "Enable ProGuard/R8 minification and obfuscation for release builds",
    "Use Android Keystore for cryptographic keys (not SharedPreferences)",
    "Root detection: check for su binary, dangerous props, custom ROM indicators",
    "Network Security Config: enforce TLS 1.2+, certificate pinning for sensitive APIs",
    "Biometric authentication: BiometricPrompt API with proper fallback",
    "Check device compatibility: SafetyNet Attestation API for device integrity",
    "Input validation: validate all external data (intents, network) to prevent injection",
    "Exported components: only if necessary, set permissions to restrict access",
    "Logging: no PII in logs, strip in release builds (Timber plant with ReleaseTree)",
]

KOTLIN_RESOURCE_OPTIMIZATION = [
    "Use vector drawables (XML) over PNGs for icons (smaller, scalable)",
    "WebP format for raster images (25-35% smaller than PNG/JPEG)",
    "Compress PNGs with pngcrush, remove unused resources with shrinkResources",
    "Use App Bundles (.aab) not APKs — Play Store delivers device-specific split",
    "Lazy initialization: by lazy {} for expensive objects not needed immediately",
    "Avoid memory leaks: no context in singletons, use WeakReference for listeners",
    "Reuse objects: ObjectPool pattern for frequently created/destroyed objects",
    "Batch database operations — transactions are faster than individual inserts",
    "Use Paging library for large lists (load pages from DB/network)",
    "Profile memory with Android Studio Memory Profiler, detect leaks",
]
