"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { Video, WifiOff } from "lucide-react";

interface Props {
  cameraId: string;
  cameraName?: string;
  location?: string | null;
  direction?: string;
  status?: string;
  streamOnly?: boolean;
}

// How many consecutive failures before showing the "No signal" overlay.
// Transient blips (edge inference pause, brief TCP reset) are silently retried.
const FAILURES_BEFORE_OFFLINE = 4;
// How long to wait for the first frame before counting as a failure.
const FRAME_TIMEOUT_MS = 45_000;
// Delay between silent retries (ms). Increases after FAILURES_BEFORE_OFFLINE.
const RETRY_DELAY_MS = 2_000;
const RETRY_DELAY_OFFLINE_MS = 8_000;

export default function CameraFeed({ cameraId, cameraName, location, direction, status, streamOnly }: Props) {
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false); // only after repeated failures
  const [retry, setRetry] = useState(0);
  const failRef = useRef(0);           // consecutive failure count (not React state — no re-render)
  const imgRef = useRef<HTMLImageElement | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const deadTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const baseUrl = process.env.NEXT_PUBLIC_EDGE_URL || "";
  const streamUrl = baseUrl ? `${baseUrl}/stream/${cameraId}` : `/stream/${cameraId}`;

  const scheduleRetry = useCallback(() => {
    if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    const delay = failRef.current >= FAILURES_BEFORE_OFFLINE ? RETRY_DELAY_OFFLINE_MS : RETRY_DELAY_MS;
    retryTimerRef.current = setTimeout(() => {
      setRetry((r) => r + 1);
    }, delay);
  }, []);

  const onFailure = useCallback(() => {
    // Clear any running poll / dead timer for this attempt
    if (pollRef.current) clearInterval(pollRef.current);
    if (deadTimerRef.current) clearTimeout(deadTimerRef.current);

    failRef.current += 1;
    if (failRef.current >= FAILURES_BEFORE_OFFLINE) {
      setOffline(true);
    }
    // Stay in loading state (spinner) while we wait to retry — don't flash "No signal"
    // unless we've hit the persistent failure threshold.
    setLoading(true);
    scheduleRetry();
  }, [scheduleRetry]);

  // Each time retry increments, mount a fresh img and start polling naturalWidth.
  useEffect(() => {
    setLoading(true);

    // Poll naturalWidth — becomes > 0 once the browser renders the first MJPEG frame.
    // onLoad never fires for multipart/x-mixed-replace streams.
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(() => {
      const img = imgRef.current;
      if (img && img.naturalWidth > 0) {
        clearInterval(pollRef.current!);
        // Success — reset failure counter and clear offline state
        failRef.current = 0;
        setOffline(false);
        setLoading(false);
      }
    }, 500);

    // Hard timeout: if no frame arrives within FRAME_TIMEOUT_MS, count as failure
    if (deadTimerRef.current) clearTimeout(deadTimerRef.current);
    deadTimerRef.current = setTimeout(onFailure, FRAME_TIMEOUT_MS);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (deadTimerRef.current) clearTimeout(deadTimerRef.current);
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    };
  }, [retry, onFailure]);

  const isOnline = status === "online";

  const streamArea = (
    <div className={`relative aspect-video bg-gray-950 flex items-center justify-center ${streamOnly ? "rounded-lg overflow-hidden mb-3" : ""}`}>
      {/* img is always mounted (unless we give up after many failures) so the
          browser keeps the connection alive. The offline overlay sits on top. */}
      {!offline && (
        <img
          ref={imgRef}
          key={`${streamUrl}-${retry}`}
          src={streamUrl}
          alt={`Camera: ${cameraName}`}
          className="h-full w-full object-contain"
          onError={onFailure}
        />
      )}

      {/* Spinner overlay while loading (first load or silent retry) */}
      {loading && !offline && (
        <div className="absolute inset-0 flex items-center justify-center bg-gray-950">
          <div className="flex flex-col items-center gap-2">
            <span className="h-6 w-6 animate-spin rounded-full border-2 border-gray-600 border-t-gray-300" />
            <span className="text-xs text-gray-600">Connecting…</span>
          </div>
        </div>
      )}

      {/* Offline overlay — only after repeated failures */}
      {offline && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-gray-950">
          <WifiOff size={22} className="text-gray-600" />
          <span className="text-xs text-gray-500 text-center px-3">
            No signal — retrying…<br />
            <span className="text-gray-600">Check RTSP URL or edge node</span>
          </span>
        </div>
      )}

      {/* Status dot */}
      <div className="absolute top-2 right-2 flex items-center gap-1 bg-black/50 rounded-full px-2 py-0.5">
        {isOnline
          ? <><span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" /><span className="text-xs text-green-300">Live</span></>
          : <><span className="w-1.5 h-1.5 rounded-full bg-gray-500" /><span className="text-xs text-gray-400">Offline</span></>
        }
      </div>

      {direction && (
        <div className="absolute top-2 left-2 bg-black/50 rounded-full px-2 py-0.5">
          <span className="text-xs text-gray-300 capitalize">{direction}</span>
        </div>
      )}
    </div>
  );

  if (streamOnly) return streamArea;

  return (
    <div className="glass rounded-xl overflow-hidden">
      {streamArea}
      <div className="px-3 py-2 flex items-center gap-2">
        <Video size={13} className="text-gray-400 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-gray-900 dark:text-white truncate">{cameraName}</p>
          {location && <p className="text-xs text-gray-400 dark:text-gray-500 truncate">{location}</p>}
        </div>
      </div>
    </div>
  );
}
