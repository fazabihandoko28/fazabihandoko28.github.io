(() => {
  // Preserve the last known-good dashboard extension exactly as it existed
  // before PMR80 UI wiring, then layer PMR80 on top. This avoids changing the
  // existing News Catalyst, radar-detail, S/R overlay, and IHSG behavior.
  const LEGACY_SRC = "https://cdn.jsdelivr.net/gh/fazabihandoko28/fazabihandoko28.github.io@af72386aaa966b827f85876263a69e7240e5e7f3/docs/dashboard/swing/news-catalyst.js";
  const PMR80_SRC = "/dashboard/swing/pmr80-radar.js?v=20261012-1";

  function loadScript(src,id){
    if(document.getElementById(id)) return;
    const s=document.createElement("script");
    s.id=id;
    s.src=src;
    s.defer=true;
    document.head.appendChild(s);
  }

  loadScript(LEGACY_SRC,"hanz-legacy-news-catalyst");
  loadScript(PMR80_SRC,"hanz-pmr80-radar-live");
})();