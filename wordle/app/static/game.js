let currentGame = null;
let metricsChart = null;

// --- API calls ---

async function api(path, opts = {}) {
    const res = await fetch(path, {
        headers: { 'Content-Type': 'application/json' },
        ...opts,
    });
    return res.json();
}

async function loadCheckpoints() {
    const data = await api('/api/checkpoints');
    const sel = document.getElementById('checkpoint-select');
    sel.innerHTML = '';

    if (data.has_sft) {
        const opt = document.createElement('option');
        opt.value = 'sft';
        opt.textContent = 'SFT (base)';
        sel.appendChild(opt);
    }

    for (const cp of (data.checkpoints || [])) {
        const opt = document.createElement('option');
        opt.value = cp.name;
        opt.textContent = `Step ${cp.step}`;
        sel.appendChild(opt);
    }

    if (data.error) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = 'Error loading';
        sel.appendChild(opt);
    }
}

async function switchCheckpoint() {
    const sel = document.getElementById('checkpoint-select');
    const step = sel.value;
    if (!step) return;

    setStatus('loading');
    setBtnLoading('switch-btn', true);

    try {
        const data = await api('/api/checkpoint/switch', {
            method: 'POST',
            body: JSON.stringify({ step }),
        });
        setStatus(data.ready ? 'ready' : 'error');
    } catch {
        setStatus('error');
    }

    setBtnLoading('switch-btn', false);
}

async function newGame() {
    const data = await api('/api/game/new', { method: 'POST' });
    currentGame = data;
    renderBoard();
    setMessage('');
    setResponse('');
    document.getElementById('turn-btn').disabled = false;
}

async function nextTurn() {
    if (!currentGame || currentGame.finished) return;

    const btn = document.getElementById('turn-btn');
    setBtnLoading('turn-btn', true);

    try {
        const data = await api('/api/game/turn', {
            method: 'POST',
            body: JSON.stringify({ game_id: currentGame.game_id }),
        });

        if (data.error && !data.last_guess) {
            setMessage(data.error);
            setBtnLoading('turn-btn', false);
            return;
        }

        currentGame = data;
        renderBoard();
        setResponse(data.raw_response || '');

        if (data.won) {
            setMessage(`The model won in ${data.turn} turns!`, 'win');
            btn.disabled = true;
        } else if (data.finished) {
            setMessage(`Game over! The word was "${data.secret_word}"`, 'lose');
            btn.disabled = true;
        }
    } catch (e) {
        setMessage('Error: ' + e.message);
    }

    setBtnLoading('turn-btn', false);
}

// --- Rendering ---

function renderBoard() {
    const board = document.getElementById('board');
    board.innerHTML = '';

    for (let row = 0; row < 6; row++) {
        const rowDiv = document.createElement('div');
        rowDiv.className = 'board-row';

        for (let col = 0; col < 5; col++) {
            const tile = document.createElement('div');
            tile.className = 'tile';

            if (currentGame && row < currentGame.guesses.length) {
                const letter = currentGame.guesses[row][col];
                const status = currentGame.feedback[row][col].status;
                tile.textContent = letter;
                tile.classList.add(status);
                // Stagger animation
                tile.style.animationDelay = `${col * 0.1}s`;
            }

            rowDiv.appendChild(tile);
        }

        board.appendChild(rowDiv);
    }
}

function setMessage(text, type = '') {
    const el = document.getElementById('game-message');
    el.textContent = text;
    el.className = 'game-message' + (type ? ' ' + type : '');
}

function setResponse(text) {
    const el = document.getElementById('response-text');
    el.textContent = text || '(no response yet)';
}

function setStatus(state) {
    const dot = document.getElementById('status-dot');
    dot.className = 'status-dot ' + state;
}

function setBtnLoading(id, loading) {
    const btn = document.getElementById(id);
    if (loading) {
        btn.disabled = true;
        btn._origText = btn.textContent;
        btn.innerHTML = '<span class="spinner"></span>';
    } else {
        btn.disabled = false;
        btn.textContent = btn._origText || btn.textContent;
    }
}

function toggleResponse() {
    const el = document.getElementById('response-text');
    el.classList.toggle('open');
    const toggle = document.getElementById('response-toggle');
    toggle.textContent = el.classList.contains('open')
        ? '▼ Hide model response'
        : '▶ Show model response';
}

// --- Chart ---

async function loadMetrics() {
    const data = await api('/api/metrics');
    if (!data.steps || data.steps.length === 0) return;

    const ctx = document.getElementById('metrics-chart');
    if (!ctx) return;

    if (metricsChart) metricsChart.destroy();

    metricsChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.steps,
            datasets: [
                {
                    label: 'Avg Reward',
                    data: data.rewards,
                    borderColor: '#6aaa64',
                    backgroundColor: 'rgba(106,170,100,0.1)',
                    tension: 0.3,
                    fill: true,
                },
                {
                    label: 'Win Rate',
                    data: data.win_rates,
                    borderColor: '#c9b458',
                    backgroundColor: 'rgba(201,180,88,0.1)',
                    tension: 0.3,
                    fill: true,
                    yAxisID: 'y1',
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            scales: {
                x: {
                    title: { display: true, text: 'Training Step', color: '#787c7e' },
                    ticks: { color: '#787c7e' },
                    grid: { color: 'rgba(120,124,126,0.2)' },
                },
                y: {
                    title: { display: true, text: 'Reward', color: '#6aaa64' },
                    ticks: { color: '#6aaa64' },
                    grid: { color: 'rgba(120,124,126,0.2)' },
                },
                y1: {
                    position: 'right',
                    title: { display: true, text: 'Win Rate', color: '#c9b458' },
                    ticks: { color: '#c9b458' },
                    grid: { display: false },
                    min: 0,
                    max: 1,
                },
            },
            plugins: {
                legend: { labels: { color: '#d7dadc' } },
            },
        },
    });
}

// --- Init ---

document.addEventListener('DOMContentLoaded', () => {
    loadCheckpoints();
    loadMetrics();
    renderBoard();

    // Refresh checkpoints and metrics periodically
    setInterval(loadCheckpoints, 60000);
    setInterval(loadMetrics, 60000);
});
