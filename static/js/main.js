// ==================================================================
// == SIGMA WORLD - Wersja Zrefaktoryzowana                        ==
// ==================================================================

// --- Stałe i Stan Globalny ---
// Uwaga: ALL_CATEGORIES jest teraz synchronizowane z backendem (app.py)
// Wartości są duplikowane dla wydajności po stronie klienta
const ALL_CATEGORIES = {
    fixed: ['Państwo', 'Miasto', 'Roślina', 'Zwierzę', 'Imię', 'Rzecz', 'Zawód'],
    optional: [
        'Tytuł książki', 'Tytuł filmu', 'Tytuł piosenki (z autorem)', 'Artysta/Zespół muzyczny', 
        'Wyspa', 'Język', 'Rzeka', 'Morze', 'Góra/pasmo górskie', 'Jezioro', 'Choroba', 'Kolor', 
        'Bohater filmowy (Pełne Imię i Nazwisko lub kryptonim)', 'Tytuł Gry komputerowej', 'Marka samochodu', 
        'Marka odzieżowa', 'Potrawa/Danie', 'Przymiotnik', 'Rzeczownik', 'Czasownik'
    ]
};
const MAX_NICK_LENGTH = 15;
let localPlayer = { id: null, nick: '' };
let gameState = {};
let countdownInterval = null;
let roundTimerInterval = null;

const app = document.getElementById('app');
const socket = io();

// NOWA FUNKCJA: Debounce do optymalizacji wysyłania danych
function debounce(func, delay) {
    let timeout;
    return function(...args) {
        const context = this;
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(context, args), delay);
    };
}

// --- Główna Logika - Odbieranie Wiadomości od Serwera ---

socket.on('connect', () => { localPlayer.id = socket.id; });
socket.on('error', (data) => { alert(`Błąd serwera: ${data.message}`); });
socket.on('game_created', (state) => updateStateAndRender(state));
socket.on('state_update', (state) => updateStateAndRender(state));

socket.on('game_started', (state) => {
    updateStateAndRender(state);
    startRoundTimer(state.round_data.round_end_time); // Uruchomienie licznika globalnego
});

socket.on('next_round', (state) => {
    closeAllModals();
    updateStateAndRender(state);
    startRoundTimer(state.round_data.round_end_time); // Uruchomienie licznika dla kolejnej rundy
});


socket.on('game_over', (state) => {
    closeAllModals();
    renderRankingScreen(state); 
});

socket.on('player_finished', ({ playerId }) => {
    const playerStatus = document.querySelector(`.player-card[data-id="${playerId}"] .status`);
    if(playerStatus) { playerStatus.textContent = 'Zakończył'; playerStatus.classList.add('finished'); }
});

socket.on('start_countdown', ({ endTime }) => {
    const timerDiv = document.getElementById('countdown-timer');
    if (!timerDiv) return;
    timerDiv.style.display = 'block';
    if (countdownInterval) clearInterval(countdownInterval);

    const updateTimer = () => {
        const remaining = Math.round(endTime - (Date.now() / 1000));
        if (remaining > 0) {
            timerDiv.textContent = `Koniec za: ${remaining}s`;
        } else {
            timerDiv.textContent = "Koniec czasu!";
            clearInterval(countdownInterval);
        }
    };
    updateTimer();
    countdownInterval = setInterval(updateTimer, 1000);
});

socket.on('start_verification', (payload) => {
    updateStateAndRender(payload.state);
    renderVerificationScreen(payload.allAnswers);
});

socket.on('round_results', (payload) => {
    updateStateAndRender(payload.state);
    renderResultsModal(payload.detailedResults);
});

// --- Funkcje Zarządzające Stanem i Renderowaniem ---

function updateStateAndRender(newState) {
    gameState = newState;
    renderCurrentScreen();
}

// NOWA FUNKCJA: Zarządza wyświetlaniem globalnego licznika czasu
function startRoundTimer(endTime) {
    const timerDiv = document.getElementById('round-timer');
    if (!timerDiv) return;
    if (roundTimerInterval) clearInterval(roundTimerInterval);

    const updateTimer = () => {
        const remaining = Math.round(endTime - (Date.now() / 1000));
        if (remaining > 0) {
            const minutes = Math.floor(remaining / 60);
            const seconds = remaining % 60;
            timerDiv.textContent = `Czas rundy: ${minutes}:${seconds.toString().padStart(2, '0')}`;
        } else {
            timerDiv.textContent = "Koniec rundy!";
            clearInterval(roundTimerInterval);
        }
    };
    updateTimer();
    roundTimerInterval = setInterval(updateTimer, 1000);
}


