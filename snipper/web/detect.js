(function () {
  let currentJobKey = null;

  function getVideoName() {
    const params = new URLSearchParams(window.location.search);
    return params.get("video") || "ozark-s03e01";
  }

  function getDeviceInfo() {
    const dpr = window.devicePixelRatio || 1;
    return {
      video: getVideoName(),
      screen_width: Math.round(screen.width * dpr),
      screen_height: Math.round(screen.height * dpr),
      dpr: dpr,
      orientation: screen.orientation?.type || (screen.width > screen.height ? "landscape-primary" : "portrait-primary"),
      refresh_rate: null,
    };
  }

  function measureRefreshThenSend(info) {
    let last = null;
    let samples = [];

    function measure(timestamp) {
      if (last !== null) samples.push(1000 / (timestamp - last));
      last = timestamp;
      if (samples.length < 10) {
        requestAnimationFrame(measure);
      } else {
        info.refresh_rate = Math.round(samples.reduce((a, b) => a + b, 0) / samples.length);
        sendToServer(info);
      }
    }
    requestAnimationFrame(measure);
  }

  function sendToServer(data) {
    console.log("[snipper] Sending device info:", data);
    fetch("/device", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    })
      .then((res) => res.json())
      .then((res) => {
        console.log("[snipper] Server response:", res);
        if (res.stream_url) {
          const jobKey = res.stream_url;
          if (jobKey !== currentJobKey) {
            currentJobKey = jobKey;
            window.__snipperLoadStream(res.stream_url, res.needs_rotate);
          } else {
            console.log("[snipper] Same stream — no switch needed");
          }
        }
      })
      .catch((err) => console.error("[snipper] Error:", err));
  }

  function init() {
    const info = getDeviceInfo();
    measureRefreshThenSend(info);
  }

  // Orientation change
  if (screen.orientation) {
    screen.orientation.addEventListener("change", () => {
      console.log("[snipper] Orientation changed → re-detecting");
      const info = getDeviceInfo();
      measureRefreshThenSend(info);
    });
  } else {
    window.addEventListener("orientationchange", () => {
      console.log("[snipper] Orientation changed (fallback) → re-detecting");
      setTimeout(() => {
        const info = getDeviceInfo();
        measureRefreshThenSend(info);
      }, 300);
    });
  }

  init();
})();
