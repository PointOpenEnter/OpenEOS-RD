//! JPEG / EXIF / TIFF parser.
//!
//! - `parse_jpeg_exif` — файл JPEG: ищет APP1 "Exif\0\0" и разбирает вложенный TIFF.
//! - `parse_jpeg_bytes` — то же для JPEG в памяти (превью внутри RAF).
//! - `parse_tiff_buffer` — любой TIFF-блок в памяти (EXIF из JPEG, CMT1/CMT2 из CR3):
//!   IFD0 и EXIF sub-IFD (0x8769): модель, дата, серийный номер, объектив, экспозиция.

use std::fs::File;
use std::io::Read;
use std::path::Path;
use super::RawAnalysisResult;

/// Сколько байт читать из начала JPEG: APP1 с EXIF всегда в самом начале файла (лимит 64 КБ на сегмент).
const JPEG_HEAD_LIMIT: u64 = 512 * 1024;

pub fn parse_jpeg_exif(path: &Path, result: &mut RawAnalysisResult) -> Result<(), String> {
    let file = File::open(path).map_err(|e| format!("Cannot open JPEG: {e}"))?;
    let mut buf = Vec::new();
    file.take(JPEG_HEAD_LIMIT)
        .read_to_end(&mut buf)
        .map_err(|e| e.to_string())?;
    if !parse_jpeg_bytes(&buf, result) {
        return Err("Not a valid JPEG file (missing SOI marker 0xFFD8)".to_string());
    }
    Ok(())
}

/// Разбирает JPEG в памяти. Возвращает false, если это не JPEG.
pub fn parse_jpeg_bytes(buf: &[u8], result: &mut RawAnalysisResult) -> bool {
    if buf.len() < 4 || buf[0] != 0xFF || buf[1] != 0xD8 {
        return false;
    }
    let mut pos = 2usize;
    while pos + 4 <= buf.len() {
        if buf[pos] != 0xFF {
            pos += 1;
            continue;
        }
        let marker = buf[pos + 1];
        if marker == 0xFF {
            pos += 1; // заполняющие байты 0xFF
            continue;
        }
        if marker == 0xDA || marker == 0xD9 {
            break; // начало данных изображения / конец файла
        }
        if (0xD0..=0xD7).contains(&marker) || marker == 0x01 {
            pos += 2; // маркеры без длины
            continue;
        }
        let len = u16::from_be_bytes([buf[pos + 2], buf[pos + 3]]) as usize;
        if len < 2 {
            break;
        }
        let payload_start = pos + 4;
        let payload_end = (pos + 2 + len).min(buf.len());
        if marker == 0xE1 && payload_end >= payload_start + 6 && &buf[payload_start..payload_start + 6] == b"Exif\0\0" {
            parse_tiff_buffer(&buf[payload_start + 6..payload_end], result);
            return true;
        }
        pos += 2 + len;
    }
    true
}

#[derive(Clone, Copy)]
struct Tiff<'a> {
    buf: &'a [u8],
    le: bool,
}

impl<'a> Tiff<'a> {
    fn u16(&self, off: usize) -> Option<u16> {
        let b = self.buf.get(off..off + 2)?;
        Some(if self.le { u16::from_le_bytes([b[0], b[1]]) } else { u16::from_be_bytes([b[0], b[1]]) })
    }
    fn u32(&self, off: usize) -> Option<u32> {
        let b = self.buf.get(off..off + 4)?;
        let a = [b[0], b[1], b[2], b[3]];
        Some(if self.le { u32::from_le_bytes(a) } else { u32::from_be_bytes(a) })
    }
}

struct Entry {
    tag: u16,
    typ: u16,
    count: u32,
    /// Смещение 4-байтового поля значения/указателя внутри буфера
    field_off: usize,
}

impl Entry {
    fn value_offset(&self, t: &Tiff) -> Option<usize> {
        let unit = match self.typ {
            1 | 2 | 6 | 7 => 1,
            3 | 8 => 2,
            4 | 9 | 11 => 4,
            5 | 10 | 12 => 8,
            _ => 1,
        };
        let size = unit * self.count as usize;
        if size <= 4 {
            Some(self.field_off)
        } else {
            t.u32(self.field_off).map(|v| v as usize)
        }
    }

    fn ascii(&self, t: &Tiff) -> Option<String> {
        if self.typ != 2 || self.count == 0 || self.count > 1024 {
            return None;
        }
        let off = self.value_offset(t)?;
        let raw = t.buf.get(off..off + self.count as usize)?;
        let end = raw.iter().position(|&b| b == 0).unwrap_or(raw.len());
        let s = String::from_utf8_lossy(&raw[..end]).trim().to_string();
        if s.is_empty() { None } else { Some(s) }
    }

    fn uint(&self, t: &Tiff) -> Option<u32> {
        match self.typ {
            3 => t.u16(self.field_off).map(|v| v as u32),
            4 => t.u32(self.field_off),
            _ => None,
        }
    }

    fn rational(&self, t: &Tiff) -> Option<(u32, u32)> {
        if self.typ != 5 && self.typ != 10 {
            return None;
        }
        let off = self.value_offset(t)?;
        Some((t.u32(off)?, t.u32(off + 4)?))
    }
}

fn read_ifd(t: &Tiff, off: usize) -> Vec<Entry> {
    let mut out = Vec::new();
    let Some(n) = t.u16(off) else { return out };
    if n > 512 {
        return out; // защита от мусорных смещений
    }
    for i in 0..n as usize {
        let e = off + 2 + i * 12;
        let (Some(tag), Some(typ), Some(count)) = (t.u16(e), t.u16(e + 2), t.u32(e + 4)) else { break };
        out.push(Entry { tag, typ, count, field_off: e + 8 });
    }
    out
}

