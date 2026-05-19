import os
import random
import string
from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, leave_room, emit
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError("Brak zmiennej środowiskowej DATABASE_URL")

# Konwersja URL dla psycopg2 (jeśli Render doda prefix postgresql://)
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgres://", 1)

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

CATEGORIES_LIST = ["Imię", "Miasto", "Kolor", "Zwierzę", "Roślina", "Przedmiot", "Zawód", "Potrawa"]
ALLOWED_LETTERS = "AĄBCĆDEĘFGHIJKLŁMNŃOÓPQRSŚTUVWXYZŹŻ"

def generate_room_code(length=6):
    chars = string.ascii_uppercase + string.digits
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    while True:
        code = ''.join(random.choices(chars, k=length))
        cur.execute("SELECT 1 FROM game_rooms WHERE room_code = %s", (code,))
        if not cur.fetchone():
            conn.close()
            return code
    conn.close()

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    print(f'Klient połączony: {request.sid}')

@socketio.on('disconnect')
def handle_disconnect():
    print(f'Klient rozłączony: {request.sid}')
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, room_id FROM players WHERE socket_id = %s", (request.sid,))
        player = cur.fetchone()
        
        if player:
            room_id = player['room_id']
            cur.execute("DELETE FROM players WHERE id = %s", (player['id'],))
            
            cur.execute("SELECT 1 FROM players WHERE room_id = %s LIMIT 1", (room_id,))
            remaining = cur.fetchone()
            
            if not remaining:
                cur.execute("UPDATE game_rooms SET is_active = FALSE WHERE id = %s", (room_id,))
            else:
                cur.execute("SELECT room_code FROM game_rooms WHERE id = %s", (room_id,))
                room_data = cur.fetchone()
                if room_data:
                    emit('player_left', {'nickname': 'Gracz'}, room=room_data['room_code'])
            
            conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Błąd przy disconnect: {e}")

