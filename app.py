import time
import random
import string
import logging
import os
from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, leave_room, emit
from flask_sqlalchemy import SQLAlchemy
import redis
import json

# --- Konfiguracja logowania
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Konfiguracja Aplikacji ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'sigma-world-final-refactored-key')

# Konfiguracja bazy danych - wymuszenie PostgreSQL dla produkcji (Supabase)
# Lokalnie może działać SQLite, ale na serwerze musi być Postgres
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    # Fallback tylko do celów lokalnych, jeśli nie ustawiono zmiennej
    DATABASE_URL = 'sqlite:///sigma_world.db'
    logger.warning("Używam lokalnej bazy SQLite. Do produkcji ustaw zmienną DATABASE_URL (PostgreSQL).")

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Konfiguracja Redis (opcjonalna, do skalowania - na razie wyłączona dla prostoty)
REDIS_URL = os.environ.get('REDIS_URL', None)
redis_client = None
if REDIS_URL:
    try:
        redis_client = redis.from_url(REDIS_URL)
        logger.info("Połączono z Redis.")
    except Exception as e:
        logger.warning(f"Nie udało się połączyć z Redis: {e}")

# Inicjalizacja SocketIO
# async_mode='threading' jest bezpieczniejszy dla Render/Heroku niż eventlet/gevent
socketio = SocketIO(app, cors_allowed_origins="*", ping_timeout=60, ping_interval=25, async_mode='threading', message_queue=None)

random.seed()

# --- Modele Bazy Danych ---
class GameRoom(db.Model):
    """Model przechowujący stan pokoju gry w bazie danych."""
    id = db.Column(db.Integer, primary_key=True)
    room_code = db.Column(db.String(6), unique=True, nullable=False, index=True)
    host_id = db.Column(db.String(100), nullable=False)
    judge_id = db.Column(db.String(100), nullable=False)
    game_state = db.Column(db.Text, nullable=False)  # JSON
    settings = db.Column(db.Text, nullable=False)  # JSON
    round_data = db.Column(db.Text, nullable=True)  # JSON
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

class Player(db.Model):
    """Model przechowujący graczy w pokojach."""
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('game_room.id'), nullable=False, index=True)
    player_sid = db.Column(db.String(100), nullable=False)
    nick = db.Column(db.String(50), nullable=False)
    score = db.Column(db.Integer, default=0)
    room = db.relationship('GameRoom', backref=db.backref('players_list', lazy=True))

class GameHistory(db.Model):
    """Model przechowujący historię zakończonych gier."""
    id = db.Column(db.Integer, primary_key=True)
    room_code = db.Column(db.String(6), nullable=False, index=True)
    final_scores = db.Column(db.Text, nullable=False)  # JSON
    total_rounds = db.Column(db.Integer, nullable=False)
    categories = db.Column(db.Text, nullable=False)  # JSON
    finished_at = db.Column(db.DateTime, server_default=db.func.now())

# Inicjalizacja bazy danych
with app.app_context():
    db.create_all()
    logger.info("Baza danych zainicjalizowana.")

# --- Globalny Stan Serwera (Cache w pamięci dla wydajności) ---
rooms = {}

# --- Stałe Gry ---
ALL_CATEGORIES = {
    "fixed": ['Państwo', 'Miasto', 'Roślina', 'Zwierzę', 'Imię', 'Rzecz', 'Zawód'],
    "optional": [
        'Tytuł książki', 'Tytuł filmu', 'Tytuł piosenki (z autorem)', 'Artysta/Zespół muzyczny', 
        'Wyspa', 'Język', 'Rzeka', 'Morze', 'Góra/pasmo górskie', 'Jezioro', 'Choroba', 'Kolor', 
        'Bohater filmowy (Pełne Imię i Nazwisko lub kryptonim)', 'Tytuł Gry komputerowej', 'Marka samochodu', 
        'Marka odzieżowa', 'Potrawa/Danie', 'Przymiotnik', 'Rzeczownik', 'Czasownik'
    ]
}
# Alfabet bez polskich znaków diakrytycznych oraz bez X i Y
ALPHABET = 'ABCDEFGHIKLMNOPRSTUWZ'
COUNTDOWN_SECONDS = 30
ROUND_TIME_LIMIT_SECONDS = 300
MAX_NICK_LENGTH = 15
MIN_NICK_LENGTH = 1
ROOM_CODE_LENGTH = 4

