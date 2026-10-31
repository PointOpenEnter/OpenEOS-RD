# -*- coding: utf-8 -*-
"""
OpenEOS - Wireshark PCAPNG Analyzer for Canon PTP/MTP Protocol
Разбирает pcapng дамп, извлекает и сопоставляет все PTP-команды, данные и ответы.
"""

import os
import sys
import struct

KNOWN_OPS = {
    0x1001: "GetDeviceInfo",
    0x1002: "OpenSession",
    0x1003: "CloseSession",
    0x1004: "GetStorageIDs",
    0x1005: "GetStorageInfo",
    0x1006: "GetNumObjects",
    0x1007: "GetObjectHandles",
    0x1008: "GetObjectInfo",
    0x1009: "GetObject",
    0x100A: "GetThumb",
    0x1014: "GetDevicePropDesc",
    0x1015: "GetDevicePropValue",
    0x1016: "SetDevicePropValue",
    0x902C: "Canon:GetStorageIDs",
    0x902F: "Canon:GetPartialObject",
    0x9101: "Canon:GetDevicePropDesc",
    0x9102: "Canon:GetDevicePropValue",
    0x9103: "Canon:SetDevicePropValue",
    0x9104: "Canon:SetDevicePropValueEx",
    0x9107: "Canon:SetRemoteMode",
    0x9109: "Canon:StartLiveView",
    0x910A: "Canon:EndLiveView",
    0x910B: "Canon:GetLiveViewFrame",
    0x910F: "Canon:RemoteRelease",
    0x9110: "Canon:CheckEvent",
    0x9113: "Canon:TransferComplete",
    0x9114: "Canon:SetEventMode",
    0x9115: "Canon:SetRemoteMode2",
    0x9116: "Canon:GetEvent",
    0x9117: "Canon:EventAcknowledge",
    0x9120: "Canon:ServiceCommand",
    0x9052: "Canon:DiagnosticDump"
}

KNOWN_PROPS = {
    0x5001: "BatteryLevel",
    0x5003: "ImageSize",
    0x5005: "WhiteBalance",
    0x5007: "FNumber (Aperture)",
    0x5008: "FocalLength",
    0x500F: "ISO",
    0x5011: "DateTime",
    0xD047: "Canon:ShutterCount (Experimental)",
    0xD102: "Canon:ShutterSpeed",
    0xD103: "Canon:Aperture",
    0xD104: "Canon:ISO",
    0xD108: "Canon:WhiteBalance",
    0xD109: "Canon:ColorTemperature",
    0xD10B: "Canon:PictureStyle",
    0xD10C: "Canon:DriveMode",
    0xD10D: "Canon:MeteringMode",
    0xD114: "Canon:AutoFocusMode",
    0xD130: "Canon:AutoPowerOff",
    0xD1A6: "Canon:ShutterCounter (Legacy)",
    0xD1B0: "Canon:ShutterCounter2 (Legacy)",
    0xD154: "Canon:ModelID",
    0xD153: "Canon:CameraOwner",
    0xD152: "Canon:Artist",
    0xD151: "Canon:Copyright",
    0xD1D3: "Canon:SerialNumber",
    0xD406: "MTP:SessionInitiatorInfo",
    0xD402: "MTP:DeviceFriendlyName"
}

RESP_CODES = {
    0x2001: "OK",
    0x2002: "GeneralError",
    0x2003: "SessionNotOpen",
    0x2004: "InvalidTransactionID",
    0x2005: "OperationNotSupported",
    0x2006: "ParameterNotSupported",
    0x2007: "DevicePropNotSupported",
    0x2019: "AccessDenied"
}

