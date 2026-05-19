# 🎮 SIGMA WORLD - Cyfrowa wersja gry "Państwa-Miasta"

Aplikacja internetowa do gry wieloosobowej w czasie rzeczywistym. Gracze wpisują słowa zaczynające się na daną literę w różnych kategoriach.

## 🚀 Szybki Start - Deployment Online

Aplikacja jest przygotowana do deploymentu na platformie **Render.com** z bazą danych **Supabase**.

### Pełna instrukcja krok po kroku:

👉 **[Zobacz DEPLOYMENT.md](DEPLOYMENT.md)**

### Podsumowanie w 3 krokach:

1. **Stwórz bazę danych w Supabase** (darmowe)
2. **Wypchnij kod na GitHub**
3. **Zdeployuj na Render.com** podłączając repozytorium i zmienne środowiskowe

Po deploymentzie aplikacja będzie dostępna pod adresem typu `https://sigma-world.onrender.com` - możesz grać ze znajomymi z dowolnego miejsca!

---

## 🛠️ Uruchomienie Lokalne (dla deweloperów)

Jeśli chcesz uruchomić aplikację lokalnie w celach testowych:

### Wymagania
- Python 3.8+
- pip

### Instalacja

```bash
# Sklonuj repozytorium
git clone <URL_TWOJEGO_REPOZYTORIUM>
cd sigma-world

# Utwórz wirtualne środowisko
python -m venv venv

# Aktywuj środowisko
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Zainstaluj zależności
pip install -r requirements.txt
```

### Uruchomienie

```bash
# Opcjonalnie: utwórz plik .env z konfiguracją
cp .env.example .env

# Uruchom serwer
python app.py
```

Aplikacja będzie dostępna pod `http://127.0.0.1:5000`

---

## ⚙️ Zmienne Środowiskowe

| Nazwa | Opis | Przykład |
|-------|------|----------|
| `SECRET_KEY` | Klucz sesji Flask | `wylosuj-dowolny-ciag` |
| `DATABASE_URL` | URL bazy PostgreSQL (Supabase) | `postgresql://user:pass@host:5432/db` |
| `REDIS_URL` | URL Redis (opcjonalne) | `redis://localhost:6379` |

---

## 📋 Funkcje

- ✅ Gra wieloosobowa w czasie rzeczywistym (WebSocket)
- ✅ System punktacji za unikalne odpowiedzi
- ✅ Losowanie liter (bez X, Y i polskich znaków)
- ✅ Konfigurowalne kategorie
- ✅ Timer rundy i odliczanie
- ✅ Responsywny design (mobile-friendly)
- ✅ Tryb jasny/ciemny
- ✅ Trwała baza danych (PostgreSQL)

---

## 🏗️ Architektura

- **Backend**: Python + Flask + Flask-SocketIO
- **Baza danych**: PostgreSQL (Supabase) / SQLite (lokalnie)
- **Frontend**: HTML5, CSS3, JavaScript (Vanilla)
- **Serwer**: Gunicorn + Eventlet
- **Hosting**: Render.com

---

## 📄 Licencja

Projekt stworzony do użytku prywatnego ze znajomymi.
