# -*- coding: utf-8 -*-

from qgis.core import QgsProcessingProvider
from .routed_drops_algorithm import RoutedDropsAlgorithm


class RoutedDropsProvider(QgsProcessingProvider):
    """Processing provider for Routed Drop Lines Generator."""
    
    def loadAlgorithms(self):
        self.addAlgorithm(RoutedDropsAlgorithm())
    
    def id(self):
        return 'routed_drops'
    
    def name(self):
        return 'Routed Drops'
    
    def longName(self):
        return 'Routed Drop Lines Generator'
    
    def icon(self):
        return QgsProcessingProvider.icon(self)
