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
