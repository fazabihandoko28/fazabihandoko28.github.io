const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const html=fs.readFileSync(path.join(__dirname,"../docs/dashboard/swing/index.html"),"utf8");
const start=html.indexOf("function expectedCompletedIdxDate(){");
const end=html.indexOf("async function openCandidateChart(index){",start);
assert.ok(start>=0 && end>start,"freshness guards must exist in production HTML");
const source=html.slice(start,end);
function guards({iso="2026-10-20",year="2026",minutes=1350,trading=true,previous="2026-10-19"}={}){
  const context={
    idxStatusNow:()=>({parts:{iso,year,minutes}}),
    isIdxTradingIso:()=>trading,
    nearestTradingDay:()=>previous,
  };
  vm.runInNewContext(source,context);
  return context;
}
function candle(time="2026-10-20",overrides={}){
  return {time,open:33,high:34,low:32,close:33,volume:1000,...overrides};
}

test("after completed session, require today's bar",()=>{
  const g=guards();
  assert.equal(g.expectedCompletedIdxDate(),"2026-10-20");
  assert.equal(g.chartFreshnessStatus("2026-10-20",[candle("2026-10-20")],"2026-10-20").ok,true);
  assert.equal(g.chartFreshnessStatus("2026-10-19",[candle("2026-10-19")],"2026-10-20").ok,false);
});
test("during session, require previous completed trading bar",()=>{
  assert.equal(guards({minutes:900}).expectedCompletedIdxDate(),"2026-10-19");
});
test("weekend uses previous trading day",()=>{
  assert.equal(guards({iso:"2026-10-24",trading:false,previous:"2026-10-23"}).expectedCompletedIdxDate(),"2026-10-23");
});
test("unverified future calendar fails closed",()=>{
  assert.equal(guards({year:"2027"}).expectedCompletedIdxDate(),"");
  assert.equal(guards().chartFreshnessStatus("2026-10-20",[candle("2026-10-20")],"").ok,false);
});
test("mismatched, missing and empty chart bars fail closed",()=>{
  const g=guards();
  assert.equal(g.chartFreshnessStatus("2026-10-20",[candle("2026-10-19")],"2026-10-20").ok,false);
  assert.equal(g.chartFreshnessStatus("2026-10-20",[],"2026-10-20").ok,false);
  assert.equal(g.chartFreshnessStatus(null,null,"2026-10-20").ok,false);
});

// Regression: technical BUY states alone must never inflate confirmed BUY counts.
test("unverified technical BUY remains radar-only and never labels hero as BUY",()=>{
  const guardStart=html.indexOf("function hanzExecutionEligible(row){");
  const guardEnd=html.indexOf("function effectiveHanzAction(row){",guardStart);
  assert.ok(guardStart>=0 && guardEnd>guardStart);
  const ctx={riskObject:row=>row.risk_validation||{},expectedCompletedIdxDate:()=> "2026-10-20"};
  vm.runInNewContext(html.slice(guardStart,guardEnd),ctx);
  const quality={verified:true,status:"VERIFIED",verifier_source:"INDEPENDENT_IDX",primary_date:"2026-10-20",verifier_date:"2026-10-20"};
  const fullSafety={data_same_session_verified:true,strategy_validation:{passed:true},costs_configured:true,account_capital_configured:true,buy_fee_pct:0.15,sell_fee_pct:0.25,slippage_pct:0.10,blockers:[],cautions:[]};
  const valid={ticker:"VALID",state:"SWING_BUY",risk_gate:"ELIGIBLE",entry_status:"ENTRY_ZONE",daily_bar_at:"2026-10-20T00:00:00Z",risk_validation:{actionable:true,data_quality:quality,...fullSafety}};
  const blocked={...valid,ticker:"BLOCKED",risk_gate:"BLOCKED",risk_validation:{actionable:false,data_quality:{...quality,verified:false}}};
  assert.equal(ctx.hanzExecutionEligible(valid),true);
  assert.equal(ctx.hanzExecutionEligible(blocked),false);
  // A spoofed ELIGIBLE/ENTRY_ZONE label must never bypass execution evidence.
  for(const key of ["data_same_session_verified","costs_configured","account_capital_configured"]){
    assert.equal(ctx.hanzExecutionEligible({...valid,risk_validation:{...valid.risk_validation,[key]:false}}),false,key);
  }
  for(const key of ["buy_fee_pct","sell_fee_pct","slippage_pct"]){
    assert.equal(ctx.hanzExecutionEligible({...valid,risk_validation:{...valid.risk_validation,[key]:null}}),false,key);
  }
  assert.equal(ctx.hanzExecutionEligible({...valid,state:"RADAR_WATCH"}),false);
  assert.equal(ctx.hanzExecutionEligible({...valid,risk_validation:{...valid.risk_validation,strategy_validation:{passed:false}}}),false);
  assert.equal(ctx.hanzExecutionEligible({...valid,risk_validation:{...valid.risk_validation,blockers:["MARKET_REGIME"]}}),false);
  assert.equal(ctx.hanzExecutionEligible({...valid,risk_validation:{...valid.risk_validation,cautions:["PERFORMANCE_WARMUP"]}}),false);
  assert.ok(html.includes('const state=candidateStateLabel(top).label;'));
  assert.ok(html.includes('const state=candidateStateLabel(row).label;'));
  assert.ok(html.includes('DAILY REFERENCE · NOT LIVE'));
  assert.ok(html.includes('.filter(r=>hanzExecutionEligible(r) && ["EARLY_CONFIRMED_BUY"'));
  assert.ok(html.includes('const isBuy=hanzExecutionEligible(top) &&'));
  assert.ok(html.includes('.filter(r=>!confirmed.includes(r));'));
  assert.ok(html.includes('<span>TOP SWING OPPORTUNITY</span>'));
  assert.ok(!html.includes('<span>CURRENT TOP SWING BUY</span>'));
});

