import { useState, useEffect } from "react";

// Role hierarchy mirrors backend core/security.py ROLE_HIERARCHY exactly.
const LEVELS: Record<string, number> = {
  super_admin: 6,
  admin: 5,
  hr: 4,
  manager: 3,
  security: 2,
  viewer: 1,
};

export const ROLE_LABELS: Record<string, string> = {
  super_admin: "Super Admin",
  admin: "Admin",
  hr: "HR",
  manager: "Manager",
  security: "Security",
  viewer: "Viewer",
};

export const ROLE_COLORS: Record<string, string> = {
  super_admin: "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300",
  admin:       "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  hr:          "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  manager:     "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
  security:    "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  viewer:      "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300",
};

/** Read the current user's role from localStorage (client-side only). */
export function getRole(): string {
  if (typeof window === "undefined") return "viewer";
  return localStorage.getItem("role") || "viewer";
}

/**
 * Returns true if the current user's role is >= the minimum required role.
 * Safe to call during SSR (returns false when window is undefined).
 */
export function hasRole(minimum: string): boolean {
  const userLevel = LEVELS[getRole()] ?? 0;
  const minLevel  = LEVELS[minimum]  ?? 99;
  return userLevel >= minLevel;
}

/**
 * React hook — reads role from localStorage after mount so SSR hydration
 * matches (false) and then flips to the real value on the client.
 * Use this in any component that conditionally renders UI based on role.
 */
export function useRole() {
  const [role, setRole] = useState("viewer");

  useEffect(() => {
    setRole(getRole());
  }, []);

  const can = (minimum: string) => (LEVELS[role] ?? 0) >= (LEVELS[minimum] ?? 99);

  return { role, can };
}
