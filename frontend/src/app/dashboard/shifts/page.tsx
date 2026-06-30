"use client";
import { useEffect, useState } from "react";
import { Clock, Plus, Pencil, Trash2, X, UserCheck, UserX } from "lucide-react";
import { api, type ShiftRow, type ShiftPayload, type AssignmentRow } from "@/lib/api";
import { useRole } from "@/lib/rbac";
import DashboardShell from "@/components/ui/DashboardShell";

const DAYS_MAP = [
  { val: 1, label: "Mon" }, { val: 2, label: "Tue" }, { val: 3, label: "Wed" },
  { val: 4, label: "Thu" }, { val: 5, label: "Fri" }, { val: 6, label: "Sat" },
  { val: 7, label: "Sun" },
];

const EMPTY: ShiftPayload = {
  name: "", start_time: "09:00", end_time: "18:00",
  grace_in_min: 10, early_out_min: 15,
  work_days: [1, 2, 3, 4, 5],
};

const INPUT = "w-full border dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500";
const LABEL = "block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1";

// ── Shift form modal ──────────────────────────────────────────────────────────
function ShiftModal({ initial, onClose, onSaved }: {
  initial?: ShiftRow; onClose: () => void; onSaved: () => void;
}) {
  const [form, setForm] = useState<ShiftPayload>(
    initial
      ? { name: initial.name, start_time: initial.start_time, end_time: initial.end_time,
          grace_in_min: initial.grace_in_min, early_out_min: initial.early_out_min,
          work_days: initial.work_days }
      : EMPTY
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  function toggleDay(d: number) {
    setForm(f => ({
      ...f,
      work_days: f.work_days.includes(d)
        ? f.work_days.filter(x => x !== d)
        : [...f.work_days, d].sort(),
    }));
  }

  async function save() {
    if (!form.name.trim()) { setErr("Shift name is required."); return; }
    if (form.work_days.length === 0) { setErr("Select at least one work day."); return; }
    setBusy(true); setErr("");
    try {
      if (initial) await api.updateShift(initial.id, form);
      else await api.createShift(form);
      onSaved();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message.replace(/^API \d+: /, "") : "Failed to save.");
    } finally { setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="glass-heavy rounded-2xl w-full max-w-md">
        <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b dark:border-gray-700">
          <h3 className="text-base font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <Clock size={16} className="text-blue-600" />
            {initial ? "Edit Shift" : "Create New Shift"}
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"><X size={18} /></button>
        </div>

        <div className="px-6 py-5 space-y-4">
          {/* Name */}
          <div>
            <label className={LABEL}>Shift Name</label>
            <input className={INPUT} value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder="e.g. Morning Shift, Night Shift" />
          </div>

          {/* Times */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={LABEL}>Start Time</label>
              <input type="time" className={INPUT} value={form.start_time}
                onChange={e => setForm(f => ({ ...f, start_time: e.target.value }))} />
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">When shift begins</p>
            </div>
            <div>
              <label className={LABEL}>End Time</label>
              <input type="time" className={INPUT} value={form.end_time}
                onChange={e => setForm(f => ({ ...f, end_time: e.target.value }))} />
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">When shift ends</p>
            </div>
          </div>

          {/* Grace periods */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={LABEL}>Grace Period (minutes)</label>
              <input type="number" min={0} max={120} className={INPUT}
                value={form.grace_in_min}
                onChange={e => setForm(f => ({ ...f, grace_in_min: +e.target.value }))} />
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                Check-in up to <strong>{form.grace_in_min} min</strong> late = not marked late
              </p>
            </div>
            <div>
              <label className={LABEL}>Early Leave Buffer (minutes)</label>
              <input type="number" min={0} max={120} className={INPUT}
                value={form.early_out_min}
                onChange={e => setForm(f => ({ ...f, early_out_min: +e.target.value }))} />
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                Leave up to <strong>{form.early_out_min} min</strong> early = not flagged
              </p>
            </div>
          </div>

          {/* Work days */}
          <div>
            <label className={LABEL}>Work Days</label>
            <div className="flex gap-2 flex-wrap">
              {DAYS_MAP.map(d => (
                <button key={d.val} type="button"
                  onClick={() => toggleDay(d.val)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                    form.work_days.includes(d.val)
                      ? "bg-blue-600 text-white border-blue-600"
                      : "bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:border-blue-400"
                  }`}>
                  {d.label}
                </button>
              ))}
            </div>
          </div>

          {/* Summary */}
          <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg px-3 py-2.5 text-xs text-blue-700 dark:text-blue-300 space-y-0.5">
            <p><strong>Late if check-in after:</strong> {form.start_time} + {form.grace_in_min} min = {addMinutes(form.start_time, form.grace_in_min)}</p>
            <p><strong>Early leave if check-out before:</strong> {form.end_time} − {form.early_out_min} min = {subtractMinutes(form.end_time, form.early_out_min)}</p>
            <p><strong>Overtime if check-out after:</strong> {form.end_time}</p>
          </div>

          {err && <p className="text-sm text-red-600 dark:text-red-400">{err}</p>}

          <div className="flex gap-2 pt-1">
            <button onClick={onClose} className="flex-1 border dark:border-gray-600 rounded-lg py-2 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">
              Cancel
            </button>
            <button onClick={save} disabled={busy}
              className="flex-1 bg-blue-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
              {busy ? "Saving…" : initial ? "Save Changes" : "Create Shift"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Assign shift modal ────────────────────────────────────────────────────────
function AssignModal({ shifts, onClose, onSaved }: {
  shifts: ShiftRow[]; onClose: () => void; onSaved: () => void;
}) {
  const [employees, setEmployees] = useState<{ id: string; full_name: string; employee_code: string | null }[]>([]);
  const [empId, setEmpId] = useState("");
  const [shiftId, setShiftId] = useState(shifts[0]?.id || "");
  const [from, setFrom] = useState(new Date().toISOString().slice(0, 10));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.employees().then(setEmployees).catch(() => {});
  }, []);

  async function save() {
    if (!empId || !shiftId) { setErr("Select an employee and a shift."); return; }
    setBusy(true); setErr("");
    try {
      await api.assignShift({ employee_id: empId, shift_id: shiftId, effective_from: from });
      onSaved();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message.replace(/^API \d+: /, "") : "Failed to assign.");
    } finally { setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="glass-heavy rounded-2xl w-full max-w-sm">
        <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b dark:border-gray-700">
          <h3 className="text-base font-semibold text-gray-900 dark:text-white">Assign Shift</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"><X size={18} /></button>
        </div>
        <div className="px-6 py-5 space-y-3">
          <div>
            <label className={LABEL}>Employee</label>
            <select value={empId} onChange={e => setEmpId(e.target.value)} className={INPUT}>
              <option value="">— select employee —</option>
              {employees.map(e => (
                <option key={e.id} value={e.id}>
                  {e.full_name}{e.employee_code ? ` (${e.employee_code})` : ""}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={LABEL}>Shift</label>
            <select value={shiftId} onChange={e => setShiftId(e.target.value)} className={INPUT}>
              {shifts.map(s => (
                <option key={s.id} value={s.id}>
                  {s.name} · {s.start_time}–{s.end_time}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={LABEL}>Effective From</label>
            <input type="date" value={from} onChange={e => setFrom(e.target.value)} className={INPUT} />
          </div>
          {err && <p className="text-sm text-red-600 dark:text-red-400">{err}</p>}
          <div className="flex gap-2 pt-1">
            <button onClick={onClose} className="flex-1 border dark:border-gray-600 rounded-lg py-2 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">Cancel</button>
            <button onClick={save} disabled={busy}
              className="flex-1 bg-blue-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
              {busy ? "Assigning…" : "Assign"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Time helpers ──────────────────────────────────────────────────────────────
function addMinutes(t: string, m: number) {
  const [h, min] = t.split(":").map(Number);
  const total = h * 60 + min + m;
  return `${String(Math.floor(total / 60) % 24).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}
function subtractMinutes(t: string, m: number) {
  const [h, min] = t.split(":").map(Number);
  const total = h * 60 + min - m;
  const pos = ((total % 1440) + 1440) % 1440;
  return `${String(Math.floor(pos / 60)).padStart(2, "0")}:${String(pos % 60).padStart(2, "0")}`;
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function ShiftsPage() {
  const { can } = useRole();
  const [shifts, setShifts] = useState<ShiftRow[]>([]);
  const [assignments, setAssignments] = useState<AssignmentRow[]>([]);
  const [editing, setEditing] = useState<ShiftRow | undefined>();
  const [showCreate, setShowCreate] = useState(false);
  const [showAssign, setShowAssign] = useState(false);
  const [err, setErr] = useState("");

  const reload = async () => {
    try {
      const [s, a] = await Promise.all([api.shifts(), api.shiftAssignments()]);
      setShifts(s); setAssignments(a);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Failed to load.");
    }
  };

  useEffect(() => { reload(); }, []);

  async function removeAssignment(empId: string, empName: string) {
    if (!confirm(`Remove shift from ${empName}?`)) return;
    try { await api.removeAssignment(empId); reload(); }
    catch (e: unknown) { setErr(e instanceof Error ? e.message : "Failed."); }
  }

  async function del(s: ShiftRow) {
    if (!confirm(`Delete shift "${s.name}"? Employees assigned to it will have no shift.`)) return;
    try { await api.deleteShift(s.id); reload(); }
    catch (e: unknown) { setErr(e instanceof Error ? e.message : "Failed."); }
  }

  return (
    <DashboardShell>
      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <Clock size={18} className="text-blue-600" /> Shift Management
          </h2>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
            Shifts control late-arrival, early-leave, and overtime detection
          </p>
        </div>
        {can("hr") && (
          <div className="flex gap-2">
            <button onClick={() => setShowAssign(true)}
              className="flex items-center gap-1.5 border dark:border-gray-600 text-gray-700 dark:text-gray-300 text-sm px-3 py-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
              <UserCheck size={14} /> Assign Employee
            </button>
            <button onClick={() => setShowCreate(true)}
              className="flex items-center gap-1.5 bg-blue-600 text-white text-sm font-medium px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors">
              <Plus size={14} /> New Shift
            </button>
          </div>
        )}
      </div>

      {err && <div className="rounded-lg bg-red-50 dark:bg-red-900/20 px-3 py-2 text-sm text-red-700 dark:text-red-400">{err}</div>}

      {/* ── How it works banner ── */}
      <div className="bg-blue-50 dark:bg-blue-900/20 rounded-xl border border-blue-100 dark:border-blue-800 px-4 py-3 text-sm text-blue-700 dark:text-blue-300 space-y-1">
        <p className="font-medium">How shift times control attendance detection:</p>
        <div className="grid grid-cols-3 gap-2 text-xs mt-1">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-2">
            <p className="font-medium text-amber-600 dark:text-amber-400">Late Arrival</p>
            <p>Check-in after <strong>Start + Grace period</strong></p>
            <p className="text-gray-500 dark:text-gray-400">e.g. 9:00 + 10 min → late after 9:10</p>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-2">
            <p className="font-medium text-orange-600 dark:text-orange-400">Early Leave</p>
            <p>Check-out before <strong>End − Buffer</strong></p>
            <p className="text-gray-500 dark:text-gray-400">e.g. 18:00 − 15 min → early before 17:45</p>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-2">
            <p className="font-medium text-purple-600 dark:text-purple-400">Overtime</p>
            <p>Check-out after <strong>End Time</strong></p>
            <p className="text-gray-500 dark:text-gray-400">Seconds past shift end are recorded</p>
          </div>
        </div>
      </div>

      {/* ── Shifts list ── */}
      <div className="glass rounded-xl">
        <div className="px-4 py-3 border-b dark:border-gray-700 text-sm font-medium text-gray-900 dark:text-white">
          Shifts ({shifts.length})
        </div>
        {shifts.length === 0 ? (
          <div className="py-12 text-center text-gray-400 dark:text-gray-500">
            <Clock className="mx-auto mb-2 opacity-30" size={36} />
            <p className="text-sm">No shifts yet</p>
            {can("hr") && <p className="text-xs mt-1">Click <strong>New Shift</strong> to create your first shift.</p>}
          </div>
        ) : (
          <div className="divide-y dark:divide-gray-700">
            {shifts.map(s => {
              const assigned = assignments.filter(a => a.shift_id === s.id).length;
              return (
                <div key={s.id} className="px-4 py-4 flex items-start justify-between hover:bg-gray-50 dark:hover:bg-gray-700/40 transition-colors">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium text-gray-900 dark:text-white">{s.name}</span>
                      <span className="text-xs bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 px-2 py-0.5 rounded-full font-mono">
                        {s.start_time} – {s.end_time}
                      </span>
                      {assigned > 0 && (
                        <span className="text-xs bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400 px-2 py-0.5 rounded-full">
                          {assigned} employee{assigned !== 1 ? "s" : ""}
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-3 text-xs text-gray-500 dark:text-gray-400">
                      <span>Grace: <strong className="text-amber-600 dark:text-amber-400">{s.grace_in_min} min</strong> → late after {addMinutes(s.start_time, s.grace_in_min)}</span>
                      <span>Early leave before: <strong className="text-orange-600 dark:text-orange-400">{subtractMinutes(s.end_time, s.early_out_min)}</strong> ({s.early_out_min} min buffer)</span>
                      <span>Days: <strong>{s.work_days_label.join(", ")}</strong></span>
                    </div>
                  </div>
                  {can("hr") && (
                    <div className="flex items-center gap-1 ml-4">
                      <button onClick={() => setEditing(s)} title="Edit shift"
                        className="p-1.5 rounded text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/30 transition-colors">
                        <Pencil size={13} />
                      </button>
                      <button onClick={() => del(s)} title="Delete shift"
                        className="p-1.5 rounded text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors">
                        <Trash2 size={13} />
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Employee assignments ── */}
      <div className="glass rounded-xl">
        <div className="px-4 py-3 border-b dark:border-gray-700 text-sm font-medium text-gray-900 dark:text-white">
          Employee Shift Assignments ({assignments.length})
        </div>
        {assignments.length === 0 ? (
          <div className="py-8 text-center text-gray-400 dark:text-gray-500 text-sm">
            No employees assigned to any shift yet.
            {can("hr") && <> Click <strong>Assign Employee</strong> above.</>}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-gray-400 dark:text-gray-500 border-b dark:border-gray-700 bg-gray-50/60 dark:bg-gray-700/40">
                <th className="text-left px-4 py-2 font-medium">Employee</th>
                <th className="text-left px-4 py-2 font-medium">Shift</th>
                <th className="text-left px-4 py-2 font-medium">Hours</th>
                <th className="text-left px-4 py-2 font-medium">Effective From</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {assignments.map(a => (
                <tr key={a.employee_id} className="border-b dark:border-gray-700 last:border-0 hover:bg-gray-50 dark:hover:bg-gray-700/40 transition-colors">
                  <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">
                    {a.employee_name}
                    {a.employee_code && <span className="ml-1.5 text-xs text-gray-400 dark:text-gray-500 font-normal font-mono">({a.employee_code})</span>}
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-xs bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 px-2 py-0.5 rounded-full font-medium">
                      {a.shift_name}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-gray-600 dark:text-gray-300">
                    {a.shift_start} – {a.shift_end}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500 dark:text-gray-400">
                    {new Date(a.effective_from).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    {can("hr") && (
                      <button onClick={() => removeAssignment(a.employee_id, a.employee_name)}
                        title="Remove shift assignment"
                        className="p-1.5 rounded text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors">
                        <UserX size={13} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Modals */}
      {showCreate && <ShiftModal onClose={() => setShowCreate(false)} onSaved={() => { setShowCreate(false); reload(); }} />}
      {editing && <ShiftModal initial={editing} onClose={() => setEditing(undefined)} onSaved={() => { setEditing(undefined); reload(); }} />}
      {showAssign && shifts.length > 0 && (
        <AssignModal shifts={shifts} onClose={() => setShowAssign(false)} onSaved={() => { setShowAssign(false); reload(); }} />
      )}
    </DashboardShell>
  );
}
