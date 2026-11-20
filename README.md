# OpenEOS

A small native desktop tool (Rust, egui) that reads the shutter actuation / image count from photo files and prepares SD cards.

## Features

- **RAW / EXIF analysis** - reads the shutter count (image counter) and camera model from EXIF / maker-notes of Canon, Sony, Nikon and Fujifilm files, and shows it against the rated shutter life of the model.
- **SD card preparation** - formats a card to FAT32 and writes the Canon Basic script files.

Supported file types: `.NEF`, `.ARW`, `.CR2`, `.CR3`, `.RAF`, `.JPG` / `.JPEG`. Drag a file onto the window or pick it with the file dialog.

## Build and run

Requires a stable Rust toolchain (Windows).

```
cargo build --release
target\release\openeos.exe
```

A prebuilt binary is in `dist\openeos.exe`.

## License

MIT - see [LICENSE](LICENSE).
