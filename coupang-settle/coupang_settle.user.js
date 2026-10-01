// ==UserScript==
// @name         쿠팡 부모님댁 배송 월별 정산
// @namespace    https://github.com/sunbong-oh/market-dashboard
// @version      0.1.0
// @description  쿠팡 주문목록에서 주문별 배송지를 확인해 부모님댁으로 간 결제액을 월별로 집계한다.
// @match        https://mc.coupang.com/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==
/*
 * 사용법은 같은 폴더의 README.md 참고.
 * 쿠팡 페이지 구조가 바뀌어도 최대한 버티도록 DOM 클래스 대신 "화면 텍스트"를 정규식으로 읽는다.
 * 금액/분류를 못 읽은 주문은 표에서 직접 고칠 수 있다(수정값은 다시 수집해도 유지).
 */
(function () {
  'use strict';

  const STORE_KEY = 'cpSettle.v1';
  const DEFAULT_CONFIG = {
    parentKeywords: [], // 부모님댁 주소에만 있는 단어 (예: "OO아파트", "OO로 12")
    myKeywords: [],     // 내 집 주소에만 있는 단어
    detailUrl: 'https://mc.coupang.com/ssr/desktop/order/{id}',
    delayMs: 800,
  };

  // ---------------------------------------------------------------- 파싱 (순수 함수)
  function decodeEntities(s) {
    return s
      .replace(/&nbsp;/g, ' ').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"').replace(/&#39;|&apos;/g, "'")
      .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(+n))
      .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCharCode(parseInt(n, 16)))
      .replace(/&amp;/g, '&');
  }

  // 화면에 보이는 텍스트 (script/style 제외)
  function visibleText(html) {
    return decodeEntities(html
      .replace(/<(script|style|noscript)\b[\s\S]*?<\/\1>/gi, ' ')
      .replace(/<[^>]+>/g, ' ')).replace(/\s+/g, ' ').trim();
  }

  // 스크립트 안 JSON까지 포함한 텍스트 (클라이언트 렌더링 페이지 대비)
  function rawText(html) {
    return decodeEntities(html
      .replace(/\\u([0-9a-fA-F]{4})/g, (_, h) => String.fromCharCode(parseInt(h, 16)))
      .replace(/<[^>]+>/g, ' ')).replace(/\s+/g, ' ').trim();
  }

  const num = (s) => parseInt(String(s).replace(/[^\d]/g, ''), 10);
  const squash = (s) => String(s).replace(/\s+/g, '').toLowerCase();

  function firstMatch(text, patterns) {
    for (const re of patterns) {
      const m = text.match(re);
      if (m) return m;
    }
    return null;
  }

  function parseAmount(text) {
    const m = firstMatch(text, [
      /총\s*결제\s*금액[^\d원]{0,20}([\d,]+)\s*원/,
      /최종\s*결제\s*금액[^\d원]{0,20}([\d,]+)\s*원/,
      /결제\s*금액[^\d원]{0,20}([\d,]+)\s*원/,
    ]);
    return m ? num(m[1]) : null;
  }

  function parseRefund(text) {
    let total = 0;
    const re = /(?:환불|취소)\s*(?:완료|예정)?\s*금액[^\d원]{0,20}([\d,]+)\s*원/g;
    let m;
    const seen = new Set();
    while ((m = re.exec(text))) {
      // 같은 금액이 요약/상세에 중복 표기되는 경우가 많아 첫 번째 값만 쓴다.
      if (!seen.size) total = num(m[1]);
      seen.add(m[1]);
    }
    return total;
  }

  function parseDate(text) {
    const m = firstMatch(text, [
      /주문\s*(?:일자|일시|날짜|일)\s*:?\s*(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})/,
      /(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.?\s*주문/,
      /(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})/,
    ]);
    if (!m) return null;
    return `${m[1]}-${String(m[2]).padStart(2, '0')}-${String(m[3]).padStart(2, '0')}`;
  }

  function parseAddressSnippet(text) {
    const m = firstMatch(text, [
      /(?:배송\s*주소|받는\s*주소|배송지)\s*:?\s*(.{5,60})/,
      /주소\s*:?\s*(.{5,60})/,
    ]);
    return m ? m[1].trim() : '';
  }

  function classify(text, cfg) {
    const t = squash(text);
    const hit = (kws) => kws.some((k) => k && t.includes(squash(k)));
    const p = hit(cfg.parentKeywords || []);
    const me = hit(cfg.myKeywords || []);
    if (p && !me) return 'parent';
    if (me && !p) return 'mine';
    return 'unknown';
  }

  function parseDetail(html, cfg) {
    const vis = visibleText(html);
    const raw = rawText(html);
    const pick = (fn) => { const v = fn(vis); return v !== null && v !== '' ? v : fn(raw); };
    let cls = classify(vis, cfg);
    if (cls === 'unknown') cls = classify(raw, cfg);
    return {
      date: pick(parseDate),
      amount: pick(parseAmount),
      refund: parseRefund(vis) || parseRefund(raw),
      address: pick(parseAddressSnippet),
      cls,
    };
  }

  // 주문목록 페이지 HTML에서 주문번호 찾기
  function findOrderIds(html) {
    const ids = new Set();
    const patterns = [
      /\/order\/(?:detail\/)?(\d{10,20})/g,
      /orderId[\\"'\s]*[:=][\\"'\s]*(\d{10,20})/gi,
      /주문\s*번호\s*:?\s*(\d{10,20})/g,
    ];
    for (const re of patterns) {
      let m;
      while ((m = re.exec(html))) ids.add(m[1]);
    }
    return [...ids];
  }

  function effective(o) {
    const amount = o.manualAmount != null ? o.manualAmount : (o.amount || 0);
    const refund = o.manualRefund != null ? o.manualRefund : (o.refund || 0);
    return {
      date: o.manualDate || o.date || '',
      cls: o.manualCls || o.cls || 'unknown',
      amount, refund, net: amount - refund,
    };
  }

  function monthlySummary(orders) {
    const months = {};
    for (const o of Object.values(orders)) {
      const e = effective(o);
      const ym = e.date ? e.date.slice(0, 7) : '날짜없음';
      const row = months[ym] || (months[ym] = { parent: 0, mine: 0, unknown: 0, parentCount: 0, unknownCount: 0 });
      row[e.cls] += e.net;
      if (e.cls === 'parent') row.parentCount++;
      if (e.cls === 'unknown') row.unknownCount++;
    }
    return months;
  }

  function settlementMessage(orders, ym) {
    const list = Object.entries(orders)
      .map(([id, o]) => ({ id, ...effective(o) }))
      .filter((e) => e.cls === 'parent' && e.date.startsWith(ym))
      .sort((a, b) => a.date.localeCompare(b.date));
    const won = (n) => n.toLocaleString('ko-KR') + '원';
    const total = list.reduce((s, e) => s + e.net, 0);
    const [y, m] = ym.split('-');
    const lines = [`[쿠팡 정산] ${y}년 ${+m}월 부모님댁 배송분`];
    for (const e of list) {
      const md = `${+e.date.slice(5, 7)}/${+e.date.slice(8, 10)}`;
      lines.push(`- ${md} ${won(e.net)}${e.refund ? ` (환불 ${won(e.refund)} 차감)` : ''}`);
    }
    lines.push(`합계: ${won(total)} (${list.length}건)`);
    return lines.join('\n');
  }

  const api = {
    visibleText, rawText, parseAmount, parseRefund, parseDate, parseAddressSnippet,
    classify, parseDetail, findOrderIds, effective, monthlySummary, settlementMessage,
  };
  if (typeof module !== 'undefined' && module.exports) { module.exports = api; return; }

  // ---------------------------------------------------------------- 저장소
  function load() {
    try {
      const s = JSON.parse(localStorage.getItem(STORE_KEY) || '{}');
      return { config: { ...DEFAULT_CONFIG, ...(s.config || {}) }, orders: s.orders || {} };
    } catch (e) {
      return { config: { ...DEFAULT_CONFIG }, orders: {} };
    }
  }
  function save() { localStorage.setItem(STORE_KEY, JSON.stringify(state)); }
  let state = load();

  // ---------------------------------------------------------------- 수집
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function detailUrlFor(id) {
    const a = [...document.querySelectorAll('a[href]')].find((el) => el.href.includes(id) && /order/i.test(el.href));
    return a ? a.href : state.config.detailUrl.replace('{id}', id);
  }

  async function fetchOrder(id) {
    const url = detailUrlFor(id);
    const res = await fetch(url, { credentials: 'include' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    if (/login/i.test(res.url)) throw new Error('로그인 필요');
    const html = await res.text();
    const parsed = parseDetail(html, state.config);
    const prev = state.orders[id] || {};
    state.orders[id] = { ...prev, ...parsed, url, fetchedAt: new Date().toISOString(), error: null };
  }

  let busy = false;
  async function collect(ids, force) {
    if (busy) return;
    busy = true;
    const todo = ids.filter((id) => force || !state.orders[id] || state.orders[id].error);
    let done = 0;
    for (const id of todo) {
      setStatus(`상세 조회 중 ${++done}/${todo.length} (주문 ${id})`);
      try {
        await fetchOrder(id);
      } catch (e) {
        state.orders[id] = { ...(state.orders[id] || {}), error: String(e.message || e) };
      }
      save();
      render();
      await sleep(state.config.delayMs);
    }
    busy = false;
    setStatus(todo.length ? `완료: ${todo.length}건 조회 (이미 있던 주문 ${ids.length - todo.length}건은 건너뜀)`
      : `이 페이지 주문 ${ids.length}건은 모두 수집되어 있음`);
  }

  // 키워드를 바꾼 뒤 다시 조회하지 않고 재분류하려면 원문이 필요하므로 재조회한다.
  async function reclassifyAll() { await collect(Object.keys(state.orders), true); }

  // ---------------------------------------------------------------- UI
  const host = document.createElement('div');
  host.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:2147483647;';
  const root = host.attachShadow({ mode: 'open' });
  document.body.appendChild(host);

  root.innerHTML = `
  <style>
    :host{all:initial;font-family:-apple-system,"Malgun Gothic",sans-serif;font-size:13px;color:#222}
    button{font:inherit;cursor:pointer;border:1px solid #bbb;background:#fff;border-radius:6px;padding:4px 10px}
    button.primary{background:#346aff;color:#fff;border-color:#346aff}
    #fab{border-radius:20px;padding:8px 14px;box-shadow:0 2px 8px rgba(0,0,0,.25)}
    #panel{display:none;width:min(760px,calc(100vw - 32px));max-height:80vh;overflow:auto;background:#fff;
      border:1px solid #ccc;border-radius:10px;box-shadow:0 4px 24px rgba(0,0,0,.25);padding:14px}
    h3{margin:0 0 8px;font-size:15px} h4{margin:14px 0 6px;font-size:13px}
    .row{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:4px 0}
    input[type=text]{font:inherit;padding:3px 6px;border:1px solid #bbb;border-radius:4px;width:100%;box-sizing:border-box}
    label{display:block;margin:4px 0 2px;color:#555}
    table{border-collapse:collapse;width:100%;margin-top:4px;font-size:13px}
    select,td button{font:inherit}
    th,td{border-bottom:1px solid #eee;padding:3px 5px;text-align:left;white-space:nowrap}
    td.num,th.num{text-align:right}
    td.addr{white-space:normal;color:#666;font-size:12px;max-width:220px}
    td input{width:80px;font:inherit;padding:1px 4px}
    tr.parent{background:#fff7e6} tr.unknown{background:#ffecec}
    #status{color:#346aff;margin:6px 0;min-height:1em}
    .muted{color:#888;font-size:12px}
  </style>
  <button id="fab" class="primary">💰 쿠팡 정산</button>
  <div id="panel">
    <div class="row" style="justify-content:space-between">
      <h3>쿠팡 부모님댁 배송 월별 정산</h3><button id="close">닫기</button>
    </div>
    <details id="cfgBox"><summary>설정 (주소 키워드)</summary>
      <label>부모님댁 주소 키워드 (쉼표로 구분, 예: 행복아파트, 행복로 12)</label>
      <input type="text" id="pkw">
      <label>내 집 주소 키워드 (쉼표로 구분)</label>
      <input type="text" id="mkw">
      <p class="muted">이름은 주문자 칸에도 나오므로 쓰지 말고, 아파트명·도로명처럼 그 주소에만 있는 단어를 쓰세요.</p>
      <div class="row"><button id="saveCfg">저장</button><button id="recls">저장 후 전체 다시 분류</button></div>
    </details>
    <div class="row">
      <button id="collect" class="primary">이 페이지 주문 수집</button>
      <button id="csv">CSV 내보내기</button>
      <button id="reset">전체 초기화</button>
    </div>
    <div class="muted">주문목록에서 페이지/연도를 넘기며 이 버튼을 누르면 누적됩니다. 이미 수집한 주문은 건너뜁니다.</div>
    <div id="status"></div>
    <h4>월별 합계 (환불 차감 후)</h4>
    <table id="months"></table>
    <h4>주문 목록 <span class="muted">— 분류/금액이 틀리면 직접 고치세요</span></h4>
    <table id="orders"></table>
  </div>`;

  const $ = (s) => root.querySelector(s);
  const setStatus = (t) => { $('#status').textContent = t; };
  const won = (n) => (n || 0).toLocaleString('ko-KR');
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const CLS_LABEL = { parent: '부모님댁', mine: '내 집', unknown: '확인필요' };

  function render() {
    $('#pkw').value = state.config.parentKeywords.join(', ');
    $('#mkw').value = state.config.myKeywords.join(', ');
    if (!state.config.parentKeywords.length) $('#cfgBox').open = true;

    const months = monthlySummary(state.orders);
    const keys = Object.keys(months).sort().reverse();
    $('#months').innerHTML = `<tr><th>월</th><th class="num">부모님댁</th><th class="num">건수</th><th class="num">내 집</th><th>확인필요</th><th></th></tr>` +
      keys.map((k) => {
        const m = months[k];
        return `<tr><td>${k}</td><td class="num"><b>${won(m.parent)}</b></td><td class="num">${m.parentCount}</td>
          <td class="num">${won(m.mine)}</td><td>${m.unknownCount ? `⚠️ ${m.unknownCount}건` : ''}</td>
          <td><button data-msg="${k}">정산 메시지 복사</button></td></tr>`;
      }).join('');

    const rows = Object.entries(state.orders)
      .map(([id, o]) => ({ id, o, e: effective(o) }))
      .sort((a, b) => b.e.date.localeCompare(a.e.date));
    $('#orders').innerHTML = `<tr><th>주문일</th><th>주문번호</th><th>분류</th><th class="num">결제액</th><th class="num">환불</th><th>배송지(추출)</th></tr>` +
      rows.map(({ id, o, e }) => `<tr class="${e.cls}">
        <td><input data-id="${id}" data-f="manualDate" value="${esc(e.date)}" style="width:100px"></td>
        <td><a href="${esc(o.url || '#')}" target="_blank">${id}</a>${o.error ? ` <span title="${esc(o.error)}">❌</span>` : ''}</td>
        <td><select data-id="${id}" data-f="manualCls">${Object.entries(CLS_LABEL).map(([v, l]) =>
          `<option value="${v}"${v === e.cls ? ' selected' : ''}>${l}</option>`).join('')}</select></td>
        <td class="num"><input data-id="${id}" data-f="manualAmount" value="${e.amount}"></td>
        <td class="num"><input data-id="${id}" data-f="manualRefund" value="${e.refund}"></td>
        <td class="addr">${esc(o.address)}</td></tr>`).join('');
  }

  function saveConfig() {
    const split = (s) => s.split(',').map((x) => x.trim()).filter(Boolean);
    state.config.parentKeywords = split($('#pkw').value);
    state.config.myKeywords = split($('#mkw').value);
    save();
  }

  function exportCsv() {
    const header = ['주문일', '주문번호', '분류', '결제액', '환불', '정산액', '배송지'];
    const lines = [header.join(',')];
    for (const [id, o] of Object.entries(state.orders)) {
      const e = effective(o);
      lines.push([e.date, id, CLS_LABEL[e.cls], e.amount, e.refund, e.net, o.address || '']
        .map((v) => `"${String(v).replace(/"/g, '""')}"`).join(','));
    }
    const blob = new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `coupang_settle_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
  }

  $('#fab').onclick = () => { $('#panel').style.display = 'block'; $('#fab').style.display = 'none'; render(); };
  $('#close').onclick = () => { $('#panel').style.display = 'none'; $('#fab').style.display = ''; };
  $('#saveCfg').onclick = () => { saveConfig(); setStatus('설정 저장됨'); };
  $('#recls').onclick = () => { saveConfig(); reclassifyAll(); };
  $('#csv').onclick = exportCsv;
  $('#reset').onclick = () => {
    if (!confirm('수집한 주문과 수정 내역을 모두 지울까요? (주소 키워드 설정은 유지)')) return;
    state.orders = {}; save(); render(); setStatus('초기화됨');
  };
  $('#collect').onclick = () => {
    saveConfig();
    if (!state.config.parentKeywords.length) { setStatus('먼저 부모님댁 주소 키워드를 입력하세요.'); return; }
    const ids = findOrderIds(document.documentElement.outerHTML);
    if (!ids.length) { setStatus('이 페이지에서 주문번호를 찾지 못했습니다. 쿠팡 마이쿠팡 > 주문목록 페이지에서 눌러주세요.'); return; }
    collect(ids, false);
  };
  root.addEventListener('change', (ev) => {
    const el = ev.target;
    const id = el.dataset && el.dataset.id;
    if (!id) return;
    const f = el.dataset.f;
    state.orders[id][f] = f === 'manualAmount' || f === 'manualRefund' ? num(el.value) || 0 : el.value;
    save(); render();
  });
  root.addEventListener('click', async (ev) => {
    const ym = ev.target.dataset && ev.target.dataset.msg;
    if (!ym) return;
    const msg = settlementMessage(state.orders, ym);
    try { await navigator.clipboard.writeText(msg); setStatus('정산 메시지를 복사했습니다. 카톡에 붙여넣으세요.'); }
    catch (e) { prompt('복사해서 쓰세요', msg); }
  });
})();
