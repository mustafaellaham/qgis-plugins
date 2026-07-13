# -*- coding: utf-8 -*-
"""
Precon Cable Optimizer
QGIS Plugin for FTTH Precon Cable Optimization

Author: Mustafa M M Elaham
Copyright (c) 2026 Mustafa M M Elaham. All rights reserved.

Reads route lengths from a 'length' column and calculates the optimal precon
cable length from fixed cable sizes by trying slack values 10-7m to minimize waste.
"""

def classFactory(iface):
    """Load PreconCableOptimizer class from file precon_optimizer.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    from .precon_optimizer import PreconCableOptimizer
    return PreconCableOptimizer(iface)
