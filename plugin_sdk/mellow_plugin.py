from __future__ import annotations

class MellowPlugin:
    name = "unnamed-plugin"
    version = "0.1.0"

    def register(self, host_registry):
        raise NotImplementedError
