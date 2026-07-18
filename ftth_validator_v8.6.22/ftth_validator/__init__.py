def classFactory(iface):
    from .ftth_validator import FTTHValidatorPlugin
    return FTTHValidatorPlugin(iface)
