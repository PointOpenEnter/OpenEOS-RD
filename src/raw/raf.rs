//! Fujifilm RAF RAW parser.
//!
//! Заголовок RAF: "FUJIFILMCCD-RAW", модель по смещению 28..60, по смещению 84 — Big-Endian
//! указатель на встроенный JPEG-превью и по смещению 88 — его длина. В этом JPEG лежит полный
//! EXIF (дата, серийный номер, объектив, экспозиция), который разбирается общим TIFF-парсером.
//! Счётчик затвора в EXIF Fujifilm не публикуется.

use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::Path;
use super::RawAnalysisResult;
use super::exif::parse_jpeg_bytes;

const MAX_PREVIEW_BYTES: u32 = 64 * 1024 * 1024;

pub fn parse_raf(path: &Path, result: &mut RawAnalysisResult) -> Result<(), String> {
    let mut file = File::open(path).map_err(|e| format!("Cannot open RAF: {e}"))?;
    let mut header = [0u8; 128];
    file.read_exact(&mut header).map_err(|e| e.to_string())?;

    if &header[0..12] != b"FUJIFILMCCD-" {
        return Err("Not a valid Fujifilm RAF header".to_string());
    }

    let model_slice = &header[28..60];
    let end = model_slice.iter().position(|&b| b == 0).unwrap_or(model_slice.len());
    if let Ok(m) = std::str::from_utf8(&model_slice[..end]) {
        let clean = m.trim();
        if !clean.is_empty() {
            result.camera_model = Some(if clean.starts_with('X') || clean.starts_with("GFX") {
                format!("FUJIFILM {clean}")
            } else {
                clean.to_string()
            });
        }
    }

    let jpeg_off = u32::from_be_bytes([header[84], header[85], header[86], header[87]]);
    let jpeg_len = u32::from_be_bytes([header[88], header[89], header[90], header[91]]);
    if jpeg_off >= 128 && jpeg_len > 4 && jpeg_len <= MAX_PREVIEW_BYTES {
        // EXIF находится в начале превью, всё JPEG целиком читать не нужно.
        let read_len = jpeg_len.min(512 * 1024) as usize;
        let mut jpeg = vec![0u8; read_len];
        if file.seek(SeekFrom::Start(jpeg_off as u64)).is_ok() && file.read_exact(&mut jpeg).is_ok() {
            // Модель уже взята из заголовка RAF (с префиксом FUJIFILM); EXIF дополняет остальные поля.
            parse_jpeg_bytes(&jpeg, result);
        }
    }

    result.notes.push("Fujifilm: счётчик затвора в EXIF файла не публикуется.".to_string());
    Ok(())
}
