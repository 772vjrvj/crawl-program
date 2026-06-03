const youtubeVideoData = [{
    "video_id": "8kFnA0oxFeI",
    "title": "[자막뉴스] 요즘 초등학교에서 점점 좁아지고 있다는 장소 / KBS 2026.02.05.",
    "channel_title": "KBS News",
    "channel_id": "UCcQTRi69dsVYHN3exePtZ1A",
    "video_url": "https://www.youtube.com/watch?v=8kFnA0oxFeI",
    "thumbnail_url": "https://i.ytimg.com/vi/8kFnA0oxFeI/maxresdefault.jpg",
    "view_count": 4319,
    "like_count": 30,
    "comment_count": 18
}];

document.addEventListener("DOMContentLoaded", () => {
    renderScene1(youtubeVideoData[0]);

    document.addEventListener("keydown", (e) => {
        const key = e.key.toLowerCase();

        if (['1', '2', '3', '4'].includes(key)) switchScene(key);

        // 키보드 q, w, e, r 을 누르면 좋댓구알 애니메이션 실행
        if (key === 'q') crackEgg('cta-q');
        if (key === 'w') crackEgg('cta-w');
        if (key === 'e') crackEgg('cta-e');
        if (key === 'r') crackEgg('cta-r');
    });
});

function crackEgg(id) {
    const target = document.getElementById(id);
    if (target && !target.classList.contains('cracked')) {
        target.classList.add('cracked');
    }
}

function switchScene(sceneNumber) {
    const allScenes = document.querySelectorAll('.scene');
    allScenes.forEach(scene => scene.classList.remove('active'));

    const targetScene = document.getElementById(`scene-${sceneNumber}`);
    if (targetScene) {
        targetScene.classList.add('active');
        if (sceneNumber === '1') animateNumbers(youtubeVideoData[0]);
    }
}

function renderScene1(data) {
    if (!data) return;
    document.getElementById('vid-thumb').src = data.thumbnail_url;
    document.getElementById('vid-title').textContent = data.title;
    document.getElementById('vid-channel').textContent = data.channel_title;
    animateNumbers(data);
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