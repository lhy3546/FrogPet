@echo off
rem =====================================================
rem  FrogPet build script: creates dist\FrogPet.exe
rem =====================================================
cd /d "%~dp0"
python -m PyInstaller --noconsole --onefile --clean -y ^
  --name FrogPet ^
  --icon assets\frog\frog.ico ^
  --add-data "assets;assets" ^
  --exclude-module PySide6.QtQml ^
  --exclude-module PySide6.QtQuick ^
  --exclude-module PySide6.QtQuickWidgets ^
  --exclude-module PySide6.QtQuick3D ^
  --exclude-module PySide6.QtNetwork ^
  --exclude-module PySide6.QtMultimedia ^
  --exclude-module PySide6.QtMultimediaWidgets ^
  --exclude-module PySide6.QtWebEngineCore ^
  --exclude-module PySide6.QtWebEngineWidgets ^
  --exclude-module PySide6.QtWebChannel ^
  --exclude-module PySide6.QtPdf ^
  --exclude-module PySide6.QtPdfWidgets ^
  --exclude-module PySide6.QtSvg ^
  --exclude-module PySide6.QtSvgWidgets ^
  --exclude-module PySide6.QtTest ^
  --exclude-module PySide6.QtOpenGL ^
  --exclude-module PySide6.QtOpenGLWidgets ^
  --exclude-module PySide6.QtCharts ^
  --exclude-module PySide6.QtDataVisualization ^
  --exclude-module PySide6.QtSerialPort ^
  --exclude-module PySide6.QtBluetooth ^
  --exclude-module PySide6.QtNfc ^
  --exclude-module PySide6.QtPositioning ^
  --exclude-module PySide6.QtSensors ^
  --exclude-module PySide6.QtWebSockets ^
  --exclude-module PySide6.QtXml ^
  --exclude-module PySide6.QtDBus ^
  --exclude-module PySide6.QtHelp ^
  --exclude-module PySide6.QtUiTools ^
  --exclude-module PySide6.QtSql ^
  --exclude-module PySide6.QtRemoteObjects ^
  --exclude-module PySide6.QtScxml ^
  --exclude-module PySide6.QtStateMachine ^
  --exclude-module PySide6.QtDesigner ^
  main.py
echo.
echo Build finished: dist\FrogPet.exe
pause
