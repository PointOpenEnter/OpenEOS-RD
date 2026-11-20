//! RAW, EXIF, and Camera Metadata inspection engine.
//!
//! Provides zero-copy, memory-safe parsing of:
//! - Nikon NEF (.NEF) — cumulative shutter count & body serial number
//! - Sony ARW (.ARW) — mechanical shutter & serial number
//! - Canon CR2 / CR3 (.CR2, .CR3) — DIGIC 8 / DIGIC X & ISOBMFF metadata
//! - Fujifilm RAF (.RAF) — Fuji camera model & metadata
//! - JPEG (.JPG, .JPEG) — APP1 EXIF structure

pub mod cr2;
pub mod cr3;
pub mod exif;
pub mod nef;
pub mod arw;
pub mod raf;

use std::path::Path;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct RawAnalysisResult {
    pub file_path: String,
    pub file_name: String,
    pub file_size_bytes: u64,
    pub format: String,
    pub camera_model: Option<String>,
    pub serial_number: Option<String>,
    pub shutter_count: Option<u32>,
    pub shutter_rating: Option<u32>,
    pub wear_percentage: Option<f32>,
    pub is_combined_shutter: bool,
    pub cbasic_sd_support: bool,
    pub date_time: Option<String>,
    pub lens_model: Option<String>,
    pub iso: Option<u32>,
    pub exposure_time: Option<String>,
    pub f_number: Option<f32>,
    pub focal_length: Option<f32>,
    pub firmware_version: Option<String>,
    pub has_mechanical_shutter: bool,
    pub is_verified: bool,
    pub notes: Vec<String>,
}

/// Analyze any supported camera file (NEF, ARW, CR2, CR3, RAF, JPG)
pub fn analyze_file<P: AsRef<Path>>(path: P) -> Result<RawAnalysisResult, String> {
    let path_ref = path.as_ref();
    let file_name = path_ref
        .file_name()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_else(|| "Unknown".to_string());
    
    let metadata = std::fs::metadata(path_ref)
        .map_err(|e| format!("Failed to read file metadata: {e}"))?;
    let file_size_bytes = metadata.len();

    let ext = path_ref
        .extension()
        .map(|s| s.to_string_lossy().to_lowercase())
        .unwrap_or_default();

    let mut result = RawAnalysisResult {
        file_path: path_ref.to_string_lossy().to_string(),
        file_name,
        file_size_bytes,
        has_mechanical_shutter: true,
        ..Default::default()
    };

    match ext.as_str() {
        "nef" => {
            result.format = "Nikon Raw (NEF)".to_string();
            nef::parse_nef(path_ref, &mut result)?;
        }
        "arw" => {
            result.format = "Sony Raw (ARW)".to_string();
            arw::parse_arw(path_ref, &mut result)?;
        }
        "cr2" => {
            result.format = "Canon Raw 2 (CR2)".to_string();
            cr2::parse_cr2(path_ref, &mut result)?;
        }
        "cr3" => {
            result.format = "Canon Raw 3 (CR3 / ISOBMFF)".to_string();
            cr3::parse_cr3(path_ref, &mut result)?;
        }
        "raf" => {
            result.format = "Fujifilm Raw (RAF)".to_string();
            raf::parse_raf(path_ref, &mut result)?;
        }
        "jpg" | "jpeg" => {
            result.format = "JPEG with EXIF".to_string();
            exif::parse_jpeg_exif(path_ref, &mut result)?;
        }
        _ => {
            return Err(format!("Unsupported file extension: .{ext}. Supported formats: .NEF, .ARW, .CR2, .CR3, .RAF, .JPG"));
        }
    }

    // High-precision fallback using system ExifTool if installed
    if result.shutter_count.is_none() {
        try_exiftool_fallback(path_ref, &mut result);
    }

    if result.shutter_count.is_none() && result.format.contains("Canon") {
        result.notes.push("В файлах Canon (CR2/CR3) производитель не сохраняет счетчик шторок в EXIF.".to_string());
    }

    // QA-FIX: Correlate with camera database to calculate shutter life / wear
    if let Some(ref model_str) = result.camera_model {
        if let Some(meta) = crate::models::find_by_name(model_str) {
            result.has_mechanical_shutter = meta.has_mechanical_shutter;
            result.cbasic_sd_support = meta.cbasic_sd_support;
            result.shutter_rating = Some(meta.shutter_rating);

            if !meta.has_mechanical_shutter {
                result.wear_percentage = None;
                result.notes.push("Камера не имеет механического затвора (сенсорный спуск). Ресурс физических шторок не ограничен.".to_string());
            } else if let Some(shutter) = result.shutter_count {
                if meta.shutter_rating > 0 {
                    let wear = (shutter as f32 / meta.shutter_rating as f32) * 100.0f32;
                    result.wear_percentage = Some((wear * 10.0f32).round() / 10.0f32);
                }
            }
        }
    }

    Ok(result)
}

