"""
ONVIF stream URI resolver — works with any ONVIF-compliant camera or DVR.

Supported brands (ONVIF Profile S / T):
  Hikvision, Dahua, Axis, Bosch, Reolink, Amcrest, Uniview, Sony, Hanwha,
  TP-Link Tapo, Imou, Tiandy, TVT, Kedacom, Honeywell, Pelco, Samsung, LG,
  and any other device that advertises ONVIF support.

What it does:
  1. Connects to the camera via ONVIF (HTTP, port 80 or 8080)
  2. Queries all available media profiles
  3. Picks the best H.264 stream URI (highest resolution first)
  4. Falls back to H.265 if no H.264 profile exists
  5. Injects credentials into the returned URI so FFmpeg can connect

Why it matters:
  Many DVRs serve H.265+ (proprietary) on the main RTSP port but expose a
  clean H.264 sub-stream via ONVIF that FFmpeg can decode without issues.
"""

import re
import logging
from urllib.parse import urlparse, urlunparse

log = logging.getLogger(__name__)

# ONVIF ports to probe, in order
_ONVIF_PORTS = [80, 8080, 8000, 2020]
# Per-port connection timeout in seconds.  Budget cameras (HiVideo) don't
# support ONVIF at all, so each failed port blocks for this long before
# moving on. Keep it short to avoid multi-minute delays on reconnect.
_ONVIF_TIMEOUT_S = 3


def parse_rtsp_credentials(rtsp_url: str) -> dict:
    """Extract host, port, user, password from an RTSP URL."""
    try:
        p = urlparse(rtsp_url)
        return {
            "host":     p.hostname or "",
            "rtsp_port": p.port or 554,
            "username": p.username or "admin",
            "password": p.password or "",
        }
    except Exception:
        return {"host": "", "rtsp_port": 554, "username": "admin", "password": ""}


def _inject_credentials(uri: str, username: str, password: str) -> str:
    """Add user:pass to an RTSP URI if not already present."""
    try:
        p = urlparse(uri)
        if p.username:
            return uri  # already has credentials
        netloc = f"{username}:{password}@{p.hostname}"
        if p.port:
            netloc += f":{p.port}"
        return urlunparse((p.scheme, netloc, p.path, p.params, p.query, p.fragment))
    except Exception:
        return uri


def resolve_best_stream(rtsp_url: str, prefer_h264: bool = True) -> str | None:
    """
    Connect to the camera via ONVIF and return the best RTSP stream URI.

    Returns None if the camera does not support ONVIF or no stream URI
    could be retrieved. The returned URI always has credentials embedded.
    """
    try:
        from onvif import ONVIFCamera  # onvif-zeep
    except ImportError:
        log.debug("onvif-zeep not installed — ONVIF resolution skipped")
        return None

    creds = parse_rtsp_credentials(rtsp_url)
    host     = creds["host"]
    username = creds["username"]
    password = creds["password"]

    if not host:
        return None

    for onvif_port in _ONVIF_PORTS:
        try:
            cam = ONVIFCamera(host, onvif_port, username, password,
                              no_cache=True, adjust_time=False,
                              transport={"timeout": _ONVIF_TIMEOUT_S})
            media = cam.create_media_service()
            profiles = media.GetProfiles()

            h264_streams: list[tuple[int, str]] = []  # (resolution_area, uri)
            h265_streams: list[tuple[int, str]] = []
            any_streams:  list[tuple[int, str]] = []

            for profile in profiles:
                vec = getattr(profile, "VideoEncoderConfiguration", None)
                if not vec:
                    continue

                try:
                    uri_resp = media.GetStreamUri({
                        "StreamSetup": {
                            "Stream": "RTP-Unicast",
                            "Transport": {"Protocol": "RTSP"},
                        },
                        "ProfileToken": profile._token,
                    })
                    uri = _inject_credentials(uri_resp.Uri, username, password)
                except Exception:
                    continue

                encoding = str(getattr(vec, "Encoding", "")).upper()
                res      = getattr(vec, "Resolution", None)
                area     = (res.Width * res.Height) if res else 0

                if "264" in encoding:
                    h264_streams.append((area, uri))
                elif "265" in encoding or "HEVC" in encoding:
                    h265_streams.append((area, uri))
                else:
                    any_streams.append((area, uri))

            # Sort each list by resolution (largest first)
            for lst in (h264_streams, h265_streams, any_streams):
                lst.sort(key=lambda x: x[0], reverse=True)

            if prefer_h264:
                ordered = h264_streams + h265_streams + any_streams
            else:
                ordered = h265_streams + h264_streams + any_streams

            if ordered:
                best_uri = ordered[0][1]
                enc = "H.264" if ordered[0] in h264_streams else \
                      "H.265" if ordered[0] in h265_streams else "unknown"
                log.info(
                    "ONVIF [%s:%d] → %s stream URI: %s",
                    host, onvif_port, enc,
                    re.sub(r":[^@]+@", ":***@", best_uri),
                )
                return best_uri

        except Exception as exc:
            log.debug("ONVIF probe %s:%d failed: %s", host, onvif_port, exc)
            continue

    log.debug("ONVIF: no stream URI found for %s", host)
    return None
