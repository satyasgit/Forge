"""
Mobile skill: Swift patterns for iOS development (SwiftUI + Combine/async-await).
Covers modern iOS architecture, security best practices, and App Store submission.
"""

SWIFTUI_VIEW_TEMPLATE = '''
import SwiftUI

struct UserProfileView: View {
  // 1. State and environment
  @StateObject private var viewModel: UserProfileViewModel
  @Environment(\.colorScheme) private var colorScheme
  @Environment(\.dismiss) private var dismiss

  // 2. Init with dependency injection
  init(viewModel: UserProfileViewModel) {
    _viewModel = StateObject(wrappedValue: viewModel)
  }

  var body: some View {
    // 3. Loading state
    if viewModel.isLoading {
      ProgressView()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    } else if let error = viewModel.error {
      // 4. Error state
      ErrorView(error: error) {
        viewModel.loadUser()
      }
    } else if let user = viewModel.user {
      // 5. Main content
      ScrollView {
        VStack(spacing: 16) {
          // Avatar
          AsyncImage(url: URL(string: user.avatarUrl)) { phase in
            switch phase {
            case .empty:
              ProgressView()
            case .success(let image):
              image
                .resizable()
                .scaledToFill()
                .frame(width: 100, height: 100)
                .clipShape(Circle())
            case .failure:
              Image(systemName: "person.crop.circle.fill")
                .font(.system(size: 100))
                .foregroundColor(.gray)
            @unknown default:
              EmptyView()
            }
          }

          // Name
          Text(user.name)
            .font(.title2)
            .fontWeight(.semibold)

          // Email
          Text(user.email)
            .font(.callout)
            .foregroundColor(.secondary)

          Divider()

          // Stats
          HStack(spacing: 32) {
            StatView(label: "Projects", value: "\(user.projectCount)")
            StatView(label: "Tasks", value: "\(user.taskCount)")
            StatView(label: "Joined", value: viewModel.formatDate(user.createdAt))
          }
          .padding(.vertical)

          // Actions
          VStack(spacing: 12) {
            NavigationLink(destination: SettingsView()) {
              LabeledRow(icon: "gearshape", label: "Settings")
            }

            NavigationLink(destination: NotificationsView()) {
              LabeledRow(icon: "bell", label: "Notifications")
            }

            Button(action: {
              viewModel.signOut()
              dismiss()
            }) {
              LabeledRow(icon: "rectangle.portrait.and.arrow.right", label: "Sign Out")
                .foregroundColor(.red)
            }
          }
        }
        .padding()
        .frame(maxWidth: .infinity)
      }
      .navigationTitle("Profile")
      .navigationBarTitleDisplayMode(.inline)
      .toolbar {
        ToolbarItem(placement: .navigationBarTrailing) {
          Button("Edit") {
            viewModel.showEditSheet = true
          }
        }
      }
      .sheet(isPresented: $viewModel.showEditSheet) {
        EditProfileView(viewModel: viewModel)
      }
    }
  }
}

struct StatView: View {
  let label: String
  let value: String

  var body: some View {
    VStack(spacing: 4) {
      Text(value)
        .font(.title3)
        .fontWeight(.bold)
      Text(label)
        .font(.caption)
        .foregroundColor(.secondary)
    }
  }
}

struct LabeledRow: View {
  let icon: String
  let label: String

  var body: some View {
    HStack(spacing: 12) {
      Image(systemName: icon)
        .font(.title3)
        .foregroundColor(.blue)
      Text(label)
        .font(.body)
      Spacer()
      Image(systemName: "chevron.right")
        .font(.caption)
        .foregroundColor(.secondary)
    }
  }
}

struct ErrorView: View {
  let error: Error
  let onRetry: () -> Void

  var body: some View {
    VStack(spacing: 16) {
      Image(systemName: "exclamationmark.triangle")
        .font(.system(size: 48))
        .foregroundColor(.orange)
      Text("Something went wrong")
        .font(.headline)
      Text(error.localizedDescription)
        .font(.caption)
        .foregroundColor(.secondary)
        .multilineTextAlignment(.center)
      Button("Retry") {
        onRetry()
      }
      .buttonStyle(.borderedProminent)
    }
    .padding()
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }
}
'''

