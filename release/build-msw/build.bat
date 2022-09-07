@echo off

if "%1"=="" (
    echo "错误: 未传入版本参数(eg: v2.0.0)"
    exit /b 1)

echo 开始pyinstaller打包.
pyinstaller ^
    --log-level=DEBUG ^
    --distpath=".\release\dist" ^
    --workpath=".\release\build" ^
    --upx-dir=".\release\build-msw\upx-3.95-win64" ^
    --noconfirm ^
    .\release\build-msw\build.spec
echo pyinstaller打包完成.

echo 开始zip打包
mkdir .\release\dist\%1
tar -a -cf .\release\dist\%1\ArchOctopus_%1_Portable.zip -C .\release\dist\ArchOctopus *
echo zip打包完成

echo 开始nsis打包
python .\release\build-msw\build_nsi.py
makensis /V4 /INPUTCHARSET UTF8 /DPRODUCT_VERSION=%1 .\release\build-msw\build.nsi
echo nsis打包完成

exit /b 0