# --- Funkcje Pomocnicze ---
def find_room_by_sid(sid):
    for code, room in rooms.items():
        if sid in room['players']:
            return code, room
    return None, None

def generate_room_code(length=ROOM_CODE_LENGTH):
    """Generuje unikalny kod pokoju, sprawdzając również bazę danych."""
    while True:
        code = ''.join(random.choices(string.ascii_uppercase, k=length))
        if code not in rooms and GameRoom.query.filter_by(room_code=code).first() is None:
            return code

def save_room_to_db(room_code):
    """Zapisuje lub aktualizuje pokój w bazie danych."""
    if room_code not in rooms:
        return
    
    room = rooms[room_code]
    db_room = GameRoom.query.filter_by(room_code=room_code).first()
    
    if not db_room:
        db_room = GameRoom(room_code=room_code)
        db.session.add(db_room)
    
    db_room.host_id = room['host_id']
    db_room.judge_id = room.get('judge_id', room['host_id'])
    db_room.game_state = json.dumps(room['game_state'])
    db_room.settings = json.dumps(room['settings'])
    db_room.round_data = json.dumps(room.get('round_data')) if room.get('round_data') else None
    
    # Aktualizacja graczy
    Player.query.filter_by(room_id=db_room.id).delete()
    for player_id, player_data in room['players'].items():
        new_player = Player(
            room_id=db_room.id,
            player_sid=player_id,
            nick=player_data['nick'],
            score=player_data['score']
        )
        db.session.add(new_player)
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Błąd zapisu pokoju {room_code} do bazy: {e}")

def load_room_from_db(room_code):
    """Ładuje pokój z bazy danych do pamięci podręcznej."""
    db_room = GameRoom.query.filter_by(room_code=room_code).first()
    if not db_room:
        return False
    
    players = {}
    for player in db_room.players_list:
        players[player.player_sid] = {
            'nick': player.nick,
            'score': player.score
        }
    
    rooms[room_code] = {
        'host_id': db_room.host_id,
        'judge_id': db_room.judge_id,
        'players': players,
        'settings': json.loads(db_room.settings),
        'game_state': json.loads(db_room.game_state),
        'round_data': json.loads(db_room.round_data) if db_room.round_data else {}
    }
    return True

def get_room_state(room_code):
    """Zwraca bezpieczną kopię stanu pokoju do wysłania klientom."""
    if room_code not in rooms:
        # Spróbuj załadować z bazy
        if not load_room_from_db(room_code):
            return {}
    
    room = rooms[room_code]
    return {
        "roomCode": room_code,
        "players": room["players"],
        "settings": room["settings"],
        "hostId": room["host_id"],
        "judgeId": room.get("judge_id"),
        "gameState": room["game_state"]
    }

# --- Główny Widok Aplikacji ---
@app.route('/')
def index():
    """Serwuje główny plik HTML."""
    return render_template('index.html')

# --- Podstawowe Zdarzenia Socket.IO ---
@socketio.on('create_game')
def handle_create_game(data):
    """Tworzy nowy pokój i dodaje hosta."""
    player_id = request.sid
    nick = data.get('nick', 'Gracz bezimienny')[:MAX_NICK_LENGTH].strip()
    
    if len(nick) < MIN_NICK_LENGTH:
        return emit('error', {'message': 'Nick musi mieć przynajmniej 1 znak.'})
    
    room_code = generate_room_code()
    join_room(room_code)
    
    rooms[room_code] = {
        "host_id": player_id,
        "judge_id": player_id,
        "players": {player_id: {"nick": nick, "score": 0}},
        "settings": {"rounds": 5, "categories": list(ALL_CATEGORIES["fixed"])},
        "game_state": {"status": "lobby", "current_round": 0, "current_letter": ""},
        "round_data": {}
    }
    
    # Zapisz nowy pokój w bazie danych
    save_room_to_db(room_code)
    
    emit('game_created', get_room_state(room_code))
    logger.info(f"Pokój '{room_code}' stworzony przez gracza {nick} ({player_id}).")

