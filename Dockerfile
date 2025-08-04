# Krok 1: Wybierz oficjalny, lekki obraz Pythona jako bazę
FROM python:3.11-slim

# Krok 2: Ustaw zmienną środowiskową, aby Python nie buforował outputu
ENV PYTHONUNBUFFERED 1

# Krok 3: Ustaw katalog roboczy wewnątrz kontenera
WORKDIR /app

# Krok 4: Skopiuj plik z zależnościami i zainstaluj je
# Robimy to jako osobny krok, aby Docker mógł wykorzystać cache,
# jeśli zależności się nie zmienią, co przyspiesza przyszłe budowanie
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Krok 5: Skopiuj resztę kodu aplikacji do katalogu roboczego
COPY . .

# Krok 6: Poinformuj Dockera, że aplikacja będzie nasłuchiwać na porcie 5000
# Render automatycznie zmapuje ten port na świat zewnętrzny
EXPOSE 5000

# Krok 7: Zdefiniuj komendę, która uruchomi aplikację, gdy kontener wystartuje
# Używamy Gunicorna z workerem eventlet, tak jak poprzednio
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--worker-class", "eventlet", "-w", "1", "app:app"]