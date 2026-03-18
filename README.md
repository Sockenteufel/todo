# To-Do App

App web minimalista para gestionar tareas del día a día. Diseñada para correr en una red local o servidor propio, con interfaz en español y tema oscuro.

## Características

- **Vista por día** — navega entre fechas y ve las tareas de cada día
- **Rollover automático** — las tareas incompletas se mueven solas al día actual al abrir la app
- **Inbox** — tareas sin fecha asignada
- **Pendientes** — todas las tareas incompletas agrupadas por fecha
- **Completadas** — historial de tareas terminadas
- **Google Calendar** — muestra tus eventos del calendario junto a las tareas (opcional)
- **Autenticación** — login con usuario y contraseña para uso privado
- **Docker-ready** — desplegable en cualquier servidor con Docker

## Instalación local

**Requisitos:** Python 3.8+

```bash
git clone https://github.com/Sockenteufel/todo.git
cd todo
pip install -r requirements.txt
```

Crea un archivo `.env` o exporta las variables de entorno:

```bash
APP_USERNAME=tu_usuario
APP_PASSWORD=tu_contraseña
SECRET_KEY=una_clave_secreta_larga
```

Inicia la app:

```bash
python app.py
```

Abre http://localhost:5000 en el navegador.

## Despliegue con Docker

```bash
docker compose up -d
```

El archivo `docker-compose.yml` incluido usa las variables de entorno `APP_USERNAME`, `APP_PASSWORD`, `SECRET_KEY` y `BASE_URL`. Los datos se guardan en el volumen `todo_data`.

## Google Calendar (opcional)

1. Crea un proyecto en [Google Cloud Console](https://console.cloud.google.com/) y habilita la API de Google Calendar
2. Descarga las credenciales OAuth como `credentials.json`
3. Coloca el archivo en `data/credentials.json` (o en el volumen de Docker)
4. Ve a `/gcal/setup` en la app para autenticarte

## Variables de entorno

| Variable | Descripción |
|---|---|
| `APP_USERNAME` | Usuario para el login |
| `APP_PASSWORD` | Contraseña para el login |
| `SECRET_KEY` | Clave para firmar la sesión |
| `BASE_URL` | URL completa del servidor (ej. `http://192.168.0.35:5000`), necesaria para OAuth |
| `OAUTHLIB_INSECURE_TRANSPORT` | Pon `1` para permitir OAuth sobre HTTP |
| `FLASK_DEBUG` | Pon `true` para modo debug |