function renderCurrentScreen() {
    clearAllTimers();
    const status = gameState.gameState?.status;
    switch (status) {
        case 'lobby':
            renderLobby();
            break;
        case 'in_game':
            renderGame();
            break;
        default:
            if (!status) renderWelcome();
            break;
    }
}

function showScreen(screenElement) {
    app.innerHTML = '';
    app.appendChild(screenElement);
}

// --- Funkcje Renderujące Poszczególne Ekrany ---

function renderWelcome() {
    const screen = document.createElement('div');
    screen.className = 'screen';
    screen.innerHTML = `
        <div class="glass-panel">
            <img src="/static/img/logo_sigma.svg" alt="Logo Sigma World" class="logo-svg">
            <input type="text" id="nick-input" class="input-field" placeholder="Podaj swój nick" maxlength="15">
            <button id="create-game-btn" class="button">Stwórz nową grę</button>
            <div style="display: flex; gap: 10px; width: 100%;"><input type="text" id="join-code-input" class="input-field" placeholder="Wpisz kod gry" style="text-transform: uppercase;"><button id="join-game-btn" class="button">Dołącz</button></div>
        </div>
    `;
    screen.querySelector('#create-game-btn').addEventListener('click', handleCreateGame);
    screen.querySelector('#join-game-btn').addEventListener('click', handleJoinGame);
    showScreen(screen);
}

function renderLobby() {
    const isHost = localPlayer.id === gameState.hostId;
    const screen = document.createElement('div');
    screen.className = 'screen';

    const judgeSelectionOptions = Object.entries(gameState.players).map(([id, player]) => `<option value="${id}" ${id === gameState.judgeId ? 'selected' : ''}>${player.nick}</option>`).join('');
    const playersHTML = Object.entries(gameState.players).map(([id, player]) => {
        const icons = (id === gameState.hostId ? ' 👑' : '') + (id === gameState.judgeId ? ' ⚖️' : '');
        return `<div class="player-card" data-id="${id}">${player.nick} ${icons}<div class="status">Wynik: ${player.score}</div></div>`;
    }).join('');

    let settingsHTML = `<p>Oczekiwanie na rozpoczęcie gry przez hosta...</p>`;
    if (isHost) {
        settingsHTML = `
            <div class="settings-section glass-panel">
                <div class="judge-selector"><label for="judge-select">Wybierz sędziego:</label><select id="judge-select" class="input-field">${judgeSelectionOptions}</select></div>
                <div><label for="rounds-input">Liczba rund: <span id="rounds-value">${gameState.settings.rounds}</span></label><input type="range" id="rounds-input" min="1" max="15" value="${gameState.settings.rounds}" style="width: 100%;"></div>
                <div><label>Dodatkowe kategorie:</label><div class="category-grid">
                    ${ALL_CATEGORIES.optional.map(cat => `<label class="category-toggle"><input type="checkbox" class="category-checkbox" value="${cat}" ${gameState.settings.categories.includes(cat) ? 'checked' : ''}> ${cat}</label>`).join('')}
                </div></div>
            </div>
            <button id="start-game-btn" class="button">Rozpocznij grę</button>`;
    }

    screen.innerHTML = `
        <div class="glass-panel" style="max-width: 600px;">
            <h2>Lobby</h2>
            <div class="game-code-container"><p>Kod dołączenia do gry:</p><div id="game-code" title="Kliknij, aby skopiować">${gameState.roomCode}</div></div>
            <div id="player-list-lobby" class="player-list">${playersHTML}</div>
        </div>
        ${settingsHTML}`;
    
    if (isHost) {
        screen.querySelector('#judge-select')?.addEventListener('change', handleSetJudge);
        screen.querySelector('#rounds-input')?.addEventListener('input', handleSettingsChange);
        screen.querySelectorAll('.category-checkbox')?.forEach(box => box.addEventListener('change', handleSettingsChange));
        screen.querySelector('#start-game-btn')?.addEventListener('click', () => socket.emit('start_game', gameState.roomCode));
    }
    screen.querySelector('#game-code').addEventListener('click', () => navigator.clipboard.writeText(gameState.roomCode).then(() => alert('Kod skopiowany!')));
    showScreen(screen);
}

function renderGame() {
    const screen = document.createElement('div');
    screen.className = 'screen';
    screen.innerHTML = `
        <div id="game-screen-content">
            <div class="game-header">
                <p>Runda <span id="current-round">${gameState.gameState.current_round}</span> / <span id="total-rounds">${gameState.settings.rounds}</span></p>
                <div class="letter" id="game-letter">${gameState.gameState.current_letter}</div>
                <div id="round-timer" class="round-timer"></div>
                <div id="countdown-timer" class="countdown-timer"></div>
            </div>
            <div id="categories-container" class="categories-container">
                ${gameState.settings.categories.map(cat => `
                    <div class="category-input-panel">
                        <label>${cat}</label>
                        <input type="text" class="input-field category-answer" data-category="${cat}">
                    </div>`).join('')}
            </div>
            <button id="end-round-btn" class="button">Koniec Rundy</button>
        </div>`;
    
    const debouncedUpdate = debounce((category, answer) => {
        socket.emit('update_answer', { category, answer });
    }, 300);

    screen.querySelectorAll('.category-answer').forEach(input => {
        input.addEventListener('input', (e) => {
            debouncedUpdate(e.target.dataset.category, e.target.value);
        });
    });

    screen.querySelector('#end-round-btn').addEventListener('click', handleFinishRound);
    showScreen(screen);
}

