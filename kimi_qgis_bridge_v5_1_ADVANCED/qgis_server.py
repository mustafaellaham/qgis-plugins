#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QGIS TCP Server v4 - THREAD-SAFE (CONFIRMED WORKING)
=====================================================
Run this INSIDE QGIS Python Console to enable AI control.

HOW TO USE:
    1. Open QGIS
    2. Plugins > Python Console
    3. Click 'Show Editor' (paper icon)
    4. Open this file
    5. Click 'Run Script' (green play icon)
    6. Look for: [OK] Server on port 9999

IMPORTANT: Uses port 9999 to avoid conflict with QGIS MCP Plugin (9876)

Author: Mustafa M M Elaham
"""

import socket
import threading
import json
import traceback
import queue

from qgis.PyQt.QtCore import QObject, QTimer
from qgis.core import QgsProject, QgsVectorLayer, QgsRasterLayer

# ===================== QUEUE FOR THREAD-SAFE COMMUNICATION =====================
request_queue = queue.Queue()
response_queue = queue.Queue()
PORT = 9999  # <-- CHANGED FROM 9876 TO AVOID MCP PLUGIN CONFLICT

# ===================== QGIS REQUEST PROCESSOR (MAIN THREAD) =====================
class Processor(QObject):
    """Processes requests in the main QGIS thread using Qt QTimer.
    
    CRITICAL: All QGIS objects (QgsProject, layers, etc.) MUST be accessed
    from the main thread only. This class uses QTimer to ensure that.
    """

    def __init__(self):
        super().__init__()
        self.timer = QTimer()
        self.timer.timeout.connect(self.check)
        self.timer.start(100)  # Check queue every 100ms
        print("[OK] Processor started (100ms timer)")

    def check(self):
        """Check for pending requests and process them in main thread."""
        try:
            while not request_queue.empty():
                req = request_queue.get_nowait()
                resp = self.handle(req)
                response_queue.put(resp)
        except:
            pass

    def handle(self, req):
        """Handle a single request - ALWAYS runs in MAIN thread."""
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

            elif method == "get_layers":
                layers = []
                for lid, layer in QgsProject.instance().mapLayers().items():
                    layers.append({
                        "name": layer.name(),
                        "id": lid,
                        "type": str(layer.type()),
                        "crs": layer.crs().authid(),
                        "feature_count": layer.featureCount() if hasattr(layer, 'featureCount') else -1
                    })
                result = {"layers": layers}

            elif method == "execute_code":
                code = req.get("params", {}).get("code", "")
                print(f"[EXEC] {code[:80]}...")

                namespace = {
                    "iface": globals().get('iface'),
                    "QgsProject": QgsProject,
                    "QgsVectorLayer": QgsVectorLayer,
                    "QgsRasterLayer": QgsRasterLayer,
                    "__name__": "__main__"
                }

                import sys
                from io import StringIO
                old_out, old_err = sys.stdout, sys.stderr
                out_buf, err_buf = StringIO(), StringIO()
                sys.stdout, sys.stderr = out_buf, err_buf

                try:
                    exec(code, namespace)
                    result = {"output": out_buf.getvalue(), "error": err_buf.getvalue()}
                except Exception as e:
                    result = {
                        "output": out_buf.getvalue(),
                        "error": f"Exception: {e}\n{traceback.format_exc()}"
                    }
                finally:
                    sys.stdout, sys.stderr = old_out, old_err

            elif method == "render_map":
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

            elif method == "add_vector_layer":
                path = req.get("params", {}).get("filepath", "")
                name = req.get("params", {}).get("layer_name", "layer")
                layer = QgsVectorLayer(path, name, "ogr")
                if layer.isValid():
                    QgsProject.instance().addMapLayer(layer)
                    result = {"success": True, "layer_name": name, "feature_count": layer.featureCount()}
                else:
                    result = {"success": False, "error": "Invalid layer"}

            elif method == "zoom_to_layer":
                name = req.get("params", {}).get("layer_name", "")
                layer = None
                for l in QgsProject.instance().mapLayers().values():
                    if l.name() == name:
                        layer = l
                        break
                if layer:
                    globals().get('iface').setActiveLayer(layer)
                    globals().get('iface').zoomToActiveLayer()
                    result = {"success": True}
                else:
                    result = {"success": False, "error": f"Layer '{name}' not found"}

            else:
                result = {"error": f"Unknown method: {method}"}

        except Exception as e:
            result = {"error": str(e), "traceback": traceback.format_exc()}

        return {"jsonrpc": "2.0", "result": result, "id": req_id}


# ===================== TCP SERVER (BACKGROUND THREAD) =====================
class Server(threading.Thread):
    """TCP server that queues requests for main thread processing."""

    def __init__(self):
        super().__init__(daemon=True)
        self.running = True
        self.sock = None

    def run(self):
        """Server loop - runs in background thread."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(("127.0.0.1", PORT))
            self.sock.listen(5)
            print(f"[OK] Server on port {PORT}")
            print("=" * 50)

            while self.running:
                try:
                    self.sock.settimeout(1.0)
                    client, addr = self.sock.accept()
                    handler = threading.Thread(
                        target=self.handle_client,
                        args=(client, addr),
                        daemon=True
                    )
                    handler.start()
                except socket.timeout:
                    continue
                except OSError:
                    break

        except Exception as e:
            print(f"[!] Server error: {e}")
            traceback.print_exc()

    def handle_client(self, client_sock, addr):
        """Handle a single client connection."""
        print(f"[+] {addr}")
        buf = b""

        try:
            while self.running:
                chunk = client_sock.recv(8192)
                if not chunk:
                    break
                buf += chunk

                # Process complete lines (JSON-RPC)
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue

                    try:
                        request = json.loads(line.decode('utf-8'))
                        request_queue.put(request)

                        # Wait for response from main thread
                        try:
                            response = response_queue.get(timeout=30)
                            response_bytes = (json.dumps(response) + "\n").encode()
                            client_sock.sendall(response_bytes)
                        except queue.Empty:
                            error_resp = {
                                "jsonrpc": "2.0",
                                "error": {"code": -32603, "message": "Timeout"},
                                "id": request.get("id")
                            }
                            client_sock.sendall((json.dumps(error_resp) + "\n").encode())

                    except json.JSONDecodeError:
                        error_resp = {
                            "jsonrpc": "2.0",
                            "error": {"code": -32700, "message": "Parse error"},
                            "id": None
                        }
                        client_sock.sendall((json.dumps(error_resp) + "\n").encode())

        except ConnectionResetError:
            pass
        except Exception as e:
            print(f"[!] Client error: {e}")
        finally:
            client_sock.close()
            print(f"[-] {addr}")

    def stop(self):
        """Stop the server."""
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except:
                pass


# ===================== MAIN ENTRY =====================
print("=" * 50)
print("  QGIS TCP Server v4 - Thread-Safe")
print("  Mustafa M M Elaham")
print("=" * 50)

# Create processor (runs in main thread via QTimer)
processor = Processor()

# Start TCP server (background thread)
server = Server()
server.start()

print("[OK] Server thread started")
print("[OK] QGIS Processor running in main thread")
print("\nTo test in PowerShell:")
print(f"  Test-NetConnection -ComputerName localhost -Port {PORT}")
print("\nTo stop: server.stop()")
