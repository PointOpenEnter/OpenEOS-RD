//! SD Card and Bootloader management module.

pub mod detector;
pub mod bootflag;

pub use detector::{CardDetector, SdCardVolume};
pub use bootflag::{BootflagManager, CamInfoReport, CamErrorItem};
