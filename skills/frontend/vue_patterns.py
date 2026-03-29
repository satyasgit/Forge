"""
Frontend skill: Vue 3 + TypeScript + Composition API patterns and conventions.
Injected into FrontendAgent system prompt context.
"""

VUE_COMPONENT_TEMPLATE = '''
<script setup lang="ts">
// 1. Imports first
import { ref, computed, onMounted, watch } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import type { User, UserResponse } from '@/types'

// 2. Props with types
interface Props {
  userId: string
  onSuccess?: (user: User) => void
}
const props = defineProps<Props>()

// 3. Emits for events
const emit = defineEmits<{
  saved: [user: User]
  cancelled: []
}>()

// 4. Reactive state
const user = ref<User | null>(null)
const localError = ref<Error | null>(null)

// 5. Vue Query for data fetching
const { data, isLoading, error, refetch } = useQuery({
  queryKey: ['user', props.userId],
  queryFn: () => fetchUser(props.userId),
  staleTime: 60_000,
})

// 6. Computed properties for derived state
const fullName = computed(() => {
  return user.value ? `${user.value.firstName} ${user.value.lastName}` : ''
})

const isFormValid = computed(() => {
  return user.value?.email && user.value?.name && user.value?.email.includes('@')
})

// 7. Actions/mutations
const queryClient = useQueryClient()

const { mutate: updateUser, isPending: isUpdating } = useMutation({
  mutationFn: (updates: Partial<User>) =>
    fetch(`/api/users/${props.userId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    }).then(r => r.json()),
  onSuccess: (updatedUser: User) => {
    queryClient.setQueryData(['user', props.userId], updatedUser)
    queryClient.invalidateQueries({ queryKey: ['users'] })
    emit('saved', updatedUser)
  },
  onError: (err: Error) => {
    localError.value = err
  },
})

// 8. Watchers for side effects
watch(
  () => props.userId,
  (newId) => {
    if (newId) {
      refetch()
    }
  },
  { immediate: true }
)

// 9. Lifecycle hooks
onMounted(() => {
  console.log('Component mounted')
})

// 10. Helper functions
async function handleSave() {
  if (!user.value) return
  await updateUser(user.value)
}

function handleCancel() {
  emit('cancelled')
}
</script>

<template>
  <!-- 11. Loading state -->
  <div v-if="isLoading" class="animate-pulse" role="status" aria-label="Loading user data">
    <div class="h-4 bg-gray-200 rounded w-3/4 mb-2"></div>
    <div class="h-4 bg-gray-200 rounded w-1/2"></div>
  </div>

  <!-- 12. Error state -->
  <div v-else-if="error || localError" role="alert" class="p-4 bg-red-50 text-red-700 rounded-md">
    {{ (error || localError)?.message || 'An error occurred' }}
  </div>

  <!-- 13. Empty state -->
  <div v-else-if="!user" class="text-gray-500 text-sm">
    No user data available.
  </div>

  <!-- 14. Happy path -->
  <div v-else class="space-y-4">
    <div>
      <label for="name" class="block text-sm font-medium text-gray-700">Name</label>
      <input
        id="name"
        v-model="user.name"
        type="text"
        class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        :disabled="isUpdating"
        aria-required="true"
        :aria-describedby="!isFormValid ? 'form-error' : undefined"
      />
    </div>

    <div v-if="!isFormValid" id="form-error" class="text-sm text-red-600">
      Please fill in all required fields correctly.
    </div>

    <div class="flex gap-3">
      <button
        @click="handleSave"
        :disabled="!isFormValid || isUpdating"
        class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        :aria-busy="isUpdating"
      >
        {{ isUpdating ? 'Saving...' : 'Save' }}
      </button>
      <button
        @click="handleCancel"
        class="px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-50"
      >
        Cancel
      </button>
    </div>
  </div>
</template>
'''

VITE_CONFIG_STANDARDS = {
    "alias": {
        "rule": "@/ -> src/",
        "reason": "Consistent absolute imports across project",
    },
    "typescript": {
        "strict": True,
        "noUnusedLocals": True,
        "noUnusedParameters": True,
        "exactOptionalPropertyTypes": True,
    },
    "vueInspiredTools": {
        "preferred": ["Vue Query", "Vue Router", "Pinia"],
        "avoid": ["Vuex (legacy)", "Options API (new code only)"],
    },
}

VUE_COMPOSABLES_PATTERNS = {
    "use_user": {
        "purpose": "Reusable composable for auth user + refresh logic",
        "example": '''
// composables/useUser.ts
export function useUser() {
  const { data: user, isLoading, error } = useQuery({
    queryKey: ['user'],
    queryFn: fetchCurrentUser,
  })

  const refresh = useMutation({
    mutationFn: () => fetchCurrentUser(true),
    onSuccess: (newUser) => {
      // Update cache
    },
  })

  return { user, isLoading, error, refresh }
}
''',
    },
    "use_async": {
        "purpose": "Wrapper around Vue Query with standardized error handling",
        "example": '''
export function useAsync<T>(key: QueryKey, fn: () => Promise<T>) {
  return useQuery({
    queryKey: key,
    queryFn: fn,
    retry: 1,  // Don't retry on 4xx errors
  })
}
''',
    },
    "use_form": {
        "purpose": "Form state + validation integrated with Zod",
        "example": '''
export function useForm<T>(schema: ZodSchema<T>) {
  const values = ref<T>(schema.parse(defaultValues))
  const errors = ref<Partial<Record<keyof T, string>>>({})

  function validate() {
    const result = schema.safeParse(values.value)
    if (!result.success) {
      errors.value = result.error.flatten().fieldErrors as any
      return false
    }
    errors.value = {}
    return true
  }

  return { values, errors, validate }
}
''',
    },
}

