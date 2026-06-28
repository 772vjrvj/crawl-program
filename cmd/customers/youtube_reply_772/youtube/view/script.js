const ANIMATION_DURATION_SEC = 4;

const youtubeVideoData = [
    {
        "video_id": "D_axHX2HaW8",
        "title": "기분이 너무 더럽습니다ㅣ히든풋볼W",
        "channel_title": "이스타TV",
        "view_count": 698987,
        "like_count": 8645,
        "comment_count": 3077,
        "thumbnail_url": "https://i.ytimg.com/vi/D_axHX2HaW8/maxresdefault.jpg"
    }];

let sentimentChart = null;

const chartData = {
    pos: 152,
    neg: 2320,
    neu: 605
};

const koreanLogs = [
    {type: 'sys', text: '>> [인프라 부팅] 데이터 연동 파이프라인 시동.'},
    {type: 'run', text: '>> [커넥션] 타겟 비디오 검증 완료: [8kFnA0oxFeI]'},
    {type: 'ok', text: '>> [성공] API 엔드포인트 보안 게이트웨이 인증 패스.'},
    {type: 'run', text: '>> [수집] 원본 댓글 세그먼트 데이터 스트림 실시간 다운로드...'},
    {type: 'ok', text: '>> [성공] 오디오 모델 가동 - 캡차 문자 해독 완료.'},
    {type: 'run', text: '>> [정제] 마스킹 암호화 트랜잭션 전개.'},
    {type: 'run', text: '>> [인덱싱] 매핑 최적화 부모 트리 구조 빌드 중...'},
    {type: 'sys', text: '>> [자연어 코어] 한국어 토큰 정규화 커널 바인딩.'},
    {type: 'run', text: '>> [텍스트마이닝] 의미어 추출 및 유효 불용어 소거 가동.'},
    {type: 'run', text: '>> [TF-IDF] 단어 가중치 기반 실시간 수치 연산.'},
    {type: 'sys', text: '>> [LLM 엔진] 가상 프롬프트 컨텍스트 스캐닝.'},
    {type: 'ok', text: '>> [성공] 분석 스크립트 빌드 및 동기화 준비 완수.'}
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
        if (['1', '2', '3', '4', '5', '6', '7', '8', '9'].includes(key)) switchScene(key);
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
    // 1. 공통 초기화 로직 (기존과 동일)
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

    // 2. 모든 씬 숨기기
    const allScenes = document.querySelectorAll('.scene');
    allScenes.forEach(scene => scene.classList.remove('active'));

    // 3. 타겟 씬 활성화
    const targetScene = document.getElementById(`scene-${sceneNumber}`);
    if (targetScene) {
        targetScene.classList.add('active');

        // [씬별 개별 로직]

        // 씬 1: 영상 데이터 애니메이션
        if (sceneNumber === '1') animateNumbers(youtubeVideoData[0]);

        // 씬 3: 데이터 수집 (기존 2번 씬)
        if (sceneNumber === '3') {
            document.getElementById('total-count').textContent = youtubeVideoData[0].comment_count;
            document.getElementById('current-count').textContent = "0";
            document.getElementById('terminal-log').innerHTML = "<div class='log-line sys'>&gt;&gt; SYSTEM READY. INITIALIZE BUTTON...</div>";
        }

        // 씬 4: 감정 분석 (기존 3번 씬)
        if (sceneNumber === '4') {
            updateSentimentChart(chartData.pos, chartData.neg, chartData.neu);
        }

        // 씬 5: 긍정 Top 5 (기존 4번 씬)
        if (sceneNumber === '5') {
            revealIdx.pos = 4;
            initRankCards('pos');
        }

        // 씬 6: 부정 Top 5 (기존 5번 씬)
        if (sceneNumber === '6') {
            revealIdx.neg = 4;
            initRankCards('neg');
        }

        // 씬 7: 주요 키워드 분석 (기존 6번 씬)
        if (sceneNumber === '7') {
            // 임시 데이터 전달 (데이터 소스에 맞춰 교체하세요)
            const rawData = youtube_comment_token;

// 데이터 빈도 집계 (중복된 token_text 합치기)
            const aggregatedData = {};
            rawData.forEach(item => {
                aggregatedData[item.token_text] = (aggregatedData[item.token_text] || 0) + item.token_count;
            });

            const finalData = Object.keys(aggregatedData).map(key => ({
                name: key,
                value: aggregatedData[key] * 20
            }));

            initWordCloud(finalData);
        }

        // 씬 8: 네트워크 분석 (새로 추가)
        if (sceneNumber === '8') {
            initNetworkGraph();
        }

// [switchScene 함수 내부에 추가]
        if (sceneNumber === '9') {
            // 네트워크가 아직 안 만들어졌을 수도 있으니 방어 코드 추가
            if (Object.keys(nodeMap).length === 0) {
                document.getElementById('cluster-info').textContent = "먼저 8번 씬에서 네트워크 분석을 실행해주세요.";
            } else {
                analyzeStructure();
            }
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
                {value: pos, name: '긍정', itemStyle: {color: '#2064b2'}},
                {value: neg, name: '부정', itemStyle: {color: '#ff6b6b'}},
                {value: neu, name: '중립', itemStyle: {color: '#a0a0a0'}}
            ]
        }]
    };
    sentimentChart.setOption(option);
}