function renderVerificationScreen(allAnswers) {
    const screen = document.createElement('div');
    screen.className = 'screen';
    const isJudge = localPlayer.id === gameState.judgeId;

    if (isJudge) {
        let verificationHTML = '';
        for (const category of gameState.settings.categories) {
            verificationHTML += `<div class="category-input-panel"><h4>${category}</h4>`;
            for (const [playerId, player] of Object.entries(gameState.players)) {
                const answer = (allAnswers[playerId]?.[category]) || '---';
                verificationHTML += `<label class="category-toggle"><input type="checkbox" class="verification-checkbox" data-player-id="${playerId}" data-category="${category}"><strong>${player.nick}:</strong> ${answer}</label>`;
            }
            verificationHTML += `</div>`;
        }
        screen.innerHTML = `
            <div class="glass-panel" style="max-width: 800px; max-height: 90vh; overflow-y: auto;">
                <h2>Weryfikacja Odpowiedzi</h2><p>Zaznacz wszystkie poprawne odpowiedzi.</p>
                <div class="verification-container">${verificationHTML}</div>
                <button id="submit-verification-btn" class="button">Zatwierdź Oceny</button>
            </div>`;
        screen.querySelector('#submit-verification-btn').addEventListener('click', handleSubmitVerification);
    } else {
        screen.innerHTML = `<div class="glass-panel"><h2>Runda zakończona</h2><p>Oczekiwanie na weryfikację przez sędziego: <strong>${gameState.players[gameState.judgeId].nick}</strong>...</p></div>`;
    }
    showScreen(screen);
}

function renderResultsModal(detailedResults) {
    const isJudge = localPlayer.id === gameState.judgeId;
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    let resultsHTML = '';
    
    const reasonClasses = {
        'jedyna poprawna (+20)': 'reason-jedyna',
        'unikalna (+10)': 'reason-unikalna',
        'powtórzona': 'reason-powtorzona',
        'zła litera': 'reason-zla',
        'odrzucona': 'reason-odrzucona',
        'brak': 'reason-brak'
    };

    for (const category in detailedResults) {
        resultsHTML += `<div class="category-input-panel"><h4>${category}</h4>`;
        detailedResults[category].forEach(res => {
            // Znajdź klasę na podstawie początku tekstu powodu
            let reasonClass = 'reason-brak';
            const reasonLower = res.reason.toLowerCase();
            if (reasonLower.includes('jedyna')) reasonClass = 'reason-jedyna';
            else if (reasonLower.includes('unikalna')) reasonClass = 'reason-unikalna';
            else if (reasonLower.includes('powtórzona')) reasonClass = 'reason-powtorzona';
            else if (reasonLower.includes('zła')) reasonClass = 'reason-zla';
            else if (reasonLower.includes('odrzucona')) reasonClass = 'reason-odrzucona';
            
            resultsHTML += `
                <div class="result-row">
                    <span><strong>${res.nick}:</strong> ${res.answer || '---'}</span>
                    <span class="result-points ${reasonClass}">${res.points} pkt (${res.reason})</span>
                </div>`;
        });
        resultsHTML += `</div>`;
    }

    const judgeControls = isJudge ? `<button id="next-round-btn" class="button">Rozpocznij Następną Rundę</button>` : `<p style="text-align: center; margin-top: 20px; color: var(--secondary-text-color);">Oczekiwanie na sędziego...</p>`;

    modal.innerHTML = `
        <div class="glass-panel" style="max-width: 800px; max-height: 90vh;">
            <div class="modal-header"><h2>Wyniki Rundy ${gameState.gameState.current_round}</h2><button id="close-results-btn" class="close-btn" style="display: none;">×</button></div>
            <div style="overflow-y: auto; padding-right: 15px;">${resultsHTML}</div>
            ${judgeControls}
        </div>`;
    document.body.appendChild(modal);
    
    if (isJudge) {
        modal.querySelector('#next-round-btn').addEventListener('click', () => {
             socket.emit('judge_requests_next_round', { roomCode: gameState.roomCode });
        });
    }
}

