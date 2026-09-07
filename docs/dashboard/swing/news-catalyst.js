(() => {
  const STYLE_ID = "hanz-news-catalyst-style";
  const ROOT_ID = "hanzNewsCatalyst";

  function esc(v){
    return String(v ?? "")
      .replaceAll("&","&amp;")
      .replaceAll("<","&lt;")
      .replaceAll(">","&gt;")
      .replaceAll('"',"&quot;");
  }

  function addStyles(){
    if(document.getElementById(STYLE_ID)) return;
    const style=document.createElement("style");
    style.id=STYLE_ID;
    style.textContent=`
      .news-catalyst-wrap{margin-top:12px}
      .news-catalyst-head{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;margin-bottom:10px}
      .news-catalyst-head h2{margin:0;font-size:17px}
      .news-catalyst-head p{margin:3px 0 0;color:var(--muted);font-size:10px}
      .news-catalyst-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
      .news-catalyst-card{border:1px solid var(--line);background:#0a1423;border-radius:18px;padding:14px}
      .news-catalyst-top{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}
      .news-catalyst-scope{font-size:16px;font-weight:950}
      .news-catalyst-badge{font-size:8px;font-weight:950;padding:5px 8px;border-radius:999px}
      .news-catalyst-badge.positive{color:var(--green);background:rgba(40,224,162,.09)}
      .news-catalyst-badge.negative{color:var(--red);background:rgba(255,101,114,.10)}
      .news-catalyst-headline{margin-top:10px;font-size:11px;font-weight:850;line-height:1.5}
      .news-catalyst-meta{margin-top:8px;color:var(--muted);font-size:8px;line-height:1.5}
      .news-catalyst-note{margin-top:8px;color:#aeb9c9;font-size:8px;line-height:1.5}
      .news-catalyst-link{display:inline-flex;margin-top:10px;text-decoration:none;border:1px solid var(--line);border-radius:9px;padding:7px 9px;color:#dce5f0;font-size:8px;font-weight:800}
      .news-catalyst-empty{padding:16px;border:1px dashed var(--line);border-radius:14px;color:var(--muted);font-size:9px}
      @media(max-width:700px){.news-catalyst-grid{grid-template-columns:1fr}}
    `;
    document.head.appendChild(style);
  }

  function ensureRoot(){
    let root=document.getElementById(ROOT_ID);
    if(root) return root;
    const overview=document.getElementById("overview");
    if(!overview) return null;
    const section=document.createElement("section");
    section.id=ROOT_ID;
    section.className="news-catalyst-wrap";
    section.innerHTML=`
      <div class="news-catalyst-head">
        <div>
          <h2>News Catalyst</h2>
          <p>Only high-confidence news likely to explain selected-stock or IHSG moves. Hidden when causal evidence is weak.</p>
        </div>
        <small class="foreign-flow-meta" id="hanzNewsCatalystUpdated">—</small>
      </div>
      <div id="hanzNewsCatalystGrid" class="news-catalyst-grid"></div>`;
    overview.appendChild(section);
    return section;
  }

  function fmtTime(v){
    if(!v) return "—";
    const d=new Date(v);
    if(Number.isNaN(d.getTime())) return "—";
    return new Intl.DateTimeFormat("en-GB",{day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit"}).format(d);
  }

  function render(payload){
    const grid=document.getElementById("hanzNewsCatalystGrid");
    const updated=document.getElementById("hanzNewsCatalystUpdated");
    if(!grid) return;
    const rows=Array.isArray(payload?.catalysts)?payload.catalysts:[];
    updated.textContent=payload?.generated_at?`Updated ${fmtTime(payload.generated_at)}`:"—";

    if(!rows.length){
      grid.innerHTML='<div class="news-catalyst-empty">No high-confidence news catalyst detected. HANZ will not force a headline.</div>';
      return;
    }

    grid.innerHTML=rows.map(row=>{
      const dir=String(row.direction||"NEUTRAL").toUpperCase();
      const cls=dir==="POSITIVE"?"positive":"negative";
      const label=row.scope==="IHSG"?"IHSG":(row.ticker||"STOCK");
      return `<article class="news-catalyst-card">
        <div class="news-catalyst-top">
          <div class="news-catalyst-scope">${esc(label)} · NEWS CATALYST</div>
          <span class="news-catalyst-badge ${cls}">${esc(row.confidence||"HIGH")} · ${esc(dir)}</span>
        </div>
        <div class="news-catalyst-headline">${esc(row.headline||"")}</div>
        <div class="news-catalyst-meta">${esc(row.source||"Source")} · ${esc(fmtTime(row.published_at))}</div>
        <div class="news-catalyst-note">${esc(row.note||"")}</div>
        ${row.url?`<a class="news-catalyst-link" href="${esc(row.url)}" target="_blank" rel="noopener noreferrer">Read source ↗</a>`:""}
      </article>`;
    }).join("");
  }

  async function load(){
    addStyles();
    if(!ensureRoot()) return;
    try{
      const response=await fetch(`./news-catalyst.json?ts=${Date.now()}`,{cache:"no-store"});
      if(!response.ok) throw new Error(`HTTP ${response.status}`);
      render(await response.json());
    }catch(error){
      const grid=document.getElementById("hanzNewsCatalystGrid");
      if(grid) grid.innerHTML='<div class="news-catalyst-empty">News catalyst layer is temporarily unavailable.</div>';
      console.warn("HANZ News Catalyst load failed",error);
    }
  }

  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",load);
  else load();
  setInterval(load,120000);
})();
