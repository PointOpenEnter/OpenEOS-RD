//! OpenEOS Modern Native Application State & UI.

use eframe::egui;
use std::path::PathBuf;
use std::time::Instant;
use crossbeam_channel::{unbounded, Receiver, Sender};
use crate::raw::{analyze_file, generate_raw_report_text, RawAnalysisResult};
use crate::card::{CardDetector, SdCardVolume, BootflagManager, CamInfoReport};

#[derive(PartialEq, Eq, Clone, Copy)]
enum ActiveTab {
    RawInspection,
    SdCardMaker,
}

pub struct OpenEosApp {
    active_tab: ActiveTab,
    raw_result: Option<RawAnalysisResult>,
    raw_error: Option<String>,
    is_loading_raw: bool,

    // Background thread channels for zero UI freeze
    raw_sender: Sender<Result<RawAnalysisResult, String>>,
    raw_receiver: Receiver<Result<RawAnalysisResult, String>>,

    // SD Card State & async background scanner
    sd_volumes: Vec<SdCardVolume>,
    selected_sd_idx: Option<usize>,
    sd_status: String,
    is_scanning_sd: bool,
    sd_sender: Sender<Vec<SdCardVolume>>,
    sd_receiver: Receiver<Vec<SdCardVolume>>,
    cam_info_report: Option<CamInfoReport>,
    /// Диск, для которого показан диалог подтверждения форматирования
    confirm_format_drive: Option<char>,
    is_preparing_sd: bool,
    sd_prep_sender: Sender<Result<String, String>>,
    sd_prep_receiver: Receiver<Result<String, String>>,

    // Feedback timers for copy buttons
    raw_copied_time: Option<Instant>,

    // Error details modal state
    show_error_details: bool,
}

impl Default for OpenEosApp {
    fn default() -> Self {
        let (raw_tx, raw_rx) = unbounded();
        let (sd_tx, sd_rx) = unbounded();
        let (prep_tx, prep_rx) = unbounded();

        let mut app = Self {
            active_tab: ActiveTab::RawInspection,
            raw_result: None,
            raw_error: None,
            is_loading_raw: false,
            raw_sender: raw_tx,
            raw_receiver: raw_rx,

            sd_volumes: Vec::new(),
            selected_sd_idx: None,
            sd_status: "Нажмите «Обновить список дисков» для поиска SD-карт".to_string(),
            is_scanning_sd: false,
            sd_sender: sd_tx,
            sd_receiver: sd_rx,
            cam_info_report: None,
            confirm_format_drive: None,
            is_preparing_sd: false,
            sd_prep_sender: prep_tx,
            sd_prep_receiver: prep_rx,

            raw_copied_time: None,

            show_error_details: false,
        };

        // Start non-blocking initial scan of SD cards in the background
        app.start_sd_scan();
        app
    }
}

impl OpenEosApp {
    pub fn new(cc: &eframe::CreationContext<'_>) -> Self {
        let mut visuals = egui::Visuals::dark();
        // Tangible, tactile buttons with clear borders and contrasting backgrounds
        visuals.widgets.inactive.bg_fill = egui::Color32::from_rgb(34, 40, 52);
        visuals.widgets.inactive.bg_stroke = egui::Stroke::new(1.0f32, egui::Color32::from_rgb(65, 80, 105));
        visuals.widgets.hovered.bg_fill = egui::Color32::from_rgb(46, 56, 75);
        visuals.widgets.hovered.bg_stroke = egui::Stroke::new(1.0f32, egui::Color32::from_rgb(0, 160, 255));
        visuals.widgets.active.bg_fill = egui::Color32::from_rgb(0, 100, 180);
        visuals.widgets.active.bg_stroke = egui::Stroke::new(1.0f32, egui::Color32::from_rgb(0, 200, 255));
        cc.egui_ctx.set_visuals(visuals);

        // Exact 1.0 native scaling to fit comfortably into fixed 980x700 window
        cc.egui_ctx.set_pixels_per_point(1.0);

        let mut style = (*cc.egui_ctx.style()).clone();
        style.text_styles.insert(egui::TextStyle::Heading, egui::FontId::proportional(16.0));
        style.text_styles.insert(egui::TextStyle::Body, egui::FontId::proportional(13.0));
        style.text_styles.insert(egui::TextStyle::Button, egui::FontId::proportional(12.5));
        style.text_styles.insert(egui::TextStyle::Small, egui::FontId::proportional(11.0));
        style.text_styles.insert(egui::TextStyle::Monospace, egui::FontId::monospace(12.0));
        style.spacing.button_padding = egui::vec2(10.0, 5.0);
        style.spacing.item_spacing = egui::vec2(6.0, 6.0);
        cc.egui_ctx.set_style(style);

        Self::default()
    }

