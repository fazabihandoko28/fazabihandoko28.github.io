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
      @media(max-width:700px){.ihsg-strip{align-items:flex-start}.ihsg-value{font-size:20px}.ihsg-meta{max-width:125px}}
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
      <div id="ihsgMeta" class="ihsg-meta">Refresh 3× per trading day<br>09:10 · 11:10 · 14:10 WIB</div>`;

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
    meta.innerHTML=`Last HANZ call: ${fmtUpdated(data?.updated_at)}<br>Server refresh only while IDX is open`;
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
  }

  function start(){
    load();
    setInterval(load,300000);
  }

  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",start);
  else start();
})();