const rankData = {"neg": [{"author_name": "@주언구", "reason_text": "댓글에서 사용된 '실력', '체격' 등의 단어와 부정적인 어조를 통해 강한 부정적 감정을 나타내고 있음.", "comment_text": "뭘바래. 실렵이 없은데. 체켝도 없고", "negative_score": 0.9000, "positive_score": 0.0100, "sentiment_score": -0.8000}, {"author_name": "@lafayetteo9235", "reason_text": "댓글에서 나타난 강한 부정적인 감정 표현으로 인해 해당 댓글은 'NEGATIVE'로 분류됩니다.", "comment_text": "더는 국대경기 꼴보기도 싫어서 그냥 안올라갔으면", "negative_score": 0.9000, "positive_score": 0.0100, "sentiment_score": -0.8000}, {"author_name": "@coupang2", "reason_text": "댓글에서 반복적으로 강한 어조로 특정 인물을 비난하고 있으며 이는 명백한 비판적인 내용을 담고 있습니다.", "comment_text": "홍명보 60억 토해내라 . 홍명보 60억 토해내라 . 홍명보 60억 토해내라 . 홍명보 60억 토해내라 . 홍명보 60억 토해내라 . 홍명보 60억 토해내라 . 홍명보 60억 토해내라 . 홍명보 60억 토해내라 . 홍명보 60억 토해내라 . 홍명보 60억 토해내라 . 홍명보 60억 토해내라 . 홍명보 60억 토해내라 . 홍명보 60억 토해내라 . 홍명보 60억 토해내라 .", "negative_score": 0.9000, "positive_score": 0.0100, "sentiment_score": -0.8000}, {"author_name": "@view8590", "reason_text": "댓글에는 강한 분노와 비난, 폭력적인 내용이 포함되어 있어 부정적인 감성이 매우 강하게 나타납니다.", "comment_text": "역대 최고의 꿀조에 최고의 일정과 경기장 운까지 역대 최고의 멤버로 이 따위 결과를 내는 인간이 국대감독이라니... 축구팬 개돼지들 취급. 스파이크로 얼굴을 찍어버리고 싶네요. 일본과 모든 면에서 너무 비교가 됨.", "negative_score": 0.9000, "positive_score": 0.0100, "sentiment_score": -0.8000}, {"author_name": "@원샷원키리", "reason_text": "댓글에는 강한 부정적인 표현인 '존나'라는 단어가 포함되어 있으며 이는 명백하게 상대방을 모욕하는 의도를 가지고 있습니다.", "comment_text": "존나 건방지다 ㅎㅎㅎ", "negative_score": 0.9000, "positive_score": 0.0100, "sentiment_score": -0.8000}], "pos": [{"author_name": "@korea43027", "reason_text": "댓글에는 강한 웃음소리가 포함되어 있으며 이는 긍정적인 감정을 나타냅니다.", "comment_text": "56:45 앜ㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋ", "negative_score": 0.0500, "positive_score": 0.9000, "sentiment_score": 0.8000}, {"author_name": "@bose3498", "reason_text": "댓글 자체가 긍정적인 반응을 보여주고 있으며, 경쟁적인 상황에서 1등을 차지한 것에 대한 기쁨과 성취감을 나타내고 있다.", "comment_text": "1등!", "negative_score": 0.0500, "positive_score": 0.9000, "sentiment_score": 0.8000}, {"author_name": "@장동엽-m3h", "reason_text": "댓글에서 '최고의 비유'라는 표현을 사용하여 긍정적인 평가를 나타내고 있다.", "comment_text": "최고의 비유입니다.", "negative_score": 0.0500, "positive_score": 0.9000, "sentiment_score": 0.8000}, {"author_name": "@MeltAmon", "reason_text": "댓글에서 웃음을 유발하는 내용에 대해 긍정적인 반응을 보임.", "comment_text": "추맨 왜이리 ㅇ웃기냐 ㅋㅋㅋㅋㅋㅋㅋㅋ", "negative_score": 0.0500, "positive_score": 0.9000, "sentiment_score": 0.8000}, {"author_name": "@김용석-y5j", "reason_text": "댓글에서 긍정적인 반응인 '말을 너무 잘해'라는 표현을 사용하여 칭찬하고 있으며, 엄지척 이모티콘을 통해 긍정의 의미를 더욱 강조하고 있다.", "comment_text": "말을 너무 잘해.. 👍", "negative_score": 0.0500, "positive_score": 0.9000, "sentiment_score": 0.8000}]};


