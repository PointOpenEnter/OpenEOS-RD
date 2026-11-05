import os
import struct
from pathlib import Path

def dump_pe_exports(dll_path: Path):
    with open(dll_path, "rb") as f:
        data = f.read()

    if data[:2] != b"MZ":
        return []
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e_lfanew:e_lfanew+4] != b"PE\x00\x00":
        return []

    magic = struct.unpack_from("<H", data, e_lfanew + 24)[0]
    is_pe32_plus = (magic == 0x20B)
    num_rva_and_sizes_offset = e_lfanew + 24 + (108 if is_pe32_plus else 92)
    export_rva_offset = num_rva_and_sizes_offset + 4
    export_rva, export_size = struct.unpack_from("<II", data, export_rva_offset)

    if export_rva == 0 or export_size == 0:
        return []

    num_sections = struct.unpack_from("<H", data, e_lfanew + 6)[0]
    opt_header_size = struct.unpack_from("<H", data, e_lfanew + 20)[0]
    section_headers_offset = e_lfanew + 24 + opt_header_size

    def rva_to_offset(rva):
        for i in range(num_sections):
            sec_offset = section_headers_offset + i * 40
            sec_vsize, sec_va, sec_raw_size, sec_raw_offset = struct.unpack_from("<IIII", data, sec_offset + 8)
            if sec_va <= rva < sec_va + max(sec_vsize, sec_raw_size):
                return sec_raw_offset + (rva - sec_va)
        return None

    exp_file_offset = rva_to_offset(export_rva)
    if not exp_file_offset:
        return []

    num_names = struct.unpack_from("<I", data, exp_file_offset + 24)[0]
    names_rva = struct.unpack_from("<I", data, exp_file_offset + 32)[0]
    names_offset = rva_to_offset(names_rva)
    if not names_offset:
        return []

    names = []
    for i in range(num_names):
        name_rva = struct.unpack_from("<I", data, names_offset + i * 4)[0]
        n_offset = rva_to_offset(name_rva)
        if n_offset:
            end = data.find(b"\x00", n_offset)
            if end != -1:
                names.append(data[n_offset:end].decode("ascii", errors="replace"))
    return names

if __name__ == "__main__":
    dll = Path(__file__).parent / "EDSDK.dll"
    if dll.exists():
        exps = dump_pe_exports(dll)
        out_txt = Path(__file__).parent / "edsdk_exports.txt"
        out_txt.write_text("\n".join(sorted(exps)), encoding="utf-8")
        print(f"Dumped {len(exps)} exports to {out_txt}")
