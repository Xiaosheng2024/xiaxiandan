@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "APP_NAME=EHX下线防错"
set "PACKAGE_DIR=dist\EHX下线防错_Windows"
set "BINARY_DIR=dist_binary"

echo [1/5] 安装打包依赖...
py -3 -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [2/5] 生成 Windows EXE...
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "%APP_NAME%" ^
  --distpath "%BINARY_DIR%" ^
  --workpath "build\pyinstaller" ^
  --specpath "build" ^
  main.py
if errorlevel 1 goto :error

echo [3/5] 创建交付目录...
if exist "%PACKAGE_DIR%" rmdir /s /q "%PACKAGE_DIR%"
mkdir "%PACKAGE_DIR%"
mkdir "%PACKAGE_DIR%\data"
mkdir "%PACKAGE_DIR%\logs"
mkdir "%PACKAGE_DIR%\output"
mkdir "%PACKAGE_DIR%\output\pdf"
mkdir "%PACKAGE_DIR%\output\barcodes"

echo [4/5] 复制交付文件...
copy /y "%BINARY_DIR%\%APP_NAME%.exe" "%PACKAGE_DIR%\%APP_NAME%.exe" >nul
copy /y "config.json" "%PACKAGE_DIR%\config.json" >nul
copy /y "EHX物料号匹配.xlsx" "%PACKAGE_DIR%\EHX物料号匹配.xlsx" >nul
copy /y "报交下线单模板.xlsx" "%PACKAGE_DIR%\报交下线单模板.xlsx" >nul
copy /y "README.md" "%PACKAGE_DIR%\README.md" >nul
copy /y "A5_PDF说明.md" "%PACKAGE_DIR%\A5_PDF说明.md" >nul
copy /y "操作员使用说明.md" "%PACKAGE_DIR%\操作员使用说明.md" >nul
copy /y "管理员部署说明.md" "%PACKAGE_DIR%\管理员部署说明.md" >nul
copy /y "启动说明.txt" "%PACKAGE_DIR%\启动说明.txt" >nul
if errorlevel 1 goto :error

echo [5/5] 压缩交付包...
if exist "dist\EHX下线防错_Windows.zip" del /q "dist\EHX下线防错_Windows.zip"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Compress-Archive -Path '%PACKAGE_DIR%' -DestinationPath 'dist\EHX下线防错_Windows.zip' -Force"
if errorlevel 1 goto :error

echo.
echo 打包完成：dist\EHX下线防错_Windows.zip
exit /b 0

:error
echo.
echo 打包失败，请检查上方错误信息。
exit /b 1