@socketio.on('create_room')
def handle_create_room(nickname):
    if not nickname or len(nickname) > 15:
        emit('error', {'message': 'Nieprawidłowy nick.'})
        return

    room_code = generate_room_code()
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            INSERT INTO game_rooms (room_code, status, created_at) 
            VALUES (%s, 'lobby', NOW())
        """, (room_code,))
        
        cur.execute("SELECT id FROM game_rooms WHERE room_code = %s", (room_code,))
        room_id = cur.fetchone()['id']
        
        cur.execute("""
            INSERT INTO players (room_id, nickname, socket_id, score) 
            VALUES (%s, %s, %s, 0)
        """, (room_id, nickname, request.sid))
        
        conn.commit()
        cur.close()
        conn.close()
        
        join_room(room_code)
        emit('room_created', {'room_code': room_code, 'player_id': request.sid})
        
        # Odśwież listę graczy
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT nickname FROM players WHERE room_id = %s", (room_id,))
        players = [p['nickname'] for p in cur.fetchall()]
        cur.close()
        conn.close()
        
        emit('update_player_list', {'players': players}, room=room_code)
        
    except Exception as e:
        print(f"Błąd tworzenia pokoju: {e}")
        emit('error', {'message': 'Nie udało się stworzyć pokoju.'})

@socketio.on('join_room')
def handle_join_room(data):
    room_code = data.get('room_code', '').upper()
    nickname = data.get('nickname', '')
    if not room_code or not nickname:
        emit('error', {'message': 'Podaj kod i nick.'})
        return

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT id, status FROM game_rooms WHERE room_code = %s AND is_active = TRUE", (room_code,))
        room = cur.fetchone()
        
        if not room:
            cur.close()
            conn.close()
            emit('error', {'message': 'Pokój nie istnieje lub jest nieaktywny.'})
            return
            
        if room['status'] != 'lobby':
            cur.close()
            conn.close()
            emit('error', {'message': 'Gra już trwa!'})
            return
            
        cur.execute("SELECT COUNT(*) as count FROM players WHERE room_id = %s", (room['id'],))
        count = cur.fetchone()['count']
        
        if count >= 8:
            cur.close()
            conn.close()
            emit('error', {'message': 'Pokój jest pełny.'})
            return

        cur.execute("""
            INSERT INTO players (room_id, nickname, socket_id, score) 
            VALUES (%s, %s, %s, 0)
        """, (room['id'], nickname, request.sid))
        
        conn.commit()
        cur.close()
        conn.close()
        
        join_room(room_code)
        emit('joined_room', {'room_code': room_code})
        
        # Odśwież listę
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT nickname FROM players WHERE room_id = %s", (room['id'],))
        players = [p['nickname'] for p in cur.fetchall()]
        cur.close()
        conn.close()
        
        emit('update_player_list', {'players': players}, room=room_code)
        emit('player_joined', {'nickname': nickname}, room=room_code)
        
    except Exception as e:
        print(f"Błąd dołączania: {e}")
        emit('error', {'message': 'Błąd dołączania do pokoju.'})

@socketio.on('start_game')
def handle_start_game(room_code):
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT id FROM game_rooms WHERE room_code = %s", (room_code,))
        room = cur.fetchone()
        if not room:
            cur.close()
            conn.close()
            return
            
        letter = random.choice(ALLOWED_LETTERS)
        
        cur.execute("""
            UPDATE game_rooms 
            SET status = 'playing', round_letter = %s, current_round = current_round + 1
            WHERE id = %s
        """, (letter, room['id']))
        
        conn.commit()
        cur.close()
        conn.close()
        
        emit('game_started', {'letter': letter}, room=room_code)
    except Exception as e:
        print(f"Błąd startu gry: {e}")

@socketio.on('submit_word')
def handle_submit_word(data):
    room_code = data.get('room_code')
    category = data.get('category')
    word = data.get('word', '').strip()
    if not word: return

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT id, round_letter FROM game_rooms WHERE room_code = %s AND status = 'playing'", (room_code,))
        room = cur.fetchone()
        if not room:
            cur.close()
            conn.close()
            return
            
        cur.execute("SELECT id FROM players WHERE socket_id = %s AND room_id = %s", (request.sid, room['id']))
        player = cur.fetchone()
        if not player:
            cur.close()
            conn.close()
            return
            
        if word[0].upper() != room['round_letter'].upper():
            cur.close()
            conn.close()
            emit('invalid_word', {'reason': 'Zła litera!'}, room=request.sid)
            return

        cur.execute("""
            SELECT 1 FROM answers 
            WHERE room_id = %s AND category = %s AND LOWER(answer) = LOWER(%s)
        """, (room['id'], category, word))
        
        if cur.fetchone():
            cur.close()
            conn.close()
            emit('duplicate_word', {'category': category}, room=request.sid)
            return

        cur.execute("""
            INSERT INTO answers (player_id, room_id, category, answer, submitted_at)
            VALUES (%s, %s, %s, %s, NOW())
        """, (player['id'], room['id'], category, word.lower()))
        
        conn.commit()
        cur.close()
        conn.close()
        
        emit('word_submitted', {'category': category, 'word': word}, room=request.sid)
    except Exception as e:
        print(f"Błąd zapisu słowa: {e}")

@socketio.on('finish_round')
def handle_finish_round(room_code):
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT id FROM game_rooms WHERE room_code = %s", (room_code,))
        room = cur.fetchone()
        if not room:
            cur.close()
            conn.close()
            return
            
        cur.execute("""
            SELECT p.nickname, a.category, a.answer
            FROM answers a
            JOIN players p ON a.player_id = p.id
            WHERE a.room_id = %s
        """, (room['id'],))
        
        answers = cur.fetchall()
        
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
                points = 5 if len(nicks) > 1 else 10
                for nick in nicks:
                    scores_update[nick] = scores_update.get(nick, 0) + points

        for nick, pts in scores_update.items():
            cur.execute("""
                UPDATE players SET score = score + %s WHERE nickname = %s AND room_id = %s
            """, (pts, nick, room['id']))
        
        conn.commit()
        
        cur.execute("""
            SELECT nickname, score FROM players WHERE room_id = %s ORDER BY score DESC
        """, (room['id'],))
        final_scores_rows = cur.fetchall()
        scores_dict = {row['nickname']: row['score'] for row in final_scores_rows}

        cur.execute("DELETE FROM answers WHERE room_id = %s", (room['id'],))
        conn.commit()
        cur.close()
        conn.close()

        emit('round_finished', {'scores': scores_dict}, room=room_code)
    except Exception as e:
        print(f"Błąd kończenia rundy: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
