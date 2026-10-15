(() => {
  const SUPABASE_URL = "https://fgyfszkadstmdzqvwppt.supabase.co";
  const SUPABASE_KEY = "sb_publishable_rBY4VJwPS1T5tm0zPw4tbg_BhApWtfM";
  const TABLE = "hanz_premarket_bullish_current";
  const V4_LABELS = new Set([
    "RADAR_STRICT_UNVALIDATED",
    "RADAR_NEAR_HIGH_CONF",
    "RADAR_CANDIDATE",
    "RADAR_LOW_CONF"
  ]);
  const className = r => ({RADAR_STRICT_UNVALIDATED:"STRICT · UNVALIDATED",RADAR_NEAR_HIGH_CONF:"NEAR STRICT",RADAR_CANDIDATE:"CANDIDATE",RADAR_LOW_CONF:"LOW SCORE"})[String(r.prediction_label||"").toUpperCase()] || "UNCLASSIFIED";
  let cache = [];
  let applying = false;
  let loading = false;
  let failure = "Loading radar data";

  const esc = v => String(v ?? "")
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;");

  const num = v => {
    if(v === null || v === undefined || v === "") return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  };

  const fmtPrice = v => {
    const n = num(v);
    return n === null ? "—" : n.toLocaleString("en-US",{maximumFractionDigits:2});
  };

  const fmtPct = v => {
    const n = num(v);
    return n === null ? "—" : `${n>=0?"+":""}${n.toFixed(2)}%`;
  };

  function addStyles(){
    if(document.getElementById("pmr80-live-style")) return;
    const s=document.createElement("style");
    s.id="pmr80-live-style";
    s.textContent=`
      .pmr80-badge{display:inline-flex;align-items:center;margin-left:4px;padding:3px 6px;border-radius:999px;font-size:7px;font-weight:950;letter-spacing:.3px;vertical-align:middle}
      .pmr80-badge.high{color:#04130e;background:linear-gradient(135deg,var(--green),var(--cyan));box-shadow:0 0 16px rgba(40,224,162,.24)}
      .pmr80-badge.radar{color:var(--yellow);background:rgba(255,200,87,.10);border:1px solid rgba(255,200,87,.18)}
      .pmr80-status{display:flex;justify-content:space-between;align-items:center;gap:8px;margin:0 0 9px;padding:7px 9px;border:1px solid rgba(40,224,162,.14);border-radius:10px;background:rgba(40,224,162,.035);font-size:8px;color:var(--muted)}
      .pmr80-status strong{color:var(--green);font-size:8px}
      #ranking .rank[data-pmr80-row="1"]{cursor:pointer}
      #pmr80DetailModal{position:fixed;inset:0;z-index:900;display:none;align-items:center;justify-content:center;padding:16px;background:rgba(1,5,12,.82);backdrop-filter:blur(8px)}
      #pmr80DetailModal.show{display:flex}
      .pmr80-modal-box{width:min(520px,100%);max-height:calc(100vh - 32px);overflow:auto;border:1px solid var(--line);border-radius:20px;background:linear-gradient(160deg,#101b2f,#080f1c);padding:18px;box-shadow:0 30px 90px rgba(0,0,0,.55)}
      .pmr80-modal-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;margin-bottom:14px}
      .pmr80-modal-head h3{margin:0;font-size:18px}.pmr80-modal-head p{margin:4px 0 0;color:var(--muted);font-size:9px}
      .pmr80-close{width:32px;height:32px;border:1px solid var(--line);border-radius:9px;background:rgba(4,10,20,.5);color:var(--muted)}
      .pmr80-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
      .pmr80-box{padding:10px;border-radius:11px;background:rgba(2,8,17,.48)}
      .pmr80-box span{display:block;color:var(--muted);font-size:7px}.pmr80-box strong{display:block;margin-top:4px;font-size:11px}
      .pmr80-reason{margin-top:10px;padding:10px;border-radius:11px;background:rgba(77,163,255,.055);color:#aeb9c9;font-size:9px;line-height:1.55}
      @media(max-width:560px){.pmr80-grid{grid-template-columns:1fr 1fr}.pmr80-status{align-items:flex-start;flex-direction:column}}
    `;
    document.head.appendChild(s);
  }

  function ensureModal(){
    if(document.getElementById("pmr80DetailModal")) return;
    const modal=document.createElement("div");
    modal.id="pmr80DetailModal";
    modal.setAttribute("aria-hidden","true");
    modal.innerHTML='<div class="pmr80-modal-box" id="pmr80ModalBox"></div>';
    modal.addEventListener("click",e=>{ if(e.target===modal) closeModal(); });
    document.body.appendChild(modal);
  }

  function closeModal(){
    const m=document.getElementById("pmr80DetailModal");
    if(!m) return;
    m.classList.remove("show");
    m.setAttribute("aria-hidden","true");
  }

  function openModal(index){
    const r=cache[index]; if(!r) return;
    ensureModal();
    const high=String(r.prediction_label||"").toUpperCase()==="RADAR_STRICT_UNVALIDATED";
    const approved=String(r.risk_gate||"").toUpperCase()==="ELIGIBLE" && String(r.entry_status||"").toUpperCase()==="ENTRY_ZONE";
    const tradeLevel=v=>approved?fmtPrice(v):"NOT VALIDATED";
    const box=document.getElementById("pmr80ModalBox");
    box.innerHTML=`
      <div class="pmr80-modal-head">
        <div><h3>${esc(r.ticker)} · ${high?"STRICT · UNVALIDATED":"HANZ RADAR"}</h3><p>Rank #${Number(r.rank||index+1)} · score ${Number(r.prediction_score||0)}/100 · source bar ${esc(String(r.source_bar_at||"").slice(0,10))}</p></div>
        <button class="pmr80-close" id="pmr80CloseBtn" type="button">×</button>
      </div>
      <div class="pmr80-grid">
        <div class="pmr80-box"><span>REFERENCE PRICE</span><strong>${fmtPrice(r.price)}</strong></div>
        <div class="pmr80-box"><span>CLASS</span><strong>${high?"NOT OUT-OF-SAMPLE VALIDATED":esc(String(r.prediction_label||"RADAR").replaceAll("_"," "))}</strong></div>
        <div class="pmr80-box"><span>1D / 3D / 5D</span><strong>${fmtPct(r.ret1_pct)} · ${fmtPct(r.ret3_pct)} · ${fmtPct(r.ret5_pct)}</strong></div>
        <div class="pmr80-box"><span>RVOL</span><strong>${num(r.daily_rvol)===null?"—":Number(r.daily_rvol).toFixed(2)+"x"}</strong></div>
        <div class="pmr80-box"><span>ENTRY ZONE</span><strong>${tradeLevel(r.entry_low)} – ${tradeLevel(r.entry_high)}</strong></div>
        <div class="pmr80-box"><span>CL / INVALIDATION</span><strong>${tradeLevel(r.stop_loss)}</strong></div>
        <div class="pmr80-box"><span>TARGET 1</span><strong>${tradeLevel(r.target_1)}</strong></div>
        <div class="pmr80-box"><span>TARGET 2</span><strong>${tradeLevel(r.target_2)}</strong></div>
      </div>
      <div class="pmr80-reason"><b>Why ranked:</b> ${esc(r.reason||"No explanation available.")}<br><br><b>Rule:</b> STRICT means all technical conditions passed, NOT an independently validated win probability. Ordinary RADAR rows are relative candidates, not an 80% probability claim and not automatic BUY confirmation.</div>`;
    document.getElementById("pmr80CloseBtn").onclick=closeModal;
    const modal=document.getElementById("pmr80DetailModal");
    modal.classList.add("show");
    modal.setAttribute("aria-hidden","false");
  }

  function ensureStatus(){
    const ranking=document.getElementById("ranking");
    if(!ranking) return null;
    let s=document.getElementById("pmr80RadarStatus");
    if(!s){
      s=document.createElement("div");
      s.id="pmr80RadarStatus";
      s.className="pmr80-status";
      ranking.parentElement?.insertBefore(s,ranking);
    }
    return s;
  }

  function render(){
    if(applying) return;
    if(!cache.length){
      const ranking=document.getElementById("ranking");
      if(ranking) ranking.innerHTML='<div class="empty">DATA UNAVAILABLE · '+esc(failure)+'</div>';
      const status=ensureStatus();
      if(status) status.innerHTML='<span>'+esc(failure)+'</span><strong>RETRYING · DATA UNAVAILABLE</strong>';
      for(const id of ["topCandidate","heroTopCandidate","lastUpdate"]) { const el=document.getElementById(id); if(el) el.textContent="—"; }
      for(const id of ["topCandidateSub","heroTopSub","lastUpdateDate"]) { const el=document.getElementById(id); if(el) el.textContent="DATA UNAVAILABLE · "+failure; }
      return;
    }
    const ranking=document.getElementById("ranking");
    if(!ranking) return;
    applying=true;
    try{
      const strictCount=cache.filter(r=>String(r.prediction_label||"").toUpperCase()==="RADAR_STRICT_UNVALIDATED").length;
      const status=ensureStatus();
      if(status){
        const newest=cache.map(r=>r.generated_at).filter(Boolean).sort().reverse()[0];
        status.innerHTML=`<span>PMR80 V4 · latest completed-bar ranking · ${strictCount}/${cache.length} strict unvalidated</span><strong>${strictCount?"STRICT SETUP DETECTED":"RADAR MODE"}${newest?` · ${esc(new Date(newest).toLocaleTimeString("en-GB",{timeZone:"Asia/Jakarta",hour:"2-digit",minute:"2-digit"})+" WIB")}`:""}</strong>`;
      }
      ranking.innerHTML=cache.slice(0,5).map((r,i)=>{
        const score=Math.max(0,Math.min(100,Number(r.prediction_score||0)));
        const high=String(r.prediction_label||"").toUpperCase()==="RADAR_STRICT_UNVALIDATED";
        const badge=`<span class="pmr80-badge ${high?'high':'radar'}">${esc(className(r))}</span>`;
        const label=className(r);
        return `<div class="rank" role="button" tabindex="0" data-pmr80-row="1" data-pmr80-index="${i}" title="${esc(r.reason||"")}">
          <div class="rank-no">#${i+1}</div>
          <div class="rank-symbol">${esc(r.ticker)} ${badge}</div>
          <div class="rank-track"><div style="width:${score}%"></div></div>
          <div class="rank-score">${score}/100 · ${label}</div>
        </div>`;
      }).join("");
      ranking.querySelectorAll('[data-pmr80-row="1"]').forEach(el=>{
        el.addEventListener("click",()=>openModal(Number(el.dataset.pmr80Index||0)));
        el.addEventListener("keydown",e=>{if(e.key==="Enter" || e.key===" "){e.preventDefault();openModal(Number(el.dataset.pmr80Index||0));}});
      });

      const top=cache[0];
      const last=document.getElementById("lastUpdate");
      if(last) last.textContent=new Date(top.generated_at).toLocaleTimeString("en-GB",{timeZone:"Asia/Jakarta",hour:"2-digit",minute:"2-digit"})+" WIB";
      const date=document.getElementById("lastUpdateDate");
      if(date) date.textContent="Daily reference bar: "+String(top.source_bar_at||"").slice(0,10)+" · ranking refreshed; price is not a live quote";
      if(top){
        const high=String(top.prediction_label||"").toUpperCase()==="RADAR_STRICT_UNVALIDATED";
        const a=document.getElementById("topCandidate"); if(a) a.textContent=top.ticker;
        const b=document.getElementById("topCandidateSub"); if(b) b.textContent=`PMR80 V4 · ${top.prediction_score}/100 · ${className(top)}`;
        const c=document.getElementById("heroTopCandidate"); if(c) c.textContent=top.ticker;
        const d=document.getElementById("heroTopSub"); if(d) d.textContent=high?"STRICT TECHNICAL SETUP · NOT VALIDATED · NOT BUY":"HANZ DAILY-BAR RADAR · NOT CONFIRMED BUY";
      }
    } finally { applying=false; }
  }

  function validateRows(rows, now=Date.now()){
    if(!Array.isArray(rows) || !rows.length) throw new Error("Radar returned no data");
    if(rows.length>5 || new Set(rows.map(r=>r.ticker)).size!==rows.length) throw new Error("Invalid radar ranking");
    for(const [i,r] of rows.entries()){
      if(!r.ticker || Number(r.rank)!==i+1 || !V4_LABELS.has(String(r.prediction_label||"").toUpperCase())) throw new Error("Radar model is syncing");
      const age=now-Date.parse(r.generated_at);
      const score=num(r.prediction_score);
      if(!Number.isFinite(age) || age < -60000 || !Number.isFinite(Date.parse(r.source_bar_at)) || score===null || score<0 || score>100 || !(num(r.price)>0)) throw new Error("Invalid radar data");
      const wib=new Date(now+7*3600000);
      const minute=wib.getUTCHours()*60+wib.getUTCMinutes();
      const marketWindow=wib.getUTCDay()>0 && wib.getUTCDay()<6 && minute>=515 && minute<=975;
      // Daily-bar predictions are not intraday quotes. Check completed-bar age, not publish age.
      const barDay=String(r.source_bar_at).slice(0,10);
      const today=new Date(now+7*3600000).toISOString().slice(0,10);
      const days=Math.floor((Date.parse(today+"T00:00:00Z")-Date.parse(barDay+"T00:00:00Z"))/86400000);
      if(days<0 || days>5) throw new Error("Radar source bar is stale or in the future");
    }
    return rows;
  }

  async function fetchRows(){
    if(loading) return;
    loading=true;
    try{
      // PostgREST interprets unknown query parameters as column filters.
      const url=`${SUPABASE_URL}/rest/v1/${TABLE}?select=*&order=rank.asc&limit=5`;
      const response=await fetch(url,{headers:{apikey:SUPABASE_KEY,Authorization:`Bearer ${SUPABASE_KEY}`},cache:"no-store",signal:AbortSignal.timeout(8000)});
      if(!response.ok) throw new Error(`PMR80 HTTP ${response.status}`);
      cache=validateRows(await response.json());
      failure="";
    }catch(err){
      cache=[];
      failure=err.message||"Radar connection failed";
      console.warn("HANZ PMR80 radar load failed",err);
    }finally{ loading=false; render(); }
  }

  window.hanzPmr80={render,fetchRows,validateRows};

  function start(){
    addStyles();
    ensureModal();
    fetchRows();
    setInterval(fetchRows,10000);
    document.addEventListener("visibilitychange",()=>{ if(!document.hidden) fetchRows(); });
    window.addEventListener("online",fetchRows);
    render();
  }

  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",start);
  else start();
})();