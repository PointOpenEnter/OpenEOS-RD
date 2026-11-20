//! Интеграционные тесты OpenEOS (Rust).

use openeos::models::{find_by_name, find_by_pid, CameraType, DigicGeneration};

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
