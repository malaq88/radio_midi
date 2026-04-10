/**
 * Radio MIDI — UI estilo Spotify (vanilla JS, responsivo, controlos avançados)
 */
(function () {
  "use strict";

  const LS_SHUFFLE = "radioMidi_shuffle";
  const HISTORY_MAX = 5;
  const PREV_RESTART_SEC = 3;

  const state = {
    sourceKey: "",
    currentLabel: "",
    playing: false,
    isFileMode: false,
    drawerOpen: false,
    edgeTouchStartX: null,
    edgeTouchStartY: null,
    shuffleEnabled: true,
    currentPathTemplate: "",
    currentMetaSnapshot: null,
    history: [],
    pb: {
      mode: null,
      sourceKey: "",
      artistName: null,
      albumName: null,
      tracks: null,
      trackIndex: 0,
      radioStream: false,
      radioBasePath: "",
    },
  };

  const mqMobile = window.matchMedia("(max-width: 768px)");

  const els = {
    content: document.getElementById("content"),
    pageTitle: document.getElementById("page-title"),
    pageSubtitle: document.getElementById("page-subtitle"),
    audio: document.getElementById("audio"),
    playerControls: document.getElementById("player-controls"),
    btnPlay: document.getElementById("btn-play"),
    btnPrev: document.getElementById("btn-prev"),
    btnNext: document.getElementById("btn-next"),
    btnShuffle: document.getElementById("btn-shuffle"),
    iconPlay: document.getElementById("icon-play"),
    iconPause: document.getElementById("icon-pause"),
    playerTitle: document.getElementById("player-title"),
    playerSub: document.getElementById("player-sub"),
    playerCover: document.getElementById("player-cover"),
    volume: document.getElementById("volume"),
    progressFill: document.getElementById("progress-fill"),
    progressInd: document.getElementById("progress-indeterminate"),
    timeCurrent: document.getElementById("time-current"),
    timeTotal: document.getElementById("time-total"),
    loading: document.getElementById("loading-overlay"),
    navItems: document.querySelectorAll("[data-nav]"),
    btnMenu: document.getElementById("btn-menu"),
    sidebar: document.getElementById("sidebar"),
    drawerBackdrop: document.getElementById("drawer-backdrop"),
    main: document.getElementById("main"),
    body: document.body,
    nowPlayingMini: document.getElementById("now-playing-mini"),
    npmTitle: document.getElementById("npm-title"),
    npmSub: document.getElementById("npm-sub"),
    npmCover: document.getElementById("npm-cover"),
    npmCoverFb: document.getElementById("npm-cover-fallback"),
    npmPlay: document.getElementById("npm-play"),
    npmIconPlay: document.getElementById("npm-icon-play"),
    npmIconPause: document.getElementById("npm-icon-pause"),
  };

  let songsCache = null;

  function loadShufflePreference() {
    try {
      const v = localStorage.getItem(LS_SHUFFLE);
      if (v === "0" || v === "false") return false;
      if (v === "1" || v === "true") return true;
    } catch (e) {
      /* ignore */
    }
    return true;
  }

  function saveShufflePreference() {
    try {
      localStorage.setItem(LS_SHUFFLE, state.shuffleEnabled ? "1" : "0");
    } catch (e) {
      /* ignore */
    }
  }

  function updateShuffleUi() {
    if (!els.btnShuffle) return;
    els.btnShuffle.classList.toggle("btn-shuffle--on", state.shuffleEnabled);
    els.btnShuffle.setAttribute("aria-pressed", state.shuffleEnabled ? "true" : "false");
    els.btnShuffle.setAttribute(
      "aria-label",
      state.shuffleEnabled ? "Aleatório ligado (clique para ordem fixa)" : "Ordem fixa (clique para aleatório)"
    );
  }

  function streamUrl(path) {
    const sep = path.includes("?") ? "&" : "?";
    return path + sep + "t=" + Date.now();
  }

  function stripCacheBust(path) {
    if (!path) return "";
    const q = path.indexOf("?");
    if (q === -1) return path;
    const base = path.slice(0, q);
    const rest = path.slice(q + 1);
    const parts = rest.split("&").filter(function (kv) {
      return !/^t=\d+$/.test(kv);
    });
    if (parts.length === 0) return base;
    return base + "?" + parts.join("&");
  }

  function coverUrl(artist, album) {
    if (!artist || !album) return "";
    return "/library/cover/" + encodeURIComponent(artist) + "/" + encodeURIComponent(album);
  }

  function isMobileNav() {
    return mqMobile.matches;
  }

  function setDrawerOpen(open) {
    state.drawerOpen = open;
    if (!els.sidebar || !els.btnMenu || !els.drawerBackdrop) return;
    els.sidebar.classList.toggle("sidebar--open", open);
    els.drawerBackdrop.classList.toggle("is-visible", open);
    els.drawerBackdrop.setAttribute("aria-hidden", open ? "false" : "true");
    els.btnMenu.setAttribute("aria-expanded", open ? "true" : "false");
    els.body.classList.toggle("drawer-open", open);
    if (!isMobileNav()) {
      els.sidebar.classList.remove("sidebar--open");
      els.drawerBackdrop.classList.remove("is-visible");
      els.body.classList.remove("drawer-open");
      els.btnMenu.setAttribute("aria-expanded", "false");
    }
  }

  function openDrawer() {
    if (!isMobileNav()) return;
    setDrawerOpen(true);
    const first = els.sidebar && els.sidebar.querySelector(".nav-item");
    if (first) first.focus();
  }

  function closeDrawer() {
    setDrawerOpen(false);
    if (els.btnMenu && isMobileNav()) els.btnMenu.focus();
  }

  function toggleDrawer() {
    if (state.drawerOpen) closeDrawer();
    else openDrawer();
  }

  function setContentLoading(on) {
    if (!els.content) return;
    els.content.classList.toggle("content--loading", !!on);
  }

  function updateNpmStripVisibility() {
    const hasSrc = !!(els.audio && els.audio.getAttribute("src"));
    if (!els.nowPlayingMini || !els.body) return;
    if (hasSrc) {
      els.body.classList.remove("npm-hidden");
      els.nowPlayingMini.classList.remove("hidden");
      els.nowPlayingMini.setAttribute("aria-hidden", "false");
    } else {
      els.body.classList.add("npm-hidden");
      els.nowPlayingMini.classList.add("hidden");
      els.nowPlayingMini.setAttribute("aria-hidden", "true");
    }
  }

  function syncNowPlayingMini() {
    if (!els.npmTitle || !els.npmSub) return;
    els.npmTitle.textContent = els.playerTitle ? els.playerTitle.textContent : "—";
    els.npmSub.textContent = els.playerSub ? els.playerSub.textContent : "";
  }

  function setNpmPlayingUi(playing) {
    if (!els.npmIconPlay || !els.npmIconPause) return;
    els.npmIconPlay.classList.toggle("hidden", playing);
    els.npmIconPause.classList.toggle("hidden", !playing);
  }

  function setTransportLocked(locked) {
    if (els.playerControls) els.playerControls.classList.toggle("is-busy", !!locked);
    [els.btnPrev, els.btnNext, els.btnPlay, els.btnShuffle].forEach(function (b) {
      if (b) b.disabled = !!locked;
    });
  }

  function setLoading(on) {
    els.loading.classList.toggle("hidden", !on);
    els.loading.setAttribute("aria-hidden", on ? "false" : "true");
    setTransportLocked(on);
  }

  function clonePb() {
    const p = state.pb;
    return {
      mode: p.mode,
      sourceKey: p.sourceKey,
      artistName: p.artistName,
      albumName: p.albumName,
      trackIndex: p.trackIndex,
      radioStream: p.radioStream,
      radioBasePath: p.radioBasePath,
      tracks: p.tracks ? p.tracks.slice() : null,
    };
  }

  function cloneMeta(m) {
    if (!m) return null;
    var o = {};
    for (var k in m) {
      if (Object.prototype.hasOwnProperty.call(m, k)) {
        if (k === "tracks" && m[k]) o[k] = m[k].slice();
        else o[k] = m[k];
      }
    }
    return o;
  }

  function pushPlaybackHistory() {
    if (!state.currentPathTemplate || !state.currentMetaSnapshot) return;
    state.history.unshift({
      pathTemplate: state.currentPathTemplate,
      metaSnapshot: cloneMeta(state.currentMetaSnapshot),
      pb: clonePb(),
    });
    while (state.history.length > HISTORY_MAX) {
      state.history.pop();
    }
  }

  function syncPbFromMeta(meta) {
    if (meta.mode != null) state.pb.mode = meta.mode;
    if (meta.sourceKey != null) state.pb.sourceKey = meta.sourceKey;
    if (meta.artistName !== undefined) state.pb.artistName = meta.artistName;
    if (meta.albumName !== undefined) state.pb.albumName = meta.albumName;
    if (meta.radioStream) {
      state.pb.radioStream = true;
      state.pb.radioBasePath = meta.radioBasePath || "";
      state.pb.tracks = null;
      state.pb.trackIndex = 0;
    } else {
      state.pb.radioStream = false;
      state.pb.radioBasePath = "";
      if (meta.tracks !== undefined) state.pb.tracks = meta.tracks;
      if (meta.trackIndex !== undefined) state.pb.trackIndex = meta.trackIndex;
    }
  }

  function appendModeHint(baseSub) {
    const b = (baseSub || "").trim();
    if (!state.pb.mode || state.pb.mode === "file") return b;
    const hint = state.shuffleEnabled ? "Aleatório" : "Ordem fixa";
    if (!b) return hint;
    if (b.indexOf("Ordem fixa") !== -1 || b.indexOf("Aleatório") !== -1) return b;
    return b + " · " + hint;
  }

  function setActiveNav(view) {
    els.navItems.forEach(function (btn) {
      btn.classList.toggle("active", btn.getAttribute("data-view") === view);
    });
  }

  function formatTime(sec) {
    if (!isFinite(sec) || sec < 0) return "—:—";
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return m + ":" + (s < 10 ? "0" : "") + s;
  }

  function updateProgressMode(isIndeterminate) {
    els.progressInd.classList.toggle("hidden", !isIndeterminate);
    if (isIndeterminate) els.progressFill.style.width = "0%";
  }

  function setPlayerCover(artist, album) {
    function applyTo(img, onLoad, onError) {
      if (artist && album) {
        const url = coverUrl(artist, album);
        img.onload = onLoad;
        img.onerror = onError;
        img.src = url + "?t=" + Date.now();
      } else {
        img.classList.add("hidden");
        img.removeAttribute("src");
      }
    }
    applyTo(
      els.playerCover,
      function () {
        els.playerCover.classList.remove("hidden");
      },
      function () {
        els.playerCover.classList.add("hidden");
      }
    );
    if (els.npmCover && els.npmCoverFb) {
      applyTo(
        els.npmCover,
        function () {
          els.npmCover.classList.remove("hidden");
        },
        function () {
          els.npmCover.classList.add("hidden");
        }
      );
    }
  }

  function playStream(path, meta, options) {
    options = options || {};
    if (!options.skipHistory && state.currentPathTemplate) {
      pushPlaybackHistory();
    }

    const pathTemplate = stripCacheBust(path);
    state.currentPathTemplate = pathTemplate;
    state.currentMetaSnapshot = cloneMeta(meta);

    syncPbFromMeta(meta);
    state.sourceKey = meta.sourceKey || "";
    state.isFileMode = !!meta.isFile;

    const url = streamUrl(path);
    const subText = appendModeHint(meta.sub || "");

    setLoading(true);
    els.audio.pause();
    els.audio.removeAttribute("src");
    els.audio.load();
    els.audio.src = url;
    els.audio.load();

    setPlayerCover(meta.coverArtist || null, meta.coverAlbum || null);
    els.playerTitle.textContent = meta.title || "A reproduzir";
    els.playerSub.textContent = subText;
    updateProgressMode(!state.isFileMode);
    syncNowPlayingMini();
    updateNpmStripVisibility();

    els.audio
      .play()
      .then(function () {
        setLoading(false);
        setPlayingUi(true);
        updateCardHighlights();
        updateHomePill();
      })
      .catch(function (err) {
        setLoading(false);
        setPlayingUi(false);
        els.playerSub.textContent = "Erro — " + (err.message || err);
        syncNowPlayingMini();
      });
  }

  function playTrackListAt(tracks, index, extras) {
    extras = extras || {};
    const t = tracks[index];
    if (!t) return;
    const path = "/radio/file?relative_path=" + encodeURIComponent(t.relative_path);
    playStream(
      path,
      {
        title: t.title || t.filename,
        sub: extras.sub != null ? extras.sub : "",
        sourceKey: extras.sourceKey != null ? extras.sourceKey : "file:" + t.relative_path,
        isFile: true,
        mode: extras.mode != null ? extras.mode : "file",
        artistName: extras.artistName !== undefined ? extras.artistName : t.folder_artist,
        albumName: extras.albumName !== undefined ? extras.albumName : t.folder_album,
        tracks: tracks,
        trackIndex: index,
        radioStream: false,
        radioBasePath: "",
        coverArtist: extras.coverArtist || t.folder_artist,
        coverAlbum: extras.coverAlbum || t.folder_album,
      },
      { skipHistory: !!extras.skipHistory }
    );
  }

  function sortByRelativePath(list) {
    return list.slice().sort(function (a, b) {
      return (a.relative_path || "").localeCompare(b.relative_path || "", undefined, { sensitivity: "base" });
    });
  }

  async function startPlaybackRandom() {
    if (state.shuffleEnabled) {
      playStream("/radio/random", {
        title: "Rádio aleatória",
        sub: "Toda a biblioteca",
        sourceKey: "radio:random",
        isFile: false,
        mode: "random",
        radioStream: true,
        radioBasePath: "/radio/random",
        artistName: null,
        albumName: null,
      });
      return;
    }
    const data = await getSongsData();
    const tracks = sortByRelativePath(data.songs || []);
    if (!tracks.length) {
      els.playerSub.textContent = "Sem faixas na biblioteca.";
      return;
    }
    playTrackListAt(tracks, 0, {
      sub: "Biblioteca · ordem fixa",
      sourceKey: "order:library:" + tracks[0].relative_path,
      mode: "random",
      artistName: null,
      albumName: null,
      coverArtist: tracks[0].folder_artist,
      coverAlbum: tracks[0].folder_album,
    });
  }

  async function startPlaybackArtist(artistName, coverArtist, coverAlbum) {
    const sk = "radio:artist:" + artistName;
    if (state.shuffleEnabled) {
      const enc = encodeURIComponent(artistName);
      playStream("/radio/artist/" + enc, {
        title: artistName,
        sub: "Faixas do artista",
        sourceKey: sk,
        isFile: false,
        mode: "artist",
        artistName: artistName,
        albumName: null,
        radioStream: true,
        radioBasePath: "/radio/artist/" + enc,
        coverArtist: coverArtist || artistName,
        coverAlbum: coverAlbum || null,
      });
      return;
    }
    const data = await getSongsData();
    const tracks = sortByRelativePath(
      (data.songs || []).filter(function (s) {
        return s.folder_artist === artistName;
      })
    );
    if (!tracks.length) {
      els.playerSub.textContent = "Sem faixas para este artista.";
      return;
    }
    playTrackListAt(tracks, 0, {
      sub: artistName,
      sourceKey: "order:artist:" + artistName + ":" + tracks[0].relative_path,
      mode: "artist",
      artistName: artistName,
      coverArtist: coverArtist || artistName,
      coverAlbum: coverAlbum || tracks[0].folder_album,
    });
  }

  async function startPlaybackAlbum(artistName, albumName) {
    const data = await getSongsData();
    const tracks = sortTracks(
      (data.songs || []).filter(function (s) {
        return s.folder_artist === artistName && s.folder_album === albumName;
      })
    );
    if (!tracks.length) return;
    const sk = "radio:album:" + artistName + "/" + albumName;
    if (state.shuffleEnabled) {
      const idx = Math.floor(Math.random() * tracks.length);
      playTrackListAt(tracks, idx, {
        sub: artistName + " · " + albumName,
        sourceKey: sk,
        mode: "album",
        artistName: artistName,
        albumName: albumName,
        coverArtist: artistName,
        coverAlbum: albumName,
      });
      return;
    }
    const path =
      "/radio/album/" +
      encodeURIComponent(artistName) +
      "/" +
      encodeURIComponent(albumName);
    playStream(path, {
      title: albumName,
      sub: artistName + " · ordem + loop",
      sourceKey: sk,
      isFile: false,
      mode: "album",
      artistName: artistName,
      albumName: albumName,
      radioStream: true,
      radioBasePath: path,
      coverArtist: artistName,
      coverAlbum: albumName,
    });
  }

  function radioReconnectMeta(mode) {
    const m = {
      isFile: false,
      mode: mode,
      radioStream: true,
      artistName: state.pb.artistName,
      albumName: state.pb.albumName,
      sourceKey: state.pb.sourceKey,
      coverArtist: state.currentMetaSnapshot ? state.currentMetaSnapshot.coverArtist : null,
      coverAlbum: state.currentMetaSnapshot ? state.currentMetaSnapshot.coverAlbum : null,
    };
    if (mode === "random") {
      m.artistName = null;
      m.albumName = null;
      m.title = "Rádio aleatória";
      m.sub = "Toda a biblioteca";
      m.sourceKey = "radio:random";
      m.radioBasePath = "/radio/random";
    } else if (mode === "artist" && state.pb.artistName) {
      const name = state.pb.artistName;
      m.albumName = null;
      m.title = name;
      m.sub = "Faixas do artista";
      m.sourceKey = "radio:artist:" + name;
      const enc = encodeURIComponent(name);
      m.radioBasePath = "/radio/artist/" + enc;
      m.coverArtist = m.coverArtist || name;
    } else if (mode === "album" && state.pb.artistName && state.pb.albumName) {
      const a = state.pb.artistName;
      const al = state.pb.albumName;
      m.title = al;
      m.sub = a + " · ordem + loop";
      m.sourceKey = "radio:album:" + a + "/" + al;
      m.radioBasePath =
        "/radio/album/" + encodeURIComponent(a) + "/" + encodeURIComponent(al);
      m.coverArtist = a;
      m.coverAlbum = al;
    }
    return m;
  }

  function onNext() {
    if (els.loading && !els.loading.classList.contains("hidden")) return;

    if (state.pb.radioStream) {
      if (state.pb.mode === "random") {
        playStream("/radio/random", radioReconnectMeta("random"));
        return;
      }
      if (state.pb.mode === "artist" && state.pb.radioBasePath) {
        playStream(state.pb.radioBasePath, radioReconnectMeta("artist"));
        return;
      }
      if (state.pb.mode === "album" && state.pb.radioBasePath) {
        playStream(state.pb.radioBasePath, radioReconnectMeta("album"));
        return;
      }
      return;
    }

    const tr = state.pb.tracks;
    if (!tr || !tr.length) return;

    if (state.pb.mode === "album" && state.shuffleEnabled) {
      let ni = Math.floor(Math.random() * tr.length);
      if (tr.length > 1) {
        while (ni === state.pb.trackIndex) ni = Math.floor(Math.random() * tr.length);
      }
      playTrackListAt(tr, ni, {
        sub: state.pb.artistName + " · " + state.pb.albumName,
        sourceKey: "radio:album:" + state.pb.artistName + "/" + state.pb.albumName,
        mode: "album",
        artistName: state.pb.artistName,
        albumName: state.pb.albumName,
        coverArtist: state.pb.artistName,
        coverAlbum: state.pb.albumName,
      });
      return;
    }

    const ni = (state.pb.trackIndex + 1) % tr.length;
    const t = tr[ni];
    const baseSub =
      state.pb.mode === "random"
        ? "Biblioteca · ordem fixa"
        : state.pb.mode === "artist"
          ? state.pb.artistName || ""
          : state.pb.artistName && state.pb.albumName
            ? state.pb.artistName + " · " + state.pb.albumName
            : "";
    let sk =
      state.pb.mode === "random"
        ? "order:library:" + t.relative_path
        : state.pb.mode === "artist"
          ? "order:artist:" + state.pb.artistName + ":" + t.relative_path
          : "radio:album:" + state.pb.artistName + "/" + state.pb.albumName;
    playTrackListAt(tr, ni, {
      sub: baseSub,
      sourceKey: sk,
      mode: state.pb.mode,
      artistName: state.pb.artistName,
      albumName: state.pb.albumName,
      coverArtist: t.folder_artist,
      coverAlbum: t.folder_album,
    });
  }

  function restoreHistoryEntry(entry) {
    playStream(entry.pathTemplate, entry.metaSnapshot, { skipHistory: true });
  }

  function onPrev() {
    if (els.loading && !els.loading.classList.contains("hidden")) return;

    if (state.isFileMode && els.audio.currentTime > PREV_RESTART_SEC) {
      els.audio.currentTime = 0;
      return;
    }

    if (state.isFileMode && state.pb.tracks && state.pb.tracks.length && state.pb.trackIndex > 0) {
      const tr = state.pb.tracks;
      const pi = state.pb.trackIndex - 1;
      const t = tr[pi];
      const baseSub =
        state.pb.mode === "random"
          ? "Biblioteca · ordem fixa"
          : state.pb.mode === "artist"
            ? state.pb.artistName || ""
            : state.pb.artistName && state.pb.albumName
              ? state.pb.artistName + " · " + state.pb.albumName
              : "";
      let sk =
        state.pb.mode === "random"
          ? "order:library:" + t.relative_path
          : state.pb.mode === "artist"
            ? "order:artist:" + state.pb.artistName + ":" + t.relative_path
            : "radio:album:" + state.pb.artistName + "/" + state.pb.albumName;
      playTrackListAt(tr, pi, {
        sub: baseSub,
        sourceKey: sk,
        mode: state.pb.mode,
        artistName: state.pb.artistName,
        albumName: state.pb.albumName,
        coverArtist: t.folder_artist,
        coverAlbum: t.folder_album,
        skipHistory: true,
      });
      return;
    }

    if (state.history.length > 0) {
      const h = state.history.shift();
      restoreHistoryEntry(h);
      return;
    }

    if (state.isFileMode) {
      els.audio.currentTime = 0;
      return;
    }

    if (state.pb.radioStream && state.pb.radioBasePath) {
      playStream(state.pb.radioBasePath, radioReconnectMeta(state.pb.mode), { skipHistory: true });
    }
  }

  function setPlayingUi(playing) {
    state.playing = playing;
    els.iconPlay.classList.toggle("hidden", playing);
    els.iconPause.classList.toggle("hidden", !playing);
    setNpmPlayingUi(playing);
  }

  function togglePlayPause() {
    if (!els.audio.src) return;
    if (els.audio.paused) {
      els.audio.play().then(function () {
        setPlayingUi(true);
      });
    } else {
      els.audio.pause();
      setPlayingUi(false);
    }
  }

  function updateHomePill() {
    const pill = document.getElementById("home-source-pill");
    if (!pill) return;
    if (state.sourceKey === "radio:random") {
      pill.textContent = "Fonte: Rádio aleatória";
      pill.classList.remove("idle");
    }
  }

  function updateCardHighlights() {
    document.querySelectorAll(".card-active").forEach(function (c) {
      c.classList.remove("card-active");
    });
    const sk = state.sourceKey;
    if (!sk) return;
    document.querySelectorAll(".card[data-source-key]").forEach(function (card) {
      if (card.getAttribute("data-source-key") === sk) {
        card.classList.add("card-active");
      }
    });
  }

  if (els.btnMenu) {
    els.btnMenu.addEventListener("click", function () {
      toggleDrawer();
    });
  }

  if (els.drawerBackdrop) {
    els.drawerBackdrop.addEventListener("click", function () {
      closeDrawer();
    });
  }

  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape" && state.drawerOpen) {
      ev.preventDefault();
      closeDrawer();
    }
  });

  function onResizeNav() {
    if (!isMobileNav()) closeDrawer();
  }

  if (typeof mqMobile.addEventListener === "function") {
    mqMobile.addEventListener("change", onResizeNav);
  } else if (typeof mqMobile.addListener === "function") {
    mqMobile.addListener(onResizeNav);
  }
  window.addEventListener("resize", onResizeNav);

  if (els.main) {
    els.main.addEventListener(
      "touchstart",
      function (ev) {
        if (!isMobileNav() || state.drawerOpen) return;
        const t = ev.changedTouches[0];
        if (t.clientX <= 28) {
          state.edgeTouchStartX = t.clientX;
          state.edgeTouchStartY = t.clientY;
        } else {
          state.edgeTouchStartX = null;
        }
      },
      { passive: true }
    );
    els.main.addEventListener(
      "touchend",
      function (ev) {
        if (state.edgeTouchStartX == null || !isMobileNav() || state.drawerOpen) return;
        const t = ev.changedTouches[0];
        const dx = t.clientX - state.edgeTouchStartX;
        const dy = Math.abs(t.clientY - state.edgeTouchStartY);
        state.edgeTouchStartX = null;
        if (dx > 56 && dy < 80) openDrawer();
      },
      { passive: true }
    );
  }

  if (els.btnPrev) els.btnPrev.addEventListener("click", onPrev);
  if (els.btnNext) els.btnNext.addEventListener("click", onNext);
  if (els.btnShuffle) {
    els.btnShuffle.addEventListener("click", function () {
      state.shuffleEnabled = !state.shuffleEnabled;
      saveShufflePreference();
      updateShuffleUi();
      if (els.playerTitle && els.playerTitle.textContent && els.audio.getAttribute("src")) {
        const rawSub = state.currentMetaSnapshot ? state.currentMetaSnapshot.sub || "" : "";
        els.playerSub.textContent = appendModeHint(rawSub);
        syncNowPlayingMini();
      }
    });
  }

  els.btnPlay.addEventListener("click", togglePlayPause);
  if (els.npmPlay) {
    els.npmPlay.addEventListener("click", function (e) {
      e.stopPropagation();
      togglePlayPause();
    });
  }

  els.volume.addEventListener("input", function () {
    els.audio.volume = Number(els.volume.value) / 100;
  });
  els.audio.volume = 1;

  els.audio.addEventListener("play", function () {
    setPlayingUi(true);
    syncNowPlayingMini();
  });
  els.audio.addEventListener("pause", function () {
    setPlayingUi(false);
    syncNowPlayingMini();
  });
  els.audio.addEventListener("loadedmetadata", function () {
    const d = els.audio.duration;
    if (state.isFileMode && isFinite(d)) {
      updateProgressMode(false);
      els.timeTotal.textContent = formatTime(d);
    } else {
      els.timeTotal.textContent = "∞";
    }
  });
  els.audio.addEventListener("timeupdate", function () {
    const d = els.audio.duration;
    const t = els.audio.currentTime;
    els.timeCurrent.textContent = formatTime(t);
    if (state.isFileMode && isFinite(d) && d > 0) {
      els.progressFill.style.width = Math.min(100, (t / d) * 100) + "%";
    }
  });
  els.audio.addEventListener("error", function () {
    setLoading(false);
    const c = els.audio.error ? els.audio.error.code : "?";
    els.playerSub.textContent = "Erro no áudio (código " + c + ")";
    syncNowPlayingMini();
  });

  async function fetchJson(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(r.status + " " + r.statusText);
    return r.json();
  }

  async function getSongsData() {
    if (!songsCache) songsCache = await fetchJson("/songs");
    return songsCache;
  }

  function buildAlbumsIndex(data) {
    const byArtist = new Map();
    (data.songs || []).forEach(function (s) {
      const a = s.folder_artist || "root";
      const al = s.folder_album || "root";
      if (!byArtist.has(a)) byArtist.set(a, new Map());
      const albums = byArtist.get(a);
      if (!albums.has(al)) albums.set(al, []);
      albums.get(al).push(s);
    });
    return byArtist;
  }

  function sortTracks(list) {
    return list.slice().sort(function (a, b) {
      const ma = /^(\d+)/.exec(a.filename);
      const mb = /^(\d+)/.exec(b.filename);
      const na = ma ? parseInt(ma[1], 10) : NaN;
      const nb = mb ? parseInt(mb[1], 10) : NaN;
      if (!isNaN(na) && !isNaN(nb) && na !== nb) return na - nb;
      return a.filename.localeCompare(b.filename, undefined, { sensitivity: "base" });
    });
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function renderHome() {
    closeDrawer();
    setActiveNav("home");
    setContentLoading(false);
    els.pageTitle.textContent = "Boa-vinda";
    els.pageSubtitle.textContent = "O teu streaming local";
    const pillClass = state.sourceKey === "radio:random" ? "source-pill" : "source-pill idle";
    const pillText =
      state.sourceKey === "radio:random" ? "A reproduzir: Rádio aleatória" : "Fonte: nenhuma";
    els.content.innerHTML =
      '<div class="hero-actions">' +
      '<button type="button" class="btn-primary" id="home-radio">▶ Rádio aleatória</button>' +
      '<button type="button" class="btn-secondary" id="home-artists">Ver artistas</button>' +
      '</div><p class="' +
      pillClass +
      '" id="home-source-pill">' +
      pillText +
      "</p>";

    document.getElementById("home-radio").onclick = function () {
      startPlaybackRandom().catch(function (e) {
        els.playerSub.textContent = escapeHtml(String(e.message || e));
      });
    };
    document.getElementById("home-artists").onclick = function () {
      renderArtists();
    };
  }

  async function renderArtists() {
    closeDrawer();
    setActiveNav("artists");
    setContentLoading(true);
    els.pageTitle.textContent = "Artistas";
    els.pageSubtitle.textContent = "A carregar…";
    els.content.innerHTML = '<p class="empty-state">A carregar…</p>';

    try {
      const data = await fetchJson("/artists");
      els.pageSubtitle.textContent = data.total_artists + " artista(s)";
      if (!data.artists || !data.artists.length) {
        els.content.innerHTML =
          '<div class="empty-state"><strong>Sem artistas</strong><p>Adiciona MP3 em MUSIC_DIR.</p></div>';
        setContentLoading(false);
        return;
      }
      const grid = document.createElement("div");
      grid.className = "grid-cards";
      data.artists.forEach(function (name) {
        const sk = "radio:artist:" + name;
        const card = document.createElement("div");
        card.className = "card";
        card.setAttribute("data-source-key", sk);
        if (state.sourceKey === sk) card.classList.add("card-active");
        card.innerHTML =
          '<div class="card-image-wrap"><div class="card-placeholder">♪</div></div>' +
          '<h3 class="card-title"></h3><p class="card-sub">Artista</p>';
        card.querySelector(".card-title").textContent = name;
        card.onclick = function () {
          renderArtistDetail(name);
        };
        grid.appendChild(card);
      });
      els.content.innerHTML = "";
      els.content.appendChild(grid);
    } catch (e) {
      els.content.innerHTML =
        '<div class="empty-state"><strong>Erro</strong><p>' + escapeHtml(String(e.message || e)) + "</p></div>";
    }
    setContentLoading(false);
  }

  async function renderArtistDetail(artistName) {
    closeDrawer();
    setActiveNav("artists");
    setContentLoading(true);
    els.pageTitle.textContent = artistName;
    els.pageSubtitle.textContent = "Álbuns";
    els.content.innerHTML = '<p class="empty-state">A carregar…</p>';

    try {
      const data = await fetchJson("/albums/" + encodeURIComponent(artistName));
      const skArtist = "radio:artist:" + data.artist;

      const wrap = document.createElement("div");
      wrap.innerHTML =
        '<button type="button" class="back-link" id="artist-back">← Artistas</button>' +
        '<div class="detail-header">' +
        '<img class="detail-cover hidden" id="artist-hero-cover" alt="" />' +
        '<div class="detail-cover-ph" id="artist-hero-ph">♪</div>' +
        "<div><h2 style=margin:0 0 0.5rem;font-size:clamp(1.35rem,4vw,2rem)>" +
        escapeHtml(data.artist) +
        "</h2>" +
        "<p style=color:var(--text-secondary);margin:0>" +
        data.total_albums +
        " álbum(ns)</p></div></div>" +
        '<div class="detail-actions">' +
        '<button type="button" class="btn-primary" id="play-artist">▶ Reproduzir artista</button>' +
        "</div>" +
        '<div class="grid-cards" id="artist-albums"></div>';

      els.content.innerHTML = "";
      els.content.appendChild(wrap);

      if (data.albums && data.albums[0]) {
        const img = document.getElementById("artist-hero-cover");
        img.src = coverUrl(data.artist, data.albums[0]) + "?t=" + Date.now();
        img.onload = function () {
          img.classList.remove("hidden");
          document.getElementById("artist-hero-ph").classList.add("hidden");
        };
        img.onerror = function () {
          img.classList.add("hidden");
        };
      }

      document.getElementById("artist-back").onclick = function () {
        renderArtists();
      };
      document.getElementById("play-artist").onclick = function () {
        startPlaybackArtist(
          data.artist,
          data.artist,
          data.albums && data.albums[0] ? data.albums[0] : null
        ).catch(function (e) {
          els.playerSub.textContent = escapeHtml(String(e.message || e));
        });
      };

      const grid = document.getElementById("artist-albums");
      data.albums.forEach(function (album) {
        const sk = "radio:album:" + data.artist + "/" + album;
        const card = document.createElement("div");
        card.className = "card";
        card.setAttribute("data-source-key", sk);
        if (state.sourceKey === sk) card.classList.add("card-active");
        card.innerHTML =
          '<div class="card-image-wrap">' +
          '<img class="card-image" alt="" loading="lazy" />' +
          '<div class="card-placeholder hidden">▣</div></div>' +
          '<h3 class="card-title"></h3><p class="card-sub">Álbum</p>';
        card.querySelector(".card-title").textContent = album;
        const im = card.querySelector(".card-image");
        const ph = card.querySelector(".card-placeholder");
        im.src = coverUrl(data.artist, album) + "?t=" + Date.now();
        im.onload = function () {
          ph.classList.add("hidden");
        };
        im.onerror = function () {
          im.classList.add("hidden");
          ph.classList.remove("hidden");
        };
        card.onclick = function () {
          renderAlbumDetail(data.artist, album, "artist");
        };
        grid.appendChild(card);
      });
    } catch (e) {
      els.content.innerHTML =
        '<div class="empty-state"><button type="button" class="back-link" id="e-back">← Artistas</button>' +
        "<strong>Erro</strong><p>" +
        escapeHtml(String(e.message || e)) +
        "</p></div>";
      document.getElementById("e-back").onclick = function () {
        renderArtists();
      };
    }
    setContentLoading(false);
  }

  async function renderAlbumDetail(artistName, albumName, backMode) {
    closeDrawer();
    backMode = backMode || "albums";
    setActiveNav("albums");
    setContentLoading(true);
    els.pageTitle.textContent = albumName;
    els.pageSubtitle.textContent = artistName;

    const data = await getSongsData();
    const tracks = (data.songs || []).filter(function (s) {
      return s.folder_artist === artistName && s.folder_album === albumName;
    });
    const sorted = sortTracks(tracks);
    const sk = "radio:album:" + artistName + "/" + albumName;

    const wrap = document.createElement("div");
    wrap.innerHTML =
      '<button type="button" class="back-link" id="alb-back">← Voltar</button>' +
      '<div class="detail-header">' +
      '<img class="detail-cover" id="alb-cover" alt="" />' +
      "<div><h2 style=margin:0 0 0.25rem;font-size:clamp(1.2rem,3.5vw,1.5rem)>" +
      escapeHtml(albumName) +
      "</h2>" +
      "<p style=color:var(--text-secondary);margin:0>" +
      escapeHtml(artistName) +
      "</p></div></div>" +
      '<div class="detail-actions">' +
      '<button type="button" class="btn-primary" id="play-album">▶ Reproduzir álbum</button>' +
      "</div>" +
      '<ul class="track-list" id="track-list"></ul>';

    els.content.innerHTML = "";
    els.content.appendChild(wrap);

    document.getElementById("alb-back").onclick = function () {
      if (backMode === "artist") renderArtistDetail(artistName);
      else renderAlbums();
    };

    const cov = document.getElementById("alb-cover");
    cov.src = coverUrl(artistName, albumName) + "?t=" + Date.now();
    cov.onerror = function () {
      cov.style.visibility = "hidden";
    };

    document.getElementById("play-album").onclick = function () {
      startPlaybackAlbum(artistName, albumName).catch(function (e) {
        els.playerSub.textContent = escapeHtml(String(e.message || e));
      });
    };

    const ul = document.getElementById("track-list");
    if (!sorted.length) {
      ul.innerHTML = '<li class="empty-state" style="grid-column:1/-1">Sem faixas neste álbum.</li>';
    } else {
      sorted.forEach(function (t, i) {
        const li = document.createElement("li");
        li.className = "track-item";
        li.innerHTML =
          '<span class="track-num">' +
          (i + 1) +
          '</span><span class="track-name"></span><span class="btn-small" role="button" tabindex="0">▶</span>';
        li.querySelector(".track-name").textContent = t.title || t.filename;
        function playTrack(ev) {
          if (ev) ev.stopPropagation();
          playTrackListAt(sorted, i, {
            sub: artistName + " · " + albumName,
            sourceKey: sk,
            mode: "album",
            artistName: artistName,
            albumName: albumName,
            coverArtist: artistName,
            coverAlbum: albumName,
          });
        }
        li.onclick = playTrack;
        li.querySelector(".btn-small").onclick = playTrack;
        ul.appendChild(li);
      });
    }
    setContentLoading(false);
  }

  async function renderAlbums() {
    closeDrawer();
    setActiveNav("albums");
    setContentLoading(true);
    els.pageTitle.textContent = "Álbuns";
    els.pageSubtitle.textContent = "A carregar…";
    els.content.innerHTML = '<p class="empty-state">A carregar…</p>';

    try {
      const data = await getSongsData();
      const index = buildAlbumsIndex(data);
      const artists = Array.from(index.keys()).sort(function (a, b) {
        return a.localeCompare(b, undefined, { sensitivity: "base" });
      });

      if (!artists.length) {
        els.content.innerHTML =
          '<div class="empty-state"><strong>Sem álbuns</strong><p>Importa música para MUSIC_DIR.</p></div>';
        setContentLoading(false);
        return;
      }

      els.pageSubtitle.textContent = artists.length + " artista(s)";
      const root = document.createElement("div");
      artists.forEach(function (artist) {
        const albumsMap = index.get(artist);
        const albumNames = Array.from(albumsMap.keys()).sort(function (a, b) {
          return a.localeCompare(b, undefined, { sensitivity: "base" });
        });
        const section = document.createElement("section");
        section.style.marginBottom = "2.5rem";
        const h = document.createElement("h2");
        h.style.cssText =
          "font-size:clamp(1.05rem,3vw,1.25rem);margin:0 0 1rem;letter-spacing:-0.02em";
        h.textContent = artist;
        section.appendChild(h);

        const grid = document.createElement("div");
        grid.className = "grid-cards";
        albumNames.forEach(function (album) {
          const sk = "radio:album:" + artist + "/" + album;
          const card = document.createElement("div");
          card.className = "card";
          card.setAttribute("data-source-key", sk);
          if (state.sourceKey === sk) card.classList.add("card-active");
          card.innerHTML =
            '<div class="card-image-wrap">' +
            '<img class="card-image" alt="" loading="lazy" />' +
            '<div class="card-placeholder hidden">▣</div></div>' +
            '<h3 class="card-title"></h3><p class="card-sub"></p>';
          card.querySelector(".card-title").textContent = album;
          card.querySelector(".card-sub").textContent = artist;
          const im = card.querySelector(".card-image");
          const ph = card.querySelector(".card-placeholder");
          im.src = coverUrl(artist, album) + "?t=" + Date.now();
          im.onload = function () {
            ph.classList.add("hidden");
          };
          im.onerror = function () {
            im.classList.add("hidden");
            ph.classList.remove("hidden");
          };
          card.onclick = function () {
            renderAlbumDetail(artist, album, "albums");
          };
          grid.appendChild(card);
        });
        section.appendChild(grid);
        root.appendChild(section);
      });
      els.content.innerHTML = "";
      els.content.appendChild(root);
    } catch (e) {
      els.content.innerHTML =
        '<div class="empty-state"><strong>Erro</strong><p>' + escapeHtml(String(e.message || e)) + "</p></div>";
    }
    setContentLoading(false);
  }

  function renderRadioView() {
    closeDrawer();
    setActiveNav("radio");
    setContentLoading(false);
    els.pageTitle.textContent = "Rádio aleatória";
    els.pageSubtitle.textContent = "Stream contínuo · shuffle";
    const active = state.sourceKey === "radio:random";
    els.content.innerHTML =
      '<div class="hero-actions">' +
      '<button type="button" class="btn-primary" id="radio-go">▶ Iniciar rádio</button>' +
      "</div>" +
      '<p class="' +
      (active ? "source-pill" : "source-pill idle") +
      '" id="radio-pill">' +
      (active ? "A reproduzir esta fonte" : "Parado") +
      "</p>";

    document.getElementById("radio-go").onclick = function () {
      startPlaybackRandom()
        .then(function () {
          var p = document.getElementById("radio-pill");
          if (p) {
            p.textContent = "A reproduzir esta fonte";
            p.classList.remove("idle");
          }
        })
        .catch(function (e) {
          els.playerSub.textContent = escapeHtml(String(e.message || e));
        });
    };
  }

  function navigate(view) {
    if (view === "home") renderHome();
    else if (view === "artists") renderArtists();
    else if (view === "albums") renderAlbums();
    else if (view === "radio") renderRadioView();
  }

  els.navItems.forEach(function (btn) {
    btn.addEventListener("click", function () {
      navigate(btn.getAttribute("data-view"));
      if (isMobileNav()) closeDrawer();
    });
  });

  state.shuffleEnabled = loadShufflePreference();
  updateShuffleUi();

  updateNpmStripVisibility();
  syncNowPlayingMini();
  setNpmPlayingUi(false);
  setTransportLocked(false);

  renderHome();
})();
