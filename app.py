import os
import random
import string
from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, leave_room, emit
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

# Konfiguracja Bazy Danych (Supabase)
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError("Brak zmiennej środowiskowej DATABASE_URL")

# Poprawka URL dla SQLAlchemy (zmiana postgresql na postgresql+psycopg2)
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Inicjalizacja SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Stałe gry
CATEGORIES_LIST = ["Imię", "Miasto", "Kolor", "Zwierzę", "Roślina", "Przedmiot", "Zawód", "Potrawa"]
ALLOWED_LETTERS = "AĄBCĆDEĘFGHIJKLŁMNŃOÓPQRSŚTUVWXYZŹŻ" # Pełny alfabet polski

def generate_room_code(length=6):
    chars = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(random.choices(chars, k=length))
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1 FROM game_rooms WHERE room_code = :code"), {"code": code}).fetchone()
            if not result:
                return code

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    print(f'Klient połączony: {request.sid}')

@socketio.on('disconnect')
def handle_disconnect():
    print(f'Klient rozłączony: {request.sid}')
    db = next(get_db())
    try:
        # Znajdź gracza
        player = db.execute(text("SELECT id, room_id FROM players WHERE socket_id = :sid"), {"sid": request.sid}).fetchone()
        if player:
            room_id = player.room_id
            db.execute(text("DELETE FROM players WHERE id = :pid"), {"pid": player.id})
            
            # Sprawdź czy pokój jest pusty
            remaining = db.execute(text("SELECT 1 FROM players WHERE room_id = :rid LIMIT 1"), {"rid": room_id}).fetchone()
            if not remaining:
                db.execute(text("UPDATE game_rooms SET is_active = FALSE WHERE id = :rid"), {"rid": room_id})
                print(f"Pokój {room_id} usunięty (pusty).")
            else:
                # Powiadom innych w pokoju
                room_data = db.execute(text("SELECT room_code FROM game_rooms WHERE id = :rid"), {"rid": room_id}).fetchone()
                if room_data:
                    emit('player_left', {'nickname': 'Gracz'}, room=room_data.room_code)
        db.commit()
    except Exception as e:
        print(f"Błąd przy disconnect: {e}")
        db.rollback()

@socketio.on('create_room')
def handle_create_room(nickname):
    if not nickname or len(nickname) > 15:
        emit('error', {'message': 'Nieprawidłowy nick.'})
        return

    room_code = generate_room_code()
    db = next(get_db())
    try:
        # Utwórz pokój
        db.execute(text("""
            INSERT INTO game_rooms (room_code, status, created_at) 
            VALUES (:code, 'lobby', NOW())
        """), {"code": room_code})
        
        room_id = db.execute(text("SELECT id FROM game_rooms WHERE room_code = :code"), {"code": room_code}).scalar()
        
        # Dodaj twórcę jako gracza
        db.execute(text("""
            INSERT INTO players (room_id, nickname, socket_id, score) 
            VALUES (:rid, :nick, :sid, 0)
        """), {"rid": room_id, "nick": nickname, "sid": request.sid})
        
        db.commit()
        join_room(room_code)
        emit('room_created', {'room_code': room_code, 'player_id': request.sid})
        # Pobierz listę graczy (tylko twórca na start)
        players = db.execute(text("SELECT nickname FROM players WHERE room_id = :rid"), {"rid": room_id}).fetchall()
        emit('update_player_list', {'players': [p.nickname for p in players]}, room=room_code)
    except Exception as e:
        print(f"Błąd tworzenia pokoju: {e}")
        db.rollback()
        emit('error', {'message': 'Nie udało się stworzyć pokoju.'})

@socketio.on('join_room')
def handle_join_room(data):
    room_code = data.get('room_code', '').upper()
    nickname = data.get('nickname', '')
    
    if not room_code or not nickname:
        emit('error', {'message': 'Podaj kod i nick.'})
        return

    db = next(get_db())
    try:
        room = db.execute(text("SELECT id, status FROM game_rooms WHERE room_code = :code AND is_active = TRUE"), {"code": room_code}).fetchone()
        
        if not room:
            emit('error', {'message': 'Pokój nie istnieje lub jest nieaktywny.'})
            return
        
        if room.status != 'lobby':
            emit('error', {'message': 'Gra już trwa!'})
            return

        count = db.execute(text("SELECT COUNT(*) FROM players WHERE room_id = :rid"), {"rid": room.id}).scalar()
        if count >= 8:
            emit('error', {'message': 'Pokój jest pełny.'})
            return

        # Dodaj gracza
        db.execute(text("""
            INSERT INTO players (room_id, nickname, socket_id, score) 
            VALUES (:rid, :nick, :sid, 0)
        """), {"rid": room.id, "nick": nickname, "sid": request.sid})
        
        db.commit()
        join_room(room_code)
        emit('joined_room', {'room_code': room_code})
        
        # Odśwież listę graczy dla wszystkich
        players = db.execute(text("SELECT nickname FROM players WHERE room_id = :rid"), {"rid": room.id}).fetchall()
        emit('update_player_list', {'players': [p.nickname for p in players]}, room=room_code)
        emit('player_joined', {'nickname': nickname}, room=room_code)
        
    except Exception as e:
        print(f"Błąd dołączania: {e}")
        db.rollback()
        emit('error', {'message': 'Błąd dołączania do pokoju.'})

