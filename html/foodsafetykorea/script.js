let filtered = [];
let currPg = 1;
let limit = 10;
const groupSize = 10;

document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => {
        filtered = [...foodsafetyData];
        render();
        document.getElementById('loadingOverlay').style.display = 'none';
    }, 400);
});

function handleSearch() {
    const reg = document.getElementById('sReg').value.toLowerCase();
    const bssh = document.getElementById('sBssh').value.toLowerCase();
    const lcns = document.getElementById('sLcns').value;
    const addr = document.getElementById('sAddr').value.toLowerCase();
    const stat = document.getElementById('sStatus').value;

    filtered = foodsafetyData.filter(d => {
        return (d['지역'] || '').toLowerCase().includes(reg) &&
            (d['업체명'] || '').toLowerCase().includes(bssh) &&
            (d['인허가번호'] || '').includes(lcns) &&
            (d['소재지'] || '').toLowerCase().includes(addr) &&
            (!stat || d['영업상태'] === stat);
    });
    currPg = 1; render();
}

function changeLimit() {
    limit = parseInt(document.getElementById('sLimit').value);
    currPg = 1; render();
}

function jump() {
    const target = parseInt(document.getElementById('jumpNum').value);
    const total = Math.ceil(filtered.length / limit);
    if (target >= 1 && target <= total) {
        currPg = target; render(); window.scrollTo(0, 0);
    } else { alert("유효한 페이지 번호를 입력하세요."); }
}

function render() {
    const tbody = document.getElementById('listBody');
    tbody.innerHTML = '';
    const start = (currPg - 1) * limit;
    const current = filtered.slice(start, start + limit);

    current.forEach(d => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${d['번호'] || ''}</td><td>${d['지역'] || ''}</td><td>${d['인허가번호'] || ''}</td>
            <td style="text-align:left;"><a class="company-link" onclick="showDetail('${d['상세키']}')">${d['업체명'] || ''}</a></td>
            <td>${d['업종'] || ''}</td><td>${d['대표자'] || ''}</td>
            <td style="text-align:left;" title="${d['소재지']}">${d['소재지'] || ''}</td>
            <td>${d['인허가기관'] || ''}</td><td><b style="color:${d['영업상태'] === '정상' ? '#0070bd' : '#f44336'}">${d['영업상태'] || ''}</b></td>
            <td>${d['비고'] || ''}</td>
        `;
        tbody.appendChild(tr);
    });
    renderPaginate();
    document.getElementById('resCnt').innerText = filtered.length.toLocaleString();
    document.getElementById('totalPg').innerText = Math.ceil(filtered.length / limit);
}

function renderPaginate() {
    const wrap = document.getElementById('pagination');
    wrap.innerHTML = '';
    const total = Math.ceil(filtered.length / limit);
    if (total <= 0) return;
    const group = Math.ceil(currPg / groupSize);
    const start = (group - 1) * groupSize + 1;
    const end = Math.min(start + groupSize - 1, total);
    const btn = (lbl, pg, dis = false, act = false) => {
        const b = document.createElement('button');
        b.innerHTML = lbl; b.disabled = dis;
        if (act) b.classList.add('active');
        b.onclick = () => { currPg = pg; render(); window.scrollTo(0,0); };
        wrap.appendChild(b);
    };
    btn('<<', 1, currPg === 1); btn('<', Math.max(1, start - 1), currPg === 1);
    for (let i = start; i <= end; i++) btn(i, i, false, i === currPg);
    btn('>', Math.min(total, end + 1), currPg === total); btn('>>', total, currPg === total);
}

function openTextPopup(text) {
    if(!text || text === '-') return;
    document.getElementById('popupContent').innerText = text;
    document.getElementById('textPopup').style.display = 'flex';
}
function closePopup() { document.getElementById('textPopup').style.display = 'none'; }

function showDetail(key) {
    const d = foodsafetyData.find(x => x['상세키'] === key);
    if (!d) return;
    const body = document.getElementById('modalBody');
    const haccp = (d['HACCP 인증 정보'] || []).map(h => `
        <tr>
            <td class="clickable-cell" onclick="openTextPopup('${h.관할기관}')">${h.관할기관 || '-'}</td>
            <td>${h.HACCP인증번호 || '-'}</td>
            <td class="clickable-cell" onclick="openTextPopup('${h.품목}')">${h.품목 || '-'}</td>
            <td>${h.인증일 || '-'}</td><td>${h.인증종료일 || '-'}</td><td>${h['의무/자율'] || '-'}</td>
        </tr>
    `).join('');
    const prods = (d['제조품목 정보'] || []).map(p => `
        <tr>
            <td>${p.품목제조번호 || '-'}</td><td>${p['식품의 유형'] || '-'}</td>
            <td class="clickable-cell" onclick="openTextPopup('${p.제품명}')">${p.제품명 || '-'}</td>
            <td>${p.일자 || '-'}</td>
        </tr>
    `).join('');
    body.innerHTML = `
        <div class="modal-title">상세정보</div>
        <p><b>업체명:</b> <span style="color:var(--primary)">${d['업체명']}</span></p>
        <h3 class="sub-h3">인허가 정보</h3>
        <table class="info-table">
            <colgroup><col style="width:18%"><col style="width:32%"><col style="width:18%"><col style="width:32%"></colgroup>
            <tr><th>업체명</th><td class="clickable-cell" onclick="openTextPopup('${d['업체명']}')">${d['업체명']}</td><th>영업 종류</th><td>${d['업종']}</td></tr>
            <tr><th>인허가번호</th><td>${d['인허가번호']}</td><th>전화번호</th><td>${d['인허가 정보']?.전화번호 || '-'}</td></tr>
            <tr><th>소재지</th><td colspan="3" class="clickable-cell" onclick="openTextPopup('${d['소재지']}')">${d['소재지']}</td></tr>
            <tr><th>대표자</th><td>${d['대표자']}</td><th>인허가기관</th><td>${d['인허가기관']}</td></tr>
        </table>
        <h3 class="sub-h3">HACCP 인증 정보</h3>
        <table class="info-table"><colgroup><col style="width:25%"><col style="width:18%"><col style="width:25%"><col style="width:11%"><col style="width:11%"><col style="width:10%"></colgroup>
            <thead><tr style="background:#f1f5f9"><th>관할기관</th><th>인증번호</th><th>품목</th><th>인증일</th><th>종료일</th><th>구분</th></tr></thead>
            <tbody>${haccp || '<tr><td colspan="6" style="text-align:center;">정보 없음</td></tr>'}</tbody>
        </table>
        <h3 class="sub-h3">제조품목 정보</h3>
        <table class="info-table"><colgroup><col style="width:20%"><col style="width:20%"><col style="width:45%"><col style="width:15%"></colgroup>
            <thead><tr style="background:#f1f5f9"><th>품목번호</th><th>유형</th><th>제품명</th><th>일자</th></tr></thead>
            <tbody>${prods || '<tr><td colspan="4" style="text-align:center;">정보 없음</td></tr>'}</tbody>
        </table>
    `;
    document.getElementById('detailModal').style.display = 'flex';
}
function closeModal() { document.getElementById('detailModal').style.display = 'none'; }
window.onclick = (e) => {
    if (e.target.id === 'textPopup') closePopup();
    if (e.target.className === 'modal') closeModal();
};