"""
Frontend Skill: Vitest + React Testing Library pattern library.
Mirrors skills/security/sast.py — each entry is a detected pattern in
React/TypeScript source with severity, category, test template, and fix.
The FrontendAgent runs this locally before the API call to identify
untested component interactions, a11y gaps, and missing coverage.
"""

# ── Component test-gap patterns ───────────────────────────────────────────────
# Detected in COMPONENT files — things that need tests written for them.

COMPONENT_TEST_PATTERNS: list[dict] = [
    {
        "name": "Interactive element without test",
        "regex": r"onClick|onPress|onSubmit|onChange",
        "severity": "high",
        "category": "interaction",
        "description": "Interactive handler found — needs userEvent test covering the interaction.",
        "test_template": '''
it("calls {handler} when {element} is {action}", async () => {
  const {handler} = vi.fn();
  render(<{Component} on{Event}={{handler}} />);
  await userEvent.click(screen.getByRole("{role}", { name: /{label}/i }));
  expect(handler).toHaveBeenCalledOnce();
});''',
        "example": '''
it("calls onSubmit with form values when submit button clicked", async () => {
  const onSubmit = vi.fn();
  render(<LoginForm onSubmit={onSubmit} />);
  await userEvent.type(screen.getByLabelText(/email/i), "test@example.com");
  await userEvent.type(screen.getByLabelText(/password/i), "password123");
  await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
  expect(onSubmit).toHaveBeenCalledWith({
    email: "test@example.com", password: "password123"
  });
});''',
    },
    {
        "name": "Loading state without test",
        "regex": r"isLoading|isPending|loading\s*&&|loading\s*\?",
        "severity": "medium",
        "category": "states",
        "description": "Loading state rendered — needs test asserting skeleton/spinner is shown during pending query.",
        "test_template": '''
it("shows loading state while {resource} is fetching", () => {
  server.use(http.get("/api/{resource}", () => new Promise(() => {})));
  render(<{Component} />);
  expect(screen.getByRole("status")).toBeInTheDocument();
  // or: expect(screen.getByLabelText(/loading/i)).toBeInTheDocument();
});''',
        "example": '''
it("shows skeleton while user data is loading", () => {
  server.use(http.get("/api/users/:id", () => new Promise(() => {})));
  render(<UserProfile userId="1" />);
  expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
  expect(screen.queryByText(/jane doe/i)).not.toBeInTheDocument();
});''',
    },
    {
        "name": "Error state without test",
        "regex": r"isError|error\s*&&|error\s*\?|catch\s*\(",
        "severity": "high",
        "category": "states",
        "description": "Error state rendered — needs test asserting error message shown when API fails.",
        "test_template": '''
it("shows error message when {resource} fetch fails", async () => {
  server.use(http.get("/api/{resource}", () => HttpResponse.error()));
  render(<{Component} />);
  expect(await screen.findByRole("alert")).toBeInTheDocument();
  expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
});''',
        "example": '''
it("shows error alert when user fetch returns 500", async () => {
  server.use(http.get("/api/users/1", () =>
    HttpResponse.json({ detail: "Server error" }, { status: 500 })
  ));
  render(<UserProfile userId="1" />);
  expect(await screen.findByRole("alert")).toBeInTheDocument();
});''',
    },
    {
        "name": "Form validation without test",
        "regex": r"(?:register|control)\s*\(\s*[\"']\w+[\"']|zodResolver|yupResolver",
        "severity": "high",
        "category": "validation",
        "description": "Form with validation — needs tests for required fields, format errors, and submit with invalid data.",
        "test_template": '''
it("shows validation error for empty {field}", async () => {
  render(<{Form} onSubmit={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: /submit/i }));
  expect(await screen.findByText(/{field} is required/i)).toBeInTheDocument();
});

it("shows format error for invalid {field}", async () => {
  render(<{Form} onSubmit={vi.fn()} />);
  await userEvent.type(screen.getByLabelText(/{field}/i), "invalid-value");
  await userEvent.click(screen.getByRole("button", { name: /submit/i }));
  expect(await screen.findByText(/invalid {field}/i)).toBeInTheDocument();
});''',
        "example": '''
it("shows email validation error for invalid format", async () => {
  render(<RegisterForm onSubmit={vi.fn()} />);
  await userEvent.type(screen.getByLabelText(/email/i), "notanemail");
  await userEvent.click(screen.getByRole("button", { name: /register/i }));
  expect(await screen.findByText(/invalid email/i)).toBeInTheDocument();
});''',
    },
    {
        "name": "useEffect side effect without test",
        "regex": r"useEffect\s*\(\s*\(\s*\)\s*=>",
        "severity": "medium",
        "category": "side_effects",
        "description": "useEffect present — test must verify the effect runs and cleans up correctly.",
        "test_template": '''
it("fetches {resource} on mount", async () => {
  render(<{Component} />);
  expect(await screen.findByText(/{expected_content}/i)).toBeInTheDocument();
});

it("cleans up {subscription} on unmount", () => {
  const { unmount } = render(<{Component} />);
  unmount();
  // assert no pending timers, subscriptions, or event listeners
});''',
        "example": '''
it("fetches and displays user on mount", async () => {
  server.use(http.get("/api/users/1",
    () => HttpResponse.json({ id: "1", name: "Jane Doe" })
  ));
  render(<UserProfile userId="1" />);
  expect(await screen.findByText(/jane doe/i)).toBeInTheDocument();
});''',
    },
    {
        "name": "Conditional render without test",
        "regex": r"&&\s*<|ternary|\?\s*<\w|\?\s*\(",
        "severity": "low",
        "category": "conditional_render",
        "description": "Conditional render found — needs tests for both truthy and falsy branches.",
        "test_template": '''
it("renders {element} when {condition} is true", () => {
  render(<{Component} {prop}={true_value} />);
  expect(screen.getByText(/{expected}/i)).toBeInTheDocument();
});

it("hides {element} when {condition} is false", () => {
  render(<{Component} {prop}={false_value} />);
  expect(screen.queryByText(/{expected}/i)).not.toBeInTheDocument();
});''',
        "example": '''
it("shows upgrade banner for free plan users", () => {
  render(<Dashboard user={{ plan: "free" }} />);
  expect(screen.getByText(/upgrade to pro/i)).toBeInTheDocument();
});

it("hides upgrade banner for pro users", () => {
  render(<Dashboard user={{ plan: "pro" }} />);
  expect(screen.queryByText(/upgrade to pro/i)).not.toBeInTheDocument();
});''',
    },
    {
        "name": "Navigation / routing without test",
        "regex": r"useNavigate|useRouter|router\.push|<Link\s",
        "severity": "medium",
        "category": "navigation",
        "description": "Navigation call found — needs test asserting correct route after action.",
        "test_template": '''
it("navigates to {route} after {action}", async () => {
  render(
    <MemoryRouter initialEntries={["{start_route}"]}>
      <{Component} />
    </MemoryRouter>
  );
  await userEvent.click(screen.getByRole("button", { name: /{label}/i }));
  expect(screen.getByText(/{destination_content}/i)).toBeInTheDocument();
});''',
        "example": '''
it("redirects to dashboard after successful login", async () => {
  render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/dashboard" element={<div>Dashboard</div>} />
      </Routes>
    </MemoryRouter>
  );
  await userEvent.type(screen.getByLabelText(/email/i), "a@b.com");
  await userEvent.type(screen.getByLabelText(/password/i), "pass123");
  await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
  expect(await screen.findByText(/dashboard/i)).toBeInTheDocument();
});''',
    },
]

