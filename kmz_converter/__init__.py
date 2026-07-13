def classFactory(iface):
    from .kmz_converter import KMZConverterPlugin
    return KMZConverterPlugin(iface)
