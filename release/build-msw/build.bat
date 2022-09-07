@echo off

if "%1"=="" (
    echo "����: δ����汾����(eg: v2.0.0)"
    exit /b 1)

echo ��ʼpyinstaller���.
pyinstaller ^
    --log-level=DEBUG ^
    --distpath=".\release\dist" ^
    --workpath=".\release\build" ^
    --upx-dir=".\release\build-msw\upx-3.95-win64" ^
    --noconfirm ^
    .\release\build-msw\build.spec
echo pyinstaller������.

echo ��ʼzip���
mkdir .\release\dist\%1
tar -a -cf .\release\dist\%1\ArchOctopus_%1_Portable.zip -C .\release\dist\ArchOctopus *
echo zip������

echo ��ʼnsis���
python .\release\build-msw\build_nsi.py
makensis /V4 /INPUTCHARSET UTF8 /DPRODUCT_VERSION=%1 .\release\build-msw\build.nsi
echo nsis������

exit /b 0