    fn start_analysis(&mut self, path: PathBuf) {
        self.is_loading_raw = true;
        self.raw_error = None;
        let tx = self.raw_sender.clone();
        std::thread::spawn(move || {
            let res = analyze_file(&path);
            let _ = tx.send(res);
        });
    }

    fn start_sd_scan(&mut self) {
        if self.is_scanning_sd {
            return;
        }
        self.is_scanning_sd = true;
        self.sd_status = "Поиск подключенных накопителей Windows...".to_string();
        let tx = self.sd_sender.clone();
        std::thread::spawn(move || {
            let vols = CardDetector::scan_removable_drives();
            let _ = tx.send(vols);
        });
    }

    /// Подготовка SD-карты в фоне: format.com и запись сектора занимают секунды и не должны
    /// замораживать окно.
    fn start_sd_prep(&mut self, drive_letter: char, format_first: bool) {
        if self.is_preparing_sd {
            return;
        }
        self.is_preparing_sd = true;
        self.sd_status = if format_first {
            format!("Форматирование {drive_letter}: и запись служебных файлов...")
        } else {
            format!("Запись SCRIPT и скриптов на {drive_letter}:...")
        };
        let tx = self.sd_prep_sender.clone();
        std::thread::spawn(move || {
            let _ = tx.send(BootflagManager::prepare_full_card(drive_letter, format_first));
        });
    }

    fn render_header(&mut self, ui: &mut egui::Ui) {
        egui::Frame::none()
            .fill(egui::Color32::from_rgb(26, 30, 38))
            .inner_margin(egui::Margin::symmetric(14.0, 10.0))
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new("OpenEOS")
                            .strong()
                            .size(19.0)
                            .color(egui::Color32::from_rgb(0, 180, 255)),
                    );

