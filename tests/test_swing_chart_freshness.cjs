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
test("after completed session, require today's bar",()=>{
  const g=guards();
  assert.equal(g.expectedCompletedIdxDate(),"2026-10-20");
  assert.equal(g.chartFreshnessStatus("2026-10-20",[{time:"2026-10-20"}],"2026-10-20").ok,true);
  assert.equal(g.chartFreshnessStatus("2026-10-19",[{time:"2026-10-19"}],"2026-10-20").ok,false);
});
test("during session, require previous completed trading bar",()=>{
  assert.equal(guards({minutes:900}).expectedCompletedIdxDate(),"2026-10-19");
});
test("weekend uses previous trading day",()=>{
  assert.equal(guards({iso:"2026-10-24",trading:false,previous:"2026-10-23"}).expectedCompletedIdxDate(),"2026-10-23");
});
test("unverified future calendar fails closed",()=>{
  assert.equal(guards({year:"2027"}).expectedCompletedIdxDate(),"");
  assert.equal(guards().chartFreshnessStatus("2026-10-20",[{time:"2026-10-20"}],"").ok,false);
});
test("mismatched, missing and empty chart bars fail closed",()=>{
  const g=guards();
  assert.equal(g.chartFreshnessStatus("2026-10-20",[{time:"2026-10-19"}],"2026-10-20").ok,false);
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
  const valid={ticker:"VALID",state:"SWING_BUY",risk_gate:"ELIGIBLE",entry_status:"ENTRY_ZONE",daily_bar_at:"2026-10-20T00:00:00Z",risk_validation:{actionable:true,data_quality:quality}};
  const blocked={...valid,ticker:"BLOCKED",risk_gate:"BLOCKED",risk_validation:{actionable:false,data_quality:{...quality,verified:false}}};
  assert.equal(ctx.hanzExecutionEligible(valid),true);
  assert.equal(ctx.hanzExecutionEligible(blocked),false);
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
    risk_validation:{actionable:true,data_quality:{
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
