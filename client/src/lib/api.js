import axios from "axios";

export const TMDB_TOKEN =
  "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJhNWU0MGMwODlmOTA0NDU3MWRjZDVjOThiMjBiZmFlMSIsIm5iZiI6MTc3ODcwOTk4Mi40ODcsInN1YiI6IjZhMDRmNWRlNTc0OWJmZmZlMTZmY2FkNCIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.lN33o5iU2l0cBkF7MOfpDPd0XO6QgDxhYT8dtF8H39A";

export const TMDB = axios.create({
  baseURL: "https://api.themoviedb.org/3",
  headers: { Authorization: `Bearer ${TMDB_TOKEN}` },
});

export const IMG = (path, size = "w500") =>
  path ? `https://image.tmdb.org/t/p/${size}${path}` : null;

export const TMDB_ENDPOINTS = {
  Trending: "/trending/all/week",
  Movies: "/movie/popular",
  "TV Shows": "/tv/popular",
  Crime: "/discover/movie?with_genres=80&sort_by=popularity.desc",
  Drama: "/discover/movie?with_genres=18&sort_by=popularity.desc",
  Thriller: "/discover/movie?with_genres=53&sort_by=popularity.desc",
};

export async function searchMagpie(q) {
  const res = await axios.get(`/api/search?q=${encodeURIComponent(q)}`);
  return res.data.filter(f => !f.name.endsWith(".aria2"));
}

export async function searchTMDB(query) {
  const res = await TMDB.get("/search/multi", { params: { query, include_adult: false } });
  return res.data.results || [];
}

export async function fetchFiles() {
  const res = await axios.get("/api/files");
  return res.data.filter(f => !f.name.endsWith(".aria2"));
}

export async function startDownloadApi(payload) {
  const res = await axios.post("/api/download", payload);
  return res.data.filter(f => !f.name.endsWith(".aria2"));
}

export async function fetchStreams(detailPath, subjectId, season, episode) {
  const res = await axios.get(
    `/api/streams?detailPath=${detailPath}&subjectId=${subjectId}&season=${season}&episode=${episode}`
  );
  return res.data.filter(f => !f.name.endsWith(".aria2"));
}

export async function playStreamApi(payload) {
  const res = await axios.post("/api/play", payload, { timeout: 60000 });
  return res.data.filter(f => !f.name.endsWith(".aria2"));
}
