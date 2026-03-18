# Instalacion: pip install flask
# Ejecutar:    python app.py
# Abrir:       http://localhost:5000

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import json
import os
import hmac
from datetime import datetime, date, timedelta
import uuid

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import Flow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build as gcal_build
    GOOGLE_LIBS = True
except ImportError:
    GOOGLE_LIBS = False

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(BASE_DIR, 'data')
DATA_FILE = os.path.join(DATA_DIR, 'tasks.json')

GCAL_SCOPES      = ['https://www.googleapis.com/auth/calendar.readonly']
CREDENTIALS_FILE = os.path.join(DATA_DIR, 'credentials.json')
TOKEN_FILE       = os.path.join(DATA_DIR, 'token.json')
BASE_URL         = os.environ.get('BASE_URL', '').rstrip('/')
APP_USERNAME     = os.environ.get('APP_USERNAME', 'admin')
APP_PASSWORD     = os.environ.get('APP_PASSWORD', 'changeme')

# Crear directorio de datos si no existe
os.makedirs(DATA_DIR, exist_ok=True)

app.permanent_session_lifetime = timedelta(hours=8)

# Permite OAuth sobre HTTP (necesario sin HTTPS en red local)
if os.environ.get('OAUTHLIB_INSECURE_TRANSPORT'):
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

MONTHS_ES = {
    1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
    5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
    9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre',
}
DAYS_ES = {0: 'Lunes', 1: 'Martes', 2: 'Miércoles', 3: 'Jueves',
           4: 'Viernes', 5: 'Sábado', 6: 'Domingo'}
DAYS_SHORT = {0: 'Lun', 1: 'Mar', 2: 'Mié', 3: 'Jue',
              4: 'Vie', 5: 'Sáb', 6: 'Dom'}


def format_date_long(date_obj):
    return (f"{DAYS_ES[date_obj.weekday()]}, {date_obj.day} "
            f"de {MONTHS_ES[date_obj.month]} de {date_obj.year}")


def format_date_short(date_str, today_str):
    try:
        d = date.fromisoformat(date_str)
        t = date.fromisoformat(today_str)
        diff = (t - d).days
        if diff == 0:
            return "Hoy"
        elif diff == 1:
            return "Ayer"
        elif diff == -1:
            return "Mañana"
        elif 2 <= diff < 7:
            return f"{DAYS_SHORT[d.weekday()]} {d.day:02d}/{d.month:02d}"
        elif -7 < diff < -1:
            return f"{DAYS_SHORT[d.weekday()]} {d.day:02d}/{d.month:02d}"
        else:
            return f"{d.day:02d}/{d.month:02d}/{str(d.year)[2:]}"
    except Exception:
        return date_str


def load_data():
    if not os.path.exists(DATA_FILE):
        return {"tasks": []}
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {"tasks": []}


def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_calendar_service():
    """Devuelve el servicio autenticado de Google Calendar, o None si no disponible."""
    if not GOOGLE_LIBS or not os.path.exists(CREDENTIALS_FILE):
        return None
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, GCAL_SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(TOKEN_FILE, 'w') as f:
                    f.write(creds.to_json())
            else:
                return None
        return gcal_build('calendar', 'v3', credentials=creds)
    except Exception as e:
        print(f"[Google Calendar] Error cargando credenciales: {e}")
        return None


def get_calendar_events(date_str):
    """Trae los eventos de Google Calendar para una fecha dada."""
    service = get_calendar_service()
    if not service:
        return []
    try:
        # Calcular offset local para delimitar el día correctamente
        offset_secs = int(datetime.now().astimezone().utcoffset().total_seconds())
        sign = '+' if offset_secs >= 0 else '-'
        h, rem = divmod(abs(offset_secs), 3600)
        tz = f"{sign}{h:02d}:{rem // 60:02d}"

        result = service.events().list(
            calendarId='primary',
            timeMin=f"{date_str}T00:00:00{tz}",
            timeMax=f"{date_str}T23:59:59{tz}",
            singleEvents=True,
            orderBy='startTime',
        ).execute()

        events = []
        for ev in result.get('items', []):
            start = ev.get('start', {})
            if 'dateTime' in start:
                dt = datetime.fromisoformat(start['dateTime']).astimezone()
                time_str = dt.strftime('%H:%M')
                is_all_day = False
            else:
                time_str = None
                is_all_day = True

            events.append({
                'id': ev['id'],
                'title': ev.get('summary', 'Sin título'),
                'notes': ev.get('description', ''),
                'location': ev.get('location', ''),
                'time': time_str,
                'is_all_day': is_all_day,
                'html_link': ev.get('htmlLink', ''),
                'source': 'google_calendar',
            })

        # Todo el día primero, luego por hora
        events.sort(key=lambda x: (0 if x['is_all_day'] else 1, x['time'] or ''))
        return events
    except Exception as e:
        print(f"[Google Calendar] {e}")
        return []


def rollover_tasks():
    """Mueve tareas incompletas de días pasados a hoy."""
    data = load_data()
    today = date.today().isoformat()
    changed = False
    for task in data['tasks']:
        if (task.get('due_date') and
                task['due_date'] < today and
                not task.get('completed', False)):
            task['due_date'] = today
            changed = True
    if changed:
        save_data(data)