def parse_pcapng(file_path):
    packets = []
    with open(file_path, "rb") as f:
        data = f.read()

    pos = 0
    total_len = len(data)

    while pos + 12 <= total_len:
        btype, blen = struct.unpack_from("<II", data, pos)
        if blen < 12 or pos + blen > total_len:
            break

        # Enhanced Packet Block (EPB = 0x00000006)
        if btype == 0x00000006:
            if blen >= 32:
                caplen, origlen = struct.unpack_from("<II", data, pos + 20)
                pkt_data = data[pos + 28 : pos + 28 + caplen]
                packets.append(pkt_data)
        # Simple Packet Block (SPB = 0x00000003)
        elif btype == 0x00000003:
            if blen >= 16:
                pkt_data = data[pos + 12 : pos + blen - 4]
                packets.append(pkt_data)

        pos += blen

    return packets

def parse_ptp_containers(raw_packets):
    ptp_messages = []

    for pkt in raw_packets:
        if len(pkt) < 28:
            continue
        header_len = struct.unpack_from("<H", pkt, 0)[0]
        if header_len < 24 or header_len >= len(pkt):
            continue

        # USBPcap header fields
        # info byte: bit 0 indicates direction (0 = OUT / Host to Device, 1 = IN / Device to Host)
        info_byte = pkt[ header_len - 1 ] if header_len > 0 else 0
        direction = "IN (Cam->PC)" if (info_byte & 0x01) else "OUT (PC->Cam)"

        payload = pkt[header_len:]
        if len(payload) < 12:
            continue

        c_len, c_type, c_code, c_trans_id = struct.unpack_from("<IHHI", payload, 0)
        if c_len < 12 or c_len > len(payload) + 512:
            continue

        params = []
        if c_type in (1, 3): # Command or Response
            num_params = (min(c_len, len(payload)) - 12) // 4
            for i in range(min(num_params, 5)):
                params.append(struct.unpack_from("<I", payload, 12 + i * 4)[0])

        ptp_messages.append({
            "len": c_len,
            "type": c_type,
            "code": c_code,
            "trans_id": c_trans_id,
            "direction": direction,
            "params": params,
            "data": payload[12:c_len] if c_type == 2 else None
        })

    return ptp_messages

