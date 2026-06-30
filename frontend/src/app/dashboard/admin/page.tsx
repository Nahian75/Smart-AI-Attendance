"use client";
import { useEffect, useState } from "react";
import { Plus, Pencil, UserX, X, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { useRole, ROLE_LABELS, ROLE_COLORS } from "@/lib/rbac";
import DashboardShell from "@/components/ui/DashboardShell";

type UserRow = {
  id: string; email: string; full_name: string | null;
  role: string; is_active: boolean; last_login_at: string | null;
};

const ROLES = ["viewer", "security", "manager", "hr", "admin", "super_admin"] as const;

const INPUT = "w-full border dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500";
const SELECT = INPUT;

// ── Edit role modal ────────────────────────────────────────────────────────────
function EditModal({ user, onClose, onSaved }: { user: UserRow; onClose: () => void; onSaved: () => void }) {
  const [role, setRole] = useState(user.role);
  const [active, setActive] = useState(user.is_active);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function save() {
    setBusy(true); setErr("");
    try {
      await api.adminUpdateUser(user.id, { role, is_active: active });
      onSaved();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message.replace(/^API \d+: /, "") : "Failed to update.");
    } finally { setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="glass-heavy rounded-2xl w-full max-w-sm">
        <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b dark:border-gray-700">
          <h3 className="text-base font-semibold dark:text-white">Edit User</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"><X size={18} /></button>
        </div>
        <div className="px-6 py-5 space-y-4">
          <div>
            <p className="text-sm font-medium dark:text-gray-200">{user.email}</p>
            <p className="text-xs text-gray-400">{user.full_name || "—"}</p>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Role</label>
            <select value={role} onChange={e => setRole(e.target.value)} className={SELECT}>
              {ROLES.map(r => <option key={r} value={r}>{ROLE_LABELS[r] ?? r}</option>)}
            </select>
          </div>
          <label className="flex items-center gap-2 text-sm cursor-pointer dark:text-gray-300">
            <input type="checkbox" checked={active} onChange={e => setActive(e.target.checked)}
              className="rounded" />
            Active account
          </label>
          {err && <p className="text-sm text-red-600 dark:text-red-400">{err}</p>}
          <div className="flex gap-2 pt-1">
            <button onClick={onClose} className="flex-1 border dark:border-gray-600 rounded-lg py-2 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">Cancel</button>
            <button onClick={save} disabled={busy} className="flex-1 bg-blue-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
              {busy ? "Saving…" : "Save Changes"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Add user modal ──────────────────────────────────────────────────────────────
function AddModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({ email: "", password: "", full_name: "", role: "viewer" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function save() {
    if (!form.email || !form.password || !form.full_name) { setErr("All fields are required."); return; }
    if (form.password.length < 8) { setErr("Password must be at least 8 characters."); return; }
    setBusy(true); setErr("");
    try {
      await api.adminCreateUser(form);
      onSaved();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message.replace(/^API \d+: /, "") : "Failed to create user.");
    } finally { setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="glass-heavy rounded-2xl w-full max-w-sm">
        <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b dark:border-gray-700">
          <h3 className="text-base font-semibold dark:text-white">Add User</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"><X size={18} /></button>
        </div>
        <div className="px-6 py-5 space-y-3">
          {(["full_name", "email", "password"] as const).map(k => (
            <div key={k}>
              <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1 capitalize">
                {k.replace("_", " ")}
              </label>
              <input type={k === "password" ? "password" : "text"}
                value={form[k]} onChange={e => setForm(f => ({ ...f, [k]: e.target.value }))}
                className={INPUT} />
            </div>
          ))}
          <div>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Role</label>
            <select value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))} className={SELECT}>
              {ROLES.map(r => <option key={r} value={r}>{ROLE_LABELS[r] ?? r}</option>)}
            </select>
          </div>
          {err && <p className="text-sm text-red-600 dark:text-red-400">{err}</p>}
          <div className="flex gap-2 pt-1">
            <button onClick={onClose} className="flex-1 border dark:border-gray-600 rounded-lg py-2 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">Cancel</button>
            <button onClick={save} disabled={busy} className="flex-1 bg-blue-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
              {busy ? "Creating…" : "Create User"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Page ────────────────────────────────────────────────────────────────────────
export default function AdminPage() {
  const { can } = useRole();
  const [users, setUsers] = useState<UserRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<UserRow | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [err, setErr] = useState("");

  const reload = async () => {
    setLoading(true);
    try { setUsers(await api.adminUsers()); }
    catch (e: unknown) { setErr(e instanceof Error ? e.message : "Failed to load users."); }
    finally { setLoading(false); }
  };

  useEffect(() => { reload(); }, []);

  async function deactivate(u: UserRow) {
    if (!confirm(`Deactivate ${u.email}?`)) return;
    try { await api.adminDeleteUser(u.id); reload(); }
    catch (e: unknown) { setErr(e instanceof Error ? e.message.replace(/^API \d+: /, "") : "Failed."); }
  }

  return (
    <DashboardShell>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <ShieldCheck size={18} className="text-blue-600" /> User Management
          </h2>
          <p className="text-xs text-gray-400 mt-0.5">{users.length} user{users.length !== 1 ? "s" : ""}</p>
        </div>
        {can("admin") && (
          <button onClick={() => setShowAdd(true)}
            className="flex items-center gap-1.5 bg-blue-600 text-white text-sm font-medium px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors">
            <Plus size={15} /> Add User
          </button>
        )}
      </div>

      {err && <div className="mb-3 rounded-lg bg-red-50 dark:bg-red-900/20 px-3 py-2 text-sm text-red-700 dark:text-red-400">{err}</div>}

      <div className="glass rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-400 border-b dark:border-gray-700 bg-gray-50/60 dark:bg-gray-700/40">
              <th className="text-left px-4 py-3 font-medium">Name</th>
              <th className="text-left px-4 py-3 font-medium">Email</th>
              <th className="text-left px-4 py-3 font-medium">Role</th>
              <th className="text-left px-4 py-3 font-medium">Status</th>
              <th className="text-left px-4 py-3 font-medium">Last Login</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={6} className="px-4 py-10 text-center text-gray-400 text-sm">Loading…</td></tr>
            )}
            {!loading && users.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-10 text-center text-gray-400 text-sm">No users found.</td></tr>
            )}
            {users.map(u => (
              <tr key={u.id} className={`border-b dark:border-gray-700 last:border-0 hover:bg-gray-50 dark:hover:bg-gray-700/40 transition-colors ${!u.is_active ? "opacity-50" : ""}`}>
                <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{u.full_name || "—"}</td>
                <td className="px-4 py-3 text-gray-500 dark:text-gray-400 text-xs">{u.email}</td>
                <td className="px-4 py-3">
                  <span className={`inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full ${ROLE_COLORS[u.role] ?? ROLE_COLORS.viewer}`}>
                    {ROLE_LABELS[u.role] ?? u.role}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${u.is_active ? "bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400" : "bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400"}`}>
                    {u.is_active ? "Active" : "Inactive"}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-gray-400">
                  {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "Never"}
                </td>
                <td className="px-4 py-3">
                  {can("admin") && (
                    <div className="flex items-center gap-1">
                      <button onClick={() => setEditing(u)} title="Edit role"
                        className="p-1.5 rounded text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/30 transition-colors">
                        <Pencil size={13} />
                      </button>
                      {u.is_active && (
                        <button onClick={() => deactivate(u)} title="Deactivate"
                          className="p-1.5 rounded text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors">
                          <UserX size={13} />
                        </button>
                      )}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && <EditModal user={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload(); }} />}
      {showAdd && <AddModal onClose={() => setShowAdd(false)} onSaved={() => { setShowAdd(false); reload(); }} />}
    </DashboardShell>
  );
}