def get_sidebar_data(current_date_str=None):
    data = load_data()
    today_str = date.today().isoformat()

    dates_info = {}
    for task in data['tasks']:
        d = task.get('due_date')
        if d:
            if d not in dates_info:
                dates_info[d] = {'total': 0, 'pending': 0, 'label': ''}
            dates_info[d]['total'] += 1
            if not task.get('completed'):
                dates_info[d]['pending'] += 1

    if today_str not in dates_info:
        dates_info[today_str] = {'total': 0, 'pending': 0, 'label': ''}

    for d in dates_info:
        dates_info[d]['label'] = format_date_short(d, today_str)

    # Futuros ascendentes, pasados descendentes
    future = sorted(d for d in dates_info if d > today_str)
    past = sorted((d for d in dates_info if d < today_str), reverse=True)
    other_dates = future + past

    inbox_count = sum(
        1 for t in data['tasks']
        if not t.get('due_date') and not t.get('completed')
    )

    return {
        'other_dates': other_dates[:20],
        'dates_info': dates_info,
        'inbox_count': inbox_count,
        'today': today_str,
        'current_date': current_date_str,
        'gcal_enabled': os.path.exists(CREDENTIALS_FILE),
        'gcal_connected': os.path.exists(CREDENTIALS_FILE) and os.path.exists(TOKEN_FILE),
    }


# ─────────────────────────────────────────────
# Autenticación
# ─────────────────────────────────────────────

@app.before_request
def require_login():
    """Protege todas las rutas excepto /login."""
    if request.path == '/login':
        return None
    if not session.get('logged_in'):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'No autenticado'}), 401
        return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        user_ok = hmac.compare_digest(username, APP_USERNAME)
        pass_ok = hmac.compare_digest(password, APP_PASSWORD)
        if user_ok and pass_ok:
            session.permanent = True
            session['logged_in'] = True
            return redirect(url_for('index'))
        error = 'Usuario o contraseña incorrectos'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ─────────────────────────────────────────────
# Rutas de vistas
# ─────────────────────────────────────────────

@app.route('/')
def index():
    rollover_tasks()
    return redirect(url_for('day_view', date_str=date.today().isoformat()))


@app.route('/inbox')
def inbox():
    data = load_data()
    inbox_tasks = [t for t in data['tasks']
                   if not t.get('due_date') and not t.get('completed')]
    inbox_tasks.sort(key=lambda x: x.get('created_at', ''))
    sidebar = get_sidebar_data(current_date_str=None)
    return render_template('inbox.html', tasks=inbox_tasks, sidebar=sidebar)


@app.route('/day/<date_str>')
def day_view(date_str):
    rollover_tasks()
    data = load_data()

    day_tasks = [t for t in data['tasks'] if t.get('due_date') == date_str]
    day_tasks.sort(key=lambda x: (x.get('completed', False), x.get('created_at', '')))

    try:
        date_obj = date.fromisoformat(date_str)
        prev_date = (date_obj - timedelta(days=1)).isoformat()
        next_date = (date_obj + timedelta(days=1)).isoformat()
        date_formatted = format_date_long(date_obj)
    except ValueError:
        prev_date = next_date = date_str
        date_formatted = date_str

    today = date.today().isoformat()
    sidebar = get_sidebar_data(current_date_str=date_str)
    cal_events = get_calendar_events(date_str)

    return render_template(
        'day.html',
        tasks=day_tasks,
        cal_events=cal_events,
        date_str=date_str,
        date_formatted=date_formatted,
        prev_date=prev_date,
        next_date=next_date,
        today=today,
        sidebar=sidebar,
        is_today=(date_str == today),
        is_past=(date_str < today),
    )


@app.route('/pending')
def pending_view():
    rollover_tasks()
    data = load_data()
    today_str = date.today().isoformat()

    tasks_dated = sorted(
        [t for t in data['tasks'] if not t.get('completed') and t.get('due_date')],
        key=lambda x: x['due_date']
    )
    tasks_inbox = [t for t in data['tasks']
                   if not t.get('completed') and not t.get('due_date')]

    groups = []
    for task in tasks_dated:
        d = task['due_date']
        if not groups or groups[-1]['date'] != d:
            try:
                label = format_date_long(date.fromisoformat(d))
            except ValueError:
                label = d
            groups.append({
                'date': d,
                'label': label,
                'is_today': d == today_str,
                'is_past': d < today_str,
                'tasks': [],
            })
        groups[-1]['tasks'].append(task)

    if tasks_inbox:
        groups.append({'date': None, 'label': 'Sin fecha (Inbox)',
                       'is_today': False, 'is_past': False, 'tasks': tasks_inbox})

    total = sum(len(g['tasks']) for g in groups)
    sidebar = get_sidebar_data(current_date_str=None)
    return render_template('pending.html', groups=groups, sidebar=sidebar,
                           today=today_str, total=total)


