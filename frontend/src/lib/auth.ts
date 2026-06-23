export function saveSession(token: string, tenantId: string, role: string) {
  localStorage.setItem("token", token);
  localStorage.setItem("tenant_id", tenantId);
  localStorage.setItem("role", role);
}
export function getSession() {
  if (typeof window === "undefined") return null;
  const token = localStorage.getItem("token");
  if (!token) return null;
  return {
    token,
    tenantId: localStorage.getItem("tenant_id") || "",
    role: localStorage.getItem("role") || "viewer",
  };
}
export function clearSession() {
  localStorage.clear();
}