def analyze_pcap(file_path):
    report = []
    def log(msg=""):
        print(msg)
        report.append(msg)

    log("=" * 70)
    log(f"      OpenEOS: Анализ PTP-дампа: {os.path.basename(file_path)}")
    log("=" * 70)
    log(f"Файл: {file_path}")
    log(f"Размер дампа: {os.path.getsize(file_path):,} байт")
    log()

    raw_pkts = parse_pcapng(file_path)
    log(f"[1/4] Всего захвачено сырых USB-пакетов: {len(raw_pkts)}")

    ptp_msgs = parse_ptp_containers(raw_pkts)
    log(f"[2/4] Извлечено PTP-сообщений: {len(ptp_msgs)}")
    log()

    if not ptp_msgs:
        log("[-] В дампе не найдено валидных PTP-контейнеров.")
        log("    Возможно, захват производился не на том корневом USB-концентраторе.")
        return report

    # Group by TransactionID
    transactions = {}
    for msg in ptp_msgs:
        tid = msg["trans_id"]
        if tid not in transactions:
            transactions[tid] = {"cmd": None, "data": [], "resp": []}
        if msg["type"] == 1:
            transactions[tid]["cmd"] = msg
        elif msg["type"] == 2:
            transactions[tid]["data"].append(msg)
        elif msg["type"] == 3:
            transactions[tid]["resp"].append(msg)

    log(f"[3/4] Уникальных PTP-транзакций (диалогов): {len(transactions)}")
    log("-" * 70)

    # Inspect each transaction
    queried_props = {}
    commands_summary = {}

    log("ХРОНОЛОГИЯ PTP-ОБМЕНА (Команды и ответы):")
    for tid, t in sorted(transactions.items()):
        cmd = t["cmd"]
        resps = t["resp"]
        datas = t["data"]

        if cmd:
            op_code = cmd["code"]
            op_name = KNOWN_OPS.get(op_code, f"Unknown Op 0x{op_code:04X}")
            commands_summary[op_name] = commands_summary.get(op_name, 0) + 1

            params_str = " ".join([f"0x{p:08X}" for p in cmd["params"]])
            extra_info = ""

            # Check if this command queries or sets a property
            if op_code in (0x1014, 0x1015, 0x1016, 0x9101, 0x9102, 0x9103) and cmd["params"]:
                prop_id = cmd["params"][0]
                prop_name = KNOWN_PROPS.get(prop_id, f"Prop 0x{prop_id:04X}")
                extra_info = f" -> Свойство: {prop_name} (0x{prop_id:04X})"
                queried_props[prop_id] = prop_name

            log(f"  [TID {tid:4d}] {cmd['direction']} CMD: 0x{op_code:04X} ({op_name}) {params_str}{extra_info}")

        for d in datas:
            d_bytes = d["data"]
            data_preview = ""
            if d_bytes:
                # Check for printable string or small integer
                if len(d_bytes) == 1:
                    data_preview = f"Byte: {d_bytes[0]} (0x{d_bytes[0]:02X})"
                elif len(d_bytes) == 2:
                    val = struct.unpack("<H", d_bytes[:2])[0]
                    data_preview = f"Word: {val} (0x{val:04X})"
                elif len(d_bytes) == 4:
                    val = struct.unpack("<I", d_bytes[:4])[0]
                    data_preview = f"DWord: {val} (0x{val:08X})"
                elif len(d_bytes) > 4:
                    hex_str = " ".join([f"{b:02X}" for b in d_bytes[:16]])
                    # Check utf-16le string
                    try:
                        uni_str = d_bytes.decode('utf-16le', errors='ignore').strip('\x00')
                        if len(uni_str) > 2 and all(31 < ord(c) < 127 or ord(c) > 160 for c in uni_str):
                            data_preview = f"String: '{uni_str}' ({len(d_bytes)} bytes)"
                        else:
                            data_preview = f"{len(d_bytes)} bytes: {hex_str}..."
                    except Exception:
                        data_preview = f"{len(d_bytes)} bytes: {hex_str}..."

            log(f"           {d['direction']} DATA: {data_preview}")

        for r in resps:
            r_code = r["code"]
            r_name = RESP_CODES.get(r_code, f"0x{r_code:04X}")
            log(f"           {r['direction']} RESP: {r_name} (0x{r_code:04X})")

    log()
    log("=" * 70)
    log("[4/4] ИТОГОВЫЙ АНАЛИЗ:")
    log()
    log("  Сводка выполненных операций:")
    for op, cnt in sorted(commands_summary.items(), key=lambda x: -x[1]):
        log(f"    - {op}: {cnt} раз(а)")

    if queried_props:
        log()
        log("  Запрошенные камерой свойства:")
        for pid, name in queried_props.items():
            log(f"    - 0x{pid:04X}: {name}")

    log("=" * 70)
    return report

def main():
    candidate_paths = [
        r"C:\Users\and!m\Documents\р10-eosinfo.pcapng",
        r"C:\Users\and!m\Documents\r10-eosinfo.pcapng",
        r"C:\Users\and!m\Documents\р10.pcapng",
        r"C:\Users\and!m\Documents\r10.pcapng"
    ]
    target_file = None
    for p in candidate_paths:
        if os.path.isfile(p):
            target_file = p
            break

    if not target_file:
        print("[-] Файл дампа не найден по путям:")
        for p in candidate_paths:
            print(f"    {p}")
        return

    report = analyze_pcap(target_file)
    out_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pcap_analysis_report.txt")
    try:
        with open(out_file, "w", encoding="utf-8") as f:
            f.write("\n".join(report) + "\n")
        print(f"\n[+] Полный отчет сохранен в: {out_file}")
    except Exception as e:
        print(f"[-] Не удалось сохранить отчет: {e}")

if __name__ == "__main__":
    main()
