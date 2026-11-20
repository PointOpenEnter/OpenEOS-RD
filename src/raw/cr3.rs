//! Canon CR3 (ISOBMFF) RAW parser.
//!
//! Разбирает боксы ftyp / moov / uuid / PRDT и TIFF-блоки CMT1/CMT2 (модель, дата, серийный номер,
//! объектив, экспозиция). Счётчик спусков: только если в метаданных есть XMP/XML-поле
//! TotalShoot / ShutterCount (встречается в файлах, прошедших через сторонний софт).
//! Дорожка Canon Timed Metadata (Track4/CTMD) не разбирается: эталонного CR3 со значением
//! счётчика, подтверждённым ExifTool, в проекте нет.

use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::Path;
use byteorder::{BigEndian, ReadBytesExt};
use super::RawAnalysisResult;

pub fn parse_cr3(path: &Path, result: &mut RawAnalysisResult) -> Result<(), String> {
    let mut file = File::open(path).map_err(|e| format!("Cannot open CR3: {e}"))?;
    let file_len = file.metadata().map_err(|e| e.to_string())?.len();

    if file_len < 16 {
        return Err("File too small to be a valid CR3 container".to_string());
    }

    // Verify ftyp box
    let ftyp_size = file.read_u32::<BigEndian>().map_err(|e| e.to_string())? as u64;
    let mut ftyp_type = [0u8; 4];
    file.read_exact(&mut ftyp_type).map_err(|e| e.to_string())?;

    if &ftyp_type != b"ftyp" {
        return Err("Not a valid ISOBMFF / CR3 container (missing 'ftyp' box)".to_string());
    }

    let mut major_brand = [0u8; 4];
    file.read_exact(&mut major_brand).map_err(|e| e.to_string())?;

    if &major_brand != b"crx " {
        result.notes.push(format!(
            "Notice: Major brand is '{}', expected 'crx '",
            String::from_utf8_lossy(&major_brand)
        ));
    }

    // Skip remainder of ftyp box
    if ftyp_size > 16 && ftyp_size <= file_len {
        file.seek(SeekFrom::Start(ftyp_size)).map_err(|e| e.to_string())?;
    }

    // Scan top-level boxes (moov, uuid, PRDT, etc.)
    while let Ok(pos) = file.stream_position() {
        if pos >= file_len || pos + 8 > file_len {
            break;
        }

        let box_size = file.read_u32::<BigEndian>().unwrap_or(0) as u64;
        let mut box_type = [0u8; 4];
        if file.read_exact(&mut box_type).is_err() {
            break;
        }

        let actual_size = if box_size == 1 {
            // 64-bit extended size
            file.read_u64::<BigEndian>().unwrap_or(0)
        } else if box_size == 0 {
            file_len - pos
        } else {
            box_size
        };

        if actual_size < 8 {
            break;
        }

        let next_pos = match pos.checked_add(actual_size) {
            Some(np) if np > pos && np <= file_len => np,
            _ => break,
        };

        match &box_type {
            b"moov" => {
                parse_moov_children(&mut file, next_pos, result);
            }
            b"uuid" => {
                let mut uuid_bytes = [0u8; 16];
                if file.read_exact(&mut uuid_bytes).is_ok() {
                    scan_payload_for_metadata(&mut file, next_pos, result);
                }
            }
            b"PRDT" => {
                let payload_len = (actual_size - 8).min(256) as usize;
                let mut name_buf = vec![0u8; payload_len];
                if file.read_exact(&mut name_buf).is_ok() {
                    let text = String::from_utf8_lossy(&name_buf);
                    let clean = text.trim_matches(char::from(0)).trim();
                    if !clean.is_empty() {
                        result.camera_model = Some(clean.to_string());
                    }
                }
            }
            _ => {}
        }

        if file.seek(SeekFrom::Start(next_pos)).is_err() {
            break;
        }
    }

    // If ShutterCount was not found in structured boxes, scan header stream (up to 8 MB)
    if result.shutter_count.is_none() {
        let _ = file.seek(SeekFrom::Start(0));
        let scan_limit = file_len.min(8 * 1024 * 1024) as usize;
        let mut head_buf = vec![0u8; scan_limit];
        if let Ok(n) = file.read(&mut head_buf) {
            extract_cr3_fields(&head_buf[..n], result);
        }
    }

    Ok(())
}