test("otherwise verified stale, future, or calendar-unverified BUY is blocked",()=>{
  const guardStart=html.indexOf("function hanzExecutionEligible(row){");
  const guardEnd=html.indexOf("function effectiveHanzAction(row){",guardStart);
  assert.ok(guardStart>=0 && guardEnd>guardStart);
  let expectedDate="2026-10-20";
  const ctx={riskObject:row=>row.risk_validation||{},expectedCompletedIdxDate:()=>expectedDate};
  vm.runInNewContext(html.slice(guardStart,guardEnd),ctx);
  const row=(date)=>({
    ticker:"TEST",state:"SWING_BUY",risk_gate:"ELIGIBLE",entry_status:"ENTRY_ZONE",
    daily_bar_at:date+"T00:00:00Z",
    risk_validation:{actionable:true,data_same_session_verified:true,
      strategy_validation:{passed:true},costs_configured:true,account_capital_configured:true,
      buy_fee_pct:0.15,sell_fee_pct:0.25,slippage_pct:0.10,blockers:[],cautions:[],data_quality:{
      verified:true,status:"VERIFIED",verifier_source:"INDEPENDENT_IDX",
      primary_date:date,verifier_date:date
    }}
  });
  assert.equal(ctx.hanzExecutionEligible(row("2026-10-20")),true);
  assert.equal(ctx.hanzExecutionEligible(row("2026-10-19")),false);
  assert.equal(ctx.hanzExecutionEligible(row("2026-10-21")),false);
  expectedDate="";
  assert.equal(ctx.hanzExecutionEligible(row("2026-10-20")),false);
});

test("matching dates never certify corrupt OHLC or zero-volume latest bars",()=>{
  const g=guards();
  assert.equal(g.chartFreshnessStatus("2026-10-20",[candle()],"2026-10-20").ok,true);
  // Actual VIVA anomaly: close 31 below low 32 despite positive volume.
  const viva=candle("2026-10-20",{open:34,high:34,low:32,close:31,volume:54589600});
  assert.equal(g.chartFreshnessStatus("2026-10-20",[viva],"2026-10-20").ok,false);
  assert.equal(g.chartFreshnessStatus("2026-10-20",[candle("2026-10-20",{volume:0})],"2026-10-20").ok,false);
  assert.equal(g.chartFreshnessStatus("2026-10-20",[candle("2026-10-19",{low:35}),candle()],"2026-10-20").ok,false);
  assert.equal(g.chartFreshnessStatus("2026-10-20",[{time:"2026-10-20"}],"2026-10-20").ok,false);
});