SWIFT_VIEWMODEL_PATTERN = '''
import Foundation
import Combine

@MainActor
class UserProfileViewModel: ObservableObject {
  // 1. Published properties for SwiftUI binding
  @Published var user: User?
  @Published var isLoading = false
  @Published var error: Error?
  @Published var showEditSheet = false

  // 2. Dependencies
  private let userService: UserServiceProtocol
  private let authService: AuthServiceProtocol

  // 3. Private cancellables for Combine
  private var cancellables = Set<AnyCancellable>()

  // 4. Init with dependency injection
  init(
    userService: UserServiceProtocol,
    authService: AuthServiceProtocol,
    userId: String
  ) {
    self.userService = userService
    self.authService = authService
    self.userId = userId
    bindToUpdates()
  }

  private let userId: String

  // 5. Business logic
  func loadUser() async {
    isLoading = true
    error = nil

    do {
      user = try await userService.fetchUser(userId: userId)
    } catch {
      self.error = error
    } finally {
      isLoading = false
    }
  }

  func updateName(_ name: String) async -> Bool {
    guard var currentUser = user else { return false }

    do {
      let updated = try await userService.updateUser(
        userId: userId,
        updates: ["name": name]
      )
      user = updated
      return true
    } catch {
      self.error = error
      return false
    }
  }

  func signOut() async {
    try? await authService.signOut()
  }

  func formatDate(_ date: Date) -> String {
    let formatter = DateFormatter()
    formatter.dateStyle = .medium
    return formatter.string(from: date)
  }

  // 6. Combine bindings for reactive updates
  private func bindToUpdates() {
    // Example: listen to user updates from other parts of app
    NotificationCenter.default.publisher(for: .userDidUpdate)
      .sink { [weak self] notification in
        if let userId = notification.userInfo?["userId"] as? String,
           userId == self?.userId {
          self?.loadUser()
        }
      }
      .store(in: &cancellables)
  }

  deinit {
    cancellables.removeAll()
  }
}

// Protocol for dependency injection (testability)
protocol UserServiceProtocol {
  func fetchUser(userId: String) async throws -> User
  func updateUser(userId: String, updates: [String: Any]) async throws -> User
}

// MARK: - Model
struct User: Codable, Identifiable {
  let id: String
  let email: String
  let name: String
  let avatarUrl: String?
  let projectCount: Int
  let taskCount: Int
  let createdAt: Date

  enum CodingKeys: String, CodingKey {
    case id
    case email
    case name
    case avatarUrl = "avatar_url"
    case projectCount = "project_count"
    case taskCount = "task_count"
    case createdAt = "created_at"
  }
}
'''

SWIFT_CONCURRENCY_PATTERNS = '''
// MARK: - Async/Await over Completion Handlers

// ❌ Old completion handler style (avoid)
func fetchUser(completion: @escaping (Result<User, Error>) -> Void) {
  URLSession.shared.dataTask(with: url) { data, _, error in
    // ...
  }.resume()
}

// ✅ Modern async/await (preferred)
func fetchUser(userId: String) async throws -> User {
  let (data, _) = try await URLSession.shared.data(from: url)
  return try JSONDecoder().decode(User.self, from: data)
}

// MARK: - Actor for Shared Mutable State

@globalActor actor AuthActor {
  static let shared = AuthActor()
}

@AuthActor
class AuthManager {
  static let shared = AuthManager()

  private var currentUser: User?
  private let lock = NSLock()

  func setUser(_ user: User?) {
    currentUser = user
  }

  func getCurrentUser() -> User? {
    currentUser
  }
}

// Use: await AuthActor.shared.setUser(user)

// MARK: - Task and TaskGroup for Parallel Operations

func fetchAllUsers(userIds: [String]) async -> [User] {
  await withTaskGroup(of: User.self) { group in
    for id in userIds {
      group.addTask {
        try? await self.fetchUser(userId: id)
      }
    }

    var users: [User] = []
    for await user in group {
      if let user = user {
        users.append(user)
      }
    }
    return users
  }
}

// MARK: - AsyncSequence for Streaming

func streamNotifications() -> AsyncThrowingStream<Notification, Error> {
  AsyncThrowingStream { continuation in
    let task = Task {
      for await event in websocket {
        continuation.yield(event.notification)
      }
    }
    continuation.onTermination = { @Sendable _ in
      task.cancel()
    }
  }
}

// MARK: - Cancellation

func fetchWithCancellation() async throws -> Data {
  return try await withTaskCancellationHandler {
    try await URLSession.shared.data(from: url).0
  } onCancel: {
    // Cleanup resources
    print("Fetch cancelled")
  }
}

// In UI: cancel in .onDisappear
.task {
  await viewModel.loadData()
}
.onDisappear {
  viewModel.cancelTask()  // Call cancellable.cancel()
}
'''

