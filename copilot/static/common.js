// 两个页面共用的小工具
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmt = (v) => v == null ? '—' : v.toLocaleString('en-US', { maximumFractionDigits: v >= 1000 ? 0 : 2 });
const r1 = (v) => Math.round(v * 10) / 10 || 0;   // 四舍五入到 0.1，避免出现 -0.0
const pctStr = (v) => `${r1(v) > 0 ? '+' : ''}${r1(v).toFixed(1)}%`;
const price = (v) => (v >= 1000 ? fmt(v) : v >= 1 ? String(+v.toFixed(3)) : String(+v.toPrecision(4)));
const SAY = {
  green: 'BTC 多头排列，<br>海面风平浪静～',
  yellow: '呃……<br>BTC 方向不明',
  red: '哇！<br>BTC 空头排列了！',
};
const LIGHT_ICON = { red: '🔴', yellow: '🟡', green: '🟢' };

// 背景泡泡
(function () {
  const box = $('#bubbles');
  for (let i = 0; i < 14; i++) {
    const s = document.createElement('span');
    const size = 8 + Math.random() * 26;
    Object.assign(s.style, {
      left: `${Math.random() * 100}%`, width: `${size}px`, height: `${size}px`,
      animationDuration: `${12 + Math.random() * 18}s`, animationDelay: `${-Math.random() * 30}s`,
    });
    box.appendChild(s);
  }
})();

// 原创的粉色胖海星，表情跟着灯色变
function starSVG(light) {
  const pts = '100,26 124.7,74 178,82.7 139.9,121 148.2,174.3 100,150 51.8,174.3 60.1,121 22,82.7 75.3,74';
  const face = {
    green: `<path d="M80 80 q8 -7 16 0 M104 80 q8 -7 16 0" fill="none" stroke="#1a1a1a" stroke-width="4" stroke-linecap="round"/>
            <path d="M82 104 Q100 132 118 104 Z" fill="#c2185b" stroke="#1a1a1a" stroke-width="3.5" stroke-linejoin="round"/>
            <path d="M91 116 Q100 124 109 116" fill="#ff8a80"/>`,
    yellow: `<ellipse cx="89" cy="86" rx="8" ry="10" fill="#fff" stroke="#1a1a1a" stroke-width="3"/>
             <ellipse cx="112" cy="86" rx="8" ry="10" fill="#fff" stroke="#1a1a1a" stroke-width="3"/>
             <circle cx="91" cy="88" r="3.5" fill="#1a1a1a"/><circle cx="110" cy="85" r="3.5" fill="#1a1a1a"/>
             <path d="M80 72 l16 4 M104 75 l15 -5" stroke="#1a1a1a" stroke-width="3.5" stroke-linecap="round"/>
             <path d="M86 114 q5 -6 10 0 t10 0 t10 0" fill="none" stroke="#1a1a1a" stroke-width="3.5" stroke-linecap="round"/>
             <text x="140" y="62" font-size="22" font-weight="700" fill="#1a1a1a" font-family="Bangers, Impact, sans-serif">?</text>`,
    red: `<ellipse cx="89" cy="86" rx="9" ry="11" fill="#fff" stroke="#1a1a1a" stroke-width="3"/>
          <ellipse cx="112" cy="86" rx="9" ry="11" fill="#fff" stroke="#1a1a1a" stroke-width="3"/>
          <circle cx="89" cy="88" r="2.5" fill="#1a1a1a"/><circle cx="112" cy="88" r="2.5" fill="#1a1a1a"/>
          <path d="M80 72 l14 -5 M106 67 l14 5" stroke="#1a1a1a" stroke-width="3.5" stroke-linecap="round"/>
          <ellipse cx="100" cy="116" rx="9" ry="11" fill="#c2185b" stroke="#1a1a1a" stroke-width="3.5"/>
          <path d="M134 66 q6 9 0 13 q-6 -4 0 -13 Z" fill="#8fd3ff" stroke="#1a1a1a" stroke-width="2.5"/>`,
  }[light];
  return `<svg class="star ${light}" viewBox="0 0 200 190" role="img" aria-label="粉色海星">
    <ellipse cx="100" cy="182" rx="56" ry="6" fill="rgb(0 0 0 / 18%)"/>
    <polygon points="${pts}" fill="#1a1a1a" stroke="#1a1a1a" stroke-width="34" stroke-linejoin="round"/>
    <polygon points="${pts}" fill="#ff9cb8" stroke="#ff9cb8" stroke-width="26" stroke-linejoin="round"/>
    <g fill="#f48fb1"><circle cx="100" cy="44" r="4"/><circle cx="160" cy="88" r="4"/><circle cx="145" cy="160" r="4"/>
      <circle cx="56" cy="160" r="4"/><circle cx="40" cy="88" r="4"/><circle cx="140" cy="140" r="3"/><circle cx="62" cy="140" r="3"/></g>
    <ellipse cx="74" cy="104" rx="9" ry="6" fill="#ff6f91" opacity=".55"/>
    <ellipse cx="126" cy="104" rx="9" ry="6" fill="#ff6f91" opacity=".55"/>
    ${face}
  </svg>`;
}

// 右上角的海星：表情和台词跟着环境灯变
function renderMascot(light) {
  $('#mascot').innerHTML = `<div class="say fun">${SAY[light]}</div>${starSVG(light)}`;
}
