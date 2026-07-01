"use client";
import { useEffect, useState, useRef, useCallback } from "react";
import {
  Star, AlertTriangle, Plus, Pencil, Trash2, Camera, X, Upload, CheckCircle,
  RefreshCw, Crosshair,
} from "lucide-react";
import { api } from "@/lib/api";
import { useRole } from "@/lib/rbac";
import DashboardShell from "@/components/ui/DashboardShell";
import type { Employee, Camera as CameraType } from "@/types";

type FormState = {
  full_name: string;
  employee_code: string;
  email: string;
  phone: string;
  department: string;
  designation: string;
};

const EMPTY_FORM: FormState = {
  full_name: "", employee_code: "", email: "", phone: "", department: "", designation: "",
};

type EnrollEntry = { file: File; status: "pending" | "ok" | "error"; msg?: string };

export default function EmployeesPage() {
  const { can } = useRole();
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(true);

  // ── Add / Edit modal ──────────────────────────────────────────────────────
  const [showAddEdit, setShowAddEdit] = useState(false);
  const [editTarget, setEditTarget] = useState<Employee | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [formError, setFormError] = useState("");
  const [formBusy, setFormBusy] = useState(false);

  // ── Face enrollment modal ─────────────────────────────────────────────────
  const [enrollTarget, setEnrollTarget] = useState<Employee | null>(null);
  const [enrollTab, setEnrollTab] = useState<"upload" | "camera">("upload");
  const [enrollList, setEnrollList] = useState<EnrollEntry[]>([]);
  const [enrolling, setEnrolling] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // ── Camera enrollment state ───────────────────────────────────────────────
  const [cameras, setCameras] = useState<CameraType[]>([]);
  const [camId, setCamId] = useState<string>("");
  const [snapshot, setSnapshot] = useState<string | null>(null);  // object URL
  const [snapLoading, setSnapLoading] = useState(false);
  const [snapError, setSnapError] = useState("");
  const [selection, setSelection] = useState<{ x: number; y: number; w: number; h: number } | null>(null);
  const [dragging, setDragging] = useState<{ startX: number; startY: number } | null>(null);
  const [camEnrolling, setCamEnrolling] = useState(false);
  const [camEnrollMsg, setCamEnrollMsg] = useState("");
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try { setEmployees(await api.employees()); }
    catch { /* silently ignore on background reloads */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  // ── Add / Edit helpers ────────────────────────────────────────────────────
  const openAdd = () => {
    setEditTarget(null);
    setForm(EMPTY_FORM);
    setFormError("");
    setShowAddEdit(true);
  };

  const openEdit = (emp: Employee) => {
    setEditTarget(emp);
    setForm({
      full_name: emp.full_name,
      employee_code: emp.employee_code ?? "",
      email: emp.email ?? "",
      phone: emp.phone ?? "",
      department: emp.department ?? "",
      designation: emp.designation ?? "",
    });
    setFormError("");
    setShowAddEdit(true);
  };

  const submitForm = async () => {
    if (!form.full_name.trim()) { setFormError("Full name is required."); return; }
    setFormBusy(true); setFormError("");
    try {
      if (editTarget) {
        await api.updateEmployee(editTarget.id, form);
      } else {
        await api.createEmployee(form);
      }
      setShowAddEdit(false);
      reload();
    } catch (e: unknown) {
      setFormError(e instanceof Error ? e.message : "Failed to save employee.");
    } finally {
      setFormBusy(false);
    }
  };

  const deactivate = async (emp: Employee) => {
    if (!confirm(`Deactivate ${emp.full_name}? They will no longer appear in attendance reports.`)) return;
    await api.deleteEmployee(emp.id);
    reload();
  };

  const toggleBL = async (emp: Employee) => {
    try { await api.setBlacklist(emp.id, !emp.is_blacklisted); reload(); }
    catch (e) { alert(e instanceof Error ? e.message : "Failed to update blacklist status."); }
  };
  const toggleVIP = async (emp: Employee) => {
    try { await api.setVip(emp.id, !emp.is_vip); reload(); }
    catch (e) { alert(e instanceof Error ? e.message : "Failed to update VIP status."); }
  };

  // ── Enrollment helpers ────────────────────────────────────────────────────
  const openEnroll = (emp: Employee) => {
    setEnrollTarget(emp);
    setEnrollList([]);
    setEnrollTab("upload");
    setSnapshot(null);
    setSelection(null);
    setSnapError("");
    setCamEnrollMsg("");
    api.cameras().then(list => {
      setCameras(list);
      if (list.length > 0) setCamId(list[0].id);
    }).catch(() => {});
  };

  const addFiles = (files: FileList | null) => {
    if (!files) return;
    const fresh = Array.from(files)
      .filter(f => f.type.startsWith("image/"))
      .map<EnrollEntry>(f => ({ file: f, status: "pending" }));
    setEnrollList(prev => [...prev, ...fresh].slice(0, 10));
  };

  const removeFile = (idx: number) => setEnrollList(prev => prev.filter((_, i) => i !== idx));

  const runEnrollment = async () => {
    if (!enrollTarget || enrollList.length === 0) return;
    setEnrolling(true);
    for (let i = 0; i < enrollList.length; i++) {
      if (enrollList[i].status === "ok") continue;
      try {
        await api.enrollFace(enrollTarget.id, enrollList[i].file);
        setEnrollList(prev => prev.map((e, idx) => idx === i ? { ...e, status: "ok" } : e));
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Upload failed";
        setEnrollList(prev => prev.map((e, idx) => idx === i ? { ...e, status: "error", msg } : e));
      }
    }
    setEnrolling(false);
    reload();
  };

  const enrollDone = enrollList.length > 0 && enrollList.every(e => e.status !== "pending");
  const okCount = enrollList.filter(e => e.status === "ok").length;

  // ── Camera enrollment helpers ─────────────────────────────────────────────
  const captureSnapshot = async () => {
    if (!camId) return;
    setSnapLoading(true); setSnapError(""); setSnapshot(null); setSelection(null); setCamEnrollMsg("");
    try {
      const blob = await api.cameraPreview(camId);
      if (snapshot) URL.revokeObjectURL(snapshot);
      setSnapshot(URL.createObjectURL(blob));
    } catch {
      setSnapError("Could not fetch snapshot. Make sure the camera is online.");
    } finally {
      setSnapLoading(false);
    }
  };

  const drawCanvas = useCallback((sel: typeof selection) => {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    if (sel) {
      ctx.strokeStyle = "#6366f1";
      ctx.lineWidth = 2;
      ctx.setLineDash([4, 3]);
      ctx.strokeRect(sel.x, sel.y, sel.w, sel.h);
      ctx.fillStyle = "rgba(99,102,241,0.12)";
      ctx.fillRect(sel.x, sel.y, sel.w, sel.h);
    }
  }, []);

  const getCanvasPos = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const onMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const p = getCanvasPos(e);
    setDragging({ startX: p.x, startY: p.y });
    setSelection(null);
    setCamEnrollMsg("");
  };

  const onMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!dragging) return;
    const p = getCanvasPos(e);
    const sel = {
      x: Math.min(dragging.startX, p.x),
      y: Math.min(dragging.startY, p.y),
      w: Math.abs(p.x - dragging.startX),
      h: Math.abs(p.y - dragging.startY),
    };
    setSelection(sel);
    drawCanvas(sel);
  };

  const onMouseUp = () => setDragging(null);

  const enrollFromCamera = async () => {
    if (!enrollTarget || !snapshot || !selection || selection.w < 10 || selection.h < 10) return;
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img) return;

    // Extract the selected region at original image resolution
    const scaleX = img.naturalWidth / canvas.width;
    const scaleY = img.naturalHeight / canvas.height;
    const off = document.createElement("canvas");
    off.width  = Math.round(selection.w * scaleX);
    off.height = Math.round(selection.h * scaleY);
    off.getContext("2d")!.drawImage(
      img,
      selection.x * scaleX, selection.y * scaleY,
      off.width, off.height,
      0, 0, off.width, off.height,
    );

    setCamEnrolling(true); setCamEnrollMsg("");
    off.toBlob(async (blob) => {
      if (!blob) { setCamEnrolling(false); return; }
      const file = new File([blob], "camera_face.jpg", { type: "image/jpeg" });
      try {
        await api.enrollFace(enrollTarget.id, file);
        setCamEnrollMsg("✓ Enrolled from camera successfully! Edge nodes sync within 60s.");
        reload();
      } catch (err) {
        setCamEnrollMsg(`✗ ${err instanceof Error ? err.message : "Enrollment failed"}`);
      } finally {
        setCamEnrolling(false);
      }
    }, "image/jpeg", 0.95);
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <DashboardShell>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-6">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Employees</h2>
          <p className="text-xs text-gray-400 mt-0.5">{employees.length} total</p>
        </div>
        {can("hr") && (
          <button onClick={openAdd}
            className="flex items-center gap-1.5 bg-blue-600 text-white text-sm font-medium px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors">
            <Plus size={15} /> Add Employee
          </button>
        )}
      </div>

      <div className="glass rounded-xl overflow-x-auto">
        <table className="w-full text-sm min-w-[860px]">
          <thead>
            <tr className="text-xs text-gray-400 dark:text-gray-500 border-b dark:border-gray-700 bg-gray-50/60 dark:bg-gray-700/40">
              <th className="text-left px-4 py-3 font-medium">Name</th>
              <th className="text-left px-4 py-3 font-medium">Code</th>
              <th className="text-left px-4 py-3 font-medium">Email</th>
              <th className="text-left px-4 py-3 font-medium">Phone</th>
              <th className="text-left px-4 py-3 font-medium">Department</th>
              <th className="text-left px-4 py-3 font-medium">Designation</th>
              <th className="text-left px-4 py-3 font-medium">Face</th>
              <th className="text-left px-4 py-3 font-medium">Flags</th>
              <th className="text-left px-4 py-3 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={9} className="px-4 py-10 text-center text-gray-400 text-sm">
                  Loading employees…
                </td>
              </tr>
            )}
            {!loading && employees.length === 0 && (
              <tr>
                <td colSpan={9} className="px-4 py-14 text-center">
                  <Camera className="mx-auto text-gray-200 mb-3" size={36} />
                  <p className="text-sm text-gray-500 font-medium">No employees yet</p>
                  <p className="text-xs text-gray-400 mt-1">
                    Click <strong>Add Employee</strong> to create your first real employee record.
                  </p>
                </td>
              </tr>
            )}
            {employees.map(emp => (
              <tr key={emp.id} className={`border-b dark:border-gray-700 last:border-0 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors ${!emp.is_active ? "opacity-50" : ""}`}>
                <td className="px-4 py-3">
                  <span className="font-medium text-gray-900 dark:text-white">{emp.full_name || "—"}</span>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-gray-500">{emp.employee_code || "—"}</td>
                <td className="px-4 py-3 text-gray-500 text-xs">{emp.email || "—"}</td>
                <td className="px-4 py-3 text-gray-500 text-xs">{emp.phone || "—"}</td>
                <td className="px-4 py-3 text-gray-600 text-xs">{emp.department || "—"}</td>
                <td className="px-4 py-3 text-gray-500 text-xs">{emp.designation || "—"}</td>
                <td className="px-4 py-3">
                  {emp.is_enrolled
                    ? <span className="inline-flex items-center gap-1 text-xs bg-green-50 text-green-700 px-2 py-0.5 rounded-full border border-green-100">
                        <CheckCircle size={10} /> Enrolled
                      </span>
                    : <span className="text-xs bg-gray-100 text-gray-400 px-2 py-0.5 rounded-full">
                        Not enrolled
                      </span>}
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {emp.is_blacklisted && <span className="text-xs bg-red-100 text-red-700 px-1.5 py-0.5 rounded font-medium">Blacklist</span>}
                    {emp.is_vip && <span className="text-xs bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded font-medium">VIP</span>}
                    {!emp.is_active && <span className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">Inactive</span>}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1">
                    {can("hr") && (
                      <ActionBtn onClick={() => openEdit(emp)} title="Edit employee" color="blue">
                        <Pencil size={13} />
                      </ActionBtn>
                    )}
                    {can("hr") && (
                      <ActionBtn onClick={() => openEnroll(emp)} title={emp.is_enrolled ? "Re-enroll face" : "Enroll face"} color={emp.is_enrolled ? "green" : "indigo"}>
                        <Camera size={13} />
                      </ActionBtn>
                    )}
                    {can("admin") && (
                      <ActionBtn onClick={() => toggleBL(emp)} title={emp.is_blacklisted ? "Remove from blacklist" : "Add to blacklist"}
                        color="red" active={emp.is_blacklisted}>
                        <AlertTriangle size={13} />
                      </ActionBtn>
                    )}
                    {can("admin") && (
                      <ActionBtn onClick={() => toggleVIP(emp)} title={emp.is_vip ? "Remove VIP" : "Mark as VIP"}
                        color="amber" active={emp.is_vip}>
                        <Star size={13} />
                      </ActionBtn>
                    )}
                    {can("hr") && (
                      <ActionBtn onClick={() => deactivate(emp)} title="Deactivate employee" color="red">
                        <Trash2 size={13} />
                      </ActionBtn>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ── Add / Edit Modal ──────────────────────────────────────────────── */}
      {showAddEdit && (
        <Modal onClose={() => setShowAddEdit(false)}
          title={editTarget ? "Edit Employee" : "Add New Employee"}>

          {/* Suggestion lists for autocomplete */}
          <datalist id="dept-list">
            {BD_DEPARTMENTS.map(d => <option key={d} value={d} />)}
          </datalist>
          <datalist id="desg-list">
            {BD_DESIGNATIONS.map(d => <option key={d} value={d} />)}
          </datalist>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Full Name *" span={2} hint="e.g. Md. Karim Hossain, Fatima Begum">
              <input className={INPUT}
                value={form.full_name}
                onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))}
                placeholder="Md. Karim Hossain" />
            </Field>
            <Field label="Employee Code" hint="e.g. EMP-001, DHK-042">
              <input className={INPUT}
                value={form.employee_code}
                onChange={e => setForm(f => ({ ...f, employee_code: e.target.value }))}
                placeholder="EMP-001" />
            </Field>
            <Field label="Department" hint="Start typing to see suggestions">
              <input list="dept-list" className={INPUT}
                value={form.department}
                onChange={e => setForm(f => ({ ...f, department: e.target.value }))}
                placeholder="e.g. Software Engineering" />
            </Field>
            <Field label="Designation" span={2} hint="Start typing to see suggestions">
              <input list="desg-list" className={INPUT}
                value={form.designation}
                onChange={e => setForm(f => ({ ...f, designation: e.target.value }))}
                placeholder="e.g. Senior Software Engineer" />
            </Field>
            <Field label="Email" hint="Work email address">
              <input type="email" className={INPUT}
                value={form.email}
                onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                placeholder="karim@company.com.bd" />
            </Field>
            <Field label="Mobile Number" hint="Bangladeshi: +880 1XXX-XXXXXX">
              <input className={INPUT}
                value={form.phone}
                onChange={e => setForm(f => ({ ...f, phone: e.target.value }))}
                placeholder="+880 1711-000000" />
            </Field>
          </div>
          {formError && <p className="mt-3 text-sm text-red-600 dark:text-red-400">{formError}</p>}
          <div className="flex justify-end gap-2 mt-5">
            <button onClick={() => setShowAddEdit(false)}
              className="px-4 py-2 text-sm border dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 dark:text-gray-300 transition-colors">
              Cancel
            </button>
            <button onClick={submitForm} disabled={formBusy}
              className="px-5 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors font-medium">
              {formBusy ? "Saving…" : editTarget ? "Save Changes" : "Add Employee"}
            </button>
          </div>
        </Modal>
      )}

      {/* ── Face Enrollment Modal ─────────────────────────────────────────── */}
      {enrollTarget && (
        <Modal onClose={() => { setEnrollTarget(null); if (snapshot) URL.revokeObjectURL(snapshot); }}
          title={`Enroll Face — ${enrollTarget.full_name}`} wide>

          {/* Tabs */}
          <div className="flex gap-1 bg-gray-100 dark:bg-gray-700 rounded-lg p-1 mb-5">
            {(["upload", "camera"] as const).map(tab => (
              <button key={tab} onClick={() => setEnrollTab(tab)}
                className={`flex-1 text-xs py-1.5 rounded-md font-medium transition-colors ${
                  enrollTab === tab
                    ? "bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow-sm"
                    : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                }`}>
                {tab === "upload" ? "📁 Upload Photos" : "📷 From Camera (CCTV)"}
              </button>
            ))}
          </div>

          {/* ── Upload tab ── */}
          {enrollTab === "upload" && (
            <>
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                Best for frontal cameras — upload 3–5 clear face photos taken under the same lighting as your entrance camera.
              </p>
              <div
                role="button" tabIndex={0}
                onClick={() => fileRef.current?.click()}
                onKeyDown={e => e.key === "Enter" && fileRef.current?.click()}
                onDragOver={e => e.preventDefault()}
                onDrop={e => { e.preventDefault(); addFiles(e.dataTransfer.files); }}
                className="border-2 border-dashed border-gray-200 dark:border-gray-600 rounded-xl p-8 text-center cursor-pointer hover:border-indigo-400 hover:bg-indigo-50/20 dark:hover:bg-indigo-900/10 transition-colors select-none">
                <Upload className="mx-auto text-gray-300 mb-2" size={28} />
                <p className="text-sm text-gray-500 font-medium">Click or drag photos here</p>
                <p className="text-xs text-gray-400 mt-1">JPG · PNG · WEBP — up to 10 images</p>
              </div>
              <input ref={fileRef} type="file" accept="image/*" multiple className="hidden"
                onChange={e => addFiles(e.target.files)} />

              {enrollList.length > 0 && (
                <ul className="mt-3 space-y-1.5 max-h-44 overflow-y-auto pr-1">
                  {enrollList.map((entry, i) => (
                    <li key={i} className="flex items-center gap-2 bg-gray-50 dark:bg-gray-700/50 rounded-lg px-3 py-2">
                      <span className="flex-1 truncate text-gray-700 dark:text-gray-300 text-xs">{entry.file.name}</span>
                      {entry.status === "pending" && !enrolling && (
                        <button onClick={() => removeFile(i)} className="text-gray-400 hover:text-red-500"><X size={13} /></button>
                      )}
                      {entry.status === "pending" && enrolling && <span className="text-gray-400 text-xs">Processing…</span>}
                      {entry.status === "ok"    && <span className="text-green-600 text-xs font-medium">✓ OK</span>}
                      {entry.status === "error" && <span className="text-red-500 text-xs" title={entry.msg}>✗ Failed</span>}
                    </li>
                  ))}
                </ul>
              )}
              {enrollDone && (
                <p className={`mt-3 text-sm font-medium ${okCount === enrollList.length ? "text-green-600" : "text-amber-600"}`}>
                  {okCount}/{enrollList.length} enrolled. {okCount > 0 && "Edge nodes sync within 60s."}
                </p>
              )}
              <div className="flex justify-end gap-2 mt-5">
                <button onClick={() => setEnrollTarget(null)}
                  className="px-4 py-2 text-sm border dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 dark:text-gray-300 transition-colors">
                  {enrollDone ? "Close" : "Cancel"}
                </button>
                {!enrollDone && enrollList.length > 0 && (
                  <button onClick={runEnrollment} disabled={enrolling}
                    className="px-5 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors font-medium">
                    {enrolling ? "Enrolling…" : `Enroll ${enrollList.length} Photo${enrollList.length > 1 ? "s" : ""}`}
                  </button>
                )}
              </div>
            </>
          )}

          {/* ── Camera tab ── */}
          {enrollTab === "camera" && (
            <>
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                Best for CCTV/overhead cameras — capture a live frame, drag to select the face, then enroll.
                The embedding will match the camera&apos;s actual viewing angle.
              </p>

              {/* Camera selector + capture */}
              <div className="flex flex-col sm:flex-row gap-2 mb-3">
                <select
                  value={camId}
                  onChange={e => { setCamId(e.target.value); setSnapshot(null); setSelection(null); setCamEnrollMsg(""); }}
                  className="flex-1 border dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white min-w-0">
                  {cameras.length === 0
                    ? <option>No cameras registered</option>
                    : cameras.map(c => <option key={c.id} value={c.id}>{c.name} — {c.location || c.direction}</option>)
                  }
                </select>
                <button
                  onClick={captureSnapshot}
                  disabled={!camId || snapLoading}
                  className="flex items-center justify-center gap-1.5 px-3 py-2 text-sm bg-gray-800 dark:bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 transition-colors font-medium whitespace-nowrap">
                  <RefreshCw size={13} className={snapLoading ? "animate-spin" : ""} />
                  {snapLoading ? "Loading…" : snapshot ? "Refresh" : "Capture"}
                </button>
              </div>

              {snapError && (
                <p className="text-xs text-red-600 dark:text-red-400 mb-2">{snapError}</p>
              )}

              {/* Snapshot canvas */}
              {snapshot ? (
                <div className="relative">
                  <img
                    ref={imgRef}
                    src={snapshot}
                    alt="Camera snapshot"
                    className="hidden"
                    onLoad={() => {
                      const canvas = canvasRef.current;
                      const img = imgRef.current;
                      if (!canvas || !img) return;
                      canvas.width  = canvas.offsetWidth;
                      canvas.height = Math.round(canvas.offsetWidth * img.naturalHeight / img.naturalWidth);
                      drawCanvas(selection);
                    }}
                  />
                  <canvas
                    ref={canvasRef}
                    className="w-full rounded-lg border dark:border-gray-600 cursor-crosshair"
                    style={{ touchAction: "none" }}
                    onMouseDown={onMouseDown}
                    onMouseMove={onMouseMove}
                    onMouseUp={onMouseUp}
                    onMouseLeave={onMouseUp}
                  />
                  <div className="absolute top-2 left-2 bg-black/60 text-white text-xs px-2 py-1 rounded flex items-center gap-1">
                    <Crosshair size={11} /> Drag to select face
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-48 border-2 border-dashed border-gray-200 dark:border-gray-600 rounded-xl text-gray-400 dark:text-gray-500">
                  <Camera size={28} className="mb-2 opacity-40" />
                  <p className="text-sm">Select a camera and click Capture</p>
                </div>
              )}

              {camEnrollMsg && (
                <p className={`mt-3 text-sm font-medium ${camEnrollMsg.startsWith("✓") ? "text-green-600" : "text-red-600"}`}>
                  {camEnrollMsg}
                </p>
              )}

              {selection && !camEnrollMsg && (
                <p className="mt-2 text-xs text-indigo-600 dark:text-indigo-400">
                  Face region selected ({Math.round(selection.w)}×{Math.round(selection.h)}px) — ready to enroll.
                </p>
              )}

              <div className="flex justify-end gap-2 mt-4">
                <button onClick={() => setEnrollTarget(null)}
                  className="px-4 py-2 text-sm border dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 dark:text-gray-300 transition-colors">
                  Close
                </button>
                <button
                  onClick={enrollFromCamera}
                  disabled={!snapshot || !selection || selection.w < 10 || camEnrolling}
                  className="px-5 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors font-medium">
                  {camEnrolling ? "Enrolling…" : "Enroll Face"}
                </button>
              </div>
            </>
          )}
        </Modal>
      )}
    </DashboardShell>
  );
}

