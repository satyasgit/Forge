"""
Frontend skill: React + TypeScript patterns and conventions.
Injected into FrontendAgent system prompt context.
"""

REACT_COMPONENT_TEMPLATE = '''
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { FC } from "react";

// 1. Types first — always in a separate .types.ts or at top
interface {ComponentName}Props {
  id: string;
  onSuccess?: () => void;
}

interface {ResourceType} {
  id: string;
  createdAt: string;
  // ... fields
}

// 2. API function — separate from component
async function fetch{ResourceType}(id: string): Promise<{ResourceType}> {
  const res = await fetch(`/api/{resource}/${id}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// 3. Component — named export + default export
export const {ComponentName}: FC<{ComponentName}Props> = ({ id, onSuccess }) => {
  const queryClient = useQueryClient();

  // 4. Data fetching — React Query
  const { data, isLoading, error } = useQuery({
    queryKey: ["{resource}", id],
    queryFn: () => fetch{ResourceType}(id),
    staleTime: 60_000,
  });

  const mutation = useMutation({
    mutationFn: (payload: Partial<{ResourceType}>) =>
      fetch(`/api/{resource}/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }).then(r => r.json()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["{resource}", id] });
      onSuccess?.();
    },
  });

  // 5. Loading state
  if (isLoading) {
    return (
      <div className="animate-pulse" aria-label="Loading..." role="status">
        <div className="h-4 bg-gray-200 rounded w-3/4 mb-2" />
        <div className="h-4 bg-gray-200 rounded w-1/2" />
      </div>
    );
  }

  // 6. Error state
  if (error) {
    return (
      <div role="alert" className="text-red-600 text-sm p-3 bg-red-50 rounded-md">
        {error instanceof Error ? error.message : "Something went wrong"}
      </div>
    );
  }

  // 7. Empty state
  if (!data) {
    return <p className="text-gray-500 text-sm">No data found.</p>;
  }

  // 8. Happy path
  return (
    <div className="space-y-4">
      {/* content */}
    </div>
  );
};

export default {ComponentName};
'''

REACT_FORM_TEMPLATE = '''
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

// 1. Zod schema — single source of truth for validation
const {FormName}Schema = z.object({
  email: z.string().email("Invalid email"),
  password: z.string().min(8, "Min 8 characters"),
});

type {FormName}Values = z.infer<typeof {FormName}Schema>;

export function {FormName}({ onSubmit }: { onSubmit: (v: {FormName}Values) => Promise<void> }) {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<{FormName}Values>({ resolver: zodResolver({FormName}Schema) });

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4">
      <div>
        <label htmlFor="email" className="block text-sm font-medium text-gray-700">
          Email
        </label>
        <input
          {...register("email")}
          id="email"
          type="email"
          autoComplete="email"
          aria-describedby={errors.email ? "email-error" : undefined}
          className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2
                     focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        {errors.email && (
          <p id="email-error" role="alert" className="mt-1 text-sm text-red-600">
            {errors.email.message}
          </p>
        )}
      </div>

      <button
        type="submit"
        disabled={isSubmitting}
        aria-busy={isSubmitting}
        className="w-full rounded-md bg-blue-600 px-4 py-2 text-white
                   hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {isSubmitting ? "Submitting..." : "Submit"}
      </button>
    </form>
  );
}
'''

REACT_QUERY_KEYS = '''
// queryKeys.ts — centralised query key factory
// Prevents typos and makes invalidation predictable

export const queryKeys = {
  users: {
    all: ["users"] as const,
    lists: () => [...queryKeys.users.all, "list"] as const,
    list: (filters: Record<string, unknown>) => [...queryKeys.users.lists(), filters] as const,
    details: () => [...queryKeys.users.all, "detail"] as const,
    detail: (id: string) => [...queryKeys.users.details(), id] as const,
  },
  // Add more resources here
} as const;
'''

TAILWIND_CONVENTIONS = {
    "layout": "Use flex/grid with gap-* not margin between siblings",
    "spacing": "Use p-4, p-6, p-8 inside containers. gap-3, gap-4 between items.",
    "text": "text-sm for secondary, text-base for body, text-lg+ for headings",
    "colors": "text-gray-900 primary, text-gray-600 secondary, text-gray-400 disabled",
    "interactive": "hover:bg-gray-50 on cards, hover:text-blue-600 on links",
    "focus": "focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2",
    "animations": "transition-colors duration-150 for colour changes, transition-transform for scale",
    "dark_mode": "Use dark: prefix variants, set darkMode: 'class' in tailwind.config",
}

ACCESSIBILITY_CHECKLIST = [
    "All images have meaningful alt text (or alt='' for decorative)",
    "All form inputs have associated <label> elements",
    "Error messages use role='alert' and aria-describedby",
    "Buttons have descriptive text (not just 'Click here')",
    "Modals trap focus and close on Escape",
    "Colour contrast ratio >= 4.5:1 for normal text, 3:1 for large",
    "Interactive elements are reachable and operable by keyboard",
    "Loading states use aria-busy and role='status'",
    "Page has a single <h1> and logical heading hierarchy",
]
