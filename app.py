import os
import random
import string
import logging
from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, leave_room, emit
import psycopg2
from psycopg2.extras import RealDictCursor

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

# Pobranie URL bazy danych
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    logger.error("BŁĄD: Brak zmiennej środowiskowej DATABASE_URL")
    raise RuntimeError("Brak zmiennej środowiskowej DATABASE_URL")

# Poprawka formatu URL dla psycopg2 (często wymagana na Render/Heroku)
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
    # Dla psycopg2.connect musimy cofnąć zmianę lub użyć bezpośredniego stringa
    # psycopg2.connect oczekuje standardowego postgresql://
    DIRECT_DB_URL = os.environ.get('DATABASE_URL').replace("postgresql://", "postgresql://", 1) 
else:
    DIRECT_DB_URL = DATABASE_URL

def get_db_connection():
    try:
        conn = psycopg2.connect(DIRECT_DB_URL)
        return conn
    except Exception as e:
        logger.error(f"Błąd połączenia z bazą: {e}")
        return None

def init_db():
    """Inicjalizacja bazy danych - tworzenie tabel jeśli nie istnieją"""
    conn = get_db_connection()
    if not conn:
        logger.error("Nie można połączyć z bazą przy inicjalizacji.")
        return
    
    try:
        with conn.cursor() as cur:
            logger.info("Sprawdzanie/tworzenie tabel...")
            
            # Tabela pokoi
            cur.execute("""
                CREATE TABLE IF NOT EXISTS game_rooms (
                    id SERIAL PRIMARY KEY,
                    room_code VARCHAR(6) UNIQUE NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    is_active BOOLEAN DEFAULT TRUE,
                    status VARCHAR(20) DEFAULT 'lobby',
                    current_round INTEGER DEFAULT 0,
                    round_letter VARCHAR(1) DEFAULT ''
                )
            """)
            
            # Tabela graczy
            cur.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    id SERIAL PRIMARY KEY,
                    room_id INTEGER REFERENCES game_rooms(id) ON DELETE CASCADE,
                    nickname VARCHAR(50) NOT NULL,
                    socket_id VARCHAR(100),
                    score INTEGER DEFAULT 0,
                    joined_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            
            # Tabela odpowiedzi
            cur.execute("""
                CREATE TABLE IF NOT EXISTS answers (
                    id SERIAL PRIMARY KEY,
                    player_id INTEGER REFERENCES players(id) ON DELETE CASCADE,
                    room_id INTEGER REFERENCES game_rooms(id) ON DELETE CASCADE,
                    category VARCHAR(50) NOT NULL,
                    answer TEXT NOT NULL,
                    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            
            # Historia gier
            cur.execute("""
                CREATE TABLE IF NOT EXISTS game_history (
                    id SERIAL PRIMARY KEY,
                    room_code VARCHAR(6) NOT NULL,
                    winner_nickname VARCHAR(50),
                    final_scores JSONB,
                    finished_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            
            conn.commit()
            logger.info("Tabele gotowe.")
    except Exception as e:
        logger.error(f"Błąd inicjalizacji bazy: {e}")
        conn.rollback()
    finally:
        conn.close()

# Uruchomienie inicjalizacji przy starcie aplikacji
init_db()

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

CATEGORIES_LIST = ["Imię", "Miasto", "Kolor", "Zwierzę", "Roślina", "Przedmiot", "Zawód", "Potrawa"]
ALLOWED_LETTERS = "AĄBCĆDEĘFGHIJKLŁMNŃOÓPQRSŚTUVWXYZŹŻ"

def generate_room_code(length=6):
    chars = string.ascii_uppercase + string.digits
    max_attempts = 100
    for _ in range(max_attempts):
        code = ''.join(random.choices(chars, k=length))
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM game_rooms WHERE room_code = %s", (code,))
                    if not cur.fetchone():
                        return code
            finally:
                conn.close()
    return None

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    logger.info(f'Klient połączony: {request.sid}')

@socketio.on('disconnect')
def handle_disconnect():
    logger.info(f'Klient rozłączony: {request.sid}')
    conn = get_db_connection()
    if not conn: return
    
    try:
        with conn.cursor() as cur:
            # Znajdź gracza
            cur.execute("SELECT id, room_id, nickname FROM players WHERE socket_id = %s", (request.sid,))
            player = cur.fetchone()
            
            if player:
                player_id, room_id, nickname = player
                # Usuń gracza
                cur.execute("DELETE FROM players WHERE id = %s", (player_id,))
                
                # Sprawdź czy pokój jest pusty
                cur.execute("SELECT room_code FROM game_rooms WHERE id = %s", (room_id,))
                room_data = cur.fetchone()
                
                if room_data:
                    room_code = room_data[0]
                    cur.execute("SELECT COUNT(*) FROM players WHERE room_id = %s", (room_id,))
                    count = cur.fetchone()[0]
                    
                    if count == 0:
                        cur.execute("UPDATE game_rooms SET is_active = FALSE WHERE id = %s", (room_id,))
                        logger.info(f"Pokój {room_code} usunięty (pusty).")
                    else:
                        emit('player_left', {'nickname': nickname}, room=room_code)
                
                conn.commit()
    except Exception as e:
        logger.error(f"Błąd przy disconnect: {e}")
        conn.rollback()
    finally:
        conn.close()

@socketio.on('create_room')
def handle_create_room(nickname):
    logger.info(f"Próba utworzenia pokoju przez: {nickname}")
    if not nickname or len(nickname) > 15:
        emit('error', {'message': 'Nieprawidłowy nick (1-15 znaków).'})
        return

    room_code = generate_room_code()
    if not room_code:
        emit('error', {'message': 'Nie udało się wygenerować kodu pokoju.'})
        return

    conn = get_db_connection()
    if not conn:
        emit('error', {'message': 'Błąd bazy danych.'})
        return

    try:
        with conn.cursor() as cur:
            # Utwórz pokój
            cur.execute("""
                INSERT INTO game_rooms (room_code, status, created_at) 
                VALUES (%s, 'lobby', NOW())
                RETURNING id
            """, (room_code,))
            room_id = cur.fetchone()[0]
            
            # Dodaj twórcę jako gracza
            cur.execute("""
                INSERT INTO players (room_id, nickname, socket_id, score) 
                VALUES (%s, %s, %s, 0)
            """, (room_id, nickname, request.sid))
            
            conn.commit()
            
            join_room(room_code)
            logger.info(f"Pokój {room_code} utworzony przez {nickname}.")
            
            emit('room_created', {'room_code': room_code, 'player_id': request.sid})
            
            # Wyślij aktualną listę graczy (tylko twórca na razie)
            emit('update_player_list', {'players': [nickname]}, room=room_code)
            
    except Exception as e:
        logger.error(f"Błąd tworzenia pokoju: {e}")
        conn.rollback()
        emit('error', {'message': 'Wewnętrzny błąd serwera przy tworzeniu pokoju.'})
    finally:
        conn.close()

@socketio.on('join_room')
def handle_join_room(data):
    room_code = data.get('room_code', '').upper().strip()
    nickname = data.get('nickname', '').strip()
    
    logger.info(f"Próba dołączenia do {room_code} jako {nickname}")
    
    if not room_code or not nickname:
        emit('error', {'message': 'Podaj kod i nick.'})
        return

    conn = get_db_connection()
    if not conn:
        emit('error', {'message': 'Błąd bazy danych.'})
        return

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Sprawdź pokój
            cur.execute("SELECT id, status FROM game_rooms WHERE room_code = %s AND is_active = TRUE", (room_code,))
            room = cur.fetchone()
            
            if not room:
                emit('error', {'message': 'Pokój nie istnieje lub jest nieaktywny.'})
                return
            
            if room['status'] != 'lobby':
                emit('error', {'message': 'Gra już trwa w tym pokoju!'})
                return
            
            # Sprawdź liczbę graczy
            cur.execute("SELECT COUNT(*) as count FROM players WHERE room_id = %s", (room['id'],))
            count = cur.fetchone()['count']
            
            if count >= 8:
                emit('error', {'message': 'Pokój jest pełny (max 8 graczy).'})
                return

            # Dodaj gracza
            cur.execute("""
                INSERT INTO players (room_id, nickname, socket_id, score) 
                VALUES (%s, %s, %s, 0)
            """, (room['id'], nickname, request.sid))
            
            conn.commit()
            
            join_room(room_code)
            logger.info(f"{nickname} dołączył do {room_code}.")
            
            emit('joined_room', {'room_code': room_code})
            
            # Pobierz i wyślistę wszystkich graczy
            cur.execute("SELECT nickname FROM players WHERE room_id = %s", (room['id'],))
            players = [p['nickname'] for p in cur.fetchall()]
            emit('update_player_list', {'players': players}, room=room_code)
            
            emit('player_joined', {'nickname': nickname}, room=room_code)
            
    except Exception as e:
        logger.error(f"Błąd dołączania: {e}")
        conn.rollback()
        emit('error', {'message': 'Błąd dołączania do pokoju.'})
    finally:
        conn.close()

@socketio.on('start_game')
def handle_start_game(room_code):
    logger.info(f"Start gry w pokoju {room_code}")
    conn = get_db_connection()
    if not conn: return
    
    try:
        with conn.cursor() as cur:
            # Sprawdź czy nadawca jest w pokoju (uproszczone)
            cur.execute("SELECT id, status FROM game_rooms WHERE room_code = %s", (room_code,))
            room = cur.fetchone()
            
            if not room or room[1] != 'lobby':
                return # Nie można zacząć
                
            letter = random.choice(ALLOWED_LETTERS)
            
            cur.execute("""
                UPDATE game_rooms 
                SET status = 'playing', round_letter = %s, current_round = current_round + 1
                WHERE id = %s
            """, (letter, room[0]))
            
            conn.commit()
            logger.info(f"Gra rozpoczęta! Litera: {letter}")
            emit('game_started', {'letter': letter}, room=room_code)
            
    except Exception as e:
        logger.error(f"Błąd startu gry: {e}")
        conn.rollback()
    finally:
        conn.close()

@socketio.on('submit_word')
def handle_submit_word(data):
    room_code = data.get('room_code')
    category = data.get('category')
    word = data.get('word', '').strip()
    
    if not word or not category:
        return

    conn = get_db_connection()
    if not conn: return
    
    try:
        with conn.cursor() as cur:
            # Pobierz literę rundy
            cur.execute("SELECT id, round_letter FROM game_rooms WHERE room_code = %s AND status = 'playing'", (room_code,))
            room = cur.fetchone()
            if not room:
                return # Gra nie trwa
            
            room_id, round_letter = room
            
            # Pobierz gracza
            cur.execute("SELECT id FROM players WHERE socket_id = %s AND room_id = %s", (request.sid, room_id))
            player = cur.fetchone()
            if not player:
                return
            
            player_id = player[0]
            
            # Walidacja litery
            if word[0].upper() != round_letter.upper():
                emit('invalid_word', {'reason': f'Słowo musi zaczynać się na {round_letter}'}, room=request.sid)
                return

            # Sprawdzenie duplikatu w tej kategorii w tym pokoju
            cur.execute("""
                SELECT 1 FROM answers 
                WHERE room_id = %s AND category = %s AND LOWER(answer) = LOWER(%s)
            """, (room_id, category, word))
            
            if cur.fetchone():
                emit('duplicate_word', {'category': category}, room=request.sid)
                return

            # Zapisz odpowiedź
            cur.execute("""
                INSERT INTO answers (player_id, room_id, category, answer, submitted_at)
                VALUES (%s, %s, %s, %s, NOW())
            """, (player_id, room_id, category, word.lower()))
            
            conn.commit()
            
            # Potwierdź graczowi
            emit('word_submitted', {'category': category, 'word': word}, room=request.sid)
            # Powiadom innych (opcjonalne, żeby nie zdradzać słów przed czasem, ale tu wysyłamy tylko info że ktoś odpisał)
            # emit('player_submitted', {'category': category}, room=room_code, include_self=False) 
            
    except Exception as e:
        logger.error(f"Błąd zapisu słowa: {e}")
        conn.rollback()
    finally:
        conn.close()

@socketio.on('finish_round')
def handle_finish_round(room_code):
    logger.info(f"Koniec rundy w {room_code}")
    conn = get_db_connection()
    if not conn: return
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id FROM game_rooms WHERE room_code = %s", (room_code,))
            room = cur.fetchone()
            if not room:
                return
            room_id = room['id']
            
            # Pobierz wszystkie odpowiedzi
            cur.execute("""
                SELECT p.nickname, a.category, a.answer
                FROM answers a
                JOIN players p ON a.player_id = p.id
                WHERE a.room_id = %s
            """, (room_id,))
            answers = cur.fetchall()
            
            # Logika punktacji
            grouped = {}
            for row in answers:
                cat = row['category']
                ans = row['answer'].lower()
                nick = row['nickname']
                
                if cat not in grouped: grouped[cat] = {}
                if ans not in grouped[cat]: grouped[cat][ans] = []
                grouped[cat][ans].append(nick)
            
            scores_update = {}
            for cat, answers_dict in grouped.items():
                for ans, nicks in answers_dict.items():
                    # Jeśli odpowiedź podało więcej niż 1 osoba -> 5 pkt, inaczej 10 pkt
                    points = 5 if len(nicks) > 1 else 10
                    for nick in nicks:
                        scores_update[nick] = scores_update.get(nick, 0) + points
            
            # Aktualizacja wyników w bazie
            for nick, pts in scores_update.items():
                cur.execute("""
                    UPDATE players SET score = score + %s WHERE nickname = %s AND room_id = %s
                """, (pts, nick, room_id))
            
            conn.commit()
            
            # Pobierz końcowe wyniki
            cur.execute("""
                SELECT nickname, score FROM players WHERE room_id = %s ORDER BY score DESC
            """, (room_id,))
            final_rows = cur.fetchall()
            scores_dict = {row['nickname']: row['score'] for row in final_rows}
            
            # Wyczyść odpowiedzi z rundy
            cur.execute("DELETE FROM answers WHERE room_id = %s", (room_id,))
            conn.commit()
            
            logger.info(f"Wyniki rundy: {scores_dict}")
            emit('round_finished', {'scores': scores_dict}, room=room_code)
            
    except Exception as e:
        logger.error(f"Błąd kończenia rundy: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Uruchamianie serwera na porcie {port}...")
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
