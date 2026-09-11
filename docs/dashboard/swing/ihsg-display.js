(() => {
  const ROOT_ID = "hanzIhsgStrip";
  const STYLE_ID = "hanz-ihsg-strip-style";

  function addStyles(){
    if(document.getElementById(STYLE_ID)) return;
    const style=document.createElement("style");
    style.id=STYLE_ID;
    style.textContent=`
      .ihsg-strip{margin:0 0 12px;padding:13px 15px;border:1px solid var(--line);border-radius:16px;background:linear-gradient(145deg,rgba(14,23,42,.9),rgba(8,15,28,.82));display:flex;align-items:center;justify-content:space-between;gap:14px}
      .ihsg-left{display:flex;align-items:center;gap:12px;min-width:0}
      .ihsg-label{font-size:9px;font-weight:900;letter-spacing:.9px;color:var(--muted)}
      .ihsg-value{font-size:23px;font-weight:950;line-height:1.05;margin-top:3px}
      .ihsg-change{font-size:11px;font-weight:900;white-space:nowrap}
      .ihsg-change.up{color:var(--green)}
      .ihsg-change.down{color:var(--red)}
      .ihsg-change.flat{color:var(--muted)}
      .ihsg-meta{text-align:right;color:var(--muted);font-size:8px;line-height:1.45}
      .hanz-action-badge{display:inline-flex;margin-left:6px;padding:3px 6px;border-radius:999px;font-size:7px;font-weight:950;letter-spacing:.3px;vertical-align:middle;border:1px solid rgba(255,255,255,.12)}
      .hanz-action-buy{color:#03120d;background:var(--green);border-color:transparent}
      .hanz-action-wait{color:var(--yellow);background:rgba(255,200,87,.10)}
      .hanz-action-chase{color:#ffb06e;background:rgba(255,176,110,.10)}
      .hanz-action-tp{color:#ff8992;background:rgba(255,101,114,.10)}
      .hanz-action-avoid{color:var(--red);background:rgba(255,101,114,.10)}
      .hanz-auto-note{margin-top:5px;color:var(--muted);font-size:7px;line-height:1.35}
      @media(max-width:700px){.ihsg-strip{align-items:flex-start}.ihsg-value{font-size:20px}.ihsg-meta{max-width:135px}.hanz-action-badge{display:flex;width:max-content;margin:4px 0 0}}
    `;
    document.head.appendChild(style);
  }

  function fmt(v, digits=2){
    const n=Number(v);
    if(!Number.isFinite(n)) return "—";
    return n.toLocaleString("en-US",{minimumFractionDigits:digits,maximumFractionDigits:digits});
  }

  function fmtUpdated(v){
    if(!v) return "Waiting first market snapshot";
    const d=new Date(v);
    if(Number.isNaN(d.getTime())) return "Snapshot available";
    return new Intl.DateTimeFormat("en-GB",{
      timeZone:"Asia/Jakarta",day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit"
    }).format(d) + " WIB";
  }

  function fmtMarketDate(v){
    if(!v) return "latest trading day";
    const d=new Date(`${v}T12:00:00+07:00`);
    if(Number.isNaN(d.getTime())) return v;
    return new Intl.DateTimeFormat("en-GB",{
      timeZone:"Asia/Jakarta",day:"2-digit",month:"short",year:"numeric"
    }).format(d);
  }

  function riskObject(row){
    const raw=row?.risk_validation;
    if(raw && typeof raw==="object") return raw;
    if(typeof raw==="string"){
      try{return JSON.parse(raw);}catch(_e){return {};}
    }
    return {};
  }

  function actionMeta(action){
    const a=String(action||"WAIT").toUpperCase();
    if(a==="BUY") return {label:"BUY",cls:"hanz-action-buy"};
    if(a==="DO_NOT_CHASE") return {label:"DO NOT CHASE",cls:"hanz-action-chase"};
    if(a==="TP_RISK") return {label:"TP RISK",cls:"hanz-action-tp"};
    if(a==="AVOID") return {label:"AVOID",cls:"hanz-action-avoid"};
    return {label:"WAIT",cls:"hanz-action-wait"};
  }

  function renderAutoDecisions(){
    const rows=Array.isArray(window.__hanzSignalRows)?window.__hanzSignalRows:[];
    const rankEls=[...document.querySelectorAll("#ranking .rank")];
    if(!rows.length || !rankEls.length) return;

    rankEls.forEach((el,i)=>{
      const row=rows[i]; if(!row) return;
      const rv=riskObject(row);
      const action=rv.hanz_action || "WAIT";
      const meta=actionMeta(action);
      const symbol=el.querySelector(".rank-symbol");
      if(symbol){
        let badge=symbol.querySelector(".hanz-action-badge");
        if(!badge){badge=document.createElement("span");badge.className="hanz-action-badge";symbol.appendChild(badge);}
        badge.className=`hanz-action-badge ${meta.cls}`;
        badge.textContent=meta.label;
        badge.title=rv.hanz_action_reason || "HANZ automatic trade decision";
      }
    });

    const top=rows[0];
    if(top){
      const rv=riskObject(top), meta=actionMeta(rv.hanz_action);
      const sub=document.getElementById("heroTopSub");
      if(sub){
        const score=Number(rv.canonical_rank_score ?? top.score ?? 0);
        sub.textContent=`HANZ ${meta.label} · Momentum Entry ${Number.isFinite(score)?Math.round(score):0}/100${rv.hanz_action_reason?` · ${rv.hanz_action_reason}`:""}`;
      }
    }

    const detail=document.getElementById("candidateDetailIndicators");
    const modal=document.getElementById("candidateDetailModal");
    if(detail && modal?.classList.contains("show")){
      const title=document.getElementById("candidateDetailTitle")?.textContent||"";
      const ticker=title.split("·")[0].trim();
      const row=rows.find(r=>String(r.ticker||"").toUpperCase()===ticker.toUpperCase());
      if(row){
        const rv=riskObject(row), meta=actionMeta(rv.hanz_action);
        let box=document.getElementById("hanzAutomaticDecisionBox");
        if(!box){
          box=document.createElement("div"); box.id="hanzAutomaticDecisionBox"; box.className="detail-reason";
          detail.insertBefore(box,detail.firstChild);
        }
        box.innerHTML=`<b>HANZ ACTION:</b> <span class="hanz-action-badge ${meta.cls}">${meta.label}</span><div class="hanz-auto-note">${String(rv.hanz_action_reason||"Automatic decision pending fresh scan.")}</div>`;
      }
    }
  }

  function ensureRoot(){
    let root=document.getElementById(ROOT_ID);
    if(root) return root;
    const overview=document.getElementById("overview");
    if(!overview) return null;

    root=document.createElement("section");
    root.id=ROOT_ID;
    root.className="ihsg-strip";
    root.innerHTML=`
      <div class="ihsg-left">
        <div>
          <div class="ihsg-label">IHSG · MARKET SNAPSHOT</div>
          <div id="ihsgValue" class="ihsg-value">—</div>
        </div>
        <div id="ihsgChange" class="ihsg-change flat">—</div>
      </div>
      <div id="ihsgMeta" class="ihsg-meta">Loading IHSG snapshot…</div>`;

    const news=document.getElementById("hanzNewsCatalyst");
    if(news) overview.insertBefore(root,news);
    else overview.insertBefore(root,overview.firstChild);
    return root;
  }

  function render(data){
    const price=Number(data?.price);
    const chg=Number(data?.change);
    const pct=Number(data?.change_pct);
    const value=document.getElementById("ihsgValue");
    const change=document.getElementById("ihsgChange");
    const meta=document.getElementById("ihsgMeta");
    if(!value || !change || !meta) return;

    value.textContent=Number.isFinite(price)?fmt(price,2):"—";
    if(Number.isFinite(chg) && Number.isFinite(pct)){
      const sign=chg>0?"+":"";
      change.textContent=`${sign}${fmt(chg,2)} (${sign}${pct.toFixed(2)}%)`;
      change.className="ihsg-change " + (chg>0?"up":chg<0?"down":"flat");
    }else{
      change.textContent="Waiting market data";
      change.className="ihsg-change flat";
    }

    const isLive=String(data?.quote_type||"").toUpperCase()==="LIVE";
    const headline=isLive
      ? `LIVE · ${fmtMarketDate(data?.market_date)}`
      : `LAST CLOSE · ${fmtMarketDate(data?.market_date)}`;
    meta.innerHTML=`${headline}<br>HANZ refresh: ${fmtUpdated(data?.updated_at)}`;
  }

  async function load(){
    addStyles();
    if(!ensureRoot()) return;
    try{
      const res=await fetch(`./ihsg-snapshot.json?ts=${Date.now()}`,{cache:"no-store"});
      if(!res.ok) throw new Error(`HTTP ${res.status}`);
      render(await res.json());
    }catch(error){
      const meta=document.getElementById("ihsgMeta");
      if(meta) meta.textContent="IHSG snapshot temporarily unavailable";
      console.warn("HANZ IHSG display load failed",error);
    }
    renderAutoDecisions();
  }

  function loadFibonacci(){
    if(document.querySelector('script[data-hanz-fib="1"]')) return;
    const script=document.createElement("script");
    script.src="./fibonacci-overlay.js?v=1";
    script.defer=true;
    script.dataset.hanzFib="1";
    document.head.appendChild(script);
  }

  function start(){
    loadFibonacci();
    load();
    setInterval(load,300000);
    setInterval(renderAutoDecisions,1000);
  }

  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",start);
  else start();
})();