fn try_exiftool_fallback(path: &Path, result: &mut RawAnalysisResult) {
    // Только системный PATH: никаких жёстко прописанных путей на диске пользователя.
    let exiftool_candidates = ["exiftool"];

    for exe in &exiftool_candidates {
        {
            use std::process::Command;
            #[cfg(windows)]
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x08000000;

            let mut cmd = Command::new(exe);
            cmd.arg("-s3")
                .arg("-ShutterCount")
                .arg("-TotalShoot")
                .arg(path);

            #[cfg(windows)]
            cmd.creation_flags(CREATE_NO_WINDOW);

            if let Ok(output) = cmd.output() {
                let out_str = String::from_utf8_lossy(&output.stdout);
                for line in out_str.lines() {
                    let clean = line.trim();
                    if let Ok(n) = clean.parse::<u32>() {
                        if n > 0 && n < 10_000_000 {
                            result.shutter_count = Some(n);
                            result.is_verified = true;
                            if result.format.contains("Canon") {
                                result.is_combined_shutter = true;
                            }
                            result.notes.push("Значение пробега подтверждено ExifTool (TotalShoot / ShutterCount)".to_string());
                            return;
                        }
                    }
                }
            }
        }
    }
}

/// Generates a standardized, structured plain text analysis report for copying or saving.
pub fn generate_raw_report_text(res: &RawAnalysisResult) -> String {
    use std::fmt::Write;
    let mut out = String::new();

    let _ = writeln!(out, "========================================================================");
    let _ = writeln!(out, "                    ОТЧЁТ АНАЛИЗА RAW / EXIF METADATA");
    let _ = writeln!(out, "========================================================================");
    let _ = writeln!(out, "Имя файла:            {}", res.file_name);
    let _ = writeln!(out, "Полный путь:          {}", res.file_path);
    let _ = writeln!(out, "Размер файла:         {:.2} МБ ({} байт)", res.file_size_bytes as f64 / 1_048_576.0, res.file_size_bytes);
    let _ = writeln!(out, "Формат контейнера:    {}", res.format);
    let _ = writeln!(out, "Модель камеры:        {}", res.camera_model.as_deref().unwrap_or("—"));
    let _ = writeln!(out, "Серийный номер:       {}", res.serial_number.as_deref().unwrap_or("—"));
    let _ = writeln!(out, "Версия прошивки:      {}", res.firmware_version.as_deref().unwrap_or("—"));
    let _ = writeln!(out, "Дата и время съёмки:  {}", res.date_time.as_deref().unwrap_or("—"));
    let _ = writeln!(out, "Объектив:             {}", res.lens_model.as_deref().unwrap_or("—"));
    let _ = writeln!(out);

    let _ = writeln!(out, "--- ДАННЫЕ ПРОБЕГА И ИЗНОСА ЗАТВОРА ---");
    if let Some(cnt) = res.shutter_count {
        if res.is_combined_shutter {
            let _ = writeln!(out, "Счетчик спусков:      {cnt} кадров (суммарно: электро + мех)");
        } else if !res.has_mechanical_shutter {
            let _ = writeln!(out, "Счетчик сенсора:      {cnt} кадров (электронный спуск)");
        } else {
            let _ = writeln!(out, "Пробег затвора:       {cnt} срабатываний (чистая механика)");
        }
    } else {
        let _ = writeln!(out, "Пробег затвора:       — (тег пробега не найден в метаданных)");
    }

    if res.has_mechanical_shutter {
        if let Some(rating) = res.shutter_rating {
            let _ = writeln!(out, "Паспортный ресурс:    {rating} срабатываний");
        }
        if let Some(wear) = res.wear_percentage {
            let status = if wear > 90.0 {
                "Критический износ шторок"
            } else if wear > 60.0 {
                "Средний эксплуатационный износ"
            } else {
                "Отличный запас ресурса"
            };
            if res.is_combined_shutter {
                let _ = writeln!(out, "Объем съемок:         {wear}% от ресурса механики [{status}]");
            } else {
                let _ = writeln!(out, "Износ затвора:        {wear}% [{status}]");
            }
        }
    } else {
        let _ = writeln!(out, "Тип затвора:          Электронный сенсор (физический износ отсутствует)");
    }

    let has_exposure = res.iso.is_some() || res.exposure_time.is_some() || res.f_number.is_some() || res.focal_length.is_some();
    if has_exposure {
    let _ = writeln!(out);
    let _ = writeln!(out, "--- ПАРАМЕТРЫ ЭКСПОЗИЦИИ ---");
    if let Some(iso) = res.iso {
        let _ = writeln!(out, "ISO:                  {iso}");
    }
    if let Some(ref exp) = res.exposure_time {
        let _ = writeln!(out, "Выдержка:             {exp}");
    }
    if let Some(f) = res.f_number {
        let _ = writeln!(out, "Диафрагма:            f/{f:.1}");
    }
    if let Some(fl) = res.focal_length {
        let _ = writeln!(out, "Фокусное расстояние:  {fl:.1} мм");
    }
    }

    if !res.notes.is_empty() {
        let _ = writeln!(out);
        let _ = writeln!(out, "--- ПРИМЕЧАНИЯ ---");
        for n in &res.notes {
            let _ = writeln!(out, "• {n}");
        }
    }

    let _ = writeln!(out);
    let _ = writeln!(out, "Сформировано в:       OpenEOS PRO v1.0 (Native Monolith Core)");
    let _ = writeln!(out, "========================================================================");

    out
}
