import time
import random
import string
from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, leave_room, emit

# --- Konfiguracja Aplikacji ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'sigma-world-final-refactored-key'
socketio = SocketIO(app, async_mode='eventlet')

random.seed()

# --- Globalny Stan Serwera ---
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
ALPHABET = 'ABCDEFGHIKLMNOPRSTUWZ'
COUNTDOWN_SECONDS = 30
# NOWA STAŁA: Globalny limit czasowy na rundę w sekundach
ROUND_TIME_LIMIT_SECONDS = 300 

# --- Funkcje Pomocnicze ---
def find_room_by_sid(sid):
    for code, room in rooms.items():
        if sid in room['players']:
            return code, room
    return None, None

def generate_room_code(length=4):
    """Generuje unikalny kod pokoju."""
    while True:
        code = ''.join(random.choices(string.ascii_uppercase, k=length))
        if code not in rooms:
            return code

def get_room_state(room_code):
    """Zwraca bezpieczną kopię stanu pokoju do wysłania klientom."""
    if room_code not in rooms:
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
    nick = data.get('nick', 'Gracz bezimienny')
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
    
    emit('game_created', get_room_state(room_code))
    print(f"Pokój '{room_code}' stworzony przez gracza {nick} ({player_id}).")

@socketio.on('join_game')
def handle_join_game(data):
    """Dodaje gracza do istniejącego pokoju."""
    player_id = request.sid
    nick = data.get('nick', 'Gracz bezimienny')
    room_code = data.get('roomCode', '').upper()
    
    if room_code not in rooms:
        return emit('error', {'message': 'Pokój o podanym kodzie nie istnieje.'})
        
    join_room(room_code)
    rooms[room_code]["players"][player_id] = {"nick": nick, "score": 0}
    emit('state_update', get_room_state(room_code), to=room_code)
    print(f"Gracz {nick} ({player_id}) dołączył do pokoju '{room_code}'.")

@socketio.on('disconnect')
def handle_disconnect():
    """Obsługuje odłączenie gracza, czyszczenie i ewentualną zmianę hosta/sędziego."""
    player_id = request.sid
    code, room = find_room_by_sid(player_id)
    if room:
        print(f"Gracz {room['players'][player_id]['nick']} ({player_id}) opuścił pokój '{code}'.")
        del room['players'][player_id]
        
        if not room['players']:
            del rooms[code]
            print(f"Pokój '{code}' jest pusty i został usunięty.")
            return
        
        if player_id == room['host_id']:
            new_host_id = next(iter(room['players']))
            room['host_id'] = new_host_id
            print(f"Nowy host w pokoju '{code}' to {room['players'][new_host_id]['nick']}.")
        
        if player_id == room['judge_id']:
            room['judge_id'] = room['host_id']
            print(f"Nowy sędzia w pokoju '{code}' to {room['players'][room['host_id']]['nick']}.")
        
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
        round_end_time = time.time() + ROUND_TIME_LIMIT_SECONDS # Czas końca globalnego timera
        room['round_data'] = {
            "answers": {}, 
            "finished_players": set(), 
            "timer_end_time": None,
            "round_end_time": round_end_time # Zapisujemy czas końca rundy
        }
        for player_id in room['players']:
            room['round_data']['answers'][player_id] = {}
            
        emit('game_started', get_room_state(room_code), to=room_code)
        # Uruchomienie globalnego timera rundy w tle
        socketio.start_background_task(target=enforce_round_time_limit, room_code=room_code, expected_round=1)
        print(f"Gra w pokoju '{room_code}' rozpoczęta. Limit czasu: {ROUND_TIME_LIMIT_SECONDS}s.")

# NOWA FUNKCJA: Pilnuje globalnego limitu czasu na rundę
def enforce_round_time_limit(room_code, expected_round):
    """Zadanie w tle, które pilnuje, by cała runda zakończyła się po upływie czasu."""
    if room_code not in rooms: return
    
    end_time = rooms[room_code].get('round_data', {}).get('round_end_time')
    if end_time and end_time > time.time():
        socketio.sleep(end_time - time.time())
    
    if room_code in rooms and rooms[room_code]['game_state']['current_round'] == expected_round and rooms[room_code]['game_state']['status'] == 'in_game':
        print(f"Globalny czas na rundę ({ROUND_TIME_LIMIT_SECONDS}s) minął w pokoju '{room_code}'. Wymuszam koniec.")
        start_verification(room_code)


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

    room['round_data']['finished_players'].add(player_id)
    emit('player_finished', {"playerId": player_id}, to=room_code)
    
    all_players_finished = len(room['round_data']['finished_players']) == len(room['players'])
    is_first_player = len(room['round_data']['finished_players']) == 1

    if is_first_player and not all_players_finished:
        end_time = time.time() + COUNTDOWN_SECONDS
        room['round_data']['timer_end_time'] = end_time
        emit('start_countdown', {'endTime': end_time}, to=room_code)
        socketio.start_background_task(target=enforce_countdown, room_code=room_code, expected_round=room['game_state']['current_round'])
        print(f"Start odliczania w pokoju '{room_code}'.")
    elif all_players_finished:
        room['round_data']['timer_end_time'] = None 
        start_verification(room_code)

