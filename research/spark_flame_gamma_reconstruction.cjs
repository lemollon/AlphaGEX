// Research reconstruction, never labeled as historical Tradier observations.
// Same dollar-GEX construction and 0..60 DTE band; prior closing quote IV,
// morning OI (previous session's closing OI), and entry-time spot.
const assert=require('node:assert/strict');
const R=.045,Q=.012,YEAR=365*24*60,MIN_T=5/YEAR;
const SOURCE='theta_prior_eod_iv_surface_morning_oi_bs_dte0-60_r045_q012_v3';
function cdf(x){const a=Math.abs(x);if(a>=9)return x>0?1:0;let term=a,sum=a;for(let n=1;n<180;n++){term*=a*a/(2*n+1);sum+=term;if(term<sum*1e-16)break;}const p=.5+Math.exp(-a*a/2)/Math.sqrt(2*Math.PI)*sum;return x>=0?p:1-p;}
function price(cp,s,k,t,v){const d1=(Math.log(s/k)+(R-Q+v*v/2)*t)/(v*Math.sqrt(t)),d2=d1-v*Math.sqrt(t);return cp==='call'?s*Math.exp(-Q*t)*cdf(d1)-k*Math.exp(-R*t)*cdf(d2):k*Math.exp(-R*t)*cdf(-d2)-s*Math.exp(-Q*t)*cdf(-d1);}
function solveIV(cp,s,k,t,mid){if(!(s>0&&k>0&&t>0&&mid>0))return null;let lo=.01,hi=3;if(mid<price(cp,s,k,t,lo)||mid>price(cp,s,k,t,hi))return null;for(let i=0;i<60;i++){const v=(lo+hi)/2;if(price(cp,s,k,t,v)<mid)lo=v;else hi=v;}return (lo+hi)/2;}
function gamma(s,k,t,v){const d1=(Math.log(s/k)+(R-Q+v*v/2)*t)/(v*Math.sqrt(t));return Math.exp(-Q*t-d1*d1/2)/Math.sqrt(2*Math.PI)/(s*v*Math.sqrt(t));}
const days=(a,b)=>(Date.parse(a+'T00:00:00Z')-Date.parse(b+'T00:00:00Z'))/86400000;
const identity=r=>`${String(r.expiration).slice(0,10)}:${Number(r.strike)}:${String(r.right).toLowerCase().startsWith('c')?'call':'put'}`;
function strikeIV(curve,k){
 const hi=curve.findIndex(x=>x.k>=k);
 if(hi>=0&&curve[hi].k===k)return {iv:curve[hi].iv,wing:false};
 if(hi>0){const l=curve[hi-1],h=curve[hi],w=(k-l.k)/(h.k-l.k);return {iv:Math.sqrt(l.iv*l.iv*(1-w)+h.iv*h.iv*w),wing:false};}
 return {iv:curve[hi===0?0:curve.length-1].iv,wing:true};
}
function surfaceIV(surfaces,exp,cp,k,priorDay,closeFor){
 const curve=surfaces.get(exp+':'+cp);
 if(curve?.length)return {...strikeIV(curve,k),term:'same_expiry'};
 const maturity=e=>Math.max((days(e,priorDay)+(closeFor(e)-closeFor(priorDay))/1440)/365,MIN_T);
 const available=[...surfaces.keys()].filter(key=>key.endsWith(':'+cp)).map(key=>({exp:key.slice(0,10),curve:surfaces.get(key)})).sort((a,b)=>a.exp.localeCompare(b.exp));
 if(!available.length)return null;
 const hi=available.findIndex(x=>x.exp>=exp),t=maturity(exp);
 if(hi>0){
  const l=available[hi-1],h=available[hi],tl=maturity(l.exp),th=maturity(h.exp),vl=strikeIV(l.curve,k),vh=strikeIV(h.curve,k),w=(t-tl)/(th-tl);
  return {iv:Math.sqrt((vl.iv*vl.iv*tl*(1-w)+vh.iv*vh.iv*th*w)/t),wing:vl.wing||vh.wing,term:'interpolated'};
 }
 const nearest=available[hi===0?0:available.length-1];
 return {...strikeIV(nearest.curve,k),term:'extrapolated'};
}
function reconstruct({day,priorDay,minute,spot,priorSpot,closingChains,morningOI,closeFor=()=>960}){
 const chains=new Map(closingChains.map(r=>[identity(r),r])),ivs=new Map(),surfaces=new Map();
 let badIV=0;
 for(const r of closingChains){
  if(r.symbol&&r.symbol.toUpperCase()!=='SPY')throw Error('gamma_wrong_symbol');
  const exp=String(r.expiration).slice(0,10),dte=days(exp,day);if(dte<0||dte>60)continue;
  const k=Number(r.strike),bid=Number(r.bid),ask=Number(r.ask),cp=String(r.right).toLowerCase().startsWith('c')?'call':'put';
  const iv=bid>=0&&ask>0&&bid<=ask?solveIV(cp,priorSpot,k,Math.max((days(exp,priorDay)+(closeFor(exp)-closeFor(priorDay))/1440)/365,MIN_T),(bid+ask)/2):null;
  if(iv===null){badIV++;continue;}ivs.set(identity(r),iv);
  const key=exp+':'+cp;if(!surfaces.has(key))surfaces.set(key,[]);surfaces.get(key).push({k,iv});
 }
 for(const rows of surfaces.values())rows.sort((a,b)=>a.k-b.k);
 let call=0,put=0,used=0,positiveOI=0,priorChainMissing=0,ivInterpolated=0,ivWingExtrapolated=0,ivTermInterpolated=0,ivTermExtrapolated=0,unpricedOIContracts=0;
 const termModelledExpiries=new Set();
 for(const r of morningOI){
  const exp=String(r.expiration).slice(0,10),dte=days(exp,day),n=Number(r.open_interest);
  if(dte<0||dte>60||n===0)continue;if(!(n>0&&Number.isFinite(n)))throw Error('gamma_invalid_oi');positiveOI++;
  const k=Number(r.strike),cp=String(r.right).toLowerCase().startsWith('c')?'call':'put',id=identity(r);
  if(!chains.has(id))priorChainMissing++;
  let iv=ivs.get(id);
  if(iv===undefined){
   const estimate=surfaceIV(surfaces,exp,cp,k,priorDay,closeFor);if(!estimate){unpricedOIContracts++;continue;}iv=estimate.iv;
   if(estimate.wing)ivWingExtrapolated++;else ivInterpolated++;
   if(estimate.term==='interpolated'){ivTermInterpolated++;termModelledExpiries.add(exp+':'+cp);}
   if(estimate.term==='extrapolated'){ivTermExtrapolated++;termModelledExpiries.add(exp+':'+cp);}
  }
  const t=Math.max((dte+(closeFor(exp)-minute)/1440)/365,MIN_T),g=gamma(spot,k,t,iv)*n*100*spot*spot*.01;
  if(!Number.isFinite(g))throw Error('gamma_nonfinite');if(cp==='call')call+=g;else put+=g;used++;
 }
 if(!used||!(call>0)||!(put>0))throw Error('gamma_no_reconstructable_chain');
 if(unpricedOIContracts)throw Error('gamma_expiry_surface_missing:'+unpricedOIContracts);
 return {value:call,call,put,net:call-put,source:SOURCE,day,priorDay,minute,spot,priorSpot,used,positiveOI,badIV,priorChainMissing,ivInterpolated,ivWingExtrapolated,ivTermInterpolated,ivTermExtrapolated,termModelledExpiries:[...termModelledExpiries].sort(),unpricedOIContracts,modelled:true};
}
function selfTest(){
 const s=500,k=500,t=30/365,v=.2,p=price('call',s,k,t,v);assert(Math.abs(solveIV('call',s,k,t,p)-v)<1e-8);
 const h=.01,numerical=(price('call',s+h,k,t,v)-2*p+price('call',s-h,k,t,v))/(h*h);assert(Math.abs(numerical-gamma(s,k,t,v))<1e-5);
 const day='2024-06-03',priorDay='2024-05-31',exp='2024-06-28',closingChains=['call','put'].map(right=>({symbol:'SPY',expiration:exp,strike:k,right,bid:price(right,s,k,days(exp,priorDay)/365,v)-.01,ask:price(right,s,k,days(exp,priorDay)/365,v)+.01})),morningOI=closingChains.map(r=>({...r,open_interest:r.right==='call'?200:100}));
 const g=reconstruct({day,priorDay,minute:665,spot:s,priorSpot:s,closingChains,morningOI});assert(g.call>g.put&&g.used===2&&g.priorChainMissing===0);assert(Math.abs(g.call/2-g.put)<1e-5);
 const added={symbol:'SPY',expiration:exp,strike:510,right:'call',open_interest:50};const extra=reconstruct({day,priorDay,minute:665,spot:s,priorSpot:s,closingChains,morningOI:[...morningOI,added]});assert(extra.call>g.call&&extra.ivWingExtrapolated===1&&extra.used===3);
 const surfaces=new Map([['2024-06-10:call',[{k:500,iv:.2}]],['2024-06-24:call',[{k:500,iv:.3}]]]);
 const interpolated=surfaceIV(surfaces,'2024-06-17','call',500,priorDay,()=>960);
 assert.equal(interpolated.term,'interpolated');assert(Math.abs(interpolated.iv**2*17-(.2**2*10+.3**2*24)/2)<1e-10);
 assert.equal(surfaceIV(surfaces,'2024-06-28','call',500,priorDay,()=>960).iv,.3);
 assert.equal(surfaceIV(surfaces,'2024-06-17','put',500,priorDay,()=>960),null);
 const missingExpiry={...added,expiration:'2024-06-21'};const term=reconstruct({day,priorDay,minute:665,spot:s,priorSpot:s,closingChains,morningOI:[...morningOI,missingExpiry]});assert.equal(term.used,3);assert.equal(term.ivTermExtrapolated,1);assert.equal(term.unpricedOIContracts,0);
 console.log(JSON.stringify({gammaReconstructionSelfTest:true,cases:'IV inversion, gamma finite-difference, side decomposition, OI scaling, prior-session timing'}));
}
if(require.main===module)selfTest();
module.exports={SOURCE,reconstruct,selfTest,price,solveIV,gamma,surfaceIV};
