# 🚀 Deployment Guide - SIGMA WORLD

## Wybór platformy: **Render.com**

Dlaczego Render?
- ✅ Darmowy plan wystarczający na start
- ✅ Pełna obsługa WebSocket (Socket.IO)
- ✅ Łatwa integracja z PostgreSQL (Supabase lub Render DB)
- ✅ Automatyczny deployment z GitHub
- ✅ Prosta konfiguracja

---

## 📋 Krok 1: Przygotowanie bazy danych (Supabase)

1. Wejdź na [supabase.com](https://supabase.com) i załóż darmowe konto
2. Kliknij **"New Project"**
3. Wypełnij formularz:
   - Nazwa projektu: `sigma-world`
   - Hasło do bazy: (zapisz je!)
   - Region: wybierz najbliższy (np. `Frankfurt` dla Europy)
4. Po utworzeniu projektu:
   - Przejdź do **Settings → Database**
   - Skopiuj **Connection String** (tryb "URI")
   - Będzie wyglądać tak: `postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres`

---

## 📋 Krok 2: Przygotowanie kodu na GitHub

1. Zainicjuj repozytorium Git (jeśli jeszcze nie masz):
   ```bash
   git init
   git add .
   git commit -m "Initial commit - Sigma World ready for deployment"
   ```

2. Stwórz repozytorium na GitHub i wypchnij kod:
   ```bash
   git remote add origin https://github.com/TWOJ_NICK/sigma-world.git
   git branch -M main
   git push -u origin main
   ```

---

## 📋 Krok 3: Deployment na Render

### Opcja A: Render + Supabase (REKOMENDOWANE)

1. Wejdź na [render.com](https://render.com) i załóż konto
2. Kliknij **"New +" → "Web Service"**
3. Podłącz swoje repozytorium GitHub z Sigma World
4. Wypełnij formularz:
   - **Name**: `sigma-world`
   - **Region**: wybierz ten sam co w Supabase (np. `Frankfurt`)
   - **Branch**: `main`
   - **Root Directory**: zostaw puste
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn --worker-class eventlet -w 1 app:app`
   - **Instance Type**: `Free`

5. **Environment Variables** (kliknij "Add Environment Variable"):
   ```
   SECRET_KEY = (wygeneruj losowy ciąg, np. na randomkeygen.com)
   DATABASE_URL = (wklej Connection String z Supabase)
   ```

6. Kliknij **"Create Web Service"**
7. Poczekaj ~3-5 minut na deployment

### Opcja B: Render + Render DB (alternatywa)

1. Podczas tworzenia Web Service, Render może zaproponować utworzenie bazy PostgreSQL
2. Jeśli tak, zaakceptuj i dodaj zmienną środowiskową `DATABASE_URL` automatycznie

---

## 📋 Krok 4: Testowanie

Po zakończeniu deploymentu:
1. Render pokaże URL Twojej aplikacji (np. `https://sigma-world.onrender.com`)
2. Otwórz ten adres w przeglądarce
3. Stwórz nowy pokój i przetestuj grę
4. Wyślij link znajomym!

---

## ⚠️ Ważne uwagi

### Darmowy plan Render ma ograniczenia:
- Aplikacja "usypia" po 15 minutach bez aktywności
- Pierwsze uruchomienie po uśpieniu trwa ~30 sekund
- Limit: 750 godzin miesięcznie (wystarczy na działanie 24/7)

### Jak utrzymać aplikację aktywną?
- Użyj darmowego monitoringu jak [UptimeRobot](https://uptimerobot.com)
- Skonfiguruj pingowanie URL co 5 minut
- To zapobiegnie usypianiu aplikacji

### Bezpieczeństwo:
- `SECRET_KEY` musi być tajny - wygeneruj nowy przed deploymentem
- Nigdy nie commituj pliku `.env` z hasłami do GitHub
- Używaj tylko zmiennych środowiskowych w panelu Render

---

## 🔧 Rozwiązywanie problemów

### Błąd połączenia z bazą danych:
- Sprawdź czy `DATABASE_URL` jest poprawny
- Upewnij się, że Supabase pozwala na połączenia z zewnątrz (Settings → Database → Connection pooling)

### WebSocket nie działa:
- Render domyślnie obsługuje WebSocket
- Sprawdź logs w panelu Render pod kątem błędów

### Gra działa wolno:
- Darmowy plan ma ograniczone zasoby
- Rozważ upgrade do płatnego planu ($7/miesiąc) jeśli grasz często

---

## 🎉 Gotowe!

Twoja aplikacja SIGMA WORLD jest teraz dostępna online 24/7!
Możesz grać ze znajomymi z dowolnego miejsca na świecie.

Powodzenia! 🎮