@socketio.on('join_game')
def handle_join_game(data):
    """Dodaje gracza do istniejącego pokoju."""
    player_id = request.sid
    nick = data.get('nick', 'Gracz bezimienny')[:MAX_NICK_LENGTH].strip()
    room_code = data.get('roomCode', '').upper().strip()
    
    if len(nick) < MIN_NICK_LENGTH:
        return emit('error', {'message': 'Nick musi mieć przynajmniej 1 znak.'})
    
    if not room_code:
        return emit('error', {'message': 'Podaj kod pokoju.'})
    
    if room_code not in rooms:
        return emit('error', {'message': 'Pokój o podanym kodzie nie istnieje.'})
        
    join_room(room_code)
    rooms[room_code]["players"][player_id] = {"nick": nick, "score": 0}
    emit('state_update', get_room_state(room_code), to=room_code)
    logger.info(f"Gracz {nick} ({player_id}) dołączył do pokoju '{room_code}'.")

@socketio.on('disconnect')
def handle_disconnect():
    """Obsługuje odłączenie gracza, czyszczenie i ewentualną zmianę hosta/sędziego."""
    player_id = request.sid
    code, room = find_room_by_sid(player_id)
    if room:
        player_nick = room['players'].get(player_id, {}).get('nick', 'Nieznany')
        logger.info(f"Gracz {player_nick} ({player_id}) opuścił pokój '{code}'.")
        
        # Jeśli gracz był w trakcie rundy, usuń go z finished_players
        if room.get('round_data'):
            if player_id in room['round_data']['finished_players']:
                room['round_data']['finished_players'].remove(player_id)
        
        del room['players'][player_id]
        
        if not room['players']:
            del rooms[code]
            # Usuń pokój z bazy danych
            db_room = GameRoom.query.filter_by(room_code=code).first()
            if db_room:
                Player.query.filter_by(room_id=db_room.id).delete()
                db.session.delete(db_room)
                try:
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"Błąd usuwania pokoju {code} z bazy: {e}")
            logger.info(f"Pokój '{code}' jest pusty i został usunięty.")
            return
        
        if player_id == room['host_id']:
            new_host_id = next(iter(room['players']))
            room['host_id'] = new_host_id
            logger.info(f"Nowy host w pokoju '{code}' to {room['players'][new_host_id]['nick']}.")
        
        if player_id == room['judge_id']:
            room['judge_id'] = room['host_id']
            logger.info(f"Nowy sędzia w pokoju '{code}' to {room['players'][room['host_id']]['nick']}.")
        
        # Zapisz zmiany w bazie
        save_room_to_db(code)
        
        emit('state_update', get_room_state(code), to=code)

# --- Zdarzenia Związane z Ustawieniami Gry ---
@socketio.on('set_judge')
def handle_set_judge(data):
    """Ustawia nowego sędziego (tylko dla hosta)."""
    if data['roomCode'] in rooms and rooms[data['roomCode']]['host_id'] == request.sid:
        rooms[data['roomCode']]['judge_id'] = data['judgeId']
        emit('state_update', get_room_state(data['roomCode']), to=data['roomCode'])

@socketio.on('update_settings')
def handle_update_settings(data):
    """Aktualizuje ustawienia gry (tylko dla hosta)."""
    if data['roomCode'] in rooms and rooms[data['roomCode']]['host_id'] == request.sid:
        rooms[data['roomCode']]['settings'].update(data.get('settings', {}))
        emit('state_update', get_room_state(data['roomCode']), to=data['roomCode'])

