#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claw Monitor - QGIS Plugin
===========================
Real-time monitoring panel showing all AI operations executing in QGIS.
Like a terminal window - shows commands, code, progress, results, errors.

Author: Mustafa M M Elaham
"""

import os
import sys
import time
import json
import queue
import threading
import traceback
from datetime import datetime
from pathlib import Path

from qgis.PyQt.QtCore import (
    Qt, QTimer, pyqtSignal, QObject, QSettings
)
from qgis.PyQt.QtWidgets import (
    QAction, QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QComboBox, QSplitter,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QProgressBar, QLineEdit, QCheckBox, QMessageBox, QFileDialog
)
from qgis.PyQt.QtGui import (
    QFont, QColor, QTextCharFormat, QBrush, QIcon,
    QTextCursor
)
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsApplication,
    QgsMessageLog, Qgis
)

# ============================================================================
# SHARED LOG QUEUE - Server writes here, Monitor reads from here
# ============================================================================

class LogBridge(QObject):
    """Thread-safe bridge between server and monitor using Qt signals."""
    
    # Signals emitted when new log entries arrive
    command_received = pyqtSignal(str, str)      # (timestamp, command_text)
    code_executing = pyqtSignal(str, str)        # (timestamp, code_preview)
    result_received = pyqtSignal(str, str)       # (timestamp, result_text)
    error_received = pyqtSignal(str, str)        # (timestamp, error_text)
    progress_update = pyqtSignal(int, str)       # (percent, message)
    
    _instance = None
    
    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = LogBridge()
        return cls._instance
    
    def __init__(self):
        super().__init__()
        self.log_queue = queue.Queue()
        self.timer = QTimer()
        self.timer.timeout.connect(self._process_queue)
        self.timer.start(100)  # Check queue every 100ms
    
    def _process_queue(self):
        """Process pending log entries from queue."""
        try:
            while not self.log_queue.empty():
                entry = self.log_queue.get_nowait()
                self._emit(entry)
        except:
            pass
    
    def _emit(self, entry):
        """Emit the appropriate signal based on entry type."""
        ts = entry.get('timestamp', '')
        msg = entry.get('message', '')
        etype = entry.get('type', 'info')
        
        if etype == 'command':
            self.command_received.emit(ts, msg)
        elif etype == 'code':
            self.code_executing.emit(ts, msg)
        elif etype == 'result':
            self.result_received.emit(ts, msg)
        elif etype == 'error':
            self.error_received.emit(ts, msg)
        elif etype == 'progress':
            pct = entry.get('percent', 0)
            self.progress_update.emit(pct, msg)
    
    @classmethod
    def log(cls, msg_type, message, percent=None):
        """Add a log entry from anywhere (server, plugins, scripts)."""
        entry = {
            'timestamp': datetime.now().strftime('%H:%M:%S.%f')[:-3],
            'type': msg_type,
            'message': message
        }
        if percent is not None:
            entry['percent'] = percent
        
        try:
            cls.instance().log_queue.put(entry)
        except:
            # If bridge not initialized, use QgsMessageLog as fallback
            QgsMessageLog.logMessage(f"[{msg_type}] {message}", 'ClawMonitor', Qgis.Info)


# Convenience functions for external scripts

def log_command(cmd):
    """Log a received command."""
    LogBridge.log('command', cmd)

def log_code(code):
    """Log code being executed."""
    preview = code[:300] + '...' if len(code) > 300 else code
    LogBridge.log('code', preview)

def log_result(result):
    """Log execution result."""
    LogBridge.log('result', str(result)[:500])

def log_error(error):
    """Log an error."""
    LogBridge.log('error', str(error)[:500])

def log_progress(percent, message):
    """Log progress update."""
    LogBridge.log('progress', message, percent)


# ============================================================================
# MONITOR DOCK WIDGET - The visual panel
# ============================================================================

class ClawMonitorDock(QDockWidget):
    """Dockable monitor panel showing AI operations in real-time."""
    
    def __init__(self, parent=None):
        super().__init__("Claw Monitor", parent)
        
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea | Qt.BottomDockWidgetArea)
        self.setMinimumWidth(500)
        self.setMinimumHeight(300)
        
        # Main widget
        main_widget = QWidget()
        self.setWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # --- Top bar ---
        top_bar = QHBoxLayout()
        
        self.status_label = QLabel("● Disconnected")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
        top_bar.addWidget(self.status_label)
        
        top_bar.addStretch()
        
        self.auto_scroll_check = QCheckBox("Auto-scroll")
        self.auto_scroll_check.setChecked(True)
        top_bar.addWidget(self.auto_scroll_check)
        
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setMaximumWidth(60)
        self.clear_btn.clicked.connect(self.clear_log)
        top_bar.addWidget(self.clear_btn)
        
        self.save_btn = QPushButton("Save Log")
        self.save_btn.setMaximumWidth(70)
        self.save_btn.clicked.connect(self.save_log)
        top_bar.addWidget(self.save_btn)
        
        layout.addLayout(top_bar)
        
        # --- Progress bar ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% - %v")
        layout.addWidget(self.progress_bar)
        
        # --- Tabs ---
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)  # stretch factor
        
        # Tab 1: Live Log (terminal-like)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
        """)
        self.tabs.addTab(self.log_text, "Live Log")
        
        # Tab 2: History Table
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(4)
        self.history_table.setHorizontalHeaderLabels(["Time", "Type", "Command/Result", "Status"])
        self.history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.history_table.setFont(QFont("Consolas", 9))
        self.tabs.addTab(self.history_table, "History")
        
        # Tab 3: Errors
        self.errors_text = QTextEdit()
        self.errors_text.setReadOnly(True)
        self.errors_text.setFont(QFont("Consolas", 9))
        self.errors_text.setStyleSheet("background-color: #1e1e1e; color: #f48771;")
        self.tabs.addTab(self.errors_text, "Errors")
        
        # --- Bottom bar ---
        bottom_bar = QHBoxLayout()
        
        self.cmd_count_label = QLabel("Commands: 0")
        bottom_bar.addWidget(self.cmd_count_label)
        
        self.err_count_label = QLabel("Errors: 0")
        self.err_count_label.setStyleSheet("color: #f48771;")
        bottom_bar.addWidget(self.err_count_label)
        
        bottom_bar.addStretch()
        
        self.last_activity = QLabel("Idle")
        bottom_bar.addWidget(self.last_activity)
        
        layout.addLayout(bottom_bar)
        
        # --- Connect to LogBridge signals ---
        self.bridge = LogBridge.instance()
        self.bridge.command_received.connect(self._on_command)
        self.bridge.code_executing.connect(self._on_code)
        self.bridge.result_received.connect(self._on_result)
        self.bridge.error_received.connect(self._on_error)
        self.bridge.progress_update.connect(self._on_progress)
        
        # Counters
        self.cmd_count = 0
        self.err_count = 0
        self.history_rows = []
        
        # Welcome message
        self._append_log("SYSTEM", "Claw Monitor started. Waiting for commands...", "#569cd6")
    
    def _append_log(self, prefix, text, color="#d4d4d4"):
        """Append colored text to live log."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        # Move cursor to end
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        # Timestamp
        fmt_time = QTextCharFormat()
        fmt_time.setForeground(QBrush(QColor("#858585")))
        fmt_time.setFont(QFont("Consolas", 8))
        cursor.insertText(f"[{timestamp}] ", fmt_time)
        
        # Prefix
        fmt_prefix = QTextCharFormat()
        fmt_prefix.setForeground(QBrush(QColor(color)))
        fmt_prefix.setFontWeight(QFont.Bold)
        fmt_prefix.setFont(QFont("Consolas", 9))
        cursor.insertText(f"{prefix} ", fmt_prefix)
        
        # Message
        fmt_msg = QTextCharFormat()
        fmt_msg.setForeground(QBrush(QColor("#d4d4d4")))
        fmt_msg.setFont(QFont("Consolas", 9))
        cursor.insertText(f"{text}\n", fmt_msg)
        
        self.log_text.setTextCursor(cursor)
        
        if self.auto_scroll_check.isChecked():
            self.log_text.verticalScrollBar().setValue(
                self.log_text.verticalScrollBar().maximum()
            )
    
    def _add_history(self, ts, etype, message, status):
        """Add row to history table."""
        row = self.history_table.rowCount()
        self.history_table.insertRow(row)
        self.history_table.setItem(row, 0, QTableWidgetItem(ts))
        self.history_table.setItem(row, 1, QTableWidgetItem(etype))
        self.history_table.setItem(row, 2, QTableWidgetItem(message[:80]))
        self.history_table.setItem(row, 3, QTableWidgetItem(status))
        
        # Color by type
        color_map = {
            'COMMAND': QColor('#4ec9b0'),
            'CODE': QColor('#ce9178'),
            'RESULT': QColor('#b5cea8'),
            'ERROR': QColor('#f48771'),
        }
        if etype in color_map:
            for col in range(4):
                self.history_table.item(row, col).setBackground(
                    QBrush(color_map[etype].lighter(180))
                )
    
    def _on_command(self, ts, cmd):
        self.cmd_count += 1
        self.cmd_count_label.setText(f"Commands: {self.cmd_count}")
        self.status_label.setText("● Receiving")
        self.status_label.setStyleSheet("color: #4ec9b0; font-weight: bold;")
        self._append_log("COMMAND", cmd, "#4ec9b0")
        self._add_history(ts, "COMMAND", cmd, "Received")
        self.last_activity.setText(f"Last: Command ({ts})")
    
    def _on_code(self, ts, code):
        self.status_label.setText("● Executing")
        self.status_label.setStyleSheet("color: #ce9178; font-weight: bold;")
        self._append_log("CODE", code[:200], "#ce9178")
        self._add_history(ts, "CODE", code[:80], "Running...")
        self.last_activity.setText(f"Last: Executing ({ts})")
    
    def _on_result(self, ts, result):
        self.status_label.setText("● Completed")
        self.status_label.setStyleSheet("color: #b5cea8; font-weight: bold;")
        self._append_log("RESULT", result, "#b5cea8")
        self._add_history(ts, "RESULT", result[:80], "OK")
        self.progress_bar.setValue(100)
        self.last_activity.setText(f"Last: Complete ({ts})")
    
    def _on_error(self, ts, error):
        self.err_count += 1
        self.err_count_label.setText(f"Errors: {self.err_count}")
        self.status_label.setText("● ERROR")
        self.status_label.setStyleSheet("color: #f48771; font-weight: bold;")
        self._append_log("ERROR", error, "#f48771")
        self._add_history(ts, "ERROR", error[:80], "FAILED")
        # Also add to errors tab
        self.errors_text.append(f"[{ts}] {error}\n")
        self.last_activity.setText(f"Last: ERROR ({ts})")
    
    def _on_progress(self, percent, message):
        self.progress_bar.setValue(percent)
        self.progress_bar.setFormat(f"{percent}% - {message}")
        if percent < 100:
            self._append_log("PROGRESS", f"{percent}% - {message}", "#569cd6")
    
    def clear_log(self):
        self.log_text.clear()
        self.history_table.setRowCount(0)
        self.errors_text.clear()
        self.cmd_count = 0
        self.err_count = 0
        self.cmd_count_label.setText("Commands: 0")
        self.err_count_label.setText("Errors: 0")
        self.progress_bar.setValue(0)
        self._append_log("SYSTEM", "Log cleared.", "#569cd6")
    
    def save_log(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Log", "claw_monitor_log.txt", "Text Files (*.txt)"
        )
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(self.log_text.toPlainText())
            self._append_log("SYSTEM", f"Log saved to {path}", "#569cd6")


# ============================================================================
# QGIS PLUGIN CLASS
# ============================================================================

class ClawMonitorPlugin:
    """QGIS Plugin entry point."""
    
    def __init__(self, iface):
        self.iface = iface
        self.dock = None
        self.action = None
    
    def initGui(self):
        """Called when plugin is loaded."""
        # Create menu action
        self.action = QAction("Claw Monitor", self.iface.mainWindow())
        self.action.setToolTip("Show AI operation monitor")
        self.action.triggered.connect(self.toggle_monitor)
        
        # Add to Plugins menu
        self.iface.addPluginToMenu("Claw Monitor", self.action)
        
        # Add to toolbar
        self.iface.addToolBarIcon(self.action)
        
        # Create dock widget (hidden initially)
        self.dock = ClawMonitorDock(self.iface.mainWindow())
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.dock.hide()
    
    def toggle_monitor(self):
        """Show/hide the monitor panel."""
        if self.dock.isVisible():
            self.dock.hide()
        else:
            self.dock.show()
            self.dock.raise_()
    
    def unload(self):
        """Called when plugin is unloaded."""
        self.iface.removePluginMenu("Claw Monitor", self.action)
        self.iface.removeToolBarIcon(self.action)
        if self.dock:
            self.dock.close()
            self.dock = None


# ============================================================================
# QGIS ENTRY POINT
# ============================================================================

def classFactory(iface):
    """QGIS plugin factory function."""
    return ClawMonitorPlugin(iface)