                    ui.label(
                        egui::RichText::new("v1.0.2")
                            .size(11.0)
                            .strong()
                            .color(egui::Color32::from_rgb(0, 170, 255)),
                    );
                });

                ui.add_space(8.0);

                ui.horizontal(|ui| {
                    let render_tab_btn = |ui: &mut egui::Ui, is_active: bool, title: &str| -> bool {
                        let fill = if is_active {
                            egui::Color32::from_rgb(0, 110, 190)
                        } else {
                            egui::Color32::from_rgb(34, 40, 52)
                        };
                        let stroke = if is_active {
                            egui::Stroke::new(1.0f32, egui::Color32::from_rgb(0, 200, 255))
                        } else {
                            egui::Stroke::new(1.0f32, egui::Color32::from_rgb(60, 75, 95))
                        };
                        let text_color = if is_active {
                            egui::Color32::WHITE
                        } else {
                            egui::Color32::from_rgb(200, 215, 230)
                        };

                        let btn = egui::Button::new(egui::RichText::new(title).color(text_color).strong())
                            .fill(fill)
                            .stroke(stroke)
                            .rounding(egui::Rounding::same(4.0));
                        ui.add(btn).clicked()
                    };

                    if render_tab_btn(ui, self.active_tab == ActiveTab::RawInspection, "RAW / EXIF Анализ") {
                        self.active_tab = ActiveTab::RawInspection;
                    }

                    if render_tab_btn(ui, self.active_tab == ActiveTab::SdCardMaker, "Подготовка SD-карт") {
                        self.active_tab = ActiveTab::SdCardMaker;
                    }
                });
            });

        ui.add_space(8.0);
    }

    fn render_raw_tab(&mut self, ui: &mut egui::Ui) {
        let raw_opt = self.raw_result.clone();
        let mut save_path_and_content: Option<(PathBuf, String)> = None;

        egui::ScrollArea::vertical().auto_shrink([false, false]).show(ui, |ui| {
            ui.add_space(4.0);

            // Native Drag-and-Drop Zone
            let drop_frame = egui::Frame::group(ui.style())
                .fill(egui::Color32::from_rgb(26, 31, 40))
                .stroke(egui::Stroke::new(1.0f32, egui::Color32::from_rgb(0, 140, 255)))
                .rounding(egui::Rounding::same(6.0))
                .inner_margin(egui::Margin::symmetric(14.0, 10.0));

            drop_frame.show(ui, |ui| {
                ui.vertical_centered(|ui| {
                    ui.label(
                        egui::RichText::new("Перетащите RAW-файл сюда (.NEF, .ARW, .CR2, .CR3, .RAF, .JPG)")
                            .size(14.0)
                            .strong(),
                    );
                    ui.label(egui::RichText::new("Или нажмите кнопку для выбора через Проводник").small().color(egui::Color32::GRAY));
                    ui.add_space(4.0);

                    if ui.button(egui::RichText::new("Выбрать файл на диске…").size(12.5)).clicked() {
                        if let Some(path) = rfd::FileDialog::new()
                            .add_filter("RAW & Image Files", &["nef", "arw", "cr2", "cr3", "raf", "jpg", "jpeg"])
                            .add_filter("All Files", &["*"])
                            .pick_file()
                        {
                            self.start_analysis(path);
                        }
                    }
                });
            });

            ui.add_space(6.0);

            if self.is_loading_raw {
                ui.horizontal(|ui| {
                    ui.spinner();
                    ui.label(egui::RichText::new("Выполняется мгновенный анализ RAW…").color(egui::Color32::LIGHT_BLUE));
                });
                ui.add_space(4.0);
            }

            if let Some(ref err) = self.raw_error {
                ui.colored_label(egui::Color32::LIGHT_RED, format!("Ошибка: {err}"));
            }

            if let Some(ref res) = raw_opt {
                egui::Frame::group(ui.style())
                    .fill(egui::Color32::from_rgb(26, 29, 36))
                    .stroke(egui::Stroke::new(1.0f32, egui::Color32::from_rgb(0, 180, 255)))
                    .rounding(egui::Rounding::same(6.0))
                    .inner_margin(egui::Margin::same(14.0))
                    .show(ui, |ui| {
                        // Header
                        let cam_title = res.camera_model.as_deref().unwrap_or("Неизвестная модель камеры");
                        ui.horizontal(|ui| {
                            ui.heading(egui::RichText::new(cam_title).size(17.0).color(egui::Color32::GOLD));
                            ui.add_space(8.0);
                            ui.label(egui::RichText::new(format!("{} • {:.2} МБ", res.format, res.file_size_bytes as f64 / 1_048_576.0)).small().color(egui::Color32::GRAY));
                        });

                        ui.add_space(8.0);

                        // Unified, High-Contrast Parameter Table
                        egui::Grid::new("raw_meta_unified_grid")
                            .striped(true)
                            .num_columns(2)
                            .spacing([16.0, 7.0])
                            .min_col_width(170.0)
                            .max_col_width(ui.available_width() - 210.0)
                            .show(ui, |ui| {
                                ui.label(egui::RichText::new("Имя файла:").color(egui::Color32::from_rgb(170, 185, 205)));
                                ui.add(egui::Label::new(egui::RichText::new(&res.file_name).strong()).wrap().selectable(true));
                                ui.end_row();

                                ui.label(egui::RichText::new("Модель камеры:").color(egui::Color32::from_rgb(170, 185, 205)));
                                ui.add(egui::Label::new(egui::RichText::new(cam_title).color(egui::Color32::GOLD).strong().size(15.0)).wrap().selectable(true));
                                ui.end_row();

                                ui.label(egui::RichText::new("Серийный номер:").color(egui::Color32::from_rgb(170, 185, 205)));
                                let sn = res.serial_number.as_deref().unwrap_or("—");
                                ui.add(egui::Label::new(egui::RichText::new(sn).strong().color(egui::Color32::from_rgb(0, 210, 255))).wrap().selectable(true));
                                ui.end_row();

                                ui.label(egui::RichText::new("Пробег затвора:").color(egui::Color32::from_rgb(170, 185, 205)));
                                if let Some(cnt) = res.shutter_count {
                                    let (txt, color) = if res.is_combined_shutter {
                                        (format!("{cnt} кадров (суммарно: электро + мех)"), egui::Color32::GREEN)
                                    } else if !res.has_mechanical_shutter {
                                        (format!("{cnt} кадров (электронный спуск, износ 0%)"), egui::Color32::from_rgb(0, 210, 255))
                                    } else {
                                        (format!("{cnt} кадров (чистая механика)"), egui::Color32::GREEN)
                                    };
                                    ui.add(egui::Label::new(egui::RichText::new(txt).size(16.0).strong().color(color)).wrap().selectable(true));
                                } else {
                                    ui.add(egui::Label::new("— (тег пробега отсутствует в метаданных)").selectable(true));
                                }
                                ui.end_row();

                                if res.has_mechanical_shutter {
                                    if let Some(r) = res.shutter_rating {
                                        ui.label(egui::RichText::new("Паспортный ресурс:").color(egui::Color32::from_rgb(170, 185, 205)));
                                        ui.add(egui::Label::new(format!("{r} срабатываний")).selectable(true));
                                        ui.end_row();
                                    }

                                    if let Some(w) = res.wear_percentage {
                                        ui.label(egui::RichText::new("Износ механизма:").color(egui::Color32::from_rgb(170, 185, 205)));
                                        ui.horizontal_wrapped(|ui| {
                                            let ratio = (w / 100.0).clamp(0.0, 1.0);
                                            ui.add(
                                                egui::ProgressBar::new(ratio)
                                                    .desired_width(120.0)
                                                    .text(format!("{w:.1}%"))
                                            );
                                            let wear_status = if w > 90.0 {
                                                egui::RichText::new("[Критический износ]").color(egui::Color32::RED).strong()
                                            } else if w > 70.0 {
                                                egui::RichText::new("[Повышенный износ]").color(egui::Color32::KHAKI)
                                            } else {
                                                egui::RichText::new("[Отличное состояние]").color(egui::Color32::GREEN)
                                            };
                                            ui.label(wear_status);
                                        });
                                        ui.end_row();
                                    }
                                }

                                if let Some(ref dt) = res.date_time {
                                    ui.label(egui::RichText::new("Дата и время съемки:").color(egui::Color32::from_rgb(170, 185, 205)));
                                    ui.add(egui::Label::new(dt).selectable(true));
                                    ui.end_row();
                                }

                                if let Some(ref lens) = res.lens_model {
                                    ui.label(egui::RichText::new("Объектив:").color(egui::Color32::from_rgb(170, 185, 205)));
                                    ui.add(egui::Label::new(lens).selectable(true));
                                    ui.end_row();
                                }

                                let mut exp_parts = Vec::new();
                                if let Some(iso) = res.iso { exp_parts.push(format!("ISO {iso}")); }
                                if let Some(ref exp) = res.exposure_time { exp_parts.push(exp.clone()); }
                                if let Some(f) = res.f_number { exp_parts.push(format!("f/{f:.1}")); }
                                if let Some(fl) = res.focal_length { exp_parts.push(format!("{fl:.1} мм")); }

                                if !exp_parts.is_empty() {
                                    ui.label(egui::RichText::new("Параметры экспозиции:").color(egui::Color32::from_rgb(170, 185, 205)));
                                    ui.add(egui::Label::new(exp_parts.join("  •  ")).selectable(true));
                                    ui.end_row();
                                }

                                if !res.notes.is_empty() {
                                    ui.label(egui::RichText::new("Примечания:").color(egui::Color32::from_rgb(170, 185, 205)));
                                    ui.vertical(|ui| {
                                        for n in &res.notes {
                                            ui.add(egui::Label::new(egui::RichText::new(format!("• {n}")).color(egui::Color32::from_rgb(220, 220, 170))).wrap());
                                        }
                                    });
                                    ui.end_row();
                                }
                            });

                        ui.add_space(8.0);
                        ui.separator();
                        ui.add_space(6.0);

                        // Section 2: Canon EOS Monospace Text Report for copying
                        ui.horizontal(|ui| {
                            ui.label(egui::RichText::new("Текстовый отчёт анализа (для копирования):").strong().color(egui::Color32::from_rgb(0, 210, 255)));
                            ui.label(egui::RichText::new("(выделите нужный фрагмент курсором)").small().color(egui::Color32::GRAY));
                        });
                        ui.add_space(4.0);

                        let report_text = generate_raw_report_text(res);
                        let mut display_text = report_text.clone();

                        ui.add(
                            egui::TextEdit::multiline(&mut display_text)
                                .font(egui::TextStyle::Monospace)
                                .desired_width(ui.available_width() - 8.0)
                                .desired_rows(8)
                                .lock_focus(false),
                        );

                        ui.add_space(6.0);
                        ui.horizontal(|ui| {
                            ui.label(egui::RichText::new("Действия:").strong());
                            ui.add_space(6.0);

                            let is_copied = self.raw_copied_time.map_or(false, |t| t.elapsed().as_secs_f32() < 2.5f32);
                            let copy_btn_text = if is_copied {
                                egui::RichText::new("Скопировано!").color(egui::Color32::from_rgb(80, 240, 140)).strong()
                            } else {
                                egui::RichText::new("Скопировать весь отчёт в буфер").strong()
                            };

                            if ui.button(copy_btn_text).clicked() {
                                ui.output_mut(|o| o.copied_text = report_text.clone());
                                self.raw_copied_time = Some(Instant::now());
                            }

                            ui.add_space(6.0);
                            if ui.button(egui::RichText::new("Сохранить отчёт в .txt").strong()).clicked() {
                                if let Some(path) = rfd::FileDialog::new()
                                    .set_file_name("OpenEOS_RAW_Report.txt")
                                    .add_filter("Text Document", &["txt"])
                                    .save_file()
                                {
                                    save_path_and_content = Some((path, report_text));
                                }
                            }
                        });
                    });
            }
            ui.add_space(10.0);
        });

        if let Some((path, content)) = save_path_and_content {
            let _ = std::fs::write(path, content);
        }
    }

    fn render_sd_tab(&mut self, ui: &mut egui::Ui) {
        let volumes = self.sd_volumes.clone();
        let selected_idx = self.selected_sd_idx;
        let mut new_selected_idx = None;
        let mut pending_prep: Option<(char, bool)> = None;
        let mut pending_parse_cam_info: Option<char> = None;

        egui::ScrollArea::vertical().show(ui, |ui| {
            ui.add_space(6.0);
            ui.horizontal(|ui| {
                if ui.button(egui::RichText::new("Обновить список дисков").strong()).clicked() {
                    self.start_sd_scan();
                }

                if self.is_scanning_sd {
                    ui.spinner();
                }
                ui.label(&self.sd_status);
            });

            ui.add_space(4.0);
            ui.label(
                egui::RichText::new("Совместимость: скрипты Canon Basic с SD-карты запускаются на камерах DIGIC 4 / 5 / 6 / 7 / 8, ранних БЗК (EOS R, RP, M50) и на оригинальном EOS R6 (проверено). На R6 Mark II, R8, R10, R3 и других DIGIC X последних поколений запуск пользовательских скриптов заблокирован производителем.")
                    .color(egui::Color32::from_rgb(160, 180, 200))
                    .small(),
            );

            ui.add_space(8.0);

            if volumes.is_empty() && !self.is_scanning_sd {
                egui::Frame::group(ui.style())
                    .fill(egui::Color32::from_rgb(26, 29, 36))
                    .rounding(egui::Rounding::same(6.0))
                    .inner_margin(egui::Margin::same(16.0))
                    .show(ui, |ui| {
                        ui.label("Съемные SD-карты не найдены.");
                        ui.label("Вставьте карту памяти в кардридер и нажмите [ Обновить список дисков ].");
                    });
            } else {
                // If multiple volumes, allow selecting via ComboBox without confusing wide buttons
                if volumes.len() > 1 {
                    ui.horizontal(|ui| {
                        ui.label(egui::RichText::new("Выбор карты:").strong());
                        let current_label = selected_idx.and_then(|i| volumes.get(i)).map(|v| format!("[{}:] {}", v.drive_letter, v.volume_name)).unwrap_or_else(|| "Выберите".to_string());
                        egui::ComboBox::from_id_salt("sd_volume_combo")
                            .selected_text(current_label)
                            .show_ui(ui, |ui| {
                                for (idx, vol) in volumes.iter().enumerate() {
                                    let label = format!("[{}:] {} ({})", vol.drive_letter, vol.volume_name, vol.file_system);
                                    if ui.selectable_value(&mut new_selected_idx, Some(idx), label).clicked() {
                                        // selected
                                    }
                                }
                            });
                    });
                    ui.add_space(6.0);
                }

                if let Some(idx) = selected_idx {
                    if let Some(vol) = volumes.get(idx) {
                        let drive_letter = vol.drive_letter;
                        egui::Frame::group(ui.style())
                            .fill(egui::Color32::from_rgb(26, 29, 36))
                            .rounding(egui::Rounding::same(6.0))
                            .inner_margin(egui::Margin::same(14.0))
                            .show(ui, |ui| {
                                ui.horizontal(|ui| {
                                    ui.label(egui::RichText::new(format!("Накопитель: {}:\\", drive_letter)).strong().size(15.0));
                                    ui.label(format!("Файловая система: {}", vol.file_system));
                                    ui.label(format!("(Свободно: {:.1} ГБ из {:.1} ГБ)", vol.free_bytes as f64 / 1_073_741_824.0, vol.total_bytes as f64 / 1_073_741_824.0));
                                });

                                let is_fat = vol.file_system.to_uppercase().contains("FAT");
                                if !is_fat {
                                    ui.add_space(4.0);
                                    ui.label(
                                        egui::RichText::new("Внимание: Карта отформатирована не в FAT32. Сервисный режим Canon Basic требует файловую систему FAT/FAT32. Используйте кнопку «Полная подготовка» ниже.")
                                            .color(egui::Color32::from_rgb(255, 180, 60))
                                            .small(),
                                    );
                                }

                                ui.add_space(8.0);
                                ui.horizontal(|ui| {
                                    ui.add_enabled_ui(!self.is_preparing_sd, |ui| {
                                        if ui.button(egui::RichText::new("Полная подготовка (FAT32 + SCRIPT)").strong()).clicked() {
                                            // Форматирование удаляет все данные: только после подтверждения
                                            self.confirm_format_drive = Some(drive_letter);
                                        }

                                        if ui.button(egui::RichText::new("Записать SCRIPT и скрипты")).clicked() {
                                            pending_prep = Some((drive_letter, false));
                                        }
                                    });
                                    if self.is_preparing_sd {
                                        ui.spinner();
                                    }
                                });

                                ui.add_space(6.0);
                                ui.label(egui::RichText::new(&self.sd_status).color(egui::Color32::GREEN));

                                // CAM_INFO.XML Detector
                                if vol.has_cam_info {
                                    ui.add_space(10.0);
                                    egui::Frame::none()
                                        .fill(egui::Color32::from_rgb(20, 38, 30))
                                        .rounding(egui::Rounding::same(4.0))
                                        .inner_margin(egui::Margin::same(10.0))
                                        .show(ui, |ui| {
                                            ui.horizontal(|ui| {
                                                ui.label(egui::RichText::new("На карте обнаружен сервисный отчет CAM_INFO.XML с камеры!").color(egui::Color32::from_rgb(80, 240, 140)).strong());
                                                if ui.button(egui::RichText::new("Разобрать отчет CAM_INFO.XML").strong()).clicked() {
                                                    pending_parse_cam_info = Some(drive_letter);
                                                }
                                            });
                                        });
                                }
                            });

                        // Render parsed CAM_INFO.XML report if available
                        if let Some(ref report) = self.cam_info_report {
                            ui.add_space(10.0);
                            egui::Frame::group(ui.style())
                                .fill(egui::Color32::from_rgb(22, 26, 34))
                                .rounding(egui::Rounding::same(6.0))
                                .inner_margin(egui::Margin::same(14.0))
                                .show(ui, |ui| {
                                    ui.heading("Заводской сервисный отчет Canon (CAM_INFO.XML)");
                                    ui.add_space(6.0);

                                    egui::Grid::new("cam_info_grid")
                                        .num_columns(2)
                                        .spacing([20.0, 6.0])
                                        .show(ui, |ui| {
                                            ui.label("Серийный номер камеры:");
                                            ui.label(report.body_id.as_deref().unwrap_or("—"));
                                            ui.end_row();

                                            ui.label("Версия прошивки:");
                                            ui.label(report.firmware.as_deref().unwrap_or("—"));
                                            ui.end_row();

                                            ui.label("Механический затвор (TotalShutter):");
                                            if let Some(shutter) = report.total_shutter {
                                                ui.label(egui::RichText::new(format!("{shutter} срабатываний шторок (чистая механика)")).strong().color(egui::Color32::GREEN));
                                            } else {
                                                ui.label("—");
                                            }
                                            ui.end_row();

                                            ui.label("Общий счетчик кадров (TotalShoot):");
                                            if let Some(shoot) = report.total_shoot {
                                                ui.label(egui::RichText::new(format!("{shoot} спусков (электро + мех)")).color(egui::Color32::from_rgb(0, 210, 255)));
                                            } else {
                                                ui.label("—");
                                            }
                                            ui.end_row();

                                            ui.label("Количество включений (PowerOnCount):");
                                            if let Some(pwr) = report.power_on_count {
                                                ui.label(format!("{pwr} раз"));
                                            } else {
                                                ui.label("—");
                                            }
                                            ui.end_row();

                                            if let Some(ref run_time) = report.total_running_time {
                                                ui.label("Общее время работы:");
                                                ui.label(run_time);
                                                ui.end_row();
                                            }
                                        });

                                    ui.add_space(8.0);
                                    ui.label(egui::RichText::new("Журнал ошибок камеры (ErrorList):").strong());
                                    if report.errors.is_empty() {
                                        ui.label(egui::RichText::new("Аппаратных ошибок не зафиксировано (камера полностью исправна)").color(egui::Color32::GREEN));
                                    } else {
                                        for err in &report.errors {
                                            ui.label(format!("• Ошибка {}: {} (кол-во: {})", err.code, err.description, err.count));
                                        }
                                    }
                                });
                        }
                    }
                }
            }
            ui.add_space(10.0);
        });

        if let Some(idx) = new_selected_idx {
            self.selected_sd_idx = Some(idx);
        }
        if let Some((dl, full)) = pending_prep {
            self.start_sd_prep(dl, full);
        }
        if let Some(dl) = pending_parse_cam_info {
            self.cam_info_report = BootflagManager::find_and_parse_cam_info(dl);
        }
    }
}