let revealIdx = {pos: 4, neg: 4};

function showDetail(data) {
    document.getElementById('modal-author').textContent = `작성자: ${data.author_name.substring(0, 3)}***`;
    document.getElementById('modal-text').textContent = data.comment_text;
    document.getElementById('modal-score').textContent = data.sentiment_score.toFixed(4);
    document.getElementById('modal-reason').textContent = data.reason_text;

    const modal = document.getElementById('detail-modal');
    modal.style.display = 'flex';

    // X 버튼 생성 로직
    if (!document.querySelector('.close-x')) {
        const x = document.createElement('span');
        x.className = 'close-x';
        x.innerHTML = '&times;';
        x.onclick = closeModal;
        document.querySelector('.modal-content').prepend(x);
    }
}

function closeModal() {
    document.getElementById('detail-modal').style.display = 'none';
}

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
    // 1. revealIdx가 유효한지 확인
    if (revealIdx[type] < 0) return;

    // 2. 카드가 존재하는지 먼저 확인
    const cardId = `${type}-card-${revealIdx[type]}`;
    const card = document.getElementById(cardId);

    if (!card) {
        console.warn(`카드를 찾을 수 없습니다: ${cardId}`);
        return;
    }

    // 3. 데이터가 존재하는지 확인
    const data = rankData[type][revealIdx[type]];
    if (!data) return;

    // 4. 안전하게 클래스 추가 및 데이터 설정
    card.classList.add('show');
    card.querySelector('.rank-text').textContent = data.comment_text;
    card.onclick = () => showDetail(data);

    revealIdx[type]--;
}

// 이 아래는 이미 있는 'keydown' 이벤트를 찾아 수정하거나 추가하세요
document.addEventListener("keydown", (e) => {
    const key = e.key.toLowerCase();
    if (['1', '2', '3', '4', '5', '6', '7', '8'].includes(key)) {
        switchScene(key);
    }
    if (key === 'q') crackEgg('cta-q');
    if (key === 'w') crackEgg('cta-w');
    if (key === 'e') crackEgg('cta-e');
    if (key === 'r') crackEgg('cta-r');
    if (key.toLowerCase() === 'u') {
        const activeScene = document.querySelector('.scene.active').id;
        if (activeScene === 'scene-5') addRankCard('pos');
        if (activeScene === 'scene-6') addRankCard('neg');
    }
});

/**
 * 워드 클라우드 차트 초기화 및 우측 랭킹 테이블 렌더링
 * @param {Array} data - {name: string, value: number} 형태의 데이터 배열
 */
