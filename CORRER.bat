@echo off
cd /d "%~dp0"
echo Iniciando servidor Bodega PA SAS...
echo.
echo Abre en el PC:   http://localhost:8000
echo Abre en el cel:  http://TU_IP_LOCAL:8000
echo.
echo Para saber tu IP local escribe: ipconfig
echo.
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause
