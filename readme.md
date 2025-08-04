# SIGMA WORLD (Wersja Serwerowa) - Instrukcja Instalacji i Uruchomienia

Ta wersja gry używa serwera napisanego w języku Python, co zapewnia jej stabilność i niezawodność. Aby ją uruchomić, należy jednorazowo skonfigurować środowisko na komputerze, który będzie pełnił rolę serwera (np. na Twoim laptopie Alienware).

Postępuj zgodnie z poniższymi krokami.

### Krok 1: Instalacja Pythona

1.  Pobierz instalator Pythona ze strony: **[https://www.python.org/downloads/](https://www.python.org/downloads/)**
2.  Uruchom pobrany plik.
3.  **BARDZO WAŻNE:** W pierwszym oknie instalatora zaznacz na samym dole pole **"Add Python to PATH"**.
4.  Następnie kliknij **"Install Now"** i poczekaj na zakończenie instalacji.

### Krok 2: Przygotowanie Projektu

1.  Umieść wszystkie pliki gry w jednym folderze, np. `C:\Users\TwojaNazwa\Desktop\sigma-world-flask`.
2.  Otwórz **Wiersz Polecenia (CMD)**. Możesz go znaleźć, wpisując "cmd" w menu Start.
3.  W czarnym oknie Wiersza Polecenia przejdź do folderu z grą, wpisując komendę `cd` i ścieżkę do folderu, np.:
    ``` cd C:\Users\TwojaNazwa\Desktop\sigma-world-flask ```
    i naciśnij Enter.

### Krok 3: Instalacja Wymaganych Bibliotek

Będąc w folderze projektu w Wierszu Polecenia, wpisz po kolei poniższe komendy, naciskając Enter po każdej z nich:

1.  ``` python -m venv venv ```
    *(Tworzy to "wirtualne środowisko", czyli czystą przestrzeń dla naszego projektu)*

3.  ``` venv\Scripts\activate ```
    *(Aktywuje to środowisko. Na początku wiersza powinna pojawić się nazwa `(venv)`)*

4.  ``` pip install -r requirements.txt ```
    *(Instaluje to wszystkie biblioteki z pliku `requirements.txt` - Flask, SocketIO i Eventlet)*

Te trzy komendy wykonujesz **tylko raz**.

### Krok 4: Uruchomienie Serwera Gry

Za każdym razem, gdy chcesz uruchomić grę, wykonaj poniższe kroki:

1.  Otwórz Wiersz Polecenia i przejdź do folderu z grą (jak w Kroku 2).
2.  Aktywuj środowisko komendą: ``` venv\Scripts\activate ```
3.  Uruchom serwer komendą: ``` python app.py ```

Jeśli wszystko poszło dobrze, zobaczysz tekst informujący, że serwer działa, np. `Server initialized for eventlet...` oraz `Listening on http://127.0.0.1:5000`. **Nie zamykaj tego okna!** Serwer musi być cały czas włączony.

### Krok 5: Jak Dołączyć do Gry

1.  **Ty (na komputerze z serwerem):** Otwórz przeglądarkę i wejdź na adres `http://127.0.0.1:5000` lub `http://localhost:5000`.
2.  **Inni gracze (na telefonach):**
    * Muszą być podłączeni do **tej samej sieci WiFi** co Twój komputer.
    * Muszą poznać **lokalny adres IP Twojego komputera**. Aby go znaleźć, otwórz **nowy** Wiersz Polecenia i wpisz `ipconfig`. Znajdź sekcję "Wireless LAN adapter Wi-Fi" i poszukaj adresu przy "IPv4 Address" (np. `192.168.1.15`).
    * W przeglądarkach na swoich telefonach muszą wpisać ten adres wraz z portem, np. `http://192.168.1.4:5000`.

Gra jest gotowa!
