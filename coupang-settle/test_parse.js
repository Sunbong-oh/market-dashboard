// 파싱 로직 테스트: node coupang-settle/test_parse.js
const assert = require('assert');
const p = require('./coupang_settle.user.js');

const cfg = { parentKeywords: ['행복아파트'], myKeywords: ['푸른 빌라'] };

const detailParent = `<html><body><script>var x={"totalPrice":99}</script>
  <div>주문일자 2026. 9. 15</div><div>주문번호 31000123456789</div>
  <div class="addr"><span>받는사람</span> 김부모 <span>배송주소</span> 서울시 OO구 행복로 12, 행복 아파트 101동 1203호</div>
  <div>상품금액 32,000 원</div><div>총 결제금액 <strong>30,500</strong>원</div>
  <div>환불 완료 금액 5,000 원</div></body></html>`;
const r1 = p.parseDetail(detailParent, cfg);
assert.deepStrictEqual([r1.date, r1.amount, r1.refund, r1.cls], ['2026-09-15', 30500, 5000, 'parent']);
assert.ok(r1.address.includes('행복로'));

const detailMine = `<div>2026.09.03 주문</div><div>배송지: 경기도 OO시 푸른빌라 202호</div><div>결제금액 12,900원</div>`;
const r2 = p.parseDetail(detailMine, cfg);
assert.deepStrictEqual([r2.date, r2.amount, r2.refund, r2.cls], ['2026-09-03', 12900, 0, 'mine']);

// 클라이언트 렌더링(데이터가 script JSON 안에만 있는 경우)
const detailJson = `<div id="root"></div><script>window.__D={"orderDate":"주문일 2026-08-30","addr":"\\uD589\\uBCF5\\uC544\\uD30C\\uD2B8 3동","txt":"총 결제금액 8,000원"}</script>`;
const r3 = p.parseDetail(detailJson, cfg);
assert.deepStrictEqual([r3.date, r3.amount, r3.cls], ['2026-08-30', 8000, 'parent']);

const unknown = p.parseDetail('<div>주문일 2026.07.01 결제금액 1,000원 배송지 부산</div>', cfg);
assert.strictEqual(unknown.cls, 'unknown');

const list = `<a href="https://mc.coupang.com/ssr/desktop/order/31000123456789">상세</a>
  <script>{"orderId":31000999999999,"x":1}</script> 주문번호 31000111111111`;
assert.deepStrictEqual(p.findOrderIds(list).sort(), ['31000111111111', '31000123456789', '31000999999999']);

const orders = {
  a: { ...r1 }, b: { ...r2 },
  c: { date: '2026-09-20', amount: 10000, refund: 0, cls: 'unknown', manualCls: 'parent', manualAmount: 9000 },
};
const ms = p.monthlySummary(orders);
assert.strictEqual(ms['2026-09'].parent, 25500 + 9000);
assert.strictEqual(ms['2026-09'].mine, 12900);
const msg = p.settlementMessage(orders, '2026-09');
assert.ok(msg.includes('합계: 34,500원 (2건)'), msg);
console.log(msg);
console.log('all tests passed');