# ── Accessibility patterns ────────────────────────────────────────────────────
# Detected in component source — a11y issues that need both code fix AND test.

A11Y_PATTERNS: list[dict] = [
    {
        "name": "Missing button accessible name",
        "regex": r"<button(?![^>]*aria-label)(?![^>]*aria-labelledby)(?![^>]*title)[^>]*>(?:\s*<(?:svg|img|span)[^/]*/?>|\s*)\s*</button>",
        "severity": "high",
        "wcag": "1.3.1 / 4.1.2",
        "description": "Button with no text content and no aria-label — screen readers will announce nothing.",
        "fix": '<button aria-label="Close dialog"><XIcon /></button>',
        "test": 'expect(screen.getByRole("button", { name: /close dialog/i })).toBeInTheDocument();',
    },
    {
        "name": "Image without alt text",
        "regex": r"<img(?![^>]*\balt\s*=)[^>]*>",
        "severity": "high",
        "wcag": "1.1.1",
        "description": "img element missing alt attribute — content inaccessible to screen readers.",
        "fix": '<img src={url} alt="User profile photo" /> or alt="" for decorative',
        "test": 'expect(screen.getByAltText(/profile photo/i)).toBeInTheDocument();',
    },
    {
        "name": "Form input without label",
        "regex": r"<input(?![^>]*aria-label)(?![^>]*aria-labelledby)(?![^>]*id\s*=)",
        "severity": "high",
        "wcag": "1.3.1",
        "description": "Input has no associated label — screen readers cannot announce its purpose.",
        "fix": '<label htmlFor="email">Email</label>\n<input id="email" type="email" />',
        "test": 'screen.getByLabelText(/email/i)',
    },
    {
        "name": "onClick on non-interactive element",
        "regex": r"<(?:div|span|p|li)\s[^>]*onClick",
        "severity": "medium",
        "wcag": "2.1.1",
        "description": "Click handler on non-interactive element — not keyboard or screen reader accessible.",
        "fix": "Use <button> or <a> instead, or add role='button' + tabIndex={0} + onKeyDown handler.",
        "test": 'expect(screen.getByRole("button", { name: /action/i })).toBeInTheDocument();',
    },
]

# ── Vitest setup file template ────────────────────────────────────────────────

VITEST_SETUP = '''
// tests/setup.ts — imported by vitest.config.ts

import "@testing-library/jest-dom";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeAll, afterAll } from "vitest";
import { server } from "./mocks/server";

// Start MSW server before all tests
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

// Reset handlers after each test (prevents test pollution)
afterEach(() => {
  cleanup();
  server.resetHandlers();
});

// Stop server after all tests
afterAll(() => server.close());
'''

# ── MSW server setup ──────────────────────────────────────────────────────────

MSW_SERVER_TEMPLATE = '''
// tests/mocks/server.ts
import { setupServer } from "msw/node";
import { handlers } from "./handlers";

export const server = setupServer(...handlers);

// tests/mocks/handlers.ts
import { http, HttpResponse } from "msw";

export const handlers = [
  http.get("/api/users/:id", ({ params }) =>
    HttpResponse.json({ id: params.id, name: "Test User", email: "test@example.com" })
  ),
  http.post("/api/auth/login", () =>
    HttpResponse.json({ access_token: "test-token", token_type: "bearer" })
  ),
  // Add more handlers as features are built
];
'''

VITEST_CONFIG = '''
// vitest.config.ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
      thresholds: {
        statements: 70,
        branches: 70,
        functions: 70,
        lines: 70,
      },
      exclude: [
        "tests/**",
        "**/*.d.ts",
        "**/*.config.*",
        "**/index.ts",    // barrel files
      ],
    },
  },
});
'''
