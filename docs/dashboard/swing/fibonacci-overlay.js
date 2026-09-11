(() => {
  const SUPABASE_URL = "https://fgyfszkadstmdzqvwppt.supabase.co";
  const SUPABASE_KEY = "sb_publishable_rBY4VJwPS1T5tm0zPw4tbg_BhApWtfM";

  function cleanRows(candles){
    return (Array.isArray(candles)?candles:[]).map(c=>({
      high:Number(c.high), low:Number(c.low), close:Number(c.close)
    })).filter(c=>Number.isFinite(c.high)&&Number.isFinite(c.low)&&Number.isFinite(c.close)).slice(-60);
  }

  function activeFib(candles){
    const data=cleanRows(candles);
    if(data.length<20) return null;
    const lows=[], highs=[];
    for(let i=2;i<data.length-2;i++){
      const d=data[i];
      if(d.low<=data[i-1].low&&d.low<=data[i-2].low&&d.low<=data[i+1].low&&d.low<=data[i+2].low) lows.push({i,price:d.low});
      if(d.high>=data[i-1].high&&d.high>=data[i-2].high&&d.high>=data[i+1].high&&d.high>=data[i+2].high) highs.push({i,price:d.high});
    }
    if(!lows.length||!highs.length) return null;
    const high=highs.at(-1);
    const low=[...lows].reverse().find(x=>x.i<high.i);
    if(!low||high.price<=low.price) return null;
    const range=high.price-low.price;
    return {
      data,
      levels:[
        ["Fib 0.382",high.price-range*0.382],
        ["Fib 0.500",high.price-range*0.500],
        ["Fib 0.618",high.price-range*0.618]
      ]
    };
  }

  function chartScale(data){
    const values=[];
    data.forEach(d=>{values.push(d.high,d.low,d.close);});
    return {min:Math.min(...values),max:Math.max(...values)};
  }

  async function fetchCandles(ticker){
    const url=`${SUPABASE_URL}/rest/v1/hanz_swing_chart_data?ticker=eq.${encodeURIComponent(ticker)}&select=candles&limit=1`;
    const r=await fetch(url,{headers:{apikey:SUPABASE_KEY,Authorization:`Bearer ${SUPABASE_KEY}`},cache:"no-store"});
    if(!r.ok) throw new Error(`Fib HTTP ${r.status}`);
    const rows=await r.json();
    return rows?.[0]?.candles||[];
  }

  function draw(container,fib){
    const svg=container?.querySelector(".tech-panel .tech-svg");
    if(!svg||!fib||svg.dataset.fibOverlay==="1") return;
    svg.dataset.fibOverlay="1";
    const W=900,H=330,padY=18,NS="http://www.w3.org/2000/svg";
    const scale=chartScale(fib.data);
    const y=v=>H-padY-((v-scale.min)/((scale.max-scale.min)||1))*(H-padY*2);

    fib.levels.forEach(([label,v],idx)=>{
      const yy=y(v);
      if(yy<8||yy>H-8) return;
      const line=document.createElementNS(NS,"line");
      line.setAttribute("x1","32"); line.setAttribute("x2",String(W-8));
      line.setAttribute("y1",String(yy)); line.setAttribute("y2",String(yy));
      line.setAttribute("stroke",idx===1?"#ffd166":"#f8c35e");
      line.setAttribute("stroke-width",idx===1?"1.8":"1.2");
      line.setAttribute("stroke-dasharray",idx===1?"7 4":"3 5");
      line.setAttribute("opacity","0.78");
      svg.appendChild(line);

      const text=document.createElementNS(NS,"text");
      text.setAttribute("x","36"); text.setAttribute("y",String(Math.max(12,yy-4)));
      text.setAttribute("fill",idx===1?"#ffd166":"#f8c35e");
      text.setAttribute("font-size","10"); text.setAttribute("font-weight","800");
      text.textContent=`${label} ${Number(v).toLocaleString("en-US",{maximumFractionDigits:2})}`;
      svg.appendChild(text);
    });
  }

  function tickerFromPage(){
    const t=document.getElementById("candidateChartTitle")?.textContent||"";
    if(t.includes("·")) return t.split("·")[0].trim();
    const d=document.getElementById("candidateDetailTitle")?.textContent||"";
    return d.includes("·")?d.split("·")[0].trim():"";
  }

  async function apply(){
    const ticker=tickerFromPage();
    if(!ticker) return;
    const containers=[document.getElementById("candidateChartBody"),document.getElementById("radarIntegratedChart")].filter(Boolean);
    if(!containers.length) return;
    try{
      const fib=activeFib(await fetchCandles(ticker));
      containers.forEach(c=>draw(c,fib));
    }catch(e){console.warn("HANZ Fibonacci overlay unavailable",e);}
  }

  const observer=new MutationObserver(()=>{setTimeout(apply,80);});
  observer.observe(document.body,{subtree:true,childList:true});
  setInterval(apply,1200);
})();
