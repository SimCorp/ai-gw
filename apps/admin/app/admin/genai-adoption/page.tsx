'use client';

import { useState, useEffect, useCallback, useId, Fragment } from 'react';
import { getAdminToken } from '../../../lib/adminAuth';

const ADMIN_API = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';
type Tab = 'adoption' | 'productivity' | 'quality';
type Period = 7 | 30 | 90;

// ── Design tokens ──────────────────────────────────────────────────────────────
const C = {
  azure:   '#56b6f5',
  amber:   '#f5b556',
  rose:    '#f47272',
  indigo:  '#7c8cf8',
  emerald: '#34d399',
  bg:      '#0f1729',
  border:  'rgba(255,255,255,0.08)',
  grid:    '#1c2942',
  fg2:     '#9aa6bd',
  display: "'Space Grotesk','Rubik',system-ui,sans-serif",
  mono:    "'Roboto Mono',monospace",
  ui:      "'Rubik',-apple-system,system-ui,sans-serif",
};

const CARD: React.CSSProperties = {
  background: 'linear-gradient(180deg,rgba(255,255,255,0.06),rgba(255,255,255,0.025)),rgba(15,23,41,0.55)',
  backdropFilter: 'blur(20px) saturate(150%)',
  WebkitBackdropFilter: 'blur(20px) saturate(150%)',
  border: `1px solid ${C.border}`,
  borderRadius: 14,
  padding: 18,
  display: 'flex',
  flexDirection: 'column',
  gap: 12,
  minWidth: 0,
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.08),0 18px 40px -24px rgba(0,0,0,0.6)',
};

// ── Mock data ─────────────────────────────────────────────────────────────────
const MOCK = {
  kpis: {
    adoption:     { overall: 76.4, overallDelta: 12.0, active: 389, activeDelta: 24, seatUtil: 81.2, seatUtilDelta: 3.8, commits: 64.2, commitsDelta: 19.0 },
    productivity: { cycleImpact: 13.85, cycleImpactDelta: 2.89, timeSavedHrs: 1840, timeSavedDelta: 18.4, throughputPct: 22.7, throughputDelta: 6.2, deploysPct: 33.4, deploysDelta: 9.1 },
    quality:      { durability: 16.87, durabilityDelta: 2.57, testCovered: 12.85, testCoveredDelta: 2.57, revertRate: 3.4, revertRateDelta: -1.2, reviewImpact: -18.67, reviewImpactDelta: -1.97 },
  },
  tools: [
    { id: 'copilot', name: 'GitHub Copilot', seats: 320, activeWeek: 247, impact: 86.5, adoption: 73.5, codeBlend: 68.5, deltas: { impact: 2.56, adoption: -4.5, codeBlend: -1.5 }, sparkline: [42,48,51,49,55,58,62,67,71,73,72,73], color: C.indigo },
    { id: 'claude',  name: 'Claude Code',    seats: 180, activeWeek: 142, impact: 93.5, adoption: 80.3, codeBlend: 48.4, deltas: { impact: 2.79, adoption:  1.9, codeBlend: -2.19 }, sparkline: [22,28,34,41,48,56,62,68,74,77,79,80], color: C.azure  },
  ],
  monthLabels: ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep'],
  weekLabels:  ['W1','W2','W3','W4','W5','W6','W7','W8','W9','W10','W11','W12'],
  adoptionTrend: { copilot: [38,44,51,56,62,66,69,72,73.5], claude: [12,22,34,48,58,67,74,78,80.3] },
  cycleTime:     { actual: [7.8,7.1,6.4,6.8,4.2,6.9,7.3,7.4,6.8], trend: [7.8,7.0,6.3,5.6,4.8,4.1,3.4,2.7,2.0] },
  cycleAvg: '6d 8h',
  cyclePerTool: [
    { label: 'Copilot',     value: 7.2, sub: '12% slower than avg', color: C.indigo },
    { label: 'Claude Code', value: 3.1, sub: '52% faster than avg', color: C.azure  },
    { label: 'Non-GenAI',   value: 9.3, sub: '50% slower than avg', color: C.rose   },
  ],
  throughput: { groups: ['May','Jun','Jul','Aug','Sep'], series: [{ name:'GenAI-assisted', color:C.azure,  data:[184,212,247,281,318] },{ name:'Non-GenAI', color:C.indigo, data:[196,191,188,172,164] }] },
  deploys:    { groups: ['May','Jun','Jul','Aug','Sep'], series: [{ name:'Deploys',   color:C.azure, data:[42,48,56,61,68] },{ name:'Rollbacks', color:C.rose,  data:[4,5,3,4,2] }] },
  durability: { months: ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug'], gen:[16,12,8,10,58,41,36,34], nonGen:[44,47,52,62,18,12,14,22] },
  heatTeams: ['Platform','Delivery','Product','Data & Insights','Core AI','Research','Security','Mobile'],
  heatmap: [
    [78,82,84,86,88,89,90,90,91,90,91,91],
    [72,75,80,82,84,85,86,87,88,87,88,88],
    [62,65,70,74,78,80,82,83,84,84,84,84],
    [55,58,62,68,72,74,76,77,78,79,79,79],
    [48,52,58,62,66,70,72,73,74,75,75,76],
    [40,44,50,54,58,60,63,65,67,67,68,68],
    [32,36,42,46,50,52,55,57,59,60,61,61],
    [22,28,34,38,42,46,48,50,52,53,53,54],
  ],
  toolMix: [{ label:'Copilot only', value:247, pct:63, color:C.indigo },{ label:'Claude only', value:86, pct:22, color:C.azure },{ label:'Both tools', value:56, pct:15, color:C.emerald }],
  dora: [
    { label:'Coding time',    value:'2.3', unit:'DAYS',  delta:'+2.88%', up:true,  sub:'First commit → last commit', spark:[2.6,2.5,2.4,2.4,2.3,2.3,2.3] },
    { label:'Pickup time',    value:'3.7', unit:'HOURS', delta:'−20.1%', up:false, sub:'Last commit → first review',  spark:[5.2,4.6,4.2,4.0,3.9,3.7,3.7] },
    { label:'Review time',    value:'1.8', unit:'DAYS',  delta:'−18.2%', up:false, sub:'First review → merge',        spark:[2.3,2.1,2.0,1.9,1.9,1.8,1.8] },
    { label:'Time to deploy', value:'4.1', unit:'HOURS', delta:'−12.5%', up:false, sub:'Merge → production',          spark:[4.8,4.6,4.4,4.3,4.2,4.1,4.1] },
  ],
  qualityContribs: [
    { name:'Delivery Group', cycle:'4.5d', color:C.azure  },
    { name:'Product Group',  cycle:'5.7d', color:C.amber  },
    { name:'Core AI Group',  cycle:'6.8d', color:C.indigo },
    { name:'Research Core',  cycle:'3.7d', color:C.rose   },
  ],
  revertByTool: [
    { label:'Copilot',     value:3.8, sub:'+0.6 vs baseline', color:C.indigo },
    { label:'Claude Code', value:2.1, sub:'−1.7 vs baseline', color:C.azure  },
    { label:'Non-GenAI',   value:4.2, sub:'baseline',         color:C.rose   },
  ],
  mockTeams: [
    { id:'platform', name:'Platform Group', icon:'PL', size:64, adoption:91, productivity:18.2 },
    { id:'delivery', name:'Delivery Group', icon:'DL', size:52, adoption:88, productivity:16.4 },
    { id:'product',  name:'Product Group',  icon:'PR', size:78, adoption:84, productivity:12.1 },
    { id:'data',     name:'Data & Insights',icon:'DI', size:41, adoption:79, productivity: 9.8 },
    { id:'core-ai',  name:'Core AI Group',  icon:'AI', size:38, adoption:76, productivity:14.6 },
    { id:'research', name:'Research Core',  icon:'RC', size:29, adoption:68, productivity: 7.4 },
  ],
};

// ── TypeScript interfaces ──────────────────────────────────────────────────────
interface AdoptionSummary  { period_days:number; total_licensed_developers:number; active_users:number; adoption_rate_pct:number; frequency_buckets:{rare:number;occasional:number;regular:number} }
interface AdoptionByTeam   { team_id:string; team_name:string; licensed_count:number; active_users:number; adoption_rate_pct:number; frequency_buckets:{rare:number;occasional:number;regular:number} }
interface CohortStats      { avg_quality_score:number|null; avg_inter_request_s:number|null; avg_turn_count:number|null; avg_tool_invocations:number|null; session_count:number }
interface ProductivitySummary { high_adoption:CohortStats; low_adoption:CohortStats }
interface ProductivityByTeam  { team_id:string; team_name:string; avg_quality_score:number|null; avg_inter_request_s:number|null; avg_turn_count:number|null; session_count:number }
interface QualityCohort    { avg_error_rate_pct:number|null; avg_retry_rate_pct:number|null; cache_hit_rate_pct:number|null }
interface QualitySummary   { high_adoption:QualityCohort; low_adoption:QualityCohort }
interface QualityByTeam    { team_id:string; team_name:string; avg_error_rate_pct:number|null; avg_retry_rate_pct:number|null; cache_hit_rate_pct:number|null; session_count:number; high_error_flag:boolean }
interface Insights         { summary:string; highlights:string[]; recommendations:string[]; risks:string[] }
interface InsightsResponse { period_days:number; insights:Insights }

// ── API helpers ────────────────────────────────────────────────────────────────
function authHeader(): HeadersInit { const t = getAdminToken(); return t ? { Authorization:`Bearer ${t}` } : {}; }
async function apiFetch<T>(path:string):Promise<T> {
  const res = await fetch(`${ADMIN_API}${path}`,{headers:authHeader()});
  if(!res.ok) throw new Error(`${res.status}`);
  return res.json();
}
function fmt(v:number|null|undefined,d=1):string { return v==null?'—':v.toFixed(d); }

// ── SVG Charts ────────────────────────────────────────────────────────────────

function Sparkline({data,color=C.azure,w=100,h=28,fill=true,strokeWidth=1.5}:{data:number[];color?:string;w?:number;h?:number;fill?:boolean;strokeWidth?:number}) {
  const id = useId();
  const min=Math.min(...data), max=Math.max(...data), range=max-min||1;
  const step=w/(data.length-1);
  const pts=data.map((v,i)=>`${(i*step).toFixed(1)},${(h-((v-min)/range)*(h-4)-2).toFixed(1)}`).join(' ');
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{display:'block'}}>
      {fill&&(<><defs><linearGradient id={`sp${id}`} x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity="0.30"/><stop offset="100%" stopColor={color} stopOpacity="0.02"/></linearGradient></defs><path d={`M0,${h} L${pts} L${w},${h} Z`} fill={`url(#sp${id})`}/></>)}
      <polyline points={pts} fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

interface LineSeries { name:string; color:string; data:number[]; dashed?:boolean }
function LineChart({series,labels,height=220,yMax,yFormat=(v:number)=>String(v),unit='',showArea=true}:{series:LineSeries[];labels:string[];height?:number;yMax?:number;yFormat?:(v:number)=>string;unit?:string;showArea?:boolean}) {
  const id=useId();
  const [hover,setHover]=useState<number|null>(null);
  const W=720,H=height,padL=40,padR=12,padT=12,padB=26;
  const innerW=W-padL-padR, innerH=H-padT-padB, n=labels.length;
  const max=yMax??Math.max(...series.flatMap(s=>s.data));
  const ticks=Array.from({length:6},(_,i)=>(max*i)/5);
  const xAt=(i:number)=>padL+(n===1?innerW/2:(i*innerW)/(n-1));
  const yAt=(v:number)=>padT+innerH-(v/max)*innerH;
  return (
    <div style={{position:'relative'}}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{display:'block',overflow:'visible'}} onMouseLeave={()=>setHover(null)}>
        <defs>{series.map((s,i)=><linearGradient key={i} id={`ln${id}-${i}`} x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor={s.color} stopOpacity="0.28"/><stop offset="100%" stopColor={s.color} stopOpacity="0"/></linearGradient>)}</defs>
        {ticks.map((v,i)=><g key={i}><line x1={padL} x2={W-padR} y1={yAt(v)} y2={yAt(v)} stroke={C.grid} strokeWidth={0.5}/><text x={padL-6} y={yAt(v)+3} textAnchor="end" style={{fill:C.fg2,fontSize:10,fontFamily:C.mono}}>{yFormat(v)}</text></g>)}
        {series.map((s,idx)=>{
          const pts=s.data.map((v,i)=>`${xAt(i)},${yAt(v)}`).join(' ');
          const area=`M${xAt(0)},${yAt(0)} L${pts} L${xAt(s.data.length-1)},${yAt(0)} Z`;
          return (<g key={idx}>
            {showArea&&!s.dashed&&<path d={area} fill={`url(#ln${id}-${idx})`}/>}
            <polyline points={pts} fill="none" stroke={s.color} strokeWidth={2} strokeDasharray={s.dashed?'4 4':undefined} strokeLinecap="round" strokeLinejoin="round"/>
            {s.data.map((v,i)=><circle key={i} cx={xAt(i)} cy={yAt(v)} r={hover===i?5:3} fill={s.color} stroke={C.bg} strokeWidth={1.5}/>)}
          </g>);
        })}
        {labels.map((_,i)=><rect key={i} x={xAt(i)-innerW/(n*2)} y={padT} width={innerW/n} height={innerH} fill="transparent" onMouseEnter={()=>setHover(i)}/>)}
        {hover!==null&&<line x1={xAt(hover)} x2={xAt(hover)} y1={padT} y2={padT+innerH} stroke={C.indigo} strokeWidth={1} strokeDasharray="3 3"/>}
        {labels.map((l,i)=>{const skip=Math.ceil(n/12);if(i%skip!==0&&i!==n-1)return null;return<text key={i} x={xAt(i)} y={H-6} textAnchor="middle" style={{fill:C.fg2,fontSize:10,fontFamily:C.mono}}>{l}</text>;})}
      </svg>
      {hover!==null&&(
        <div style={{position:'absolute',left:`${(xAt(hover)/W)*100}%`,top:0,transform:'translateX(-50%)',pointerEvents:'none',background:'rgba(10,17,31,0.95)',border:`1px solid ${C.border}`,borderRadius:8,padding:'6px 10px',fontSize:12,whiteSpace:'nowrap',boxShadow:'0 4px 16px rgba(0,0,0,0.4)',zIndex:10}}>
          <div style={{color:C.fg2,marginBottom:4,fontSize:11}}>{labels[hover]}</div>
          {series.map((s,i)=><div key={i} style={{display:'flex',alignItems:'center',gap:6}}><span style={{width:8,height:8,borderRadius:2,background:s.color,flexShrink:0,display:'inline-block'}}/><span style={{color:C.fg2}}>{s.name}</span><span style={{marginLeft:'auto',color:'#fff',fontWeight:700,fontFamily:C.mono}}>{yFormat(s.data[hover!])}{unit}</span></div>)}
        </div>
      )}
    </div>
  );
}

