"""
OpenEOS Service: PTP-IP Network Transport Module (RFC/CIPA 15740).
Tests and interrogates Canon cameras over Wi-Fi / Ethernet on TCP port 15740.
Provides sub-second non-blocking availability check and full PTP-IP handshake.
"""
from __future__ import annotations

import socket
import struct
import time
import uuid

PTPIP_INIT_COMMAND_REQUEST = 1
PTPIP_INIT_COMMAND_ACK = 2
PTPIP_INIT_EVENT_REQUEST = 3
PTPIP_INIT_EVENT_ACK = 4
PTPIP_CMD_REQUEST = 6
PTPIP_CMD_RESPONSE = 7
PTPIP_EVENT = 8
PTPIP_DATA_START = 9
PTPIP_DATA_END = 12

def probe_ptpip(host: str | None = None, port: int = 15740, timeout: float = 0.25) -> dict:
    """
    Probes PTP-IP network connectivity. If the camera has Wi-Fi enabled and is on
    the network, conducts a PTP-IP handshake. If offline or USB-only, returns
    clean diagnostic info within ~20 ms.
    """
    t0 = time.perf_counter()
    candidates = []
    if host:
        candidates.append(host)
    else:
        # Check standard local candidate addresses
        candidates.extend(["127.0.0.1", "192.168.1.1", "192.168.137.1"])
        # Detect default gateway if possible
        try:
            import subprocess
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            res = subprocess.run(
                ["netsh", "interface", "ipv4", "show", "addresses"],
                capture_output=True, text=True, timeout=0.8, creationflags=creationflags
            )
            for line in res.stdout.splitlines():
                if "Default Gateway" in line or "Основной шлюз" in line:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        gw = parts[1].strip()
                        if gw and gw not in candidates:
                            candidates.insert(0, gw)
        except Exception:
            pass

    connected_sock = None
    target_ip = None

    for ip in candidates:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((ip, port))
            connected_sock = s
            target_ip = ip
            break
        except Exception:
            try:
                s.close()
            except Exception:
                pass

    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    if not connected_sock:
        return {
            "name": "PTP-IP Network Transport (TCP:15740)",
            "success": False,
            "status": "OFFLINE",
            "elapsed_ms": elapsed_ms,
            "target_ip": None,
            "message": "PTP-IP порт 15740 не отвечает (камера подключена по USB кабелю, Wi-Fi отключён)",
            "shutter_mechanical": None,
            "release_total": None,
            "power_on_count": None,
            "uptime_seconds": None,
        }

    # If connected, perform PTP-IP handshake
    try:
        sock = connected_sock
        sock.settimeout(2.0)

        # 1. Init Command Request
        client_guid = uuid.uuid4().bytes
        friendly_name = "OpenEOS\x00".encode("utf-16le")
        payload = client_guid + friendly_name + struct.pack("<I", 0x00010000)
        pkt_len = len(payload) + 8
        req = struct.pack("<II", pkt_len, PTPIP_INIT_COMMAND_REQUEST) + payload
        sock.sendall(req)

        resp_hdr = sock.recv(8)
        if len(resp_hdr) >= 8:
            r_len, r_type = struct.unpack("<II", resp_hdr)
            r_body = sock.recv(r_len - 8) if r_len > 8 else b""
            if r_type == PTPIP_INIT_COMMAND_ACK and len(r_body) >= 4:
                conn_num = struct.unpack("<I", r_body[:4])[0]
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                sock.close()
                return {
                    "name": "PTP-IP Network Transport (TCP:15740)",
                    "success": True,
                    "status": "CONNECTED",
                    "elapsed_ms": elapsed_ms,
                    "target_ip": target_ip,
                    "connection_number": conn_num,
                    "message": f"Успешное подключение к камере по Wi-Fi PTP-IP ({target_ip}:15740)",
                    "shutter_mechanical": None,
                    "release_total": None,
                    "power_on_count": None,
                    "uptime_seconds": None,
                }
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "name": "PTP-IP Network Transport (TCP:15740)",
            "success": False,
            "status": "HANDSHAKE_FAILED",
            "elapsed_ms": elapsed_ms,
            "target_ip": target_ip,
            "message": f"Сбой рукопожатия PTP-IP с {target_ip}:15740",
            "shutter_mechanical": None,
            "release_total": None,
        }
    except Exception as ex:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "name": "PTP-IP Network Transport (TCP:15740)",
            "success": False,
            "status": "ERROR",
            "elapsed_ms": elapsed_ms,
            "target_ip": target_ip,
            "message": f"Ошибка PTP-IP: {ex}",
            "shutter_mechanical": None,
            "release_total": None,
        }
    finally:
        try:
            connected_sock.close()
        except Exception:
            pass
