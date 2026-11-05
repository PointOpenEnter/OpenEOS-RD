from pathlib import Path
import struct

pcap = Path(r"c:\Users\and!m\Documents\р62.pcapng")
lines = []

raw = pcap.read_bytes()
idx = 0
total = len(raw)
packets = []

while idx < total - 12:
    block_type, block_len = struct.unpack_from("<II", raw, idx)
    if block_len < 12 or idx + block_len > total:
        idx += 4
        continue

    if block_type == 0x00000006:
        cap_len = struct.unpack_from("<I", raw, idx + 20)[0]
        if cap_len > 32 and idx + 28 + cap_len <= total:
            pkt_data = raw[idx + 28:idx + 28 + cap_len]
            usb_hdr_len = struct.unpack_from("<H", pkt_data, 0)[0]
            if 24 <= usb_hdr_len < cap_len:
                endpoint = pkt_data[22]
                transfer_type = pkt_data[23]
                payload = pkt_data[usb_hdr_len:]
                packets.append({"ep": endpoint, "type": transfer_type, "payload": payload})
    idx += block_len

ptp_events = []
current_cmd = None
current_data = bytearray()

for p in packets:
    payload = p["payload"]
    if len(payload) < 12:
        continue
    c_len, c_type, code, tx_id = struct.unpack_from("<IHHI", payload, 0)
    if c_type == 1:
        params = []
        for poff in range(12, min(len(payload), 32), 4):
            params.append(struct.unpack_from("<I", payload, poff)[0])
        current_cmd = {"code": code, "tx_id": tx_id, "params": params, "params_hex": [f"0x{x:08X}" for x in params]}
        current_data = bytearray()
    elif c_type == 2:
        current_data.extend(payload[12:c_len])
    elif c_type == 3:
        if current_cmd and current_cmd["tx_id"] == tx_id:
            ptp_events.append({"cmd": current_cmd, "data": bytes(current_data), "resp_code": code, "resp_tx_id": tx_id})
            current_cmd = None
            current_data = bytearray()

# Dump transactions 1 to 40
out = []
for ev in ptp_events:
    tx_id = ev["cmd"]["tx_id"]
    if tx_id <= 40:
        cmd = ev["cmd"]
        d = ev["data"]
        out.append(f"TxID={tx_id:2d} | OpCode=0x{cmd['code']:04X} | Params={cmd['params_hex']} | DataLen={len(d):3d} | DataHex={d.hex(' ')} | Resp=0x{ev['resp_code']:04X}")

Path(r"C:\Users\and!m\OpenEOS\pcap_start_sequence.txt").write_text("\n".join(out), encoding="utf-8")