COMPOSITION_API_GUIDELINES = [
    "Always use <script setup> - Options API deprecated for new code",
    "Define props with TypeScript interface + defineProps<Props>()",
    "Use ref() for primitive/reactives, reactive() for objects (but prefer ref with .value)",
    "Use computed() for derived state — never store derived in ref",
    "Use watch() for side effects on reactive changes, not to sync state",
    "Extract complex logic to custom composables (useXxx pattern) — max 200 lines per component",
    "Keep components under 200 lines — extract sub-components for readability",
    "Always provide types for composable return values — no implicit any",
    "Use defineEmits<Type>() for type-safe event emissions",
    "Use defineExpose() sparingly — prefer v-model or props/events for parent communication",
]

VUE_ROUTING_CONVENTIONS = {
    "file_structure": {
        "src/router/index.ts": "Router configuration with createRouter()",
        "src/routes/": "Route components organized by feature",
        "src/routes/(auth)/": "Group for auth routes (no layout)",
        "src/routes/(app)/": "Group for authenticated routes with layout",
    },
    "navigation": {
        "named_routes": "Use named routes (not paths) for navigation",
        "lazy_loading": "Route-level code splitting via() => import('./About.vue')",
        "guards": "Global auth guard in router.beforeEach()",
        "meta_fields": "Use route.meta for title, layout, requiresAuth",
    },
    "dynamic_routes": {
        "pattern": "[id].tsx for params, [...catchAll].tsx for wildcards",
        "types": "Use TypeScript interface for route params: RouteRecordRaw['meta']",
    },
}

VITE_BUILD_OPTIMIZATION = {
    "chunking": "Route-based code splitting (automatic with vue-router)",
    "compression": "gzip or brotli via vite-plugin-compression",
    "cdn": "Static assets to CDN in production (VITE_CDN_URL)",
    "environment": "VITE_ prefix for env vars exposed to client",
    "sourcemap": "Production: hidden sourcemap for error reporting",
}

VUE_TESTING_STRATEGY = {
    "framework": "Vitest + Vue Test Utils (VTU)",
    "component_tests": "Test rendering, props, emits, user interactions",
    "mounting": "use mount() for full DOM, shallowMount() for unit isolation",
    "mocking": "Mock API calls via vi.mock() or Vue Query mocks",
    "accessibility": "Use jest-axe or @axe-core/vue for a11y testing",
}

PINIA_STORE_PATTERNS = {
    "store_definition": '''
// stores/user.ts
export const useUserStore = defineStore('user', {
  state: () => ({
    id: null as string | null,
    email: '',
    name: '',
  }),
  getters: {
    fullName: (state) => `${state.firstName} ${state.lastName}`,
    isAdmin: (state) => state.roles.includes('admin'),
  },
  actions: {
    async fetchUser(userId: string) {
      const data = await api.getUser(userId)
      this.id = data.id
      this.email = data.email
      this.name = data.name
    },
  },
})
''',
    "composition_api_alternative": "defineStore('id', () => { ref(), computed(), action() })",
    "typescript": "Full type inference — state, getters, actions all typed",
}

VUE_SSR_VS_SPA = {
    "ssr_next_nuxt": "Use when SEO matters, fast first paint, but complexity ↑",
    "spa": "Use for dashboards, admin panels, mobile-first apps (PWA)",
    "ssg": "Static site generation for marketing/docs sites",
    "decision": "Start SPA, add SSR only if SEO or performance metrics demand it",
}

VUE_PERFORMANCE_TIPS = [
    "Use v-once for static content that never re-renders",
    "Use v-memo for expensive component subtrees (Vue 3.2+)",
    "Avoid deeply nested reactive objects — flatten state",
    "Virtualize long lists (>100 items) with vue-virtual-scroller",
    "Lazy-load images with loading='lazy' and IntersectionObserver",
    "Debounce/throttle expensive watchers or computed properties",
    "Use keep-alive for component caching in router-view",
    "Extract heavy computed to Web Worker via comlink",
]

VUE_A11Y_CHECKLIST = [
    "All interactive elements have accessible name (aria-label or text content)",
    "Form inputs have associated <label> (for/id or aria-labelledby)",
    "Modal dialogs trap focus and restore on close (use-focus-trap)",
    "Color contrast ratio >= 4.5:1 for normal text, 3:1 for large",
    "Keyboard navigable: all actions reachable via Tab, visible focus ring",
    "Skip links for main content on complex layouts",
    "ARIA live regions for dynamic updates (notifications, alerts)",
    "Heading hierarchy: single h1 per page, headings in order",
    "Decorative images have empty alt (alt='')",
    "Icons have aria-hidden='true' or accessible label",
]

VUE_BEST_PRACTICES = [
    "Single-file components: <script setup>, <template>, <style scoped>",
    "Component names: PascalCase for components, kebab-case for files (UserProfile.vue)",
    "Props: pass primitives, not objects; provide defaults; validate with PropType",
    "Events: kebab-case emit names (user-saved, not userSaved)",
    "Slots: use named slots for flexible composition",
    "Business logic in composables, not components",
    "TypeScript: strict mode, avoid any, use interface over type when possible",
    "Testing: every component needs test for rendering, user interaction, edge cases",
]
