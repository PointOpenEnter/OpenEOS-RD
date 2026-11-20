//! Canon CR2 (TIFF-based) RAW parser.
//!
//! Extracts Model, Serial Number, Date, Lens, and Shooting parameters
//! from TIFF IFD0, EXIF IFD, and Canon MakerNote tags.

use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::Path;
use byteorder::{BigEndian, LittleEndian, ReadBytesExt};
use super::RawAnalysisResult;

pub fn parse_cr2(path: &Path, result: &mut RawAnalysisResult) -> Result<(), String> {
    let mut file = File::open(path).map_err(|e| format!("Cannot open CR2: {e}"))?;
    let mut header = [0u8; 16];
    file.read_exact(&mut header).map_err(|e| format!("Cannot read CR2 header: {e}"))?;

    let is_little_endian = match &header[0..2] {
        b"II" => true,
        b"MM" => false,
        _ => return Err("Invalid TIFF header magic in CR2".to_string()),
    };

    if &header[8..10] != b"CR" {
        result.notes.push("Notice: Missing Canon CR2 signature at offset 8, parsing as generic TIFF".to_string());
    }

    if is_little_endian {
        parse_tiff::<LittleEndian>(&mut file, result)
    } else {
        parse_tiff::<BigEndian>(&mut file, result)
    }
}

fn parse_tiff<E: byteorder::ByteOrder>(file: &mut File, result: &mut RawAnalysisResult) -> Result<(), String> {
    file.seek(SeekFrom::Start(4)).map_err(|e| e.to_string())?;
    let ifd0_offset = file.read_u32::<E>().map_err(|e| e.to_string())? as u64;

    let mut exif_ifd_offset = 0u64;
    let mut makernote_offset = 0u64;

    // Parse IFD0
    if ifd0_offset > 0 && file.seek(SeekFrom::Start(ifd0_offset)).is_ok() {
        let entry_count = file.read_u16::<E>().unwrap_or(0);
        for _ in 0..entry_count {
            let tag = file.read_u16::<E>().unwrap_or(0);
            let _tag_type = file.read_u16::<E>().unwrap_or(0);
            let count = file.read_u32::<E>().unwrap_or(0);
            let value_or_offset = file.read_u32::<E>().unwrap_or(0);

            match tag {
                0x0110 => {
                    // Model
                    if let Ok(s) = read_ascii::<E>(file, count, value_or_offset) {
                        result.camera_model = Some(s.trim().to_string());
                    }
                }
                0x0132 => {
                    // DateTime
                    if let Ok(s) = read_ascii::<E>(file, count, value_or_offset) {
                        result.date_time = Some(s.trim().to_string());
                    }
                }
                0x8769 => {
                    exif_ifd_offset = value_or_offset as u64;
                }
                _ => {}
            }
        }
    }

    // Parse EXIF IFD
    if exif_ifd_offset > 0 && file.seek(SeekFrom::Start(exif_ifd_offset)).is_ok() {
        let entry_count = file.read_u16::<E>().unwrap_or(0);
        for _ in 0..entry_count {
            let tag = file.read_u16::<E>().unwrap_or(0);
            let _tag_type = file.read_u16::<E>().unwrap_or(0);
            let count = file.read_u32::<E>().unwrap_or(0);
            let value_or_offset = file.read_u32::<E>().unwrap_or(0);

            match tag {
                0x927C => {
                    makernote_offset = value_or_offset as u64;
                }
                0xA431 => {
                    // BodySerialNumber
                    if let Ok(s) = read_ascii::<E>(file, count, value_or_offset) {
                        if !s.trim().is_empty() {
                            result.serial_number = Some(s.trim().to_string());
                        }
                    }
                }
                0xA434 => {
                    // LensModel
                    if let Ok(s) = read_ascii::<E>(file, count, value_or_offset) {
                        result.lens_model = Some(s.trim().to_string());
                    }
                }
                _ => {}
            }
        }
    }

    // Parse Canon MakerNote
    if makernote_offset > 0 && file.seek(SeekFrom::Start(makernote_offset)).is_ok() {
        let entry_count = file.read_u16::<E>().unwrap_or(0);
        for _ in 0..entry_count {
            let tag = file.read_u16::<E>().unwrap_or(0);
            let _tag_type = file.read_u16::<E>().unwrap_or(0);
            let count = file.read_u32::<E>().unwrap_or(0);
            let value_or_offset = file.read_u32::<E>().unwrap_or(0);

            match tag {
                0x000C => {
                    // Camera Serial Number (in MakerNote)
                    if result.serial_number.is_none() {
                        if count <= 4 {
                            result.serial_number = Some(format!("{:010}", value_or_offset));
                        } else if let Ok(s) = read_ascii::<E>(file, count, value_or_offset) {
                            result.serial_number = Some(s.trim().to_string());
                        }
                    }
                }
                // QA-FIX: Removed dangerous tag 0x0001 allocating huge buffers,
                // and removed unverified heuristic from tag 0x0093.
                _ => {}
            }
        }
    }

    Ok(())
}

fn read_ascii<E: byteorder::ByteOrder>(file: &mut File, count: u32, offset: u32) -> Result<String, ()> {
    // QA-FIX: Safe upper bound on count
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
