"use client";
import { useEffect, useState } from "react";
import { Video, Shield, MapPin, Pencil, Trash2, Calendar } from "lucide-react";
import { api } from "@/lib/api";
import { useRole } from "@/lib/rbac";
import DashboardShell from "@/components/ui/DashboardShell";
import CameraFeed from "@/components/live/CameraFeed";
import type { Camera } from "@/types";

const STATUS_COLOR: Record<string, string> = {
  online: "bg-green-100 text-green-700", offline: "bg-gray-100 text-gray-500", error: "bg-red-100 text-red-700",
};

const STATUS_LABEL: Record<string, string> = {
  online: "Online", offline: "Offline", error: "Error",
};
const ROLE_LABEL: Record<string, string> = {
  meeting_room: "Meeting Room", reception: "Reception", entrance_gate: "Entrance Gate", general: "General",
};

type FormState = { name: string; location: string; rtsp_url: string; direction: string;
                   camera_role: string; camera_zone: string; is_restricted: boolean; fps_target: number };

const EMPTY_FORM: FormState = {
  name: "", location: "", rtsp_url: "", direction: "entrance",
  camera_role: "general", camera_zone: "", is_restricted: false, fps_target: 10,
};


export default function CamerasPage() {
  const { can } = useRole();
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const reload = () => api.cameras().then(setCameras).catch((err) => setError(err.message));
  useEffect(() => {
    reload();
    const t = setInterval(reload, 30_000);
    return () => clearInterval(t);
  }, []);

  function openNew() {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setError("");
    setShowForm(true);
  }

  function openEdit(cam: Camera) {
    setEditingId(cam.id);
    setForm({
      name: cam.name,
      location: cam.location || "",
      rtsp_url: cam.rtsp_url || "",
      direction: cam.direction,
      camera_role: cam.camera_role,
      camera_zone: cam.camera_zone || "",
      is_restricted: cam.is_restricted,
      fps_target: cam.fps_target || 10,
    });
    setError("");
    setShowForm(true);
  }

  async function saveCamera() {
    if (!form.name.trim() || !form.rtsp_url.trim()) {
      setError("Camera name and RTSP URL are required.");
      return;
    }
    if (!/^(rtsps?|https?):\/\//i.test(form.rtsp_url.trim())) {
      setError("Stream URL must start with rtsp://, http://, or https://");
      return;
    }
    setSaving(true);
    setError("");
    try {
      if (editingId) await api.updateCamera(editingId, form);
      else await api.addCamera(form);
      setShowForm(false);
      setEditingId(null);
      setForm(EMPTY_FORM);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save camera.");
    } finally {
      setSaving(false);
    }
  }

  async function removeCamera(cam: Camera) {
    if (!window.confirm(`Remove camera "${cam.name}"? This cannot be undone.`)) return;
    setError("");
    try {
      await api.deleteCamera(cam.id);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove camera.");
    }
  }

  return (
    <DashboardShell>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-medium">Cameras</h2>
        {can("admin") && (
          <button onClick={openNew}
                  className="text-sm bg-brand text-white px-3 py-1.5 rounded-lg hover:bg-brand-dark">
            + Add camera
          </button>
        )}
      </div>
      {error && <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
      {showForm && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border dark:border-gray-700 p-4 mb-4 space-y-3">
          <p className="text-sm font-medium">{editingId ? "Edit camera" : "New camera"}</p>
          <div className="grid grid-cols-2 gap-3">
            {(["name", "location", "rtsp_url", "camera_zone"] as const).map((k) => (
              <div key={k}>
                <label className="text-xs text-gray-500 capitalize">{k.replace(/_/g, " ")}</label>
                <input value={form[k] as string}
                       onChange={(e) => setForm((p) => ({ ...p, [k]: e.target.value }))}
                       className="w-full border dark:border-gray-600 rounded-lg px-3 py-1.5 text-sm mt-0.5 bg-white dark:bg-gray-700 text-gray-900 dark:text-white" />
              </div>
            ))}
            <div>
              <label className="text-xs text-gray-500">Direction</label>
              <select value={form.direction} onChange={(e) => setForm((p) => ({ ...p, direction: e.target.value }))}
                      className="w-full border dark:border-gray-600 rounded-lg px-3 py-1.5 text-sm mt-0.5 bg-white dark:bg-gray-700 text-gray-900 dark:text-white">
                <option value="entrance">Entrance</option><option value="exit">Exit</option><option value="interior">Interior</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-500">Role</label>
              <select value={form.camera_role} onChange={(e) => setForm((p) => ({ ...p, camera_role: e.target.value }))}
                      className="w-full border dark:border-gray-600 rounded-lg px-3 py-1.5 text-sm mt-0.5 bg-white dark:bg-gray-700 text-gray-900 dark:text-white">
                <option value="general">General</option><option value="meeting_room">Meeting Room</option>
                <option value="reception">Reception</option><option value="entrance_gate">Entrance Gate</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-500">Target FPS</label>
              <input type="number" min={1} max={60} value={form.fps_target}
                     onChange={(e) => setForm((p) => ({ ...p, fps_target: Number(e.target.value) }))}
                     className="w-full border dark:border-gray-600 rounded-lg px-3 py-1.5 text-sm mt-0.5 bg-white dark:bg-gray-700 text-gray-900 dark:text-white" />
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" checked={form.is_restricted}
                   onChange={(e) => setForm((p) => ({ ...p, is_restricted: e.target.checked }))} />
            Restricted area (any detection → alert)
          </label>
          <div className="flex gap-2 justify-end">
            <button onClick={() => setShowForm(false)} disabled={saving}
                    className="text-sm text-gray-500 px-3 py-1.5">Cancel</button>
            <button onClick={saveCamera} disabled={saving}
                    className="text-sm bg-brand text-white px-3 py-1.5 rounded-lg disabled:opacity-50">
              {saving ? "Saving..." : editingId ? "Update" : "Save"}
            </button>
          </div>
        </div>
      )}
      {cameras.length === 0 && !error && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border dark:border-gray-700 p-10 text-center">
          <Video className="mx-auto text-gray-200 dark:text-gray-600 mb-3" size={36} />
          <p className="text-sm font-medium text-gray-500 dark:text-gray-400">No cameras registered yet</p>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
            {can("admin") ? "Click + Add camera to register your first camera." : "Ask an admin to add cameras."}
          </p>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        {cameras.map((cam) => (
          <div key={cam.id} className="bg-white dark:bg-gray-800 rounded-xl border dark:border-gray-700 p-4">
            <CameraFeed cameraId={cam.id} direction={cam.direction} status={cam.status} streamOnly />
            <div className="flex items-start justify-between mb-2">
              <span className="font-medium text-sm">{cam.name}</span>
              <div className="flex items-center gap-1">
                {can("admin") && (
                  <button onClick={() => openEdit(cam)} title="Edit camera"
                          className="p-1 text-gray-400 hover:text-brand"><Pencil size={14} /></button>
                )}
                {can("admin") && (
                  <button onClick={() => removeCamera(cam)} title="Remove camera"
                          className="p-1 text-gray-400 hover:text-red-600"><Trash2 size={14} /></button>
                )}
                <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_COLOR[cam.status] || STATUS_COLOR.offline}`}>
                  {STATUS_LABEL[cam.status] || cam.status}
                </span>
              </div>
            </div>
            <div className="text-xs text-gray-500 space-y-1">
              <div className="flex items-center gap-1"><MapPin size={11} />{cam.location || "No location"}</div>
              <div className="flex items-center gap-1"><Video size={11} />{ROLE_LABEL[cam.camera_role] || "General"} · {cam.direction}</div>
              {cam.camera_zone && <div>Zone: {cam.camera_zone}</div>}
              {cam.last_seen_at && <div className="flex items-center gap-1"><Calendar size={11} />Last seen: {new Date(cam.last_seen_at).toLocaleString()}</div>}
              {cam.is_restricted && <div className="flex items-center gap-1 text-red-600"><Shield size={11} /> Restricted</div>}
            </div>
          </div>
        ))}
      </div>
    </DashboardShell>
  );
}
