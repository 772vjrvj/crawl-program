const ANIMATION_DURATION_SEC = 4;

const youtubeVideoData = [{"video_id":"8kFnA0oxFeI","title":"[자막뉴스] 요즘 초등학교에서 점점 좁아지고 있다는 장소 / KBS 2026.02.05.","channel_title":"KBS News","view_count":4319,"like_count":30,"comment_count":18,"thumbnail_url":"https://i.ytimg.com/vi/8kFnA0oxFeI/maxresdefault.jpg"}];

let sentimentChart = null;

const chartData = {
    pos: 150,
    neg: 100,
    neu: 20
};

const koreanLogs = [
    { type: 'sys', text: '>> [인프라 부팅] 데이터 연동 파이프라인 시동.' },
    { type: 'run', text: '>> [커넥션] 타겟 비디오 검증 완료: [8kFnA0oxFeI]' },
    { type: 'ok',  text: '>> [성공] API 엔드포인트 보안 게이트웨이 인증 패스.' },
    { type: 'run', text: '>> [수집] 원본 댓글 세그먼트 데이터 스트림 실시간 다운로드...' },
    { type: 'ok',  text: '>> [성공] 오디오 모델 가동 - 캡차 문자 해독 완료.' },
    { type: 'run', text: '>> [정제] 마스킹 암호화 트랜잭션 전개.' },
    { type: 'run', text: '>> [인덱싱] 매핑 최적화 부모 트리 구조 빌드 중...' },
    { type: 'sys', text: '>> [자연어 코어] 한국어 토큰 정규화 커널 바인딩.' },
    { type: 'run', text: '>> [텍스트마이닝] 의미어 추출 및 유효 불용어 소거 가동.' },
    { type: 'run', text: '>> [TF-IDF] 단어 가중치 기반 실시간 수치 연산.' },
    { type: 'sys', text: '>> [LLM 엔진] 가상 프롬프트 컨텍스트 스캐닝.' },
    { type: 'ok',  text: '>> [성공] 분석 스크립트 빌드 및 동기화 준비 완수.' }
];

let crawlerInterval = null;
let canvasAnimId = null;

let waveState = {
    currentPercent: 0,
    targetPercent: 0,
    angle: 0,
    bubbles: []
};

document.addEventListener("DOMContentLoaded", () => {
    renderScene1(youtubeVideoData[0]);
    initCanvas();

    document.addEventListener("keydown", (e) => {
        const key = e.key.toLowerCase();
        if (['1', '2', '3', '4'].includes(key)) switchScene(key);
        if (key === 'q') crackEgg('cta-q');
        if (key === 'w') crackEgg('cta-w');
        if (key === 'e') crackEgg('cta-e');
        if (key === 'r') crackEgg('cta-r');
    });
});

