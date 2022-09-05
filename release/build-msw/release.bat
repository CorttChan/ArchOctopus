@echo off
pyinstaller ^
    --log-level=DEBUG ^
    --distpath=".\dist" ^
    --workpath=".\build" ^
    --upx-dir=".\upx-3.95-win64" ^
    --noconfirm ^
    build.spec
echo 'ArchOctopus build completed...'.
pause