# --- Zdarzenia Związane z Rozgrywką ---
@socketio.on('start_game')
def handle_start_game(room_code):
    """Rozpoczyna grę, resetuje punkty i ustawia pierwszą rundę."""
    if room_code in rooms and rooms[room_code]['host_id'] == request.sid:
        room = rooms[room_code]
        if room['game_state']['current_round'] == 0:
            for p_id in room['players']:
                room['players'][p_id]['score'] = 0
        
        room['game_state'].update({"status": 'in_game', "current_round": 1, "current_letter": random.choice(ALPHABET)})
        round_end_time = time.time() + ROUND_TIME_LIMIT_SECONDS
        room['round_data'] = {
            "answers": {}, 
            "finished_players": [],  # Zmieniono z set() na listę dla serializacji JSON
            "timer_end_time": None,
            "round_end_time": round_end_time
        }
        for player_id in room['players']:
            room['round_data']['answers'][player_id] = {}
            
        emit('game_started', get_room_state(room_code), to=room_code)
        socketio.start_background_task(target=enforce_round_time_limit, room_code=room_code, expected_round=1)
        logger.info(f"Gra w pokoju '{room_code}' rozpoczęta. Limit czasu: {ROUND_TIME_LIMIT_SECONDS}s.")

# NOWA FUNKCJA: Pilnuje globalnego limitu czasu na rundę
def enforce_round_time_limit(room_code, expected_round):
    """Zadanie w tle, które pilnuje, by cała runda zakończyła się po upływie czasu."""
    try:
        if room_code not in rooms:
            return
        
        end_time = rooms[room_code].get('round_data', {}).get('round_end_time')
        if end_time and end_time > time.time():
            socketio.sleep(end_time - time.time())
        
        if room_code in rooms and rooms[room_code]['game_state']['current_round'] == expected_round and rooms[room_code]['game_state']['status'] == 'in_game':
            logger.info(f"Globalny czas na rundę ({ROUND_TIME_LIMIT_SECONDS}s) minął w pokoju '{room_code}'. Wymuszam koniec.")
            start_verification(room_code)
    except Exception as e:
        logger.error(f"Błąd w enforce_round_time_limit dla pokoju {room_code}: {e}")


@socketio.on('update_answer')
def handle_update_answer(data):
    """Odbiera i zapisuje odpowiedź gracza na bieżąco."""
    player_id = request.sid
    room_code, room = find_room_by_sid(player_id)
    if not room or room['game_state']['status'] != 'in_game':
        return
    
    category = data.get('category')
    answer = data.get('answer', '')
    
    if isinstance(answer, str) and category is not None:
        if player_id not in room['round_data']['answers']:
            room['round_data']['answers'][player_id] = {}
        room['round_data']['answers'][player_id][category] = answer

@socketio.on('finish_round')
def handle_finish_round():
    """Gracz sygnalizuje koniec rundy."""
    player_id = request.sid
    room_code, room = find_room_by_sid(player_id)
    if not room or room['game_state']['status'] != 'in_game' or player_id in room['round_data']['finished_players']:
        return

    room['round_data']['finished_players'].append(player_id)
    emit('player_finished', {"playerId": player_id}, to=room_code)
    
    all_players_finished = len(room['round_data']['finished_players']) == len(room['players'])
    is_first_player = len(room['round_data']['finished_players']) == 1

    if is_first_player and not all_players_finished:
        end_time = time.time() + COUNTDOWN_SECONDS
        room['round_data']['timer_end_time'] = end_time
        emit('start_countdown', {'endTime': end_time}, to=room_code)
        socketio.start_background_task(target=enforce_countdown, room_code=room_code, expected_round=room['game_state']['current_round'])
        logger.info(f"Start odliczania w pokoju '{room_code}'.")
    elif all_players_finished:
        room['round_data']['timer_end_time'] = None 
        start_verification(room_code)

