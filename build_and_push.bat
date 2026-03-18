@echo off
set /p USERNAME="Docker Hub usuario: "
set IMAGE=%USERNAME%/todo-app:latest

echo.
echo Construyendo imagen %IMAGE%...
docker build -t %IMAGE% .

echo.
echo Subiendo a Docker Hub...
docker push %IMAGE%

echo.
echo Listo. Imagen disponible en: %IMAGE%
echo Actualiza el docker-compose.yml con este nombre de imagen.
pause