function renderRankingScreen(state) {
    const screen = document.createElement('div');
    screen.className = 'screen';
    const isHost = localPlayer.id === state.hostId;

    const sortedPlayers = Object.values(state.players).sort((a, b) => b.score - a.score);

    let rankingHTML = '';
    sortedPlayers.forEach((player, index) => {
        const winnerIcon = index === 0 ? ' 🏆' : '';
        rankingHTML += `<div class="player-card"><strong>${index + 1}. ${player.nick}${winnerIcon}</strong><div class="status">Wynik końcowy: ${player.score}</div></div>`;
    });

    let hostControls = `<p style="text-align:center; color: var(--secondary-text-color);">Poczekaj, aż host zdecyduje co dalej...</p>`;
    if (isHost) {
        hostControls = `
            <div style="display:flex; flex-direction:column; gap:15px; width:100%;">
                <button id="continue-game-btn" class="button">Kontynuuj grę (zachowaj punkty)</button>
                <button id="new-game-btn" class="button" style="background-color:#555;">Zagraj ponownie (nowa gra)</button>
            </div>
        `;
    }

    screen.innerHTML = `
        <div class="glass-panel" style="max-width: 600px;">
            <h2>Koniec Gry!</h2>
            <p style="text-align:center; margin-bottom: 20px;">Oto ostateczny ranking:</p>
            <div class="player-list">${rankingHTML}</div>
        </div>
        <div class="glass-panel" style="max-width: 600px;">
            ${hostControls}
        </div>
    `;

    if (isHost) {
        screen.querySelector('#continue-game-btn').addEventListener('click', () => {
            socket.emit('continue_game', gameState.roomCode);
        });
        screen.querySelector('#new-game-btn').addEventListener('click', () => {
            window.location.reload();
        });
    }

    showScreen(screen);
}


// --- Funkcje Pomocnicze i Wysyłające Zdarzenia ---

function closeAllModals() { document.querySelectorAll('.modal-overlay').forEach(modal => modal.remove()); }
function clearAllTimers() {
    if (countdownInterval) { clearInterval(countdownInterval); countdownInterval = null; }
    if (roundTimerInterval) { clearInterval(roundTimerInterval); roundTimerInterval = null; }
    const countdownTimerDiv = document.getElementById('countdown-timer');
    if (countdownTimerDiv) { countdownTimerDiv.style.display = 'none'; countdownTimerDiv.textContent = ''; }
    const roundTimerDiv = document.getElementById('round-timer');
    if (roundTimerDiv) { roundTimerDiv.textContent = ''; }
}

function handleCreateGame() {
    const nick = document.getElementById('nick-input').value.trim().slice(0, MAX_NICK_LENGTH);
    if (!nick) return alert('Musisz podać swój nick!');
    localPlayer.nick = nick;
    socket.emit('create_game', { nick });
}
function handleJoinGame() {
    const nick = document.getElementById('nick-input').value.trim().slice(0, MAX_NICK_LENGTH);
    const roomCode = document.getElementById('join-code-input').value.trim().toUpperCase();
    if (!nick || !roomCode) return alert('Musisz podać nick i kod gry!');
    localPlayer.nick = nick;
    socket.emit('join_game', { nick, roomCode });
}
function handleSetJudge(event) { socket.emit('set_judge', { roomCode: gameState.roomCode, judgeId: event.target.value }); }
function handleSettingsChange() {
    const rounds = parseInt(document.getElementById('rounds-input').value, 10);
    document.getElementById('rounds-value').textContent = rounds;
    const categories = [...ALL_CATEGORIES.fixed, ...Array.from(document.querySelectorAll('.category-checkbox:checked')).map(box => box.value)];
    socket.emit('update_settings', { roomCode: gameState.roomCode, settings: { rounds, categories } });
}

function handleFinishRound() {
    const endBtn = document.getElementById('end-round-btn');
    if (endBtn) { endBtn.disabled = true; endBtn.textContent = 'Oczekiwanie...'; }
    document.querySelectorAll('.category-answer').forEach(input => { input.disabled = true; });
    socket.emit('finish_round');
}

function handleSubmitVerification() {
    const verifiedAnswers = {};
    document.querySelectorAll('.verification-checkbox').forEach(checkbox => {
        const playerId = checkbox.dataset.playerId;
        const category = checkbox.dataset.category;
        if (!verifiedAnswers[playerId]) verifiedAnswers[playerId] = {};
        verifiedAnswers[playerId][category] = checkbox.checked;
    });
    socket.emit('submit_verification', { roomCode: gameState.roomCode, verifiedAnswers: verifiedAnswers });
    document.getElementById('submit-verification-btn').disabled = true;
    document.getElementById('submit-verification-btn').textContent = 'Wysłano!';
}

// --- Start Aplikacji ---
init();
function init() {
    renderWelcome();
}