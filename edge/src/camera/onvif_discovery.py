"""Best-effort ONVIF discovery via WS-Discovery probe.

Falls back gracefully if the wsdiscovery package isn't installed; cameras
can always be added manually by RTSP URL in the admin dashboard.
"""
from ..utils.logger import get_logger

log = get_logger("onvif")


def discover(timeout: int = 4) -> list[dict]:
    try:
        from wsdiscovery.discovery import ThreadedWSDiscovery as WSD
        wsd = WSD()
        wsd.start()
        services = wsd.searchServices(timeout=timeout)
        out = []
        for s in services:
            xaddrs = s.getXAddrs()
            if any("onvif" in x.lower() for x in xaddrs):
                out.append({"xaddrs": xaddrs, "types": str(s.getTypes())})
        wsd.stop()
        return out
    except ImportError:
        log.warning("wsdiscovery not installed; add cameras manually by RTSP URL")
        return []
