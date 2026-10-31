OpenEOS - local Windows x64 one-file build

WHAT THIS DOES
- Builds one OpenEOS.exe for Windows x64.
- Bundles Python/Tkinter through PyInstaller.
- Bundles TkinterDnD2 and its TkDnD support files.
- Bundles C:\Tools\ExifTool\exiftool.exe and its exiftool_files folder.
- Does not modify the original openeos.py.

REQUIREMENTS ALREADY ESTABLISHED IN THIS PROJECT
- C:\Users\<your-user>\OpenEOS\openeos.py
- C:\Users\<your-user>\OpenEOS\build-env\Scripts\python.exe
- PyInstaller installed in build-env
- tkinterdnd2 installed in build-env
- C:\Tools\ExifTool\exiftool.exe
- C:\Tools\ExifTool\exiftool_files\

HOW TO USE
1. Extract BUILD_OpenEOS.bat, prepare_for_build.py and README.txt into:
   %USERPROFILE%\OpenEOS\
2. Make sure the existing openeos.py is still in that folder.
3. Double-click BUILD_OpenEOS.bat.
4. When it finishes successfully, the single distributable is:
   %USERPROFILE%\OpenEOS\dist\OpenEOS.exe

The helper creates openeos_portable.py as a build copy. Your original
openeos.py is not changed.

IMPORTANT
- Build is for Windows x64. Do not try to build this Windows EXE on Linux.
- The one-file EXE temporarily extracts its embedded runtime and bundled
  ExifTool resources into a PyInstaller temporary directory when launched.
  This is automatic and does not require user installation.
- The build output must be tested on the current PC and then on a clean
  Windows 10/11 x64 computer without Python or ExifTool before distribution.
- SmartScreen/antivirus reputation warnings may still appear for an unsigned
  EXE. No universal guarantee can be made for every PC/security configuration.