function BarChart({data,height=220,yMax,yFormat=(v:number)=>String(v),refLine}:{data:{label:string;value:number;color?:string;sub?:string}[];height?:number;yMax?:number;yFormat?:(v:number)=>string;refLine?:{value:number;label:string}}) {
  const [hover,setHover]=useState<number|null>(null);
  const W=720,H=height,padL=40,padR=12,padT=16,padB=60;
  const innerW=W-padL-padR, innerH=H-padT-padB, n=data.length;
  const max=yMax??Math.max(...data.map(d=>d.value),refLine?.value??0)*1.15;
  const ticks=Array.from({length:6},(_,i)=>(max*i)/5);
  const slot=innerW/n, barW=Math.min(slot*0.55,64);
  const xAt=(i:number)=>padL+slot*i+(slot-barW)/2;
  const yAt=(v:number)=>padT+innerH-(v/max)*innerH;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{display:'block',overflow:'visible'}}>
      {ticks.map((v,i)=><g key={i}><line x1={padL} x2={W-padR} y1={yAt(v)} y2={yAt(v)} stroke={C.grid} strokeWidth={0.5}/><text x={padL-6} y={yAt(v)+3} textAnchor="end" style={{fill:C.fg2,fontSize:10,fontFamily:C.mono}}>{yFormat(v)}</text></g>)}
      {refLine&&<g><line x1={padL} x2={W-padR} y1={yAt(refLine.value)} y2={yAt(refLine.value)} stroke={C.amber} strokeWidth={1.5} strokeDasharray="5 4"/><rect x={W-padR-96} y={yAt(refLine.value)-11} width="92" height="22" rx="11" fill="rgba(245,181,86,0.14)" stroke={C.amber} strokeWidth={1}/><text x={W-padR-50} y={yAt(refLine.value)+4} textAnchor="middle" style={{fill:C.amber,fontSize:10,fontWeight:700,fontFamily:C.mono}}>{refLine.label}</text></g>}
      {data.map((d,i)=>{const color=d.color??C.indigo;return(<g key={i} onMouseEnter={()=>setHover(i)} onMouseLeave={()=>setHover(null)} style={{cursor:'pointer'}}>
        <rect x={xAt(i)} y={yAt(d.value)} width={barW} height={padT+innerH-yAt(d.value)} rx={3} fill={color} opacity={hover===i?1:0.9}/>
        <text x={xAt(i)+barW/2} y={yAt(d.value)-8} textAnchor="middle" style={{fill:'#fff',fontSize:11,fontWeight:700,fontFamily:C.display}}>{yFormat(d.value)}</text>
        <text x={xAt(i)+barW/2} y={H-padB+18} textAnchor="middle" style={{fill:'#fff',fontSize:11,fontWeight:600}}>{d.label}</text>
        {d.sub&&<text x={xAt(i)+barW/2} y={H-padB+34} textAnchor="middle" style={{fill:C.fg2,fontSize:9}}>{d.sub}</text>}
      </g>);})}
    </svg>
  );
}

