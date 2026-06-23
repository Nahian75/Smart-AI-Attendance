"use client";
import { useEffect, useRef, useState } from "react";
import { Video, WifiOff } from "lucide-react";

interface Props {
  cameraId: string;
  cameraName?: string;
  location?: string | null;
  direction?: string;
  status?: string;
  /** When true renders only the video area — no card wrapper or info bar */
  streamOnly?: boolean;
}

export default function CameraFeed({ cameraId, cameraName, location, direction, status, streamOnly }: Props) {
  const [dead, setDead] = useState(false);
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const loadTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const baseUrl = process.env.NEXT_PUBLIC_EDGE_URL || "";
  const streamUrl = baseUrl ? `${baseUrl}/stream/${cameraId}` : `/stream/${cameraId}`;

  // Auto-retry 8 s after going dead
  useEffect(() => {
    if (dead) {
      retryRef.current = setTimeout(() => {
        setDead(false);
        setRetry((r) => r + 1);
      }, 8000);
    }
    return () => { if (retryRef.current) clearTimeout(retryRef.current); };
  }, [dead]);

  // 20 s timeout: edge node loads AI models on first start which takes ~30 s.
  // The MJPEG endpoint returns HTTP 200 immediately but sends no frames until
  // the camera is connected and the first frame is processed. Give it time
  // before showing the "no signal" state so it doesn't loop during startup.
  useEffect(() => {
    if (!dead) {
      setLoading(true);
      loadTimerRef.current = setTimeout(() => setDead(true), 20000);
    }
    return () => { if (loadTimerRef.current) clearTimeout(loadTimerRef.current); };
  }, [dead, retry]);

  const handleLoad = () => {
    if (loadTimerRef.current) clearTimeout(loadTimerRef.current);
    setLoading(false);
  };

  const isOnline = status === "online";

  const streamArea = (
    <div className={`relative aspect-video bg-gray-950 flex items-center justify-center ${streamOnly ? "rounded-lg overflow-hidden mb-3" : ""}`}>
      {dead ? (
        <div className="flex flex-col items-center gap-2">
          <WifiOff size={22} className="text-gray-600" />
          <span className="text-xs text-gray-500 text-center px-3">
            No signal — retrying…<br />
            <span className="text-gray-600">Check RTSP URL or edge node</span>
          </span>
        </div>
      ) : (
        <>
          <img
            key={`${streamUrl}-${retry}`}
            src={streamUrl}
            alt={`Camera: ${cameraName}`}
            className="h-full w-full object-contain"
            onLoad={handleLoad}
            onError={() => { if (loadTimerRef.current) clearTimeout(loadTimerRef.current); setDead(true); }}
          />
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center bg-gray-950">
              <div className="flex flex-col items-center gap-2">
                <span className="h-6 w-6 animate-spin rounded-full border-2 border-gray-600 border-t-gray-300" />
                <span className="text-xs text-gray-600">Connecting…</span>
              </div>
            </div>
          )}
        </>
      )}

      {/* Status dot */}
      <div className="absolute top-2 right-2 flex items-center gap-1 bg-black/50 rounded-full px-2 py-0.5">
        {isOnline
          ? <><span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" /><span className="text-xs text-green-300">Live</span></>
          : <><span className="w-1.5 h-1.5 rounded-full bg-gray-500" /><span className="text-xs text-gray-400">Offline</span></>
        }
      </div>

      {/* Direction badge */}
      {direction && (
        <div className="absolute top-2 left-2 bg-black/50 rounded-full px-2 py-0.5">
          <span className="text-xs text-gray-300 capitalize">{direction}</span>
        </div>
      )}
    </div>
  );

  if (streamOnly) return streamArea;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border dark:border-gray-700 overflow-hidden">
      {streamArea}
      {/* Info bar */}
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
