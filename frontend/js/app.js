const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const state = {
  book: null,
  mapping: null,
  voices: [],
  rvc: null,
  queue: [],
  queueIndex: -1,
  playing: false,
  activeChapter: null,
  preparing: false,
};

const els = {
  home: $("#view-home"),
  reader: $("#view-reader"),
  file: $("#file-input"),
  drop: $("#dropzone"),
  libraryList: $("#library-list"),
  libraryPanel: $("#library-panel"),
  bookTitle: $("#book-title"),
  bookMeta: $("#book-meta"),
  chapters: $("#chapter-list"),
  script: $("#script"),
  voicePanel: $("#voice-panel"),
  narratorVoice: $("#narrator-voice"),
  characterVoices: $("#character-voices"),
  useRvc: $("#use-rvc"),
  rvcHint: $("#rvc-hint"),
  audio: $("#audio"),
  play: $("#btn-play"),
  stop: $("#btn-stop"),
  speed: $("#speed"),
  speedOut: $("#speed-out"),
  now: $("#now-playing"),
  toast: $("#toast"),
  layout: $(".reader-layout"),
};

function toast(msg) {
  els.toast.textContent = msg;
  els.toast.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => {
    els.toast.hidden = true;
  }, 2800);
}

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch (_) {}
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

async function loadVoices() {
  const data = await api("/api/voices");
  state.voices = data.voices || [];
  state.rvc = data.rvc;
  if (els.rvcHint) {
    const n = (data.rvc?.weights || []).length;
    els.rvcHint.textContent = data.rvc?.available
      ? `RVC ready — ${n} model(s) in ${data.rvc.weights_dir}`
      : `RVC optional — ${data.rvc?.note || "using LocalTTS voice variants."}`;
  }
}

async function refreshLibrary() {
  const books = await api("/api/books");
  els.libraryList.innerHTML = "";
  if (!books.length) {
    els.libraryPanel.hidden = true;
    return;
  }
  els.libraryPanel.hidden = false;
  for (const b of books) {
    const li = document.createElement("li");
    const open = document.createElement("button");
    open.className = "open";
    open.textContent = b.title;
    open.addEventListener("click", () => openBook(b.id));
    const meta = document.createElement("span");
    meta.className = "meta";
    meta.textContent = `${b.kind} · ${b.chapter_count} ch · ${b.format}`;
    const del = document.createElement("button");
    del.className = "btn ghost compact";
    del.textContent = "Remove";
    del.addEventListener("click", async () => {
      await api(`/api/books/${b.id}`, { method: "DELETE" });
      refreshLibrary();
    });
    li.append(open, meta, del);
    els.libraryList.append(li);
  }
}

async function uploadFile(file) {
  const fd = new FormData();
  fd.append("file", file);
  toast(`Opening ${file.name}…`);
  const data = await api("/api/books", { method: "POST", body: fd });
  state.book = data.book;
  state.mapping = data.mapping;
  showReader();
}

async function openBook(id) {
  const data = await api(`/api/books/${id}`);
  state.book = data.book;
  state.mapping = data.mapping;
  showReader();
}

function showHome() {
  stopPlayback();
  els.home.hidden = false;
  els.reader.hidden = true;
  refreshLibrary();
}

function showReader() {
  els.home.hidden = true;
  els.reader.hidden = false;
  renderReader();
}