SWIFT_SECURITY_PRACTICES = '''
// MARK: - Keychain Storage (not UserDefaults)

import Security

class KeychainManager {
  static let shared = KeychainManager()

  func save(token: String, forKey key: String) -> Bool {
    guard let tokenData = token.data(using: .utf8) else { return false }

    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrAccount as String: key,
      kSecValueData as String: tokenData,
      kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly,  // Device-specific
    ]

    // Delete existing first
    SecItemDelete(query as CFDictionary)
    return SecItemAdd(query as CFDictionary, nil) == errSecSuccess
  }

  func read(forKey key: String) -> String? {
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrAccount as String: key,
      kSecReturnData as String: true,
      kSecMatchLimit as String: kSecMatchLimitOne,
    ]

    var dataTypeRef: AnyObject?
    let status = SecItemCopyMatching(query as CFDictionary, &dataTypeRef)

    guard status == errSecSuccess,
          let data = dataTypeRef as? Data,
          let token = String(data: data, encoding: .utf8) else {
      return nil
    }
    return token
  }
}

// MARK: - SSL Pinning (for sensitive APIs)

class PinningURLSessionDelegate: NSObject, URLSessionDelegate {
  let host: String
  let publicKeyHash: String  // SHA256 of certificate public key

  init(host: String, publicKeyHash: String) {
    self.host = host
    self.publicKeyHash = publicKeyHash
  }

  func urlSession(
    _ session: URLSession,
    didReceive challenge: URLAuthenticationChallenge,
    completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLSession.AuthChallengeDisposition) -> Void
  ) {
    guard let serverTrust = challenge.protectionSpace.serverTrust else {
      completionHandler(.cancelAuthenticationChallenge, nil)
      return
    }

    let certificates = SecTrustCopyCertificateChain(serverTrust) as? [SecCertificate] ?? []
    guard let serverCertificate = certificates.first,
          let serverPublicKey = SecCertificateCopyKey(serverCertificate) else {
      completionHandler(.cancelAuthenticationChallenge, nil)
      return
    }

    let serverKeyData = SecKeyCopyExternalRepresentation(serverPublicKey, nil) as Data?
    let serverKeyHash = SHA256.hash(data: serverKeyData!).compactMap { String(format: "%02x", $0) }.joined()

    if serverKeyHash == publicKeyHash {
      completionHandler(.useCredential, URLCredential(trust: serverTrust))
    } else {
      completionHandler(.cancelAuthenticationChallenge, nil)
    }
  }
}

// MARK: - App Transport Security (ATS)

// Info.plist:
// <key>NSAppTransportSecurity</key>
// <dict>
//   <key>NSAllowsArbitraryLoads</key>
//   <false/>
//   <key>NSExceptionDomains</key>
//   <dict>
//     <key>api.example.com</key>
//     <dict>
//       <key>NSIncludesSubdomains</key>
//       <true/>
//       <key>NSExceptionMinimumTLSVersion</key>
//       <string>TLSv1.2</string>
//       <key>NSExceptionRequiresForwardSecrecy</key>
//       <true/>
//     </dict>
//   </dict>
// </dict>
'''

SWIFT_PERFORMANCE_OPTIMIZATION = [
    "Use LazyVStack/LazyHStack for long lists (only renders visible items)",
    "Avoid GeometryReader in scroll views — causes layout recalculations",
    "Use .task modifier for async initialization (not .onAppear for async work)",
    "Cache images with AsyncImage + custom cache (NSCache)",
    "Reduce view hierarchy depth: combine with overlays, background modifier",
    "Use @State for local state, @ObservedObject for external objects, @StateObject for owned",
    "Avoid unnecessary @State changes — use shouldUpdate pattern",
    "Prefer struct over class for View types (value semantics, no retain cycles)",
    "Use Instruments: Time Profiler for CPU, Allocations for memory, Core Animation for GPU",
    "Enable compiler optimization: -O in release, -Onone debug for hot reload",
]