def enforce_countdown(room_code, expected_round):
    """Zadanie w tle, które pilnuje, by runda zakończyła się po upływie czasu."""
    try:
        if room_code not in rooms:
            return
        end_time = rooms[room_code].get('round_data', {}).get('timer_end_time')
        
        if end_time and end_time > time.time():
            socketio.sleep(end_time - time.time())
        
        if room_code in rooms and rooms[room_code]['game_state']['current_round'] == expected_round and rooms[room_code]['game_state']['status'] == 'in_game':
            logger.info(f"Czas minął w pokoju '{room_code}'. Wymuszam koniec rundy.")
            start_verification(room_code)
    except Exception as e:
        logger.error(f"Błąd w enforce_countdown dla pokoju {room_code}: {e}")

def start_verification(room_code):
    """Przygotowuje i wysyła dane do ekranu weryfikacji sędziego."""
    try:
        if room_code not in rooms:
            return
        if rooms[room_code]['game_state']['status'] != 'in_game':
            return

        room = rooms[room_code]
        
        all_player_answers = room['round_data'].get('answers', {}).copy()
        for player_id in room['players']:
            all_player_answers.setdefault(player_id, {})
        
        room['game_state']['status'] = 'verification'
        verification_payload = {"state": get_room_state(room_code), "allAnswers": all_player_answers}
        socketio.emit('start_verification', verification_payload, to=room_code)
        logger.info(f"Przechodzę do weryfikacji w pokoju '{room_code}'.")
    except Exception as e:
        logger.error(f"Błąd w start_verification dla pokoju {room_code}: {e}")

@socketio.on('submit_verification')
def handle_submit_verification(data):
    """Przyjmuje werdykt sędziego i uruchamia liczenie punktów."""
    if data['roomCode'] in rooms and rooms[data['roomCode']]['judge_id'] == request.sid:
        calculate_and_send_results(data['roomCode'], data.get('verifiedAnswers'))

def calculate_and_send_results(room_code, verified_answers):
    """Oblicza punkty z uwzględnieniem systemu za powtarzające się słowa i wysyła wyniki."""
    try:
        room = rooms[room_code]
        letter = room['game_state']['current_letter'].lower()
        all_player_answers = room['round_data'].get('answers', {})
        detailed_results = {}

        for category in room['settings']['categories']:
            detailed_results[category] = []
            
            # Zbieramy wszystkie poprawne i zweryfikowane odpowiedzi w tej kategorii
            valid_answers = {}
            for p_id in room['players']:
                answer = all_player_answers.get(p_id, {}).get(category, "").strip()
                is_verified = verified_answers.get(p_id, {}).get(category, False)
                if answer and answer.lower().startswith(letter) and is_verified:
                    valid_answers[p_id] = answer.lower()
            
            # Liczymy wystąpienia każdej odpowiedzi
            answer_counts = {}
            for answer in valid_answers.values():
                answer_counts[answer] = answer_counts.get(answer, 0) + 1

            # Obliczamy punkty dla każdego gracza w tej kategorii
            for p_id, p_data in room['players'].items():
                answer = all_player_answers.get(p_id, {}).get(category, "").strip()
                points, reason = 0, "Brak"
                
                if p_id in valid_answers:
                    count = answer_counts[valid_answers[p_id]]
                    
                    if count == 1:
                        # Sprawdzenie czy to naprawdę jedyna odpowiedź w kategorii
                        if len(valid_answers) == 1:
                            points, reason = 20, "Jedyna poprawna (+20)"
                        else:
                            points, reason = 10, "Unikalna (+10)"
                    else:
                        # Powtórzona odpowiedź - zawsze 5 pkt, niezależnie od liczby graczy
                        points, reason = 5, f"Powtórzona ({count}x) (+5)"
                else:
                    if not answer:
                        reason = "Brak"
                    elif not answer.lower().startswith(letter):
                        reason = "Zła litera"
                    else: 
                        reason = "Odrzucona"
                
                room['players'][p_id]['score'] += points
                detailed_results[category].append({
                    "playerId": p_id, "nick": p_data['nick'], "answer": answer,
                    "points": points, "reason": reason
                })

        room['game_state']['status'] = 'results'
        
        # Zapisz aktualny stan gry w bazie (zaktualizowane punkty)
        save_room_to_db(room_code)
        
        results_payload = {"state": get_room_state(room_code), "detailedResults": detailed_results}
        socketio.emit('round_results', results_payload, to=room_code)
        logger.info(f"Wyniki rundy {room['game_state']['current_round']} wysłane do pokoju '{room_code}'.")
    except Exception as e:
        logger.error(f"Błąd w calculate_and_send_results dla pokoju {room_code}: {e}")