// ── Bangladesh-friendly suggestion lists ────────────────────────────────────

const BD_DEPARTMENTS = [
  "Software Engineering", "Information Technology (IT)", "Human Resources (HR)",
  "Finance & Accounts", "Marketing", "Sales", "Operations",
  "Administration", "Customer Service", "Procurement", "Supply Chain",
  "Quality Assurance (QA)", "Research & Development (R&D)", "Production",
  "Legal & Compliance", "Security", "Business Development",
];

const BD_DESIGNATIONS = [
  "Managing Director (MD)", "Chief Executive Officer (CEO)",
  "Chief Operating Officer (COO)", "Chief Financial Officer (CFO)",
  "General Manager (GM)", "Deputy General Manager (DGM)",
  "Assistant General Manager (AGM)", "Senior Manager", "Manager",
  "Deputy Manager", "Assistant Manager (AM)",
  "Senior Executive", "Executive", "Junior Executive",
  "Principal Engineer", "Senior Software Engineer", "Software Engineer",
  "Junior Software Engineer", "DevOps Engineer", "UI/UX Designer",
  "Business Analyst", "System Analyst", "Database Administrator (DBA)",
  "Accounts Officer", "Senior Accounts Officer", "Finance Officer",
  "HR Officer", "Senior HR Officer", "HR Manager",
  "Marketing Officer", "Senior Marketing Officer", "Brand Manager",
  "Sales Executive", "Senior Sales Executive", "Sales Manager",
  "Customer Service Representative", "Customer Service Manager",
  "Operations Officer", "Operations Manager",
  "Procurement Officer", "Supply Chain Officer",
  "Quality Control Officer", "QA Engineer",
  "Legal Officer", "Compliance Officer",
  "Security Officer", "Security Guard",
  "Intern", "Management Trainee Officer (MTO)",
];

