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
      /* Compact main page: Selected HANZ Candidates stays as hidden data source only. */
      .candidate-section{display:none!important}
      .rank{cursor:pointer;transition:.16s ease;border:1px solid transparent}
      .rank:hover,.rank:focus{border-color:rgba(40,224,162,.38);background:rgba(40,224,162,.055);outline:none;transform:translateY(-1px)}
      .rank:after{content:"›";color:var(--green);font-size:15px;font-weight:900;margin-left:2px}
      .radar-detail-hint{margin-top:10px;color:var(--muted);font-size:8px;line-height:1.5}
      .radar-chart-wrap{margin-top:14px}
      .radar-chart-title{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:8px}
      .radar-chart-title strong{font-size:11px}.radar-chart-title span{color:var(--muted);font-size:8px}

      .news-catalyst-wrap{margin:0 0 12px}
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
    const ihsg=document.getElementById("hanzIhsgStrip");
    if(ihsg && ihsg.nextSibling) overview.insertBefore(section,ihsg.nextSibling);
    else if(ihsg) overview.appendChild(section);
    else overview.insertBefore(section,overview.firstElementChild);
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

  function copyChartIntoDetail(index){
    const chartButton=document.querySelector(`[data-candidate-chart="${index}"]`);
    const chartModal=document.getElementById("candidateChartModal");
    const chartBody=document.getElementById("candidateChartBody");
    const detailBody=document.getElementById("candidateDetailIndicators");
    if(!chartButton || !chartModal || !chartBody || !detailBody) return;

    let integrated=document.getElementById("radarIntegratedChart");
    if(integrated) integrated.remove();

    integrated=document.createElement("div");
    integrated.id="radarIntegratedChart";
    integrated.className="radar-chart-wrap";
    integrated.innerHTML='<div class="radar-chart-title"><strong>PRICE + TECHNICAL CHART</strong><span>60 completed daily bars</span></div><div class="mover-empty">Loading chart…</div>';
    detailBody.appendChild(integrated);

    chartModal.style.visibility="hidden";
    chartButton.click();

    let tries=0;
    const timer=setInterval(()=>{
      tries+=1;
      const loading=chartBody.textContent.trim().toLowerCase().startsWith("loading chart");
      if(!loading || tries>=40){
        clearInterval(timer);
        const target=document.getElementById("radarIntegratedChart");
        if(target){
          target.innerHTML=`<div class="radar-chart-title"><strong>PRICE + TECHNICAL CHART</strong><span>60 completed daily bars</span></div>${chartBody.innerHTML}`;
        }
        chartModal.classList.remove("show");
        chartModal.style.visibility="";
      }
    },150);
  }

  function openRadarDetail(index){
    const detailButton=document.querySelector(`[data-candidate-detail="${index}"]`);
    if(!detailButton) return;
    detailButton.click();
    const detailBody=document.getElementById("candidateDetailIndicators");
    if(detailBody && !detailBody.querySelector(".radar-detail-hint")){
      const hint=document.createElement("div");
      hint.className="radar-detail-hint";
      hint.textContent="Opened directly from HANZ Opportunity Radar · indicators and chart are detail-only so the main page stays compact.";
      detailBody.appendChild(hint);
    }
    copyChartIntoDetail(index);
  }

  function bindRadarRows(){
    const rows=[...document.querySelectorAll("#ranking .rank")];
    rows.forEach((row,index)=>{
      if(row.dataset.compactRadarBound==="1") return;
      row.dataset.compactRadarBound="1";
      row.setAttribute("role","button");
      row.setAttribute("tabindex","0");
      row.setAttribute("aria-label",`Open HANZ candidate detail ${index+1}`);
      row.addEventListener("click",()=>openRadarDetail(index));
      row.addEventListener("keydown",event=>{
        if(event.key==="Enter" || event.key===" "){
          event.preventDefault();
          openRadarDetail(index);
        }
      });
    });
  }

  function loadIhsgDisplay(){
    if(document.querySelector('script[data-hanz-ihsg="1"]')) return;
    const script=document.createElement("script");
    script.src=`./ihsg-display.js?v=1`;
    script.defer=true;
    script.dataset.hanzIhsg="1";
    document.head.appendChild(script);
  }

  async function load(){
    addStyles();
    if(!ensureRoot()) return;
    bindRadarRows();
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

  function start(){
    loadIhsgDisplay();
    load();
    setInterval(bindRadarRows,1000);
    setInterval(load,120000);
  }

  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",start);
  else start();
})();
