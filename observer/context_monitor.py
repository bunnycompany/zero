# zero/observer/context_monitor.py
#
# Watches what the user is doing and publishes it to namespace/context/current.
# Runs as its own process (`python -m observer.context_monitor`) — the
# namespace is the IPC, so the agent loop just reads the file.
#
# Deliberately starts with NSWorkspace polling: frontmost app needs no
# Accessibility permission at all. AXObserver/CFRunLoop wiring (window titles,
# selection) can replace poll_once() behind the same file later.

import logging
import time

from AppKit import NSWorkspace

from zero import ns

POLL_S = 1.0
# republish even without change, so readers' staleness checks (main.py treats
# docs older than 30s as stale) stay satisfied while the user sits in one app
HEARTBEAT_S = 15.0


class ContextMonitor:
    def __init__(self):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("ContextMonitor")
        self._last = None
        self._last_publish = 0.0

    def poll_once(self):
        """Read the frontmost app; publish on change or heartbeat. Returns the
        context dict, or None when nothing is frontmost."""
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return None
        context = {
            "app": str(app.localizedName() or ""),
            "bundle_id": str(app.bundleIdentifier() or ""),
        }
        now = time.time()
        if context != self._last or now - self._last_publish >= HEARTBEAT_S:
            ns.write_doc("context", "observer", context)
            if context != self._last:
                ns.log("observer", "context_changed", **context)
            self._last = context
            self._last_publish = now
        return context

    def run(self, interval=POLL_S):
        self.logger.info("Context monitor running (NSWorkspace polling)")
        try:
            while True:
                self.poll_once()
                time.sleep(interval)
        except KeyboardInterrupt:
            self.logger.info("Context monitor stopped")


if __name__ == "__main__":
    ContextMonitor().run()