/// Разбирает TIFF-блок в памяти и заполняет поля, которые ещё не заданы.
pub fn parse_tiff_buffer(buf: &[u8], result: &mut RawAnalysisResult) {
    if buf.len() < 8 {
        return;
    }
    let le = match &buf[0..2] {
        b"II" => true,
        b"MM" => false,
        _ => return,
    };
    let t = Tiff { buf, le };
    let Some(ifd0) = t.u32(4) else { return };
    let ifd0_entries = read_ifd(&t, ifd0 as usize);

    let mut exif_off = None;
    apply_entries(&t, &ifd0_entries, result, &mut exif_off);
    if let Some(off) = exif_off {
        if off < buf.len() && off != ifd0 as usize {
            let exif_entries = read_ifd(&t, off);
            let mut ignored = None;
            apply_entries(&t, &exif_entries, result, &mut ignored);
        }
    }
}

fn apply_entries(t: &Tiff, entries: &[Entry], result: &mut RawAnalysisResult, exif_off: &mut Option<usize>) {
    for e in entries {
        match e.tag {
            0x0110 if result.camera_model.is_none() => result.camera_model = e.ascii(t),
            0x0132 if result.date_time.is_none() => result.date_time = e.ascii(t),
            0x9003 => {
                // DateTimeOriginal точнее DateTime из IFD0
                if let Some(d) = e.ascii(t) {
                    result.date_time = Some(d);
                }
            }
            0x8769 => *exif_off = t.u32(e.field_off).map(|v| v as usize),
            0xA431 if result.serial_number.is_none() => result.serial_number = e.ascii(t),
            0xA434 if result.lens_model.is_none() => result.lens_model = e.ascii(t),
            0x829A if result.exposure_time.is_none() => {
                if let Some((n, d)) = e.rational(t) {
                    if n > 0 && d > 0 {
                        result.exposure_time = Some(if n >= d {
                            format!("{:.1} с", n as f32 / d as f32)
                        } else {
                            format!("1/{} с", (d as f32 / n as f32).round() as u32)
                        });
                    }
                }
            }
            0x829D if result.f_number.is_none() => {
                if let Some((n, d)) = e.rational(t) {
                    if d > 0 {
                        result.f_number = Some(n as f32 / d as f32);
                    }
                }
            }
            0x8827 if result.iso.is_none() => result.iso = e.uint(t).filter(|&v| v > 0),
            0x920A if result.focal_length.is_none() => {
                if let Some((n, d)) = e.rational(t) {
                    if d > 0 {
                        result.focal_length = Some(n as f32 / d as f32);
                    }
                }
            }
            _ => {}
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Минимальный little-endian TIFF: IFD0 (Model, ExifIFD) + EXIF IFD (серийник, ISO, выдержка).
    fn sample_tiff() -> Vec<u8> {
        let mut b = vec![0u8; 256];
        b[0..4].copy_from_slice(b"II*\0");
        b[4..8].copy_from_slice(&8u32.to_le_bytes());
        let put_entry = |b: &mut Vec<u8>, at: usize, tag: u16, typ: u16, count: u32, val: u32| {
            b[at..at + 2].copy_from_slice(&tag.to_le_bytes());
            b[at + 2..at + 4].copy_from_slice(&typ.to_le_bytes());
            b[at + 4..at + 8].copy_from_slice(&count.to_le_bytes());
            b[at + 8..at + 12].copy_from_slice(&val.to_le_bytes());
        };
        // IFD0 @8: 2 entries
        b[8..10].copy_from_slice(&2u16.to_le_bytes());
        put_entry(&mut b, 10, 0x0110, 2, 14, 200); // Model -> @200
        put_entry(&mut b, 22, 0x8769, 4, 1, 60); // ExifIFD -> @60
        // EXIF IFD @60: 3 entries
        b[60..62].copy_from_slice(&3u16.to_le_bytes());
        put_entry(&mut b, 62, 0xA431, 2, 9, 220); // BodySerialNumber -> @220
        put_entry(&mut b, 74, 0x8827, 3, 1, 400); // ISO 400 (inline)
        put_entry(&mut b, 86, 0x829A, 5, 1, 240); // ExposureTime -> @240
        b[200..214].copy_from_slice(b"Canon EOS R10\0");
        b[220..229].copy_from_slice(b"12345678\0");
        b[240..244].copy_from_slice(&1u32.to_le_bytes());
        b[244..248].copy_from_slice(&250u32.to_le_bytes());
        b
    }

    #[test]
    fn tiff_walker_reads_ifd0_and_exif_ifd() {
        let mut r = RawAnalysisResult::default();
        parse_tiff_buffer(&sample_tiff(), &mut r);
        assert_eq!(r.camera_model.as_deref(), Some("Canon EOS R10"));
        assert_eq!(r.serial_number.as_deref(), Some("12345678"));
        assert_eq!(r.iso, Some(400));
        assert_eq!(r.exposure_time.as_deref(), Some("1/250 с"));
    }

    #[test]
    fn jpeg_app1_is_found() {
        let tiff = sample_tiff();
        let mut jpg = vec![0xFF, 0xD8, 0xFF, 0xE1];
        jpg.extend_from_slice(&((tiff.len() + 8) as u16).to_be_bytes());
        jpg.extend_from_slice(b"Exif\0\0");
        jpg.extend_from_slice(&tiff);
        jpg.extend_from_slice(&[0xFF, 0xD9]);
        let mut r = RawAnalysisResult::default();
        assert!(parse_jpeg_bytes(&jpg, &mut r));
        assert_eq!(r.serial_number.as_deref(), Some("12345678"));
    }
}