@socketio.on('judge_requests_next_round')
def handle_judge_requests_next_round(data):
    """Uruchamia następną rundę lub kończy grę na żądanie sędziego."""
    room_code = data.get('roomCode')
    if room_code not in rooms or rooms[room_code]['judge_id'] != request.sid:
        return

    room = rooms[room_code]
    
    if room['game_state']['current_round'] >= room['settings']['rounds']:
        room['game_state']['status'] = 'game_over'
        
        # Zapisz historię gry w bazie danych
        try:
            final_scores = {p_id: p_data['score'] for p_id, p_data in room['players'].items()}
            game_history = GameHistory(
                room_code=room_code,
                final_scores=json.dumps(final_scores),
                total_rounds=room['game_state']['current_round'],
                categories=json.dumps(room['settings']['categories'])
            )
            db.session.add(game_history)
            
            # Usuń aktywny pokój z bazy (gra zakończona)
            db_room = GameRoom.query.filter_by(room_code=room_code).first()
            if db_room:
                Player.query.filter_by(room_id=db_room.id).delete()
                db.session.delete(db_room)
            
            db.session.commit()
            logger.info(f"Gra w pokoju '{room_code}' zakończona i zapisana w historii.")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Błąd zapisu historii gry {room_code}: {e}")
        
        socketio.emit('game_over', get_room_state(room_code), to=room_code)
        logger.info(f"Koniec gry w pokoju '{room_code}'.")
    else:
        next_round_number = room['game_state']['current_round'] + 1
        room['game_state']['status'] = 'in_game'
        room['game_state']['current_round'] = next_round_number
        room['game_state']['current_letter'] = random.choice(ALPHABET)
        round_end_time = time.time() + ROUND_TIME_LIMIT_SECONDS
        room['round_data'] = {
            "answers": {}, 
            "finished_players": [],  # Zmieniono z set() na listę
            "timer_end_time": None,
            "round_end_time": round_end_time
        }
        for player_id in room['players']:
            room['round_data']['answers'][player_id] = {}

        # Zapisz stan nowej rundy w bazie
        save_room_to_db(room_code)

        socketio.emit('next_round', get_room_state(room_code), to=room_code)
        socketio.start_background_task(target=enforce_round_time_limit, room_code=room_code, expected_round=next_round_number)
        logger.info(f"Sędzia rozpoczął następną rundę ({next_round_number}) w pokoju '{room_code}'.")


@socketio.on('continue_game')
def handle_continue_game(room_code):
    """Resetuje grę do lobby, ZACHOWUJĄC punkty graczy."""
    if room_code in rooms and rooms[room_code]['host_id'] == request.sid:
        room = rooms[room_code]
        room['game_state'] = {"status": "lobby", "current_round": 0, "current_letter": ""}
        room['round_data'] = {}
        
        # Zapisz zmiany w bazie
        save_room_to_db(room_code)
        
        emit('state_update', get_room_state(room_code), to=room_code)
        logger.info(f"Gra w pokoju '{room_code}' kontynuowana (powrót do lobby z zachowaniem punktów).")

# --- Uruchomienie Serwera ---
if __name__ == '__main__':
    logger.info("Serwer SIGMA WORLD uruchomiony. Otwórz przeglądarkę i wejdź na http://127.0.0.1:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)