impl eframe::App for OpenEosApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        // Poll background RAW analysis channel
        if let Ok(res) = self.raw_receiver.try_recv() {
            self.is_loading_raw = false;
            match res {
                Ok(data) => {
                    self.raw_result = Some(data);
                    self.raw_error = None;
                }
                Err(e) => {
                    self.raw_error = Some(e);
                }
            }
        }

        // Poll background SD card scanner channel
        if let Ok(vols) = self.sd_receiver.try_recv() {
            self.is_scanning_sd = false;
            self.sd_volumes = vols;
            self.sd_status = format!("Обнаружено накопителей: {}", self.sd_volumes.len());
            if self.selected_sd_idx.is_none() && !self.sd_volumes.is_empty() {
                self.selected_sd_idx = Some(0);
            } else if let Some(idx) = self.selected_sd_idx {
                if idx >= self.sd_volumes.len() {
                    self.selected_sd_idx = if self.sd_volumes.is_empty() { None } else { Some(0) };
                }
            }
        }

        // Poll background SD preparation channel
        if let Ok(res) = self.sd_prep_receiver.try_recv() {
            self.is_preparing_sd = false;
            self.sd_status = match res {
                Ok(msg) => format!("Успешно:\n{msg}"),
                Err(e) => format!("Ошибка: {e}"),
            };
            self.start_sd_scan();
        }

        // Handle native Windows Shell drag-and-drop
        ctx.input(|i| {
            if !i.raw.dropped_files.is_empty() {
                for file in &i.raw.dropped_files {
                    if let Some(ref path) = file.path {
                        self.start_analysis(path.clone());
                        self.active_tab = ActiveTab::RawInspection;
                    }
                }
            }
        });

        if let Some(dl) = self.confirm_format_drive {
            let mut decision: Option<bool> = None;
            egui::Window::new("Подтверждение форматирования")
                .collapsible(false)
                .resizable(false)
                .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
                .show(ctx, |ui| {
                    ui.label(egui::RichText::new(format!("Диск {dl}: будет отформатирован в FAT32.")).strong());
                    ui.label("Все файлы на этой карте будут удалены без возможности восстановления.");
                    ui.add_space(8.0);
                    ui.horizontal(|ui| {
                        if ui.button(egui::RichText::new(format!("Форматировать {dl}:")).color(egui::Color32::from_rgb(255, 130, 130))).clicked() {
                            decision = Some(true);
                        }
                        if ui.button("Отмена").clicked() {
                            decision = Some(false);
                        }
                    });
                });
            match decision {
                Some(true) => {
                    self.confirm_format_drive = None;
                    self.start_sd_prep(dl, true);
                }
                Some(false) => self.confirm_format_drive = None,
                None => {}
            }
        }

        egui::CentralPanel::default().show(ctx, |ui| {
            self.render_header(ui);

            match self.active_tab {
                ActiveTab::RawInspection => self.render_raw_tab(ui),
                ActiveTab::SdCardMaker => self.render_sd_tab(ui),
            }
        });

        // egui перерисовывает окно только по событиям ввода. Пока идут фоновые задачи или
        // показывается «Скопировано!», просим перерисовку сами, иначе результат и сброс
        // надписи появятся только после движения мыши.
        let busy = self.is_loading_raw || self.is_scanning_sd || self.is_preparing_sd;
        if busy {
            ctx.request_repaint_after(std::time::Duration::from_millis(100));
        }
        for t in [self.raw_copied_time].into_iter().flatten() {
            let left = 2.5f32 - t.elapsed().as_secs_f32();
            if left > 0.0 {
                ctx.request_repaint_after(std::time::Duration::from_secs_f32(left + 0.05));
            }
        }
    }
}