// ── Tiny reusable components ────────────────────────────────────────────────

const INPUT = "w-full border dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition";

function Field({ label, span, hint, children }: { label: string; span?: 1 | 2; hint?: string; children: React.ReactNode }) {
  return (
    <div className={span === 2 ? "col-span-2" : ""}>
      <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">{label}</label>
      {children}
      {hint && <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{hint}</p>}
    </div>
  );
}

function Modal({ title, onClose, children, wide }: {
  title: string; onClose: () => void; children: React.ReactNode; wide?: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className={`glass-heavy rounded-2xl w-full ${wide ? "max-w-2xl" : "max-w-lg"} max-h-[90vh] overflow-y-auto`}>
        <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-white/30 dark:border-white/[0.07] sticky top-0 glass-heavy z-10">
          <h3 className="text-base font-semibold text-gray-900 dark:text-white">{title}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 transition-colors">
            <X size={18} />
          </button>
        </div>
        <div className="px-6 py-5">{children}</div>
      </div>
    </div>
  );
}

const COLOR_MAP: Record<string, { base: string; active: string }> = {
  blue:   { base: "text-gray-400 hover:text-blue-600 hover:bg-blue-50",    active: "bg-blue-100 text-blue-700" },
  indigo: { base: "text-gray-400 hover:text-indigo-600 hover:bg-indigo-50", active: "bg-indigo-100 text-indigo-700" },
  green:  { base: "text-green-500 hover:bg-green-50",                        active: "bg-green-100 text-green-700" },
  red:    { base: "text-gray-400 hover:text-red-600 hover:bg-red-50",        active: "bg-red-100 text-red-700" },
  amber:  { base: "text-gray-400 hover:text-amber-600 hover:bg-amber-50",   active: "bg-amber-100 text-amber-700" },
};

function ActionBtn({ onClick, title, color, active, children }: {
  onClick: () => void; title: string; color: keyof typeof COLOR_MAP; active?: boolean; children: React.ReactNode;
}) {
  const c = COLOR_MAP[color];
  return (
    <button onClick={onClick} title={title}
      className={`p-1.5 rounded transition-colors ${active ? c.active : c.base}`}>
      {children}
    </button>
  );
}