@socketio.on('start_game')
def handle_start_game(room_code):
    db = next(get_db())
    try:
        room = db.execute(text("SELECT id FROM game_rooms WHERE room_code = :code"), {"code": room_code}).fetchone()
        if not room: return
        
        letter = random.choice(ALLOWED_LETTERS)
        db.execute(text("""
            UPDATE game_rooms SET status = 'playing', round_letter = :letter, current_round = current_round + 1
            WHERE id = :rid
        """), {"letter": letter, "rid": room.id})
        db.commit()
        
        emit('game_started', {'letter': letter}, room=room_code)
    except Exception as e:
        print(f"Błąd startu gry: {e}")
        db.rollback()

@socketio.on('submit_word')
def handle_submit_word(data):
    room_code = data.get('room_code')
    category = data.get('category')
    word = data.get('word', '').strip()
    
    if not word: return
    
    db = next(get_db())
    try:
        # Znajdź pokój i literę
        room = db.execute(text("SELECT id, round_letter FROM game_rooms WHERE room_code = :code AND status = 'playing'"), {"code": room_code}).fetchone()
        if not room: return
        
        # Znajdź gracza
        player = db.execute(text("SELECT id FROM players WHERE socket_id = :sid AND room_id = :rid"), {"sid": request.sid, "rid": room.id}).fetchone()
        if not player: return
        
        # Walidacja litery
        if word[0].upper() != room.round_letter.upper():
            emit('invalid_word', {'reason': 'Zła litera!'}, room=request.sid)
            return

        # Sprawdź duplikat w tej rundzie
        existing = db.execute(text("""
            SELECT 1 FROM answers 
            WHERE room_id = :rid AND category = :cat AND LOWER(answer) = LOWER(:word)
        """), {"rid": room.id, "cat": category, "word": word}).fetchone()
        
        if existing:
            emit('duplicate_word', {'category': category}, room=request.sid)
            return

        # Zapisz odpowiedź
        db.execute(text("""
            INSERT INTO answers (player_id, room_id, category, answer, submitted_at)
            VALUES (:pid, :rid, :cat, :word, NOW())
        """), {"pid": player.id, "rid": room.id, "cat": category, "word": word.lower()})
        
        db.commit()
        emit('word_submitted', {'category': category, 'word': word}, room=request.sid)
        # Opcjonalnie: powiadom innych, że ktoś odpisał (bez pokazywania słowa)
        # emit('player_responded', {'category': category}, room=room_code)
        
    except Exception as e:
        print(f"Błąd zapisu słowa: {e}")
        db.rollback()

@socketio.on('finish_round')
def handle_finish_round(room_code):
    db = next(get_db())
    try:
        room = db.execute(text("SELECT id FROM game_rooms WHERE room_code = :code"), {"code": room_code}).fetchone()
        if not room: return
        
        # Pobierz wszystkie odpowiedzi
        answers = db.execute(text("""
            SELECT p.nickname, a.category, a.answer
            FROM answers a
            JOIN players p ON a.player_id = p.id
            WHERE a.room_id = :rid
        """), {"rid": room.id}).fetchall()
        
        # Logika punktacji (grupowanie)
        # Struktura: { category: { answer: [nick1, nick2] } }
        grouped = {}
        for row in answers:
            cat = row.category
            ans = row.answer.lower()
            nick = row.nickname
            
            if cat not in grouped: grouped[cat] = {}
            if ans not in grouped[cat]: grouped[cat][ans] = []
            grouped[cat][ans].append(nick)
        
        scores_update = {} # { nick: total_points }
        
        for cat, answers_dict in grouped.items():
            for ans, nicks in answers_dict.items():
                points = 0
                count = len(nicks)
                
                if count == 1:
                    points = 10 # Unikalna
                else:
                    points = 5 # Powtórzona (zgodnie z ostatnią decyzją)
                
                for nick in nicks:
                    scores_update[nick] = scores_update.get(nick, 0) + points

        # Aktualizacja wyników w bazie
        for nick, pts in scores_update.items():
            db.execute(text("""
                UPDATE players SET score = score + :pts WHERE nickname = :nick AND room_id = :rid
            """), {"pts": pts, "nick": nick, "rid": room.id})
        
        db.commit()
        
        # Pobierz aktualne wyniki do wysłania
        final_scores = db.execute(text("""
            SELECT nickname, score FROM players WHERE room_id = :rid ORDER BY score DESC
        """), {"rid": room.id}).fetchall()
        
        scores_dict = {row.nickname: row.score for row in final_scores}
        
        # Wyczyść odpowiedzi z tej rundy
        db.execute(text("DELETE FROM answers WHERE room_id = :rid"), {"rid": room.id})
        db.commit()
        
        emit('round_finished', {'scores': scores_dict}, room=room_code)
        
    except Exception as e:
        print(f"Błąd kończenia rundy: {e}")
        db.rollback()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # debug=False jest wymagane na produkcji
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
