//! OpenEOS v1.0 — Public Community Edition (2 Tabs: RAW / EXIF & SD-Card Maker).
//!
//! Clean public edition for distribution (RAW metadata analysis & SD card preparation).

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod models;
mod raw;
mod card;
mod app;

use app::OpenEosApp;
use eframe::egui;

fn main() -> eframe::Result<()> {
    let _ = env_logger::try_init();

    let native_options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_title("OpenEOS Community Edition — RAW & SD Inspector")
            .with_inner_size([980.0, 700.0])
            .with_min_inner_size([980.0, 700.0])
            .with_max_inner_size([980.0, 700.0])
            .with_resizable(false)
            .with_maximize_button(false)
            .with_drag_and_drop(true)
            .with_active(true),
        ..Default::default()
    };

    eframe::run_native(
        "OpenEOS Public",
        native_options,
        Box::new(|cc| Ok(Box::new(OpenEosApp::new(cc)))),
    )
}