def enforce_countdown(room_code, expected_round):
    """Zadanie w tle, które pilnuje, by runda zakończyła się po upływie czasu."""
    if room_code not in rooms: return
    end_time = rooms[room_code].get('round_data', {}).get('timer_end_time')
    
    if end_time and end_time > time.time():
        socketio.sleep(end_time - time.time())
    
    if room_code in rooms and rooms[room_code]['game_state']['current_round'] == expected_round and rooms[room_code]['game_state']['status'] == 'in_game':
        print(f"Czas minął w pokoju '{room_code}'. Wymuszam koniec rundy.")
        start_verification(room_code)

def start_verification(room_code):
    """Przygotowuje i wysyła dane do ekranu weryfikacji sędziego."""
    if room_code not in rooms: return
    if rooms[room_code]['game_state']['status'] != 'in_game': return

    room = rooms[room_code]
    
    all_player_answers = room['round_data'].get('answers', {}).copy()
    for player_id in room['players']:
        all_player_answers.setdefault(player_id, {})
    
    room['game_state']['status'] = 'verification'
    verification_payload = {"state": get_room_state(room_code), "allAnswers": all_player_answers}
    socketio.emit('start_verification', verification_payload, to=room_code)
    print(f"Przechodzę do weryfikacji w pokoju '{room_code}'.")

@socketio.on('submit_verification')
def handle_submit_verification(data):
    """Przyjmuje werdykt sędziego i uruchamia liczenie punktów."""
    if data['roomCode'] in rooms and rooms[data['roomCode']]['judge_id'] == request.sid:
        calculate_and_send_results(data['roomCode'], data.get('verifiedAnswers'))

def calculate_and_send_results(room_code, verified_answers):
    """Oblicza punkty i wysyła wyniki."""
    room = rooms[room_code]
    letter = room['game_state']['current_letter'].lower()
    all_player_answers = room['round_data'].get('answers', {})
    detailed_results = {}

    for category in room['settings']['categories']:
        detailed_results[category] = []
        
        valid_answers = {}
        for p_id in room['players']:
            answer = all_player_answers.get(p_id, {}).get(category, "").strip()
            is_verified = verified_answers.get(p_id, {}).get(category, False)
            if answer and answer.lower().startswith(letter) and is_verified:
                valid_answers[p_id] = answer.lower()
        
        answer_counts = {}
        for answer in valid_answers.values():
            answer_counts[answer] = answer_counts.get(answer, 0) + 1

        for p_id, p_data in room['players'].items():
            answer = all_player_answers.get(p_id, {}).get(category, "").strip()
            points, reason = 0, "Brak"
            
            if p_id in valid_answers:
                if len(valid_answers) == 1:
                    points, reason = 15, "Jedyna poprawna"
                else:
                    if answer_counts[valid_answers[p_id]] == 1:
                        points, reason = 10, "Unikalna"
                    else:
                        points, reason = 5, "Powtórzona"
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
    results_payload = {"state": get_room_state(room_code), "detailedResults": detailed_results}
    socketio.emit('round_results', results_payload, to=room_code)
    print(f"Wyniki rundy {room['game_state']['current_round']} wysłane do pokoju '{room_code}'.")


@socketio.on('judge_requests_next_round')
def handle_judge_requests_next_round(data):
    """Uruchamia następną rundę lub kończy grę na żądanie sędziego."""
    room_code = data.get('roomCode')
    if room_code not in rooms or rooms[room_code]['judge_id'] != request.sid:
        return

    room = rooms[room_code]
    
    if room['game_state']['current_round'] >= room['settings']['rounds']:
        room['game_state']['status'] = 'game_over'
        socketio.emit('game_over', get_room_state(room_code), to=room_code)
        print(f"Koniec gry w pokoju '{room_code}'.")
    else:
        next_round_number = room['game_state']['current_round'] + 1
        room['game_state']['status'] = 'in_game'
        room['game_state']['current_round'] = next_round_number
        room['game_state']['current_letter'] = random.choice(ALPHABET)
        round_end_time = time.time() + ROUND_TIME_LIMIT_SECONDS
        room['round_data'] = {
            "answers": {}, 
            "finished_players": set(), 
            "timer_end_time": None,
            "round_end_time": round_end_time
        }
        for player_id in room['players']:
            room['round_data']['answers'][player_id] = {}

        socketio.emit('next_round', get_room_state(room_code), to=room_code)
        # Uruchomienie globalnego timera dla KOLEJNEJ rundy
        socketio.start_background_task(target=enforce_round_time_limit, room_code=room_code, expected_round=next_round_number)
        print(f"Sędzia rozpoczął następną rundę ({next_round_number}) w pokoju '{room_code}'.")


@socketio.on('continue_game')
def handle_continue_game(room_code):
    """Resetuje grę do lobby, ZACHOWUJĄC punkty graczy."""
    if room_code in rooms and rooms[room_code]['host_id'] == request.sid:
        room = rooms[room_code]
        room['game_state'] = {"status": "lobby", "current_round": 0, "current_letter": ""}
        room['round_data'] = {}
        emit('state_update', get_room_state(room_code), to=room_code)
        print(f"Gra w pokoju '{room_code}' kontynuowana (powrót do lobby z zachowaniem punktów).")

# --- Uruchomienie Serwera ---
if __name__ == '__main__':
    print("Serwer SIGMA WORLD uruchomiony. Otwórz przeglądarkę i wejdź na http://127.0.0.1:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)