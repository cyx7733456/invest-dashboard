/* 五组投资大看板 · 全站密码门锁 v2.1
 * 保护级别：客户端 deterrent（君子锁）——挡普通访问者，不挡查看源码者。
 * 源码只存 SHA-256 指纹，不存明文；SHA-256(密码) 可被彩虹表反查短数字，
 * 属可接受风险，用户知情（见 build_report.md「v2.1 密码门锁」）。
 * 有效期 12 小时（localStorage 签发时间戳，过期重新输入）。
 * 无外部依赖；crypto.subtle 不可用时回退内置同步 SHA-256 兜底（file:// 双击可用）。
 */
(function () {
  'use strict';
  var FP = 'd9f4268cbdf0de3ff1a268fb337ab3dec607e9f2cfcdeeda4536b0e55064db4a';
  var KEY = 'dash_auth';
  var TTL = 12 * 3600 * 1000; // 12h

  function valid(rec) {
    if (!rec || rec.fp !== FP) return false;
    var iat = Number(rec.iat);
    return isFinite(iat) && (Date.now() - iat) < TTL && (Date.now() - iat) >= 0;
  }

  function readRec() {
    try { return JSON.parse(localStorage.getItem(KEY)); } catch (e) { return null; }
  }

  // 未认证：先隐藏全部内容，防闪烁（本脚本置于 <head>，同步执行）
  var rec = readRec();
  var ok = valid(rec);
  if (!ok) {
    document.documentElement.style.visibility = 'hidden';
  }

  function reveal() {
    document.documentElement.style.visibility = '';
    var ov = document.getElementById('dash-lock');
    if (ov) ov.remove();
  }

  // ---- 内置同步 SHA-256 兜底（无 crypto.subtle 的环境）----
  function sha256Sync(ascii) {
    function rrot(v, n) { return (v >>> n) | (v << (32 - n)); }
    var mathPow = Math.pow, maxWord = mathPow(2, 32);
    var result = '', words = [], asciiBitLength = ascii.length * 8;
    var hash = [], k = [], primeCounter = 0, isComposite = {};
    for (var candidate = 2; primeCounter < 64; candidate++) {
      if (!isComposite[candidate]) {
        for (var i = 0; i < 313; i += candidate) isComposite[i] = candidate;
        hash[primeCounter] = (mathPow(candidate, 0.5) * maxWord) | 0;
        k[primeCounter++] = (mathPow(candidate, 1 / 3) * maxWord) | 0;
      }
    }
    ascii += '\x80';
    while (ascii.length % 64 - 56) ascii += '\x00';
    for (i = 0; i < ascii.length; i++) {
      var j = ascii.charCodeAt(i);
      if (j >> 8) return '';
      words[i >> 2] |= j << ((3 - i) % 4) * 8;
    }
    words[words.length] = ((asciiBitLength / maxWord) | 0);
    words[words.length] = asciiBitLength;
    for (j = 0; j < words.length;) {
      var w = words.slice(j, j += 16), oldHash = hash.slice(0, 8);
      for (i = 16; i < 64; i++) {
        var w15 = w[i - 15], w2 = w[i - 2];
        var s0 = rrot(w15, 7) ^ rrot(w15, 18) ^ (w15 >>> 3);
        var s1 = rrot(w2, 17) ^ rrot(w2, 19) ^ (w2 >>> 10);
        w[i] = (w[i - 16] + s0 + w[i - 7] + s1) | 0;
      }
      var a = hash[0], b = hash[1], c = hash[2], d = hash[3],
          e = hash[4], f = hash[5], g = hash[6], h = hash[7];
      for (i = 0; i < 64; i++) {
        var S1 = rrot(e, 6) ^ rrot(e, 11) ^ rrot(e, 25);
        var ch = (e & f) ^ (~e & g);
        var temp1 = (h + S1 + ch + k[i] + w[i]) | 0;
        var S0 = rrot(a, 2) ^ rrot(a, 13) ^ rrot(a, 22);
        var maj = (a & b) ^ (a & c) ^ (b & c);
        var temp2 = (S0 + maj) | 0;
        h = g; g = f; f = e; e = (d + temp1) | 0;
        d = c; c = b; b = a; a = (temp1 + temp2) | 0;
      }
      hash[0] = (hash[0] + a) | 0; hash[1] = (hash[1] + b) | 0;
      hash[2] = (hash[2] + c) | 0; hash[3] = (hash[3] + d) | 0;
      hash[4] = (hash[4] + e) | 0; hash[5] = (hash[5] + f) | 0;
      hash[6] = (hash[6] + g) | 0; hash[7] = (hash[7] + h) | 0;
    }
    for (i = 0; i < 8; i++)
      for (j = 3; j + 1; j--) {
        var b2 = (hash[i] >> (j * 8)) & 255;
        result += ((b2 >> 4) % 16).toString(16) + (b2 % 16).toString(16);
      }
    return result;
  }

  function digestHex(pw) {
    if (window.crypto && crypto.subtle && crypto.subtle.digest) {
      return crypto.subtle.digest('SHA-256', new TextEncoder().encode(pw)).then(function (buf) {
        return Array.prototype.map.call(new Uint8Array(buf), function (b) {
          return ('0' + b.toString(16)).slice(-2);
        }).join('');
      });
    }
    return Promise.resolve(sha256Sync(pw));
  }

  function buildOverlay() {
    var ov = document.createElement('div');
    ov.id = 'dash-lock';
    ov.style.visibility = 'visible'; // 正文根节点 hidden 时遮罩层单独可见
    ov.innerHTML =
      '<style>' +
      '#dash-lock{position:fixed;inset:0;z-index:99999;background:#0b0e14;display:flex;align-items:center;justify-content:center;font-family:-apple-system,"PingFang SC","Microsoft YaHei",monospace}' +
      '#dash-lock .card{background:#12161f;border:1px solid #232a36;border-radius:10px;padding:30px 34px;width:340px;max-width:90vw;box-shadow:0 8px 40px rgba(0,0,0,.55)}' +
      '#dash-lock h1{margin:0 0 4px;font-size:17px;color:#d7dee8;font-weight:700}' +
      '#dash-lock .sub{color:#8a93a3;font-size:11.5px;margin-bottom:18px}' +
      '#dash-lock input{width:100%;box-sizing:border-box;background:#0d1117;border:1px solid #232a36;border-radius:7px;color:#d7dee8;font:15px/1.4 monospace;padding:10px 12px;letter-spacing:3px;outline:none}' +
      '#dash-lock input:focus{border-color:#58a6ff}' +
      '#dash-lock input.err{border-color:#e5544b;animation:dashshake .3s}' +
      '#dash-lock button{width:100%;margin-top:12px;background:#1f3a5f;border:1px solid #58a6ff;border-radius:7px;color:#cfe4ff;font-size:14px;font-weight:700;padding:9px 0;cursor:pointer}' +
      '#dash-lock button:hover{background:#25477a}' +
      '#dash-lock .msg{color:#e5544b;font-size:12px;margin-top:9px;min-height:16px}' +
      '#dash-lock .foot{color:#5c6575;font-size:10.5px;margin-top:14px}' +
      '@keyframes dashshake{0%,100%{transform:translateX(0)}25%{transform:translateX(-6px)}75%{transform:translateX(6px)}}' +
      '</style>' +
      '<div class="card">' +
      '<h1>五组投资大看板 · 访问验证</h1>' +
      '<div class="sub">请输入访问密码（验证通过后 12 小时内免输）</div>' +
      '<input id="dash-pw" type="password" inputmode="numeric" autocomplete="off" autofocus>' +
      '<button id="dash-go">解锁</button>' +
      '<div class="msg" id="dash-msg"></div>' +
      '<div class="foot">仅本地校验（SHA-256 指纹比对）｜AI 生成，仅供参考</div>' +
      '</div>';
    document.body.appendChild(ov);

    var inp = ov.querySelector('#dash-pw');
    var msg = ov.querySelector('#dash-msg');
    var btn = ov.querySelector('#dash-go');

    function fail() {
      msg.textContent = '密码错误';
      inp.classList.remove('err');
      void inp.offsetWidth; // 重启动画
      inp.classList.add('err');
    }
    function tryUnlock() {
      var pw = inp.value;
      if (!pw) { fail(); return; }
      digestHex(pw).then(function (hex) {
        if (hex === FP) {
          try {
            localStorage.setItem(KEY, JSON.stringify({ fp: FP, iat: Date.now() }));
          } catch (e) { /* 隐私模式：本次会话内放行 */ }
          reveal();
        } else {
          fail(); // 不清空已输入，便于修改重试
        }
      });
    }
    btn.addEventListener('click', tryUnlock);
    inp.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); tryUnlock(); }
    });
    inp.addEventListener('input', function () { inp.classList.remove('err'); msg.textContent = ''; });
  }

  function boot() {
    if (ok) { reveal(); return; }
    if (!document.body) {
      document.addEventListener('DOMContentLoaded', boot);
      return;
    }
    buildOverlay(); // 正文保持 hidden，仅遮罩层可见
  }
  boot();
})();
