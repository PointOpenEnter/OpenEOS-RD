//! Sony ARW (TIFF-based) RAW parser.
//!
//! Extracts Sony Model, Body Serial Number, Date, and Shutter Count (MakerNote Tag 36944)).

use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::Path;
use byteorder::{BigEndian, LittleEndian, ReadBytesExt};
use super::RawAnalysisResult;

pub fn parse_arw(path: &Path, result: &mut RawAnalysisResult) -> Result<(), String> {
    let mut file = File::open(path).map_err(|e| format!("Cannot open ARW: {e}"))?;
    let mut header = [0u8; 8];
    file.read_exact(&mut header).map_err(|e| e.to_string())?;

    let is_little_endian = match &header[0..2] {
        b"II" => true,
        b"MM" => false,
        _ => return Err("Invalid TIFF magic in ARW".to_string()),
    };

    if is_little_endian {
        walk_arw::<LittleEndian>(&mut file, result)
    } else {
        walk_arw::<BigEndian>(&mut file, result)
    }
}

fn walk_arw<E: byteorder::ByteOrder>(file: &mut File, result: &mut RawAnalysisResult) -> Result<(), String> {
    file.seek(SeekFrom::Start(4)).map_err(|e| e.to_string())?;
    let ifd0_offset = file.read_u32::<E>().map_err(|e| e.to_string())? as u64;

    let mut exif_ifd_offset = 0u64;
    let mut makernote_offset = 0u64;

    // IFD0
    if ifd0_offset > 0 && file.seek(SeekFrom::Start(ifd0_offset)).is_ok() {
        let count = file.read_u16::<E>().unwrap_or(0);
        for _ in 0..count {
            let tag = file.read_u16::<E>().unwrap_or(0);
            let _tag_type = file.read_u16::<E>().unwrap_or(0);
            let val_count = file.read_u32::<E>().unwrap_or(0);
            let val_or_offset = file.read_u32::<E>().unwrap_or(0);

            match tag {
                0x0110 => {
                    // Model
                    if let Ok(s) = read_ascii_str::<E>(file, val_count, val_or_offset) {
                        result.camera_model = Some(s.trim().to_string());
                    }
                }
                0x0132 => {
                    // Date
                    if let Ok(s) = read_ascii_str::<E>(file, val_count, val_or_offset) {
                        result.date_time = Some(s.trim().to_string());
                    }
                }
                0x8769 => {
                    exif_ifd_offset = val_or_offset as u64;
                }
                _ => {}
            }
        }
    }

    // EXIF IFD
    if exif_ifd_offset > 0 && file.seek(SeekFrom::Start(exif_ifd_offset)).is_ok() {
        let count = file.read_u16::<E>().unwrap_or(0);
        for _ in 0..count {
            let tag = file.read_u16::<E>().unwrap_or(0);
            let _tag_type = file.read_u16::<E>().unwrap_or(0);
            let val_count = file.read_u32::<E>().unwrap_or(0);
            let val_or_offset = file.read_u32::<E>().unwrap_or(0);

            match tag {
                0x927C => {
                    makernote_offset = val_or_offset as u64;
                }
                0xA431 => {
                    // Serial Number
                    if let Ok(s) = read_ascii_str::<E>(file, val_count, val_or_offset) {
                        let clean = s.trim();
                        if !clean.is_empty() {
                            result.serial_number = Some(clean.to_string());
                        }
                    }
                }
                _ => {}
            }
        }
    }

    // Sony MakerNote
    if makernote_offset > 0 && file.seek(SeekFrom::Start(makernote_offset)).is_ok() {
        let mut prefix = [0u8; 12];
        let _ = file.read_exact(&mut prefix);

        let mn_base = if &prefix[0..9] == b"SONY DSC " {
            makernote_offset + 12
        } else {
            makernote_offset
        };

        if file.seek(SeekFrom::Start(mn_base)).is_ok() {
            let count = file.read_u16::<E>().unwrap_or(0);
            for _ in 0..count {
                let tag = file.read_u16::<E>().unwrap_or(0);
                let tag_type = file.read_u16::<E>().unwrap_or(0);
                let val_count = file.read_u32::<E>().unwrap_or(0);
                let val_or_offset = file.read_u32::<E>().unwrap_or(0);

                if tag == 36944 /* Sony shutter-count tag */ && tag_type == 7 && val_count >= 0x40 {
                    // Tag9050 — зашифрованный блок (UNDEFINED). Значение всегда по указателю.
                    let cur_pos = file.stream_position().unwrap_or(0);
                    if file.seek(SeekFrom::Start(val_or_offset as u64)).is_ok() {
                        let read_len = (val_count as usize).min(512);
                        let mut blob = vec![0u8; read_len];
                        if file.read_exact(&mut blob).is_ok() {
                            sony_decipher(&mut blob);
                            let model = result.camera_model.clone().unwrap_or_default();
                            // Как raw_engine._decode_sony_block: у новых моделей счётчик по 0x0A,
                            // затем 0x3A (либо 0x32 для старой раскладки 9050a), затем 0x50.
                            let m = model.to_uppercase();
                            let mut cands: Vec<(usize, &str)> = Vec::new();
                            if ["7M5", "6700", "7CM2", "7CR", "1M2"].iter().any(|k| m.contains(k)) {
                                cands.push((0x0A, "9050 (новая раскладка)"));
                            }
                            if is_tag9050a_model(&model) {
                                cands.push((0x32, "9050a"));
                            }
                            cands.push((0x3A, "9050b/c"));
                            cands.push((0x50, "9050 (альт.)"));
                            for (off, layout) in cands {
                                if let Some(cnt) = read_u24_le(&blob, off) {
                                    if cnt > 0 && cnt < 5_000_000 {
                                        result.shutter_count = Some(cnt);
                                        result.notes.push(format!(
                                            "Sony: счётчик из расшифрованного блока Tag{layout}, смещение 0x{off:02X}.                                              Раскладка выбрана по модели; сверьте с ExifTool на эталонном файле этой модели."
                                        ));
                                        break;
                                    }
                                }
                            }
                        }
                    }
                    let _ = file.seek(SeekFrom::Start(cur_pos));
                }
            }
        }
    }

    Ok(())
}

