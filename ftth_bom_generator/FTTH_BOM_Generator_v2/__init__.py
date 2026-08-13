# -*- coding: utf-8 -*-
from .bom_generator import BOMGeneratorV2b

def classFactory(iface):
    return BOMGeneratorV2b(iface)