SWIFTUI_TESTING_STRATEGY = {
    "unit_tests": "Test view models, services, utilities with XCTest framework",
    "ui_tests": "XCUITest for full app flows (launch, tap, type)",
    "snapshot_tests": "FBSnapshotTestCase for view snapshot regression",
    " accessibility": "Xcode Accessibility Inspector, VoiceOver testing",
    "mocking": "Use protocols and dependency injection, mock with Cuckoo or Mockingbird",
}

SWIFT_ARCHITECTURE_PATTERNS = {
    "mvvm": {
        "view": "SwiftUI View with @State/@ObservedObject",
        "view_model": "@StateObject/@ObservedObject with @Published properties",
        "model": "Struct with Codable, Identifiable",
        "service": "Protocol-based, injected via init",
    },
    "viper": {
        "view": "UIViewController (UIKit) or UIViewRepresentable",
        "interactor": "Business logic, use cases",
        "presenter": "Formats data for view, handles UI events",
        "entity": "Data models",
        "router": "Navigation logic",
    },
    "clean_architecture": {
        "layers": {
            "presentation": "SwiftUI Views + ViewModels (outer)",
            "domain": "Use cases, entities, repository interfaces (core)",
            "data": "Repository implementations, API clients, local DB (inner)",
        },
        "dependency_rule": "Domain layer has no dependencies on outer layers",
    },
}

SWIFT_IOS_APP_ORGANIZATION = {
    "folder_structure": [
      "App/",
      "  AppDelegate.swift (UIKit lifecycle, if needed)",
      "  SceneDelegate.swift (window management)",
      "  MyAppApp.swift (SwiftUI entry point)",
      "Views/",
      "  Components/",
      "    ButtonCustom.swift",
      "    AvatarView.swift",
      "  Screens/",
      "    UserProfileView.swift",
      "    SettingsView.swift",
      "ViewModels/",
      "  UserProfileViewModel.swift",
      "Models/",
      "  User.swift",
      "  API/",
      "    Request.swift",
      "    Response.swift",
      "Services/",
      "  UserService.swift",
      "  AuthService.swift",
      "Networking/",
      "  APIClient.swift",
      "  Interceptors/",
      "Utils/",
      "  Extensions/",
      "  Formatters/",
      "Resources/",
      "  Assets.xcassets/",
      "  Localizable.strings",
    ],
    "naming_convention": {
      "classes": "UpperCamelCase (UserService)",
      "files": "UpperCamelCase matching content (UserProfileView.swift)",
      "extensions": "UpperCamelCase + Purpose (UIView+Constraints.swift)",
      "constants": "lowerCamelCase or snake_case for enum cases",
    },
}

SWIFTUI_ANIMATION_PATTERNS = '''
// MARK: - Implicit Animations
Button("Animate") {
  withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
    isExpanded.toggle()
  }
}

// MARK: - Explicit Animations
.withAnimation {
  offset = CGSize(width: 100, height: 0)
}

// MARK: - Transition Animations
.if(isVisible) { view in
  view.transition(.scale.combined(with: .opacity))
}

// MARK: - Matched Geometry Effect
@Namespace private var buttonAnimation

if isExpanded {
  Button("Expanded") {
    withAnimation {
      isExpanded = false
    }
  }
  .matchedGeometryEffect(id: "button", in: buttonAnimation)
} else {
  Button("Collapsed") {
    withAnimation {
      isExpanded = true
    }
  }
  .matchedGeometryEffect(id: "button", in: buttonAnimation)
}

// MARK: - Animation Modifiers
.animation(.default, value: someState)  // Since SwiftUI 3, use value parameter
'''

SWIFTUI_COMPOSITION_PATTERNS = '''
// MARK: - View Extensions for Reusability
extension View {
  func cardStyle() -> some View {
    self
      .padding()
      .background(Color(.systemBackground))
      .cornerRadius(12)
      .shadow(color: .black.opacity(0.1), radius: 4, y: 2)
  }

  func hiddenWhen(_ condition: Bool) -> some View {
    self.hidden(condition)
  }
}

// MARK: - Custom View Modifiers
struct CardModifier: ViewModifier {
  func body(content: Content) -> some View {
    content
      .padding()
      .background(Color(.systemBackground))
      .cornerRadius(12)
      .shadow(radius: 2)
  }
}

extension View {
  func card() -> some View {
    modifier(CardModifier())
  }
}

// MARK: - Custom Container View
struct VerticalStack<Content: View>: View {
  let spacing: CGFloat
  @ViewBuilder let content: () -> Content

  init(spacing: CGFloat = 16, @ViewBuilder content: @escaping () -> Content) {
    self.spacing = spacing
    self.content = content
  }

  var body: some View {
    VStack(spacing: spacing) {
      content()
    }
  }
}
'''

