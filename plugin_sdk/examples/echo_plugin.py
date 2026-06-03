from plugin_sdk.mellow_plugin import MellowPlugin

class EchoPlugin(MellowPlugin):
    name = "echo-plugin"
    version = "0.1.0"

    def register(self, host_registry):
        host_registry["echo"] = lambda value: value
