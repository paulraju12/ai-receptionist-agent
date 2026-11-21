/* Automation Studio chat widget.
   Install on any website with ONE line:
   <script src="https://YOUR-SERVER/widget.js" data-tenant="demo-dental" defer></script> */
(function () {
  var me = document.currentScript;
  var tenant = me.getAttribute("data-tenant");
  var api = me.src.replace(/\/widget\.js.*$/, "");
  var sid = (function () {
    var k = "as_sid_" + tenant, v;
    try { v = localStorage.getItem(k); } catch (e) {}
    if (!v) { v = "s" + Math.random().toString(36).slice(2) + Date.now().toString(36); try { localStorage.setItem(k, v); } catch (e) {} }
    return v;
  })();

  fetch(api + "/api/tenant/" + tenant).then(function (r) { return r.json(); }).then(build);

  function build(t) {
    var c = t.brand_color || "#0f766e";
    var css = document.createElement("style");
    css.textContent =
      ".as-btn{position:fixed;right:20px;bottom:20px;width:60px;height:60px;border-radius:50%;border:0;background:" + c + ";color:#fff;font-size:26px;cursor:pointer;box-shadow:0 6px 20px rgba(0,0,0,.25);z-index:99999}" +
      ".as-box{position:fixed;right:20px;bottom:92px;width:360px;max-width:calc(100vw - 40px);height:520px;max-height:calc(100vh - 120px);background:#fff;border-radius:16px;box-shadow:0 12px 40px rgba(0,0,0,.25);display:none;flex-direction:column;overflow:hidden;z-index:99999;font:14px/1.45 -apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#111}" +
      ".as-head{background:" + c + ";color:#fff;padding:14px 16px;font-weight:600}.as-head small{display:block;font-weight:400;opacity:.85}" +
      ".as-log{flex:1;overflow:auto;padding:14px;background:#f6f7f9}" +
      ".as-m{max-width:85%;padding:9px 12px;border-radius:14px;margin:6px 0;white-space:pre-wrap;word-wrap:break-word}" +
      ".as-bot{background:#fff;border:1px solid #e5e7eb}.as-me{background:" + c + ";color:#fff;margin-left:auto}" +
      ".as-in{display:flex;border-top:1px solid #e5e7eb}.as-in input{flex:1;border:0;padding:14px;font:inherit;outline:none}" +
      ".as-in button{border:0;background:none;color:" + c + ";font-weight:600;padding:0 16px;cursor:pointer}" +
      ".as-lead{font-size:12px;color:#047857;text-align:center;margin:6px 0}";
    document.head.appendChild(css);

    var btn = document.createElement("button"); btn.className = "as-btn"; btn.setAttribute("aria-label", "Chat with us"); btn.textContent = "💬";
    var box = document.createElement("div"); box.className = "as-box";
    box.innerHTML = '<div class="as-head"></div><div class="as-log"></div><form class="as-in"><input placeholder="Type your message…" aria-label="Message"><button>Send</button></form>';
    box.querySelector(".as-head").innerHTML = "";
    var head = box.querySelector(".as-head"); head.textContent = t.assistant_name + " · " + t.business_name;
    var sm = document.createElement("small"); sm.textContent = "Typically replies instantly"; head.appendChild(sm);
    document.body.appendChild(btn); document.body.appendChild(box);
    var log = box.querySelector(".as-log"), form = box.querySelector("form"), input = form.querySelector("input");

    function add(text, who) { var d = document.createElement("div"); d.className = "as-m " + who; d.textContent = text; log.appendChild(d); log.scrollTop = log.scrollHeight; return d; }
    add(t.greeting, "as-bot");
    btn.onclick = function () { box.style.display = box.style.display === "flex" ? "none" : "flex"; input.focus(); };

    form.onsubmit = function (e) {
      e.preventDefault();
      var text = input.value.trim(); if (!text) return;
      input.value = ""; add(text, "as-me");
      var wait = add("…", "as-bot");
      fetch(api + "/api/chat/" + tenant, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: sid, message: text }) })
        .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || "error"); return j; }); })
        .then(function (j) {
          wait.textContent = j.reply;
          if (j.lead) { var n = document.createElement("div"); n.className = "as-lead"; n.textContent = "✓ Details sent to the team"; log.appendChild(n); }
        })
        .catch(function () { wait.textContent = "Sorry, I'm having trouble right now. Please try again in a moment."; });
    };
  }
})();