function Gauge({value,max=100,color=C.azure,size=140,thickness=14,label}:{value:number;max?:number;color?:string;size?:number;thickness?:number;label?:string}) {
  const r=(size-thickness)/2, cx=size/2, cy=size/2+4;
  const start=-Math.PI, end=0;
  const angle=start+(value/max)*(end-start);
  const polar=(a:number):[number,number]=>[cx+r*Math.cos(a),cy+r*Math.sin(a)];
  const [sx,sy]=polar(start),[ex,ey]=polar(end),[vx,vy]=polar(angle);
  const largeArc=angle-start>Math.PI?1:0;
  const vbH=cy+thickness+(label?22:4);
  return (
    <svg viewBox={`0 0 ${size} ${vbH}`} width="100%" style={{display:'block'}}>
      <path d={`M ${sx} ${sy} A ${r} ${r} 0 0 1 ${ex} ${ey}`} stroke="rgba(255,255,255,0.08)" strokeWidth={thickness} fill="none" strokeLinecap="round"/>
      <path d={`M ${sx} ${sy} A ${r} ${r} 0 ${largeArc} 1 ${vx} ${vy}`} stroke={color} strokeWidth={thickness} fill="none" strokeLinecap="round"/>
      <text x={cx} y={cy-4} textAnchor="middle" style={{fill:'#fff',fontSize:size*0.22,fontWeight:700,fontFamily:C.display}}>{Math.round(value)}%</text>
      {label&&<text x={cx} y={cy+thickness+14} textAnchor="middle" style={{fill:C.fg2,fontSize:10,fontFamily:C.mono}}>{label}</text>}
    </svg>
  );
}

function Donut({segments,size=120,thickness=16,centerLabel,centerValue}:{segments:{value:number;color:string}[];size?:number;thickness?:number;centerLabel?:string;centerValue?:string}) {
  const r=(size-thickness)/2, cx=size/2, cy=size/2;
  const total=segments.reduce((a,s)=>a+s.value,0);
  let acc=0;
  return (
    <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} style={{display:'block'}}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={thickness}/>
      {segments.map((s,i)=>{const len=(s.value/total)*2*Math.PI*r, off=-((acc/total)*2*Math.PI*r);acc+=s.value;return<circle key={i} cx={cx} cy={cy} r={r} fill="none" stroke={s.color} strokeWidth={thickness} strokeDasharray={`${len} ${2*Math.PI*r}`} strokeDashoffset={off} transform={`rotate(-90 ${cx} ${cy})`} strokeLinecap="butt"/>;})}
      {centerValue&&<text x={cx} y={cy-2} textAnchor="middle" style={{fill:'#fff',fontSize:size*0.21,fontWeight:700,fontFamily:C.display}}>{centerValue}</text>}
      {centerLabel&&<text x={cx} y={cy+14} textAnchor="middle" style={{fill:C.fg2,fontSize:10}}>{centerLabel}</text>}
    </svg>
  );
}

function GroupedBars({groups,series,height=180}:{groups:string[];series:{name:string;color:string;data:number[]}[];height?:number}) {
  const W=720,H=height,padL=30,padR=8,padT=14,padB=28;
  const innerW=W-padL-padR, innerH=H-padT-padB;
  const max=Math.max(...series.flatMap(s=>s.data))*1.18;
  const slot=innerW/groups.length, groupW=Math.min(slot*0.7,60), barW=groupW/series.length-2;
  const yAt=(v:number)=>padT+innerH-(v/max)*innerH;
  const xGroup=(i:number)=>padL+slot*i+(slot-groupW)/2;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{display:'block'}}>
      {[0,.25,.5,.75,1].map((p,i)=><line key={i} x1={padL} x2={W-padR} y1={padT+innerH*(1-p)} y2={padT+innerH*(1-p)} stroke={C.grid} strokeWidth={0.5}/>)}
      {groups.map((g,gi)=><g key={gi}>{series.map((s,si)=><rect key={si} x={xGroup(gi)+si*(barW+2)} y={yAt(s.data[gi])} width={barW} height={padT+innerH-yAt(s.data[gi])} rx={2} fill={s.color}/>)}<text x={xGroup(gi)+groupW/2} y={H-8} textAnchor="middle" style={{fill:C.fg2,fontSize:10,fontFamily:C.mono}}>{g}</text></g>)}
    </svg>
  );
}

function Bullet({value,target,max,color=C.azure}:{value:number;target:number;max:number;color?:string}) {
  return (
    <div style={{position:'relative',height:8,background:'rgba(255,255,255,0.05)',borderRadius:18,marginTop:4}}>
      <div style={{width:`${(value/max)*100}%`,height:'100%',background:color,borderRadius:18}}/>
      <div style={{position:'absolute',left:`${(target/max)*100}%`,top:-2,bottom:-2,width:2,background:'#fff',borderRadius:1}} title={`target ${target}`}/>
    </div>
  );
}

// ── UI primitives ──────────────────────────────────────────────────────────────

function CardWrap({children,style}:{children:React.ReactNode;style?:React.CSSProperties}) {
  return <div style={{...CARD,...style}}>{children}</div>;
}

function CardHead({title,sub,help,right}:{title:string;sub?:string;help?:string;right?:React.ReactNode}) {
  return (
    <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',gap:12}}>
      <div>
        <div style={{fontSize:14,fontWeight:600,color:'#fff',fontFamily:C.ui}}>{title}</div>
        {sub&&<div style={{fontSize:11,color:C.fg2,marginTop:2}}>{sub}</div>}
      </div>
      <div style={{display:'flex',alignItems:'center',gap:8,flexShrink:0}}>
        {right}
        {help&&<span title={help} style={{color:C.fg2,fontSize:13,cursor:'help',opacity:.6}}>?</span>}
      </div>
    </div>
  );
}

function DeltaChip({value,inverted=false,suffix='%'}:{value:number;inverted?:boolean;suffix?:string}) {
  const pos=inverted?value<=0:value>=0;
  return (
    <span style={{fontSize:11,fontWeight:700,padding:'2px 6px',borderRadius:4,background:pos?'rgba(86,182,245,0.12)':'rgba(244,114,114,0.12)',color:pos?C.azure:C.rose}}>
      {pos?'▲':'▼'} {Math.abs(value)}{suffix}
    </span>
  );
}

function BigNum({value,unit,color}:{value:string|number;unit?:string;color?:string}) {
  return (
    <div style={{display:'flex',alignItems:'baseline',gap:5}}>
      <span style={{fontSize:32,fontWeight:700,color:color??'#fff',fontFamily:C.display,lineHeight:1}}>{value}</span>
      {unit&&<span style={{fontSize:13,fontWeight:600,color:C.fg2,textTransform:'uppercase',letterSpacing:'.25px'}}>{unit}</span>}
    </div>
  );
}

function Legend({items}:{items:{label:string;color:string}[]}) {
  return (
    <div style={{display:'flex',gap:14,flexWrap:'wrap'}}>
      {items.map(it=><div key={it.label} style={{display:'flex',alignItems:'center',gap:6,fontSize:12,color:C.fg2}}><span style={{width:16,height:2,background:it.color,borderRadius:1,display:'inline-block'}}/>{it.label}</div>)}
    </div>
  );
}

function SegControl({options,value,onChange}:{options:{value:string;label:string}[];value:string;onChange:(v:string)=>void}) {
  return (
    <div style={{display:'flex',background:'rgba(255,255,255,0.04)',borderRadius:8,padding:2,gap:2}}>
      {options.map(o=><button key={o.value} onClick={()=>onChange(o.value)} style={{padding:'4px 10px',fontSize:11,fontWeight:600,borderRadius:6,border:'none',cursor:'pointer',fontFamily:C.ui,background:value===o.value?'rgba(86,182,245,0.18)':'transparent',color:value===o.value?C.azure:C.fg2,transition:'all 120ms'}}>{o.label}</button>)}
    </div>
  );
}

function HeatCell({v}:{v:number}) {
  const intensity=Math.max(0.06,v/100);
  return <div style={{padding:'4px 2px',background:`rgba(86,182,245,${intensity*0.95})`,color:v>60?'rgba(10,17,31,0.85)':'rgba(255,255,255,0.75)',fontSize:9,fontWeight:600,textAlign:'center',borderRadius:3,fontFamily:C.mono}}>{v}</div>;
}

function BarTrack({value,color=C.azure,height=5}:{value:number;color?:string;height?:number}) {
  return <div style={{height,background:'rgba(255,255,255,0.06)',borderRadius:3,overflow:'hidden'}}><div style={{width:`${value}%`,height:'100%',background:color,borderRadius:3}}/></div>;
}

