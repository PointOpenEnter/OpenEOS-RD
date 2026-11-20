//! Интеграционные тесты OpenEOS (Rust).

use openeos::models::{find_by_name, find_by_pid, CameraType, DigicGeneration};
use openeos::card::BootflagManager;

#[test]
fn camera_database_lookup() {
    let r6m2 = find_by_pid("330B").expect("R6 Mark II must exist");
    assert_eq!(r6m2.short_tag, "R6m2");
    assert_eq!(r6m2.camera_type, CameraType::Mirrorless);
    assert_eq!(r6m2.generation, DigicGeneration::DigicX);
    assert!(r6m2.verified_for_live_counters);
    assert_eq!(r6m2.shutter_rating, 400_000);

    let dslr = find_by_name("Canon EOS 5D Mark IV").expect("5D4 must exist");
    assert_eq!(dslr.camera_type, CameraType::Dslr);
    assert!(!dslr.verified_for_live_counters);
}

#[test]
fn only_dump_verified_bodies_are_marked_live() {
    // Живое чтение подтверждено дампами только для R6 Mark II и R10.
    let live: Vec<&str> = openeos::models::CANON_REGISTRY
        .iter()
        .filter(|m| m.verified_for_live_counters)
        .map(|m| m.short_tag)
        .collect();
    assert_eq!(live, vec!["R6m2", "R10"]);
}

#[test]
fn deviceinfo_model_names_resolve() {
    // Так модель называется в метаданных
    assert_eq!(find_by_name("Canon EOS R6m2").unwrap().short_tag, "R6m2");
    assert_eq!(find_by_name("Canon EOS R10").unwrap().short_tag, "R10");
    assert!(find_by_name("Canon EOS R100").map(|m| m.short_tag) != Some("R10"));
}


#[test]
fn nikon_z9_exact_word_lookup() {
    // "RP" внутри "CORPORATION" не должно находить Canon RP
    let z9 = find_by_name("NIKON CORPORATION NIKON Z 9").expect("Z9 must match exact model");
    assert_eq!(z9.name, "NIKON Z 9");
    assert!(!z9.has_mechanical_shutter);
}

#[test]
fn sony_and_fuji_lookup() {
    assert_eq!(find_by_name("ILCE-7M4").unwrap().name, "SONY ILCE-7M4");
    assert_eq!(find_by_name("FUJIFILM X100V").unwrap().shutter_rating, 100_000);
}

#[test]
fn real_raw_files_if_present() {
    // ВНИМАНИЕ: без OPENEOS_RAW_DIR этот тест ничего не проверяет (не считать его подтверждением).
    use openeos::raw::analyze_file;
    // Каталог с эталонными RAW можно задать переменной окружения OPENEOS_RAW_DIR.
    let Ok(dir) = std::env::var("OPENEOS_RAW_DIR") else { return };
    let nef_file = std::path::Path::new(&dir).join("NZ9_2714.nef");
    if nef_file.exists() {
        let res = analyze_file(&nef_file).expect("NEF parsing must succeed");
        assert_eq!(res.camera_model.as_deref(), Some("NIKON Z 9"));
        assert_eq!(res.shutter_count, Some(530_627));
        assert_eq!(res.wear_percentage, None);
        assert!(!res.has_mechanical_shutter);
    }
}

#[test]
fn prepare_card_fails_when_boot_marker_fails() {
    let dir = std::env::temp_dir().join("openeos_test_prepare_fail");
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    let r = BootflagManager::prepare_card_steps(
        &dir,
        false,
        || Ok(String::new()),
        || Err("нет прав администратора".to_string()),
    );
    let e = r.unwrap_err();
    assert!(e.contains("НЕ загрузочная"));
    assert!(!dir.join("extend.m").exists(), "скрипты не должны писаться после провала маркера");

    let ok = BootflagManager::prepare_card_steps(&dir, false, || Ok(String::new()), || Ok("маркер".into()));
    assert!(ok.is_ok());
    assert_eq!(std::fs::read(dir.join("script.req")).unwrap(), b"for DC_scriptdisk\n");
    assert!(std::fs::read_to_string(dir.join("extend.m")).unwrap().contains("CamInfo_Debug(1)"));
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn write_scripts_to_missing_root_fails() {
    let p = std::env::temp_dir().join("openeos_definitely_missing_dir_xyz");
    assert!(BootflagManager::write_canon_basic_scripts(&p).is_err());
}

#[test]
fn cam_info_xml_parses_like_python_reference() {
    let xml = r#"<?xml version="1.0" encoding="utf-8"?>
<CamInfo>
  <BodyID>243021001234</BodyID>
  <Firmware>1.3.0</Firmware>
  <TotalShutter>14250</TotalShutter>
  <TotalShoot>838541</TotalShoot>
  <ErrorList>
    <Kind><ID>E20</ID><Count>2</Count></Kind>
    <Kind><ID>E99</ID><Count>abc</Count></Kind>
    <Kind><ID>E01</ID></Kind>
  </ErrorList>
</CamInfo>"#;
    let r = BootflagManager::parse_cam_info_str(xml, "x").unwrap();
    assert_eq!(r.body_id.as_deref(), Some("243021001234"));
    assert_eq!(r.firmware.as_deref(), Some("1.3.0"));
    assert_eq!(r.total_shutter, Some(14250));
    assert_eq!(r.total_shoot, Some(838541));
    assert_eq!(r.errors.len(), 3);
    assert_eq!(r.errors[0].count, Some(2));
    assert_eq!(r.errors[1].count, None);
    assert_eq!(r.errors[2].count, None);
    assert!(r.errors[1].description.contains("не расшифрован"));

    let xml2 = "<CamInfo><ShutterCount>100</ShutterCount><ReleaseCount>250</ReleaseCount></CamInfo>";
    let r2 = BootflagManager::parse_cam_info_str(xml2, "x").unwrap();
    assert_eq!(r2.total_shutter, Some(100));
    assert_eq!(r2.total_shoot, Some(250));
    let xml3 = "<CamInfo><TotalShutter>x1</TotalShutter><ShutterCount>5</ShutterCount></CamInfo>";
    assert_eq!(BootflagManager::parse_cam_info_str(xml3, "x").unwrap().total_shutter, None);
}
