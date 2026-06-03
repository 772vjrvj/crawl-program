// ⏱️ [시간 설정 제어 컨트롤러] 원하는 애니메이션 타임(초 단위)을 수정하세요.
const ANIMATION_DURATION_SEC = 4;

const youtubeVideoData = [{"video_id":"8kFnA0oxFeI","title":"[자막뉴스] 요즘 초등학교에서 점점 좁아지고 있다는 장소 / KBS 2026.02.05.","channel_title":"KBS News","view_count":4319,"like_count":30,"comment_count":18,"thumbnail_url":"https://i.ytimg.com/vi/8kFnA0oxFeI/maxresdefault.jpg"}];

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

// 유체 웨이브 그래픽용 글로벌 상태 스토리지
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

    // 리셋 초기화
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
        if (sceneNumber === '1') animateNumbers(youtubeVideoData[0]);
        if (sceneNumber === '2') {
            document.getElementById('total-count').textContent = youtubeVideoData[0].comment_count;
            document.getElementById('current-count').textContent = "0";
            document.getElementById('terminal-log').innerHTML = "<div class='log-line sys'>&gt;&gt; SYSTEM READY. INITIALIZE BUTTON...</div>";
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

// ===================================================
// 🌊 [Scene 2] 자연스러운 사인파 기반 캔버스 애니메이션 코어
// ===================================================
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

    // 실시간 유체 드로잉 루프 가동
    drawWaveLoop();

    crawlerInterval = setInterval(() => {
        elapsed += tickRate;
        let percentage = (elapsed / totalDuration) * 100;
        if (percentage > 100) percentage = 100;

        // 목표 수치 업데이트 (렌더링 루프에서 보간 추적)
        waveState.targetPercent = percentage;
        percentText.textContent = `${Math.floor(percentage)}%`;

        // 상단 카운트 갱신
        currentCountObj.textContent = Math.floor((percentage / 100) * totalComments);

        // 시간 분할 비례 식 로그 출력
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

    // 자연스러운 수치 추적 보간 연산
    waveState.currentPercent += (waveState.targetPercent - waveState.currentPercent) * 0.1;
    waveState.angle += 0.04; // 물결 치는 속도

    ctx.clearRect(0, 0, width, height);

    // 100%가 되면 물결 파고(Amplitude)를 0으로 만들어 출렁임 정지
    const isFull = waveState.currentPercent >= 99.8;
    const waveAmplitude1 = isFull ? 0 : 7;
    const waveAmplitude2 = isFull ? 0 : 5;

    // 물이 다 찼을 때는 상단 깎임 보정하기 위해 수위를 살짝 올려 채움
    const fillLevel = isFull ? height : (waveState.currentPercent / 100) * height;
    const yCenter = height - fillLevel;

    // 버블 입자 관리 (차오르는 중일 때만 생성)
    if (!isFull && Math.random() < 0.15 && waveState.currentPercent > 5) {
        waveState.bubbles.push({
            x: Math.random() * width,
            y: height + 10,
            size: Math.random() * 3 + 2,
            speed: Math.random() * 1.5 + 1
        });
    }

    // [Layer 1] 뒷배경 연한 물결 렌더링
    ctx.fillStyle = 'rgba(128, 216, 255, 0.5)';
    ctx.beginPath();
    for (let x = 0; x <= width; x++) {
        // 사인파 공식을 이용해 일정한 파고 렌더링
        let y = yCenter + Math.sin(x * 0.025 + waveState.angle) * waveAmplitude1;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.lineTo(width, height);
    ctx.lineTo(0, height);
    ctx.closePath();
    ctx.fill();

    // [Layer 2] 앞배경 메인 파란 물결 렌더링
    ctx.fillStyle = '#00b0ff';
    ctx.beginPath();
    for (let x = 0; x <= width; x++) {
        // 주기를 다르게 뒤틀어 엇갈리는 입체감 생성
        let y = yCenter + Math.cos(x * 0.03 + waveState.angle * 1.2) * waveAmplitude2;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.lineTo(width, height);
    ctx.lineTo(0, height);
    ctx.closePath();
    ctx.fill();

    // 버블 그리기 및 업데이트
    ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
    for (let i = waveState.bubbles.length - 1; i >= 0; i--) {
        let b = waveState.bubbles[i];
        b.y -= b.speed;

        ctx.beginPath();
        ctx.arc(b.x, b.y, b.size, 0, Math.PI * 2);
        ctx.fill();

        // 현재 수면 위로 올라가거나 어항 꼭대기를 벗어나면 소거
        if (b.y < yCenter || b.y < 0) {
            waveState.bubbles.splice(i, 1);
        }
    }

    // 브라우저 프레임 동기화 유지
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
