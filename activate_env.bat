@echo off
REM CancerCare360 - Activation de l'environnement de developpement
REM Usage : activate_env.bat
REM A lancer au debut de CHAQUE nouvelle session de travail (nouveau terminal).

call .venv\Scripts\activate.bat
set DBT_PROFILES_DIR=lakehouse\dbt

echo.
echo Environnement active :
echo   - venv Python actif
echo   - DBT_PROFILES_DIR = %DBT_PROFILES_DIR%
echo.
echo Pensez a lancer Docker si ce n'est pas deja fait :
echo   docker compose -f infra\docker\docker-compose.yml up -d
echo.
