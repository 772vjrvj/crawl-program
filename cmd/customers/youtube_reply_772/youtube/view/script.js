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

        if (sceneNumber === '6') {
            // 임시 데이터 전달 (데이터 소스에 맞춰 교체하세요)
            const rawData = [{"token_id":128,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgySblOmguHZz_AVeCh4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"아이","token_norm":"아이","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":1,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":129,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgySblOmguHZz_AVeCh4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"학교","token_norm":"학교","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":2,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":130,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgySblOmguHZz_AVeCh4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"폐교","token_norm":"폐교","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":3,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":131,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgySblOmguHZz_AVeCh4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"앞뒤","token_norm":"앞뒤","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":4,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":132,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgySblOmguHZz_AVeCh4AaABAg.ASq2tqotg_iASqJEvi50ep","parent_comment_id":"UgySblOmguHZz_AVeCh4AaABAg","comment_kind":"REPLY","token_text":"도시","token_norm":"도시","pos":"NNG","token_type":"MORPHEME","token_count":4,"first_token_order":1,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":133,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgySblOmguHZz_AVeCh4AaABAg.ASq2tqotg_iASqJEvi50ep","parent_comment_id":"UgySblOmguHZz_AVeCh4AaABAg","comment_kind":"REPLY","token_text":"도심","token_norm":"도심","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":2,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":134,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgySblOmguHZz_AVeCh4AaABAg.ASq2tqotg_iASqJEvi50ep","parent_comment_id":"UgySblOmguHZz_AVeCh4AaABAg","comment_kind":"REPLY","token_text":"부부","token_norm":"부부","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":3,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":135,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgySblOmguHZz_AVeCh4AaABAg.ASq2tqotg_iASqJEvi50ep","parent_comment_id":"UgySblOmguHZz_AVeCh4AaABAg","comment_kind":"REPLY","token_text":"초등학교","token_norm":"초등학교","pos":"NNG","token_type":"MORPHEME","token_count":2,"first_token_order":5,"token_len":4,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":136,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgySblOmguHZz_AVeCh4AaABAg.ASq2tqotg_iASqJEvi50ep","parent_comment_id":"UgySblOmguHZz_AVeCh4AaABAg","comment_kind":"REPLY","token_text":"증설","token_norm":"증설","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":6,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":137,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgySblOmguHZz_AVeCh4AaABAg.ASq2tqotg_iASqJEvi50ep","parent_comment_id":"UgySblOmguHZz_AVeCh4AaABAg","comment_kind":"REPLY","token_text":"수도","token_norm":"수도","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":7,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":138,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgySblOmguHZz_AVeCh4AaABAg.ASq2tqotg_iASqJEvi50ep","parent_comment_id":"UgySblOmguHZz_AVeCh4AaABAg","comment_kind":"REPLY","token_text":"외곽","token_norm":"외곽","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":8,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":139,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgySblOmguHZz_AVeCh4AaABAg.ASq2tqotg_iASqJEvi50ep","parent_comment_id":"UgySblOmguHZz_AVeCh4AaABAg","comment_kind":"REPLY","token_text":"연령","token_norm":"연령","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":9,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":140,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgySblOmguHZz_AVeCh4AaABAg.ASq2tqotg_iASqJEvi50ep","parent_comment_id":"UgySblOmguHZz_AVeCh4AaABAg","comment_kind":"REPLY","token_text":"지방","token_norm":"지방","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":11,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":141,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgySblOmguHZz_AVeCh4AaABAg.ASq2tqotg_iASqJEvi50ep","parent_comment_id":"UgySblOmguHZz_AVeCh4AaABAg","comment_kind":"REPLY","token_text":"애기","token_norm":"애기","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":13,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":142,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugz_KLeMk6Erbs83BQZ4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"평택","token_norm":"평택","pos":"NNP","token_type":"MORPHEME","token_count":1,"first_token_order":1,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":143,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugz_KLeMk6Erbs83BQZ4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"서재초등학교","token_norm":"서재초등학교","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":2,"token_len":6,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":144,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugz_KLeMk6Erbs83BQZ4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"운동장","token_norm":"운동장","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":3,"token_len":3,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":145,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugz_KLeMk6Erbs83BQZ4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"사용","token_norm":"사용","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":4,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":146,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugz_KLeMk6Erbs83BQZ4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"시청각실","token_norm":"시청각실","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":5,"token_len":4,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":147,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugz_KLeMk6Erbs83BQZ4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"체육","token_norm":"체육","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":6,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":148,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugz_KLeMk6Erbs83BQZ4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"수업","token_norm":"수업","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":7,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":149,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugz_KLeMk6Erbs83BQZ4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"아이","token_norm":"아이","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":8,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":150,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugz_KLeMk6Erbs83BQZ4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"증축","token_norm":"증축","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":9,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":151,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw40z9nI2HLnG9yNTt4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"한국","token_norm":"한국","pos":"NNP","token_type":"MORPHEME","token_count":1,"first_token_order":1,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":152,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw40z9nI2HLnG9yNTt4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"교육","token_norm":"교육","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":2,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":153,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgyfKg3w_Kmv3UjKrZ94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"초딩","token_norm":"초딩","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":1,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":154,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgyfKg3w_Kmv3UjKrZ94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"나중","token_norm":"나중","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":2,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":155,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgyfKg3w_Kmv3UjKrZ94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"사회","token_norm":"사회","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":3,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":156,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgyfKg3w_Kmv3UjKrZ94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"생각","token_norm":"생각","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":4,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":157,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgyfKg3w_Kmv3UjKrZ94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"작정","token_norm":"작정","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":5,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":158,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgyPztjxAPp9GE0umcx4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"부모","token_norm":"부모","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":1,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":159,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"체육","token_norm":"체육","pos":"NNG","token_type":"MORPHEME","token_count":2,"first_token_order":1,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":160,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"활동","token_norm":"활동","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":2,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":161,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"자체","token_norm":"자체","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":3,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":162,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"기피","token_norm":"기피","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":4,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":163,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"학교","token_norm":"학교","pos":"NNG","token_type":"MORPHEME","token_count":3,"first_token_order":5,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":164,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"연락","token_norm":"연락","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":6,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":165,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"항의","token_norm":"항의","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":7,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":166,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"방과","token_norm":"방과","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":9,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":167,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"운동장","token_norm":"운동장","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":10,"token_len":3,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":168,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"사교육비","token_norm":"사교육비","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":11,"token_len":4,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":169,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"형국","token_norm":"형국","pos":"NNG","token_type":"MORPHEME","token_count":2,"first_token_order":12,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":170,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"기존","token_norm":"기존","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":13,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":171,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"태권도","token_norm":"태권도","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":14,"token_len":3,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":172,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"유도","token_norm":"유도","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":15,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":173,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"가라데","token_norm":"가라데","pos":"NNP","token_type":"MORPHEME","token_count":1,"first_token_order":16,"token_len":3,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":174,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"복싱","token_norm":"복싱","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":17,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":175,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"테니스","token_norm":"테니스","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":18,"token_len":3,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":176,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"야구","token_norm":"야구","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":19,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":177,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"농구","token_norm":"농구","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":20,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":178,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"축구","token_norm":"축구","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":21,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":179,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"수영","token_norm":"수영","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":22,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":180,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"비용","token_norm":"비용","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":23,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":181,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"인근","token_norm":"인근","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":25,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":182,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"아파트","token_norm":"아파트","pos":"NNG","token_type":"MORPHEME","token_count":2,"first_token_order":26,"token_len":3,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":183,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"대부분","token_norm":"대부분","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":27,"token_len":3,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":184,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"아이","token_norm":"아이","pos":"NNG","token_type":"MORPHEME","token_count":2,"first_token_order":28,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":185,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"근처","token_norm":"근처","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":29,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":186,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"단지","token_norm":"단지","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":31,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":187,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"민원","token_norm":"민원","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":33,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":188,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"대회","token_norm":"대회","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":35,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":189,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"소풍","token_norm":"소풍","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":36,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":190,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"취소","token_norm":"취소","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":37,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":191,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"교단","token_norm":"교단","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":39,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":192,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugyza8pd9rE5e44pdJN4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"학생","token_norm":"학생","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":40,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":193,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgwtNdqLr0TahYgC3Il4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"아이","token_norm":"아이","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":1,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":194,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgwtNdqLr0TahYgC3Il4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"초등학교","token_norm":"초등학교","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":2,"token_len":4,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":195,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgwtNdqLr0TahYgC3Il4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"어른","token_norm":"어른","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":3,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":196,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgwtNdqLr0TahYgC3Il4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"주차장","token_norm":"주차장","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":4,"token_len":3,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":197,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgwtNdqLr0TahYgC3Il4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"아이러니","token_norm":"아이러니","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":5,"token_len":4,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":198,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugxx4Y2mLIw9lK-TwBB4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"체육","token_norm":"체육","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":1,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":199,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugxx4Y2mLIw9lK-TwBB4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"활동","token_norm":"활동","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":2,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":200,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugxx4Y2mLIw9lK-TwBB4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"공간","token_norm":"공간","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":3,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":201,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugxx4Y2mLIw9lK-TwBB4AaABAg.ASqK5k5t8iVASqRY6Sf27g","parent_comment_id":"Ugxx4Y2mLIw9lK-TwBB4AaABAg","comment_kind":"REPLY","token_text":"세종시","token_norm":"세종시","pos":"NNP","token_type":"MORPHEME","token_count":1,"first_token_order":1,"token_len":3,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":202,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugxx4Y2mLIw9lK-TwBB4AaABAg.ASqK5k5t8iVASqRY6Sf27g","parent_comment_id":"Ugxx4Y2mLIw9lK-TwBB4AaABAg","comment_kind":"REPLY","token_text":"사건","token_norm":"사건","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":2,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":203,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw-8KAxLs55msPFKPd4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"미필","token_norm":"미필","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":1,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":204,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw-8KAxLs55msPFKPd4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"학교","token_norm":"학교","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":2,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":205,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw-8KAxLs55msPFKPd4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"전시","token_norm":"전시","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":3,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":206,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw-8KAxLs55msPFKPd4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"군인","token_norm":"군인","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":4,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":207,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw-8KAxLs55msPFKPd4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"막사","token_norm":"막사","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":5,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":208,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw-8KAxLs55msPFKPd4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"운동장","token_norm":"운동장","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":6,"token_len":3,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":209,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgwCgZ0ZIty_ashGxel4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"체육","token_norm":"체육","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":1,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":210,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgwCgZ0ZIty_ashGxel4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"학교","token_norm":"학교","pos":"NNG","token_type":"MORPHEME","token_count":2,"first_token_order":2,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":211,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgwCgZ0ZIty_ashGxel4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"운동장","token_norm":"운동장","pos":"NNG","token_type":"MORPHEME","token_count":2,"first_token_order":3,"token_len":3,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":212,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgwCgZ0ZIty_ashGxel4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"부모","token_norm":"부모","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":4,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":213,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgwCgZ0ZIty_ashGxel4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"난리","token_norm":"난리","pos":"NNG","token_type":"MORPHEME","token_count":2,"first_token_order":5,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":214,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgwCgZ0ZIty_ashGxel4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"방법","token_norm":"방법","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":7,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":215,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgwCgZ0ZIty_ashGxel4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"등교","token_norm":"등교","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":8,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":216,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgwCgZ0ZIty_ashGxel4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"시간","token_norm":"시간","pos":"NNG","token_type":"MORPHEME","token_count":2,"first_token_order":9,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":217,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgwCgZ0ZIty_ashGxel4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"학부모","token_norm":"학부모","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":11,"token_len":3,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":218,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgwCgZ0ZIty_ashGxel4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"교문","token_norm":"교문","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":12,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":219,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgxDsMsnkBes7b_n7kF4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"운동장","token_norm":"운동장","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":1,"token_len":3,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":220,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgxDsMsnkBes7b_n7kF4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"필요","token_norm":"필요","pos":"NNG","token_type":"MORPHEME","token_count":2,"first_token_order":2,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":221,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgxDsMsnkBes7b_n7kF4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"체육관","token_norm":"체육관","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":4,"token_len":3,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":222,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgxDsMsnkBes7b_n7kF4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"확충","token_norm":"확충","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":5,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":223,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgybcKQTocA_tpWtfw94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"운동장","token_norm":"운동장","pos":"NNG","token_type":"MORPHEME","token_count":2,"first_token_order":1,"token_len":3,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":224,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgybcKQTocA_tpWtfw94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"체육관","token_norm":"체육관","pos":"NNG","token_type":"MORPHEME","token_count":2,"first_token_order":2,"token_len":3,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":225,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgybcKQTocA_tpWtfw94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"체육","token_norm":"체육","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":3,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":226,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgybcKQTocA_tpWtfw94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"수업","token_norm":"수업","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":4,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":227,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgybcKQTocA_tpWtfw94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"사고","token_norm":"사고","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":5,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":228,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgybcKQTocA_tpWtfw94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"교사","token_norm":"교사","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":6,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":229,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgybcKQTocA_tpWtfw94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"책임","token_norm":"책임","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":7,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":230,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgybcKQTocA_tpWtfw94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"교실","token_norm":"교실","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":10,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":231,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugx2YuwzBvjeZNhM4l54AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"주차장","token_norm":"주차장","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":1,"token_len":3,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":232,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugx2YuwzBvjeZNhM4l54AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"크네","token_norm":"크네","pos":"NNP","token_type":"MORPHEME","token_count":1,"first_token_order":2,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":233,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgxGeWWTqtCkGrxkYrx4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"체력","token_norm":"체력","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":1,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":234,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"UgxGeWWTqtCkGrxkYrx4AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"국력","token_norm":"국력","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":2,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":235,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw48047GRob0vYOQW94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"학교","token_norm":"학교","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":1,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":236,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw48047GRob0vYOQW94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"운동장","token_norm":"운동장","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":2,"token_len":3,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":237,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw48047GRob0vYOQW94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"폐지","token_norm":"폐지","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":3,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":238,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw48047GRob0vYOQW94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"주장","token_norm":"주장","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":4,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":239,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw48047GRob0vYOQW94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"지하","token_norm":"지하","pos":"NNG","token_type":"MORPHEME","token_count":2,"first_token_order":5,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":240,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw48047GRob0vYOQW94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"거대","token_norm":"거대","pos":"NNG","token_type":"MORPHEME","token_count":2,"first_token_order":6,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":241,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw48047GRob0vYOQW94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"어린이","token_norm":"어린이","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":7,"token_len":3,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":242,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw48047GRob0vYOQW94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"시설","token_norm":"시설","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":8,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":243,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw48047GRob0vYOQW94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"체육","token_norm":"체육","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":9,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":244,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw48047GRob0vYOQW94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"활동","token_norm":"활동","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":10,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":245,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw48047GRob0vYOQW94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"중요","token_norm":"중요","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":11,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":246,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw48047GRob0vYOQW94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"맨땅","token_norm":"맨땅","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":12,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":247,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw48047GRob0vYOQW94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"덤블링","token_norm":"덤블링","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":15,"token_len":3,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":248,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw48047GRob0vYOQW94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"콜로세움","token_norm":"콜로세움","pos":"NNP","token_type":"MORPHEME","token_count":1,"first_token_order":16,"token_len":4,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":249,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw48047GRob0vYOQW94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"수영장","token_norm":"수영장","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":17,"token_len":3,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":250,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw48047GRob0vYOQW94AaABAg","parent_comment_id":null,"comment_kind":"TOP","token_text":"준비","token_norm":"준비","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":18,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":251,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw48047GRob0vYOQW94AaABAg.AT4XjJAI6whATBtGdDJ3Px","parent_comment_id":"Ugw48047GRob0vYOQW94AaABAg","comment_kind":"REPLY","token_text":"초등학생","token_norm":"초등학생","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":1,"token_len":4,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}, {"token_id":252,"run_id":"381ff056-b3d2-4316-8584-2c9ed90cabd8","method_id":"MORPH_KIWI_V1","video_id":"8kFnA0oxFeI","comment_id":"Ugw48047GRob0vYOQW94AaABAg.AT4XjJAI6whATBtGdDJ3Px","parent_comment_id":"Ugw48047GRob0vYOQW94AaABAg","comment_kind":"REPLY","token_text":"대처","token_norm":"대처","pos":"NNG","token_type":"MORPHEME","token_count":1,"first_token_order":2,"token_len":2,"create_dt":"2026-05-09 23:11:42","update_dt":"2026-05-09 23:11:42"}]
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
    if (['1', '2', '3', '4', '5', '6'].includes(key)) switchScene(key);
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
                textStyle: { shadowBlur: 10, shadowColor: 'rgba(0, 0, 0, 0.3)' }
            },
            data: sortedData
        }]
    };
    myChart.setOption(option);
}