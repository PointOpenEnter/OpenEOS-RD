//! Canon Basic / Magic Lantern / CHDK SD-card bootloader preparator.
//!
//! Replicates Canon Basic SD-card procedures:
//! - Writing ASCII "SCRIPT" marker at sector 0 offset 0x1F0 (FAT32 VBR boot record)
//! - FAT32 quick formatting with volume label OPENEOS
//! - Writing extend.m and script.req payloads
//! - Parsing camera diagnostic report CAM_INFO.XML

use std::fs::File;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CamErrorItem {
    pub code: String,
    /// None when <Count> is missing/malformed (never invented).
    pub count: Option<u32>,
    pub description: String,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CamInfoReport {
    pub file_path: String,
    pub body_id: Option<String>,
    pub firmware: Option<String>,
    pub total_shutter: Option<u32>,      // Pure mechanical shutter count!
    pub total_shoot: Option<u32>,        // Combined (electronic + mechanical)
    pub power_on_count: Option<u32>,
    pub total_running_time: Option<String>,
    pub errors: Vec<CamErrorItem>,
}

pub struct BootflagManager;

impl BootflagManager {
    /// Formats the target SD card in FAT32 using Windows format.com
    pub fn format_card_fat32(drive_letter: char, label: &str) -> Result<String, String> {
        #[cfg(windows)]
        {
            use std::process::{Command, Stdio};
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x08000000;

            let sysroot = std::env::var("SystemRoot").unwrap_or_else(|_| r"C:\Windows".to_string());
            let format_exe = format!(r"{}\System32\format.com", sysroot);
            let drive_arg = format!("{}:", drive_letter);
            let vol_arg = format!("/V:{}", if label.is_empty() { "OPENEOS" } else { label });

            let mut child = Command::new(&format_exe)
                .args(&[&drive_arg, "/FS:FAT32", &vol_arg, "/Q", "/X", "/Y"])
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .creation_flags(CREATE_NO_WINDOW)
                .spawn()
                .map_err(|e| format!("Не удалось запустить format.com: {e}"))?;

            if let Some(mut stdin) = child.stdin.take() {
                let _ = stdin.write_all(b"\r\n\r\n\r\n");
            }

            let output = child
                .wait_with_output()
                .map_err(|e| format!("Ошибка выполнения форматирования: {e}"))?;

            if !output.status.success() {
                let err_msg = String::from_utf8_lossy(&output.stderr);
                let out_msg = String::from_utf8_lossy(&output.stdout);
                return Err(format!("Сбой форматирования: {} {}", err_msg.trim(), out_msg.trim()));
            }

            // Pause briefly for Windows volume manager to remount
            std::thread::sleep(std::time::Duration::from_millis(1000));
            Ok("Карта памяти успешно отформатирована в FAT32 (метка OPENEOS)".to_string())
        }
        #[cfg(not(windows))]
        {
            Err("Форматирование карты поддерживается только в Windows".to_string())
        }
    }

    /// Write ASCII "SCRIPT" marker at sector offset 0x1F0 of the SD card volume
    pub fn write_script_marker(drive_letter: char) -> Result<String, String> {
        #[cfg(windows)]
        {
            use self::win_raw::*;
            use std::ffi::OsStr;
            use std::os::windows::ffi::OsStrExt;

            let volume_path = format!(r"\\.\{}:", drive_letter);
            let wide_path: Vec<u16> = OsStr::new(&volume_path)
                .encode_wide()
                .chain(std::iter::once(0))
                .collect();

            unsafe {
                let h_vol = CreateFileW(
                    wide_path.as_ptr(),
                    GENERIC_READ | GENERIC_WRITE,
                    FILE_SHARE_READ | FILE_SHARE_WRITE,
                    std::ptr::null_mut(),
                    OPEN_EXISTING,
                    0,
                    std::ptr::null_mut(),
                );

                if h_vol == INVALID_HANDLE_VALUE || h_vol.is_null() {
                    let err = GetLastError();
                    return Err(format!(
                        "Не удалось открыть том {} (код ошибки {}). Запустите OpenEOS от имени Администратора для прямой записи в сектор!",
                        volume_path, err
                    ));
                }

                // 1. Lock volume
                let mut locked = false;
                let mut dw = 0u32;
                for _ in 0..10 {
                    if DeviceIoControl(
                        h_vol,
                        FSCTL_LOCK_VOLUME,
                        std::ptr::null(),
                        0,
                        std::ptr::null_mut(),
                        0,
                        &mut dw,
                        std::ptr::null_mut(),
                    ) != 0 {
                        locked = true;
                        break;
                    }
                    std::thread::sleep(std::time::Duration::from_millis(200));
                }

                if !locked {
                    CloseHandle(h_vol);
                    return Err("Том занят другой программой (Проводник Windows / антивирус). Закройте открытые папки карты и повторите.".to_string());
                }

                // 2. Dismount volume
                let _ = DeviceIoControl(
                    h_vol,
                    FSCTL_DISMOUNT_VOLUME,
                    std::ptr::null(),
                    0,
                    std::ptr::null_mut(),
                    0,
                    &mut dw,
                    std::ptr::null_mut(),
                );

                // 3. Read sector 0 (512 bytes)
                let mut sector = [0u8; 512];
                let mut bytes_read = 0u32;
                if ReadFile(
                    h_vol,
                    sector.as_mut_ptr() as *mut _,
                    512,
                    &mut bytes_read,
                    std::ptr::null_mut(),
                ) == 0 || bytes_read != 512 {
                    if locked {
                        let _ = DeviceIoControl(h_vol, FSCTL_UNLOCK_VOLUME, std::ptr::null(), 0, std::ptr::null_mut(), 0, &mut dw, std::ptr::null_mut());
                    }
                    CloseHandle(h_vol);
                    return Err("Не удалось прочитать загрузочный сектор карты памяти.".to_string());
                }

                // 4. Validate boot signature 0x55AA at offset 0x1FE
                if sector[0x1FE] != 0x55 || sector[0x1FF] != 0xAA {
                    if locked {
                        let _ = DeviceIoControl(h_vol, FSCTL_UNLOCK_VOLUME, std::ptr::null(), 0, std::ptr::null_mut(), 0, &mut dw, std::ptr::null_mut());
                    }
                    CloseHandle(h_vol);
                    return Err("Сигнатура 0x55AA в конце сектора не найдена. Запись отменена для защиты носителя.".to_string());
                }

                // 5. Write "SCRIPT" at offset 0x1F0
                let marker = b"SCRIPT";
                sector[0x1F0..0x1F0 + marker.len()].copy_from_slice(marker);

                // Rewind to sector 0
                if SetFilePointerEx(h_vol, 0, std::ptr::null_mut(), FILE_BEGIN) == 0 {
                    if locked {
                        let _ = DeviceIoControl(h_vol, FSCTL_UNLOCK_VOLUME, std::ptr::null(), 0, std::ptr::null_mut(), 0, &mut dw, std::ptr::null_mut());
                    }
                    CloseHandle(h_vol);
                    return Err("Не удалось позиционироваться на начало сектора 0.".to_string());
                }

                // Write modified sector
                let mut bytes_written = 0u32;
                if WriteFile(
                    h_vol,
                    sector.as_ptr() as *const _,
                    512,
                    &mut bytes_written,
                    std::ptr::null_mut(),
                ) == 0 || bytes_written != 512 {
                    let err = GetLastError();
                    if locked {
                        let _ = DeviceIoControl(h_vol, FSCTL_UNLOCK_VOLUME, std::ptr::null(), 0, std::ptr::null_mut(), 0, &mut dw, std::ptr::null_mut());
                    }
                    CloseHandle(h_vol);
                    return Err(format!("Сбой записи сектора (код ошибки {err}). Требуются права Администратора!"));
                }

                // 6. Verify sector write
                let _ = SetFilePointerEx(h_vol, 0, std::ptr::null_mut(), FILE_BEGIN);
                let mut verify_buf = [0u8; 512];
                let mut v_read = 0u32;
                let _ = ReadFile(h_vol, verify_buf.as_mut_ptr() as *mut _, 512, &mut v_read, std::ptr::null_mut());

                // Unlock and close
                if locked {
                    let _ = DeviceIoControl(h_vol, FSCTL_UNLOCK_VOLUME, std::ptr::null(), 0, std::ptr::null_mut(), 0, &mut dw, std::ptr::null_mut());
                }
                CloseHandle(h_vol);

                if &verify_buf[0x1F0..0x1F6] != b"SCRIPT" {
                    return Err("Верификация не удалась: маркер SCRIPT не подтвержден после записи.".to_string());
                }

                Ok("Флаг SCRIPT успешно записан в загрузочный сектор 0!".to_string())
            }
        }
        #[cfg(not(windows))]
        {
            Err("Запись boot-сектора поддерживается только в Windows".to_string())
        }
    }

    /// Записывает файл, сбрасывает на носитель (sync_all) и перечитывает: содержимое должно совпасть.
    fn write_and_verify(path: &Path, content: &[u8]) -> Result<(), String> {
        let name = path.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
        let mut f = File::create(path).map_err(|e| format!("Не удалось создать {name}: {e}"))?;
        f.write_all(content).map_err(|e| format!("Не удалось записать {name}: {e}"))?;
        f.sync_all().map_err(|e| format!("Не удалось сбросить {name} на карту (sync): {e}"))?;
        drop(f);
        let back = std::fs::read(path).map_err(|e| format!("Не удалось перечитать {name}: {e}"))?;
        if back != content {
            return Err(format!("Проверка чтения {name} не удалась: записанное содержимое не совпало."));
        }
        Ok(())
    }

    /// Write Canon Basic diagnostic scripts (extend.m + script.req), with sync and read-back verification.
    pub fn write_canon_basic_scripts<P: AsRef<Path>>(card_root: P) -> Result<(), String> {
        let root = card_root.as_ref();
        if !root.exists() {
            return Err("Указанный путь к карте памяти не существует".to_string());
        }

        // 1. script.req trigger for Canon Basic bootloader
        Self::write_and_verify(&root.join("script.req"), b"for DC_scriptdisk
")?;

        // 2. extend.m script with CamInfo_Debug(1) payload
        let script_payload = "private sub Initialize()
System.Create()
CamInfo_Debug(1)
end sub
";
        Self::write_and_verify(&root.join("extend.m"), script_payload.as_bytes())?;

        Ok(())
    }

    /// Full preparation: format FAT32, write SCRIPT marker, copy extend.m + script.req.
    /// Любой сбой (в том числе записи маркера в сектор 0) возвращает Err: карта НЕ загрузочная.
    pub fn prepare_full_card(drive_letter: char, format_first: bool) -> Result<String, String> {
        let drive_root = format!("{}:\\", drive_letter);
        Self::prepare_card_steps(
            Path::new(&drive_root),
            format_first,
            || Self::format_card_fat32(drive_letter, "OPENEOS"),
            || Self::write_script_marker(drive_letter),
        )
    }

    /// Логика подготовки карты с внедряемыми шагами (для тестов без физического носителя).
    pub fn prepare_card_steps<F, M>(
        drive_root: &Path,
        format_first: bool,
        format_step: F,
        marker_step: M,
    ) -> Result<String, String>
    where
        F: FnOnce() -> Result<String, String>,
        M: FnOnce() -> Result<String, String>,
    {
        let mut log_messages = Vec::new();

        if format_first {
            match format_step() {
                Ok(msg) => log_messages.push(msg),
                Err(e) => return Err(format!("Ошибка форматирования: {e}")),
            }
        }

        match marker_step() {
            Ok(msg) => log_messages.push(msg),
            Err(e) => {
                return Err(format!(
                    "Карта НЕ загрузочная: не удалось записать маркер SCRIPT в сектор 0: {e}"
                ));
            }
        }

        match Self::write_canon_basic_scripts(drive_root) {
            Ok(()) => log_messages.push("Скрипты extend.m и script.req записаны и проверены чтением.".to_string()),
            Err(e) => return Err(format!("Ошибка записи скриптов: {e}")),
        }

        Ok(log_messages.join("
"))
    }

    /// Check if CAM_INFO.XML exists on the card and parse it
    pub fn find_and_parse_cam_info(drive_letter: char) -> Option<CamInfoReport> {
        let drive_root = format!("{}:\\", drive_letter);
        let path = PathBuf::from(&drive_root).join("CAM_INFO.XML");
        if path.is_file() {
            return Self::parse_cam_info_xml(&path).ok();
        }
        let lower_path = PathBuf::from(&drive_root).join("cam_info.xml");
        if lower_path.is_file() {
            return Self::parse_cam_info_xml(&lower_path).ok();
        }
        None
    }

    /// Parse CAM_INFO.XML diagnostic dump generated by Canon Basic
    /// (mirrors Python `parse_cam_info_xml`: size limit 4 MiB, 0 bytes rejected).
    pub fn parse_cam_info_xml(path: &Path) -> Result<CamInfoReport, String> {
        const MAX_CAM_INFO_XML_BYTES: u64 = 4 * 1024 * 1024;
        let mut file = File::open(path).map_err(|e| format!("Cannot open {}: {e}", path.display()))?;
        let size = file.metadata().map_err(|e| format!("Cannot stat XML: {e}"))?.len();
        if size == 0 || size > MAX_CAM_INFO_XML_BYTES {
            return Err(format!("Invalid XML size: {size} bytes"));
        }
        let mut bytes = Vec::new();
        file.read_to_end(&mut bytes).map_err(|e| format!("Cannot read XML: {e}"))?;
        let content = Self::decode_xml_bytes(&bytes);
        Self::parse_cam_info_str(&content, &path.to_string_lossy())
    }

    /// Decode bytes tolerantly (UTF-8 / UTF-16 BOM); never fails on odd encodings.
    fn decode_xml_bytes(bytes: &[u8]) -> String {
        let utf16 = |b: &[u8], le: bool| {
            let units: Vec<u16> = b
                .chunks_exact(2)
                .map(|c| if le { u16::from_le_bytes([c[0], c[1]]) } else { u16::from_be_bytes([c[0], c[1]]) })
                .collect();
            String::from_utf16_lossy(&units)
        };
        if bytes.starts_with(&[0xFF, 0xFE]) {
            utf16(&bytes[2..], true)
        } else if bytes.starts_with(&[0xFE, 0xFF]) {
            utf16(&bytes[2..], false)
        } else {
            let b = bytes.strip_prefix(&[0xEF, 0xBB, 0xBF][..]).unwrap_or(bytes);
            String::from_utf8_lossy(b).into_owned()
        }
    }

    /// Parse CAM_INFO.XML text. Field names and fallbacks match the Python reference.
    pub fn parse_cam_info_str(content: &str, file_path: &str) -> Result<CamInfoReport, String> {
        let content = content.to_string();
        // Python as_int: ASCII digits only, otherwise None.
        let as_int = |v: Option<String>| -> Option<u32> {
            v.filter(|s| !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit()))
                .and_then(|s| s.parse::<u32>().ok())
        };
        let mut report = CamInfoReport {
            file_path: file_path.to_string(),
            ..Default::default()
        };

        let get_tag_value = |text: &str, tag: &str| -> Option<String> {
            let open = format!("<{tag}>");
            let close = format!("</{tag}>");
            if let Some(start) = text.find(&open) {
                let rest = &text[start + open.len()..];
                if let Some(end) = rest.find(&close) {
                    let val = rest[..end].trim();
                    if !val.is_empty() {
                        return Some(val.to_string());
                    }
                }
            }
            None
        };

        report.body_id = get_tag_value(&content, "BodyID")
            .or_else(|| get_tag_value(&content, "Serial"))
            .or_else(|| get_tag_value(&content, "BodyIDEx"));

        report.firmware = get_tag_value(&content, "Firmware")
            .or_else(|| get_tag_value(&content, "FirmwareVer"));

        report.total_shutter = as_int(get_tag_value(&content, "TotalShutter").or_else(|| get_tag_value(&content, "ShutterCount")));
        report.total_shoot = as_int(get_tag_value(&content, "TotalShoot").or_else(|| get_tag_value(&content, "ReleaseCount")));
        report.power_on_count = as_int(get_tag_value(&content, "PowerOnCount"));

        report.total_running_time = get_tag_value(&content, "TotalRunningTime");

        // Parse ErrorList. The code->meaning table is NOT grounded in a real CAM_INFO.XML
        // dump (copied from the Python reference), so meanings are shown only as hedged hints.
        let known_errors = [
            ("E01", "lens communication"),
            ("E02", "memory card communication"),
            ("E04", "buffer read/write"),
            ("E20", "mechanical (mirror/shutter drive)"),
            ("E30", "shutter unit timing"),
            ("E60", "aperture / auxiliary motor"),
            ("E70", "firmware / RAM"),
        ];
        // Only <Kind> entries inside <ErrorList>, like Python `.//ErrorList/Kind`.
        let error_block: String = match content.find("<ErrorList>") {
            Some(s0) => {
                let rest = &content[s0..];
                match rest.find("</ErrorList>") {
                    Some(e0) => rest[..e0].to_string(),
                    None => rest.to_string(),
                }
            }
            None => String::new(),
        };
        let content = error_block;

        let mut search_idx = 0;
        while let Some(kind_start) = content[search_idx..].find("<Kind>") {
            let start = search_idx + kind_start;
            let kind_block = if let Some(end) = content[start..].find("</Kind>") {
                &content[start..start + end + 7]
            } else {
                break;
            };

            let code = get_tag_value(kind_block, "ID");
            let count_str = get_tag_value(kind_block, "Count");
            let count = as_int(count_str);

            if let Some(cd) = code {
                let desc = known_errors
                    .iter()
                    .find(|(k, _)| *k == cd.as_str())
                    .map(|(_, desc)| format!("возможно: {desc} (значение не подтверждено)"))
                    .unwrap_or_else(|| "Сервисное событие (код не расшифрован)".to_string());

                report.errors.push(CamErrorItem {
                    code: cd,
                    count,
                    description: desc,
                });
            }

            search_idx = start + 6;
        }

        Ok(report)
    }
}

#[cfg(windows)]
mod win_raw {
    use std::ffi::c_void;

    pub type HANDLE = *mut c_void;
    pub const INVALID_HANDLE_VALUE: HANDLE = -1isize as HANDLE;

    pub const GENERIC_READ: u32 = 0x80000000;
    pub const GENERIC_WRITE: u32 = 0x40000000;
    pub const FILE_SHARE_READ: u32 = 0x00000001;
    pub const FILE_SHARE_WRITE: u32 = 0x00000002;
    pub const OPEN_EXISTING: u32 = 3;
    pub const FILE_BEGIN: u32 = 0;

    pub const FSCTL_LOCK_VOLUME: u32 = 0x00090018;
    pub const FSCTL_DISMOUNT_VOLUME: u32 = 0x00090020;
    pub const FSCTL_UNLOCK_VOLUME: u32 = 0x0009001C;

    extern "system" {
        pub fn CreateFileW(
            lpFileName: *const u16,
            dwDesiredAccess: u32,
            dwShareMode: u32,
            lpSecurityAttributes: *mut c_void,
            dwCreationDisposition: u32,
            dwFlagsAndAttributes: u32,
            hTemplateFile: HANDLE,
        ) -> HANDLE;

        pub fn DeviceIoControl(
            hDevice: HANDLE,
            dwIoControlCode: u32,
            lpInBuffer: *const c_void,
            nInBufferSize: u32,
            lpOutBuffer: *mut c_void,
            nOutBufferSize: u32,
            lpBytesReturned: *mut u32,
            lpOverlapped: *mut c_void,
        ) -> i32;

        pub fn ReadFile(
            hFile: HANDLE,
            lpBuffer: *mut c_void,
            nNumberOfBytesToRead: u32,
            lpNumberOfBytesRead: *mut u32,
            lpOverlapped: *mut c_void,
        ) -> i32;

        pub fn WriteFile(
            hFile: HANDLE,
            lpBuffer: *const c_void,
            nNumberOfBytesToWrite: u32,
            lpNumberOfBytesWritten: *mut u32,
            lpOverlapped: *mut c_void,
        ) -> i32;

        pub fn SetFilePointerEx(
            hFile: HANDLE,
            liDistanceToMove: i64,
            lpNewFilePointer: *mut i64,
            dwMoveMethod: u32,
        ) -> i32;

        pub fn CloseHandle(hObject: HANDLE) -> i32;

        pub fn GetLastError() -> u32;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_cam_info_xml_mock() {
        let xml_mock = r#"<?xml version="1.0" encoding="utf-8"?>
<CamInfo>
    <BodyID>243021001234</BodyID>
    <Firmware>1.3.0</Firmware>
    <TotalShutter>14250</TotalShutter>
    <TotalShoot>838541</TotalShoot>
    <PowerOnCount>1200</PowerOnCount>
    <TotalRunningTime>120:45:00</TotalRunningTime>
    <ErrorList>
        <Kind>
            <ID>E20</ID>
            <Count>2</Count>
        </Kind>
    </ErrorList>
</CamInfo>"#;

        let temp_dir = std::env::temp_dir();
        let test_file = temp_dir.join("test_cam_info.xml");
        std::fs::write(&test_file, xml_mock).unwrap();

        let res = BootflagManager::parse_cam_info_xml(&test_file).expect("Parsing failed");
        let _ = std::fs::remove_file(test_file);

        assert_eq!(res.body_id.as_deref(), Some("243021001234"));
        assert_eq!(res.firmware.as_deref(), Some("1.3.0"));
        assert_eq!(res.total_shutter, Some(14250));
        assert_eq!(res.total_shoot, Some(838541));
        assert_eq!(res.power_on_count, Some(1200));
        assert_eq!(res.errors.len(), 1);
        assert_eq!(res.errors[0].code, "E20");
        assert_eq!(res.errors[0].count, Some(2));
    }
}
