"""
Mobile skill: React Native + Expo patterns.
Injected into MobileAgent context.
"""

EXPO_SCREEN_TEMPLATE = '''
// screens/FeatureScreen.tsx
import { View, Text, ScrollView, Pressable } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { useQuery } from "@tanstack/react-query";
import { Stack } from "expo-router";

export default function FeatureScreen() {
  const insets = useSafeAreaInsets();

  const { data, isLoading, error } = useQuery({
    queryKey: ["feature"],
    queryFn: () => fetch("/api/feature").then(r => r.json()),
  });

  if (isLoading) return <LoadingSkeleton />;
  if (error) return <ErrorView error={error} />;

  return (
    <>
      <Stack.Screen options={{ title: "Feature", headerLargeTitle: true }} />
      <ScrollView
        className="flex-1 bg-white dark:bg-gray-900"
        contentContainerStyle={{ paddingBottom: insets.bottom + 16 }}
      >
        <View className="px-4 pt-4 gap-4">
          {data?.items.map(item => (
            <Pressable
              key={item.id}
              onPress={() => {
                Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                // navigate
              }}
              className="bg-gray-50 dark:bg-gray-800 rounded-2xl p-4 active:opacity-70"
              accessibilityRole="button"
              accessibilityLabel={item.title}
            >
              <Text className="text-base font-semibold text-gray-900 dark:text-white">
                {item.title}
              </Text>
            </Pressable>
          ))}
        </View>
      </ScrollView>
    </>
  );
}
'''

EXPO_AUTH_FLOW = '''
// Expo Router auth flow with SecureStore

// app/(auth)/login.tsx
import { useState } from "react";
import { View, TextInput, Pressable, Text, Alert } from "react-native";
import * as SecureStore from "expo-secure-store";
import { router } from "expo-router";

export default function LoginScreen() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleLogin() {
    setLoading(true);
    try {
      const res = await fetch(`${process.env.EXPO_PUBLIC_API_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) throw new Error("Invalid credentials");
      const { access_token, refresh_token } = await res.json();

      // Store tokens securely (hardware-backed on iOS/Android)
      await SecureStore.setItemAsync("access_token", access_token);
      await SecureStore.setItemAsync("refresh_token", refresh_token);

      router.replace("/(app)/home");
    } catch (e: any) {
      Alert.alert("Login failed", e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <View className="flex-1 justify-center px-6 bg-white dark:bg-gray-900">
      <TextInput
        value={email}
        onChangeText={setEmail}
        placeholder="Email"
        keyboardType="email-address"
        autoCapitalize="none"
        autoComplete="email"
        textContentType="emailAddress"
        className="border border-gray-300 rounded-xl px-4 py-3 mb-3 text-base"
        accessibilityLabel="Email address"
      />
      <TextInput
        value={password}
        onChangeText={setPassword}
        placeholder="Password"
        secureTextEntry
        textContentType="password"
        className="border border-gray-300 rounded-xl px-4 py-3 mb-6 text-base"
        accessibilityLabel="Password"
      />
      <Pressable
        onPress={handleLogin}
        disabled={loading || !email || !password}
        className="bg-blue-600 rounded-xl py-4 items-center active:opacity-80 disabled:opacity-50"
        accessibilityRole="button"
      >
        <Text className="text-white font-semibold text-base">
          {loading ? "Signing in..." : "Sign in"}
        </Text>
      </Pressable>
    </View>
  );
}
'''

EXPO_ROUTER_STRUCTURE = """
app/
  _layout.tsx              # Root layout (fonts, providers)
  (auth)/
    _layout.tsx            # Auth stack — no bottom tab
    login.tsx
    register.tsx
    forgot-password.tsx
  (app)/
    _layout.tsx            # Tab layout (bottom tabs)
    home/
      index.tsx            # Home tab
      [id].tsx             # Dynamic route: /home/123
    profile/
      index.tsx
      edit.tsx
    settings/
      index.tsx
      billing.tsx          # Paywall / subscription management
"""

PUSH_NOTIFICATIONS = '''
// notifications/setup.ts — Expo Push Notifications

import * as Notifications from "expo-notifications";
import * as Device from "expo-device";
import { Platform } from "react-native";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

export async function registerForPushNotifications(): Promise<string | null> {
  if (!Device.isDevice) return null;   // Simulators can\'t receive push

  const { status: existingStatus } = await Notifications.getPermissionsAsync();
  let finalStatus = existingStatus;

  if (existingStatus !== "granted") {
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
  }
  if (finalStatus !== "granted") return null;

  // Android notification channel
  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("default", {
      name: "default",
      importance: Notifications.AndroidImportance.MAX,
      vibrationPattern: [0, 250, 250, 250],
    });
  }

  const token = (await Notifications.getExpoPushTokenAsync()).data;
  // Send token to your backend
  await fetch("/api/users/push-token", {
    method: "POST",
    body: JSON.stringify({ token }),
    headers: { "Content-Type": "application/json" },
  });
  return token;
}
'''

APP_STORE_CHECKLIST = [
    "Set CFBundleVersion and CFBundleShortVersionString in app.json",
    "Add Privacy Manifest (iOS 17+): NSPrivacyAccessedAPITypes",
    "Configure permissions strings in app.json for camera, location, etc.",
    "Set up App Store Connect: app ID, certificates, provisioning profile",
    "EAS Build: eas build --platform ios --profile production",
    "Submit: eas submit --platform ios",
    "Google Play: generate keystore, configure eas.json release",
    "ASO: title (30 chars), subtitle (30), description (4000), keywords (100)",
    "Screenshots: 6.7\" iPhone + 12.9\" iPad + Android 16:9",
    "Age rating: fill questionnaire in App Store Connect",
]
