const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('docs/dashboard/swing/ihsg-display.js','utf8').replace('if(document.readyState===','globalThis.renderSnapshot=render; if(document.readyState===');
function display(overrides={},elapsed=0){
  const now=Date.parse('2026-10-20T15:54:00+07:00')+elapsed;
  const elements={ihsgValue:{},ihsgChange:{},ihsgMeta:{}};
  class Clock extends Date {static now(){return now;}}
  const context={Date:Clock,Intl,document:{readyState:'loading',addEventListener(){},getElementById:id=>elements[id]}};
  vm.createContext(context);vm.runInContext(source,context);
  context.renderSnapshot({price:5159.51,change:162.9,change_pct:3.26,market_date:'2026-10-20',quote_type:'LIVE',stale:false,quote_at:'2026-10-20T15:52:00+07:00',updated_at:'2026-10-20T15:53:00+07:00',...overrides});
  return elements.ihsgMeta.innerHTML;
}
test('stale deployed quote cannot retain LIVE despite stale=false and new refresh',()=>{
  const html=display({quote_at:'2026-10-20T14:17:00+07:00'});
  assert.match(html,/STALE FEED/);assert.doesNotMatch(html,/LIVE/);assert.match(html,/14:17/);
});
test('fresh observation is identified as snapshot and shows price time',()=>{
  assert.match(display(),/FRESH SNAPSHOT/);assert.match(display(),/Price time:.*15:52/);
});
test('unchanged snapshot ages out as the browser polls',()=>{
  assert.match(display({},16*60*1000),/STALE FEED/);
});
test('invalid, future, timezone-free, or explicitly stale observations fail closed',()=>{
  for(const overrides of [{quote_at:null},{quote_at:'bad'},{quote_at:'2026-10-20T16:00:00+07:00'},{quote_at:'2026-10-20T15:52:00'},{stale:true}]) assert.match(display(overrides),/STALE FEED/);
});
test('last close remains last close',()=>{assert.match(display({quote_type:'LAST_CLOSE'}),/LAST CLOSE/);});