function initCanvas() {
    const canvas = document.getElementById('wave-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
}

function switchScene(sceneNumber) {
    clearInterval(crawlerInterval);
    cancelAnimationFrame(canvasAnimId);

    document.getElementById('stage-overlay').style.opacity = '1';
    document.getElementById('stage-overlay').style.pointerEvents = 'auto';
    document.getElementById('clear-popup').classList.remove('show');
    document.getElementById('cylinder-percent').textContent = "0%";

    waveState.currentPercent = 0;
    waveState.targetPercent = 0;
    waveState.angle = 0;
    waveState.bubbles = [];
    initCanvas();

    const allScenes = document.querySelectorAll('.scene');
    allScenes.forEach(scene => scene.classList.remove('active'));

    const targetScene = document.getElementById(`scene-${sceneNumber}`);
    if (targetScene) {
        targetScene.classList.add('active');

        if (sceneNumber === '4') {
            revealIdx.pos = 4; // 5위(인덱스 4)부터 시작
            initRankCards('pos');
        }
        if (sceneNumber === '5') {
            revealIdx.neg = 4; // 5위(인덱스 4)부터 시작
            initRankCards('neg');
        }

        if (sceneNumber === '1') animateNumbers(youtubeVideoData[0]);
        if (sceneNumber === '2') {
            document.getElementById('total-count').textContent = youtubeVideoData[0].comment_count;
            document.getElementById('current-count').textContent = "0";
            document.getElementById('terminal-log').innerHTML = "<div class='log-line sys'>&gt;&gt; SYSTEM READY. INITIALIZE BUTTON...</div>";
        }
        if (sceneNumber === '3') {
            updateSentimentChart(chartData.pos, chartData.neg, chartData.neu);
        }


    }
}

function renderScene1(data) {
    if (!data) return;
    document.getElementById('vid-thumb').src = data.thumbnail_url;
    document.getElementById('vid-title').textContent = data.title;
    document.getElementById('vid-channel').textContent = data.channel_title;
    animateNumbers(data);
}

function crackEgg(id) {
    const target = document.getElementById(id);
    if (target && !target.classList.contains('cracked')) target.classList.add('cracked');
}

function animateNumbers(data) {
    animateValue("vid-views", 0, data.view_count, 1500);
    animateValue("vid-likes", 0, data.like_count, 1500);
    animateValue("vid-comments", 0, data.comment_count, 1500);
}

function animateValue(id, start, end, duration) {
    const obj = document.getElementById(id);
    let startTimestamp = null;
    const step = (timestamp) => {
        if (!startTimestamp) startTimestamp = timestamp;
        const progress = Math.min((timestamp - startTimestamp) / duration, 1);
        const easeOutQuart = 1 - Math.pow(1 - progress, 4);
        const currentVal = Math.floor(easeOutQuart * (end - start) + start);
        obj.innerHTML = currentVal.toLocaleString();
        if (progress < 1) window.requestAnimationFrame(step);
    };
    window.requestAnimationFrame(step);
}

function triggerCrawling() {
    document.getElementById('stage-overlay').style.opacity = '0';
    document.getElementById('stage-overlay').style.pointerEvents = 'none';

    const totalComments = youtubeVideoData[0].comment_count;
    const currentCountObj = document.getElementById('current-count');
    const percentText = document.getElementById('cylinder-percent');
    const terminal = document.getElementById('terminal-log');

    const totalDuration = ANIMATION_DURATION_SEC * 1000;
    const tickRate = 30;
    let elapsed = 0;
    let logIndex = 0;

    terminal.innerHTML = `<div class='log-line sys'>&gt;&gt; MINING ENGINE STARTED [${ANIMATION_DURATION_SEC}s]...</div>`;

    drawWaveLoop();

    crawlerInterval = setInterval(() => {
        elapsed += tickRate;
        let percentage = (elapsed / totalDuration) * 100;
        if (percentage > 100) percentage = 100;

        waveState.targetPercent = percentage;
        percentText.textContent = `${Math.floor(percentage)}%`;

        currentCountObj.textContent = Math.floor((percentage / 100) * totalComments);

        let logTriggerThreshold = (totalDuration / koreanLogs.length) * logIndex;
        if (elapsed >= logTriggerThreshold && logIndex < koreanLogs.length) {
            addLogLine(koreanLogs[logIndex].type, koreanLogs[logIndex].text);
            logIndex++;
        }

        if (elapsed >= totalDuration) {
            clearInterval(crawlerInterval);
            currentCountObj.textContent = totalComments;
            addLogLine('ok', '>> [동기화 완료] SUCCESS. ALL DATA COMMITTED.');
            document.getElementById('clear-popup').classList.add('show');
        }
    }, tickRate);
}

function drawWaveLoop() {
    const canvas = document.getElementById('wave-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;

    waveState.currentPercent += (waveState.targetPercent - waveState.currentPercent) * 0.1;
    waveState.angle += 0.04;

    ctx.clearRect(0, 0, width, height);

    const isFull = waveState.currentPercent >= 99.8;
    const waveAmplitude1 = isFull ? 0 : 7;
    const waveAmplitude2 = isFull ? 0 : 5;

    const fillLevel = isFull ? height : (waveState.currentPercent / 100) * height;
    const yCenter = height - fillLevel;

    if (!isFull && Math.random() < 0.15 && waveState.currentPercent > 5) {
        waveState.bubbles.push({
            x: Math.random() * width,
            y: height + 10,
            size: Math.random() * 3 + 2,
            speed: Math.random() * 1.5 + 1
        });
    }

    ctx.fillStyle = 'rgba(128, 216, 255, 0.5)';
    ctx.beginPath();
    for (let x = 0; x <= width; x++) {
        let y = yCenter + Math.sin(x * 0.025 + waveState.angle) * waveAmplitude1;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.lineTo(width, height);
    ctx.lineTo(0, height);
    ctx.closePath();
    ctx.fill();

    ctx.fillStyle = '#00b0ff';
    ctx.beginPath();
    for (let x = 0; x <= width; x++) {
        let y = yCenter + Math.cos(x * 0.03 + waveState.angle * 1.2) * waveAmplitude2;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.lineTo(width, height);
    ctx.lineTo(0, height);
    ctx.closePath();
    ctx.fill();

    ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
    for (let i = waveState.bubbles.length - 1; i >= 0; i--) {
        let b = waveState.bubbles[i];
        b.y -= b.speed;

        ctx.beginPath();
        ctx.arc(b.x, b.y, b.size, 0, Math.PI * 2);
        ctx.fill();

        if (b.y < yCenter || b.y < 0) {
            waveState.bubbles.splice(i, 1);
        }
    }
    canvasAnimId = requestAnimationFrame(drawWaveLoop);
}

function addLogLine(type, text) {
    const terminal = document.getElementById('terminal-log');
    const line = document.createElement('div');
    line.className = `log-line ${type}`;
    line.innerText = text;
    terminal.appendChild(line);
    terminal.scrollTop = terminal.scrollHeight;
}

function updateSentimentChart(pos, neg, neu) {
    const total = pos + neg + neu || 1;
    const posPerc = Math.round((pos / total) * 100);
    const negPerc = Math.round((neg / total) * 100);
    const neuPerc = Math.round((neu / total) * 100);

    document.getElementById('pos-val').innerHTML = `${posPerc}% (${pos}건)`;
    document.getElementById('neg-val').innerHTML = `${negPerc}% (${neg}건)`;
    document.getElementById('neu-val').innerHTML = `${neuPerc}% (${neu}건)`;

    if (!sentimentChart) {
        sentimentChart = echarts.init(document.getElementById('chart'));
    }

    var option = {
        graphic: [{
            type: 'text',
            left: 'center',
            top: 'middle',
            style: {
                text: `총 ${total}건`,
                font: 'bold 30px Pretendard',
                fill: '#333'
            }
        }],
        series: [{
            type: 'pie',
            radius: ['45%', '75%'], // 기존 도넛 두께
            avoidLabelOverlap: false, // 겹침 방지
            label: {
                show: true,
                position: 'outside', // 라벨 위치
                formatter: '{d}%',
                color: '#000',
                fontSize: 24,
                fontWeight: 'bold'
            },
            // [복원] 기존 스타일 속성 추가
            itemStyle: {
                borderRadius: 12,
                borderColor: '#fff',
                borderWidth: 4
            },
            data: [
                { value: pos, name: '긍정', itemStyle: { color: '#2064b2' } },
                { value: neg, name: '부정', itemStyle: { color: '#ff6b6b' } },
                { value: neu, name: '중립', itemStyle: { color: '#a0a0a0' } }
            ]
        }]
    };
    sentimentChart.setOption(option);
}

const rankData = {
    pos: [
        { "comment_text": "1위 내용", "author_name": "@u1", "sentiment_score": 0.9, "positive_score": 0.9, "negative_score": 0.1, "reason_text": "사유 1" },
        { "comment_text": "2위 내용", "author_name": "@u2", "sentiment_score": 0.8, "positive_score": 0.8, "negative_score": 0.1, "reason_text": "사유 2" },
        { "comment_text": "3위 내용", "author_name": "@u3", "sentiment_score": 0.7, "positive_score": 0.7, "negative_score": 0.1, "reason_text": "사유 3" },
        { "comment_text": "4위 내용", "author_name": "@u4", "sentiment_score": 0.6, "positive_score": 0.6, "negative_score": 0.1, "reason_text": "사유 4" },
        { "comment_text": "5위 내용", "author_name": "@u5", "sentiment_score": 0.5, "positive_score": 0.5, "negative_score": 0.1, "reason_text": "사유 5" }
    ],
    neg: [
        { "comment_text": "1위 내용", "author_name": "@h1", "sentiment_score": -0.9, "positive_score": 0.1, "negative_score": 0.9, "reason_text": "사유 1" },
        { "comment_text": "2위 내용", "author_name": "@h2", "sentiment_score": -0.8, "positive_score": 0.1, "negative_score": 0.8, "reason_text": "사유 2" },
        { "comment_text": "3위 내용", "author_name": "@h3", "sentiment_score": -0.7, "positive_score": 0.1, "negative_score": 0.7, "reason_text": "사유 3" },
        { "comment_text": "4위 내용", "author_name": "@h4", "sentiment_score": -0.6, "positive_score": 0.1, "negative_score": 0.6, "reason_text": "사유 4" },
        { "comment_text": "5위 내용", "author_name": "@h5", "sentiment_score": -0.5, "positive_score": 0.1, "negative_score": 0.5, "reason_text": "사유 5" }
    ]
};

let revealIdx = { pos: 4, neg: 4 };

function showDetail(data) {
    document.getElementById('modal-author').textContent = `작성자: ${data.author_name.substring(0,3)}***`;
    document.getElementById('modal-text').textContent = data.comment_text;
    document.getElementById('modal-score').textContent = data.sentiment_score.toFixed(4);
    document.getElementById('modal-reason').textContent = data.reason_text;

    const modal = document.getElementById('detail-modal');
    modal.style.display = 'flex';

    // X 버튼 생성 로직
    if(!document.querySelector('.close-x')) {
        const x = document.createElement('span');
        x.className = 'close-x'; x.innerHTML = '&times;';
        x.onclick = closeModal;
        document.querySelector('.modal-content').prepend(x);
    }
}

function closeModal() { document.getElementById('detail-modal').style.display = 'none'; }

// 1. 카드 미리 깔기 (DOMContentLoaded 내부 혹은 switchScene 시 실행)
function initRankCards(type) {
    const container = document.getElementById(`${type}-container`);
    container.innerHTML = '';

    // 카드는 5위(ID 4)부터 생성됨
    for (let i = 4; i >= 0; i--) {
        const card = document.createElement('div');
        card.className = `rank-card ${type}`;
        card.id = `${type}-card-${i}`;

        // [수정] ID가 4(5위)면 화면에도 '5위'라고 나오게 수정
        // (5 - i)가 아니라, 카드 ID i가 곧 순위 텍스트가 되도록 매칭
        // 카드 ID 4 -> 5위, 카드 ID 0 -> 1위
        const rankText = (i + 1) + "위";

        card.innerHTML = `<span class="rank-num">${rankText}</span><span class="rank-text">비공개</span>`;
        container.appendChild(card);
    }
}
function addRankCard(type) {
    if (revealIdx[type] < 0) return;

    // 카드는 5위 카드(revealIdx: 4)부터 시작
    const card = document.getElementById(`${type}-card-${revealIdx[type]}`);

    // revealIdx가 4일 때: rankData[type][4] (데이터의 5위 내용)를 가져옴
    // revealIdx가 0일 때: rankData[type][0] (데이터의 1위 내용)를 가져옴
    const data = rankData[type][revealIdx[type]];

    card.classList.add('show');
    card.querySelector('.rank-text').textContent = data.comment_text;
    card.onclick = () => showDetail(data);

    revealIdx[type]--;
}

// 이 아래는 이미 있는 'keydown' 이벤트를 찾아 수정하거나 추가하세요
document.addEventListener("keydown", (e) => {
    const key = e.key.toLowerCase();
    if (['1', '2', '3', '4', '5'].includes(key)) switchScene(key);
    if (key === 'q') crackEgg('cta-q');
    if (key === 'w') crackEgg('cta-w');
    if (key === 'e') crackEgg('cta-e');
    if (key === 'r') crackEgg('cta-r');
    if (key === 'u') {
        const activeScene = document.querySelector('.scene.active').id;
        if (activeScene === 'scene-4') addRankCard('pos');
        if (activeScene === 'scene-5') addRankCard('neg');
    }
});