function initWordCloud(data) {
    const chartDom = document.getElementById('word-cloud-chart');
    const tableBody = document.getElementById('rank-table-body');
    if (!chartDom || !tableBody) return;

    // 1. 데이터 정렬 (내림차순) 및 Top 10 추출
    const sortedData = [...data].sort((a, b) => b.value - a.value);
    const top10 = sortedData.slice(0, 10);

    // 2. 테이블 렌더링 (순위 데이터 삽입)
    tableBody.innerHTML = top10.map((item, index) => `
        <tr>
            <td class="rank-num-col">${index + 1}위</td>
            <td>${item.name}</td>
            <td class="rank-val-col">${item.value / 20}회</td>
        </tr>
    `).join('');

    // 3. 기존 인스턴스 정리 및 차트 초기화
    if (echarts.getInstanceByDom(chartDom)) {
        echarts.dispose(chartDom);
    }
    const myChart = echarts.init(chartDom);

    const vibrantPalette = [
        '#007bff', '#20c997', '#fd7e14', '#e83e8c',
        '#6f42c1', '#17a2b8', '#d63384', '#0d6efd'
    ];

    const option = {
        series: [{
            type: 'wordCloud',
            shape: 'circle',
            width: '85%', height: '85%',
            sizeRange: [20, 90],
            rotationRange: [0, 0],
            gridSize: 12,
            textStyle: {
                fontFamily: 'Pretendard',
                fontWeight: 'bold',
                color: () => vibrantPalette[Math.floor(Math.random() * vibrantPalette.length)]
            },
            emphasis: {
                focus: 'self',
                textStyle: {shadowBlur: 10, shadowColor: 'rgba(0, 0, 0, 0.3)'}
            },
            data: sortedData
        }]
    };
    myChart.setOption(option);
}

let nodeMap = {}; // 전역으로 선언하여 어디서든 접근 가능하게 합니다.