function renderReader() {
  const { meta, chapters, segments } = state.book;
  els.bookTitle.textContent = meta.title;
  els.bookMeta.textContent = `${meta.kind} · ${meta.segment_count} segments · ${meta.character_names.length} characters`;
  state.activeChapter = chapters[0]?.id || null;

  els.chapters.innerHTML = "";
  for (const ch of chapters) {
    const btn = document.createElement("button");
    btn.textContent = ch.title;
    btn.classList.toggle("active", ch.id === state.activeChapter);
    btn.addEventListener("click", () => {
      state.activeChapter = ch.id;
      $$(".chapters button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const first = segments.find((s) => s.chapter_id === ch.id);
      if (first) {
        const node = $(`[data-seg="${first.id}"]`);
        node?.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });
    els.chapters.append(btn);
  }

  els.script.innerHTML = "";
  for (const seg of segments) {
    const div = document.createElement("div");
    div.className = `seg ${seg.kind}`;
    div.dataset.seg = seg.id;
    div.innerHTML = `
      <span class="who">${escapeHtml(seg.speaker)} · ${seg.kind}</span>
      <p class="line">${escapeHtml(seg.text)}</p>
      <div class="edit-speaker">
        <input type="text" value="${escapeAttr(seg.speaker)}" aria-label="Speaker name" />
        <button type="button" class="btn ghost compact">Set</button>
      </div>
    `;
    div.addEventListener("click", (e) => {
      if (e.target.closest(".edit-speaker")) return;
      playFrom(seg.id);
    });
    const setBtn = $(".edit-speaker button", div);
    const input = $(".edit-speaker input", div);
    setBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const speaker = input.value.trim() || "Narrator";
      const updated = await api(`/api/books/${meta.id}/segments/${seg.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ speaker }),
      });
      seg.speaker = updated.speaker;
      $(".who", div).textContent = `${updated.speaker} · ${seg.kind}`;
      // refresh characters in mapping UI
      if (!state.book.meta.character_names.includes(updated.speaker) && updated.speaker !== "Narrator") {
        state.book.meta.character_names.push(updated.speaker);
      }
      renderVoicePanel();
      toast(`Speaker → ${updated.speaker}`);
    });
    els.script.append(div);
  }
  renderVoicePanel();
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}
function escapeAttr(s) {
  return escapeHtml(s).replaceAll('"', "&quot;");
}

function renderVoicePanel() {
  const voices = state.voices;
  const mapping = state.mapping;
  const opts = voices
    .map((v) => `<option value="${escapeAttr(v.id)}">${escapeHtml(v.name)} (${v.engine})</option>`)
    .join("");
  els.narratorVoice.innerHTML = opts;
  if (mapping.narrator_voice) els.narratorVoice.value = mapping.narrator_voice;
  els.useRvc.checked = !!mapping.use_rvc;

  const chars = state.book.meta.character_names || [];
  els.characterVoices.innerHTML = "";
  for (const name of chars) {
    const label = document.createElement("label");
    label.className = "field";
    label.innerHTML = `<span>${escapeHtml(name)}</span><select data-char="${escapeAttr(name)}">${opts}</select>`;
    const select = $("select", label);
    if (mapping.character_voices?.[name]) select.value = mapping.character_voices[name];
    els.characterVoices.append(label);
  }
}

async function saveVoices() {
  const character_voices = {};
  $$("#character-voices select").forEach((sel) => {
    character_voices[sel.dataset.char] = sel.value;
  });
  const payload = {
    book_id: state.book.meta.id,
    narrator_voice: els.narratorVoice.value,
    character_voices,
    speed: Number(els.speed.value),
    use_rvc: els.useRvc.checked,
  };
  state.mapping = await api(`/api/books/${state.book.meta.id}/mapping`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  toast("Voice mapping saved");
}

function setActiveSegment(id) {
  $$(".seg").forEach((n) => n.classList.toggle("active", n.dataset.seg === id));
  const node = $(`[data-seg="${id}"]`);
  node?.scrollIntoView({ behavior: "smooth", block: "center" });
  const seg = state.book.segments.find((s) => s.id === id);
  if (seg) {
    els.now.textContent = `${seg.speaker}: ${seg.text.slice(0, 72)}${seg.text.length > 72 ? "…" : ""}`;
    state.activeChapter = seg.chapter_id;
    $$(".chapters button").forEach((b, i) => {
      b.classList.toggle("active", state.book.chapters[i]?.id === seg.chapter_id);
    });
  }
}

async function playFrom(segmentId = null) {
  if (state.preparing) return;
  if (state.playing && !segmentId) {
    els.audio.pause();
    state.playing = false;
    els.play.textContent = "▶";
    return;
  }
  if (state.queue.length && state.queueIndex >= 0 && !segmentId && els.audio.src && els.audio.paused) {
    await els.audio.play();
    state.playing = true;
    els.play.textContent = "❚❚";
    return;
  }

  const fromId = segmentId || state.book.segments[0]?.id;
  if (!fromId) return;
  state.preparing = true;
  els.now.textContent = "Synthesizing…";
  els.play.textContent = "…";
  try {
    const data = await api("/api/playback/synthesize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        book_id: state.book.meta.id,
        from_segment_id: fromId,
        chapter_id: null,
        speed: Number(els.speed.value),
      }),
    });
    state.queue = data.segments;
    state.queueIndex = 0;
    await playQueueItem();
  } catch (err) {
    toast(err.message || String(err));
    els.play.textContent = "▶";
    els.now.textContent = "TTS error";
  } finally {
    state.preparing = false;
  }
}

async function playQueueItem() {
  if (state.queueIndex < 0 || state.queueIndex >= state.queue.length) {
    stopPlayback();
    els.now.textContent = "Finished";
    return;
  }
  const item = state.queue[state.queueIndex];
  setActiveSegment(item.segment_id);
  els.audio.src = item.audio_url;
  try {
    await els.audio.play();
    state.playing = true;
    els.play.textContent = "❚❚";
  } catch (err) {
    toast("Could not play audio — check browser autoplay settings");
    state.playing = false;
    els.play.textContent = "▶";
  }
}

function stopPlayback() {
  els.audio.pause();
  els.audio.removeAttribute("src");
  els.audio.load();
  state.playing = false;
  state.queue = [];
  state.queueIndex = -1;
  els.play.textContent = "▶";
  els.now.textContent = "Stopped";
}

els.audio.addEventListener("ended", () => {
  state.queueIndex += 1;
  playQueueItem();
});

els.play.addEventListener("click", () => playFrom());
els.stop.addEventListener("click", stopPlayback);
els.speed.addEventListener("input", () => {
  els.speedOut.textContent = `${Number(els.speed.value).toFixed(2)}×`;
});
$("#btn-back").addEventListener("click", showHome);
$("#btn-voices").addEventListener("click", () => {
  const open = els.voicePanel.hidden;
  els.voicePanel.hidden = !open;
  els.layout.classList.toggle("voices-open", open);
});
$("#btn-save-voices").addEventListener("click", saveVoices);
$("#btn-show-library").addEventListener("click", () => {
  els.libraryPanel.hidden = false;
  els.libraryPanel.scrollIntoView({ behavior: "smooth" });
});
$("#btn-sample").addEventListener("click", async () => {
  try {
    const res = await fetch("/api/demo/sample");
    if (!res.ok) throw new Error("Sample missing");
    const blob = await res.blob();
    const file = new File([blob], "the_quiet_carriage.txt", { type: "text/plain" });
    await uploadFile(file);
  } catch (err) {
    toast("Could not load sample — drop samples/the_quiet_carriage.txt instead");
  }
});

els.file.addEventListener("change", async () => {
  const file = els.file.files?.[0];
  if (file) await uploadFile(file);
  els.file.value = "";
});

["dragenter", "dragover"].forEach((ev) => {
  els.drop.addEventListener(ev, (e) => {
    e.preventDefault();
    els.drop.classList.add("drag");
  });
});
["dragleave", "drop"].forEach((ev) => {
  els.drop.addEventListener(ev, (e) => {
    e.preventDefault();
    els.drop.classList.remove("drag");
  });
});
els.drop.addEventListener("drop", async (e) => {
  const file = e.dataTransfer?.files?.[0];
  if (file) await uploadFile(file);
});

// Also allow dropping on hero
document.body.addEventListener("dragover", (e) => e.preventDefault());
document.body.addEventListener("drop", async (e) => {
  if (e.target.closest("#dropzone")) return;
  const file = e.dataTransfer?.files?.[0];
  if (file && /\.(txt|md|markdown|pdf|epub|docx)$/i.test(file.name)) {
    e.preventDefault();
    await uploadFile(file);
  }
});

(async function init() {
  try {
    await loadVoices();
    await refreshLibrary();
  } catch (err) {
    toast("Backend not ready: " + err.message);
  }
})();
