@echo off
:: Copied to <PortableRoot>/run_gui_portable.bat at build time (legacy fallback)
call "%~dp0Next-Trainer\scripts\portable\launch_portable.bat" %*
exit /b %errorlevel%
