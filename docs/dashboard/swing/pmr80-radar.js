(() => {
  const SUPABASE_URL = "https://fgyfszkadstmdzqvwppt.supabase.co";
  const SUPABASE_KEY = "sb_publishable_rBY4VJwPS1T5tm0zPw4tbg_BhApWtfM";
  const TABLE = "hanz_premarket_bullish_current";
  const V4_LABELS = new Set([
    "HIGH_CONFIDENCE_CALL_PMR80",
    "RADAR_NEAR_HIGH_CONF",
    "RADAR_CANDIDATE",
    "RADAR_LOW_CONF"
  ]);
  let cache = [];
  let applying = false;

  const esc = v => String(v ?? "")
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;");

  const num = v => {
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
    const high=String(r.prediction_label||"").toUpperCase()==="HIGH_CONFIDENCE_CALL_PMR80";
    const box=document.getElementById("pmr80ModalBox");
    box.innerHTML=`
      <div class="pmr80-modal-head">
        <div><h3>${esc(r.ticker)} · ${high?"PMR80 HIGH CONF":"HANZ RADAR"}</h3><p>Rank #${Number(r.rank||index+1)} · score ${Number(r.prediction_score||0)}/100 · source bar ${esc(String(r.source_bar_at||"").slice(0,10))}</p></div>
        <button class="pmr80-close" id="pmr80CloseBtn" type="button">×</button>
      </div>
      <div class="pmr80-grid">
        <div class="pmr80-box"><span>REFERENCE PRICE</span><strong>${fmtPrice(r.price)}</strong></div>
        <div class="pmr80-box"><span>CLASS</span><strong>${high?"PMR80 ≥80% HIST.":esc(String(r.prediction_label||"RADAR").replaceAll("_"," "))}</strong></div>
        <div class="pmr80-box"><span>1D / 3D / 5D</span><strong>${fmtPct(r.ret1_pct)} · ${fmtPct(r.ret3_pct)} · ${fmtPct(r.ret5_pct)}</strong></div>
        <div class="pmr80-box"><span>RVOL</span><strong>${num(r.daily_rvol)===null?"—":Number(r.daily_rvol).toFixed(2)+"x"}</strong></div>
        <div class="pmr80-box"><span>ENTRY ZONE</span><strong>${fmtPrice(r.entry_low)} – ${fmtPrice(r.entry_high)}</strong></div>
        <div class="pmr80-box"><span>CL / INVALIDATION</span><strong>${fmtPrice(r.stop_loss)}</strong></div>
        <div class="pmr80-box"><span>TARGET 1</span><strong>${fmtPrice(r.target_1)}</strong></div>
        <div class="pmr80-box"><span>TARGET 2</span><strong>${fmtPrice(r.target_2)}</strong></div>
      </div>
      <div class="pmr80-reason"><b>Why ranked:</b> ${esc(r.reason||"No explanation available.")}<br><br><b>Rule:</b> PMR80 badge is only shown for the strict historically validated pattern. Ordinary RADAR rows are relative candidates, not an 80% probability claim and not automatic BUY confirmation.</div>`;
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
    if(applying || !cache.length) return;
    const ranking=document.getElementById("ranking");
    if(!ranking) return;
    applying=true;
    try{
      const strictCount=cache.filter(r=>String(r.prediction_label||"").toUpperCase()==="HIGH_CONFIDENCE_CALL_PMR80").length;
      const status=ensureStatus();
      if(status){
        const newest=cache.map(r=>r.generated_at).filter(Boolean).sort().reverse()[0];
        status.innerHTML=`<span>PMR80 V4 · latest completed-bar ranking · ${strictCount}/5 strict high-confidence</span><strong>${strictCount?"PMR80 ACTIVE":"RADAR MODE"}${newest?` · ${esc(new Date(newest).toLocaleTimeString("en-GB",{hour:"2-digit",minute:"2-digit"}))}`:""}</strong>`;
      }
      ranking.innerHTML=cache.slice(0,5).map((r,i)=>{
        const score=Math.max(0,Math.min(100,Number(r.prediction_score||0)));
        const high=String(r.prediction_label||"").toUpperCase()==="HIGH_CONFIDENCE_CALL_PMR80";
        const badge=high?'<span class="pmr80-badge high">PMR80 HIGH CONF</span>':'<span class="pmr80-badge radar">RADAR</span>';
        const label=high?"PMR80":"WATCH";
        return `<div class="rank" data-pmr80-row="1" data-pmr80-index="${i}" title="${esc(r.reason||"")}">
          <div class="rank-no">#${i+1}</div>
          <div class="rank-symbol">${esc(r.ticker)} ${badge}</div>
          <div class="rank-track"><div style="width:${score}%"></div></div>
          <div class="rank-score">${score}/100 · ${label}</div>
        </div>`;
      }).join("");
      ranking.querySelectorAll('[data-pmr80-row="1"]').forEach(el=>{
        el.addEventListener("click",()=>openModal(Number(el.dataset.pmr80Index||0)));
      });

      const top=cache[0];
      if(top){
        const high=String(top.prediction_label||"").toUpperCase()==="HIGH_CONFIDENCE_CALL_PMR80";
        const a=document.getElementById("topCandidate"); if(a) a.textContent=top.ticker;
        const b=document.getElementById("topCandidateSub"); if(b) b.textContent=`PMR80 V4 · ${top.prediction_score}/100 · ${high?"HIGH CONF":"RADAR"}`;
        const c=document.getElementById("heroTopCandidate"); if(c) c.textContent=top.ticker;
        const d=document.getElementById("heroTopSub"); if(d) d.textContent=high?"PMR80 HIGH-CONFIDENCE BULLISH BEHAVIOR CALL":"HANZ PREMARKET / LIVE RADAR · NOT PMR80 HIGH CONF";
      }
    } finally { applying=false; }
  }

  async function fetchRows(){
    try{
      const url=`${SUPABASE_URL}/rest/v1/${TABLE}?select=*&order=rank.asc&limit=5&ts=${Date.now()}`;
      const response=await fetch(url,{headers:{apikey:SUPABASE_KEY,Authorization:`Bearer ${SUPABASE_KEY}`},cache:"no-store"});
      if(!response.ok) throw new Error(`PMR80 HTTP ${response.status}`);
      const rows=await response.json();
      if(!Array.isArray(rows) || !rows.length) return;
      const isV4=rows.every(r=>V4_LABELS.has(String(r.prediction_label||"").toUpperCase()));
      if(!isV4){
        const status=ensureStatus();
        if(status) status.innerHTML='<span>PMR80 V4 is syncing from the latest completed bar…</span><strong>UPDATING</strong>';
        return;
      }
      cache=rows.slice(0,5);
      render();
    }catch(err){ console.warn("HANZ PMR80 radar load failed",err); }
  }

  function start(){
    addStyles();
    ensureModal();
    fetchRows();
    setInterval(fetchRows,10000);
    const ranking=document.getElementById("ranking");
    if(ranking){
      const obs=new MutationObserver(()=>{ if(cache.length) setTimeout(render,0); });
      obs.observe(ranking,{childList:true,subtree:true});
    }
  }

  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",start);
  else start();
})();