def classFactory(iface):
    from .auto_bom_plugin import AutoBOMPlugin
    return AutoBOMPlugin(iface)
