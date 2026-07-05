# Building the Windows installer

This installer wraps the existing PyInstaller onedir build at
`dist-fixed\AgenticDSS`.
Build that folder first, then compile the Inno Setup script from the repository
root:

```powershell
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" installer\AgenticDSS.iss
```

If you installed the 64-bit Inno Setup 7 beta, the compiler may instead be under
`$env:ProgramFiles`:

```powershell
& "$env:ProgramFiles\Inno Setup 7\ISCC.exe" installer\AgenticDSS.iss
```

Inno Setup must be installed on the build machine. The official download page is
https://jrsoftware.org/isdl.php. As of the current documentation check, the stable
Inno Setup 6 download is `innosetup-6.7.3.exe`, and the page also lists Inno Setup
7 beta installers.

The compiled setup executable is written to:

```text
installer\output\AgenticDSS-Setup.exe
```

That setup executable is the file to give to participants. They should download
and double-click `AgenticDSS-Setup.exe`; they should not download `dist\`,
`dist-fixed\`, or the repository source tree. The `dist-fixed\AgenticDSS` folder
is only an intermediate build input used by Inno Setup when creating the single
installer EXE.

Because `dist\`, `dist-fixed\`, and `installer\output\` are generated build
artifacts, they are intentionally ignored by Git. To distribute the app, upload
`installer\output\AgenticDSS-Setup.exe` as a release asset or share that single
file directly with participants.

The uninstaller removes the installed application files and shortcuts. It does not
remove the per-user app data folder returned by `paths.user_data_dir()`, so a
participant's saved API keys, settings, history database, usage counter, watchlist,
and portfolio survive uninstall/reinstall.

Final manual verification is still required on a clean Windows machine or VM with
no Python installed: run the setup executable, launch the installed app, save
settings/API keys, and complete one real analysis run.