type ToolTileData = typeof MOCK.tools[number];
function ToolTile({tool,chartType}:{tool:ToolTileData;chartType:string}) {
  return (
    <div style={{background:'rgba(255,255,255,0.03)',border:`1px solid rgba(255,255,255,0.06)`,borderRadius:12,padding:16,display:'flex',flexDirection:'column',gap:14}}>
      <div style={{display:'flex',alignItems:'center',gap:10}}>
        <div style={{width:32,height:32,borderRadius:8,background:`${tool.color}20`,display:'flex',alignItems:'center',justifyContent:'center',fontSize:10,fontWeight:700,color:tool.color}}>{tool.name.slice(0,2).toUpperCase()}</div>
        <div style={{flex:1}}>
          <div style={{fontSize:14,fontWeight:600,color:'#fff'}}>{tool.name}</div>
          <div style={{fontSize:11,color:C.fg2,marginTop:2,textTransform:'uppercase',letterSpacing:'.04em'}}>{tool.activeWeek} / {tool.seats} seats · 7d</div>
        </div>
        <DeltaChip value={tool.deltas.adoption}/>
      </div>
      {chartType==='sparkline'&&(
        <div><Sparkline data={tool.sparkline} color={tool.color} w={300} h={48} strokeWidth={2}/>
        <div style={{display:'flex',justifyContent:'space-between',fontSize:10,color:C.fg2,marginTop:4}}><span>9 weeks ago</span><span>today</span></div></div>
      )}
      {chartType==='gauges'&&(
        <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:8}}>
          <Gauge value={tool.impact}    color={C.azure}    size={110} thickness={11} label="IMPACT"/>
          <Gauge value={tool.adoption}  color={tool.color} size={110} thickness={11} label="ADOPTION"/>
          <Gauge value={tool.codeBlend} color={C.amber}    size={110} thickness={11} label="CODE BLEND"/>
        </div>
      )}
      {chartType==='bars'&&(
        <div style={{display:'flex',flexDirection:'column',gap:10}}>
          {[{l:'Impact',v:tool.impact,d:tool.deltas.impact,c:C.azure},{l:'Adoption',v:tool.adoption,d:tool.deltas.adoption,c:tool.color},{l:'Code blend',v:tool.codeBlend,d:tool.deltas.codeBlend,c:C.amber}].map(s=>(
            <div key={s.l}>
              <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:5}}>
                <span style={{fontSize:12,color:C.fg2}}>{s.l}</span>
                <div style={{display:'flex',alignItems:'center',gap:8}}><span style={{fontSize:14,fontWeight:700,color:'#fff',fontFamily:C.display}}>{s.v}%</span><DeltaChip value={s.d}/></div>
              </div>
              <BarTrack value={s.v} color={s.c} height={6}/>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── AI Insights Panel ─────────────────────────────────────────────────────────

function InsightsPanel({period}:{period:Period}) {
  const [data,setData]=useState<InsightsResponse|null>(null);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState('');
  const [open,setOpen]=useState(true);
  const analyze=useCallback(async()=>{
    setLoading(true);setError('');
    try{const r=await apiFetch<InsightsResponse>(`/genai-adoption/insights?period_days=${period}`);setData(r);}
    catch{setError('AI analysis unavailable.');}
    finally{setLoading(false);}
  },[period]);
  const ins=data?.insights;
  return (
    <div style={{border:`1px solid rgba(86,182,245,0.25)`,borderRadius:12,overflow:'hidden',marginBottom:4}}>
      <div onClick={()=>setOpen(o=>!o)} style={{display:'flex',alignItems:'center',gap:10,padding:'12px 16px',background:'rgba(86,182,245,0.07)',cursor:'pointer',userSelect:'none'}}>
        <span style={{fontSize:16,color:C.azure}}>✦</span>
        <span style={{fontWeight:700,fontSize:13,color:C.azure,flex:1,fontFamily:C.ui}}>AI Analysis — last {period} days</span>
        {!loading&&<button onClick={e=>{e.stopPropagation();analyze();}} style={{padding:'4px 12px',borderRadius:6,background:'rgba(86,182,245,0.15)',border:`1px solid rgba(86,182,245,0.35)`,color:C.azure,fontFamily:C.ui,fontSize:12,fontWeight:600,cursor:'pointer'}}>{data?'Refresh':'Analyse'}</button>}
        {loading&&<span style={{fontSize:12,color:C.azure}}>Analysing…</span>}
        <span style={{color:C.fg2,fontSize:12}}>{open?'▲':'▼'}</span>
      </div>
      {open&&(
        <div style={{padding:'16px 20px',background:'rgba(15,23,41,0.55)'}}>
          {error&&<ErrorBox msg={error}/>}
          {!data&&!loading&&!error&&<div style={{fontSize:13,color:C.fg2,padding:'8px 0'}}>Click <strong style={{color:C.azure}}>Analyse</strong> to generate an AI-powered summary of current adoption health, anomalies, and recommendations.</div>}
          {ins&&(
            <div style={{display:'flex',flexDirection:'column',gap:16}}>
              <p style={{margin:0,fontSize:13,lineHeight:1.7,color:'#fff'}}>{ins.summary}</p>
              <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:12}}>
                <InsightBlock title="Key Findings" items={ins.highlights} color={C.azure} icon="◆"/>
                <InsightBlock title="Recommendations" items={ins.recommendations} color={C.emerald} icon="→"/>
                <InsightBlock title="Watch Items" items={ins.risks} color={C.amber} icon="⚠"/>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function InsightBlock({title,items,color,icon}:{title:string;items:string[];color:string;icon:string}) {
  if(!items.length) return null;
  return (
    <div style={{background:`${color}0d`,border:`1px solid ${color}33`,borderTop:`2px solid ${color}`,borderRadius:8,padding:'12px 14px'}}>
      <div style={{fontWeight:700,fontSize:11,letterSpacing:'.06em',textTransform:'uppercase',color,marginBottom:10}}>{title}</div>
      <ul style={{margin:0,padding:0,listStyle:'none',display:'flex',flexDirection:'column',gap:8}}>
        {items.map((item,i)=><li key={i} style={{display:'flex',gap:8,fontSize:12,lineHeight:1.5,color:'#e8eaf0'}}><span style={{color,flexShrink:0,marginTop:1}}>{icon}</span><span>{item}</span></li>)}
      </ul>
    </div>
  );
}

// ── Adoption Tab ──────────────────────────────────────────────────────────────

function AdoptionTab({period}:{period:Period}) {
  const [summary,setSummary]=useState<AdoptionSummary|null>(null);
  const [teams,setTeams]=useState<AdoptionByTeam[]>([]);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [chartType,setChartType]=useState('bars');
  const km=MOCK.kpis.adoption;

  const load=useCallback(async()=>{
    setLoading(true);setError('');
    try{
      const [s,t]=await Promise.all([
        apiFetch<AdoptionSummary>(`/genai-adoption/adoption/summary?period_days=${period}`),
        apiFetch<AdoptionByTeam[]>(`/genai-adoption/adoption/by-team?period_days=${period}`),
      ]);
      setSummary(s);setTeams(t);
    }catch{setError('Failed to load adoption data');}
    finally{setLoading(false);}
  },[period]);
  useEffect(()=>{load();},[load]);

  const adoptionPct=summary?.adoption_rate_pct??km.overall;
  const activeDev=summary?.active_users??km.active;
  const totalDev=summary?.total_licensed_developers??487;

  const trendSeries=[
    {name:'Copilot',    color:C.indigo, data:MOCK.adoptionTrend.copilot},
    {name:'Claude Code',color:C.azure,  data:MOCK.adoptionTrend.claude},
  ];

  const displayTeams = teams.length > 0
    ? teams.slice(0,6).map(t=>({id:t.team_id,name:t.team_name,icon:t.team_name.slice(0,2).toUpperCase(),size:t.licensed_count,adoption:t.adoption_rate_pct,productivity:0}))
    : MOCK.mockTeams;

  if(loading) return <Spinner/>;
  if(error)   return <ErrorBox msg={`Failed to load adoption data: ${error} — showing illustrative data below`}/>;
  return <AdoptionMockContent km={km} activeDev={activeDev} totalDev={totalDev} adoptionPct={adoptionPct} trendSeries={trendSeries} displayTeams={displayTeams} chartType={chartType} setChartType={setChartType}/>;
}

function AdoptionMockContent({km,activeDev,totalDev,adoptionPct,trendSeries,displayTeams,chartType,setChartType}:{
  km:typeof MOCK.kpis.adoption; activeDev:number; totalDev:number; adoptionPct:number;
  trendSeries:{name:string;color:string;data:number[]}[];
  displayTeams:{id:string;name:string;icon:string;size:number;adoption:number;productivity:number}[];
  chartType:string; setChartType:(v:string)=>void;
}) {
  return (
    <div style={{display:'flex',flexDirection:'column',gap:16}}>
      {/* KPI row */}
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:16}}>
        <CardWrap>
          <CardHead title="Overall adoption" sub="Developers using GenAI weekly" help="% of developers with ≥1 GenAI interaction in the last 7 days"/>
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:12}}>
            <div style={{width:120,flexShrink:0}}><Gauge value={adoptionPct} color={C.azure} size={120} thickness={14}/></div>
            <div style={{textAlign:'right'}}><DeltaChip value={km.overallDelta}/><div style={{fontSize:10,color:C.fg2,marginTop:4,textTransform:'uppercase',letterSpacing:'.04em'}}>from last month</div></div>
          </div>
        </CardWrap>
        <CardWrap>
          <CardHead title="Active developers" sub="Weekly active GenAI users"/>
          <BigNum value={activeDev} color={C.azure}/>
          <div style={{display:'flex',alignItems:'center',gap:8}}><DeltaChip value={km.activeDelta} suffix=""/><span style={{fontSize:11,color:C.fg2}}>of {totalDev} total developers</span></div>
        </CardWrap>
        <CardWrap>
          <CardHead title="Seat utilization" sub="Licensed seats actively used" help="Active 7d users / total licensed seats"/>
          <BigNum value={`${km.seatUtil}%`}/>
          <Bullet value={km.seatUtil} target={85} max={100} color={C.amber}/>
          <div style={{display:'flex',alignItems:'center',gap:8}}><DeltaChip value={km.seatUtilDelta}/><span style={{fontSize:11,color:C.fg2}}>target 85%</span></div>
        </CardWrap>
        <CardWrap>
          <CardHead title="Code commits" sub="Commits with GenAI suggestions" help="% of commits in last 30d touched by a GenAI suggestion"/>
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:12}}>
            <Donut size={110} thickness={16} centerValue={`${km.commits}%`} centerLabel="OF COMMITS"
              segments={[{value:km.commits,color:C.indigo},{value:100-km.commits,color:'rgba(255,255,255,0.04)'}]}/>
            <div style={{textAlign:'right'}}><DeltaChip value={km.commitsDelta}/><div style={{fontSize:10,color:C.fg2,marginTop:4,textTransform:'uppercase',letterSpacing:'.04em'}}>from last month</div></div>
          </div>
        </CardWrap>
      </div>

      {/* Per-tool breakdown */}
      <CardWrap>
        <CardHead title="By GenAI tool" sub="Adoption & impact per assistant · last 30 days"
          right={<SegControl options={[{value:'bars',label:'Bars'},{value:'gauges',label:'Gauges'},{value:'sparkline',label:'Trend'}]} value={chartType} onChange={setChartType}/>}/>
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
          {MOCK.tools.map(t=><ToolTile key={t.id} tool={t} chartType={chartType}/>)}
        </div>
      </CardWrap>

      {/* Adoption trend + Team list */}
      <div style={{display:'grid',gridTemplateColumns:'2fr 1fr',gap:16}}>
        <CardWrap>
          <CardHead title="Adoption over time" sub="% of developers active per week, by tool"
            right={<Legend items={[{label:'Copilot',color:C.indigo},{label:'Claude Code',color:C.azure}]}/>}/>
          <LineChart series={trendSeries} labels={MOCK.monthLabels} height={240} yMax={100} yFormat={v=>`${v}`} unit="%"/>
        </CardWrap>
        <CardWrap>
          <CardHead title="By team" sub="Adoption ranked · top 6"/>
          <div style={{display:'flex',flexDirection:'column'}}>
            {displayTeams.slice(0,6).map((t,i)=>(
              <div key={t.id} style={{display:'grid',gridTemplateColumns:'28px 1fr 80px',gap:10,alignItems:'center',padding:'8px 0',borderBottom:`1px solid rgba(255,255,255,0.04)`}}>
                <div style={{fontSize:11,fontWeight:700,color:C.fg2,fontFamily:C.mono}}>{String(i+1).padStart(2,'0')}</div>
                <div style={{display:'flex',alignItems:'center',gap:8}}>
                  <div style={{width:26,height:26,borderRadius:6,background:'rgba(124,140,248,0.15)',display:'flex',alignItems:'center',justifyContent:'center',fontSize:9,fontWeight:700,color:C.indigo}}>{t.icon}</div>
                  <div><div style={{fontSize:13,fontWeight:600,color:'#fff'}}>{t.name}</div><div style={{fontSize:10,color:C.fg2,textTransform:'uppercase',letterSpacing:'.04em'}}>{t.size} DEVS</div></div>
                </div>
                <div><div style={{fontSize:14,fontWeight:700,color:'#fff',fontFamily:C.display,textAlign:'right'}}>{t.adoption}%</div><BarTrack value={t.adoption} color={C.azure} height={4}/></div>
              </div>
            ))}
          </div>
        </CardWrap>
      </div>

      {/* Heatmap + Tool mix */}
      <div style={{display:'grid',gridTemplateColumns:'2fr 1fr',gap:16}}>
        <CardWrap>
          <CardHead title="Adoption heatmap" sub="Team × week · last 12 weeks" help="% of team active per week"/>
          <div style={{display:'grid',gridTemplateColumns:`110px repeat(12,1fr)`,gap:3,overflowX:'auto'}}>
            <div/>
            {MOCK.weekLabels.map(w=><div key={w} style={{textAlign:'center',fontSize:9,color:C.fg2,padding:'2px 0'}}>{w}</div>)}
            {MOCK.heatTeams.map((team,i)=>(
              <Fragment key={team}>
                <div style={{fontSize:11,color:C.fg2,display:'flex',alignItems:'center',paddingRight:6,whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>{team}</div>
                {MOCK.heatmap[i].map((v,j)=><HeatCell key={j} v={v}/>)}
              </Fragment>
            ))}
          </div>
          <div style={{display:'flex',alignItems:'center',gap:8,fontSize:11,color:C.fg2,justifyContent:'flex-end'}}>
            <span>Less</span>
            {[0.08,.2,.4,.65,.9].map((o,i)=><span key={i} style={{width:12,height:12,borderRadius:2,background:`rgba(86,182,245,${o})`,display:'inline-block'}}/>)}
            <span>More</span>
          </div>
        </CardWrap>
        <CardWrap>
          <CardHead title="Tool mix" sub="Active devs · split by primary tool"/>
          <div style={{display:'flex',justifyContent:'center',padding:'8px 0'}}>
            <Donut size={160} thickness={22} centerValue={String(MOCK.kpis.adoption.active)} centerLabel="ACTIVE DEVS"
              segments={MOCK.toolMix.map(s=>({value:s.value,color:s.color}))}/>
          </div>
          <div style={{display:'flex',flexDirection:'column',gap:8}}>
            {MOCK.toolMix.map(s=>(
              <div key={s.label} style={{display:'grid',gridTemplateColumns:'10px 1fr auto auto',gap:8,alignItems:'center'}}>
                <span style={{width:10,height:10,borderRadius:2,background:s.color,display:'inline-block'}}/>
                <span style={{fontSize:13,color:'#fff'}}>{s.label}</span>
                <span style={{fontSize:12,color:C.fg2,fontFamily:C.mono}}>{s.value}</span>
                <span style={{fontSize:12,color:C.azure,fontWeight:700,fontFamily:C.display}}>{s.pct}%</span>
              </div>
            ))}
          </div>
        </CardWrap>
      </div>
    </div>
  );
}

// ── Productivity Tab ──────────────────────────────────────────────────────────

function ProductivityTab({period}:{period:Period}) {
  const [summary,setSummary]=useState<ProductivitySummary|null>(null);
  const [teams,setTeams]=useState<ProductivityByTeam[]>([]);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [cycleChart,setCycleChart]=useState('line');
  const km=MOCK.kpis.productivity;

  const load=useCallback(async()=>{
    setLoading(true);setError('');
    try{
      const [s,t]=await Promise.all([
        apiFetch<ProductivitySummary>(`/genai-adoption/productivity/summary?period_days=${period}`),
        apiFetch<ProductivityByTeam[]>(`/genai-adoption/productivity/by-team?period_days=${period}`),
      ]);
      setSummary(s);setTeams(t);
    }catch{setError('Failed to load productivity data');}
    finally{setLoading(false);}
  },[period]);
  useEffect(()=>{load();},[load]);

  const cycleSeries=[
    {name:'PR cycle time',color:C.azure, data:MOCK.cycleTime.actual},
    {name:'Trend',        color:C.amber, data:MOCK.cycleTime.trend, dashed:true},
  ];

  const rankTeams=teams.length>0
    ? [...teams].sort((a,b)=>(b.avg_quality_score??0)-(a.avg_quality_score??0)).slice(0,6).map((t,i)=>({id:t.team_id,name:t.team_name,icon:t.team_name.slice(0,2).toUpperCase(),size:t.session_count,value:t.avg_quality_score??0,unit:'/5',maxBar:5}))
    : MOCK.mockTeams.map(t=>({id:t.id,name:t.name,icon:t.icon,size:t.size,value:t.productivity,unit:'%',maxBar:25}));

  return (
    <div style={{display:'flex',flexDirection:'column',gap:16}}>
      {error&&<ErrorBox msg={`Failed to load productivity data: ${error} — charts show illustrative data`}/>}
      {/* KPI row */}
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:16}}>
        <CardWrap>
          <CardHead title="Productivity impact" sub="Improvement in PR cycle time" help="GenAI-assisted PR cycle time vs. baseline, 90-day window"/>
          <BigNum value={`${km.cycleImpact}%`} color={C.azure}/>
          <div style={{display:'flex',alignItems:'center',gap:8}}><DeltaChip value={km.cycleImpactDelta}/><span style={{fontSize:11,color:C.fg2}}>vs. baseline</span></div>
        </CardWrap>
        <CardWrap>
          <CardHead title="Time saved" sub="Estimated engineering hours"/>
          <BigNum value={km.timeSavedHrs.toLocaleString()} unit="hrs"/>
          <div style={{display:'flex',alignItems:'center',gap:8}}><DeltaChip value={km.timeSavedDelta}/><span style={{fontSize:11,color:C.fg2}}>this month</span></div>
        </CardWrap>
        <CardWrap>
          <CardHead title="Throughput" sub="GenAI PRs/week vs baseline"/>
          <BigNum value={`+${km.throughputPct}%`} color={C.azure}/>
          <Sparkline data={[184,196,212,234,247,261,281,303,318]} color={C.azure} w={200} h={32}/>
          <div style={{display:'flex',alignItems:'center',gap:8}}><DeltaChip value={km.throughputDelta}/><span style={{fontSize:11,color:C.fg2}}>this month</span></div>
        </CardWrap>
        <CardWrap>
          <CardHead title="Deploys" sub="Weekly deploys vs baseline"/>
          <BigNum value={`+${km.deploysPct}%`} color={C.azure}/>
          <Sparkline data={[42,44,47,51,54,58,61,65,68]} color={C.amber} w={200} h={32}/>
          <div style={{display:'flex',alignItems:'center',gap:8}}><DeltaChip value={km.deploysDelta}/><span style={{fontSize:11,color:C.fg2}}>this month</span></div>
        </CardWrap>
      </div>

      {/* Cycle time chart + DORA */}
      <div style={{display:'grid',gridTemplateColumns:'2fr 1fr',gap:16}}>
        <CardWrap>
          <CardHead title="GenAI PR cycle time" sub="First commit to merge · monthly average"
            right={<div style={{display:'flex',gap:12,alignItems:'center'}}><Legend items={[{label:'PR cycle time',color:C.azure},{label:'Trend',color:C.amber}]}/><SegControl options={[{value:'line',label:'Line'},{value:'bars',label:'Bars'}]} value={cycleChart} onChange={setCycleChart}/></div>}/>
          <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-end',marginBottom:4}}>
            <div style={{fontSize:11,color:C.fg2,textTransform:'uppercase',letterSpacing:'.04em'}}>Last 9 months</div>
            <div style={{textAlign:'right'}}><div style={{fontSize:28,fontWeight:700,color:'#fff',fontFamily:C.display,lineHeight:1}}>{MOCK.cycleAvg}</div><div style={{fontSize:11,color:C.fg2,textTransform:'uppercase',letterSpacing:'.04em'}}>avg. cycle time</div></div>
          </div>
          {cycleChart==='line'
            ?<LineChart series={cycleSeries} labels={MOCK.monthLabels} height={240} yMax={10} yFormat={v=>`${v}d`} unit="d" showArea={false}/>
            :<BarChart data={MOCK.cycleTime.actual.map((v,i)=>({label:MOCK.monthLabels[i],value:v,color:i===4?C.azure:C.indigo}))} height={240} yMax={10} yFormat={v=>`${v}d`}/>
          }
        </CardWrap>
        <CardWrap>
          <CardHead title="DORA breakdown" sub="PR lifecycle averages"/>
          {MOCK.dora.map(s=>(
            <div key={s.label} style={{display:'grid',gridTemplateColumns:'1fr auto',gap:8,alignItems:'center',padding:'10px 0',borderTop:`1px solid ${C.grid}`}}>
              <div><div style={{fontSize:13,fontWeight:600,color:'#fff'}}>{s.label}</div><div style={{fontSize:11,color:C.fg2,marginTop:2}}>{s.sub}</div></div>
              <div style={{textAlign:'right',display:'flex',alignItems:'center',gap:12}}>
                <Sparkline data={s.spark} color={s.up?C.azure:C.amber} w={64} h={28} fill={false}/>
                <div><div style={{fontSize:22,fontWeight:700,color:'#fff',fontFamily:C.display,lineHeight:1}}>{s.value}<span style={{fontSize:10,fontWeight:600,color:C.fg2,marginLeft:4}}>{s.unit}</span></div><div style={{fontSize:9,color:s.up?C.azure:C.amber,marginTop:3,fontWeight:700}}>{s.delta}</div></div>
              </div>
            </div>
          ))}
        </CardWrap>
      </div>

      {/* Per-tool cycle time */}
      <CardWrap>
        <CardHead title="PR cycle time per GenAI tool" sub="Average cycle time of PRs impacted by each tool" help="GenAI tool attributed to a PR if the assistant produced an accepted suggestion"/>
        <BarChart data={MOCK.cyclePerTool} height={260} yMax={11} yFormat={v=>`${v}d`} refLine={{value:6.3,label:'AVG 6D 8H'}}/>
        <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:12,paddingTop:12,borderTop:`1px solid ${C.grid}`}}>
          {MOCK.cyclePerTool.map(t=>(
            <div key={t.label} style={{textAlign:'center'}}>
              <div style={{fontSize:12,fontWeight:600,color:'#fff',marginBottom:6}}>{t.label}</div>
              <span style={{display:'inline-block',fontSize:11,fontWeight:700,padding:'3px 8px',borderRadius:12,background:`${t.color}18`,color:t.color,border:`1px solid ${t.color}33`}}>{t.sub}</span>
            </div>
          ))}
        </div>
      </CardWrap>

      {/* Throughput + Team ranking */}
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:16}}>
        <CardWrap>
          <CardHead title="Throughput · PRs merged" sub="GenAI-assisted vs Non-GenAI · last 5 months"
            right={<Legend items={[{label:'GenAI',color:C.azure},{label:'Non-GenAI',color:C.indigo}]}/>}/>
          <GroupedBars groups={MOCK.throughput.groups} series={MOCK.throughput.series} height={200}/>
        </CardWrap>
        <CardWrap>
          <CardHead title="Team productivity ranking" sub="Cycle-time improvement vs baseline"/>
          <div style={{display:'flex',flexDirection:'column'}}>
            {rankTeams.map((t,i)=>(
              <div key={t.id} style={{display:'grid',gridTemplateColumns:'28px 1fr auto',gap:10,alignItems:'center',padding:'8px 0',borderBottom:`1px solid rgba(255,255,255,0.04)`}}>
                <div style={{fontSize:11,fontWeight:700,color:C.fg2,fontFamily:C.mono}}>{String(i+1).padStart(2,'0')}</div>
                <div style={{display:'flex',alignItems:'center',gap:8}}>
                  <div style={{width:26,height:26,borderRadius:6,background:'rgba(124,140,248,0.15)',display:'flex',alignItems:'center',justifyContent:'center',fontSize:9,fontWeight:700,color:C.indigo}}>{t.icon}</div>
                  <div><div style={{fontSize:13,fontWeight:600,color:'#fff'}}>{t.name}</div><div style={{fontSize:10,color:C.fg2}}>{t.size} {t.unit==='/5'?'sessions':'devs'}</div></div>
                </div>
                <div style={{textAlign:'right'}}><div style={{fontSize:14,fontWeight:700,color:C.azure,fontFamily:C.display}}>+{t.value.toFixed(1)}{t.unit}</div></div>
              </div>
            ))}
          </div>
        </CardWrap>
      </div>

      {/* Deploys + Hours saved */}
      <div style={{display:'grid',gridTemplateColumns:'2fr 1fr',gap:16}}>
        <CardWrap>
          <CardHead title="Deploys & rollbacks" sub="Production deploys · last 5 months"
            right={<Legend items={[{label:'Deploys',color:C.azure},{label:'Rollbacks',color:C.rose}]}/>}/>
          <GroupedBars groups={MOCK.deploys.groups} series={MOCK.deploys.series} height={200}/>
        </CardWrap>
        <CardWrap>
          <CardHead title="Hours saved by tool" sub="Last 30 days · estimated"/>
          {[{name:'Claude Code',hrs:1124,color:C.azure,pct:61},{name:'Copilot',hrs:716,color:C.indigo,pct:39}].map(s=>(
            <div key={s.name} style={{marginBottom:12}}>
              <div style={{display:'flex',justifyContent:'space-between',alignItems:'baseline',marginBottom:5}}>
                <span style={{fontSize:13,fontWeight:600,color:'#fff'}}>{s.name}</span>
                <span style={{fontSize:18,fontWeight:700,color:'#fff',fontFamily:C.display}}>{s.hrs.toLocaleString()}<span style={{fontSize:10,color:C.fg2,marginLeft:4}}>HRS</span></span>
              </div>
              <BarTrack value={s.pct} color={s.color} height={8}/>
              <div style={{fontSize:11,color:C.fg2,marginTop:4}}>{s.pct}% of total saved</div>
            </div>
          ))}
          <div style={{borderTop:`1px solid ${C.grid}`,paddingTop:12,display:'flex',justifyContent:'space-between',alignItems:'center'}}>
            <span style={{fontSize:12,color:C.fg2}}>Total saved</span>
            <span style={{fontSize:16,fontWeight:700,color:C.azure,fontFamily:C.display}}>1,840 HRS</span>
          </div>
        </CardWrap>
      </div>

      {/* Real cohort data */}
      {summary&&(
        <CardWrap>
          <CardHead title="Session quality cohort comparison" sub={`High vs low adoption · last ${period} days`}/>
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
            {[{label:'High Adoption (≥15 active days)',stats:summary.high_adoption,color:C.azure},{label:'Low Adoption (<4 active days)',stats:summary.low_adoption,color:C.rose}].map(c=>(
              <div key={c.label} style={{background:'rgba(255,255,255,0.03)',border:`1px solid ${c.color}33`,borderTop:`3px solid ${c.color}`,borderRadius:10,padding:'14px 16px'}}>
                <div style={{fontWeight:700,fontSize:13,color:c.color,marginBottom:12}}>{c.label}</div>
                {[{k:'avg_quality_score',l:'Avg quality score',u:' / 5'},{k:'avg_inter_request_s',l:'Avg inter-request time',u:'s'},{k:'avg_turn_count',l:'Avg turns per session',u:''},{k:'session_count',l:'Sessions',u:''}].map(f=>(
                  <div key={f.k} style={{display:'flex',justifyContent:'space-between',marginBottom:8,fontSize:13}}>
                    <span style={{color:C.fg2}}>{f.l}</span>
                    <span style={{fontWeight:600,color:'#fff'}}>{fmt((c.stats as unknown as Record<string,number|null>)[f.k])}{f.u}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </CardWrap>
      )}
    </div>
  );
}

// ── Quality Tab ───────────────────────────────────────────────────────────────

function QualityTab({period}:{period:Period}) {
  const [summary,setSummary]=useState<QualitySummary|null>(null);
  const [teams,setTeams]=useState<QualityByTeam[]>([]);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [durChart,setDurChart]=useState('line');
  const km=MOCK.kpis.quality;

  const load=useCallback(async()=>{
    setLoading(true);setError('');
    try{
      const [s,t]=await Promise.all([
        apiFetch<QualitySummary>(`/genai-adoption/quality/summary?period_days=${period}`),
        apiFetch<QualityByTeam[]>(`/genai-adoption/quality/by-team?period_days=${period}`),
      ]);
      setSummary(s);setTeams(t);
    }catch{setError('Failed to load quality data');}
    finally{setLoading(false);}
  },[period]);
  useEffect(()=>{load();},[load]);

  const durSeries=[
    {name:'GenAI tools',   color:C.indigo,  data:MOCK.durability.gen},
    {name:'Non-GenAI tools',color:C.fg2,    data:MOCK.durability.nonGen},
  ];

  return (
    <div style={{display:'flex',flexDirection:'column',gap:16}}>
      {error&&<ErrorBox msg={`Failed to load quality data: ${error} — charts show illustrative data`}/>}
      {/* KPI row */}
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:16}}>
        <CardWrap>
          <CardHead title="Code durability" sub="More stable code with GenAI" help="Code that remains unchanged after 30 days"/>
          <BigNum value={`+${km.durability}%`} color={C.azure}/>
          <div style={{display:'flex',alignItems:'center',gap:8}}><DeltaChip value={km.durabilityDelta}/><span style={{fontSize:11,color:C.fg2}}>vs non-GenAI</span></div>
        </CardWrap>
        <CardWrap>
          <CardHead title="Tests covered" sub="Commits with tests added" help="GenAI-assisted commits adding test coverage"/>
          <BigNum value={`${km.testCovered}%`} color={C.azure}/>
          <div style={{display:'flex',alignItems:'center',gap:8}}><DeltaChip value={km.testCoveredDelta}/><span style={{fontSize:11,color:C.fg2}}>vs non-GenAI</span></div>
        </CardWrap>
        <CardWrap>
          <CardHead title="Revert rate" sub="PRs reverted within 7d" help="% of merged PRs reverted within 7 days"/>
          <BigNum value={`${km.revertRate}%`} color={C.amber}/>
          <div style={{display:'flex',alignItems:'center',gap:8}}><DeltaChip value={km.revertRateDelta} inverted={true}/><span style={{fontSize:11,color:C.fg2}}>improving</span></div>
        </CardWrap>
        <CardWrap>
          <CardHead title="Review impact" sub="Review time vs non-GenAI" help="Change in code review time on GenAI-assisted PRs"/>
          <BigNum value={`${km.reviewImpact}%`} color={C.rose}/>
          <div style={{display:'flex',alignItems:'center',gap:8}}><DeltaChip value={km.reviewImpactDelta} inverted={true}/><span style={{fontSize:11,color:C.fg2}}>faster reviews</span></div>
        </CardWrap>
      </div>

      {/* Most impacted contributors */}
      <CardWrap>
        <CardHead title="Most impacted contributors" sub="Groups with highest GenAI impact · avg PR cycle time"/>
        <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:12}}>
          {MOCK.qualityContribs.map(c=>(
            <div key={c.name} style={{background:'rgba(255,255,255,0.03)',border:`1px solid rgba(255,255,255,0.06)`,borderRadius:10,padding:'14px 16px',display:'flex',flexDirection:'column',gap:8}}>
              <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
                <div style={{width:32,height:32,borderRadius:8,background:`${c.color}20`,display:'flex',alignItems:'center',justifyContent:'center',color:c.color,fontSize:14}}>●</div>
                <span style={{fontSize:18,fontWeight:700,color:'#fff',fontFamily:C.display}}>{c.cycle}</span>
              </div>
              <div style={{fontSize:13,fontWeight:600,color:'#fff'}}>{c.name}</div>
              <div style={{display:'flex',gap:3}}>
                {['JK','RM','SE','NV'].map((a,i)=><div key={i} style={{width:22,height:22,borderRadius:'50%',background:[C.indigo,C.amber,C.rose,'rgba(66,32,130,0.8)'][i],display:'flex',alignItems:'center',justifyContent:'center',fontSize:9,fontWeight:700,color:'#fff',marginLeft:i?-4:0,border:'1.5px solid rgba(15,23,41,0.8)'}}>{a}</div>)}
                <div style={{width:22,height:22,borderRadius:'50%',background:'rgba(255,255,255,0.08)',display:'flex',alignItems:'center',justifyContent:'center',fontSize:8,color:C.fg2,marginLeft:-4,border:'1.5px solid rgba(15,23,41,0.8)'}}>15+</div>
              </div>
            </div>
          ))}
        </div>
      </CardWrap>

      {/* Code durability chart + side cards */}
      <div style={{display:'grid',gridTemplateColumns:'2fr 1fr',gap:16}}>
        <CardWrap>
          <CardHead title="Code durability" sub="Code remaining stable for more than 30 days"
            right={<div style={{display:'flex',gap:12,alignItems:'center'}}><Legend items={[{label:'GenAI Tools',color:C.indigo},{label:'Non GenAI',color:C.fg2}]}/><SegControl options={[{value:'line',label:'Line'},{value:'bars',label:'Bars'}]} value={durChart} onChange={setDurChart}/></div>}/>
          <div style={{display:'flex',gap:24,alignItems:'flex-end',marginBottom:8}}>
            <div><div style={{fontSize:10,color:C.fg2,textTransform:'uppercase',letterSpacing:'.04em'}}>All GenAI Tools</div><div style={{display:'flex',gap:10,alignItems:'baseline',marginTop:4}}><span style={{fontSize:32,fontWeight:700,color:C.azure,fontFamily:C.display,lineHeight:1}}>{km.testCovered}%</span><DeltaChip value={km.testCoveredDelta}/></div></div>
            <div><div style={{fontSize:10,color:C.fg2,textTransform:'uppercase',letterSpacing:'.04em'}}>Delta</div><div style={{fontSize:28,color:'#fff',fontFamily:C.display,fontWeight:700,marginTop:4,lineHeight:1}}>+{km.durability}%</div><div style={{fontSize:11,color:C.fg2,textTransform:'uppercase',letterSpacing:'.04em'}}>more stable with genai</div></div>
          </div>
          {durChart==='line'
            ?<LineChart series={durSeries} labels={MOCK.durability.months} height={240} yMax={100} yFormat={v=>`${v}%`} showArea={true}/>
            :<GroupedBars groups={MOCK.durability.months} series={durSeries} height={240}/>
          }
        </CardWrap>
        <div style={{display:'flex',flexDirection:'column',gap:12}}>
          <CardWrap style={{gap:10}}>
            <CardHead title="Tests covered commits" help=""/>
            <div style={{display:'flex',alignItems:'baseline',gap:10}}><span style={{fontSize:28,fontWeight:700,color:C.azure,fontFamily:C.display}}>{km.testCovered}%</span><DeltaChip value={km.testCoveredDelta}/></div>
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8}}>
              <div style={{background:'rgba(255,255,255,0.03)',borderRadius:8,padding:'10px 12px',border:`1px solid ${C.border}`}}><div style={{fontSize:10,color:C.fg2,textTransform:'uppercase',letterSpacing:'.04em'}}>Non-GenAI</div><div style={{fontSize:18,fontWeight:700,color:'#fff',fontFamily:C.display,marginTop:4}}>8.2%</div><div style={{fontSize:10,color:C.fg2}}>of commits</div></div>
              <div style={{background:'rgba(86,182,245,0.06)',borderRadius:8,padding:'10px 12px',border:`1px solid rgba(86,182,245,0.25)`}}><div style={{fontSize:10,color:C.azure,textTransform:'uppercase',letterSpacing:'.04em'}}>GenAI</div><div style={{fontSize:18,fontWeight:700,color:'#fff',fontFamily:C.display,marginTop:4}}>{km.testCovered}%</div><div style={{fontSize:10,color:C.fg2}}>of commits</div></div>
            </div>
          </CardWrap>
          <CardWrap style={{gap:10}}>
            <CardHead title="Code review impact" help=""/>
            <div style={{display:'flex',alignItems:'baseline',gap:10}}><span style={{fontSize:28,fontWeight:700,color:C.rose,fontFamily:C.display}}>{km.reviewImpact}%</span><DeltaChip value={km.reviewImpactDelta} inverted={true}/></div>
            <div style={{fontSize:11,color:C.fg2}}>Time in review on GenAI PRs vs non-GenAI</div>
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8}}>
              <div style={{background:'rgba(255,255,255,0.03)',borderRadius:8,padding:'10px 12px',border:`1px solid ${C.border}`}}><div style={{fontSize:10,color:C.fg2,textTransform:'uppercase'}}>Non-GenAI</div><div style={{fontSize:18,fontWeight:700,color:'#fff',fontFamily:C.display,marginTop:4}}>2.2d</div></div>
              <div style={{background:'rgba(124,140,248,0.08)',borderRadius:8,padding:'10px 12px',border:`1px solid rgba(124,140,248,0.25)`}}><div style={{fontSize:10,color:C.indigo,textTransform:'uppercase'}}>GenAI</div><div style={{fontSize:18,fontWeight:700,color:'#fff',fontFamily:C.display,marginTop:4}}>1.8d</div></div>
            </div>
          </CardWrap>
          <CardWrap style={{gap:10}}>
            <CardHead title="Code longevity" help=""/>
            <div style={{display:'flex',alignItems:'baseline',gap:10}}><span style={{fontSize:28,fontWeight:700,color:C.azure,fontFamily:C.display}}>10.13%</span><DeltaChip value={3.46}/></div>
            <div style={{fontSize:11,color:C.fg2}}>Lines surviving 90+ days on GenAI PRs</div>
            <Sparkline data={[6,7,7.5,8.4,9.1,9.8,10.1]} color={C.azure} w={200} h={32}/>
          </CardWrap>
        </div>
      </div>

      {/* Revert rate + Bug-introducing */}
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:16}}>
        <CardWrap>
          <CardHead title="Revert rate by tool" sub="% of merged PRs reverted within 7 days" help="Lower is better"/>
          <BarChart data={MOCK.revertByTool} height={220} yMax={6} yFormat={v=>`${v}%`}/>
        </CardWrap>
        <CardWrap>
          <CardHead title="Bug-introducing commits" sub="Commits later linked to incidents · last 90 days"/>
          <div style={{display:'grid',gridTemplateColumns:'auto 1fr',gap:18,alignItems:'center'}}>
            <Donut size={140} thickness={20} centerValue="4.2%" centerLabel="OF COMMITS"
              segments={[{value:4.2,color:C.rose},{value:95.8,color:'rgba(255,255,255,0.04)'}]}/>
            <div style={{display:'flex',flexDirection:'column',gap:10}}>
              {[{label:'GenAI assisted',v:'3.1%',pct:31,color:C.azure,sub:'lower than baseline'},{label:'Non-GenAI',v:'5.4%',pct:54,color:C.rose,sub:'above baseline'},{label:'Mixed',v:'4.0%',pct:40,color:C.amber,sub:'at baseline'}].map(s=>(
                <div key={s.label}>
                  <div style={{display:'flex',justifyContent:'space-between',marginBottom:4}}><span style={{color:'#fff',fontSize:12}}>{s.label}</span><span style={{color:'#fff',fontSize:13,fontWeight:700,fontFamily:C.display}}>{s.v}</span></div>
                  <BarTrack value={s.pct} color={s.color} height={6}/>
                  <div style={{fontSize:9,color:C.fg2,marginTop:3}}>{s.sub}</div>
                </div>
              ))}
            </div>
          </div>
        </CardWrap>
      </div>

      {/* Real API data panel */}
      {loading&&<div style={{...CARD,padding:'12px 16px'}}><Spinner/></div>}
      {error&&<ErrorBox msg={error}/>}
      {summary&&(
        <CardWrap>
          <CardHead title="Session error & cache metrics" sub={`Cohort comparison · last ${period} days`}/>
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
            {[{label:'High Adoption (≥15 active days)',stats:summary.high_adoption,color:C.azure},{label:'Low Adoption (<4 active days)',stats:summary.low_adoption,color:C.rose}].map(c=>(
              <div key={c.label} style={{background:'rgba(255,255,255,0.03)',border:`1px solid ${c.color}33`,borderTop:`3px solid ${c.color}`,borderRadius:10,padding:'14px 16px'}}>
                <div style={{fontWeight:700,fontSize:13,color:c.color,marginBottom:12}}>{c.label}</div>
                {[{k:'avg_error_rate_pct',l:'Avg error rate',u:'%'},{k:'avg_retry_rate_pct',l:'Avg retry rate',u:'%'},{k:'cache_hit_rate_pct',l:'Cache hit rate',u:'%'}].map(f=>(
                  <div key={f.k} style={{display:'flex',justifyContent:'space-between',marginBottom:8,fontSize:13}}>
                    <span style={{color:C.fg2}}>{f.l}</span>
                    <span style={{fontWeight:600,color:'#fff'}}>{fmt((c.stats as unknown as Record<string,number|null>)[f.k])}{f.u}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
          {teams.length>0&&(
            <>
              <div style={{fontSize:12,fontWeight:600,color:C.fg2,textTransform:'uppercase',letterSpacing:'.06em',marginTop:8}}>By Team</div>
              <table style={{width:'100%',borderCollapse:'collapse',fontSize:12}}>
                <thead><tr style={{borderBottom:`1px solid ${C.grid}`}}>{['Team','Sessions','Error Rate','Retry Rate','Cache Hit',''].map((h,i)=><th key={i} style={{padding:'6px 8px',textAlign:'left',fontSize:10,textTransform:'uppercase',letterSpacing:'.04em',color:C.fg2}}>{h}</th>)}</tr></thead>
                <tbody>{teams.map(t=><tr key={t.team_id} style={{borderBottom:`1px solid rgba(255,255,255,0.04)`}}><td style={{padding:'8px',color:'#fff',fontWeight:500}}>{t.team_name}</td><td style={{padding:'8px',color:C.fg2}}>{t.session_count}</td><td style={{padding:'8px'}}><span style={{color:(t.avg_error_rate_pct??0)>10?C.rose:C.azure,fontWeight:600}}>{fmt(t.avg_error_rate_pct)}%</span></td><td style={{padding:'8px',color:'#fff'}}>{fmt(t.avg_retry_rate_pct)}%</td><td style={{padding:'8px',color:'#fff'}}>{fmt(t.cache_hit_rate_pct)}%</td><td style={{padding:'8px'}}>{t.high_error_flag&&<span style={{fontSize:11,padding:'2px 6px',borderRadius:4,background:`rgba(244,114,114,0.1)`,color:C.rose,fontWeight:600}}>⚠ High error rate</span>}</td></tr>)}</tbody>
              </table>
            </>
          )}
        </CardWrap>
      )}
    </div>
  );
}

// ── Utils ─────────────────────────────────────────────────────────────────────
function Spinner() { return <div style={{padding:'32px 0',color:C.fg2,fontSize:14,textAlign:'center'}}>Loading…</div>; }
function ErrorBox({msg}:{msg:string}) { return <div style={{padding:'10px 14px',background:'rgba(244,114,114,0.1)',border:`1px solid ${C.rose}`,borderRadius:8,color:C.rose,fontSize:13}}>{msg}</div>; }

// ── Page ──────────────────────────────────────────────────────────────────────
export default function GenAiAdoptionPage() {
  const [tab,setTab]=useState<Tab>('adoption');
  const [period,setPeriod]=useState<Period>(30);

  useEffect(()=>{
    const link=document.createElement('link');
    link.rel='stylesheet';
    link.href='https://fonts.googleapis.com/css2?family=Rubik:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&family=Roboto+Mono:wght@400;700&display=swap';
    document.head.appendChild(link);
    return ()=>{document.head.removeChild(link);};
  },[]);

  const tabs=[{id:'adoption' as Tab,label:'GenAI Adoption'},{id:'productivity' as Tab,label:'GenAI Productivity'},{id:'quality' as Tab,label:'GenAI Code Quality'}];

  return (
    <div style={{fontFamily:C.ui,color:'#fff',minHeight:'100vh',position:'relative'}}>
      {/* Ambient orbs */}
      <div style={{position:'fixed',inset:0,pointerEvents:'none',zIndex:0,background:'radial-gradient(900px 600px at 12% 8%,rgba(124,140,248,0.14),transparent 60%),radial-gradient(800px 500px at 88% 18%,rgba(86,182,245,0.11),transparent 65%),radial-gradient(700px 500px at 75% 92%,rgba(245,181,86,0.07),transparent 65%),radial-gradient(600px 400px at 22% 78%,rgba(244,114,114,0.06),transparent 65%)'}}/>
      <div style={{position:'relative',zIndex:1,padding:'28px 32px',maxWidth:1100}}>
        {/* Header */}
        <div style={{display:'flex',alignItems:'flex-start',gap:16,marginBottom:24}}>
          <div>
            <h1 style={{margin:0,fontSize:22,fontWeight:700,color:'#fff',fontFamily:C.display,letterSpacing:'-.01em'}}>
              GenAI Adoption <span style={{color:C.azure}}>✦</span>
            </h1>
            <div style={{fontSize:11,color:C.fg2,marginTop:4,display:'flex',alignItems:'center',gap:6}}>
              <span style={{padding:'1px 6px',borderRadius:4,background:'rgba(245,181,86,0.12)',border:'1px solid rgba(245,181,86,0.3)',color:C.amber,fontSize:10,fontWeight:600}}>ILLUSTRATIVE</span>
              <span>Charts use representative data · live cohort metrics load where available</span>
            </div>
          </div>
          <select value={period} onChange={e=>setPeriod(Number(e.target.value) as Period)} style={{marginLeft:'auto',padding:'7px 14px',borderRadius:10,background:'rgba(124,140,248,0.18)',border:'1px solid rgba(124,140,248,0.30)',color:'#fff',fontFamily:C.ui,fontSize:13,cursor:'pointer',backdropFilter:'blur(12px)'}}>
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
        </div>

        {/* AI Insights */}
        <InsightsPanel period={period}/>

        {/* Tabs */}
        <div style={{display:'flex',gap:2,marginBottom:24,borderBottom:`1px solid rgba(255,255,255,0.08)`,paddingBottom:0}}>
          {tabs.map(t=>(
            <button key={t.id} onClick={()=>setTab(t.id)} style={{padding:'9px 18px',background:'transparent',border:'none',borderBottom:tab===t.id?`2px solid ${C.azure}`:'2px solid transparent',color:tab===t.id?C.azure:C.fg2,fontFamily:C.ui,fontSize:13,fontWeight:tab===t.id?600:400,cursor:'pointer',paddingBottom:10,marginBottom:-1,transition:'all 120ms'}}>
              {t.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {tab==='adoption'    &&<AdoptionTab     period={period}/>}
        {tab==='productivity'&&<ProductivityTab  period={period}/>}
        {tab==='quality'     &&<QualityTab       period={period}/>}
      </div>
    </div>
  );
}
