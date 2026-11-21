/* Общие хелперы ролевых страниц (кухня/сборка/курьеры). */
const UI = (() => {
  const STATUS = {
    new: ["Новый", "var(--info)"], started: ["Готовится", "var(--warn)"],
    ready: ["Готов", "var(--ok)"], assigned: ["Курьер назначен", "var(--accent)"],
    picked_up: ["В пути", "var(--accent)"], delivered: ["Доставлен", "var(--ok)"],
    failed: ["Не доставлен", "var(--err)"], cancelled: ["Отменён", "var(--err)"],
  };
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const dt = (iso) => { const d = new Date(iso); return isNaN(d) ? iso : d.toLocaleString("ru-RU"); };
  const money = (v) => Number(v).toLocaleString("ru-RU",
    { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " ₽";
  const badge = (s) => {
    const [l, c] = STATUS[s] || [s, "var(--muted)"];
    return `<span class="badge" style="background:${c}22;color:${c}">${esc(l)}</span>`;
  };

  async function api(path, method = "GET", body) {
    const resp = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    let data;
    try { data = await resp.json(); } catch (e) { data = {}; }
    return { status: resp.status, data };
  }

  async function orders(statuses) {
    const qs = statuses.map((s) => "status=" + encodeURIComponent(s)).join("&");
    const list = await api(`/api/orders/orders?${qs}`);
    if (list.status !== 200) throw new Error(list.data.detail || ("HTTP " + list.status));
    const details = await Promise.all(
      list.data.orders.map((o) => api(`/api/orders/order/${o.order_id}`)));
    return details.filter((d) => d.status === 200).map((d) => d.data);
  }

  async function couriers() {
    const r = await api("/api/orders/couriers");
    return r.status === 200 ? r.data.couriers : [];
  }

  function setAvailable(courierId, available) {
    return api("/api/orders/courier/available", "POST",
      { courier_id: courierId, available });
  }

  function courierOf(order) {
    const ev = (order.history || []).find((e) => e.status === "assigned" && e.courier_id != null);
    return ev ? ev.courier_id : null;
  }

  function setMsg(text, kind) {
    const el = $("msg");
    if (!text) { el.className = "msg"; el.textContent = ""; return; }
    el.className = "msg show " + (kind || "ok");
    el.textContent = text;
  }

  async function post(path, body, okText) {
    const r = await api(path, "POST", body);
    if (r.status >= 200 && r.status < 300) { setMsg(okText || "Готово", "ok"); return true; }
    setMsg((r.data && r.data.detail) || ("HTTP " + r.status), "err");
    return false;
  }

  return { $, esc, dt, money, badge, api, orders, couriers, setAvailable, courierOf,
           setMsg, post, STATUS };
})();