function initNetworkGraph() {
    const container = document.getElementById("network");

    // 이미 생성되어 있다면 초기화 방지
    // 설정 바꿨으면 새로고침 후 8번 씬 다시 실행
    if (container.innerHTML !== "") return;

    // =====================================================
    // 1. 연결선 표시 기준
    // =====================================================
    const MIN_WEIGHT = 1;
    const MAX_EDGE_COUNT = 200;

    // =====================================================
    // 2. 스타일 프리셋
    // =====================================================
    const STYLE_PRESET = "SOFT";
    // const STYLE_PRESET = "CLEAR";
    // const STYLE_PRESET = "STRONG";

    const STYLE_MAP = {
        SOFT: {
            normalNodeOpacity: 0.12,
            normalNodeBorderOpacity: 0.12,
            normalNodeFontOpacity: 0.18,
            normalEdgeOpacity: 0.12,

            dimNodeOpacity: 0.03,
            dimNodeBorderOpacity: 0.03,
            dimNodeFontOpacity: 0.04,
            dimEdgeOpacity: 0.03,

            activeNodeOpacity: 0.95,
            activeNodeBorderOpacity: 1,
            activeNodeFontOpacity: 1,
            activeEdgeOpacity: 0.95
        },

        CLEAR: {
            normalNodeOpacity: 0.35,
            normalNodeBorderOpacity: 0.35,
            normalNodeFontOpacity: 0.45,
            normalEdgeOpacity: 0.25,

            dimNodeOpacity: 0.08,
            dimNodeBorderOpacity: 0.08,
            dimNodeFontOpacity: 0.08,
            dimEdgeOpacity: 0.05,

            activeNodeOpacity: 0.95,
            activeNodeBorderOpacity: 1,
            activeNodeFontOpacity: 1,
            activeEdgeOpacity: 0.95
        },

        STRONG: {
            normalNodeOpacity: 0.75,
            normalNodeBorderOpacity: 0.75,
            normalNodeFontOpacity: 0.85,
            normalEdgeOpacity: 0.45,

            dimNodeOpacity: 0.15,
            dimNodeBorderOpacity: 0.15,
            dimNodeFontOpacity: 0.15,
            dimEdgeOpacity: 0.08,

            activeNodeOpacity: 1,
            activeNodeBorderOpacity: 1,
            activeNodeFontOpacity: 1,
            activeEdgeOpacity: 1
        }
    };

    const style = STYLE_MAP[STYLE_PRESET];

    // =====================================================
    // 3. 색상 설정
    // =====================================================
    const nodeColors = [
        "#00E5FF",
        "#42A5F5",
        "#A970FF"
    ];

    const DEFAULT_EDGE_COLOR = "#9CA3AF";

    // 노드 클릭 / 노드 hover 시 연결선 색상: 밝은 연두색
    const ACTIVE_EDGE_COLOR = "#B6FF4D";

    // 노드 클릭 / 노드 hover 시 노드 테두리 색상: 밝은 연두색
    const ACTIVE_NODE_BORDER_COLOR = "#B6FF4D";

    // 라인 직접 클릭 시 고정 색상: 밝은 붉은색
    const PINNED_EDGE_COLOR = "#FF4D4D";

    // 라인 직접 클릭 시 양쪽 노드 테두리 색상
    const PINNED_NODE_BORDER_COLOR = "#FF4D4D";

    function hexToRgba(hex, alpha) {
        const value = hex.replace("#", "");
        const r = parseInt(value.substring(0, 2), 16);
        const g = parseInt(value.substring(2, 4), 16);
        const b = parseInt(value.substring(4, 6), 16);

        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }

    // edge id가 숫자/문자열로 섞여도 비교되도록 통일
    function toEdgeKey(edgeId) {
        return String(edgeId);
    }

    function getEdgeByKey(edgeKey) {
        return edgeDataSet.get(edgeKey) || edgeDataSet.get(Number(edgeKey));
    }

    // =====================================================
    // 4. 데이터 필터링
    // =====================================================
    if (typeof youtube_token_edge === "undefined" || !Array.isArray(youtube_token_edge)) {
        console.warn("youtube_token_edge 데이터가 없습니다.");
        return;
    }

    const filteredEdges = youtube_token_edge
        .filter(edge => edge.weight >= MIN_WEIGHT)
        .sort((a, b) => b.weight - a.weight)
        .slice(0, MAX_EDGE_COUNT);

    // =====================================================
    // 5. 노드 연결성 계산
    // =====================================================
    nodeMap = {};

    filteredEdges.forEach(edge => {
        if (!nodeMap[edge.source_token]) {
            nodeMap[edge.source_token] = {count: 0};
        }

        if (!nodeMap[edge.target_token]) {
            nodeMap[edge.target_token] = {count: 0};
        }

        nodeMap[edge.source_token].count++;
        nodeMap[edge.target_token].count++;
    });

    // =====================================================
    // 6. 노드 생성
    // =====================================================
    let id = 1;
    const nodeIds = {};
    const nodes = [];

    Object.keys(nodeMap).forEach(word => {
        nodeIds[word] = id++;

        const baseColor = nodeColors[Math.floor(Math.random() * nodeColors.length)];

        nodes.push({
            id: nodeIds[word],
            label: word,
            baseColor: baseColor,

            // 연결이 많을수록 동그라미 크게
            value: 15 + nodeMap[word].count * 10,

            shape: "dot",

            color: {
                background: hexToRgba(baseColor, style.normalNodeOpacity),
                border: `rgba(255, 255, 255, ${style.normalNodeBorderOpacity})`
            },

            font: {
                color: `rgba(255, 255, 255, ${style.normalNodeFontOpacity})`,
                size: 20,
                face: "Pretendard"
            }
        });
    });

    // =====================================================
    // 7. 연결선 생성
    // =====================================================
    const edges = filteredEdges.map((edge, index) => {
        const baseWidth = Math.log(edge.weight + 1) * 1.5;

        return {
            id: index + 1,
            from: nodeIds[edge.source_token],
            to: nodeIds[edge.target_token],

            sourceToken: edge.source_token,
            targetToken: edge.target_token,
            weight: edge.weight,

            baseWidth: baseWidth,
            width: baseWidth,

            color: {
                color: DEFAULT_EDGE_COLOR,
                opacity: style.normalEdgeOpacity
            },

            smooth: false
        };
    });

    const nodeDataSet = new vis.DataSet(nodes);
    const edgeDataSet = new vis.DataSet(edges);

    const data = {
        nodes: nodeDataSet,
        edges: edgeDataSet
    };

    // =====================================================
    // 8. 네트워크 옵션
    // =====================================================
    const options = {
        physics: {
            enabled: true,
            stabilization: false,
            barnesHut: {
                // 노드끼리 서로 밀어내는 힘
                // 숫자가 더 작을수록 더 멀리 퍼짐
                // 예: -3000 기본 / -6000 적당히 퍼짐 / -9000 많이 퍼짐
                gravitationalConstant: -6000,

                // 연결된 노드 사이의 기본 거리
                // 숫자가 클수록 연결된 노드끼리 더 멀어짐
                // 예: 180 기본 / 260 적당히 퍼짐 / 320 많이 퍼짐
                springLength: 260,

                // 선이 노드를 잡아당기는 힘
                // 너무 높이면 다시 뭉치고, 너무 낮으면 많이 흐트러짐
                // 일단 기존값 유지 추천
                springConstant: 0.02,

                // 노드 겹침 방지
                // 0은 겹침 허용, 1에 가까울수록 겹침 방지 강함
                avoidOverlap: 0.5
            }
        },
        nodes: {
            borderWidth: 2,
            shadow: {
                enabled: true,
                size: 20
            }
        },
        edges: {
            shadow: {
                enabled: true,
                size: 10
            },

            // 라인에 마우스 올렸을 때 클릭 범위 확보
            hoverWidth: 5,
            selectionWidth: 0
        },
        interaction: {
            hover: true,
            zoomView: true,
            dragView: true,

            // 노드 클릭 시 vis 기본 연결선 선택 효과 방지
            selectConnectedEdges: false
        }
    };

    const network = new vis.Network(container, data, options);

    // =====================================================
    // 9. 상태값
    // =====================================================
    const selectedNodeIds = new Set(); // 클릭 활성화된 노드들
    const pinnedEdgeIds = new Set();   // 빨간색 고정 라인들

    let hoveredNodeId = null;
    let hoveredEdgeId = null;

    // =====================================================
    // 10. 기본 스타일 적용 함수
    // =====================================================
    function applyNormalStyle() {
        const nodeUpdates = nodes.map(node => ({
            id: node.id,
            color: {
                background: hexToRgba(node.baseColor, style.normalNodeOpacity),
                border: `rgba(255, 255, 255, ${style.normalNodeBorderOpacity})`
            },
            font: {
                color: `rgba(255, 255, 255, ${style.normalNodeFontOpacity})`,
                size: 20,
                face: "Pretendard"
            }
        }));

        const edgeUpdates = edges.map(edge => ({
            id: edge.id,
            width: edge.baseWidth,
            color: {
                color: DEFAULT_EDGE_COLOR,
                opacity: style.normalEdgeOpacity
            }
        }));

        nodeDataSet.update(nodeUpdates);
        edgeDataSet.update(edgeUpdates);
    }

    // =====================================================
    // 11. 전체 초기화
    // =====================================================
    function resetGraphStyle() {
        selectedNodeIds.clear();
        pinnedEdgeIds.clear();

        hoveredNodeId = null;
        hoveredEdgeId = null;

        network.unselectAll();
        applyNormalStyle();
    }

    // =====================================================
    // 12. 선택 노드 + hover 노드 + 빨간 라인 합쳐서 렌더링
    // =====================================================
    function renderGraphStyle() {
        const hasSelectedNode = selectedNodeIds.size > 0;
        const hasHoverNode = hoveredNodeId !== null;
        const hasHoverEdge = hoveredEdgeId !== null; // 연결선 hover 여부 추가
        const hasPinnedEdge = pinnedEdgeIds.size > 0;

        if (!hasSelectedNode && !hasHoverNode && !hasHoverEdge && !hasPinnedEdge) {
            applyNormalStyle();
            return;
        }

        const activeNodeIds = new Set();
        const activeEdgeIds = new Set();
        const pinnedNodeIds = new Set();

        // 클릭된 노드들의 주변 활성화
        selectedNodeIds.forEach(selectedNodeId => {
            activeNodeIds.add(selectedNodeId);

            const connectedNodeIds = network.getConnectedNodes(selectedNodeId);
            const connectedEdgeIds = network.getConnectedEdges(selectedNodeId);

            connectedNodeIds.forEach(nodeId => activeNodeIds.add(nodeId));
            connectedEdgeIds.forEach(edgeId => activeEdgeIds.add(toEdgeKey(edgeId)));
        });

        // hover 중인 노드의 주변 활성화
        if (hoveredNodeId !== null) {
            activeNodeIds.add(hoveredNodeId);

            const connectedNodeIds = network.getConnectedNodes(hoveredNodeId);
            const connectedEdgeIds = network.getConnectedEdges(hoveredNodeId);

            connectedNodeIds.forEach(nodeId => activeNodeIds.add(nodeId));
            connectedEdgeIds.forEach(edgeId => activeEdgeIds.add(toEdgeKey(edgeId)));
        }

        // 직접 클릭한 라인은 빨간색 고정 + 양쪽 노드 활성화
        pinnedEdgeIds.forEach(edgeKey => {
            const edge = getEdgeByKey(edgeKey);

            if (!edge) return;

            activeEdgeIds.add(toEdgeKey(edge.id));

            activeNodeIds.add(edge.from);
            activeNodeIds.add(edge.to);

            pinnedNodeIds.add(edge.from);
            pinnedNodeIds.add(edge.to);
        });

        // 연결선 hover 시 해당 선 진하게 + 양쪽 노드 활성화
        if (hoveredEdgeId !== null) {
            const hoverEdgeKey = toEdgeKey(hoveredEdgeId);
            const edge = getEdgeByKey(hoverEdgeKey);

            if (edge) {
                activeEdgeIds.add(toEdgeKey(edge.id));

                // 선 양쪽 노드도 같이 활성화
                activeNodeIds.add(edge.from);
                activeNodeIds.add(edge.to);
            }
        }

        const nodeUpdates = nodes.map(node => {
            const isActive = activeNodeIds.has(node.id);
            const isPinnedNode = pinnedNodeIds.has(node.id);

            if (isActive) {
                return {
                    id: node.id,
                    color: {
                        background: hexToRgba(node.baseColor, style.activeNodeOpacity),

                        // 빨간 라인의 양쪽 노드만 빨간 테두리
                        // 일반 노드 클릭/hover는 연두색 테두리
                        border: isPinnedNode
                            ? PINNED_NODE_BORDER_COLOR
                            : ACTIVE_NODE_BORDER_COLOR
                    },
                    font: {
                        color: `rgba(255, 255, 255, ${style.activeNodeFontOpacity})`,
                        size: isPinnedNode ? 26 : 24,
                        face: "Pretendard"
                    }
                };
            }

            return {
                id: node.id,
                color: {
                    background: hexToRgba(node.baseColor, style.dimNodeOpacity),
                    border: `rgba(255, 255, 255, ${style.dimNodeBorderOpacity})`
                },
                font: {
                    color: `rgba(255, 255, 255, ${style.dimNodeFontOpacity})`,
                    size: 20,
                    face: "Pretendard"
                }
            };
        });

        const edgeUpdates = edges.map(edge => {
            const edgeKey = toEdgeKey(edge.id);

            const isPinnedEdge = pinnedEdgeIds.has(edgeKey);
            const isActiveEdge = activeEdgeIds.has(edgeKey);

            // 라인 직접 클릭한 경우: 항상 빨간색 최우선
            if (isPinnedEdge) {
                return {
                    id: edge.id,
                    width: edge.baseWidth + 6,
                    color: {
                        color: PINNED_EDGE_COLOR,
                        opacity: 1
                    }
                };
            }

            // 노드 클릭 / 노드 hover 연결선: 연두색
            if (isActiveEdge) {
                return {
                    id: edge.id,
                    width: edge.baseWidth + 2,
                    color: {
                        color: ACTIVE_EDGE_COLOR,
                        opacity: style.activeEdgeOpacity
                    }
                };
            }

            return {
                id: edge.id,
                width: edge.baseWidth,
                color: {
                    color: DEFAULT_EDGE_COLOR,
                    opacity: style.dimEdgeOpacity
                }
            };
        });

        nodeDataSet.update(nodeUpdates);
        edgeDataSet.update(edgeUpdates);
    }

    // =====================================================
    // 13. hover 이벤트
    // =====================================================
    network.on("hoverNode", function (params) {
        hoveredNodeId = params.node;
        renderGraphStyle();
    });

    network.on("blurNode", function () {
        hoveredNodeId = null;
        renderGraphStyle();
    });

    // 라인 클릭 밀림 방지용
    // click 이벤트에서 params.edges를 읽지 않고,
    // 마우스가 올라간 라인을 미리 저장했다가 클릭 시 사용
    network.on("hoverEdge", function (params) {
        hoveredEdgeId = params.edge;

        // 연결선에 마우스 올리면 즉시 진하게 표시
        renderGraphStyle();
    });

    network.on("blurEdge", function () {
        hoveredEdgeId = null;

        // 연결선에서 마우스 빠지면 원래 상태로 복구
        renderGraphStyle();
    });

    // =====================================================
    // 14. 클릭 이벤트
    // =====================================================
    network.on("click", function (params) {
        // 1. 노드 클릭 먼저 처리
        // 노드 클릭 시 밑에 깔린 라인이 빨간색으로 잘못 잡히지 않게 함
        const clickedNodeId = params.nodes && params.nodes.length > 0
            ? params.nodes[0]
            : network.getNodeAt(params.pointer.DOM);

        if (clickedNodeId !== undefined && clickedNodeId !== null) {
            if (selectedNodeIds.has(clickedNodeId)) {
                selectedNodeIds.delete(clickedNodeId);

                // 같은 노드를 다시 클릭해서 해제했을 때
                // hover 효과가 남아서 바로 다시 활성화되는 것 방지
                if (hoveredNodeId === clickedNodeId) {
                    hoveredNodeId = null;
                }
            } else {
                selectedNodeIds.add(clickedNodeId);
            }

            network.unselectAll();
            renderGraphStyle();
            return;
        }

        // 2. 라인 클릭 처리
        // 중요:
        // params.edges[0] 사용 금지.
        // 한 박자 밀림 원인이므로 hoveredEdgeId를 우선 사용.
        let clickedEdgeId = hoveredEdgeId;

        // 혹시 hoverEdge가 안 잡힌 상태에서 클릭했을 때만 보조 감지
        if (clickedEdgeId === undefined || clickedEdgeId === null) {
            clickedEdgeId = network.getEdgeAt(params.pointer.DOM);
        }

        if (clickedEdgeId !== undefined && clickedEdgeId !== null) {
            const edgeKey = toEdgeKey(clickedEdgeId);

            // 라인 1번 클릭: 빨간색 고정
            // 같은 라인 2번 클릭: 빨간색 해제
            if (pinnedEdgeIds.has(edgeKey)) {
                pinnedEdgeIds.delete(edgeKey);
            } else {
                pinnedEdgeIds.add(edgeKey);
            }

            network.unselectAll();
            renderGraphStyle();
            return;
        }

        // 3. 빈 공간 클릭하면 전체 초기화
        resetGraphStyle();
    });

    // =====================================================
    // 15. 핵심 키워드 3개 요약 표 생성
    // =====================================================
    const sortedNodes = Object.keys(nodeMap)
        .map(word => ({
            word: word,
            count: nodeMap[word].count
        }))
        .sort((a, b) => b.count - a.count)
        .slice(0, 15); // Top 15까지 표시

    const table = document.getElementById("network-table");

    // 우측 제목도 JS에서 Top 10으로 변경
    const summaryTitle = document.querySelector(".network-summary h3");
    if (summaryTitle) {
        summaryTitle.textContent = "핵심 키워드 (Top 15) 중심성(Centrality)";
    }

    table.innerHTML =
        `<tr><th>순위</th><th>키워드</th><th>연결성</th></tr>` +
        sortedNodes.map((item, index) =>
            `<tr>
            <td>${index + 1}</td>
            <td>${item.word}</td>
            <td>${item.count}</td>
        </tr>`
        ).join("");
}


function analyzeStructure() {
    if (typeof nodeMap !== 'undefined') {
        // 1. 연결성(count) 기준 내림차순 정렬
        const sorted = Object.keys(nodeMap).sort((a, b) => nodeMap[b].count - nodeMap[a].count);

        // 2. 데이터가 충분한지 체크
        if (sorted.length < 9) {
            document.querySelectorAll('.analysis-card p').forEach(p => p.textContent = "분석할 데이터가 충분하지 않습니다.");
            return;
        }

        // 3. 3개의 클러스터 정의
        const groupA = sorted.slice(0, 3); // 활용 그룹
        const groupB = sorted.slice(3, 6); // 시설/행정 그룹
        const groupC = sorted.slice(6, 9); // 이해관계자 그룹

        // 4. 화면 출력 (3개 카드로 분산 배치)
        document.getElementById('group-1').innerHTML = `<b>관련 키워드:</b> ${groupA.join(', ')}`;
        document.getElementById('group-2').innerHTML = `<b>관련 키워드:</b> ${groupB.join(', ')}`;
        document.getElementById('group-3').innerHTML = `<b>관련 키워드:</b> ${groupC.join(', ')}`;
    }
}