fn parse_moov_children(file: &mut File, moov_end: u64, result: &mut RawAnalysisResult) {
    while let Ok(pos) = file.stream_position() {
        if pos >= moov_end || pos + 8 > moov_end {
            break;
        }

        let box_size = file.read_u32::<BigEndian>().unwrap_or(0) as u64;
        let mut box_type = [0u8; 4];
        if file.read_exact(&mut box_type).is_err() {
            break;
        }

        let actual_size = if box_size == 1 {
            file.read_u64::<BigEndian>().unwrap_or(0)
        } else if box_size == 0 {
            moov_end - pos
        } else {
            box_size
        };

        if actual_size < 8 {
            break;
        }

        let next_pos = match pos.checked_add(actual_size) {
            Some(np) if np > pos && np <= moov_end => np,
            _ => break,
        };

        if &box_type == b"uuid" || &box_type == b"trak" || &box_type == b"meta" {
            scan_payload_for_metadata(file, next_pos, result);
        }

        if file.seek(SeekFrom::Start(next_pos)).is_err() {
            break;
        }
    }
}

fn scan_payload_for_metadata(file: &mut File, end_offset: u64, result: &mut RawAnalysisResult) {
    let curr = file.stream_position().unwrap_or(0);
    if curr >= end_offset {
        return;
    }

    // Read payload in blocks up to 1 MB for thorough XML & metadata scanning
    let to_read = (end_offset - curr).min(1024 * 1024) as usize;
    let mut buffer = vec![0u8; to_read];
    if file.read_exact(&mut buffer).is_err() {
        return;
    }

    extract_cr3_fields(&buffer, result);
}

/// Блоки CMT1..CMT4 внутри uuid-бокса Canon содержат обычные TIFF-структуры:
/// CMT1 — IFD0 (Model, DateTime), CMT2 — EXIF IFD (BodySerialNumber 0xA431, LensModel 0xA434,
/// экспозиция), CMT3 — Canon MakerNotes, CMT4 — GPS.
fn parse_cmt_boxes(buffer: &[u8], result: &mut RawAnalysisResult) {
    for name in [b"CMT1", b"CMT2"] {
        let mut from = 0usize;
        while let Some(rel) = buffer[from..].windows(4).position(|w| w == name) {
            let at = from + rel;
            from = at + 4;
            if at < 4 {
                continue;
            }
            let size = u32::from_be_bytes([buffer[at - 4], buffer[at - 3], buffer[at - 2], buffer[at - 1]]) as usize;
            let start = at + 4;
            if size < 16 || start + 4 > buffer.len() {
                continue;
            }
            let tiff = &buffer[start..(at - 4 + size).min(buffer.len())];
            if tiff.starts_with(b"II*\0") || tiff.starts_with(b"MM\0*") {
                // В CMT2 EXIF-теги лежат прямо в первом IFD блока; общий парсер
                // применяет одни и те же теги на любом уровне, поэтому вызов одинаковый.
                super::exif::parse_tiff_buffer(tiff, result);
                break;
            }
        }
    }
}

