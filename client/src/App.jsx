import { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import {
  TMDB, IMG, TMDB_ENDPOINTS,
  searchMagpie, searchTMDB, fetchFiles, startDownloadApi, fetchStreams,
} from "./lib/api";
import { useDebounce, useToast, useJobPoller } from "./hooks/index";
import { pollJob } from "./lib/api";

const CATEGORIES = ["Trending", "Movies", "TV Shows", "Crime", "Drama", "Thriller"];

const Icon = {
  Home: () => (<svg viewBox="0 0 24 24" fill="currentColor" width="22" height="22"><path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/></svg>),
  Search: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="22" height="22"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>),
  Download: () => (<svg viewBox="0 0 24 24" fill="currentColor" width="22" height="22"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>),
  List: () => (<svg viewBox="0 0 24 24" fill="currentColor" width="22" height="22"><path d="M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z"/></svg>),
  Play: () => (<svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M8 5v14l11-7z"/></svg>),
  Plus: () => (<svg viewBox="0 0 24 24" fill="currentColor" width="18" height="18"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>),
  Info: () => (<svg viewBox="0 0 24 24" fill="currentColor" width="18" height="18"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>),
  Close: () => (<svg viewBox="0 0 24 24" fill="currentColor" width="22" height="22"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>),
  ChevronLeft: () => (<svg viewBox="0 0 24 24" fill="currentColor" width="24" height="24"><path d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z"/></svg>),
  ChevronRight: () => (<svg viewBox="0 0 24 24" fill="currentColor" width="24" height="24"><path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/></svg>),
  Star: () => (<svg viewBox="0 0 24 24" fill="#f5c518" width="13" height="13"><path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/></svg>),
  Volume: () => (<svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02z"/></svg>),
  Fullscreen: () => (<svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"/></svg>),
  Pause: () => (<svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>),
};

function Carousel({ title, items, onSelect, onPlay }) {
  const rowRef = useRef(null);
  const [showLeft, setShowLeft] = useState(false);
  const [showRight, setShowRight] = useState(true);
  const scroll = (dir) => rowRef.current?.scrollBy({ left: dir * 600, behavior: "smooth" });
  const onScroll = () => {
    const el = rowRef.current;
    if (!el) return;
    setShowLeft(el.scrollLeft > 10);
    setShowRight(el.scrollLeft < el.scrollWidth - el.clientWidth - 10);
  };
  if (!items?.length) return null;
  return (
    <div className="carousel-section">
      <h2 className="carousel-title">{title}</h2>
      <div className="carousel-wrapper">
        {showLeft && <button className="carousel-btn carousel-btn-left" onClick={() => scroll(-1)}><Icon.ChevronLeft /></button>}
        <div className="carousel-row" ref={rowRef} onScroll={onScroll}>
          {items.map((item, i) => <MediaCard key={i} item={item} onSelect={onSelect} onPlay={onPlay} />)}
        </div>
        {showRight && <button className="carousel-btn carousel-btn-right" onClick={() => scroll(1)}><Icon.ChevronRight /></button>}
      </div>
    </div>
  );
}

function MediaCard({ item, onSelect, onPlay }) {
  const [hover, setHover] = useState(false);
  const title = item.title || item.name;
  const year = (item.release_date || item.first_air_date || "").slice(0, 4);
  const poster = IMG(item.poster_path);
  const rating = item.vote_average?.toFixed(1);
  const payload = { detailPath: title, subjectId: item.id, title, cover: IMG(item.poster_path), backdrop: IMG(item.backdrop_path, "w1280"), overview: item.overview, year, rating, mediaType: item.media_type || (item.first_air_date ? "tv" : "movie"), _fromTMDB: true };
  return (
    <div className={`media-card ${hover ? "media-card--hover" : ""}`} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)} onClick={() => onSelect(payload)}>
      {poster ? <img src={poster} alt={title} className="media-card__poster" loading="lazy" /> : <div className="media-card__placeholder">🎬</div>}
      <div className="media-card__overlay">
        <div className="media-card__meta">
          <span className="media-card__title">{title}</span>
          <span className="media-card__sub"><Icon.Star /> {rating} · {year}</span>
        </div>
        <div className="media-card__actions">
          <button className="btn-play-sm" onClick={(e) => { e.stopPropagation(); onPlay({ detailPath: title, subjectId: item.id, title, _fromTMDB: true }); }}><Icon.Play /> Watch</button>
          <button className="btn-dl-sm" onClick={(e) => { e.stopPropagation(); onSelect(payload); }}><Icon.Plus /></button>
        </div>
      </div>
    </div>
  );
}

function Hero({ item, onPlay, onSelect }) {
  const [loaded, setLoaded] = useState(false);
  if (!item) return <div className="hero hero--skeleton" />;
  const title = item.title || item.name;
  const year = (item.release_date || item.first_air_date || "").slice(0, 4);
  const backdrop = IMG(item.backdrop_path, "original");
  const type = item.media_type === "tv" || item.first_air_date ? "Series" : "Film";
  return (
    <div className="hero">
      {backdrop && <img src={backdrop} alt="" className={`hero__bg ${loaded ? "hero__bg--loaded" : ""}`} onLoad={() => setLoaded(true)} />}
      <div className="hero__scrim" />
      <div className="hero__content">
        <span className="hero__badge">{type} · {year}</span>
        <h1 className="hero__title">{title}</h1>
        <p className="hero__overview">{(item.overview || "").slice(0, 220)}{item.overview?.length > 220 ? "…" : ""}</p>
        <div className="hero__rating"><Icon.Star /><Icon.Star /><Icon.Star /><Icon.Star /><Icon.Star /><span>{item.vote_average?.toFixed(1)} / 10</span></div>
        <div className="hero__btns">
          <button className="btn-hero-play" onClick={() => onPlay({ detailPath: title, subjectId: item.id, title, _fromTMDB: true })}><Icon.Play /> Play Now</button>
          <button className="btn-hero-info" onClick={() => onSelect({ detailPath: title, subjectId: item.id, title, cover: IMG(item.poster_path), backdrop: IMG(item.backdrop_path, "w1280"), overview: item.overview, year, mediaType: item.media_type || (item.first_air_date ? "tv" : "movie"), _fromTMDB: true })}><Icon.Info /> More Info</button>
        </div>
      </div>
    </div>
  );
}

function SearchResults({ results, query, onPlay, onSelect, downloading }) {
  if (!results.length) return (
    <div className="empty-state"><div className="empty-state__icon">🔍</div><p>Searching for <strong>"{query}"</strong>…</p></div>
  );
  return (
    <div className="search-results">
      <h2 className="search-results__heading">Results for <span>"{query}"</span></h2>
      <div className="search-grid">
        {results.map((item, i) => {
          const key = `${item.detailPath}-s1e1`;
          const status = downloading[key];
          return (
            <div key={i} className="search-card" onClick={() => onSelect(item)}>
              {item.cover ? <img src={item.cover} alt={item.title} className="search-card__img" loading="lazy" /> : <div className="search-card__img search-card__img--placeholder">🎬</div>}
              <div className="search-card__body">
                <h3 className="search-card__title">{item.title}</h3>
                <div className="search-card__meta">
                  {item.year && <span className="badge">{item.year}</span>}
                  {item.genre && <span className="badge badge--genre">{item.genre}</span>}
                  {item.hasResource && <span className="badge badge--avail">Available</span>}
                </div>
                <div className="search-card__actions">
                  <button className="btn-play-sm" onClick={(e) => { e.stopPropagation(); onPlay(item); }}><Icon.Play /> Watch</button>
                  <button className="btn-dl-sm btn-dl-sm--labeled" onClick={(e) => { e.stopPropagation(); onSelect(item); }}>
                    {status?.status === "done" ? "✓ Done" : status?.status === "starting" ? "…" : <><Icon.Download /> Save</>}
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Downloads({ files, onPlay }) {
  return (
    <div className="downloads">
      <h2 className="section-heading">My Downloads</h2>
      {!files.length ? (
        <div className="empty-state"><div className="empty-state__icon">📂</div><p>No downloads yet. Search for something to get started.</p></div>
      ) : (
        <div className="downloads-grid">
          {files.map((f, i) => (
            <div key={i} className="dl-card">
              <div className="dl-card__icon">🎬</div>
              <div className="dl-card__info">
                <span className="dl-card__name">{f.name}</span>
                <span className="dl-card__size">{f.size_mb} MB</span>
                {f.progress !== undefined && f.progress < 100 && (
                  <div className="dl-card__progress-bar"><div className="dl-card__progress-fill" style={{ width: `${f.progress}%` }} /></div>
                )}
              </div>
              <button className="btn-play-sm" onClick={() => onPlay({ stream_url: `/api/files/${f.name}`, title: f.name })}><Icon.Play /></button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DetailModal({ item, onClose, onPlay, onDownload }) {
  const [season, setSeason] = useState(1);
  const [episode, setEpisode] = useState(1);
  const isTV = item.mediaType === "tv";
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="detail-modal" onClick={(e) => e.stopPropagation()}>
        {item.backdrop && <div className="detail-modal__backdrop"><img src={item.backdrop} alt="" /><div className="detail-modal__backdrop-scrim" /></div>}
        <button className="detail-modal__close" onClick={onClose}><Icon.Close /></button>
        <div className="detail-modal__body">
          <div className="detail-modal__left">{item.cover && <img src={item.cover} alt={item.title} className="detail-modal__poster" />}</div>
          <div className="detail-modal__right">
            <h2 className="detail-modal__title">{item.title}</h2>
            {item.year && <span className="badge" style={{ marginBottom: 12, display: "inline-block" }}>{item.year}</span>}
            {item.rating && <div className="detail-modal__rating"><Icon.Star /> {item.rating} / 10</div>}
            {item.overview && <p className="detail-modal__overview">{item.overview}</p>}
            {isTV && (
              <div className="detail-modal__episode-row">
                <div className="detail-modal__field"><label>Season</label><input type="number" min={1} value={season} onFocus={() => setSeason("")} onChange={(e) => setSeason(parseInt(e.target.value) || 1)} /></div>
                <div className="detail-modal__field"><label>Episode</label><input type="number" min={1} value={episode} onFocus={() => setEpisode("")} onChange={(e) => setEpisode(parseInt(e.target.value) || 1)} /></div>
              </div>
            )}
            <div className="detail-modal__actions">
              <button className="btn-hero-play" onClick={() => { onPlay(item, season, episode); onClose(); }}><Icon.Play /> Watch Now</button>
              <button className="btn-hero-info" onClick={() => { onDownload(item, season, episode); onClose(); }}><Icon.Download /> Download</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function VideoPlayer({ player, onClose }) {
  const videoRef = useRef(null);

  useEffect(() => {
    if (!player?.stream_url || !videoRef.current) return;
    const video = videoRef.current;
    let hls;

    const Hls = window.Hls;
    if (!player.stream_url.endsWith('.mp4') && Hls && Hls.isSupported()) {
      hls = new Hls({
        enableWorker:     true,
        lowLatencyMode:   true,
        maxBufferLength:  10,
        maxMaxBufferLength: 30,
        fragLoadingTimeOut: 20000,
      });
      hls.loadSource(player.stream_url);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => video.play().catch(() => {}));
      hls.on(Hls.Events.ERROR, (_, data) => {
        if (data.fatal) {
          console.error("[hls] fatal error", data);
          hls.destroy();
        }
      });
    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
      // Safari native HLS
      video.src = player.stream_url;
      video.play().catch(() => {});
    } else {
      // Direct MP4
      video.src = player.stream_url;
      video.play().catch(() => {});
    }

    return () => { hls?.destroy(); };
  }, [player?.stream_url]);

  if (!player) return null;

  const spinnerStyle = {
    width: 52, height: 52,
    border: "4px solid rgba(255,255,255,0.15)",
    borderTop: "4px solid #fff",
    borderRadius: "50%",
    animation: "spin 0.75s linear infinite",
    marginBottom: 16,
  };

  const overlayStyle = {
    position: "fixed", inset: 0, zIndex: 9999,
    background: "#000",
    display: "flex", alignItems: "center", justifyContent: "center",
  };

  const closeBtnStyle = {
    position: "absolute", top: 16, right: 16,
    background: "rgba(255,255,255,0.12)",
    border: "none", color: "#fff",
    width: 40, height: 40, borderRadius: "50%",
    cursor: "pointer", fontSize: 20, zIndex: 10,
    display: "flex", alignItems: "center", justifyContent: "center",
  };

  const jobStatus = useJobPoller(
    player?.loading ? player?.jobKey : null,
    null,
    null
  );

  const statusLabel = () => {
    if (!jobStatus) return "Preparing stream…";
    switch (jobStatus.status) {
      case "queued":   return `Queue position ${jobStatus.queue_position ?? "…"}`;
      case "starting": return "Starting encoder…";
      case "running":  return "Encoding stream…";
      case "error":    return `Error: ${jobStatus.error || "unknown"}`;
      default:         return "Preparing stream…";
    }
  };

  if (player.loading) return (
    <div style={overlayStyle}>
      <button style={closeBtnStyle} onClick={onClose}><Icon.Close /></button>
      <div style={{ textAlign: "center", color: "#fff", fontFamily: "sans-serif" }}>
        <div style={spinnerStyle} />
        <p style={{ fontSize: 15, opacity: 0.85 }}>{statusLabel()}</p>
        <p style={{ fontSize: 12, opacity: 0.4, marginTop: 6 }}>{player.title}</p>
      </div>
    </div>
  );

  return (
    <div style={overlayStyle}>
      <button style={closeBtnStyle} onClick={onClose}><Icon.Close /></button>
      {player.needs_rotate && (
        <div style={{
          position: "absolute", bottom: 28, left: "50%", transform: "translateX(-50%)",
          background: "rgba(255,255,255,0.12)", color: "#fff",
          padding: "8px 20px", borderRadius: 20, fontSize: 13,
          fontFamily: "sans-serif", backdropFilter: "blur(8px)",
          pointerEvents: "none", zIndex: 11,
        }}>↺ Rotate for fullscreen</div>
      )}
      <video
        ref={videoRef}
        controls
        autoPlay
        playsInline
        style={{ width: "100vw", height: "100vh", objectFit: "cover" }}
      />
    </div>
  );
}

function Toast({ toast }) {
  if (!toast) return null;
  const colors = { error: "#e50914", success: "#46d369", info: "#1a1a2e" };
  return <div className="toast" style={{ background: colors[toast.type] || colors.info }}>{toast.msg}</div>;
}

function BottomNav({ active, onChange }) {
  const tabs = [
    { id: "home", label: "Home", I: Icon.Home },
    { id: "search", label: "Search", I: Icon.Search },
    { id: "downloads", label: "Downloads", I: Icon.Download },
    { id: "mylist", label: "My List", I: Icon.List },
  ];
  return (
    <nav className="bottom-nav">
      {tabs.map(({ id, label, I }) => (
        <button key={id} className={`bottom-nav__item ${active === id ? "bottom-nav__item--active" : ""}`} onClick={() => onChange(id)}>
          <I /><span>{label}</span>
        </button>
      ))}
    </nav>
  );
}

function TopNav({ activeTab, onTabChange, query, onQuery, history, onHistoryPick, onHistoryRemove }) {
  return (
    <nav className="top-nav">
      <div className="top-nav__logo"><span className="top-nav__logo-icon">🐦</span>MAGPIE</div>
      <div className="top-nav__tabs">
        {["Home", ...CATEGORIES, "Downloads"].map((t) => (
          <button key={t} className={`top-nav__tab ${activeTab === t ? "top-nav__tab--active" : ""}`} onClick={() => onTabChange(t)}>{t}</button>
        ))}
      </div>
      <div className="top-nav__search" style={{ position: "relative" }}>
        <Icon.Search />
        <input value={query} onChange={(e) => onQuery(e.target.value)} placeholder="Search titles…" className="top-nav__search-input" />
        {query && <button className="top-nav__search-clear" onClick={() => onQuery("")}><Icon.Close /></button>}
        {!query && history?.length > 0 && (
          <div className="search-history">
            {history.map((h, i) => (
              <div key={i} className="search-history__item">
                <span onClick={() => onHistoryPick(h)}>{h}</span>
                <button onClick={() => onHistoryRemove(h)}>×</button>
              </div>
            ))}
          </div>
        )}
      </div>
    </nav>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState("Home");
  const [mobileTab, setMobileTab] = useState("home");
  const [categories, setCategories] = useState({});
  const [hero, setHero] = useState(null);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [selected, setSelected] = useState(null);
  const [player, setPlayer] = useState(null);
  const [downloads, setDownloads] = useState([]);
  const [downloading, setDownloading] = useState({});
  const [myList, setMyList] = useState(() => { try { return JSON.parse(localStorage.getItem("magpie_mylist") || "[]"); } catch { return []; } });
  const [searchHistory, setSearchHistory] = useState(() => { try { return JSON.parse(localStorage.getItem("magpie_history") || "[]"); } catch { return []; } });

  const addToHistory = (q) => {
    if (!q.trim()) return;
    setSearchHistory(prev => {
      const filtered = prev.filter(h => h.toLowerCase() !== q.toLowerCase());
      const next = [q, ...filtered].slice(0, 10);
      localStorage.setItem("magpie_history", JSON.stringify(next));
      return next;
    });
  };

  const removeFromHistory = (q) => {
    setSearchHistory(prev => {
      const next = prev.filter(h => h !== q);
      localStorage.setItem("magpie_history", JSON.stringify(next));
      return next;
    });
  };
  const { toast, showToast } = useToast();
  const debouncedQuery = useDebounce(query, 450);
  const pollRef = useRef(null);

  const isSearching = debouncedQuery.trim().length > 0 || (query.trim().length > 0 && mobileTab === "search");
  const showDownloads = activeTab === "Downloads" || mobileTab === "downloads";
  const showMyList = mobileTab === "mylist";

  useEffect(() => {
    const load = async () => {
      const cats = {};
      await Promise.all(Object.entries(TMDB_ENDPOINTS).map(async ([key, endpoint]) => {
        try { const r = await TMDB.get(endpoint); cats[key] = r.data.results || []; } catch {}
      }));
      setCategories(cats);
      const trending = cats["Trending"] || [];
      if (trending.length) setHero(trending[Math.floor(Math.random() * Math.min(5, trending.length))]);
    };
    load();
    fetchFiles().then(setDownloads).catch(() => {});
  }, []);

  useEffect(() => {
    if (!debouncedQuery.trim()) { setSearchResults([]); return; }
    addToHistory(debouncedQuery);
    searchTMDB(debouncedQuery)
      .then((items) => setSearchResults(
        items
          .filter((item) => item.media_type === "movie" || item.media_type === "tv")
          .map((item) => {
            const title = item.title || item.name;
            const year = (item.release_date || item.first_air_date || "").slice(0, 4);
            return {
              detailPath: title,
              subjectId: item.id,
              title,
              cover: IMG(item.poster_path),
              backdrop: IMG(item.backdrop_path, "w1280"),
              overview: item.overview,
              year,
              rating: item.vote_average?.toFixed(1),
              mediaType: item.media_type,
              _fromTMDB: true,
            };
          })
      ))
      .catch(() => setSearchResults([]));
  }, [debouncedQuery]);

  const pollDownloads = () => {
    clearInterval(pollRef.current);
    pollRef.current = setInterval(() => fetchFiles().then(setDownloads), 3000);
    setTimeout(() => clearInterval(pollRef.current), 90000);
  };

  const resolveItem = async (item) => {
    if (item.detailPath && item.subjectId && !item._fromTMDB) return item;
    showToast(`Finding "${item.title}" on magpie…`, "info");
    const results = await searchMagpie(item.title);
    if (!results?.length) { showToast("Not found on magpie", "error"); return null; }
    return results[0];
  };

  const playStream = async (item, season = 1, episode = 1) => {
    const title = item.title || item.name;
    const safe = title.replace(/[^\w-]/g, '').replace(/ /g, '-');
    const jobKey = `${safe}-s${String(season).padStart(2,'0')}e${String(episode).padStart(2,'0')}_`;
    setPlayer({ loading: true, title, season, episode, jobKey });
    try {
      const resolved = await resolveItem(item);
      if (!resolved) { setPlayer(null); return; }

      const dpr = window.devicePixelRatio || 1;
      const orientation = screen.orientation?.type ||
        (screen.width > screen.height ? "landscape-primary" : "portrait-primary");

      const res = await axios.post("/api/play", {
        detailPath:   resolved.detailPath,
        subjectId:    resolved.subjectId,
        title:        resolved.title || title,
        season,
        episode,
        screen_width:  Math.round(screen.width  * dpr),
        screen_height: Math.round(screen.height * dpr),
        orientation,
      });

      if (res.data?.stream_url) {
        setPlayer({
          stream_url:  res.data.stream_url,
          title:       resolved.title || title,
          season,
          episode,
          needs_rotate: res.data.needs_rotate,
          loading:     false,
        });
      } else {
        setPlayer(null);
        showToast("Could not prepare stream", "error");
      }
    } catch (err) {
      setPlayer(null);
      showToast("Stream error: " + (err?.response?.data?.error || err.message || "Unknown"), "error");
    }
  };

  const startDownload = async (item, season = 1, episode = 1) => {
    const resolved = await resolveItem(item);
    if (!resolved) return;
    const key = `${resolved.detailPath}-s${season}e${episode}`;
    setDownloading((d) => ({ ...d, [key]: { progress: 0, status: "starting" } }));
    try {
      await startDownloadApi({ detailPath: resolved.detailPath, subjectId: resolved.subjectId, title: resolved.title, season, episode });
      setDownloading((d) => ({ ...d, [key]: { status: "done" } }));
      showToast(`Download started: ${resolved.title}`, "success");
      pollDownloads();
    } catch {
      setDownloading((d) => ({ ...d, [key]: { status: "error" } }));
      showToast("Download failed", "error");
    }
  };

  const handleMobileTab = (id) => {
    setMobileTab(id);
    if (id === "home") { setActiveTab("Home"); setQuery(""); }
    if (id === "search") setActiveTab("Home");
    if (id === "downloads") setActiveTab("Downloads");
  };

  const renderContent = () => {
    if (isSearching) return <SearchResults results={searchResults} query={debouncedQuery || query} onPlay={playStream} onSelect={setSelected} downloading={downloading} />;
    if (showMyList) return (
      <div className="downloads">
        <h2 className="section-heading">My List</h2>
        {!myList.length
          ? <div className="empty-state"><div className="empty-state__icon">📋</div><p>Nothing saved yet.</p></div>
          : <div className="search-grid">{myList.map((item, i) => <div key={i} className="search-card" onClick={() => setSelected(item)}>{item.cover && <img src={item.cover} alt={item.title} className="search-card__img" />}<div className="search-card__body"><h3 className="search-card__title">{item.title}</h3><div className="search-card__actions"><button className="btn-play-sm" onClick={(e) => { e.stopPropagation(); playStream(item); }}><Icon.Play /> Watch</button></div></div></div>)}</div>
        }
      </div>
    );
    if (showDownloads) return <Downloads files={downloads} onPlay={setPlayer} />;
    const catOrder = activeTab === "Home" ? CATEGORIES : [activeTab];
    return (
      <>
        {activeTab === "Home" && <Hero item={hero} onPlay={playStream} onSelect={setSelected} />}
        <div className="carousels">
          {catOrder.map((cat) => categories[cat]?.length ? <Carousel key={cat} title={cat} items={categories[cat]} onSelect={setSelected} onPlay={playStream} /> : null)}
        </div>
      </>
    );
  };

  return (
    <div className="app">
      <TopNav activeTab={activeTab} onTabChange={(t) => { setActiveTab(t); setQuery(""); setMobileTab("home"); }} query={query} onQuery={setQuery} history={searchHistory} onHistoryPick={(h) => setQuery(h)} onHistoryRemove={removeFromHistory} />
      <main className="main-content">{renderContent()}</main>
      <BottomNav active={mobileTab} onChange={handleMobileTab} />
      {selected && <DetailModal item={selected} onClose={() => setSelected(null)} onPlay={playStream} onDownload={startDownload} />}
      {player && <VideoPlayer player={player} onClose={() => setPlayer(null)} />}
      <Toast toast={toast} />
    </div>
  );
}
