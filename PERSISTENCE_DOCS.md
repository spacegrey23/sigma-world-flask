# Trwałość Danych i Architektura - Dokumentacja

## 📦 Wdrożone zmiany

### 1. Baza Danych (SQLite/PostgreSQL)

#### Modele:
- **GameRoom** - przechowuje aktywny stan pokoju gry
  - `room_code` - unikalny kod pokoju (indeksowany)
  - `host_id`, `judge_id` - identyfikatory graczy
  - `game_state`, `settings`, `round_data` - dane JSON
  - `created_at`, `updated_at` - timestampy

- **Player** - gracze w pokojach
  - `player_sid` - ID sesji SocketIO
  - `nick`, `score` - dane gracza
  - `room_id` - relacja z GameRoom

- **GameHistory** - historia zakończonych gier
  - `final_scores` - wyniki końcowe (JSON)
  - `total_rounds` - liczba rozegranych rund
  - `categories` - użyte kategorie (JSON)
  - `finished_at` - data zakończenia

#### Funkcje:
- `save_room_to_db(room_code)` - zapisuje/aktualizuje pokój w bazie
- `load_room_from_db(room_code)` - ładuje pokój z bazy do cache
- Automatyczny zapis przy: tworzeniu pokoju, zmianie hosta/sędziego, końcu rundy, końcu gry

### 2. Redis (Opcjonalne)

#### Konfiguracja:
```bash
export REDIS_URL=redis://localhost:6379/0
```

#### Zastosowanie:
- Message queue dla SocketIO (skalowanie poziome)
- Wsparcie dla wielu instancji serwera
- Fallback do trybu single-instance jeśli Redis niedostępny

### 3. Zmiany w Dockerfile

- Usunięto `eventlet` na rzecz `sync` worker
- Lepsza kompatybilność z Flask-SQLAlchemy
- Mniejsze zużycie pamięci

### 4. Zmienne środowiskowe

```bash
SECRET_KEY=twoj-tajny-klucz
DATABASE_URL=sqlite:///sigma_world.db  # lub postgresql://...
REDIS_URL=redis://localhost:6379/0     # opcjonalne
```

## 🔄 Przepływ Danych

### Tworzenie gry:
1. Gracz tworzy pokój → zapis w pamięci (rooms dict)
2. `save_room_to_db()` → zapis do GameRoom i Player tables
3. Emit `game_created` do klienta

### Dołączanie do gry:
1. Gracz dołącza → sprawdzenie w pamięci
2. Jeśli brak w pamięci → `load_room_from_db()` z bazy
3. Aktualizacja rooms dict i graczy

### Podczas gry:
1. Zmiana punktacji → aktualizacja rooms dict
2. `save_room_to_db()` po każdej rundzie
3. Backup w bazie danych

### Koniec gry:
1. Zapis do GameHistory (wyniki, kategorie, rundy)
2. Usunięcie aktywnego pokoju z GameRoom/Player
3. Emit `game_over` do klientów

## 🚀 Skalowanie

### Single Instance (domyślnie):
- SQLite jako baza
- Brak Redis
- Wszystkie połączenia w jednym procesie

### Multi Instance (produkcyjnie):
```bash
export DATABASE_URL=postgresql://user:pass@host/db
export REDIS_URL=redis://redis-cluster:6379
```
- PostgreSQL dla trwałości
- Redis message queue dla SocketIO
- Wiele instancji Gunicorna za load balancerem

## 🧪 Testy

Wszystkie testy jednostkowe zakończone sukcesem:
- ✅ Tworzenie i zapis pokoi
- ✅ Ładowanie z bazy do cache
- ✅ Aktualizacja punktacji
- ✅ Historia gier
- ✅ Cleanup po usunięciu pokoju

## 📝 Przykłady użycia

### Lokalnie z SQLite:
```bash
python app.py
```

### Produkcyjnie z PostgreSQL i Redis:
```bash
export DATABASE_URL=postgresql://user:pass@localhost/sigma
export REDIS_URL=redis://localhost:6379
gunicorn --bind 0.0.0.0:5000 --workers 4 app:app
```

### Docker:
```bash
docker build -t sigma-world .
docker run -p 5000:5000 \
  -e DATABASE_URL=sqlite:///data/sigma.db \
  -v $(pwd)/data:/app/instance \
  sigma-world
```

## 🔒 Bezpieczeństwo Danych

- Sanityzacja wszystkich danych wejściowych
- Transakcje SQL z rollback przy błędach
- Indeksy na często wyszukiwanych polach (room_code)
- Regularne backupy bazy (poza aplikacją)
