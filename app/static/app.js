"use strict";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ICONS = { music: "♫", group: "☺", film: "🎞", tv: "📺", reading: "📖", outing: "📍", food: "🍰" };
const TOOL_LABELS = {
  search_entities: "Resolving favourites in Qloo",
  taste_recommendations: "Qloo taste graph",
  find_outing_places: "Qloo places nearby",
  search_tags: "Qloo tag lookup",
  group_common_ground: "Scoring the group's common ground",
  submit_plan: "Submitting plan",
};

let residents = [];

async function init() {
  const [health, list] = await Promise.all([fetch("/api/health").then((r) => r.json()), fetch("/api/residents").then((r) => r.json())]);
  $("#modes").innerHTML =
    `<span class="pill ${health.qloo === "mock" ? "mock" : ""}">Qloo: ${health.qloo === "mock" ? "mock data" : "live API"}</span>` +
    `<span class="pill ${health.agent === "scripted" ? "mock" : ""}">Agent: ${health.agent === "live" ? esc(health.model) : "scripted demo"}</span>`;
  residents = list;
  renderResidents();
}

function renderResidents() {
  $("#residents").innerHTML = residents
    .map(
      (r, i) => `<label class="res"><input type="checkbox" value="${esc(r.id)}" ${i === 0 ? "checked" : ""} />
      <div><b>${esc(r.name)}</b> <span class="meta">b. ${r.birth_year} · ${esc(r.hometown)}</span>
      <div class="meta">${esc(r.background)}</div>
      <div class="chips">${r.favourites.map((f) => `<span class="chip">${esc(f.name)}</span>`).join("")}
      ${(r.avoid || []).map((a) => `<span class="chip avoid">avoid: ${esc(a)}</span>`).join("")}</div></div></label>`
    )
    .join("");
}

$("#add-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const favourites = String(fd.get("favourites"))
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => {
      const m = l.match(/^(artist|movie|tv_show|book|place)\s*:\s*(.+)$/i);
      return m ? { type: m[1].toLowerCase(), name: m[2].trim() } : { type: "artist", name: l };
    });
  residents.push({
    id: "r" + Date.now(),
    name: String(fd.get("name")).trim(),
    birth_year: Number(fd.get("birth_year")),
    hometown: String(fd.get("hometown") || ""),
    background: String(fd.get("background") || ""),
    favourites: favourites.slice(0, 10),
    avoid: String(fd.get("avoid") || "").split(",").map((s) => s.trim()).filter(Boolean),
  });
  renderResidents();
  e.target.reset();
  e.target.closest("details").open = false;
});

function addTrace(cls, html) {
  const li = document.createElement("li");
  li.className = cls;
  li.innerHTML = html;
  $("#trace").appendChild(li);
  li.scrollIntoView({ block: "nearest" });
  return li;
}

function shortInput(name, input) {
  if (name === "search_entities") return input.queries.map((q) => q.name).join(", ");
  if (name === "taste_recommendations") return `${input.type}${input.birth_year ? `, era of someone born ${input.birth_year}` : ""}`;
  if (name === "find_outing_places") return input.location;
  if (name === "group_common_ground") return `${input.candidate_entity_ids.length} ${input.type}s × ${input.residents.length} residents`;
  if (name === "search_tags") return input.query;
  return "";
}

function renderPlan(p) {
  const sections = (p.sections || [])
    .map(
      (s) => `<article class="card"><h4><span aria-hidden="true">${ICONS[s.kind] || "★"}</span>${esc(s.title)}</h4><ul>${(s.items || [])
        .map((it) => `<li><b>${esc(it.name)}</b><span>${esc(it.why)}</span></li>`)
        .join("")}</ul></article>`
    )
    .join("");
  const list = (title, arr, cls = "") =>
    arr && arr.length ? `<article class="card ${cls}"><h4>${title}</h4><ul>${arr.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></article>` : "";
  $("#plan").innerHTML = `<h3>${esc(p.title)}</h3><p class="summary">${esc(p.summary)}</p>
    <div class="cards">${sections}</div>
    <div class="lists">${list("Conversation starters", p.conversation_prompts)}${list("Facilitator tips", p.facilitator_tips)}${list("Cautions honoured", p.cautions, "caution")}</div>
    <div class="actions"><button class="btn ghost" onclick="window.print()">Print session sheet</button></div>`;
}

$("#go").addEventListener("click", async () => {
  const ids = [...document.querySelectorAll("#residents input:checked")].map((i) => i.value);
  if (!ids.length) return alert("Choose at least one resident.");
  const chosen = residents.filter((r) => ids.includes(r.id));
  let session = document.querySelector('input[name="session"]:checked').value;
  if (chosen.length > 1 && session === "one_to_one") session = "group";
  const body = { residents: chosen, session, location: $("#location").value || "Brighton", notes: $("#notes").value };

  const btn = $("#go");
  btn.disabled = true;
  btn.textContent = "Planning…";
  $("#trace").innerHTML = "";
  $("#plan").innerHTML = "";
  const pending = {};

  try {
    const resp = await fetch("/api/plan", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!resp.ok) throw new Error(`Request failed (${resp.status}): ${await resp.text()}`);
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const line = buf.slice(0, idx).replace(/^data: /, "");
        buf = buf.slice(idx + 2);
        if (!line.trim()) continue;
        const ev = JSON.parse(line);
        if (ev.type === "message") addTrace("msg", esc(ev.text));
        else if (ev.type === "tool_call") {
          (pending[ev.name] ||= []).push(addTrace("call", `<code>${esc(TOOL_LABELS[ev.name] || ev.name)}</code> ${esc(shortInput(ev.name, ev.input))}`));
        } else if (ev.type === "tool_result") {
          const li = (pending[ev.name] || []).shift();
          if (li) li.insertAdjacentHTML("beforeend", `<span class="res-sum">→ ${esc(ev.summary)}</span>`);
        } else if (ev.type === "plan") renderPlan(ev.plan);
        else if (ev.type === "error") addTrace("err", esc(ev.message));
        else if (ev.type === "done") addTrace("muted", `Done · ${ev.qloo_calls} Qloo API calls`);
      }
    }
  } catch (err) {
    addTrace("err", esc(err.message));
  } finally {
    btn.disabled = false;
    btn.textContent = "Plan the session";
  }
});

init();
