@echo off
echo Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller

echo Building exe...
pyinstaller --onefile --windowed --name "PDF Nikudot" app.py

echo.
echo Done! Find the exe in the "dist" folder.
pause
