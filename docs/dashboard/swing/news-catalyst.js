(() => {
  const STYLE_ID = "hanz-news-catalyst-style";
  const ROOT_ID = "hanzNewsCatalyst";
  const SUPABASE_URL = "https://fgyfszkadstmdzqvwppt.supabase.co";
  const SUPABASE_KEY = "sb_publishable_rBY4VJwPS1T5tm0zPw4tbg_BhApWtfM";

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
      .candidate-section{display:none!important}
      .rank{cursor:pointer;transition:.16s ease;border:1px solid transparent}
      .rank:hover,.rank:focus{border-color:rgba(40,224,162,.38);background:rgba(40,224,162,.055);outline:none;transform:translateY(-1px)}
      .rank:after{content:"›";color:var(--green);font-size:15px;font-weight:900;margin-left:2px}
      .radar-detail-hint{margin-top:10px;color:var(--muted);font-size:8px;line-height:1.5}
      .radar-chart-wrap{margin-top:14px}
      .radar-chart-title{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:8px}
      .radar-chart-title strong{font-size:11px}.radar-chart-title span{color:var(--muted);font-size:8px}
      .sr-legend{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 2px}
      .sr-chip{padding:5px 8px;border-radius:999px;font-size:8px;font-weight:900;border:1px solid rgba(255,255,255,.12);background:rgba(7,14,27,.72)}
      .sr-support{color:#66e3a4}.sr-resistance{color:#ff9c70}.sr-trigger{color:#48d7ff}

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

  function pivotLevels(candles){
    const rows=(Array.isArray(candles)?candles:[]).map(c=>({
      high:Number(c.high), low:Number(c.low), close:Number(c.close), volume:Number(c.volume)
    })).filter(c=>Number.isFinite(c.close)&&Number.isFinite(c.high)&&Number.isFinite(c.low));
    if(rows.length<12) return null;
    const data=rows.slice(-60);
    const latest=data.at(-1).close;
    const lows=[], highs=[];
    for(let i=2;i<data.length-2;i++){
      const d=data[i];
      if(d.low<=data[i-1].low && d.low<=data[i-2].low && d.low<=data[i+1].low && d.low<=data[i+2].low) lows.push(d.low);
      if(d.high>=data[i-1].high && d.high>=data[i-2].high && d.high>=data[i+1].high && d.high>=data[i+2].high) highs.push(d.high);
    }
    const uniq=(arr,tol=.012)=>{
      const out=[];
      arr.sort((a,b)=>a-b).forEach(v=>{
        if(!out.some(x=>Math.abs(v/x-1)<=tol)) out.push(v);
      });
      return out;
    };
    const us=uniq(lows), ur=uniq(highs);
    const supports=us.filter(v=>v<latest).sort((a,b)=>b-a);
    const resistances=ur.filter(v=>v>latest).sort((a,b)=>a-b);
    const recent=data.slice(-6,-1);
    const trigger=recent.length?Math.max(...recent.map(d=>d.high)):null;
    return {
      s1:supports[0]??null,s2:supports[1]??null,
      r1:resistances[0]??null,r2:resistances[1]??null,
      trigger:Number.isFinite(trigger)?trigger:null,
      latest,
      data
    };
  }

  function chartScale(data){
    const close=data.map(d=>d.close);
    const sma=(vals,p)=>vals.map((_,i)=>i<p-1?null:vals.slice(i-p+1,i+1).reduce((a,b)=>a+b,0)/p);
    const sd=(vals,p)=>vals.map((_,i)=>{
      if(i<p-1) return null;
      const s=vals.slice(i-p+1,i+1),m=s.reduce((a,b)=>a+b,0)/p;
      return Math.sqrt(s.reduce((a,b)=>a+(b-m)*(b-m),0)/p);
    });
    const ma20=sma(close,20),ma50=sma(close,50),sd20=sd(close,20);
    const up=ma20.map((m,i)=>m===null||sd20[i]===null?null:m+2*sd20[i]);
    const lo=ma20.map((m,i)=>m===null||sd20[i]===null?null:m-2*sd20[i]);
    const all=[...close,...ma20.filter(Number.isFinite),...ma50.filter(Number.isFinite),...up.filter(Number.isFinite),...lo.filter(Number.isFinite)];
    return {min:Math.min(...all),max:Math.max(...all)};
  }

  async function fetchChartCandles(ticker){
    const url=`${SUPABASE_URL}/rest/v1/hanz_swing_chart_data?ticker=eq.${encodeURIComponent(ticker)}&select=candles&limit=1`;
    const r=await fetch(url,{headers:{apikey:SUPABASE_KEY,Authorization:`Bearer ${SUPABASE_KEY}`},cache:"no-store"});
    if(!r.ok) throw new Error(`chart level HTTP ${r.status}`);
    const rows=await r.json();
    return rows?.[0]?.candles||[];
  }

  function addSupportResistanceOverlay(container,levels){
    if(!container || !levels) return;
    const svg=container.querySelector(".tech-panel .tech-svg");
    if(!svg || svg.dataset.srOverlay==="1") return;
    svg.dataset.srOverlay="1";
    const W=900,H=330,padY=18;
    const scale=chartScale(levels.data);
    const y=v=>H-padY-((v-scale.min)/((scale.max-scale.min)||1))*(H-padY*2);
    const NS="http://www.w3.org/2000/svg";
    const specs=[
      ["S1",levels.s1,"#66e3a4","5 4"],
      ["S2",levels.s2,"#3fbf86","3 5"],
      ["BUY TRIGGER",levels.trigger,"#48d7ff","8 4"],
      ["R1",levels.r1,"#ff9c70","5 4"],
      ["R2",levels.r2,"#ff6572","3 5"]
    ].filter(([,v])=>Number.isFinite(v));

    specs.forEach(([label,v,color,dash])=>{
      const yy=y(v);
      if(yy<8||yy>H-8) return;
      const line=document.createElementNS(NS,"line");
      line.setAttribute("x1","32");line.setAttribute("x2",String(W-8));
      line.setAttribute("y1",String(yy));line.setAttribute("y2",String(yy));
      line.setAttribute("stroke",color);line.setAttribute("stroke-width","1.6");
      line.setAttribute("stroke-dasharray",dash);line.setAttribute("opacity","0.9");
      svg.appendChild(line);
      const text=document.createElementNS(NS,"text");
      text.setAttribute("x",String(W-10));text.setAttribute("y",String(Math.max(12,yy-4)));
      text.setAttribute("text-anchor","end");text.setAttribute("fill",color);
      text.setAttribute("font-size","10");text.setAttribute("font-weight","800");
      text.textContent=`${label} ${Number(v).toLocaleString("en-US",{maximumFractionDigits:2})}`;
      svg.appendChild(text);
    });

    const legend=document.createElement("div");
    legend.className="sr-legend";
    const chip=(cls,label,v)=>Number.isFinite(v)?`<span class="sr-chip ${cls}">${label} ${Number(v).toLocaleString("en-US",{maximumFractionDigits:2})}</span>`:"";
    legend.innerHTML=chip("sr-support","S1",levels.s1)+chip("sr-support","S2",levels.s2)+chip("sr-trigger","BUY TRIGGER",levels.trigger)+chip("sr-resistance","R1",levels.r1)+chip("sr-resistance","R2",levels.r2);
    const panel=svg.closest(".tech-panel");
    if(panel) panel.appendChild(legend);
  }

  async function enrichChartWithLevels(container,ticker){
    try{
      const candles=await fetchChartCandles(ticker);
      addSupportResistanceOverlay(container,pivotLevels(candles));
    }catch(e){ console.warn("HANZ S/R overlay unavailable",e); }
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
          const title=document.getElementById("candidateChartTitle")?.textContent||"";
          const ticker=title.split("·")[0].trim();
          if(ticker) enrichChartWithLevels(target,ticker);
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

  function bindStandaloneChartOverlay(){
    const modal=document.getElementById("candidateChartModal");
    if(!modal || modal.dataset.srObserver==="1") return;
    modal.dataset.srObserver="1";
    const obs=new MutationObserver(()=>{
      if(!modal.classList.contains("show")) return;
      const body=document.getElementById("candidateChartBody");
      if(!body?.querySelector(".tech-svg") || body.querySelector('.tech-svg[data-sr-overlay="1"]')) return;
      const title=document.getElementById("candidateChartTitle")?.textContent||"";
      const ticker=title.split("·")[0].trim();
      if(ticker) enrichChartWithLevels(body,ticker);
    });
    obs.observe(modal,{subtree:true,childList:true,attributes:true});
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
    bindStandaloneChartOverlay();
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
