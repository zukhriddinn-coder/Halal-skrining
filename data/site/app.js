(() => {
  "use strict";
  const CFG = window.SITE_CONFIG || {};
  const $ = (s) => document.querySelector(s);
  const PAGE = 50;

  const STATUS = {
    halal: "Halol",
    not_halal: "Halol emas",
    doubtful: "Shubhali",
    no_data: "Ma'lumot yetarli emas",
  };
  const CAT = { value: "Value", growth: "Growth", penny: "Penny", blend: "Aralash" };

  let rows = [];
  let byTicker = new Map();
  let filtered = [];
  let shown = 0;
  const state = { q: "", status: "", cat: "", ex: "", sort: "mc" };

  // ---------- yordamchilar ----------
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const money = (v) => {
    if (v == null) return "—";
    const a = Math.abs(v);
    if (a >= 1e12) return "$" + (v / 1e12).toFixed(2) + " trln";
    if (a >= 1e9) return "$" + (v / 1e9).toFixed(2) + " mlrd";
    if (a >= 1e6) return "$" + (v / 1e6).toFixed(1) + " mln";
    if (a >= 1e3) return "$" + (v / 1e3).toFixed(0) + " ming";
    return "$" + v.toFixed(0);
  };
  const price = (p) => (p == null ? "—" : "$" + (p < 1 ? p.toFixed(4) : p.toFixed(2)));
  const pct = (v, d = 1) => (v == null ? "—" : (v * 100).toFixed(d) + "%");
  const when = (iso) => {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleString("uz-UZ", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  };
  const ago = (iso) => {
    const m = Math.round((Date.now() - new Date(iso)) / 60000);
    if (m < 1) return "hozirgina";
    if (m < 60) return m + " daqiqa oldin";
    const h = Math.round(m / 60);
    if (h < 48) return h + " soat oldin";
    return Math.round(h / 24) + " kun oldin";
  };
  const moons = (r) => (r ? "☾".repeat(r) + "<i>" + "☾".repeat(5 - r) + "</i>" : "");

  // ---------- CTA ----------
  for (const id of ["topCta", "bandCta"]) {
    const a = document.getElementById(id);
    a.href = CFG.channelUrl || "#";
  }
  $("#ctaText").textContent = CFG.ctaText || "";
  $("#brandName").textContent = CFG.channelName || "Trading Laboratory";
  $("#year").textContent = new Date().getFullYear();

  // ---------- yuklash ----------
  async function load() {
    try {
      const res = await fetch("data/stocks.json?ts=" + Math.floor(Date.now() / 600000), { cache: "no-cache" });
      if (!res.ok) throw new Error(res.status);
      const js = await res.json();
      const F = js.fields;
      rows = js.rows.map((r) => Object.fromEntries(F.map((f, i) => [f, r[i]])));
      byTicker = new Map(rows.map((r) => [r.t, r]));
      renderStats(js.counts);
      $("#updated").innerHTML = '<span class="dot"></span>Yangilandi: ' + esc(when(js.updated_at)) + " (" + esc(ago(js.updated_at)) + ")";
      apply();
      openFromHash();
    } catch (e) {
      $("#updated").textContent = "Ma'lumotni yuklab bo'lmadi. Sahifani birozdan keyin yangilang.";
      console.error(e);
    }
    try {
      const res = await fetch("data/changes.json?ts=" + Math.floor(Date.now() / 600000));
      if (res.ok) renderChanges(await res.json());
    } catch (_) { /* ixtiyoriy */ }
  }

  function renderStats(c) {
    const total = c.halal + c.not_halal + c.doubtful + c.no_data;
    $("#stats").innerHTML = [
      ["halal", "Halol"], ["not_halal", "Halol emas"], ["doubtful", "Shubhali"], ["no_data", "Ma'lumot yo'q"],
    ].map(([k, l]) => `<div class="stat ${k}"><b>${(c[k] || 0).toLocaleString("en-US")}</b><span>${l} · ${total ? Math.round((c[k] / total) * 100) : 0}%</span></div>`).join("");
  }

  // ---------- filtr va qidiruv ----------
  function apply() {
    const q = state.q.trim().toUpperCase();
    let list = rows.filter((r) =>
      (!state.status || r.st === state.status) &&
      (!state.cat || r.cat === state.cat) &&
      (!state.ex || r.ex === state.ex));
    if (q) {
      const scored = [];
      for (const r of list) {
        let s = -1;
        if (r.t === q) s = 0;
        else if (r.t.startsWith(q)) s = 1;
        else if (r.n.toUpperCase().startsWith(q)) s = 2;
        else if (r.n.toUpperCase().includes(q)) s = 3;
        if (s >= 0) scored.push([s, r]);
      }
      scored.sort((a, b) => a[0] - b[0] || (b[1].mc || 0) - (a[1].mc || 0));
      list = scored.map((x) => x[1]);
    } else {
      const k = state.sort;
      list.sort((a, b) => {
        if ((a.st === "no_data") !== (b.st === "no_data")) return a.st === "no_data" ? 1 : -1;
        if (k === "t") return a.t.localeCompare(b.t);
        if (k === "rt") return (b.rt || 0) - (a.rt || 0) || (b.mc || 0) - (a.mc || 0);
        return (b[k] ?? -Infinity) - (a[k] ?? -Infinity);
      });
    }
    filtered = list;
    shown = 0;
    $("#list").innerHTML = "";
    more();
    $("#resultCount").textContent = filtered.length.toLocaleString("en-US") + " ta aksiya";
  }

  function rowHtml(r) {
    const chg = r.chg == null ? "" : `<span class="${r.chg >= 0 ? "up" : "down"}">${r.chg >= 0 ? "+" : ""}${r.chg.toFixed(2)}%</span>`;
    return `<li class="row" tabindex="0" data-t="${esc(r.t)}">
      <div class="id"><div class="tk">${esc(r.t)} <span class="tag">${esc(CAT[r.cat] || "")}</span></div><div class="nm">${esc(r.n)}</div></div>
      <div class="px"><b>${price(r.p)}</b>${chg}</div>
      <div class="st"><span class="pill ${r.st}">${STATUS[r.st]}</span><span class="moons">${moons(r.rt)}</span></div>
    </li>`;
  }

  function more() {
    const next = filtered.slice(shown, shown + PAGE);
    if (!filtered.length) {
      $("#list").innerHTML = '<li class="empty">Hech narsa topilmadi. Tikerni tekshirib ko\'ring.</li>';
    } else {
      $("#list").insertAdjacentHTML("beforeend", next.map(rowHtml).join(""));
    }
    shown += next.length;
    $("#more").hidden = shown >= filtered.length;
  }

  let qTimer;
  $("#q").addEventListener("input", (e) => {
    clearTimeout(qTimer);
    qTimer = setTimeout(() => { state.q = e.target.value; apply(); }, 120);
  });
  $("#q").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && filtered[0]) openDetail(filtered[0].t);
  });
  $("#fStatus").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    for (const x of $("#fStatus").children) x.classList.toggle("on", x === b);
    state.status = b.dataset.v; apply();
  });
  $("#fCat").addEventListener("change", (e) => { state.cat = e.target.value; apply(); });
  $("#fEx").addEventListener("change", (e) => { state.ex = e.target.value; apply(); });
  $("#fSort").addEventListener("change", (e) => { state.sort = e.target.value; apply(); });
  $("#more").addEventListener("click", more);
  $("#list").addEventListener("click", (e) => { const li = e.target.closest(".row"); if (li) openDetail(li.dataset.t); });
  $("#list").addEventListener("keydown", (e) => { if (e.key === "Enter") { const li = e.target.closest(".row"); if (li) openDetail(li.dataset.t); } });

  // ---------- o'zgarishlar ----------
  function renderChanges(list) {
    const ol = $("#changes");
    if (!list.length) {
      ol.innerHTML = '<li class="muted" style="cursor:default">Hozircha o\'zgarish yo\'q. Tizim har soatda kuzatib boradi.</li>';
      return;
    }
    ol.innerHTML = list.slice(0, 12).map((c) => `<li data-t="${esc(c.t)}">
      <b>${esc(c.t)}</b><span class="muted small">${esc(c.n)}</span>
      <span class="pill ${c.from}">${STATUS[c.from]}</span><span class="arrow">→</span><span class="pill ${c.to}">${STATUS[c.to]}</span>
      <time datetime="${esc(c.at)}">${esc(ago(c.at))}</time></li>`).join("");
    ol.addEventListener("click", (e) => { const li = e.target.closest("li[data-t]"); if (li) openDetail(li.dataset.t); });
  }

  // ---------- batafsil oyna ----------
  const dlg = $("#detail");

  function check(label, v, limit, hint) {
    const st = v == null ? "unknown" : v >= limit ? "fail" : v >= limit * 0.85 ? "near" : "pass";
    const scale = Math.max(limit * 2, v || 0);
    const w = v == null ? 0 : Math.min(100, (v / scale) * 100);
    const lim = (limit / scale) * 100;
    const icon = st === "pass" ? "✓" : st === "near" ? "!" : st === "fail" ? "✕" : "?";
    return `<div class="check">
      <div class="lbl"><span>${icon} ${label}</span><b>${v == null ? "Topilmadi" : pct(v)} <span class="muted">/ ${pct(limit, 0)}</span></b></div>
      <div class="bar"><div class="fill ${st}" style="width:${w}%"></div><div class="limit" style="left:${lim}%"></div></div>
      <div class="sub">${hint}</div></div>`;
  }

  function openDetail(t) {
    const r = byTicker.get(t);
    if (!r) return;
    const reasons = (r.why || []).map((x) => `<li>${esc(x)}</li>`).join("");
    const bizIcon = r.biz === "pass" ? "✓" : r.biz === "fail" ? "✕" : "!";
    const purify = r.st === "halal" && r.ir != null
      ? `<div class="purify"><b>Dividendni tozalash:</b> har $100 dividenddan taxminan <b>$${(r.ir * 100).toFixed(2)}</b> sadaqa qilinadi (foizli daromad ulushi ${pct(r.ir, 2)}).</div>`
      : "";
    $("#dBody").innerHTML = `
      <div class="d-top">
        <div><h2 id="dTitle">${esc(r.t)}</h2><div class="nm">${esc(r.n)} · ${esc(r.ex)} · ${esc(CAT[r.cat] || "")}</div></div>
        <button class="x" aria-label="Yopish" data-close>×</button>
      </div>
      <div class="verdict ${r.st}">
        <div class="big">${STATUS[r.st]} <span class="moons" style="font-size:16px">${moons(r.rt)}</span></div>
        ${reasons ? `<ul>${reasons}</ul>` : r.st === "halal" ? '<ul><li>Barcha mezonlardan o\'tdi</li></ul>' : ""}
      </div>
      <div class="biz"><span>${bizIcon}</span><div><b>Biznes skrining:</b> ${esc(r.bizr)}${r.sic ? `<div class="muted small">Soha: ${esc(r.sic)}</div>` : ""}</div></div>
      <div class="checks">
        ${check("Foizli qarz / kapitalizatsiya", r.dr, 0.30, "Qarz: " + money(r.debt) + (r.note ? " · " + esc(r.note) : ""))}
        ${check("Naqd pul va foizli qog'ozlar / kapitalizatsiya", r.cr, 0.30, "Naqd va qog'ozlar: " + money(r.cash))}
        ${check("Foizli daromad / jami daromad", r.ir, 0.05, "Foizli daromad: " + money(r.ii) + " · Daromad: " + money(r.rev))}
      </div>
      <div class="kv">
        <div><span>Narx</span><b>${price(r.p)}</b> ${r.chg == null ? "" : `<span class="${r.chg >= 0 ? "up" : "down"}">${r.chg >= 0 ? "+" : ""}${r.chg.toFixed(2)}%</span>`}</div>
        <div><span>Bozor kapitalizatsiyasi</span><b>${money(r.mc)}</b></div>
        <div><span>P/E</span><b>${r.pe == null ? "—" : r.pe.toFixed(1)}</b></div>
        <div><span>Hisobot sanasi</span><b>${esc(r.bs || "—")}</b>${r.fy ? `<span>Yillik daromad: ${esc(r.fy)}-yil</span>` : ""}${r.std ? `<span>Standart: ${esc(r.std)}</span>` : ""}</div>
      </div>
      ${purify}
      <div class="d-cta">
        <p>${esc(CFG.ctaText || "")}</p>
        <a class="btn btn-tg" href="${esc(CFG.channelUrl || "#")}" target="_blank" rel="noopener">Kanalga qo'shilish</a>
      </div>
      <div class="d-actions">
        <button class="btn btn-ghost" data-share>Havolani nusxalash</button>
      </div>
      <div class="d-meta">Narx yangilangan: ${esc(when(r.pat))}. Natija avtomatik hisoblangan, fatvo emas.</div>`;
    if (!dlg.open) dlg.showModal();
    if (location.hash !== "#" + t) history.replaceState(null, "", "#" + t);
  }

  dlg.addEventListener("click", async (e) => {
    if (e.target === dlg || e.target.closest("[data-close]")) dlg.close();
    const sh = e.target.closest("[data-share]");
    if (sh) {
      const url = location.href;
      try {
        if (navigator.share) await navigator.share({ title: document.title, url });
        else { await navigator.clipboard.writeText(url); sh.textContent = "Nusxalandi ✓"; }
      } catch (_) { /* bekor qilindi */ }
    }
  });
  dlg.addEventListener("close", () => {
    if (location.hash) history.replaceState(null, "", location.pathname + location.search);
  });

  function openFromHash() {
    const t = decodeURIComponent(location.hash.slice(1)).toUpperCase();
    if (t && byTicker.has(t)) openDetail(t);
  }
  window.addEventListener("hashchange", openFromHash);

  load();
})();
