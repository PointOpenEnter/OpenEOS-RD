//! Removable SD Card detection and volume inspection.
//!
//! High-speed, non-blocking enumeration of removable drives and SD cards.
//! Protects against Windows kernel timeouts on unready/empty card reader slots.

use serde::{Deserialize, Serialize};
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SdCardVolume {
    pub drive_letter: char,
    pub volume_name: String,
    pub file_system: String,
    pub total_bytes: u64,
    pub free_bytes: u64,
    pub is_removable: bool,
    pub is_bootable_eos: bool,
    pub has_cam_info: bool,
}

pub struct CardDetector;

#[cfg(windows)]
extern "system" {
    fn SetErrorMode(uMode: u32) -> u32;
}

#[cfg(windows)]
const SEM_FAILCRITICALERRORS: u32 = 0x0001;
#[cfg(windows)]
const SEM_NOOPENFILEERRORBOX: u32 = 0x8000;

impl CardDetector {
    /// Enumerate all connected removable drives / SD cards with zero lag
    pub fn scan_removable_drives() -> Vec<SdCardVolume> {
        let mut volumes = Vec::new();

        #[cfg(windows)]
        {
            // Suppress system modal error dialogues and media insertion timeouts
            unsafe {
                SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOOPENFILEERRORBOX);
            }

            let drive_mask = unsafe { windows::Win32::Storage::FileSystem::GetLogicalDrives() };

            // Scan removable letters (skipping A: and B: which are historic floppy drives)
            for letter in b'C'..=b'Z' {
                let bit_index = (letter - b'A') as u32;
                if (drive_mask & (1 << bit_index)) == 0 {
                    continue; // Skip non-existent drive letters instantly
                }

                // Never treat primary system drive C: as a removable SD card
                if letter == b'C' {
                    continue;
                }

                let drive_root = format!("{}:\\", letter as char);
                if let Ok(vol) = Self::inspect_drive(&drive_root, letter as char) {
                    if vol.is_removable {
                        volumes.push(vol);
                    }
                }
            }
        }

        volumes
    }

    #[cfg(windows)]
    fn inspect_drive(path_str: &str, letter: char) -> Result<SdCardVolume, ()> {
        use std::ffi::OsStr;
        use std::os::windows::ffi::OsStrExt;

        let wide_path: Vec<u16> = OsStr::new(path_str)
            .encode_wide()
            .chain(std::iter::once(0))
            .collect();

        unsafe {
            // 1. FAST CHECK: Only query removable media (DRIVE_REMOVABLE = 2)
            let drive_type = windows::Win32::Storage::FileSystem::GetDriveTypeW(
                windows::core::PCWSTR(wide_path.as_ptr()),
            );

            if drive_type != 2 {
                return Err(()); // Instantly skip fixed HDDs, SSDs, CD-ROMs, and network shares
            }

            // 2. Query volume details; if no media is in the card reader, this returns immediately
            let mut vol_name_buf = [0u16; 260];
            let mut fs_name_buf = [0u16; 260];
            let mut serial = 0u32;
            let mut max_comp = 0u32;
            let mut flags = 0u32;

            let ok = windows::Win32::Storage::FileSystem::GetVolumeInformationW(
                windows::core::PCWSTR(wide_path.as_ptr()),
                Some(&mut vol_name_buf),
                Some(&mut serial),
                Some(&mut max_comp),
                Some(&mut flags),
                Some(&mut fs_name_buf),
            );

            if ok.is_err() {
                return Err(()); // Drive not ready / empty card reader slot
            }

            let mut free_bytes_avail = 0u64;
            let mut total_bytes = 0u64;
            let mut total_free = 0u64;

            let _ = windows::Win32::Storage::FileSystem::GetDiskFreeSpaceExW(
                windows::core::PCWSTR(wide_path.as_ptr()),
                Some(&mut free_bytes_avail),
                Some(&mut total_bytes),
                Some(&mut total_free),
            );

            let vol_name = String::from_utf16_lossy(&vol_name_buf)
                .trim_matches(char::from(0))
                .to_string();
            let fs_name = String::from_utf16_lossy(&fs_name_buf)
                .trim_matches(char::from(0))
                .to_string();

            // Check if Canon Basic files and CAM_INFO.XML exist
            let is_bootable = Self::check_eos_boot_signature(path_str);
            let has_cam_info = PathBuf::from(path_str).join("CAM_INFO.XML").is_file()
                || PathBuf::from(path_str).join("cam_info.xml").is_file();

            Ok(SdCardVolume {
                drive_letter: letter,
                volume_name: vol_name,
                file_system: fs_name,
                total_bytes,
                free_bytes: total_free,
                is_removable: true,
                is_bootable_eos: is_bootable,
                has_cam_info,
            })
        }
    }

    fn check_eos_boot_signature(path_str: &str) -> bool {
        let script_req = PathBuf::from(path_str).join("script.req");
        let extend_m = PathBuf::from(path_str).join("extend.m");
        script_req.exists() && extend_m.exists()
    }
}