fn extract_cr3_fields(buffer: &[u8], result: &mut RawAnalysisResult) {
    parse_cmt_boxes(buffer, result);

    // 1. Look for Canon camera signature pattern "Canon EOS "
    let search_bytes = b"Canon EOS ";
    if result.camera_model.is_none() {
        if let Some(pos) = buffer.windows(search_bytes.len()).position(|w| w == search_bytes) {
            let slice = &buffer[pos..];
            let end_str = slice.iter().position(|&b| b == 0 || b == b'\n' || b == b'\r' || b < 32).unwrap_or(slice.len().min(40));
            if let Ok(model) = std::str::from_utf8(&slice[..end_str]) {
                result.camera_model = Some(model.trim().to_string());
            }
        }
    }

    // 2. Look for serial number patterns
    if result.serial_number.is_none() {
        let serial_tags: [&[u8]; 4] = [
            b"aux:SerialNumber>",
            b"SerialNumber>",
            b"BodySerialNumber>",
            b"BodyID>",
        ];
        for tag in serial_tags {
            if let Some(num) = extract_digits_after_tag(buffer, tag) {
                result.serial_number = Some(num.to_string());
                break;
            }
        }
        if result.serial_number.is_none() {
            let pattern = b"BodySerialNumber";
            if let Some(pos) = buffer.windows(pattern.len()).position(|w| w == pattern) {
                let slice = &buffer[pos + pattern.len()..];
                let digits: Vec<u8> = slice
                    .iter()
                    .skip_while(|&&b| !b.is_ascii_digit())
                    .take_while(|&&b| b.is_ascii_digit())
                    .copied()
                    .collect();
                if digits.len() >= 8 && digits.len() <= 16 {
                    if let Ok(s) = String::from_utf8(digits) {
                        result.serial_number = Some(s);
                    }
                }
            }
        }
    }

    // 3. Look for TotalShoot / TotalShutter / ShutterCount / ImageCount in CR3 metadata / XMP
    if result.shutter_count.is_none() {
        // Form A: <TotalShoot>12345</TotalShoot> or TotalShoot>12345<
        if let Some(cnt) = extract_digits_after_tag(buffer, b"TotalShoot>") {
            result.shutter_count = Some(cnt);
            result.is_verified = true;
            result.is_combined_shutter = true;
            result.notes.push("Canon: Счетчик TotalShoot (электро + мех) из метаданных CR3".to_string());
            return;
        }

        // Form B: <TotalShutter>12345</TotalShutter> or TotalShutter>12345<
        if let Some(cnt) = extract_digits_after_tag(buffer, b"TotalShutter>") {
            result.shutter_count = Some(cnt);
            result.is_verified = true;
            result.is_combined_shutter = true;
            result.notes.push("Canon: Счетчик TotalShutter из метаданных CR3".to_string());
            return;
        }

        // Form C: <x:ShutterCount>12345</x:ShutterCount> or ShutterCount>12345<
        if let Some(cnt) = extract_digits_after_tag(buffer, b"ShutterCount>") {
            result.shutter_count = Some(cnt);
            result.is_verified = true;
            result.is_combined_shutter = true;
            result.notes.push("Canon: ShutterCount из пакета XMP / CR3".to_string());
            return;
        }

        // Form D: ShutterCount="12345" or TotalShoot="12345"
        if let Some(cnt) = extract_digits_after_tag(buffer, b"ShutterCount=\"") {
            result.shutter_count = Some(cnt);
            result.is_verified = true;
            result.is_combined_shutter = true;
            result.notes.push("Canon: ShutterCount из атрибута XMP".to_string());
            return;
        }
        if let Some(cnt) = extract_digits_after_tag(buffer, b"TotalShoot=\"") {
            result.shutter_count = Some(cnt);
            result.is_verified = true;
            result.is_combined_shutter = true;
            result.notes.push("Canon: TotalShoot (электро + мех) из атрибута CR3".to_string());
            return;
        }
    }
}

fn extract_digits_after_tag(buffer: &[u8], tag: &[u8]) -> Option<u32> {
    let mut offset = 0;
    while let Some(rel) = buffer[offset..].windows(tag.len()).position(|w| w == tag) {
        let start = offset + rel + tag.len();
        let rest = &buffer[start..];

        let digits: Vec<u8> = rest
            .iter()
            .take(32)
            .skip_while(|&&b| b == b' ' || b == b'\t' || b == b'\r' || b == b'\n')
            .take_while(|&&b| b.is_ascii_digit())
            .copied()
            .collect();

        if !digits.is_empty() && digits.len() <= 8 {
            if let Ok(s) = std::str::from_utf8(&digits) {
                if let Ok(num) = s.parse::<u32>() {
                    if num > 0 && num < 10_000_000 {
                        return Some(num);
                    }
                }
            }
        }
        offset = start;
    }
    None
}
