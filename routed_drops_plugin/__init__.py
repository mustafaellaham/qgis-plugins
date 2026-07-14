# -*- coding: utf-8 -*-

def classFactory(iface):
    from .routed_drops_plugin import RoutedDropsPlugin
    return RoutedDropsPlugin(iface)
