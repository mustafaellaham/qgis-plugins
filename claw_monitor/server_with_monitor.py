#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QGIS TCP Server v5.1 - With Monitor Integration
================================================
Run this INSIDE QGIS Python Console.

NEW: All operations are logged to the Claw Monitor panel in real-time.
Shows: commands received, code executing, progress, results, errors.

INSTALL MONITOR PLUGIN FIRST:
  1. Copy claw_monitor folder to QGIS plugins directory
  2. Plugins > Manage and Install Plugins > Enable "Claw Monitor"
  3. Plugins > Claw Monitor > Show Monitor

Author: Mustafa M M Elaham
Version: 5.1
"""

import socket
import threading
import json
import traceback
import queue
import sys
import os

from qgis.PyQt.QtCore import QObject, QTimer
from qgis.core import QgsProject, QgsVectorLayer, QgsRasterLayer

# ============================================================================
# LOG BRIDGE - Sends events to Claw Monitor
# ============================================================================

class LogBridge(QObject):
    """Thread-safe log bridge between server and monitor."""
    
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
        self.timer.timeout.connect(self._process)
        self.timer.start(100)
        self._has_monitor = False
    
    def _process(self):
        try:
            while not self.log_queue.empty():
                entry = self.log_queue.get_nowait()
                self._send(entry)
        except:
            pass
    
    def _send(self, entry):
        """Try to send to monitor plugin if available."""
        try:
            # Try importing the monitor's log functions
            from claw_monitor import log_command, log_code, log_result, log_error, log_progress
            msg_type = entry.get('type', 'info')
            msg = entry.get('message', '')
            
            if msg_type == 'command':
                log_command(msg)
            elif msg_type == 'code':
                log_code(msg)
            elif msg_type == 'result':
                log_result(msg)
            elif msg_type == 'error':
                log_error(msg)
            elif msg_type == 'progress':
                pct = entry.get('percent', 0)
                log_progress(pct, msg)
            
            self._has_monitor = True
        except ImportError:
            # Monitor plugin not installed - print to QGIS console instead
            if not self._has_monitor:
                print(f"[MONITOR] {entry.get('type','').upper()}: {entry.get('message','')}")
    
    @classmethod
    def log(cls, msg_type, message, percent=None):
        entry = {
            'timestamp': __import__('datetime').datetime.now().strftime('%H:%M:%S.%f')[:-3],
            'type': msg_type,
            'message': message
        }
        if percent is not None:
            entry['percent'] = percent
        try:
            cls.instance().log_queue.put(entry)
        except:
            pass


# Convenience functions

def log_cmd(cmd):
    LogBridge.log('command', cmd)

def log_code_executing(code):
    preview = code[:300] + '...' if len(code) > 300 else code
    LogBridge.log('code', preview)

def log_result(result):
    LogBridge.log('result', str(result)[:500])

def log_err(error):
    LogBridge.log('error', str(error)[:500])

def log_prog(percent, message=""):
    LogBridge.log('progress', message, percent)


# ============================================================================
# TCP SERVER
# ============================================================================

PORT = 9999
request_queue = queue.Queue()
response_queue = queue.Queue()


class Processor(QObject):
    def __init__(self):
        super().__init__()
        self.timer = QTimer()
        self.timer.timeout.connect(self.check)
        self.timer.start(100)
        log_prog(0, "Server initializing...")
    
    def check(self):
        try:
            while not request_queue.empty():
                req = request_queue.get_nowait()
                resp = self.handle(req)
                response_queue.put(resp)
        except:
            pass
    
    def handle(self, req):
        method = req.get("method", "")
        req_id = req.get("id", 1)
        
        try:
            if method == "get_project_info":
                p = QgsProject.instance()
                result = {
                    "title": p.title() or "Untitled",
                    "crs": p.crs().authid(),
                    "layer_count": len(p.mapLayers())
                }
                log_prog(100, "Project info retrieved")
            
            elif method == "get_layers":
                layers = []
                for lid, layer in QgsProject.instance().mapLayers().items():
                    layers.append({
                        "name": layer.name(),
                        "feature_count": layer.featureCount() if hasattr(layer, 'featureCount') else -1
                    })
                result = {"layers": layers}
                log_prog(100, f"Listed {len(layers)} layers")
            
            elif method == "execute_code":
                code = req.get("params", {}).get("code", "")
                
                # LOG TO MONITOR
                log_cmd("Execute PyQGIS code")
                log_code_executing(code)
                log_prog(10, "Preparing execution...")
                
                import processing
                namespace = {
                    "iface": globals().get('iface'),
                    "QgsProject": QgsProject,
                    "QgsVectorLayer": QgsVectorLayer,
                    "QgsRasterLayer": QgsRasterLayer,
                    "processing": processing,
                    "__name__": "__main__"
                }
                
                # Add monitor logging functions to namespace
                namespace['claw_log'] = log_prog
                namespace['claw_progress'] = log_prog
                
                import sys
                from io import StringIO
                old_out, old_err = sys.stdout, sys.stderr
                out_buf, err_buf = StringIO(), StringIO()
                sys.stdout, sys.stderr = out_buf, err_buf
                
                log_prog(50, "Executing...")
                try:
                    exec(code, namespace)
                    log_prog(90, "Finalizing...")
                    result = {"output": out_buf.getvalue(), "error": err_buf.getvalue()}
                    if result["output"]:
                        log_result(result["output"])
                    log_prog(100, "Complete")
                except Exception as e:
                    err_msg = f"{err_buf.getvalue()}\nException: {e}"
                    result = {"output": out_buf.getvalue(), "error": err_msg}
                    log_err(err_msg)
                    log_prog(100, "Failed")
                finally:
                    sys.stdout, sys.stderr = old_out, old_err
            
            elif method == "render_map":
                log_cmd("Capture map screenshot")
                log_prog(50, "Rendering map...")
                iface_ref = globals().get('iface')
                canvas = iface_ref.mapCanvas()
                img = canvas.grab()
                from qgis.PyQt.QtCore import QByteArray, QBuffer, QIODevice
                ba = QByteArray()
                buf = QBuffer(ba)
                buf.open(QIODevice.WriteOnly)
                img.save(buf, "PNG")
                import base64
                img_b64 = base64.b64encode(ba.data()).decode('utf-8')
                result = {"image_base64": img_b64}
                log_prog(100, "Screenshot captured")
            
            elif method == "add_vector_layer":
                path = req.get("params", {}).get("filepath", "")
                name = req.get("params", {}).get("layer_name", "layer")
                log_cmd(f"Load layer: {name}")
                log_prog(30, f"Loading {name}...")
                layer = QgsVectorLayer(path, name, "ogr")
                if layer.isValid():
                    QgsProject.instance().addMapLayer(layer)
                    result = {"success": True, "layer_name": name, "feature_count": layer.featureCount()}
                    log_result(f"Loaded {name}: {layer.featureCount()} features")
                    log_prog(100, "Loaded")
                else:
                    result = {"success": False, "error": "Invalid layer"}
                    log_err(f"Failed to load {name}")
                    log_prog(100, "Failed")
            
            else:
                result = {"error": f"Unknown method: {method}"}
                log_err(f"Unknown method: {method}")
        
        except Exception as e:
            result = {"error": str(e), "traceback": traceback.format_exc()}
            log_err(str(e))
        
        return {"jsonrpc": "2.0", "result": result, "id": req_id}


class Server(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.running = True
        self.sock = None
    
    def run(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", PORT))
        s.listen(5)
        print(f"[OK] Server on port {PORT}")
        log_prog(100, "Server ready - waiting for connections")
        
        while self.running:
            try:
                s.settimeout(1.0)
                c, a = s.accept()
                threading.Thread(target=self.client, args=(c,a), daemon=True).start()
            except socket.timeout:
                continue
    
    def client(self, sock, addr):
        print(f"[+] Client: {addr}")
        log_cmd(f"Client connected: {addr}")
        buf = b""
        try:
            while True:
                d = sock.recv(8192)
                if not d:
                    break
                buf += d
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        req = json.loads(line.decode())
                        log_cmd(f"Method: {req.get('method', '?')}")
                        request_queue.put(req)
                        try:
                            resp = response_queue.get(timeout=30)
                            sock.sendall((json.dumps(resp)+"\n").encode())
                        except queue.Empty:
                            log_err("Timeout waiting for QGIS")
                            sock.sendall(b'{"error":"timeout"}\n')
                    except Exception as e:
                        log_err(f"Parse error: {e}")
                        sock.sendall(b'{"error":"parse"}\n')
        except:
            pass
        finally:
            sock.close()
            print(f"[-] Client: {addr}")


# ============================================================================
# MAIN
# ============================================================================

print("="*60)
print("  QGIS TCP Server v5.1 - With Monitor")
print("  Mustafa M M Elaham")
print("="*60)

processor = Processor()
server = Server()
server.start()

print("[OK] Server started")
print("[INFO] Install Claw Monitor plugin to see real-time logs")
print("[INFO] Or watch this console for [MONITOR] messages")
print(f"[TEST] Test: Test-NetConnection -ComputerName localhost -Port {PORT}")