fn read_ascii_str<E: byteorder::ByteOrder>(file: &mut File, count: u32, offset: u32) -> Result<String, ()> {
    if count == 0 || count > 512 {
        return Err(());
    }
    let pos = file.stream_position().map_err(|_| ())?;
    let target = if count <= 4 { pos - 4 } else { offset as u64 };
    file.seek(SeekFrom::Start(target)).map_err(|_| ())?;

    let mut buf = vec![0u8; count as usize];
    file.read_exact(&mut buf).map_err(|_| ())?;
    let _ = file.seek(SeekFrom::Start(pos));

    let clean: Vec<u8> = buf.into_iter().take_while(|&b| b != 0).collect();
    String::from_utf8(clean).map_err(|_| ())
}

/// Расшифровка блоков Sony MakerNote (Tag9050, Tag94xx): при записи каждый байт b < 249
/// заменяется на b^3 mod 249, байты 249..255 не меняются. Обратная таблица строится один раз.
pub fn sony_decipher(data: &mut [u8]) {
    let mut table = [0u8; 256];
    for (i, v) in table.iter_mut().enumerate() {
        *v = i as u8;
    }
    for b in 0u32..249 {
        let enc = (b * b * b) % 249;
        table[enc as usize] = b as u8;
    }
    for byte in data.iter_mut() {
        *byte = table[*byte as usize];
    }
}

/// Модели с ранней раскладкой Tag9050a (счётчик по смещению 0x32). Остальные — 0x3A.
fn is_tag9050a_model(model: &str) -> bool {
    let m = model.trim().to_uppercase();
    const OLD: &[&str] = &[
        "ILCE-7", "ILCE-7R", "ILCE-7S", "ILCE-7M2", "ILCE-7RM2", "ILCE-7SM2",
        "ILCE-5000", "ILCE-5100", "ILCE-6000", "ILCE-QX1",
    ];
    m.starts_with("NEX-") || m.starts_with("SLT-") || m.starts_with("ILCA-") || OLD.contains(&m.as_str())
}

fn read_u24_le(b: &[u8], off: usize) -> Option<u32> {
    let s = b.get(off..off + 3)?;
    Some(s[0] as u32 | (s[1] as u32) << 8 | (s[2] as u32) << 16)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sony_cipher_roundtrip() {
        let plain: Vec<u8> = (0u8..=255).collect();
        let mut data: Vec<u8> = plain
            .iter()
            .map(|&b| if b < 249 { ((b as u32).pow(3) % 249) as u8 } else { b })
            .collect();
        sony_decipher(&mut data);
        assert_eq!(data, plain);
    }

    #[test]
    fn tag9050_layout_by_model() {
        assert!(is_tag9050a_model("ILCE-7M2"));
        assert!(!is_tag9050a_model("ILCE-7M3"));
        assert!(!is_tag9050a_model("ILCE-7M4"));
    }
}