test("PMR80 trade levels fail closed even when risk flags are spoofed",()=>{
  const pmr=fs.readFileSync(path.join(__dirname,"../docs/dashboard/swing/pmr80-radar.js"),"utf8");
  const start=pmr.indexOf("function openModal(index){");
  const end=pmr.indexOf("function ensureStatus(){",start);
  assert.ok(start>=0 && end>start,"PMR80 modal must exist");
  for(const [risk_gate,entry_status] of [["ELIGIBLE","ENTRY_ZONE"],[null,"UNVALIDATED_LEVELS"]]){
    const box={innerHTML:""};
    const modal={classList:{add(){}},setAttribute(){}};
    const ctx={
      cache:[{ticker:"SPOOF",rank:1,prediction_label:"RADAR_CANDIDATE",risk_gate,entry_status,
        price:123,entry_low:101,entry_high:102,stop_loss:90,target_1:130,target_2:140}],
      ensureModal(){},closeModal(){},
      document:{getElementById:id=>id==="pmr80ModalBox"?box:id==="pmr80DetailModal"?modal:{onclick:null}},
      esc:v=>String(v??""),fmtPrice:v=>String(v),fmtPct:v=>String(v),
      num:v=>v==null?null:Number(v)
    };
    vm.runInNewContext(pmr.slice(start,end),ctx);
    ctx.openModal(0);
    assert.match(box.innerHTML,/ENTRY ZONE<\/span><strong>NOT VALIDATED – NOT VALIDATED/);
    assert.equal((box.innerHTML.match(/NOT VALIDATED/g)||[]).length,5);
    assert.doesNotMatch(box.innerHTML,/ENTRY ZONE<\/span><strong>101 – 102/);
    assert.match(box.innerHTML,/REFERENCE PRICE<\/span><strong>123/);
  }
});

test("daily-bar KPI uses the actual source bar date, never row update or market clock",()=>{
  assert.doesNotMatch(html, /id="lastUpdateDate">Supabase Live/);
  assert.match(html, /hanzDailyBarStatus\(top,expectedCompletedIdxDate\(\)\)/);
  const start=html.indexOf("function hanzDailyBarStatus(row,expectedDate){");
  const end=html.indexOf("/* SHARED SWING BUY */",start);
  assert.ok(start>=0 && end>start,"daily-bar source date guard must exist");
  const ctx={riskObject:row=>row?.risk_validation||{}};
  vm.runInNewContext(html.slice(start,end),ctx);
  const date="2026-10-23";
  const row={daily_bar_at:date+"T00:00:00Z",updated_at:"2026-10-24T10:00:00Z",risk_validation:{
    data_quality:{verified:false,status:"UNVERIFIED",primary_date:date}
  }};
  const unverified=ctx.hanzDailyBarStatus(row,date);
  assert.match(unverified,/BAR 2026-10-23/);
  assert.match(unverified,/PRICE UNVERIFIED/);
  assert.match(unverified,/NOT LIVE/);
  assert.doesNotMatch(unverified,/2026-10-24/);
  assert.match(ctx.hanzDailyBarStatus(row,"2026-10-22"),/STALE \/ UNKNOWN/);
  assert.match(ctx.hanzDailyBarStatus({...row,daily_bar_at:null},date),/BAR UNKNOWN/);
  assert.match(ctx.hanzDailyBarStatus(row,""),/STALE \/ UNKNOWN/);
  const verified={...row,risk_validation:{data_quality:{
    verified:true,status:"VERIFIED",verifier_source:"INDEPENDENT_IDX",
    primary_date:date,verifier_date:date
  }}};
  assert.match(ctx.hanzDailyBarStatus(verified,date),/INDEPENDENTLY VERIFIED DAILY BAR/);
  assert.match(ctx.hanzDailyBarStatus(verified,date),/NOT LIVE/);
  assert.match(ctx.hanzDailyBarStatus({...verified,risk_validation:{data_quality:{
    ...verified.risk_validation.data_quality,verifier_date:"2026-10-22"
  }}},date),/PRICE UNVERIFIED/);
  const clockStart=html.indexOf("function renderIdxMarketClock(){");
  const clockEnd=html.indexOf("/* Exchange event confirmed",clockStart);
  assert.ok(clockStart>=0 && clockEnd>clockStart);
  assert.doesNotMatch(html.slice(clockStart,clockEnd),/lastUpdateDate/,
    "market clock must not overwrite the real daily-bar freshness label");
});