SWIFT_PERFORMANCE_MONITORING = '''
// MARK: - Measure Execution Time
func measure<T>(_ operation: () async throws -> T) async rethrows -> (result: T, elapsed: TimeInterval) {
  let start = Date()
  let result = try await operation()
  let elapsed = Date().timeIntervalSince(start)
  return (result, elapsed)
}

// MARK: - Signpost for Instruments
import os.signpost

let logger = Logger(subsystem: "com.myapp.network", category: "api")

logger.signpost(
  name: "fetchUser",
  signpostID: .init(),
  begin: "Starting fetch",
  Clock: .continuous
)

data = try await session.data(for: request)

logger.signpost(
  name: "fetchUser",
  signpostID: signpostID,
  end: "Completed fetch"
)

// View in Instruments → Logging → Custom logging
'''

SWIFTUI_ACCESSIBILITY = '''
// MARK: - VoiceOver Support
// 1. Accessibility labels
Button(action: {}) {
  Image(systemName: "trash")
    .accessibilityLabel("Delete item")
    .accessibilityHint("Deletes this item permanently")
}

// 2. Grouping elements
HStack {
  Image(systemName: "star.fill")
  Text("4.5")
}
.accessibilityElement(children: .combine)  // Read as "4.5 stars"

// 3. Dynamic type support
.font(.body)  // Not hardcoded sizes
.lineLimit(nil)  // Allow unlimited lines for larger text scaling

// 4. Reduce motion
.horizontalSizeClass(horizontal)  // Adapt layout for reduced width
.animation(
  .easeInOut(duration: 0.3),
  value: isVisible
)
.withAnimation {
  // Animate conditionally
  if !reduceMotion {
    // Full animation
  }
}

// Check reduced motion:
if UIAccessibility.isReduceMotionEnabled {
  // Disable non-essential animations
}

// 5. Accessibility traits
Image(systemName: "play.fill")
  .accessibilityAddTraits(.isButton)
  .accessibilityRemoveTraits(.isImage)

// 6. Custom actions for complex gestures
.mapView
  .accessibilityAddTraits(.isButton)
  .accessibilityCustomActions([
    UIAccessibilityCustomAction(
      name: "Zoom in",
      actionHandler: { zoomIn() }
    ),
    UIAccessibilityCustomAction(
      name: "Zoom out",
      actionHandler: { zoomOut() }
    ),
  ])
'''

SWIFT_APP_STORE_SUBMISSION = {
    "certificates": {
        "development": "Apple Development certificate (Xcode-managed)",
        "distribution": "Apple Distribution certificate (3-year renewal)",
        "push_notifications": "APNs key (not certificate) — single key for all apps",
    },
    "provisioning_profiles": {
        "development": "Local development on registered devices",
        "ad_hoc": "Distribute to specific devices without App Store",
        "app_store": "App Store Connect — automatic via Xcode",
    },
    "info_plist_required": [
        "CFBundleDisplayName (App name)",
        "CFBundleShortVersionString (marketing version: 1.2.3)",
        "CFBundleVersion (build number: 123, auto-increment)",
        "NSCameraUsageDescription (if using camera)",
        "NSLocationWhenInUseUsageDescription (if location)",
        "NSPhotoLibraryAddUsageDescription (if saving photos)",
    ],
    "app_store_connect": {
        "create_app": "New app, bundle ID must match Xcode project",
        "screenshots": "6.7\" (iPhone), 12.9\" (iPad), Desktop for Mac apps",
        "keywords": "Comma-separated, character-limited",
        "description": "What it does, benefits, key features (min 1, max 4,000 chars)",
        "privacy_policy": "URL required — host on your domain or App Store Connect",
        "review_contact": "Email + phone for App Review team to contact you",
        "demo_account": "Provide test account credentials if login required",
    },
    "review_guidelines": {
        "common_rejections": [
            "Broken functionality (crashes, blank screens)",
            "Placeholder content (test data, example.com)",
            "Incomplete metadata (missing screenshots, descriptions)",
            "Copyrighted content without permission",
            "Spammy behavior (duplicate apps, misleading)",
        ],
        "avoid": "In-app purchase bypass, hidden functionality, modifying system UI",
    },
}
