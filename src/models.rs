//! Canon & Multi-Brand Camera Models Registry
//!
//! Provides hardware-level metadata, shutter life ratings, processor generations,
//! and safety parameters for all supported cameras.
//!
//! rating_official=true only where Canon itself publishes the figure (Canon Canada
//! Full Frame EOS R comparison chart, 2024: R1/R3/R5m2/R5 500k, R6m2 400k).
//! All other ratings are estimates.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CameraType {
    Dslr,
    Mirrorless,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum DigicGeneration {
    Digic4,
    Digic5,
    Digic6,
    Digic7,
    Digic8,
    DigicX,
    DigicXAccelerator,
    Unknown,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CanonCameraMeta {
    pub name: &'static str,
    pub short_tag: &'static str,
    pub pid_hex: &'static str,
    pub camera_type: CameraType,
    pub generation: DigicGeneration,
    pub shutter_rating: u32,
    /// true только если ресурс затвора опубликован производителем (иначе это оценка).
    pub rating_official: bool,
    pub has_mechanical_shutter: bool,
    pub cbasic_sd_support: bool,
    pub verified_for_live_counters: bool,
}

pub static CANON_REGISTRY: &[CanonCameraMeta] = &[
    // Modern Mirrorless DIGIC X
    CanonCameraMeta {
        name: "Canon EOS R6 Mark II",
        short_tag: "R6m2",
        pid_hex: "330B",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::DigicX,
        shutter_rating: 400_000,
        rating_official: true,
        has_mechanical_shutter: true,
        cbasic_sd_support: false, // Заблокировано в DIGIC X прошивке
        verified_for_live_counters: true,
    },
    CanonCameraMeta {
        name: "Canon EOS R6 Mark III",
        short_tag: "R6m3",
        pid_hex: "3323",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::DigicX,
        shutter_rating: 500_000, // оценка; Canon не публикует, источники расходятся (300–500k)
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false, // Заблокировано в DIGIC X
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "Canon EOS R10",
        short_tag: "R10",
        pid_hex: "32F8",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::DigicX,
        shutter_rating: 120_000, // Canon ресурс для R10 не публикует: оценка
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false, // Заблокировано в DIGIC X
        verified_for_live_counters: true,
    },
    CanonCameraMeta {
        name: "Canon EOS R5",
        short_tag: "R5",
        pid_hex: "32F4",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::DigicX,
        shutter_rating: 500_000,
        rating_official: true,
        has_mechanical_shutter: true,
        cbasic_sd_support: true,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "Canon EOS R5 Mark II",
        short_tag: "R5m2",
        pid_hex: "3314",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::DigicXAccelerator,
        shutter_rating: 500_000,
        rating_official: true,
        has_mechanical_shutter: true,
        cbasic_sd_support: false, // Secure Boot v2
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "Canon EOS R6",
        short_tag: "R6",
        pid_hex: "32F5",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::DigicX,
        shutter_rating: 300_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: true, // Подтверждено на практике: R6 читается скриптом с SD-карты
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "Canon EOS R3",
        short_tag: "R3",
        pid_hex: "32FC",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::DigicX,
        shutter_rating: 500_000,
        rating_official: true,
        has_mechanical_shutter: true,
        cbasic_sd_support: false, // Заблокировано в DIGIC X
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "Canon EOS R7",
        short_tag: "R7",
        pid_hex: "32F7",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::DigicX,
        shutter_rating: 200_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false, // Заблокировано в DIGIC X
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "Canon EOS R8",
        short_tag: "R8",
        pid_hex: "330C",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::DigicX,
        shutter_rating: 120_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false, // Заблокировано в DIGIC X
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "Canon EOS R50",
        short_tag: "R50",
        pid_hex: "330D",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::DigicX,
        shutter_rating: 100_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false, // Заблокировано в DIGIC X
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "Canon EOS R100",
        short_tag: "R100",
        pid_hex: "3312",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::Digic8,
        shutter_rating: 100_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: true,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "Canon EOS R1",
        short_tag: "R1",
        pid_hex: "3313",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::DigicXAccelerator,
        shutter_rating: 500_000,
        rating_official: true,
        has_mechanical_shutter: true,
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "Canon EOS R",
        short_tag: "EOS R",
        pid_hex: "32DA",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::Digic8,
        shutter_rating: 200_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: true,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "Canon EOS RP",
        short_tag: "RP",
        pid_hex: "32E2",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::Digic8,
        shutter_rating: 100_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: true,
        verified_for_live_counters: false,
    },

    // Professional DSLRs (DIGIC 5/6/7/8)
    CanonCameraMeta {
        name: "Canon EOS 5D Mark IV",
        short_tag: "5D4",
        pid_hex: "3281",
        camera_type: CameraType::Dslr,
        generation: DigicGeneration::Digic6,
        shutter_rating: 150_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "Canon EOS 5D Mark III",
        short_tag: "5D3",
        pid_hex: "323A",
        camera_type: CameraType::Dslr,
        generation: DigicGeneration::Digic5,
        shutter_rating: 150_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "Canon EOS 6D Mark II",
        short_tag: "6D2",
        pid_hex: "32CA",
        camera_type: CameraType::Dslr,
        generation: DigicGeneration::Digic7,
        shutter_rating: 100_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "Canon EOS 6D",
        short_tag: "6D",
        pid_hex: "3250",
        camera_type: CameraType::Dslr,
        generation: DigicGeneration::Digic5,
        shutter_rating: 100_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "Canon EOS 7D Mark II",
        short_tag: "7D2",
        pid_hex: "326F",
        camera_type: CameraType::Dslr,
        generation: DigicGeneration::Digic6,
        shutter_rating: 200_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "Canon EOS 80D",
        short_tag: "80D",
        pid_hex: "3294",
        camera_type: CameraType::Dslr,
        generation: DigicGeneration::Digic6,
        shutter_rating: 100_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "Canon EOS 90D",
        short_tag: "90D",
        pid_hex: "32EA",
        camera_type: CameraType::Dslr,
        generation: DigicGeneration::Digic8,
        shutter_rating: 120_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "Canon EOS-1D X Mark II",
        short_tag: "1DX2",
        pid_hex: "3292",
        camera_type: CameraType::Dslr,
        generation: DigicGeneration::Digic6,
        shutter_rating: 400_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "Canon EOS-1D X Mark III",
        short_tag: "1DX3",
        pid_hex: "32E8",
        camera_type: CameraType::Dslr,
        generation: DigicGeneration::DigicX,
        shutter_rating: 500_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },

    // Multi-brand cameras for RAW / EXIF inspection
    CanonCameraMeta {
        name: "NIKON Z 9",
        short_tag: "Z 9",
        pid_hex: "",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::Unknown,
        shutter_rating: 500_000,
        rating_official: false,
        has_mechanical_shutter: false, // QA-FIX: No physical shutter
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "NIKON Z 8",
        short_tag: "Z 8",
        pid_hex: "",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::Unknown,
        shutter_rating: 500_000,
        rating_official: false,
        has_mechanical_shutter: false, // QA-FIX: No physical shutter
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "SONY ILCE-7M3",
        short_tag: "ILCE-7M3",
        pid_hex: "",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::Unknown,
        shutter_rating: 200_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "SONY ILCE-7M4",
        short_tag: "ILCE-7M4", // QA-FIX: matches without SONY prefix
        pid_hex: "",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::Unknown,
        shutter_rating: 200_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "SONY ILCE-7RM4",
        short_tag: "ILCE-7RM4",
        pid_hex: "",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::Unknown,
        shutter_rating: 500_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "SONY ILCE-7RM5",
        short_tag: "ILCE-7RM5",
        pid_hex: "",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::Unknown,
        shutter_rating: 500_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "SONY ILCE-1",
        short_tag: "ILCE-1",
        pid_hex: "",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::Unknown,
        shutter_rating: 500_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "SONY ILCE-9",
        short_tag: "ILCE-9",
        pid_hex: "",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::Unknown,
        shutter_rating: 500_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "SONY ILCE-6400",
        short_tag: "ILCE-6400",
        pid_hex: "",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::Unknown,
        shutter_rating: 200_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "NIKON Z 7",
        short_tag: "Z 7",
        pid_hex: "",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::Unknown,
        shutter_rating: 200_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "NIKON Z 6",
        short_tag: "Z 6",
        pid_hex: "",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::Unknown,
        shutter_rating: 200_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "NIKON D850",
        short_tag: "D850",
        pid_hex: "",
        camera_type: CameraType::Dslr,
        generation: DigicGeneration::Unknown,
        shutter_rating: 200_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "FUJIFILM X-T4",
        short_tag: "X-T4",
        pid_hex: "",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::Unknown,
        shutter_rating: 300_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "FUJIFILM X-T5",
        short_tag: "X-T5",
        pid_hex: "",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::Unknown,
        shutter_rating: 300_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },
    CanonCameraMeta {
        name: "FUJIFILM X100V",
        short_tag: "X100V",
        pid_hex: "",
        camera_type: CameraType::Mirrorless,
        generation: DigicGeneration::Unknown,
        shutter_rating: 100_000,
        rating_official: false,
        has_mechanical_shutter: true,
        cbasic_sd_support: false,
        verified_for_live_counters: false,
    },
];

/// Find camera metadata by Product ID (hex string, e.g. "330B")
pub fn find_by_pid(pid: &str) -> Option<&'static CanonCameraMeta> {
    let clean = pid.trim().trim_start_matches("0x").to_uppercase();
    CANON_REGISTRY.iter().find(|m| m.pid_hex == clean)
}