@app.route('/completed')
def completed_view():
    data = load_data()
    today_str = date.today().isoformat()

    tasks_dated = sorted(
        [t for t in data['tasks'] if t.get('completed') and t.get('due_date')],
        key=lambda x: x['due_date']
    )
    tasks_no_date = [t for t in data['tasks']
                     if t.get('completed') and not t.get('due_date')]

    groups = []
    for task in tasks_dated:
        d = task['due_date']
        if not groups or groups[-1]['date'] != d:
            try:
                label = format_date_long(date.fromisoformat(d))
            except ValueError:
                label = d
            groups.append({
                'date': d,
                'label': label,
                'is_today': d == today_str,
                'is_past': d < today_str,
                'tasks': [],
            })
        groups[-1]['tasks'].append(task)

    if tasks_no_date:
        groups.append({'date': None, 'label': 'Sin fecha',
                       'is_today': False, 'is_past': False, 'tasks': tasks_no_date})

    total = sum(len(g['tasks']) for g in groups)
    sidebar = get_sidebar_data(current_date_str=None)
    return render_template('completed.html', groups=groups, sidebar=sidebar,
                           today=today_str, total=total)


# ─────────────────────────────────────────────
# API REST
# ─────────────────────────────────────────────

@app.route('/api/tasks', methods=['POST'])
def create_task():
    data = load_data()
    req = request.get_json(force=True)
    title = (req.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'El título es requerido'}), 400

    task = {
        'id': str(uuid.uuid4()),
        'title': title,
        'notes': (req.get('notes') or '').strip(),
        'due_date': req.get('due_date') or None,
        'completed': False,
        'created_at': datetime.now().isoformat(),
        'completed_at': None,
    }
    data['tasks'].append(task)
    save_data(data)
    return jsonify(task), 201


@app.route('/api/tasks/<task_id>', methods=['PUT'])
def update_task(task_id):
    data = load_data()
    for task in data['tasks']:
        if task['id'] == task_id:
            req = request.get_json(force=True)
            if 'title' in req:
                task['title'] = (req['title'] or '').strip()
            if 'notes' in req:
                task['notes'] = (req['notes'] or '').strip()
            if 'due_date' in req:
                task['due_date'] = req['due_date'] or None
            if 'completed' in req:
                task['completed'] = bool(req['completed'])
                task['completed_at'] = (
                    datetime.now().isoformat() if task['completed'] else None
                )
            save_data(data)
            return jsonify(task)
    return jsonify({'error': 'Tarea no encontrada'}), 404


@app.route('/api/tasks/<task_id>/toggle', methods=['POST'])
def toggle_task(task_id):
    data = load_data()
    for task in data['tasks']:
        if task['id'] == task_id:
            task['completed'] = not task.get('completed', False)
            task['completed_at'] = (
                datetime.now().isoformat() if task['completed'] else None
            )
            save_data(data)
            return jsonify(task)
    return jsonify({'error': 'Tarea no encontrada'}), 404


@app.route('/api/tasks/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    data = load_data()
    before = len(data['tasks'])
    data['tasks'] = [t for t in data['tasks'] if t['id'] != task_id]
    if len(data['tasks']) == before:
        return jsonify({'error': 'Tarea no encontrada'}), 404
    save_data(data)
    return jsonify({'success': True})


@app.route('/gcal/setup')
def gcal_setup():
    sidebar = get_sidebar_data()
    return render_template('gcal_setup.html', sidebar=sidebar)


def _callback_url():
    if BASE_URL:
        return f"{BASE_URL}/auth/google/callback"
    return url_for('auth_google_callback', _external=True)


@app.route('/auth/google')
def auth_google():
    if not GOOGLE_LIBS or not os.path.exists(CREDENTIALS_FILE):
        return redirect(url_for('gcal_setup'))
    try:
        flow = Flow.from_client_secrets_file(
            CREDENTIALS_FILE,
            scopes=GCAL_SCOPES,
            redirect_uri=_callback_url(),
        )
        auth_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent',
        )
        session['oauth_state'] = state
        return redirect(auth_url)
    except Exception as e:
        return f'Error iniciando autorización: {e}', 500


@app.route('/auth/google/callback')
def auth_google_callback():
    state = session.get('oauth_state')
    try:
        flow = Flow.from_client_secrets_file(
            CREDENTIALS_FILE,
            scopes=GCAL_SCOPES,
            state=state,
            redirect_uri=_callback_url(),
        )
        # Corregir URL si hay proxy que cambia http→https
        auth_response = request.url
        if BASE_URL.startswith('https://') and auth_response.startswith('http://'):
            auth_response = 'https://' + auth_response[7:]

        flow.fetch_token(authorization_response=auth_response)
        with open(TOKEN_FILE, 'w') as f:
            f.write(flow.credentials.to_json())
        session.pop('oauth_state', None)
        return redirect(url_for('index'))
    except Exception as e:
        return f'Error completando autorización: {e}', 500


@app.route('/auth/google/disconnect')
def auth_google_disconnect():
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)
    return redirect(url_for('index'))


if __name__ == '__main__':
    print("\n  TODO App iniciada -> http://0.0.0.0:5000\n")
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=5000, debug=debug)
