//! Nikon NEF RAW Parser.
//!
//! Extracts Model, Serial Number, Date, and cumulative Shutter Count (MakerNote Tag 0x00A7).

use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::Path;
use byteorder::{BigEndian, LittleEndian, ReadBytesExt};
use super::RawAnalysisResult;

pub fn parse_nef(path: &Path, result: &mut RawAnalysisResult) -> Result<(), String> {
    let mut file = File::open(path).map_err(|e| format!("Cannot open NEF: {e}"))?;
    let mut header = [0u8; 8];
    file.read_exact(&mut header).map_err(|e| e.to_string())?;

    let is_little_endian = match &header[0..2] {
        b"II" => true,
        b"MM" => false,
        _ => return Err("Invalid TIFF magic in NEF".to_string()),
    };

    if is_little_endian {
        walk_nef_tiff::<LittleEndian>(&mut file, result)
    } else {
        walk_nef_tiff::<BigEndian>(&mut file, result)
    }
}

fn walk_nef_tiff<E: byteorder::ByteOrder>(file: &mut File, result: &mut RawAnalysisResult) -> Result<(), String> {
    file.seek(SeekFrom::Start(4)).map_err(|e| e.to_string())?;
    let ifd0_offset = file.read_u32::<E>().map_err(|e| e.to_string())? as u64;

    let mut exif_ifd_offset = 0u64;
    let mut makernote_offset = 0u64;

    // 1. IFD0
    if ifd0_offset > 0 {
        if file.seek(SeekFrom::Start(ifd0_offset)).is_ok() {
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
    }

    // 2. EXIF IFD
    if exif_ifd_offset > 0 {
        if file.seek(SeekFrom::Start(exif_ifd_offset)).is_ok() {
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
                        // Serial
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
    }

    // 3. Nikon MakerNote
    if makernote_offset > 0 {
        if file.seek(SeekFrom::Start(makernote_offset)).is_ok() {
            let mut prefix = [0u8; 10];
            let _ = file.read_exact(&mut prefix);

            // Nikon Type 3 MakerNotes start with "Nikon\0" followed by 4 version bytes and a TIFF header at +10
            let mn_sub_offset = if &prefix[0..6] == b"Nikon\x00" {
                makernote_offset + 10
            } else {
                makernote_offset
            };

            if file.seek(SeekFrom::Start(mn_sub_offset)).is_ok() {
                let mut sub_hdr = [0u8; 8];
                if file.read_exact(&mut sub_hdr).is_ok() {
                    let sub_le = &sub_hdr[0..2] == b"II";
                    if sub_le {
                        parse_nikon_mn::<LittleEndian>(file, mn_sub_offset, result);
                    } else {
                        parse_nikon_mn::<BigEndian>(file, mn_sub_offset, result);
                    }
                }
            }
        }
    }

    Ok(())
}

fn parse_nikon_mn<E: byteorder::ByteOrder>(file: &mut File, base_offset: u64, result: &mut RawAnalysisResult) {
    if file.seek(SeekFrom::Start(base_offset + 4)).is_err() {
        return;
    }
    let ifd_rel = file.read_u32::<E>().unwrap_or(0) as u64;
    let ifd_target = base_offset + ifd_rel;

    if file.seek(SeekFrom::Start(ifd_target)).is_err() {
        return;
    }

    let count = file.read_u16::<E>().unwrap_or(0);
    for _ in 0..count {
        let tag = file.read_u16::<E>().unwrap_or(0);
        let _tag_type = file.read_u16::<E>().unwrap_or(0);
        let val_count = file.read_u32::<E>().unwrap_or(0);
        let val_or_offset = file.read_u32::<E>().unwrap_or(0);

        match tag {
            0x00A7 => {
                // Nikon Shutter Count Tag!
                if val_count <= 4 {
                    result.shutter_count = Some(val_or_offset);
                    result.is_verified = true;
                } else {
                    let pos = file.stream_position().unwrap_or(0);
                    let target = base_offset + val_or_offset as u64;
                    if file.seek(SeekFrom::Start(target)).is_ok() {
                        let cnt = file.read_u32::<E>().unwrap_or(0);
                        if cnt > 0 {
                            result.shutter_count = Some(cnt);
                            result.is_verified = true;
                        }
                    }
                    let _ = file.seek(SeekFrom::Start(pos));
                }
            }
            0x001D => {
                // Nikon Serial Number
                if result.serial_number.is_none() {
                    let pos = file.stream_position().unwrap_or(0);
                    let target = base_offset + val_or_offset as u64;
                    if file.seek(SeekFrom::Start(target)).is_ok() {
                        let mut buf = vec![0u8; val_count.min(64) as usize];
                        if file.read_exact(&mut buf).is_ok() {
                            let clean: Vec<u8> = buf.into_iter().take_while(|&b| b != 0).collect();
                            if let Ok(s) = String::from_utf8(clean) {
                                if !s.trim().is_empty() {
                                    result.serial_number = Some(s.trim().to_string());
                                }
                            }
                        }
                    }
                    let _ = file.seek(SeekFrom::Start(pos));
                }
            }
            _ => {}
        }
    }
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
