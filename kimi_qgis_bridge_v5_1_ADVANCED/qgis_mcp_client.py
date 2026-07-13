# -*- coding: utf-8 -*-
"""
QGIS MCP Client - Low-level TCP client for QGIS MCP Plugin.
Connects to the QGIS MCP Plugin's TCP socket server and sends/receives commands.

Author: Mustafa M M Elaham
"""

import json
import socket
import base64
import traceback
from typing import Dict, Any, Optional, List


class QGISMCPClient:
    """TCP client for communicating with QGIS MCP Plugin."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9876, timeout: float = 30.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self.buffer = b""

    def connect(self) -> bool:
        """Connect to QGIS MCP TCP server."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(self.timeout)
            self.sock.connect((self.host, self.port))
            print(f"[OK] Connected to QGIS MCP at {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to connect to QGIS MCP: {e}")
            print("[HINT] Make sure QGIS MCP Plugin is started in QGIS (Plugins > QGIS MCP > Start Server)")
            return False

    def disconnect(self):
        """Close the TCP connection."""
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None
            print("[OK] Disconnected from QGIS MCP")

    def _send_jsonrpc(self, method: str, params: dict = None, msg_id: int = 1) -> dict:
        """Send a JSON-RPC 2.0 request and return the response."""
        if not self.sock:
            raise ConnectionError("Not connected to QGIS MCP")

        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": msg_id
        }

        message = json.dumps(payload) + "\n"
        self.sock.sendall(message.encode("utf-8"))

        # Read response line by line
        while b"\n" not in self.buffer:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("QGIS MCP closed connection")
            self.buffer += chunk

        line, self.buffer = self.buffer.split(b"\n", 1)
        response = json.loads(line.decode("utf-8"))

        if "error" in response:
            raise RuntimeError(f"QGIS MCP Error: {response['error']}")

        return response.get("result", {})

    # ========== Core QGIS Operations ==========

    def get_project_info(self) -> dict:
        """Get current QGIS project information."""
        return self._send_jsonrpc("get_project_info")

    def get_layers(self) -> List[dict]:
        """Get list of all layers in the project."""
        result = self._send_jsonrpc("get_layers")
        return result.get("layers", [])

    def get_layer_features(self, layer_name: str, limit: int = 100) -> List[dict]:
        """Get features from a specific layer."""
        return self._send_jsonrpc("get_layer_features", {
            "layer_name": layer_name,
            "limit": limit
        }).get("features", [])

    def execute_code(self, code: str) -> dict:
        """Execute arbitrary Python code in QGIS."""
        return self._send_jsonrpc("execute_code", {"code": code})

    def render_map(self, extent: Optional[List[float]] = None, width: int = 1200, height: int = 800) -> str:
        """Render current map canvas to PNG and return as base64."""
        params = {"width": width, "height": height}
        if extent:
            params["extent"] = extent
        result = self._send_jsonrpc("render_map", params)
        return result.get("image_base64", "")

    def save_map_image(self, filepath: str, width: int = 1200, height: int = 800) -> bool:
        """Render and save map image to file."""
        b64 = self.render_map(width=width, height=height)
        if b64:
            with open(filepath, "wb") as f:
                f.write(base64.b64decode(b64))
            return True
        return False

    def add_vector_layer(self, filepath: str, layer_name: str) -> dict:
        """Add a vector layer to the project."""
        return self._send_jsonrpc("add_vector_layer", {
            "filepath": filepath,
            "layer_name": layer_name
        })

    def remove_layer(self, layer_name: str) -> dict:
        """Remove a layer from the project."""
        return self._send_jsonrpc("remove_layer", {"layer_name": layer_name})

    def zoom_to_layer(self, layer_name: str) -> dict:
        """Zoom map canvas to a layer's extent."""
        return self._send_jsonrpc("zoom_to_layer", {"layer_name": layer_name})

    def run_processing(self, algorithm: str, parameters: dict) -> dict:
        """Run a QGIS Processing algorithm."""
        return self._send_jsonrpc("run_processing", {
            "algorithm": algorithm,
            "parameters": parameters
        })

    def get_qgis_state_summary(self) -> str:
        """Get a human-readable summary of QGIS state for AI context."""
        try:
            project = self.get_project_info()
            layers = self.get_layers()

            lines = []
            lines.append(f"Project: {project.get('title', 'Untitled')}")
            lines.append(f"CRS: {project.get('crs', 'Unknown')}")
            lines.append(f"Layers ({len(layers)}):")

            for layer in layers:
                name = layer.get('name', 'Unknown')
                geom = layer.get('geometry_type', 'Unknown')
                count = layer.get('feature_count', '?')
                crs = layer.get('crs', '')
                lines.append(f"  - {name} | Type: {geom} | Features: {count} | CRS: {crs}")

            return "\n".join(lines)
        except Exception as e:
            return f"Error getting QGIS state: {e}"
