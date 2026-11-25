@echo off
REM Creates a virtual environment for the VAT Identifier project, activates it,
REM and only then installs the dependencies from crawler\requirements.txt.
cd /d "%~dp0"

if not exist .venv (
    echo Creating virtual environment in .venv ...
    python -m venv .venv || (echo Python not found. Install Python 3.10+ and tick "Add to PATH". & exit /b 1)
)

echo Activating .venv ...
call .venv\Scripts\activate.bat

echo Python in use:
where python
python -c "import sys; print(sys.prefix)"

echo Installing dependencies into the venv ...
python -m pip install --upgrade pip
python -m pip install -r crawler\requirements.txt

echo Checking ...
python -c "import requests, bs4, pypdf, pandas, pytest; import sys; print('OK - dependencies installed in', sys.prefix)"
echo.
echo Done. In a new terminal, activate with:  .venv\Scripts\activate
