"""
Look at the packets directly preceding TxID 26 and TxID 32 in р62.pcapng.
"""
from pathlib import Path
import struct

data = Path(r"c:\Users\and!m\Documents\р62.pcapng").read_bytes()

for target_name, data_offset, target_tx in [("Shutter (60689)", 0x0006BB17, 26), ("Release (840377)", 0x0006C6AB, 32)]:
    print(f"\n================ {target_name} : Data at 0x{data_offset:08X}, TxID={target_tx} ================")
    # Scan backward up to 2000 bytes before data_offset to find the Command packet (Type 1)
    chunk = data[max(0, data_offset - 2048):data_offset]
    # Search for struct.pack("<IHHI", len, 1, opcode, target_tx)
    for i in range(len(chunk) - 12):
        ctype = struct.unpack_from("<H", chunk, i + 4)[0]
        if ctype == 1: # Command
            clen = struct.unpack_from("<I", chunk, i)[0]
            if 12 <= clen <= 64:
                code, tx = struct.unpack_from("<HI", chunk, i + 6)
                if tx == target_tx:
                    params = [struct.unpack_from("<I", chunk, p)[0] for p in range(i + 12, i + clen, 4)]
                    p_hex = [f"0x{p:08X}" for p in params]
                    abs_offset = max(0, data_offset - 2048) + i
                    print(f"COMMAND at 0x{abs_offset:08X}: OpCode=0x{code:04X}, TxID={tx}, Params={p_hex}")
                    print(f"    Raw bytes: {chunk[i:i+clen].hex(' ')}")

    # Also show the Data payload at data_offset
    d_len, d_type, d_code, d_tx = struct.unpack_from("<IHHI", data, data_offset)
    d_payload = data[data_offset + 12:data_offset + d_len]
    print(f"DATA payload (Len={d_len}): {d_payload.hex(' ')}")