/// QA-FIX: True word boundary matcher.
/// Prevents "RP" from matching inside "NIKON CORPORATION"
fn matches_word(haystack: &str, needle: &str) -> bool {
    let needle_clean = needle.trim();
    if needle_clean.is_empty() {
        return false;
    }
    let mut start = 0;
    while let Some(pos) = haystack[start..].find(needle_clean) {
        let abs_pos = start + pos;
        let before_ok = if abs_pos == 0 {
            true
        } else {
            let prev = haystack[..abs_pos].chars().last().unwrap_or(' ');
            !prev.is_alphanumeric()
        };
        let after_idx = abs_pos + needle_clean.len();
        let after_ok = if after_idx >= haystack.len() {
            true
        } else {
            let next = haystack[after_idx..].chars().next().unwrap_or(' ');
            !next.is_alphanumeric()
        };

        if before_ok && after_ok {
            return true;
        }
        start = abs_pos + needle_clean.len();
    }
    false
}

/// Match camera metadata from DeviceInfo string, EXIF Model, or Windows FriendlyName
pub fn find_by_name(text: &str) -> Option<&'static CanonCameraMeta> {
    let lower = text.to_lowercase();
    // Sort matches: longest candidate names first
    let mut candidates: Vec<&'static CanonCameraMeta> = CANON_REGISTRY.iter().collect();
    candidates.sort_by(|a, b| b.name.len().cmp(&a.name.len()));

    for meta in candidates {
        let name_lower = meta.name.to_lowercase();
        let short_lower = meta.short_tag.to_lowercase();
        if matches_word(&lower, &name_lower) || matches_word(&lower, &short_lower) {
            return Some(meta);
        }
    }
    None
}
