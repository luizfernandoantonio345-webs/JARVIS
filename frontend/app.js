const _h = window.location.hostname || 'localhost';
const API_URL = `http://${_h}:8000`;
// session_id persiste entre recarregamentos via localStorage
let _sessionId = localStorage.getItem('jarvis_session') || '';

// ── TOKEN DE AUTENTICAÇÃO JARVIS ──────────────────────────────────────────────
// Salva token se vier na URL (?auth=TOKEN) — ex: link gerado por generate_token.bat
(()=>{
  const usp=new URLSearchParams(window.location.search);
  const urlTok=usp.get('auth');
  if(urlTok&&urlTok.length===64){
    localStorage.setItem('jarvis_token',urlTok);
    // Limpa o token da URL (não fica visível no histórico)
    const clean=window.location.pathname+(usp.toString().replace(/&?auth=[^&]*/,'').replace(/^\?$/,'')?'?'+usp:'');
    window.history.replaceState({},'',clean);
  }
})();
const _jarvisToken = ()=>localStorage.getItem('jarvis_token')||'';
// Cabeçalhos padrão para todas as requisições (inclui Bearer token se existir)
function _authHeaders(extra){
  const h={'Content-Type':'application/json',...(extra||{})};
  const tok=_jarvisToken();
  if(tok)h['Authorization']='Bearer '+tok;
  return h;
}
// ──────────────────────────────────────────────────────────────────────────────

function _wsUrl(){
  const tok=_jarvisToken();
  const params=[];
  if(_sessionId)params.push('session_id='+_sessionId);
  if(tok)params.push('auth='+tok);
  return`ws://${_h}:8000/ws/jarvis${params.length?'?'+params.join('&'):''}`;
}
const WS_URL = _wsUrl(); // mantido para compatibilidade
const cvStars=document.getElementById('c-stars'),cxS=cvStars.getContext('2d');
const cvRings=document.getElementById('c-rings'),cxR=cvRings.getContext('2d');
const cvOrb=document.getElementById('c-orb'),cxO=cvOrb.getContext('2d');
const cvFx=document.getElementById('c-fx'),cxF=cvFx.getContext('2d');
let W,H,CX,CY,R,lastT=performance.now();
function resize(){
  W=window.innerWidth;H=window.innerHeight;
  [cvStars,cvRings,cvOrb,cvFx].forEach(c=>{c.width=W;c.height=H});
  CX=W/2;CY=H/2;R=Math.min(W,H)*0.22;
  buildMap();drawCharts();buildStreams();initStars();
}
window.addEventListener('resize',resize);
let t=0,al=0,tal=0,speaking=false,wvis=false,alertMode=false;
let stimer=null;
let anl=null,fdata=null;
async function initMic(){
  try{
    const s=await navigator.mediaDevices.getUserMedia({audio:true});
    const ac=new AudioContext();const src=ac.createMediaStreamSource(s);
    anl=ac.createAnalyser();anl.fftSize=512;anl.smoothingTimeConstant=0.84;
    src.connect(anl);fdata=new Uint8Array(anl.frequencyBinCount);
  }catch(e){startDemo()}
}
function getMic(){
  if(!anl)return 0;
  anl.getByteFrequencyData(fdata);
  let sum=0,cnt=0;const bin=anl.sampleRate/(anl.fftSize||512);
  for(let i=0;i<fdata.length;i++){const freq=i*bin;if(freq>150&&freq<3500){sum+=fdata[i];cnt++;}}
  return cnt?Math.min(1,sum/cnt/55):0;
}
function startDemo(){
  function cycle(){const wait=2000+Math.random()*5000,dur=2000+Math.random()*5000;setTimeout(()=>{setSpeaking(true,dur);setTimeout(cycle,dur+600)},wait);}
  setSpeaking(true,4500);setTimeout(cycle,5500);
}
let stars=[];
function initStars(){
  stars=Array.from({length:350},()=>({x:Math.random()*W,y:Math.random()*H,r:0.12+Math.random()*0.9,al:0.06+Math.random()*0.42,tw:1.5+Math.random()*7,ph:Math.random()*Math.PI*2,isCyan:Math.random()>0.7}));
}
function drawStars(){
  cxS.clearRect(0,0,W,H);
  stars.forEach(s=>{const fl=s.al*(0.4+0.6*Math.sin(t*s.tw+s.ph));cxS.beginPath();cxS.arc(s.x,s.y,s.r,0,Math.PI*2);cxS.fillStyle=s.isCyan?`rgba(180,240,255,${fl})`:`rgba(200,215,255,${fl*0.6})`;cxS.fill();});
}
const ringDefs=[
  {r:1.62,lw:0.75,al:0.11,spd:0.007,isC:true,dash:0,doff:0,ticks:20,angle:0,ta:0},
  {r:1.98,lw:0.55,al:0.075,spd:-0.005,isC:false,dash:0,doff:0,ticks:16,angle:0,ta:0},
  {r:2.38,lw:0.44,al:0.046,spd:0.003,isC:true,dash:6,doff:9,ticks:28,angle:0,ta:0},
  {r:2.82,lw:0.36,al:0.028,spd:-0.0022,isC:false,dash:3,doff:12,ticks:8,angle:0,ta:0},
  {r:3.22,lw:0.28,al:0.015,spd:0.0014,isC:true,dash:2,doff:14,ticks:40,angle:0,ta:0},
];
ringDefs.forEach(rg=>{rg.angle=Math.random()*Math.PI*2;rg.ta=Math.random()*Math.PI*2});
const hudArcs=[
  {r:1.36,s:0.06,e:0.55,al:0.14,isC:true,spd:0.0095,off:0,lw:2.5},
  {r:1.36,s:0.68,e:1.08,al:0.1,isC:false,spd:0.0095,off:0,lw:2.5},
  {r:1.48,s:1.35,e:2.08,al:0.12,isC:true,spd:-0.007,off:0,lw:2.2},
  {r:1.48,s:2.36,e:3.02,al:0.09,isC:false,spd:-0.007,off:0,lw:2.2},
];
function drawRings(OR){
  cxR.clearRect(0,0,W,H);
  const bg=cxR.createRadialGradient(CX,CY,0,CX,CY,OR*4);
  bg.addColorStop(0,`rgba(0,18,58,${0.07+al*0.07})`);bg.addColorStop(0.35,`rgba(0,8,20,${0.05+al*0.03})`);bg.addColorStop(1,'rgba(0,0,0,0)');
  cxR.beginPath();cxR.arc(CX,CY,OR*4,0,Math.PI*2);cxR.fillStyle=bg;cxR.fill();
  ringDefs.forEach(rg=>{
    rg.angle+=rg.spd;rg.ta+=rg.spd*1.6;const rr=OR*rg.r;
    cxR.save();cxR.translate(CX,CY);cxR.rotate(rg.angle);
    cxR.beginPath();cxR.arc(0,0,rr,0,Math.PI*2);
    if(rg.dash>0)cxR.setLineDash([rg.dash,rg.doff]);else cxR.setLineDash([]);
    cxR.strokeStyle=rg.isC?`rgba(0,229,255,${rg.al})`:`rgba(212,168,30,${rg.al})`;
    cxR.lineWidth=rg.lw;cxR.stroke();
    for(let i=0;i<rg.ticks;i++){const a=(i/rg.ticks)*Math.PI*2+rg.ta;const maj=i%(rg.ticks/4)===0;const len=maj?6:3.5;cxR.beginPath();cxR.moveTo(Math.cos(a)*(rr-len),Math.sin(a)*(rr-len));cxR.lineTo(Math.cos(a)*(rr+len),Math.sin(a)*(rr+len));cxR.strokeStyle=rg.isC?`rgba(0,229,255,${rg.al*2.4})`:`rgba(212,168,30,${rg.al*2.4})`;cxR.lineWidth=maj?0.95:0.42;cxR.stroke();}
    cxR.setLineDash([]);cxR.restore();
  });
  hudArcs.forEach(h=>{h.off+=h.spd;const rr=OR*h.r;cxR.beginPath();cxR.arc(CX,CY,rr,h.s+h.off,h.e+h.off);cxR.strokeStyle=h.isC?`rgba(0,229,255,${h.al})`:`rgba(212,168,30,${h.al})`;cxR.lineWidth=h.lw;cxR.stroke();});
}
const WNUM=32;
const waves=Array.from({length:WNUM},(_,i)=>({ph:(i/WNUM)*Math.PI*2,spd:0.08+(i%8)*0.04,amp:0.036+(i%9)*0.014,f1:2+(i%11),f2:3+(i%8),f3:1+(i%7),f4:4+(i%5),isC:(i%5)!==2,al:0.028+(i%9)*0.011,lw:0.22+(i%6)*0.14,dir:i%2?1:-1}));
const PN=480,TLEN=8;
const pA=new Float32Array(PN),pR=new Float32Array(PN),pSp=new Float32Array(PN);
const pSz=new Float32Array(PN),pAl=new Float32Array(PN),pPh=new Float32Array(PN);
const pC=new Uint8Array(PN);
const pTX=new Float32Array(PN*TLEN),pTY=new Float32Array(PN*TLEN),pTH=new Int32Array(PN);
for(let i=0;i<PN;i++){pA[i]=Math.random()*Math.PI*2;pR[i]=0.78+Math.random()*0.9;pSp[i]=(Math.random()>.5?1:-1)*(0.0004+Math.random()*0.0032);pSz[i]=0.18+Math.random()*2.1;pAl[i]=0.05+Math.random()*0.62;pPh[i]=Math.random()*Math.PI*2;pC[i]=Math.random()>.27?1:0;}
const MFL=16;
const mflPh=Array.from({length:MFL},(_,i)=>(i/MFL)*Math.PI*2);
const ckt=[[-0.31,-0.19,0.13,-0.19],[0.13,-0.19,0.13,0.07],[-0.19,0.13,0.23,0.13],[-0.29,-0.19,-0.29,0.23],[0.13,0.07,0.23,0.07],[-0.11,0.23,-0.11,0.34],[0.23,0.07,0.23,-0.05],[0.23,-0.05,0.33,-0.05]];
function drawOrb(){
  cxO.clearRect(0,0,W,H);
  const m=getMic();
  // Prioridade: microfone (usuario falando) > voz real do JARVIS > nada.
  // A senoide falsa que ficava aqui pulsava em ritmo fixo, sem relacao com
  // as palavras, porque o TTS tocava no backend e o navegador nunca via o
  // audio. Agora tts-voice.js toca no navegador e devolve o nivel real.
  const ttsLvl=(window.JarvisTTS&&window.JarvisTTS.estaFalando())
    ?window.JarvisTTS.nivelTTS():0;
  tal=m>0.01?m:(ttsLvl>0.004?ttsLvl:(speaking?0.16+Math.sin(t*18)*0.22:0));
  al+=(tal-al)*0.082;
  const pulse=0.5+0.5*Math.sin(t*1.78);
  const OR=R*(1+pulse*0.022+al*0.32);
  const cg=cxO.createRadialGradient(CX-OR*0.24,CY-OR*0.2,OR*0.01,CX,CY,OR);
  cg.addColorStop(0,'rgba(22,85,225,0.98)');cg.addColorStop(0.08,'rgba(10,105,215,0.96)');cg.addColorStop(0.2,'rgba(0,140,230,0.9)');cg.addColorStop(0.4,'rgba(0,188,248,0.68)');cg.addColorStop(0.62,'rgba(0,215,255,0.38)');cg.addColorStop(0.8,'rgba(0,229,255,0.12)');cg.addColorStop(1,'rgba(0,229,255,0)');
  cxO.beginPath();cxO.arc(CX,CY,OR,0,Math.PI*2);cxO.fillStyle=cg;cxO.fill();
  if(al>0.012){const gg=cxO.createRadialGradient(CX,CY,0,CX,CY,OR*0.75);gg.addColorStop(0,`rgba(245,188,35,${Math.min(al*0.65,0.56)})`);gg.addColorStop(0.35,`rgba(200,130,18,${Math.min(al*0.25,0.24)})`);gg.addColorStop(1,'rgba(200,120,0,0)');cxO.beginPath();cxO.arc(CX,CY,OR*0.75,0,Math.PI*2);cxO.fillStyle=gg;cxO.fill();}
  if(alertMode){const ag=cxO.createRadialGradient(CX,CY,0,CX,CY,OR);const ap=0.04+Math.sin(t*7)*0.025;ag.addColorStop(0,`rgba(255,42,74,${ap*2})`);ag.addColorStop(1,'rgba(255,42,74,0)');cxO.beginPath();cxO.arc(CX,CY,OR,0,Math.PI*2);cxO.fillStyle=ag;cxO.fill();}
  if(al>0.015){mflPh.forEach((ph,i)=>{const a0=ph+t*0.07*((i%2)?1:-1);const fal=al*0.16;cxO.beginPath();for(let j=0;j<=55;j++){const fr=j/55,r2=OR*(1.01+fr*0.48),curl=Math.sin(fr*Math.PI)*0.4,fa=a0+curl,fx=CX+Math.cos(fa)*r2,fy=CY+Math.sin(fa)*r2;j===0?cxO.moveTo(fx,fy):cxO.lineTo(fx,fy);}cxO.strokeStyle=i%3===0?`rgba(212,168,30,${fal})`:`rgba(0,229,255,${fal})`;cxO.lineWidth=0.45;cxO.stroke();});}
  const ab=1+al*6.2;
  waves.forEach(w=>{const amp=w.amp*ab;cxO.beginPath();const ST=380;for(let i=0;i<=ST;i++){const a=(i/ST)*Math.PI*2,n1=Math.sin(a*w.f1+t*w.spd*w.dir+w.ph),n2=Math.sin(a*w.f2+t*w.spd*0.55*w.dir+w.ph*1.38)*0.38,n3=Math.sin(a*w.f3+t*w.spd*1.48*w.dir+w.ph*0.62)*0.24,n4=Math.sin(a*w.f4+t*w.spd*0.32+w.ph*1.85)*0.14*(0.3+al*0.7),n5=Math.sin(a*(w.f1+w.f2)*0.5+t*w.spd*0.2+w.ph*2.1)*0.1*al,rr=OR*(0.76+(n1+n2+n3+n4+n5)*amp),x=CX+Math.cos(a)*rr,y=CY+Math.sin(a)*rr;i===0?cxO.moveTo(x,y):cxO.lineTo(x,y);}cxO.closePath();const ral=Math.min(w.al*(1+al*4.5),w.isC?0.58:0.48);cxO.strokeStyle=w.isC?`rgba(0,229,255,${ral})`:`rgba(212,168,30,${ral})`;cxO.lineWidth=w.lw+al*0.9;cxO.setLineDash([]);cxO.stroke();});
  for(let i=0;i<PN;i++){pA[i]+=pSp[i]*(1+al*3.5);const wb=Math.sin(pA[i]*3+pPh[i]+t)*0.09*al,pr=OR*(pR[i]+wb),px=CX+Math.cos(pA[i])*pr,py=CY+Math.sin(pA[i])*pr,head=pTH[i];pTX[i*TLEN+head]=px;pTY[i*TLEN+head]=py;pTH[i]=(head+1)%TLEN;const pal=Math.min(pAl[i]+al*0.65,0.95);if(al>0.025){for(let j=1;j<TLEN;j++){const jj=(head-j+TLEN)%TLEN,jj2=(head-j+1+TLEN)%TLEN,ta=pal*(1-j/TLEN)*0.28;cxO.beginPath();cxO.moveTo(pTX[i*TLEN+jj2],pTY[i*TLEN+jj2]);cxO.lineTo(pTX[i*TLEN+jj],pTY[i*TLEN+jj]);cxO.strokeStyle=pC[i]?`rgba(0,229,255,${ta})`:`rgba(212,168,30,${ta})`;cxO.lineWidth=pSz[i]*0.45;cxO.stroke();}}cxO.beginPath();cxO.arc(px,py,pSz[i]*(1+al*0.9),0,Math.PI*2);cxO.fillStyle=pC[i]?`rgba(0,229,255,${pal})`:`rgba(212,168,30,${pal})`;cxO.fill();}
  const rim=cxO.createRadialGradient(CX,CY,OR*0.82,CX,CY,OR*1.15);rim.addColorStop(0,'rgba(0,229,255,0)');rim.addColorStop(0.62,`rgba(0,229,255,${0.03+al*0.1})`);rim.addColorStop(1,`rgba(0,229,255,${0.18+al*0.3})`);cxO.beginPath();cxO.arc(CX,CY,OR*1.12,0,Math.PI*2);cxO.fillStyle=rim;cxO.fill();
  if(al>0.025){const nsp=Math.floor(5+al*18);for(let i=0;i<nsp;i++){const ang=(i/nsp)*Math.PI*2+t*0.65+Math.sin(t*6+i)*0.35,len=(0.045+Math.sin(t*16+i*1.8)*0.038+al*0.19)*OR,x1=CX+Math.cos(ang)*OR*1.02,y1=CY+Math.sin(ang)*OR*1.02,x2=CX+Math.cos(ang)*(OR*1.02+len),y2=CY+Math.sin(ang)*(OR*1.02+len);cxO.beginPath();cxO.moveTo(x1,y1);cxO.lineTo(x2,y2);cxO.strokeStyle=(i%3!==0)?`rgba(0,229,255,${Math.min(al*0.7,0.52)})`:`rgba(212,168,30,${Math.min(al*0.55,0.44)})`;cxO.lineWidth=0.65;cxO.stroke();}}
  cxO.save();cxO.translate(CX,CY);cxO.globalAlpha=0.04+al*0.025;cxO.strokeStyle='#00e5ff';cxO.lineWidth=0.4;ckt.forEach(([x1,y1,x2,y2])=>{cxO.beginPath();cxO.moveTo(x1*OR,y1*OR);cxO.lineTo(x2*OR,y2*OR);cxO.stroke();cxO.beginPath();cxO.arc(x2*OR,y2*OR,1.7,0,Math.PI*2);cxO.fillStyle='rgba(0,229,255,0.55)';cxO.fill();});cxO.restore();cxO.globalAlpha=1;
}
function drawFx(OR){
  cxF.clearRect(0,0,W,H);
  if(wvis){
    const wConf=[{id:'w0',side:'right',ox:CX-OR*0.88,oy:CY-OR*0.44},{id:'w1',side:'left',ox:CX+OR*0.88,oy:CY-OR*0.44},{id:'w2',side:'right',ox:CX-OR*0.88,oy:CY+OR*0.44},{id:'w3',side:'left',ox:CX+OR*0.88,oy:CY+OR*0.44}];
    wConf.forEach(wc=>{const el=document.getElementById(wc.id);if(!el||!el.classList.contains('show'))return;const rect=el.getBoundingClientRect(),ex=wc.side==='right'?rect.left:rect.right,ey=rect.top+rect.height*0.5,mx=(wc.ox+ex)/2;cxF.beginPath();cxF.moveTo(wc.ox,wc.oy);cxF.lineTo(mx,wc.oy);cxF.lineTo(mx,ey);cxF.lineTo(ex,ey);cxF.strokeStyle=`rgba(0,229,255,${0.05+al*0.06})`;cxF.lineWidth=0.55;cxF.setLineDash([3,9]);cxF.stroke();cxF.setLineDash([]);cxF.beginPath();cxF.arc(ex,ey,2.2,0,Math.PI*2);cxF.fillStyle=`rgba(0,229,255,${0.3+al*0.28})`;cxF.fill();cxF.beginPath();cxF.arc(wc.ox,wc.oy,1.8,0,Math.PI*2);cxF.fillStyle=`rgba(0,229,255,${0.2+al*0.2})`;cxF.fill();});
  }
  if(Math.random()<0.0032){cxF.save();cxF.globalAlpha=Math.random()*0.06;cxF.fillStyle='rgba(0,229,255,1)';const gy=Math.random()*H;cxF.fillRect(0,gy,W,0.8+Math.random()*2.5);cxF.restore();}
}
const cpuH=Array.from({length:80},()=>35+Math.random()*30);
const ramH=Array.from({length:80},()=>45+Math.random()*20);
let _realMetrics=null;
function drawChart(id,data,color,fill){
  const mc=document.getElementById(id);if(!mc)return;
  const mw=mc.offsetWidth||mc.parentElement?.clientWidth||220;mc.width=mw;mc.height=parseInt(mc.getAttribute('height'))||36;
  const mctx=mc.getContext('2d'),h=mc.height;mctx.clearRect(0,0,mw,h);
  const pad=20;mctx.strokeStyle='rgba(0,229,255,0.04)';mctx.lineWidth=0.5;
  [25,50,75,100].forEach(p=>{const y=h-(p/100)*h*0.93;mctx.beginPath();mctx.moveTo(pad,y);mctx.lineTo(mw,y);mctx.stroke()});
  mctx.fillStyle='rgba(0,229,255,0.18)';mctx.font='5px Courier New';['100%','50%','0%'].forEach((l,i)=>mctx.fillText(l,0,i===0?8:i===1?h*0.53:h-1));
  const bw=(mw-pad)/data.length;data.forEach((v,i)=>{const bh=(v/100)*(h*0.92);mctx.fillStyle=fill;mctx.fillRect(pad+i*bw,h-bh,Math.max(1,bw-0.8),bh)});
  mctx.beginPath();data.forEach((v,i)=>{const x=pad+i*bw+bw/2,y=h-(v/100)*(h*0.92);i===0?mctx.moveTo(x,y):mctx.lineTo(x,y)});mctx.strokeStyle=color;mctx.lineWidth=1.1;mctx.stroke();
}
function drawCharts(){drawChart('cc',cpuH,'rgba(0,229,255,0.72)','rgba(0,229,255,0.062)');drawChart('rc',ramH,'rgba(255,200,80,0.65)','rgba(255,200,80,0.05)');}
function buildMap(){
  const w=document.getElementById('mapwrap');if(!w)return;
  w.querySelectorAll('.mdot').forEach(d=>d.remove());
  [{t:'17%',l:'12%',dl:'0s'},{t:'31%',l:'49%',dl:'.5s'},{t:'59%',l:'67%',dl:'1s'},{t:'19%',l:'79%',dl:'.3s'},{t:'63%',l:'27%',dl:'.8s'},{t:'41%',l:'91%',dl:'1.35s'}].forEach(d=>{const el=document.createElement('div');el.className='mdot';el.style.top=d.t;el.style.left=d.l;el.style.animationDelay=d.dl;w.appendChild(el);});
}
const snips=[
`<span class="ln">16</span><span class="kw">import</span> jarvis.neural <span class="kw">as</span> nn
<span class="ln">17</span>
<span class="ln">18</span><span class="kw">def</span> <span class="fn">optimize_neural_path</span>(self, data_stream):
<span class="ln">19</span>    <span class="kw">return</span> data_stream.processed
<span class="ln">20</span>
<span class="ln">21</span><span class="kw">def</span> <span class="fn">optimize_procalpath</span>(self, data_stream):
<span class="ln">22</span>    data_stream.stream = deste.data_stream
<span class="ln">23</span>    <span class="kw">return</span> data_stream.procset(self)`,
`<span class="ln">30</span>
<span class="ln">31</span><span class="cm"># Neural defense — Stark v10 —</span>
<span class="ln">32</span><span class="kw">class</span> <span class="fn">NeuralCore</span>:
<span class="ln">33</span>    version = <span class="st">"10.4-stark"</span>
<span class="ln">34</span>    <span class="kw">def</span> <span class="fn">__init__</span>(self):
<span class="ln">35</span>        self.active = <span class="kw">True</span>
<span class="ln">36</span>        self.mode = <span class="st">"stark_priority"</span>`,
`<span class="ln">42</span><span class="kw">async def</span> <span class="fn">listen_voice</span>():
<span class="ln">43</span>    audio = <span class="kw">await</span> capture_stream()
<span class="ln">44</span>    <span class="cm"># STT pipeline stark mark X</span>
<span class="ln">45</span>    text = stt.transcribe(audio)
<span class="ln">46</span>    response = <span class="kw">await</span> orq.process(
<span class="ln">47</span>        text, source=<span class="st">"voice_input"</span>)
<span class="ln">48</span>    <span class="kw">return</span> tts.speak(response)`,
];
let ci=0;
const cEl=document.getElementById('codeEl');
cEl.innerHTML=snips[0];cEl.style.transition='opacity 0.32s';
setInterval(()=>{ci=(ci+1)%snips.length;cEl.style.opacity='0';setTimeout(()=>{cEl.innerHTML=snips[ci];cEl.style.opacity='1';document.getElementById('clinf').textContent=`SL#${17+ci*12} / 060`;},340);},5000);
const DSC='01アイウエオカキABCDEFX¥§∑∂√∞≠≈ΩΨΦ';
function buildStreams(){
  ['ds-l','ds-r'].forEach(id=>{const el=document.getElementById(id);el.innerHTML='';const rows=Math.floor(H/11)+5;for(let i=0;i<rows;i++){const d=document.createElement('div');d.className='dsc';d.textContent=DSC[Math.floor(Math.random()*DSC.length)];d.style.animationDuration=(2+Math.random()*4.5)+'s';d.style.animationDelay=(Math.random()*5)+'s';el.appendChild(d);}});
}
setInterval(()=>{document.querySelectorAll('.dsc').forEach(el=>{if(Math.random()<0.11)el.textContent=DSC[Math.floor(Math.random()*DSC.length)];});},750);
const WIDS=['w0','w1','w2','w3'],RIDS=['r0','r1','r2','r3'];
function showW(i){document.getElementById(WIDS[i])?.classList.add('show');document.getElementById(RIDS[i])?.classList.add('show');wvis=true}
function closeW(i){document.getElementById(WIDS[i])?.classList.remove('show');document.getElementById(RIDS[i])?.classList.remove('show');const any=WIDS.some(id=>document.getElementById(id)?.classList.contains('show'));if(!any)wvis=false}
function showAll(){wvis=true;WIDS.forEach((_,i)=>setTimeout(()=>showW(i),i*115))}
function hideAll(){WIDS.forEach((_,i)=>closeW(i))}
// ── UTILITIES ────────────────────────────────────────────────────────────────
function escHtml(t){return String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function tsNow(){const n=new Date();return`${n.getHours().toString().padStart(2,'0')}:${n.getMinutes().toString().padStart(2,'0')}:${n.getSeconds().toString().padStart(2,'0')}`;}

// ── TOAST SYSTEM ─────────────────────────────────────────────────────────────
function showToast(msg,type='info',dur=3200){
  const c=document.getElementById('toastContainer');if(!c)return;
  const t=document.createElement('div');t.className=`toast toast-${type}`;t.textContent=msg;c.appendChild(t);
  setTimeout(()=>t.classList.add('show'),10);
  setTimeout(()=>{t.classList.remove('show');setTimeout(()=>t.remove(),350);},dur);
}

// ── MARKDOWN RENDERER v8.0 — code copy, tables, blockquotes, HR ─────────────
let _codeBlockCount=0;
function renderMd(text){
  // Extract code blocks before any escaping
  const blocks=[];
  text=text.replace(/```([\w]*)\n?([\s\S]*?)```/g,(_,lang,code)=>{
    const id='cb'+(++_codeBlockCount);
    blocks.push({id,lang:lang||'',code});
    return '%%CODEBLOCK_'+id+'%%';
  });
  let t=escHtml(text);
  // Restore code blocks with copy button
  blocks.forEach(b=>{
    const langL=b.lang?`<span class="md-code-lang">${escHtml(b.lang)}</span>`:'';
    const cHtml=escHtml(b.code);
    t=t.replace('%%CODEBLOCK_'+b.id+'%%',
      `<div class="md-code-wrap">${langL}<button class="md-copy-btn" onclick="copyCodeBlock(this,'${b.id}')">COPIAR</button><pre class="md-code" id="${b.id}">${cHtml}</pre></div>`);
  });
  // Inline code
  t=t.replace(/`([^`\n]+)`/g,'<code class="md-inline">$1</code>');
  // Bold + italic
  t=t.replace(/\*\*\*([^*\n]+)\*\*\*/g,'<strong><em>$1</em></strong>');
  t=t.replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>');
  t=t.replace(/\*([^*\n]+)\*/g,'<em>$1</em>');
  // Headers
  t=t.replace(/^### (.+)$/gm,'<span class="md-h3">$1</span>');
  t=t.replace(/^## (.+)$/gm,'<span class="md-h2">$1</span>');
  t=t.replace(/^# (.+)$/gm,'<span class="md-h1">$1</span>');
  // Lists
  t=t.replace(/^[\-\*] (.+)$/gm,'<span class="md-li">• $1</span>');
  t=t.replace(/^\d+\. (.+)$/gm,'<span class="md-li">◆ $1</span>');
  // Blockquotes
  t=t.replace(/^&gt; (.+)$/gm,'<div class="md-blockquote">$1</div>');
  // Horizontal rule
  t=t.replace(/^---+$/gm,'<hr class="md-hr">');
  // Newlines
  t=t.replace(/\n/g,'<br>');
  return t;
}
function copyCodeBlock(btn,id){
  const el=document.getElementById(id);if(!el)return;
  const code=el.innerText||el.textContent;
  if(navigator.clipboard){navigator.clipboard.writeText(code).then(()=>{
    btn.textContent='✓ COPIADO';btn.classList.add('copied');
    setTimeout(()=>{btn.textContent='COPIAR';btn.classList.remove('copied');},2200);
  }).catch(()=>{});}
}

// ── CONVERSATION HISTORY (Panel 0) ───────────────────────────────────────────
const convHistory=[];
let _thinkingEntryId=null;
function addConvEntry(role,text){
  const id='ce_'+Date.now();
  convHistory.push({id,role,text,ts:tsNow()});
  if(convHistory.length>40)convHistory.shift();
  renderConvPanel();
  document.getElementById('convCount').textContent=convHistory.length+' msgs';
  return id;
}
function removeThinking(){
  if(_thinkingEntryId){
    const idx=convHistory.findIndex(e=>e.id===_thinkingEntryId);
    if(idx>=0)convHistory.splice(idx,1);
    _thinkingEntryId=null;renderConvPanel();
  }
}
function renderConvPanel(){
  const el=document.getElementById('convLog');if(!el)return;
  el.innerHTML=convHistory.map(e=>{
    const isUser=e.role==='user';
    const txt=e.thinking?`<div class="conv-thinking"><div class="think-dot"></div><div class="think-dot"></div><div class="think-dot"></div></div>`:
      `<span class="${isUser?'conv-txt-user':'conv-txt-jarvis'}">${escHtml((e.text||'').substring(0,140)+(e.text&&e.text.length>140?'…':''))}</span>`;
    return`<div class="conv-entry" id="${e.id}"><span class="conv-ts">${e.ts}</span><span class="${isUser?'conv-who-user':'conv-who-jarvis'}">${isUser?'VOCÊ':'JAR'}</span>${txt}</div>`;
  }).join('');
  el.scrollTop=el.scrollHeight;
}

// ── SYSTEM EVENTS FEED (Panel 1) ─────────────────────────────────────────────
const sysEvents=[];
function addEvent(type,msg){
  sysEvents.push({type,msg,ts:tsNow()});
  if(sysEvents.length>50)sysEvents.shift();
  renderEventsPanel();
}
function renderEventsPanel(){
  const el=document.getElementById('evtLog');if(!el)return;
  el.innerHTML=sysEvents.slice().reverse().slice(0,25).map(e=>
    `<div class="evt-entry evt-${escHtml(e.type)}"><span class="evt-ts">${e.ts}</span><span class="evt-msg">${escHtml(e.msg)}</span></div>`
  ).join('');
}

// ── ELAPSED TIME ─────────────────────────────────────────────────────────────
let _reqStart=0,_elTimer=null;
function startElapsed(){_reqStart=Date.now();_elTimer=setInterval(()=>{const el=document.getElementById('elapsed');if(el)el.textContent=((Date.now()-_reqStart)/1000).toFixed(1)+'s';},100);}
function stopElapsed(){clearInterval(_elTimer);_elTimer=null;const el=document.getElementById('elapsed');if(el)el.textContent=((Date.now()-_reqStart)/1000).toFixed(1)+'s';}

// ── RESPONSE PANEL ──
const resPanel=document.getElementById('respanel');
const resText=document.getElementById('restext');
let hideResTimer=null;
let _fullResponseText='';
function showResponse(text){
  _fullResponseText=text;resText.innerHTML=renderMd(text);resPanel.classList.add('show');
  clearTimeout(hideResTimer);hideResTimer=setTimeout(()=>resPanel.classList.remove('show'),22000);
}
function appendResponse(chunk){
  _fullResponseText+=chunk;resText.innerHTML=renderMd(_fullResponseText);resPanel.classList.add('show');
  clearTimeout(hideResTimer);resPanel.scrollTop=resPanel.scrollHeight;
}
function clearResponse(){_fullResponseText='';resText.innerHTML='';clearTimeout(hideResTimer);hideResTimer=setTimeout(()=>resPanel.classList.remove('show'),400);}
function copyResponse(){
  const text=resText.innerText||resText.textContent;
  if(navigator.clipboard){navigator.clipboard.writeText(text).then(()=>showToast('COPIADO!','success'));}
  else{const ta=document.createElement('textarea');ta.value=text;document.body.appendChild(ta);ta.select();document.execCommand('copy');ta.remove();showToast('COPIADO!','success');}
}
// ── SPEAKING STATE ──
function setSpeaking(v,dur){
  speaking=v;
  const sb=document.getElementById('sbar'),sl=document.getElementById('stlive');
  const bls=document.getElementById('blstat'),lr=document.getElementById('lring');
  if(v){sb.classList.add('on');lr.classList.add('on');sl.textContent='STATUS: ONLINE (FALANDO)';bls.textContent='STATUS: FALANDO';if(dur){clearTimeout(stimer);stimer=setTimeout(()=>setSpeaking(false),dur)}}
  else{sb.classList.remove('on');lr.classList.remove('on');sl.textContent='STATUS: AGUARDANDO';bls.textContent='STATUS: ONLINE';}
}
// ── SEND MESSAGE via SSE stream ──
let currentStream=null;
function sendMessage(msg){
  if(!msg.trim())return;
  if(currentStream){currentStream.abort();currentStream=null;}
  clearResponse();resPanel.classList.add('show');
  document.getElementById('stlive').textContent='STATUS: PROCESSANDO...';
  document.getElementById('sbar').classList.add('on');
  document.getElementById('lring').classList.add('on');
  startElapsed();
  // Add user entry to conv log
  addConvEntry('user',msg);
  // Add thinking dots for JARVIS
  const thinkId='ce_think_'+Date.now();
  convHistory.push({id:thinkId,role:'jarvis',text:'',thinking:true,ts:tsNow()});
  _thinkingEntryId=thinkId;renderConvPanel();
  addEvent('ai',`QUERY: ${msg.substring(0,60)}${msg.length>60?'…':''}`);
  const ctrl=new AbortController();currentStream=ctrl;
  fetch(`${API_URL}/chat/stream`,{
    method:'POST',signal:ctrl.signal,
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({message:msg,session_id:_sessionId||'jarvis'})
  }).then(async r=>{
    const reader=r.body.getReader(),dec=new TextDecoder();
    let buf='',gotFirst=false;
    while(true){
      const{done,value}=await reader.read();if(done)break;
      buf+=dec.decode(value,{stream:true});
      const lines=buf.split('\n');buf=lines.pop();
      for(const line of lines){
        if(!line.startsWith('data:'))continue;
        try{
          const ev=JSON.parse(line.slice(5).trim());
          if(ev.type==='token'){
            if(!gotFirst){removeThinking();gotFirst=true;}
            appendResponse(ev.content);
          }else if(ev.type==='turbo'){
            removeThinking();showResponse(ev.response);setSpeaking(true,3500);
            addConvEntry('jarvis',ev.response);
            addEvent('ok',`RESP [${ev.tier||'turbo'}]: ${ev.response.substring(0,60)}…`);
          }else if(ev.type==='done'){
            stopElapsed();setSpeaking(true,3500);currentStream=null;
            if(_fullResponseText){addConvEntry('jarvis',_fullResponseText);}
            addEvent('ok',`CONCLUÍDO em ${((Date.now()-_reqStart)/1000).toFixed(1)}s`);
          }else if(ev.type==='error'){
            removeThinking();showResponse('⚠ Erro: '+ev.detail);setSpeaking(false);currentStream=null;
            stopElapsed();addEvent('err','ERRO: '+ev.detail.substring(0,60));
            showToast('Erro na resposta','error');
          }
        }catch(e){}
      }
    }
  }).catch(err=>{
    removeThinking();
    if(err.name!=='AbortError'){showResponse('Conexão com backend falhou.');setSpeaking(false);addEvent('err','CONEXÃO FALHOU');showToast('Backend offline','error');}
    currentStream=null;stopElapsed();
  });
}
// ── WEBSOCKET ──
let ws=null,wsRetry=0,_wsPingSent=0,_wsMaxRetry=12,_secAlertCount=0;
function _wsBackoff(n){return Math.min(30000,500*Math.pow(2,n)+Math.random()*300);}
function _wsSetStatus(state,color){
  const el=document.getElementById('stws');
  if(!el)return;
  el.textContent='WS: '+state;
  el.style.color=color||'';
}
function connectWS(){
  if(wsRetry>_wsMaxRetry){
    _wsSetStatus('ERRO','rgba(255,107,107,0.8)');
    addEvent('err','WS: falhou após '+_wsMaxRetry+' tentativas — recarregue');
    return;
  }
  try{
    ws=new WebSocket(_wsUrl());
    ws.onopen=()=>{
      _wsSetStatus('ONLINE','rgba(78,255,145,0.85)');wsRetry=0;
      addEvent('ok','WebSocket conectado');
      // Measure ping latency
      _wsPingSent=Date.now();
      ws.send(JSON.stringify({type:'ping'}));
    };
    ws.onmessage=(ev)=>{
      try{
        const m=JSON.parse(ev.data);
        if(m.type==='ping'){ws.send(JSON.stringify({type:'pong'}));return;}
        if(m.type==='pong'||m.status==='pong'){
          const lat=Date.now()-_wsPingSent;
          document.getElementById('sWsLatency').textContent=lat+'ms';
          return;
        }
        if(m.session_id&&m.session_id!==_sessionId){
          _sessionId=m.session_id;
          localStorage.setItem('jarvis_session',_sessionId);
          document.getElementById('convSession').textContent='SESSÃO: '+_sessionId.substring(0,12)+'…';
          document.getElementById('sSessionVal').textContent=_sessionId.substring(0,20);
        }
        if(m.status==='speaking'){setSpeaking(true);
          if(m.message){showResponse(m.message);addConvEntry('jarvis',m.message);
            // Toca no NAVEGADOR para o orb poder analisar a voz. Se o backend
            // tambem estiver falando (JARVIS_VOICE_ENABLED=true), desligue um
            // dos dois para nao ouvir em dobro.
            window.JarvisTTS&&window.JarvisTTS.falar(m.message);
          }
          addEvent('voice','TTS: FALANDO');}
        if(m.status==='thinking'){document.getElementById('stlive').textContent='STATUS: PROCESSANDO...';addEvent('ai','PROCESSANDO...');}
        if(m.status==='idle'){if(!currentStream)setSpeaking(false);}
        if(m.status==='error'){setSpeaking(false);addEvent('err','WS ERRO: '+(m.message||'desconhecido'));}
        if(m.type==='token'&&m.content){appendResponse(m.content);}
        // ── Laço de agente: atividade e confirmação ──────────────────────────
        if(m.type==='agent_event'){_onAgentEvent(m);return;}
        if(m.type==='agent_confirm'){_pedirConfirmacao(m);return;}
        if(m.type==='agent_busy'){showToast(m.message||'Tarefa em andamento.','warn');addEvent('warn','MENSAGEM NÃO PROCESSADA — tarefa em andamento');return;}
        if(m.type==='agent_confirm_timeout'){_fecharConfirmacao();addEvent('warn','CONFIRMAÇÃO EXPIROU — ação recusada');return;}
        if(m.type==='agent_confirm_ack'){
          if(!m.handled)addEvent('warn','CONFIRMAÇÃO JÁ EXPIRADA — ação recusada');
          return;
        }
        // ── Alerta de segurança do Guardian ──────────────────────────────────
        if(m.type==='security_alert'){_onSecurityAlert(m);}
      }catch(e){}
    };
    ws.onclose=(ev)=>{
      const clean=ev.wasClean;
      _wsSetStatus('RECONECTANDO...','rgba(255,209,102,0.8)');
      wsRetry++;
      const delay=_wsBackoff(wsRetry);
      addEvent('warn',`WS desconectado${clean?'':', inesperado'} — retry #${wsRetry} em ${Math.round(delay/1000)}s`);
      setTimeout(connectWS,delay);
    };
    ws.onerror=()=>{_wsSetStatus('ERRO','rgba(255,107,107,0.8)');ws.close();};
  }catch(e){
    _wsSetStatus('FALHA','rgba(255,107,107,0.7)');
    setTimeout(connectWS,_wsBackoff(wsRetry));
  }
}
function reconnectWS(){wsRetry=0;if(ws){try{ws.close();}catch(e){}}connectWS();}
// ── HEALTH POLL ──
async function pollHealth(){
  try{
    const r=await fetch(`${API_URL}/health`,{signal:AbortSignal.timeout(2000)});
    if(r.ok){const d=await r.json();
      document.getElementById('stuptime').textContent='UP: '+(d.uptime||'—');
      document.getElementById('blstat').textContent='STATUS: '+(d.status==='ok'?'ONLINE':'DEGRADED');
      if(d.status!=='ok')document.getElementById('blstat').style.color='rgba(255,107,107,0.7)';
      else document.getElementById('blstat').style.color='';
    }
  }catch(e){}
}
setInterval(pollHealth,8000);pollHealth();
// ── SECURITY ALERT HANDLER ────────────────────────────────────────────────────
const _THREAT_COLORS={critical:'rgba(255,42,74,0.9)',high:'rgba(255,140,0,0.88)',medium:'rgba(255,209,102,0.85)',low:'rgba(0,229,255,0.7)'};
function _onSecurityAlert(m){
  const lvl=m.level||'high';
  const color=_THREAT_COLORS[lvl]||_THREAT_COLORS.high;
  const typeLabel=(m.threat||'THREAT').replace(/_/g,' ').toUpperCase();
  _secAlertCount++;
  // Badge de contador de alertas
  const badge=document.getElementById('secAlertBadge');
  if(badge){badge.textContent=_secAlertCount;badge.style.display='inline-block';}
  // Toast de alerta
  showToast(`⚠ AMEAÇA [${lvl.toUpperCase()}] ${typeLabel} — ${m.ip||'?'}`,'error');
  // Adicionar no feed de eventos
  addEvent('err',`[SECURITY/${lvl.toUpperCase()}] ${typeLabel} — IP: ${m.ip||'?'} — ${m.path||''}`);
  // Se for crítico/alto: ativar modo alerta visual
  if(lvl==='critical'||lvl==='high'){
    document.body.classList.add('alert');
    clearTimeout(window._alertTimer);
    window._alertTimer=setTimeout(()=>document.body.classList.remove('alert'),8000);
  }
  // Atualizar indicador de segurança no painel de settings se existir
  const ss=document.getElementById('sSecScore');
  if(ss&&(lvl==='critical'||lvl==='high')){
    ss.textContent=`ALERTA ${_secAlertCount}x — ${typeLabel}`;
    ss.style.color=color;
  }
  // Registrar no console de ameaças (se existir)
  const tc=document.getElementById('threatConsole');
  if(tc){
    const row=document.createElement('div');
    row.style.cssText=`padding:2px 4px;border-left:2px solid ${color};margin:1px 0;font-size:clamp(5px,0.55vw,6.5px)`;
    row.textContent=`[${new Date().toLocaleTimeString()}] ${lvl.toUpperCase()} ${typeLabel} ${m.ip||''}`;
    tc.prepend(row);
    if(tc.children.length>50)tc.lastChild.remove();
  }
}
// ── COMMAND SYSTEM ──
const cmdInput=document.getElementById('cmdinput'),cmdText=document.getElementById('cmdtext');
const CMDS={
  'mostrar codigo':()=>{showW(0);setSpeaking(true,3000)},
  'show code':()=>{showW(0);setSpeaking(true,3000)},
  'mostrar mapa':()=>{showW(1);setSpeaking(true,2500)},
  'show map':()=>{showW(1);setSpeaking(true,2500)},
  'mostrar dados':()=>{showW(2);setSpeaking(true,2500)},
  'show data':()=>{showW(2);setSpeaking(true,2500)},
  'mostrar protocolos':()=>{showW(3);setSpeaking(true,2500)},
  'show protocols':()=>{showW(3);setSpeaking(true,2500)},
  'mostrar tudo':()=>{showAll();setSpeaking(true,4000)},
  'show all':()=>{showAll();setSpeaking(true,4000)},
  'fechar':()=>{hideAll();setSpeaking(false)},
  'hide':()=>{hideAll();setSpeaking(false)},
  'alerta':()=>setAlert(true),'alert':()=>setAlert(true),
  'normal':()=>setAlert(false),
  'analise':()=>{showAll();setSpeaking(true,5000)},
  'analyze':()=>{showAll();setSpeaking(true,5000)},
};
function runCmd(raw){
  const cmd=raw.trim().toLowerCase();
  if(!cmd)return;
  _hasInteracted=true;
  let ran=false;
  for(const key in CMDS){if(cmd.includes(key)){CMDS[key]();addConvEntry('user',raw);addEvent('info','CMD: '+key);ran=true;break}}
  if(!ran&&cmd.length>2){sendMessage(raw);showAll();}
}
function initSpeech(){
  const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR){document.getElementById('hint').textContent='[ VOZ NÃO SUPORTADA — USE CHROME ]';return;}
  const recognition=new SR();recognition.lang='pt-BR';recognition.continuous=true;recognition.interimResults=true;recognition.maxAlternatives=1;
  recognition.onstart=()=>{document.getElementById('hint').textContent='[ ◉ OUVINDO... ]';};
  recognition.onresult=(e)=>{for(let i=e.resultIndex;i<e.results.length;i++){const transcript=e.results[i][0].transcript;cmdText.value=transcript;cmdInput.classList.add('show');if(e.results[i].isFinal){addEvent('voice','SPEECH: '+transcript.substring(0,60));runCmd(transcript);setTimeout(()=>cmdInput.classList.remove('show'),1600);}}};
  recognition.onerror=(e)=>{if(e.error==='no-speech'||e.error==='aborted')return};
  recognition.onend=()=>{setTimeout(()=>{try{recognition.start()}catch(e){}},250)};
  try{recognition.start()}catch(e){}
}
// ── VOICE AUDIO CAPTURE & PLAYBACK ──
let mediaRecorder=null,audioChunks=[],audioStream=null,isRecording=false;
async function startRecording(){
  try{
    if(!audioStream)audioStream=await navigator.mediaDevices.getUserMedia({audio:true});
    const ac=new(window.AudioContext||window.webkitAudioContext)();
    mediaRecorder=new MediaRecorder(audioStream);
    audioChunks=[];
    mediaRecorder.ondataavailable=(e)=>audioChunks.push(e.data);
    mediaRecorder.onstart=()=>{isRecording=true;document.getElementById('hint').textContent='[ ◉ GRAVANDO... ]';setSpeaking(false);document.getElementById('pttBtn').classList.add('active');const wc=document.getElementById('waveCanvas');if(wc)wc.classList.add('show');addEvent('voice','GRAVANDO ÁUDIO...');};
    mediaRecorder.onstop=async()=>{isRecording=false;const audioBlob=new Blob(audioChunks,{type:'audio/wav'});await sendVoiceCommand(audioBlob);};
    mediaRecorder.start();
    setTimeout(()=>{if(isRecording)stopRecording();},12000);
  }catch(e){console.error('Erro ao gravar:',e);document.getElementById('hint').textContent='[ ✗ ERRO MICROFONE ]';}
}
function stopRecording(){
  if(mediaRecorder&&isRecording){
    mediaRecorder.stop();
    document.getElementById('hint').textContent='[ PROCESSANDO... ]';
    document.getElementById('pttBtn').classList.remove('active');
    const wc=document.getElementById('waveCanvas');if(wc)wc.classList.remove('show');
  }
}
async function sendVoiceCommand(audioBlob){
  addEvent('voice','ÁUDIO ENVIADO: '+Math.round(audioBlob.size/1024)+'KB');
  startElapsed();
  try{
    const fd=new FormData();
    fd.append('audio',audioBlob,'command.wav');
    fd.append('session_id',_sessionId||'voice');
    const r=await fetch(`${API_URL}/voice/command`,{method:'POST',body:fd});
    if(!r.ok){
      showResponse('⚠ Erro de voz: '+r.status);document.getElementById('hint').textContent='[ ✗ ERRO ]';
      addEvent('err','VOICE ERRO HTTP: '+r.status);stopElapsed();showToast('Erro de voz','error');return;
    }
    const d=await r.json();
    stopElapsed();
    if(d.transcript){addConvEntry('user',d.transcript);addEvent('voice','STT: '+d.transcript.substring(0,60));}
    if(d.response){showResponse(d.response);addConvEntry('jarvis',d.response);addEvent('ok','VOZ RESP: '+d.response.substring(0,60));}
    else showResponse('Comando processado');
    const audioSrc=d.audio_url||d.audio_path;
    if(audioSrc){await playVoiceResponse(audioSrc);}
    document.getElementById('hint').textContent='[ SPACE: VOZ | ENTER: TEXTO ]';
  }catch(e){
    stopElapsed();console.error('Erro enviando áudio:',e);
    showResponse('⚠ Erro de conexão');document.getElementById('hint').textContent='[ ✗ ERRO ]';
    addEvent('err','VOICE FALHOU: '+e.message);showToast('Erro de voz','error');
  }
}
async function playVoiceResponse(audioPath){
  try{
    setSpeaking(true,5000);
    const url=`${API_URL}${audioPath.startsWith('/')?'':'/'}${audioPath}`;
    const audio=new Audio();
    audio.onended=()=>setSpeaking(false);
    audio.onerror=()=>{console.error('Erro tocando áudio');setSpeaking(false);};
    audio.src=url;
    await audio.play();
  }catch(e){console.error('Erro ao tocar áudio:',e);setSpeaking(false);}
}
document.addEventListener('keydown',e=>{
  if(e.target===cmdText)return;
  // Ctrl+K — foco no chat input
  if(e.ctrlKey&&e.key==='k'){e.preventDefault();const ci=cmdText||document.querySelector('textarea,input[type=text]');if(ci){ci.focus();ci.scrollIntoView({behavior:'smooth'});}return}
  // Ctrl+/ — atalhos de ajuda
  if(e.ctrlKey&&e.key==='/'){e.preventDefault();showToast('ATALHOS: Espaço=voz 1-4=paineis Esc=fechar Ctrl+K=chat Ctrl+L=limpar Ctrl+R=reconectar WS','ok');return}
  // Ctrl+L — limpar chat
  if(e.ctrlKey&&e.key==='l'){e.preventDefault();clearResponse();addEvent('ok','Chat limpo');return}
  // Ctrl+R — reconectar WebSocket (sem recarregar a página)
  if(e.ctrlKey&&e.key==='r'&&!e.shiftKey){e.preventDefault();reconnectWS();addEvent('ok','Reconectando WS...');return}
  if(e.target!==document.body&&e.target.tagName!=='BODY')return;
  if(e.key===' '){e.preventDefault();if(isRecording){stopRecording();}else{startRecording();showAll();}return}
  if(e.key==='Escape'){cmdInput.classList.remove('show');hideAll();setSpeaking(false);return}
  if(e.key==='a'||e.key==='A'){setAlert(!alertMode);return}
  if(e.key>='1'&&e.key<='4'){const i=parseInt(e.key)-1;const el=document.getElementById(WIDS[i]);if(el?.classList.contains('show'))closeW(i);else{showW(i);setSpeaking(true,2500)};return}
  if(e.key==='0'){hideAll();setSpeaking(false)}
});
cmdText.addEventListener('keydown',e=>{
  if(e.key==='Enter'){runCmd(cmdText.value);cmdInput.classList.remove('show')}
  if(e.key==='Escape'){cmdInput.classList.remove('show')}
  e.stopPropagation();
});
function setAlert(on){alertMode=on;document.body.classList.toggle('alert',on);if(on){document.getElementById('stlive').textContent='⚠ ALERTA: AMEAÇA DETECTADA';setSpeaking(true)}}
async function fetchMetrics(){
  try{
    const d=await fetch(`${API_URL}/metrics`,{signal:AbortSignal.timeout(2500)}).then(r=>r.json());
    if(!d.error)_realMetrics=d;
  }catch(e){}
}
setInterval(fetchMetrics,3000);fetchMetrics();

let lm=0;
function updateMetrics(ts){
  if(ts-lm<1600)return;lm=ts;
  let c,r,n,dk;
  if(_realMetrics){
    c=_realMetrics.cpu_percent||0;
    r=_realMetrics.ram_percent||0;
    n=Math.min((_realMetrics.net_recv_mb||0),100);
    dk=_realMetrics.disk_percent||0;
    const el=document.getElementById('blstat');
    if(el&&_realMetrics.ram_used_gb!=null)el.textContent=`RAM: ${_realMetrics.ram_used_gb}/${_realMetrics.ram_total_gb}GB | DISK: ${_realMetrics.disk_free_gb}GB livre`;
  }else{
    c=Math.max(10,Math.min(90,cpuH[cpuH.length-1]+(Math.random()-0.45)*12));
    r=Math.max(30,Math.min(85,ramH[ramH.length-1]+(Math.random()-0.5)*5));
    n=Math.max(0,Math.min(60,Math.random()*40));
    dk=50;
  }
  cpuH.push(c);cpuH.shift();ramH.push(r);ramH.shift();
  const cv=Math.round(c),rv=Math.round(r),nv=parseFloat(n.toFixed(1)),dv=Math.round(dk);
  document.getElementById('cpuv').textContent=cv+'%';
  document.getElementById('ramv').textContent=rv+'%';
  document.getElementById('netv').textContent=nv+'MB';
  document.getElementById('cpuv2').textContent=cv+'%';
  document.getElementById('ramv2').textContent=rv+'%';
  document.getElementById('cpubar').style.width=cv+'%';
  document.getElementById('rambar').style.width=rv+'%';
  document.getElementById('netbar').style.width=Math.min(n*2,100)+'%';
  const db=document.getElementById('diskbar');if(db)db.style.width=dv+'%';
  const dv2=document.getElementById('diskv');if(dv2)dv2.textContent=dv+'%';
  // Net stats
  if(_realMetrics){
    const ns=document.getElementById('netSent');if(ns)ns.textContent='↑ '+(_realMetrics.net_sent_mb||0)+'MB';
    const nr=document.getElementById('netRecv');if(nr)nr.textContent='↓ '+(_realMetrics.net_recv_mb||0)+'MB';
    const pc=document.getElementById('procCount');if(pc)pc.textContent='PROCS: '+(_realMetrics.process_count||'—');
    // Process list
    if(_realMetrics.top_processes&&_realMetrics.top_processes.length>0){
      const pl=document.getElementById('procList');
      if(pl)pl.innerHTML=_realMetrics.top_processes.map(p=>`<div class="prow"><span class="pname">${escHtml(p.name.substring(0,20))}</span><span class="pcpu">${p.cpu}%</span></div>`).join('');
    }
  }
  drawCharts();
}
function loop(now){
  const dt=Math.min((now-lastT)/1000,0.05);lastT=now;t+=dt;
  const OR=R*(1+(0.5+0.5*Math.sin(t*1.78))*0.022+al*0.32);
  drawStars();drawRings(OR);drawOrb();drawFx(OR);updateMetrics(now);
  if(isRecording)drawWaveform();
  requestAnimationFrame(loop);
}
resize();initMic();initSpeech();connectWS();
lastT=performance.now();requestAnimationFrame(loop);

// ── Status real-time: modelo + uptime ───────────────────────────────────────
async function fetchStatus(){
  try{
    const d=await fetch(`${API_URL}/status`,{cache:'no-store',signal:AbortSignal.timeout(2000)}).then(r=>r.json());
    const sl=document.getElementById('stlive');
    if(sl&&!speaking){
      const up=Math.floor((d.uptime_seconds||0)/60);
      sl.textContent=`ONLINE | ${d.model||'?'} | UP: ${up}min`;
    }
  }catch(e){
    const sl=document.getElementById('stlive');
    if(sl&&!speaking)sl.textContent='CONECTANDO...';
  }
}
setInterval(fetchStatus,15000);fetchStatus();

// ── MELHORIA 2: Histórico de comandos com seta para cima ──
const cmdHistory=[];let cmdHistIdx=-1;
if(cmdText){
  const _origKeydown=cmdText.onkeydown;
  cmdText.addEventListener('keydown',e=>{
    if(e.key==='ArrowUp'){
      e.preventDefault();
      if(cmdHistIdx<cmdHistory.length-1){cmdHistIdx++;cmdText.value=cmdHistory[cmdHistIdx]||'';}
    } else if(e.key==='ArrowDown'){
      e.preventDefault();
      if(cmdHistIdx>0){cmdHistIdx--;cmdText.value=cmdHistory[cmdHistIdx]||'';}
      else{cmdHistIdx=-1;cmdText.value='';}
    }
  });
  const _origRunCmd=window.runCmd;
  window.runCmd=function(msg){
    if(msg&&msg.trim()){cmdHistory.unshift(msg.trim());if(cmdHistory.length>50)cmdHistory.pop();cmdHistIdx=-1;}
    return _origRunCmd(msg);
  };
}

// ── MELHORIA 3: Indicador visual de escutando ──
function setListeningVisual(on){
  const ring=document.getElementById('lring');
  if(ring){if(on)ring.classList.add('on');else ring.classList.remove('on');}
}

// ── F1 = status rápido ──
document.addEventListener('keydown',e=>{
  if(e.key==='F1'){e.preventDefault();runCmd('status');}
},{capture:true});

// ── WAVEFORM CANVAS ───────────────────────────────────────────────────────────
function drawWaveform(){
  const wc=document.getElementById('waveCanvas');if(!wc||!anl)return;
  const wctx=wc.getContext('2d');
  const wd=wc.offsetWidth||300,wh=22;
  wc.width=wd;wc.height=wh;
  const td=new Uint8Array(anl.frequencyBinCount);
  anl.getByteTimeDomainData(td);
  wctx.clearRect(0,0,wd,wh);
  wctx.beginPath();
  const sw=wd/td.length;let x=0;
  for(let i=0;i<td.length;i++){const v=td[i]/128,y=v*(wh/2);i===0?wctx.moveTo(x,y):wctx.lineTo(x,y);x+=sw;}
  wctx.strokeStyle='rgba(0,229,255,0.75)';wctx.lineWidth=1;wctx.stroke();
}

// ── PTT TOGGLE ───────────────────────────────────────────────────────────────
function togglePTT(){if(isRecording)stopRecording();else{startRecording();showAll();}}

// ── SETTINGS PANEL ───────────────────────────────────────────────────────────
function toggleSettings(){
  const p=document.getElementById('settingsPanel');
  if(!p)return;
  const showing=p.classList.toggle('show');
  if(showing){
    // Populate live values
    const sl=document.getElementById('sSessionVal');if(sl)sl.textContent=_sessionId.substring(0,24)||'—';
    fetchSettings();
  }
}
async function fetchSettings(){
  // Fetch security score
  try{
    // Tenta /security/guardian (guardian score) ou fallback para /security/status (health score)
    let sec=null;
    try{sec=await fetch(`${API_URL}/security/guardian`,{signal:AbortSignal.timeout(2000)}).then(r=>r.ok?r.json():null);}catch(e2){}
    if(!sec)try{sec=await fetch(`${API_URL}/security/status`,{signal:AbortSignal.timeout(2000)}).then(r=>r.json());}catch(e2){}
    if(sec){
      const ss=document.getElementById('sSecScore');
      const score=sec.security_score!==undefined?sec.security_score:null;
      const level=sec.level||sec.status||'—';
      const lockdown=sec.lockdown?'🔒 LOCKDOWN':'';
      if(ss){
        ss.textContent=(score!==null?score+'/100 — ':'')+level+(lockdown?' '+lockdown:'');
        const good=level==='MAXIMUM'||level==='active'||score>=80;
        ss.style.color=good?'rgba(78,255,145,0.85)':score>=50?'rgba(255,209,102,0.8)':'rgba(255,107,107,0.8)';
      }
      if(score!==null)addEvent(score>=80?'ok':'warn',`SEGURANÇA: ${score}/100 ${lockdown}`);
    }
  }catch(e){}
  try{
    const d=await fetch(`${API_URL}/system/info`,{signal:AbortSignal.timeout(2500)}).then(r=>r.json());
    const m=document.getElementById('sModelVal');if(m)m.textContent=d.model||'—';
    const mn=document.getElementById('modelName');if(mn)mn.textContent=(d.model||'—').replace('mistral:','m:').replace('llama','ll').replace('qwen2','qw').substring(0,12);
    const o=document.getElementById('sOllamaVal');if(o)o.textContent=d.ollama_url||'—';
    const v=document.getElementById('sVoiceVal');if(v)v.textContent=(d.voice_enabled?'ATIVO':'INATIVO')+' | '+d.tts_voice;
    const up=document.getElementById('sUptimeVal');if(up)up.textContent=d.uptime_human||'—';
    const ac=document.getElementById('agentCount');if(ac)ac.textContent=(d.agent_count||0)+' AGENTES';
    addEvent('ok','Sistema: '+d.platform+' | '+d.ram_used_gb+'GB/'+d.ram_total_gb+'GB RAM');
  }catch(e){
    // Fallback to /status
    try{
      const d=await fetch(`${API_URL}/status`,{signal:AbortSignal.timeout(2000)}).then(r=>r.json());
      const m=document.getElementById('sModelVal');if(m)m.textContent=d.model||'—';
      const mn=document.getElementById('modelName');if(mn)mn.textContent=d.model||'—';
    }catch(e2){}
  }
}  // end fetchSettings

// ── CLEAR CONVERSATION ────────────────────────────────────────────────────────
function clearConversation(){
  convHistory.length=0;sysEvents.length=0;
  renderConvPanel();renderEventsPanel();
  clearResponse();
  document.getElementById('convCount').textContent='0 msgs';
  toggleSettings();
  showToast('CONVERSA LIMPA','warn');
  addEvent('warn','Histórico limpo pelo utilizador');
}

// ── FETCH AGENT STATUS (Panel 3) ─────────────────────────────────────────────
async function fetchAgentStatus(){
  try{
    const d=await fetch(`${API_URL}/agents/`,{signal:AbortSignal.timeout(3000)}).then(r=>r.json());
    const el=document.getElementById('agentList');if(!el)return;
    const agents=d.agents||d.registered||[];
    if(agents.length>0){
      el.innerHTML=agents.slice(0,8).map(a=>{
        const name=a.name||a.role||a.id||'Agent';
        const status=(a.status||'run').toUpperCase();
        const cls=status==='RUN'?'run':status==='STN'?'stn':'wrn';
        return`<div class="pi"><span>${escHtml(name.substring(0,28))}</span><span class="pbadge ${cls}">${status}</span></div>`;
      }).join('');
      const ac=document.getElementById('agentCount');if(ac)ac.textContent=agents.length+' AGENTES';
    }
  }catch(e){}
}
setInterval(fetchAgentStatus,45000);
setTimeout(fetchAgentStatus,3000);

// ── BOOT EVENTS ───────────────────────────────────────────────────────────────
setTimeout(()=>{
  addEvent('ok','JARVIS v7.0 FORTRESS — SISTEMA ONLINE');
  addEvent('ok','Segurança: InputGuard + AuditLog + RateLimit + WSGuard');
  addEvent('info','Backend: '+API_URL);
  addEvent('info','Sessão: '+(_sessionId.substring(0,16)||'nova'));
  // Show all panels on boot briefly then close
  showAll();
  setTimeout(()=>{if(!_hasInteracted){hideAll();}},8000);
  fetchSettings();
  // Periodic WS ping for latency
  setInterval(()=>{if(ws&&ws.readyState===1){_wsPingSent=Date.now();ws.send(JSON.stringify({type:'ping'}));}},30000);
},800);
let _hasInteracted=false;
document.addEventListener('keydown',()=>{_hasInteracted=true;},{once:true});
document.addEventListener('click',()=>{_hasInteracted=true;},{once:true});

// ── FEEDBACK SYSTEM ──────────────────────────────────────────────────────────
function showFeedback(){const fr=document.getElementById('feedbackRow');if(fr)fr.style.display='flex';}
function hideFeedback(){const fr=document.getElementById('feedbackRow');if(fr)fr.style.display='none';}
async function sendFeedback(type){
  const text=_fullResponseText||'';
  if(!text)return;
  const btns=document.querySelectorAll('.fb-btn');
  btns.forEach(b=>b.classList.add('active'));
  try{
    if(type==='remember'||type==='forget'){
      const action=type==='remember'?'SALVAR':'ESQUECER';
      const msg=type==='remember'
        ?`Lembra desta resposta: "${text.substring(0,200)}"`
        :`Esqueça informações sobre: "${text.substring(0,100)}"`;
      await fetch(`${API_URL}/chat`,{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({message:msg,session_id:_sessionId||'jarvis'})
      });
      showToast(type==='remember'?'✓ Memorizado!':'✦ Esquecido!','success');
    } else {
      // Logar feedback localmente (futuramente integrar ao learning loop)
      const entry={type,text:text.substring(0,300),ts:Date.now(),session:_sessionId};
      const fb=JSON.parse(localStorage.getItem('jarvis_feedback')||'[]');
      fb.push(entry);if(fb.length>100)fb.splice(0,fb.length-100);
      localStorage.setItem('jarvis_feedback',JSON.stringify(fb));
      showToast(type==='good'?'✓ Obrigado!':'Feedback registrado','info');
    }
  }catch(e){showToast('Erro ao enviar feedback','error');}
  setTimeout(()=>btns.forEach(b=>b.classList.remove('active')),1500);
}

// Mostrar feedback quando resposta completa
const _origShowResponse=showResponse;
showResponse=function(text){
  _origShowResponse(text);
  showFeedback();
};
const _origClearResponse=clearResponse;
clearResponse=function(){
  _origClearResponse();
  hideFeedback();
};

// ── MEMORY MODAL ─────────────────────────────────────────────────────────────
function openMemModal(){
  document.getElementById('memModal').classList.add('show');
  toggleSettings();
  loadMemories();
}
function closeMemModal(){document.getElementById('memModal').classList.remove('show');}
async function loadMemories(){
  const list=document.getElementById('memList');
  if(!list)return;
  list.innerHTML='<div class="mem-empty">Carregando...</div>';
  try{
    // Carregar sessões
    const r=await fetch(`${API_URL}/memory`,{signal:AbortSignal.timeout(3000)});
    const d=await r.json();
    const sessions=d.sessions||[];
    if(!sessions.length){list.innerHTML='<div class="mem-empty">Nenhuma memória ainda.<br>Use o JARVIS para criar memórias.</div>';return;}

    // Carregar memória da sessão atual
    const mr=await fetch(`${API_URL}/memory/${_sessionId||'default'}`,{signal:AbortSignal.timeout(3000)});
    const md=await mr.json();
    const history=(md.episodic||[]).slice(-20);
    const prefs=md.preferences||{};
    const proj=md.project_context||{};

    let html='';
    // Episódic memory
    if(history.length){
      history.reverse().forEach((h,i)=>{
        const msg=(h.message||'').substring(0,80);
        const resp=(h.response||'').substring(0,60);
        html+=`<div class="mem-item">
          <div>
            <div><strong>Q:</strong> ${escHtml(msg)}${msg.length<(h.message||'').length?'…':''}</div>
            <div style="color:rgba(0,229,255,0.35);margin-top:2px"><strong>A:</strong> ${escHtml(resp)}${resp.length<(h.response||'').length?'…':''}</div>
            <div class="mem-session">SESSÃO: ${escHtml(_sessionId||'?').substring(0,16)}</div>
          </div>
          <button class="mem-del" onclick="deleteMemoryEntry(${i})">✕</button>
        </div>`;
      });
    }
    // Preferences
    if(Object.keys(prefs).length){
      html+=`<div class="mem-item" style="border-color:rgba(255,209,102,0.12)">
        <div><strong style="color:rgba(255,209,102,0.6)">PREFERÊNCIAS:</strong> ${escHtml(JSON.stringify(prefs).substring(0,120))}</div>
        <div></div>
      </div>`;
    }
    list.innerHTML=html||'<div class="mem-empty">Sem histórico nesta sessão.</div>';

    // Stats
    document.getElementById('memTotalCount').textContent=history.length+' mensagens';
    // RAG stats
    try{
      const rs=await fetch(`${API_URL}/chat/rag/stats`,{signal:AbortSignal.timeout(2000)});
      const rd=await rs.json();
      document.getElementById('ragCount').textContent='RAG: '+(rd.count||0)+' docs';
    }catch(e){document.getElementById('ragCount').textContent='RAG: —';}
    // Sessions
    document.getElementById('memTotalCount').textContent=sessions.length+' sessões | '+history.length+' msgs';
  }catch(e){
    list.innerHTML='<div class="mem-empty">Erro ao carregar memórias: '+escHtml(e.message)+'</div>';
  }
}
async function deleteMemoryEntry(idx){
  if(!confirm('Apagar esta entrada da memória?'))return;
  try{
    await fetch(`${API_URL}/memory/${_sessionId||'default'}`,{method:'DELETE',signal:AbortSignal.timeout(3000)});
    showToast('Entrada apagada','warn');
    loadMemories();
  }catch(e){showToast('Erro ao apagar','error');}
}
async function clearAllMemories(){
  if(!confirm('Apagar TODAS as memórias desta sessão? Esta ação não pode ser desfeita.'))return;
  try{
    await fetch(`${API_URL}/memory/${_sessionId||'default'}`,{method:'DELETE',signal:AbortSignal.timeout(3000)});
    showToast('Memórias limpas','warn');
    loadMemories();
  }catch(e){showToast('Erro ao limpar','error');}
}
async function openRagStats(){
  try{
    const r=await fetch(`${API_URL}/chat/rag/stats`,{signal:AbortSignal.timeout(3000)});
    const d=await r.json();
    showToast(`RAG: ${d.count||0} docs indexados — ${d.available?'ATIVO':'INATIVO'}`,'info',4500);
  }catch(e){showToast('RAG não disponível','warn');}
}
async function indexCurrentProject(){
  showToast('Indexando... aguarde','info',8000);
  try{
    const r=await fetch(`${API_URL}/chat`,{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message:'Indexe os arquivos do projeto atual na base RAG',session_id:_sessionId||'jarvis'})
    });
    const d=await r.json();
    showToast('Projeto indexado no RAG!','success');
  }catch(e){showToast('Erro ao indexar projeto','error');}
}

// ── PWA: Service Worker Registration ─────────────────────────────────────────
if('serviceWorker' in navigator){
  window.addEventListener('load',()=>{
    navigator.serviceWorker.register('/sw.js',{scope:'/'})
      .then(reg=>{
        addEvent('ok','PWA: Service Worker registrado (v9.0)');
        reg.addEventListener('updatefound',()=>{
          addEvent('info','PWA: nova versão disponível');
        });
      })
      .catch(err=>addEvent('warn','PWA: SW não registrado — '+err.message));
  });
}

// ── AUTO-SHOW CMD ON ANY PRINTABLE KEY ───────────────────────────────────────
document.addEventListener('keydown',e=>{
  if(e.target===cmdText)return;
  if(e.ctrlKey||e.altKey||e.metaKey)return;
  if(e.key.length===1&&!e.key.match(/[\d]/)){
    // Letter key — auto-focus input
    cmdInput.classList.add('show');cmdText.focus();
    _hasInteracted=true;
  }
});

// ── SPEECH RECOGNITION EVENT LOG ─────────────────────────────────────────────
const _origInitSpeech=initSpeech;
initSpeech=function(){
  const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR){addEvent('warn','Speech Recognition não disponível');return _origInitSpeech();}
  addEvent('ok','Speech Recognition ativo (pt-BR)');
  return _origInitSpeech();
};

// ══════════════════════════════════════════════════════════════════════════════
// JARVIS v7.0 — RICH PANEL SYSTEM
// OSINT Investigation | Code Analysis | System Architect
// ══════════════════════════════════════════════════════════════════════════════

// ── INTENT DETECTION ─────────────────────────────────────────────────────────
function detectIntent(msg){
  const m=msg.toLowerCase();
  // OSINT: investigação de telefone, IP, email, perfil
  const osintKw=[
    'hackear','hackear o','localizar','rastrear','investigar','investigação',
    'número de telefone','número desse','osint','quem é esse número',
    'descobrir onde','descobrir quem','encontrar essa pessoa',
    'pesquisa o ip','pesquisa o número','pesquisa esse número',
    'quem é dono','dono do número','dono desse número',
    'pesquisar número','buscar número','informações sobre o número',
    'que número é esse','localização dessa pessoa',
  ];
  if(osintKw.some(k=>m.includes(k))) return 'osint';
  // Regex: phone numbers in message
  if(/\+?\d[\d\s\-().]{8,18}\d/.test(msg)&&/(localiz|investig|hackear|osint|rastr|descobrir|quem|número|phone)/i.test(msg)) return 'osint';
  // IP addresses
  if(/\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/.test(msg)&&/(investigar|osint|ip|localiz|rastr)/i.test(msg)) return 'osint';

  // CODE ANALYSIS: analisar arquivos, erros, bugs
  const analyzeKw=[
    'analise o arquivo','analise esse arquivo','analise esse código','analise o código',
    'analise o main','analise o backend','analise o frontend',
    'o que está errado','o que está dando errado','o que está errado no arquivo',
    'analyze the file','analyze this code','what\'s wrong',
    'qual é o bug','qual é o erro','me explique o erro',
    'me explique o código','explique esse arquivo','explique o código',
    'bug no arquivo','erro no arquivo','problema no arquivo',
    'debug o arquivo','debug o código','review o arquivo',
    'o que tem de errado','encontre o bug','encontre o erro',
    'qual o erro do arquivo','corrija o arquivo','corrija o código',
  ];
  if(analyzeKw.some(k=>m.includes(k))) return 'code_analysis';
  // File path patterns with analysis intent
  if(/(analise|analyze|revise|review|debug|erro|bug|errado|problema|explain|explique)/.test(m)&&/\.(py|js|ts|jsx|tsx|java|go|rs|php|rb|cs|cpp|html|css|sql|sh)/.test(m)) return 'code_analysis';

  // ARCHITECT: criar sistemas, apps, planos de desenvolvimento
  const archKw=[
    'criar sistema de','criar um sistema','criar app de','criar um app',
    'criar plataforma','criar uma plataforma','desenvolver sistema','desenvolver app',
    'quero criar um sistema','quero criar um app','quero desenvolver',
    'plano para sistema','arquitetura para','arquitetura de sistema',
    'como criar um sistema','como criar um app','design de sistema',
    'system design','plano completo para','estrutura do sistema',
    'me mostre a linguagem','que tecnologia usar','que stack usar',
    'preciso criar um','preciso de um sistema','quero montar um',
    'montar um sistema','montar um app','criar um e-commerce',
    'criar um saas','criar um marketplace',
  ];
  if(archKw.some(k=>m.includes(k))) return 'architect';

  return null;
}

// ── TARGET EXTRACTORS ─────────────────────────────────────────────────────────
function extractOsintTarget(msg){
  // Phone number
  let m=msg.match(/\+?[\d][\d\s\-().]{8,18}[\d]/);
  if(m) return {target:m[0].trim(),type:'phone'};
  // IP
  m=msg.match(/\b(\d{1,3}\.){3}\d{1,3}\b/);
  if(m) return {target:m[0],type:'ip'};
  // Email
  m=msg.match(/[^\s<>"]+@[^\s<>"]+\.[a-zA-Z]{2,}/);
  if(m) return {target:m[0],type:'email'};
  // Domain
  m=msg.match(/[a-zA-Z0-9][a-zA-Z0-9\-]{1,61}[a-zA-Z0-9]\.[a-zA-Z]{2,}/);
  if(m&&!m[0].startsWith('jarvis')) return {target:m[0],type:'domain'};
  return {target:'',type:'auto'};
}

function extractFilePath(msg){
  // Match file.ext or path/to/file.ext
  const m=msg.match(/[\w.\/\\-]+\.(py|js|ts|jsx|tsx|java|go|rs|php|rb|cs|cpp|c|html|css|sql|sh|yaml|yml|json|xml|tf|ps1|md)\b/i);
  return m?m[0]:'';
}

function extractArchDescription(msg){
  // Remove trigger words to get the domain description
  return msg
    .replace(/jarvis[,.]?\s*/gi,'')
    .replace(/^(criar|preciso|quero|me|por favor|cria|desenvolver|montar|arquitetura)\s+(sistema|app|aplicativo|plataforma|uma|um|de|para|criar|um|sistema|app|se|o|a)\s*/gi,'')
    .replace(/^(criar um|criar uma|criar|preciso de|quero um|quero uma|plano para|arquitetura de|design de|como criar um|como criar uma)\s*/gi,'')
    .trim()||msg;
}

// ── RICH PANEL CORE ───────────────────────────────────────────────────────────
let _richPanelData=null;

function openRichPanel(title,badgeText,badgeCls){
  const panel=document.getElementById('richPanel');
  const backdrop=document.getElementById('richPanelBackdrop');
  const rtitle=document.getElementById('rpTitle');
  const rbadge=document.getElementById('rpBadge');
  const rfooter=document.getElementById('rpFooter');
  if(!panel)return;
  rtitle.textContent=title;
  rbadge.textContent=badgeText;
  rbadge.className='rp-badge '+badgeCls;
  document.getElementById('rpBody').innerHTML='<div class="rp-loading"><div class="rp-spin"></div><span>PROCESSANDO...</span></div>';
  rfooter.style.display='none';rfooter.innerHTML='';
  panel.classList.add('show');
  backdrop.classList.add('show');
  _hasInteracted=true;
}

function closeRichPanel(){
  document.getElementById('richPanel')?.classList.remove('show');
  document.getElementById('richPanelBackdrop')?.classList.remove('show');
}

function _esc(s){return escHtml(String(s||'—'));}

// ── OSINT RENDERER ────────────────────────────────────────────────────────────
function renderOsintPanel(data){
  const d=data.data||data;
  const type=d.type||'unknown';
  const body=document.getElementById('rpBody');if(!body)return;

  let rows='';
  if(type==='phone'){
    rows=`
      <div class="rp-grid-3">
        <div class="rp-card"><div class="rp-card-label">ALVO</div><div class="rp-card-value">${_esc(d.target)}</div></div>
        <div class="rp-card"><div class="rp-card-label">STATUS</div><div class="rp-card-value ${d.valid?'valid':'invalid'}">${d.valid?'✓ VÁLIDO':'✗ INVÁLIDO'}</div></div>
        <div class="rp-card"><div class="rp-card-label">TIPO</div><div class="rp-card-value">${_esc(d.number_type||'—')}</div></div>
      </div>
      <div class="rp-grid-3">
        <div class="rp-card"><div class="rp-card-label">PAÍS</div><div class="rp-card-value">${_esc(d.country)}</div></div>
        <div class="rp-card"><div class="rp-card-label">REGIÃO / DDD</div><div class="rp-card-value">${_esc(d.region)}</div></div>
        <div class="rp-card"><div class="rp-card-label">OPERADORA</div><div class="rp-card-value">${_esc(d.carrier)}</div></div>
      </div>
      <div class="rp-grid-2">
        <div class="rp-card"><div class="rp-card-label">INTERNACIONAL</div><div class="rp-card-value">${_esc(d.format?.international)}</div></div>
        <div class="rp-card"><div class="rp-card-label">FUSO HORÁRIO</div><div class="rp-card-value">${_esc((d.timezone||[])[0]||'—')}</div></div>
      </div>`;
  }else if(type==='ip'){
    rows=`
      <div class="rp-grid-3">
        <div class="rp-card"><div class="rp-card-label">IP</div><div class="rp-card-value">${_esc(d.target)}</div></div>
        <div class="rp-card"><div class="rp-card-label">PAÍS</div><div class="rp-card-value">${_esc(d.country)}</div></div>
        <div class="rp-card"><div class="rp-card-label">CIDADE</div><div class="rp-card-value">${_esc(d.city)}</div></div>
      </div>
      <div class="rp-grid-2">
        <div class="rp-card"><div class="rp-card-label">ORGANIZAÇÃO / ASN</div><div class="rp-card-value">${_esc(d.org)}</div></div>
        <div class="rp-card"><div class="rp-card-label">FUSO / REGIÃO</div><div class="rp-card-value">${_esc(d.timezone)}</div></div>
      </div>
      ${d.hostname&&d.hostname!=='—'?`<div class="rp-card"><div class="rp-card-label">HOSTNAME</div><div class="rp-card-value">${_esc(d.hostname)}</div></div>`:''}
      ${d.lat!=null?`<div class="rp-card"><div class="rp-card-label">COORDENADAS</div><div class="rp-card-value">${d.lat}, ${d.lon}</div></div>`:''}`;
  }else if(type==='email'){
    rows=`
      <div class="rp-grid-3">
        <div class="rp-card"><div class="rp-card-label">EMAIL</div><div class="rp-card-value">${_esc(d.target)}</div></div>
        <div class="rp-card"><div class="rp-card-label">DOMÍNIO</div><div class="rp-card-value">${_esc(d.domain)}</div></div>
        <div class="rp-card"><div class="rp-card-label">STATUS</div><div class="rp-card-value ${d.valid?'valid':'invalid'}">${d.valid?'✓ VÁLIDO':'✗ INVÁLIDO'}</div></div>
      </div>
      <div class="rp-card"><div class="rp-card-label">MX RECORDS</div><div class="rp-card-value">${_esc((d.mx_records||[]).join(' | ')||'—')}</div></div>`;
  }else{
    rows=`<div class="rp-card"><div class="rp-card-label">ALVO</div><div class="rp-card-value">${_esc(d.target||d.analysis||'—')}</div></div>`;
  }

  const findings=(d.findings||[]).map(f=>`<div class="rp-finding">${_esc(f)}</div>`).join('');
  const links=Object.entries(d.links||{}).map(([k,v])=>`<a class="rp-link" href="${v}" target="_blank">${_esc(k.replace(/_/g,' ').toUpperCase())} ↗</a>`).join('');

  body.innerHTML=`
    <div>${rows}</div>
    ${findings?`<div><div class="rp-section-title">DESCOBERTAS</div><div class="rp-findings">${findings}</div></div>`:''}
    ${links?`<div><div class="rp-section-title">VERIFICAR EM</div><div class="rp-links">${links}</div></div>`:''}`;
}

// ── CODE ANALYSIS RENDERER ────────────────────────────────────────────────────
function renderCodePanel(data){
  const d=data.data||data;
  const body=document.getElementById('rpBody');
  const footer=document.getElementById('rpFooter');
  if(!body)return;

  const score=d.quality_score||0;
  const scoreCls=score>=75?'high':score>=50?'mid':'low';
  const issues=(d.issues||[]);
  const issueHtml=issues.map(i=>`
    <div class="rp-issue ${_esc(i.severity||'info')}">
      <span class="issue-sev">${_esc((i.severity||'info').toUpperCase())}</span>
      <span class="issue-line">${i.line?'L'+i.line:'—'}</span>
      <div class="issue-body">
        <span class="issue-desc">${_esc(i.description||'')}</span>
        ${i.fix?`<span class="issue-fix">Fix: ${_esc(i.fix)}</span>`:''}
      </div>
    </div>`).join('');

  body.innerHTML=`
    <div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <div>
          <div style="font-size:clamp(6.5px,0.7vw,8.5px);color:rgba(0,229,255,0.75);letter-spacing:1px">${_esc(d.file||'código')}</div>
          <div style="font-size:5px;color:rgba(0,229,255,0.25);letter-spacing:1.5px;margin-top:2px">${_esc(d.language||'?')} · ${d.lines||0} linhas · ${issues.length} problema${issues.length!==1?'s':''}</div>
        </div>
        <div class="rp-score" style="min-width:120px">
          <div class="rp-score-bar"><div class="rp-score-fill ${scoreCls}" style="width:${score}%"></div></div>
          <span class="rp-score-num ${scoreCls}">${score}/100</span>
        </div>
      </div>
      ${d.summary?`<div style="font-size:5.5px;color:rgba(120,195,210,0.62);margin-bottom:6px;letter-spacing:0.5px">${_esc(d.summary)}</div>`:''}
    </div>
    ${issues.length>0?`<div><div class="rp-section-title">PROBLEMAS DETECTADOS (${issues.length})</div><div class="rp-issues">${issueHtml}</div></div>`:'<div style="color:rgba(78,255,145,0.7);font-size:clamp(6px,0.65vw,7.5px);padding:4px 0">✓ Nenhum problema detectado — código saudável</div>'}
    ${d.solution?`<div><div class="rp-section-title">SOLUÇÃO</div><pre class="rp-code">${_esc(d.solution)}</pre></div>`:''}
    ${d.explanation?`<div><div class="rp-section-title">EXPLICAÇÃO</div><div style="font-size:clamp(6px,0.65vw,7.5px);color:rgba(120,195,215,0.78);line-height:1.75;letter-spacing:0.3px">${_esc(d.explanation)}</div></div>`:''}`;

  if(d.solution&&footer){
    footer.style.display='flex';
    footer.innerHTML=`
      <button class="rp-btn-confirm" onclick="_copyCode()">COPIAR SOLUÇÃO</button>
      <button class="rp-btn-cancel" onclick="closeRichPanel()">FECHAR</button>`;
  }
}
function _copyCode(){
  const el=document.querySelector('#rpBody .rp-code');
  if(!el)return;
  const txt=el.innerText||el.textContent;
  navigator.clipboard?.writeText(txt).then(()=>showToast('SOLUÇÃO COPIADA!','success')).catch(()=>{});
}

// ── ARCHITECT PLAN RENDERER ───────────────────────────────────────────────────
let _currentArchPlan=null;
function renderArchitectPanel(data){
  const d=data.data||data;
  _currentArchPlan=d;
  const body=document.getElementById('rpBody');
  const footer=document.getElementById('rpFooter');
  if(!body)return;

  const tech=d.tech_stack||{};
  const techRows=Object.entries(tech).filter(([k,v])=>v&&k!=='extras').map(([k,v])=>
    `<div class="arch-stack-row"><span class="arch-stack-key">${_esc(k.replace(/_/g,' ').toUpperCase())}</span><span class="arch-stack-val">${_esc(v)}</span></div>`
  ).join('');

  const screens=(d.screens||[]).slice(0,10).map((s,i)=>
    `<div class="arch-screen-item"><span class="arch-screen-name">${i+1}. ${_esc(s.name||s)}</span><span class="arch-screen-pri">${_esc((s.priority||1==='1'?'ALTA':s.priority<=2?'ALTA':s.priority<=3?'MÉDIA':'BAIXA'))}</span></div>`
  ).join('');

  const modules=(d.modules||[]).slice(0,8).map(m=>
    `<div class="arch-module-item"><div class="arch-module-name">${_esc(m.name||m)}</div>${m.estimated_hours?`<div class="arch-module-hours">≈ ${m.estimated_hours}h</div>`:''}</div>`
  ).join('');

  const tables=(d.database_tables||[]).slice(0,6).map(t=>
    `<div class="arch-table-row"><span class="arch-table-name">${_esc(t.name||t)}</span><span class="arch-table-fields">${_esc((t.main_fields||[]).join(', '))}</span></div>`
  ).join('');

  const endpoints=(d.api_endpoints||[]).slice(0,8).map(e=>
    `<div class="arch-api-row"><span class="arch-api-method ${_esc(e.method)}">${_esc(e.method)}</span><span class="arch-api-path">${_esc(e.path)}</span><span class="arch-api-desc">${_esc(e.description)}</span></div>`
  ).join('');

  const monRows=(d.monetization||[]).map(m=>
    `<div class="mon-row"><span class="mon-model">${_esc(m.model||m)}</span><span class="mon-price">${_esc(m.price||'—')}</span><span class="mon-desc">${_esc(m.description||'')}</span></div>`
  ).join('');

  const risks=(d.risks||[]).map(r=>
    `<div class="risk-row"><span class="risk-text">⚠ ${_esc(r.risk||r)}</span><span class="risk-mit">→ ${_esc(r.mitigation||'Mitigar')}</span></div>`
  ).join('');

  const nextSteps=(d.next_steps||[]).map((s,i)=>
    `<div class="next-step"><span class="next-step-num">0${i+1}</span><span>${_esc(s)}</span></div>`
  ).join('');

  const mvp=(d.mvp_features||[]).map(f=>`<span class="mvp-feat">${_esc(f)}</span>`).join('');

  body.innerHTML=`
    <div class="arch-title-block">
      <div class="arch-main-title">${_esc(d.title||'SISTEMA')}</div>
      ${d.tagline?`<div class="arch-tagline">${_esc(d.tagline)}</div>`:''}
      <div class="arch-tags">
        <span class="arch-tag">${_esc((d.type||'').toUpperCase())}</span>
        <span class="arch-tag">${_esc((d.complexity||'?').toUpperCase())}</span>
        <span class="arch-tag">${d.estimated_hours||0}H ESTIMADO</span>
        <span class="arch-tag">${d.estimated_sprints||0} SPRINTS</span>
        <span class="arch-tag">${_esc(d.team_size||'SOLO DEV')}</span>
      </div>
    </div>
    ${d.description?`<div style="font-size:clamp(5.5px,0.6vw,7px);color:rgba(120,195,210,0.65);letter-spacing:0.5px;line-height:1.7">${_esc(d.description)}</div>`:''}
    <div class="rp-grid-2">
      <div><div class="rp-section-title">STACK TECNOLÓGICA</div>${techRows}${(tech.extras||[]).length>0?`<div style="font-size:5px;color:rgba(0,229,255,0.25);margin-top:3px">Extras: ${_esc((tech.extras||[]).join(', '))}</div>`:''}</div>
      <div><div class="rp-section-title">TELAS PRINCIPAIS (${(d.screens||[]).length})</div>${screens}</div>
    </div>
    ${mvp?`<div><div class="rp-section-title">MVP — LANÇAR PRIMEIRO</div><div>${mvp}</div></div>`:''}
    ${modules?`<div><div class="rp-section-title">MÓDULOS DO SISTEMA</div>${modules}</div>`:''}
    ${tables?`<div><div class="rp-section-title">BANCO DE DADOS (TABELAS PRINCIPAIS)</div>${tables}</div>`:''}
    ${endpoints?`<div><div class="rp-section-title">API ENDPOINTS (PRINCIPAIS)</div>${endpoints}</div>`:''}
    ${monRows?`<div><div class="rp-section-title">MODELO DE MONETIZAÇÃO</div>${monRows}</div>`:''}
    ${risks?`<div><div class="rp-section-title">RISCOS & MITIGAÇÕES</div>${risks}</div>`:''}
    ${nextSteps?`<div><div class="rp-section-title">PRÓXIMOS PASSOS</div>${nextSteps}</div>`:''}`;

  if(footer){
    footer.style.display='flex';
    footer.innerHTML=`
      <button class="rp-btn-confirm" onclick="confirmArchitectPlan()">CONFIRMAR E INICIAR PROJETO</button>
      <button class="rp-btn-cancel" onclick="closeRichPanel()">AJUSTAR REQUISITOS</button>`;
  }
}

function confirmArchitectPlan(){
  if(!_currentArchPlan)return;
  const summary=`Implementar: ${_currentArchPlan.title||'sistema'}. Stack: ${_currentArchPlan.tech_stack?.backend||'FastAPI'} + ${_currentArchPlan.tech_stack?.frontend||'React'}. Começar pelo MVP: ${(_currentArchPlan.mvp_features||[]).slice(0,3).join(', ')}.`;
  closeRichPanel();
  showToast('PROJETO CONFIRMADO — INICIANDO','success',5000);
  addEvent('ok','ARQUITETURA CONFIRMADA: '+_currentArchPlan.title);
  sendMessage(summary);
  showAll();
}

// ── POWER MODE RUNNERS ────────────────────────────────────────────────────────
async function runOsintInvestigation(msg){
  const{target,type}=extractOsintTarget(msg);
  openRichPanel('INVESTIGAÇÃO OSINT','OSINT','rp-badge-osint');
  addConvEntry('user',msg);
  addEvent('ai','[OSINT] Investigando: '+(target||msg).substring(0,60));
  startElapsed();
  try{
    const r=await fetch(`${API_URL}/investigate`,{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({target:target||'',query:msg,type:target?type:'auto'}),
      signal:AbortSignal.timeout(25000),
    });
    stopElapsed();
    if(!r.ok){throw new Error('HTTP '+r.status);}
    const data=await r.json();
    renderOsintPanel(data);
    const voice=data.voice_response||'Investigação concluída, Senhor.';
    showResponse(voice);addConvEntry('jarvis',voice);
    addEvent('ok','OSINT concluído: '+(target||'').substring(0,40));
    showToast('OSINT CONCLUÍDO','success');
  }catch(e){
    stopElapsed();
    document.getElementById('rpBody').innerHTML=`<div style="color:rgba(255,107,107,0.8);font-size:clamp(6px,0.65vw,7.5px);padding:10px">✗ ERRO: ${_esc(e.message)}</div>`;
    addEvent('err','OSINT FALHOU: '+e.message);
    showToast('ERRO NA INVESTIGAÇÃO','error');
  }
}

async function runCodeAnalysis(msg){
  const filePath=extractFilePath(msg);
  openRichPanel('ANÁLISE DE CÓDIGO','CODE ANALYSIS','rp-badge-code');
  addConvEntry('user',msg);
  addEvent('ai','[CODE] Analisando: '+(filePath||'código'));
  startElapsed();
  try{
    const r=await fetch(`${API_URL}/analyze`,{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({file_path:filePath,query:msg,error_message:''}),
      signal:AbortSignal.timeout(90000),
    });
    stopElapsed();
    if(!r.ok){throw new Error('HTTP '+r.status);}
    const data=await r.json();
    renderCodePanel(data);
    const voice=data.voice_response||'Análise concluída, Senhor.';
    showResponse(voice);addConvEntry('jarvis',voice);
    addEvent('ok','Análise concluída: '+(filePath||'código'));
    showToast('ANÁLISE CONCLUÍDA','success');
  }catch(e){
    stopElapsed();
    document.getElementById('rpBody').innerHTML=`<div style="color:rgba(255,107,107,0.8);font-size:clamp(6px,0.65vw,7.5px);padding:10px">✗ ERRO: ${_esc(e.message)}</div>`;
    addEvent('err','CODE ANALYSIS FALHOU: '+e.message);
    showToast('ERRO NA ANÁLISE','error');
  }
}

async function runArchitectPlan(msg){
  const description=extractArchDescription(msg);
  openRichPanel('PLANO ARQUITETURAL','ARCHITECT','rp-badge-arch');
  addConvEntry('user',msg);
  addEvent('ai','[ARCH] Gerando plano: '+description.substring(0,60));
  startElapsed();
  try{
    const r=await fetch(`${API_URL}/architect`,{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({description:description,type:'auto',budget:'startup'}),
      signal:AbortSignal.timeout(90000),
    });
    stopElapsed();
    if(!r.ok){throw new Error('HTTP '+r.status);}
    const data=await r.json();
    renderArchitectPanel(data);
    const voice=data.voice_response||'Plano gerado, Senhor.';
    showResponse(voice);addConvEntry('jarvis',voice);
    addEvent('ok','PLANO gerado: '+(data.data?.title||description).substring(0,40));
    showToast('PLANO ARQUITETURAL GERADO','success');
  }catch(e){
    stopElapsed();
    document.getElementById('rpBody').innerHTML=`<div style="color:rgba(255,107,107,0.8);font-size:clamp(6px,0.65vw,7.5px);padding:10px">✗ ERRO: ${_esc(e.message)}</div>`;
    addEvent('err','ARCHITECT FALHOU: '+e.message);
    showToast('ERRO NO PLANO','error');
  }
}

// ── PATCH runCmd TO USE INTENT DETECTION ──────────────────────────────────────
const _origRunCmdV7=window.runCmd;
window.runCmd=function(raw){
  const cmd=(raw||'').trim();
  if(!cmd)return;
  _hasInteracted=true;

  const intent=detectIntent(cmd);

  if(intent==='osint'){
    showAll();
    runOsintInvestigation(cmd);
    return;
  }
  if(intent==='code_analysis'){
    showAll();
    runCodeAnalysis(cmd);
    return;
  }
  if(intent==='architect'){
    showAll();
    runArchitectPlan(cmd);
    return;
  }

  // Default: original handler
  return _origRunCmdV7(cmd);
};

// ── KEYBOARD SHORTCUTS ────────────────────────────────────────────────────────
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'&&document.getElementById('richPanel')?.classList.contains('show')){
    e.preventDefault();closeRichPanel();return;
  }
  if(e.key==='F2'){
    e.preventDefault();
    const t=window.prompt('OSINT — Alvo (número, IP, email):','');
    if(t)runOsintInvestigation(t);
    return;
  }
  if(e.key==='F3'){
    e.preventDefault();
    const t=window.prompt('CODE ANALYSIS — Caminho do arquivo:','backend/main.py');
    if(t)runCodeAnalysis('analise o arquivo '+t);
    return;
  }
  if(e.key==='F4'){
    e.preventDefault();
    const t=window.prompt('ARCHITECT — Descreva o sistema:','sistema de gestão de academia');
    if(t)runArchitectPlan('criar um sistema de '+t);
    return;
  }
},{capture:false});

// ── BOOT MESSAGE ──────────────────────────────────────────────────────────────
setTimeout(()=>{
  addEvent('ok','Power Modes ONLINE: F2=OSINT | F3=CODE | F4=ARCH');
  addEvent('ok','Voice: "investiga o número..." | "analise o arquivo..." | "cria um sistema de..."');
},1200);

// ══════════════════════════════════════════════════════════════════════════════
// JARVIS v8.0 — BLUETOOTH HEADSET + MOBILE SUPPORT
// ══════════════════════════════════════════════════════════════════════════════

// ── SILENT AUDIO KEEP-ALIVE (obrigatório para MediaSession funcionar) ────────
let _keepAliveAudio=null;
function _startMediaKeepAlive(){
  if(_keepAliveAudio)return;
  try{
    // WAV mínimo silencioso em base64 — 1 sample, 44100Hz
    const silent='data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=';
    _keepAliveAudio=new Audio(silent);
    _keepAliveAudio.loop=true;
    _keepAliveAudio.volume=0.001;
    _keepAliveAudio.play().then(()=>{
      addEvent('ok','MediaSession keep-alive ativo');
    }).catch(()=>{});
  }catch(e){}
}
// Iniciar após primeira interação do utilizador (política de autoplay)
['click','keydown','touchstart'].forEach(ev=>{
  document.addEventListener(ev,()=>_startMediaKeepAlive(),{once:true,passive:true});
});

// ── VIBRATION FEEDBACK ────────────────────────────────────────────────────────
function vibrateDevice(pattern=[50,30,50]){
  try{if(navigator.vibrate)navigator.vibrate(pattern);}catch(e){}
}

// ── WAKE LOCK — impede o ecrã do celular de apagar ───────────────────────────
let _wakeLock=null;
async function initWakeLock(){
  if(!('wakeLock' in navigator))return;
  try{
    _wakeLock=await navigator.wakeLock.request('screen');
    const wl=document.getElementById('sWakeLock');
    if(wl){wl.textContent='ATIVO';wl.style.color='rgba(78,255,145,0.85)';}
    addEvent('ok','Wake Lock: ecrã mantido ativo');
    // Re-adquirir se a página voltar ao foco
    document.addEventListener('visibilitychange',async()=>{
      if(document.visibilityState==='visible'&&(_wakeLock===null||_wakeLock.released)){
        try{_wakeLock=await navigator.wakeLock.request('screen');}catch(e){}
      }
    });
  }catch(e){
    const wl=document.getElementById('sWakeLock');
    if(wl){wl.textContent='INDISPONÍVEL';wl.style.color='rgba(255,107,107,0.6)';}
  }
}

// ── HEADSET ACTION HANDLER ────────────────────────────────────────────────────
function _onHeadsetPress(){
  vibrateDevice([40,20,40]);
  if(isRecording){
    stopRecording();
    addEvent('voice','HEADSET: gravação parada');
  }else{
    startRecording();
    showAll();
    addEvent('voice','HEADSET: ◉ OUVINDO...');
  }
}
function _onHeadsetLongPress(){
  vibrateDevice([80,40,80,40,80]);
  clearResponse();
  addEvent('voice','HEADSET (longo): resposta limpa');
}

// ── MEDIA SESSION API — botão do headset bluetooth ───────────────────────────
function initHeadsetSupport(){
  const btn=document.getElementById('headsetBtn');

  // MediaSession API (Android Chrome, Safari 14+, Edge)
  if('mediaSession' in navigator){
    try{
      navigator.mediaSession.metadata=new MediaMetadata({
        title:'JARVIS Neural Core',
        artist:'J.A.R.V.I.S. v8.0',
        album:'Personal AI — Online',
      });

      // Botão play/pause do headset → PTT
      navigator.mediaSession.setActionHandler('play',()=>_onHeadsetPress());
      navigator.mediaSession.setActionHandler('pause',()=>_onHeadsetPress());
      // Botão anterior → também ativa PTT (headsets de 1 botão enviam previoustrack)
      navigator.mediaSession.setActionHandler('previoustrack',()=>_onHeadsetPress());
      // Botão próximo → limpa resposta
      try{navigator.mediaSession.setActionHandler('nexttrack',()=>_onHeadsetLongPress());}catch(e){}
      // Stop → para gravação se estiver a gravar
      try{navigator.mediaSession.setActionHandler('stop',()=>{if(isRecording)stopRecording();});}catch(e){}

      if(btn){btn.classList.add('ready');}
      const hs=document.getElementById('sHeadsetVal');
      if(hs){hs.textContent='MediaSession ATIVO';hs.style.color='rgba(78,255,145,0.85)';}
      addEvent('ok','🎧 Headset BT: MediaSession API configurado');
    }catch(e){
      addEvent('warn','MediaSession parcial: '+e.message);
    }
  }else{
    const hs=document.getElementById('sHeadsetVal');
    if(hs){hs.textContent='Não suportado neste browser';hs.style.color='rgba(255,107,107,0.6)';}
    addEvent('warn','MediaSession não disponível — use Chrome/Edge no celular');
  }

  // MediaKeys keyboard events (fallback desktop + alguns headsets)
  document.addEventListener('keydown',e=>{
    const mediaKeys=['MediaPlayPause','MediaPlay','MediaPause','MediaStop','AudioVolumeMute'];
    if(mediaKeys.includes(e.key)){
      e.preventDefault();
      _onHeadsetPress();
    }
  });

  // Visual feedback no ícone do headset quando gravando
  const _origStart=window.startRecording;
  window.startRecording=async function(){
    await _origStart();
    if(btn)btn.classList.add('listening');
    // Atualizar MediaSession playback state
    if('mediaSession' in navigator){
      navigator.mediaSession.playbackState='playing';
    }
  };
  const _origStop=window.stopRecording;
  window.stopRecording=function(){
    _origStop();
    if(btn)btn.classList.remove('listening');
    if('mediaSession' in navigator){
      navigator.mediaSession.playbackState='paused';
    }
  };

  // Click manual no ícone do headset
  if(btn)btn.addEventListener('click',()=>{_startMediaKeepAlive();_onHeadsetPress();});
}

// ── REDE LOCAL — URL para o celular ──────────────────────────────────────────
let _netInfo=null;
async function fetchNetworkInfo(){
  try{
    const d=await fetch(`${API_URL}/network/info`,{signal:AbortSignal.timeout(3000)}).then(r=>r.json());
    _netInfo=d;
    const el=document.getElementById('sNetUrl');
    if(el){
      el.textContent=d.jarvis_url||API_URL;
      el.title=d.qr_hint||'';
    }
    addEvent('ok','Rede: '+d.jarvis_url);
    return d;
  }catch(e){
    // Fallback: mostrar URL atual
    const el=document.getElementById('sNetUrl');
    const guessUrl=API_URL.replace('localhost','[IP-DO-PC]').replace('127.0.0.1','[IP-DO-PC]');
    if(el)el.textContent=guessUrl+' (substitua [IP-DO-PC] pelo IP da escola)';
    return null;
  }
}

function copyNetUrl(){
  const url=_netInfo?.jarvis_url||API_URL;
  if(navigator.clipboard){
    navigator.clipboard.writeText(url).then(()=>showToast('URL COPIADA — Cole no celular!','success',5000));
  }else{
    const ta=document.createElement('textarea');ta.value=url;
    document.body.appendChild(ta);ta.select();document.execCommand('copy');ta.remove();
    showToast('URL COPIADA','success');
  }
}

// Patch fetchSettings para incluir rede
const _origFetchSettings=window.fetchSettings;
window.fetchSettings=async function(){
  await _origFetchSettings();
  await fetchNetworkInfo();
};

// ── PWA: INSTALAR NO CELULAR ──────────────────────────────────────────────────
let _pwaPrompt=null;
window.addEventListener('beforeinstallprompt',e=>{
  e.preventDefault();_pwaPrompt=e;
  addEvent('ok','PWA: "Adicionar ao ecrã inicial" disponível');
  // Mostrar botão no settings
  const row=document.querySelector('#settingsPanel .srow:last-child');
  if(row){
    const btn=document.createElement('button');
    btn.className='sbtn';btn.textContent='INSTALAR APP';
    btn.onclick=async()=>{
      if(_pwaPrompt){await _pwaPrompt.prompt();_pwaPrompt=null;}
    };
    row.prepend(btn);
  }
});

// ── PWA MANIFEST dinâmico ─────────────────────────────────────────────────────
(function(){
  try{
    const manifest={
      name:'JARVIS Neural Core',short_name:'JARVIS',
      description:'J.A.R.V.I.S. Personal AI Assistant',
      start_url:'/',display:'standalone',
      background_color:'#000000',theme_color:'#00e5ff',
      orientation:'portrait-primary',
      icons:[{src:'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="48" fill="%23000" stroke="%2300e5ff" stroke-width="2"/><text x="50" y="68" font-size="52" text-anchor="middle" fill="%2300e5ff" font-family="monospace">J</text></svg>',sizes:'any',type:'image/svg+xml'}]
    };
    const blob=new Blob([JSON.stringify(manifest)],{type:'application/json'});
    const link=document.createElement('link');
    link.rel='manifest';link.href=URL.createObjectURL(blob);
    document.head.appendChild(link);
  }catch(e){}
})();

// ── INICIALIZAÇÃO MOBILE ──────────────────────────────────────────────────────
setTimeout(()=>{
  initHeadsetSupport();
  initWakeLock();
  fetchNetworkInfo();
  addEvent('ok','Mobile: Headset BT + Wake Lock + PWA prontos');
  addEvent('info','Celular: abra o URL de rede (⚙ Configurações) no mesmo WiFi');
},1500);

// ══════════════════════════════════════════════════════════════════════════════
// JARVIS v8.0 — 50+ MELHORIAS DE UX E FUNCIONALIDADES
// ══════════════════════════════════════════════════════════════════════════════

// ── #1: ENTRADA — HISTÓRICO DE COMANDOS ──────────────────────────────────────
const _cmdHistory=[]; let _cmdHistIdx=-1;
const charCounter=document.getElementById('charCounter');
if(cmdText){
  cmdText.addEventListener('input',()=>{
    const n=cmdText.value.length;
    if(charCounter)charCounter.textContent=n;
    if(n>200){charCounter.style.color='rgba(255,107,107,0.7)';}
    else{charCounter.style.color='rgba(0,229,255,0.25)';}
    // Auto show quick bar when typing
    const qb=document.getElementById('quickBar');
    if(qb){if(n===0){qb.classList.remove('show');}else{qb.classList.add('show');}}
  });

  cmdText.addEventListener('keydown',e=>{
    if(e.key==='ArrowUp'){
      e.preventDefault();
      if(_cmdHistIdx<_cmdHistory.length-1){_cmdHistIdx++;cmdText.value=_cmdHistory[_cmdHistIdx];if(charCounter)charCounter.textContent=cmdText.value.length;}
    }else if(e.key==='ArrowDown'){
      e.preventDefault();
      if(_cmdHistIdx>0){_cmdHistIdx--;cmdText.value=_cmdHistory[_cmdHistIdx];}
      else{_cmdHistIdx=-1;cmdText.value='';if(charCounter)charCounter.textContent='0';}
    }else if(e.key==='Enter'&&!e.shiftKey){
      e.preventDefault();
      const v=cmdText.value.trim();
      if(v){
        if(_cmdHistory[0]!==v){_cmdHistory.unshift(v);if(_cmdHistory.length>50)_cmdHistory.pop();}
        _cmdHistIdx=-1;
        runCmd(v);cmdText.value='';if(charCounter)charCounter.textContent='0';
        const qb=document.getElementById('quickBar');if(qb)qb.classList.remove('show');
      }
    }
  });
}
// Input history button
const inputHistBtn=document.getElementById('inputHistBtn');
if(inputHistBtn){
  inputHistBtn.addEventListener('click',()=>{
    if(_cmdHistory.length===0){showToast('Histórico vazio','info');return;}
    const hist=_cmdHistory.slice(0,10).map((h,i)=>`${i+1}. ${h.substring(0,60)}`).join('\n');
    const sel=window.prompt('HISTÓRICO (clique em nenhum para cancelar):\n\n'+hist+'\n\nDigite número ou texto:');
    if(sel){
      const n=parseInt(sel)-1;
      if(n>=0&&n<_cmdHistory.length){cmdText.value=_cmdHistory[n];}
      else{cmdText.value=sel;}
      cmdText.focus();
      if(charCounter)charCounter.textContent=cmdText.value.length;
    }
  });
}

// ── #2: EXPORTAR CONVERSA ──────────────────────────────────────────────────────
function exportConversation(){
  const lines=[`# JARVIS v8.0 — Conversa exportada em ${new Date().toLocaleString('pt-BR')}`,`Sessão: ${_sessionId||'—'}`,'---',''];
  convHistory.forEach(e=>{
    const role=e.role==='user'?'**Você**':'**JARVIS**';
    lines.push(`${role} [${e.ts}]`);
    lines.push(e.text||'');lines.push('');
  });
  const blob=new Blob([lines.join('\n')],{type:'text/markdown;charset=utf-8'});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');
  a.href=url;a.download=`jarvis_conversa_${Date.now()}.md`;
  document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url);
  showToast('CONVERSA EXPORTADA','success');
  addEvent('ok','Exportou conversa como .md');
}

// ── #3: EXPORTAR RESPOSTA ATUAL ─────────────────────────────────────────────
function exportResponse(){
  if(!_fullResponseText){showToast('Nenhuma resposta para exportar','warn');return;}
  const header=`# JARVIS v8.0 — Resposta exportada\n${new Date().toLocaleString('pt-BR')}\n\n---\n\n`;
  const blob=new Blob([header+_fullResponseText],{type:'text/markdown;charset=utf-8'});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');
  a.href=url;a.download=`jarvis_resposta_${Date.now()}.md`;
  document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url);
  showToast('RESPOSTA EXPORTADA','success');
}

// ── #4: PESQUISAR NA CONVERSA ──────────────────────────────────────────────────
function toggleConvSearch(){
  const s=document.getElementById('convSearch');
  if(s){s.classList.toggle('show');
    if(s.classList.contains('show'))document.getElementById('convSearchInput')?.focus();
    else searchConversation('');
  }
}
function searchConversation(query){
  const entries=document.querySelectorAll('.conv-entry');
  if(!query){entries.forEach(e=>e.classList.remove('search-match'));return;}
  const q=query.toLowerCase();
  entries.forEach(e=>{
    const txt=(e.textContent||'').toLowerCase();
    e.classList.toggle('search-match',txt.includes(q));
  });
}

// ── #5: QUICK ACTIONS ─────────────────────────────────────────────────────────
function quickAction(type){
  const map={
    'status':()=>runCmd('status'),
    'osint':()=>{const t=window.prompt('OSINT — Alvo (número, IP, email ou domínio):');if(t)runOsintInvestigation(t.trim());},
    'analyze':()=>{const f=window.prompt('Analisar — Caminho do arquivo (ex: backend/main.py):');if(f)runCodeAnalysis(f.trim());},
    'architect':()=>{const d=window.prompt('Arquitetar — Descreva o sistema:');if(d)runArchitectPlan(d.trim());},
    'generate':()=>{const d=window.prompt('Gerar código — Descreva o que precisa:\n\nEx: "API REST em FastAPI para gerenciar usuários"');if(d)runGenerateCode(d.trim());},
    'summarize':()=>{const t=window.prompt('Resumir — Cole o texto ou caminho do arquivo:');if(t)runSummarize(t.trim());},
    'explain':()=>{const t=window.prompt('Explicar — Cole o código ou conceito:');if(t)runExplain(t.trim());},
    'review':()=>{const t=window.prompt('Code Review — Cole o código para revisar:');if(t)runCodeReview(t.trim());},
  };
  const fn=map[type];if(fn)fn();
  const qb=document.getElementById('quickBar');if(qb)qb.classList.remove('show');
}

// ── #6: GERAÇÃO DE CÓDIGO v8.0 ────────────────────────────────────────────────
async function runGenerateCode(description,language='python'){
  if(!description)return;
  openRichPanel('GERANDO CÓDIGO','generating');
  addEvent('ai','GENERATE: '+description.substring(0,50));
  try{
    const d=await fetch(`${API_URL}/generate/code`,{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({description,language,style:'clean'}),
      signal:AbortSignal.timeout(90000)
    }).then(r=>r.json());
    if(d.voice_response)showResponse(d.voice_response);
    if(d.data?.code){
      const code=d.data.code;
      const lang=d.data.language||language;
      document.getElementById('rpTitle').textContent='CÓDIGO GERADO';
      const badge=document.getElementById('rpBadge');
      if(badge){badge.className='rp-badge';badge.textContent=lang.toUpperCase();badge.style.color='rgba(78,255,145,0.85)';badge.style.borderColor='rgba(78,255,145,0.3)';}
      const body=document.getElementById('rpBody');
      if(body){
        body.innerHTML=`
          <div class="rp-row"><span class="rp-label">LINGUAGEM</span><span class="rp-value">${escHtml(lang)}</span></div>
          <div class="rp-row"><span class="rp-label">DESCRIÇÃO</span><span class="rp-value" style="color:rgba(180,210,240,0.7)">${escHtml(description.substring(0,100))}</span></div>
          <div style="position:relative;margin-top:8px">
            <button class="md-copy-btn" style="position:static;display:block;margin-bottom:3px;width:auto" onclick="navigator.clipboard?.writeText(document.getElementById('genCodePre').innerText)">COPIAR CÓDIGO</button>
            <pre class="rp-gen-code" id="genCodePre">${escHtml(code)}</pre>
          </div>`;
      }
      const footer=document.getElementById('rpFooter');
      if(footer){
        footer.style.display='flex';footer.innerHTML='<button class="rp-confirm-btn" onclick="downloadGeneratedCode()">DOWNLOAD .'+lang+' ↓</button>';
        window._lastGeneratedCode={code,lang};
      }
    }
    addEvent('ok','Código gerado com sucesso');
  }catch(e){
    addEvent('err','GENERATE ERROR: '+e.message);
    document.getElementById('rpBody').innerHTML=`<div style="color:rgba(255,107,107,0.8);font-size:7px;padding:10px">Erro ao gerar código: ${escHtml(e.message)}</div>`;
  }
}
function downloadGeneratedCode(){
  const gc=window._lastGeneratedCode;if(!gc)return;
  const extMap={python:'.py',javascript:'.js',typescript:'.ts',java:'.java',go:'.go',rust:'.rs'};
  const ext=extMap[gc.lang]||'.txt';
  const blob=new Blob([gc.code],{type:'text/plain;charset=utf-8'});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');a.href=url;a.download='jarvis_generated'+ext;
  document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url);
  showToast('CÓDIGO BAIXADO','success');
}

// ── #7: RESUMIR v8.0 ──────────────────────────────────────────────────────────
async function runSummarize(text){
  if(!text)return;
  openRichPanel('RESUMINDO','summarizing');
  addEvent('ai','SUMMARIZE: '+text.substring(0,40));
  try{
    const isPath=text.includes('/')||text.includes('\\')&&text.length<200;
    const body=isPath?{file_path:text,format:'structured',length:'medium'}:{text,format:'structured',length:'medium'};
    const d=await fetch(`${API_URL}/generate/summarize`,{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body),signal:AbortSignal.timeout(60000)
    }).then(r=>r.json());
    if(d.voice_response)showResponse(d.voice_response);
    document.getElementById('rpTitle').textContent='RESUMO';
    const badge=document.getElementById('rpBadge');
    if(badge){badge.textContent='SUMÁRIO';badge.className='rp-badge';badge.style.color='rgba(212,168,32,0.85)';badge.style.borderColor='rgba(212,168,32,0.3)';}
    const rpBody=document.getElementById('rpBody');
    if(rpBody&&d.data){
      const sd=d.data;
      rpBody.innerHTML=`
        <div style="font-size:6.5px;color:rgba(0,229,255,0.5);letter-spacing:1px;margin-bottom:5px">RESUMO ESTRUTURADO</div>
        ${sd.tldr?`<div class="rp-section-title">TL;DR</div><div style="font-size:7px;color:rgba(180,210,240,0.8);line-height:1.7;padding:5px 0">${escHtml(sd.tldr)}</div>`:''}
        ${sd.key_points?.length?`<div class="rp-section-title" style="margin-top:8px">PONTOS PRINCIPAIS</div>${sd.key_points.map(p=>`<div class="next-step"><span class="next-step-num">•</span><span>${escHtml(p)}</span></div>`).join('')}`:''}
        ${sd.action_items?.length?`<div class="rp-section-title" style="margin-top:8px">AÇÕES</div>${sd.action_items.map(p=>`<div class="next-step"><span class="next-step-num">→</span><span>${escHtml(p)}</span></div>`).join('')}`:''}
        ${sd.conclusion?`<div class="rp-section-title" style="margin-top:8px">CONCLUSÃO</div><div style="font-size:6.5px;color:rgba(180,210,240,0.65);line-height:1.6">${escHtml(sd.conclusion)}</div>`:''}`;
    }
    addEvent('ok','Resumo gerado com sucesso');
  }catch(e){
    addEvent('err','SUMMARIZE ERROR: '+e.message);
    document.getElementById('rpBody').innerHTML=`<div style="color:rgba(255,107,107,0.8);padding:10px">${escHtml(e.message)}</div>`;
  }
}

// ── #8: EXPLICAR v8.0 ─────────────────────────────────────────────────────────
async function runExplain(topic){
  if(!topic)return;
  openRichPanel('EXPLICANDO','explaining');
  addEvent('ai','EXPLAIN: '+topic.substring(0,40));
  try{
    const d=await fetch(`${API_URL}/generate/explain`,{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({topic,level:'intermediate',language:'pt-BR'}),
      signal:AbortSignal.timeout(60000)
    }).then(r=>r.json());
    if(d.voice_response)showResponse(d.voice_response);
    document.getElementById('rpTitle').textContent='EXPLICAÇÃO';
    const badge=document.getElementById('rpBadge');
    if(badge){badge.textContent='LEARN';badge.className='rp-badge';badge.style.color='rgba(78,255,145,0.8)';badge.style.borderColor='rgba(78,255,145,0.25)';}
    const rpBody=document.getElementById('rpBody');
    if(rpBody&&d.data){
      const dd=d.data;
      rpBody.innerHTML=`
        ${dd.summary?`<div style="font-size:7.5px;color:rgba(0,229,255,0.7);line-height:1.7;margin-bottom:8px;padding:5px;background:rgba(0,229,255,0.03);border-left:2px solid rgba(0,229,255,0.2)">${escHtml(dd.summary)}</div>`:''}
        <div class="rp-section-title">EXPLICAÇÃO</div>
        <div style="font-size:6.5px;color:rgba(180,210,240,0.75);line-height:1.8">${escHtml(dd.explanation||'')}</div>
        ${dd.key_concepts?.length?`<div class="rp-section-title" style="margin-top:8px">CONCEITOS-CHAVE</div>${dd.key_concepts.map(c=>`<span class="mvp-feat">${escHtml(c)}</span>`).join('')}`:''}
        ${dd.examples?.length?`<div class="rp-section-title" style="margin-top:8px">EXEMPLOS</div>${dd.examples.map(e=>`<div class="next-step"><span class="next-step-num">◆</span><span>${escHtml(e)}</span></div>`).join('')}`:''}
        ${dd.common_mistakes?.length?`<div class="rp-section-title" style="margin-top:8px;color:rgba(255,209,102,0.5)">ERROS COMUNS</div>${dd.common_mistakes.map(e=>`<div class="next-step" style="border-color:rgba(255,209,102,0.08)"><span class="next-step-num" style="color:rgba(255,107,107,0.5)">⚠</span><span>${escHtml(e)}</span></div>`).join('')}`:''}`;
    }
    addEvent('ok','Explicação gerada');
  }catch(e){
    addEvent('err','EXPLAIN ERROR: '+e.message);
  }
}

// ── #9: CODE REVIEW v8.0 ─────────────────────────────────────────────────────
async function runCodeReview(code){
  if(!code)return;
  openRichPanel('REVISANDO CÓDIGO','reviewing');
  addEvent('ai','CODE REVIEW: '+code.substring(0,40));
  try{
    const d=await fetch(`${API_URL}/generate/review`,{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({code,focus:['security','readability','performance']}),
      signal:AbortSignal.timeout(90000)
    }).then(r=>r.json());
    if(d.voice_response)showResponse(d.voice_response);
    document.getElementById('rpTitle').textContent='CODE REVIEW';
    const rpBody=document.getElementById('rpBody');
    if(rpBody&&d.data){
      const dd=d.data;
      const verdictColors={approve:'rgba(78,255,145,0.85)',request_changes:'rgba(255,107,107,0.85)',needs_discussion:'rgba(255,209,102,0.85)'};
      const verdictLabels={approve:'✓ APROVADO',request_changes:'✗ SOLICITA MUDANÇAS',needs_discussion:'⚠ DISCUSSÃO NECESSÁRIA'};
      rpBody.innerHTML=`
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <span style="font-size:8px;color:${verdictColors[dd.verdict]||'rgba(0,229,255,0.7)'}">${verdictLabels[dd.verdict]||dd.verdict||'—'}</span>
          <span style="font-size:7px;color:rgba(0,229,255,0.4)">SCORE: ${dd.score||0}/100</span>
        </div>
        ${dd.blocking_issues?.length?`<div class="rp-section-title" style="color:rgba(255,107,107,0.5)">ISSUES BLOQUEANTES (${dd.blocking_issues.length})</div>
          ${dd.blocking_issues.map(i=>`<div style="padding:4px 0;border-bottom:1px solid rgba(255,107,107,0.06)">
            <div style="font-size:5.5px;color:rgba(255,107,107,0.7)">${i.severity?.toUpperCase()||'ISSUE'} ${i.line?'L'+i.line:''}</div>
            <div style="font-size:6px;color:rgba(220,180,180,0.8)">${escHtml(i.issue||'')}</div>
            ${i.suggestion?`<div style="font-size:6px;color:rgba(78,255,145,0.6);margin-top:2px">→ ${escHtml(i.suggestion)}</div>`:''}
          </div>`).join('')}`:''}
        ${dd.praise?.length?`<div class="rp-section-title" style="margin-top:8px;color:rgba(78,255,145,0.5)">PONTOS POSITIVOS</div>
          ${dd.praise.map(p=>`<div class="next-step"><span class="next-step-num" style="color:rgba(78,255,145,0.5)">✓</span><span>${escHtml(p)}</span></div>`).join('')}`:''}
        ${dd.overall_feedback?`<div class="rp-section-title" style="margin-top:8px">FEEDBACK GERAL</div>
          <div style="font-size:6.5px;color:rgba(180,210,240,0.65);line-height:1.7">${escHtml(dd.overall_feedback)}</div>`:''}`;
    }
    addEvent('ok','Code review concluído');
  }catch(e){addEvent('err','REVIEW ERROR: '+e.message);}
}

// ── #10: GERAR DIAGRAMA MERMAID v8.0 ─────────────────────────────────────────
async function runGenerateDiagram(description){
  if(!description)return;
  openRichPanel('GERANDO DIAGRAMA','diagramming');
  addEvent('ai','DIAGRAM: '+description.substring(0,40));
  try{
    const d=await fetch(`${API_URL}/generate/diagram`,{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({description,type:'auto'}),
      signal:AbortSignal.timeout(60000)
    }).then(r=>r.json());
    if(d.voice_response)showResponse(d.voice_response);
    const mermaidCode=d.data?.mermaid||'';
    document.getElementById('rpTitle').textContent='DIAGRAMA MERMAID';
    const badge=document.getElementById('rpBadge');
    if(badge){badge.textContent='DIAGRAM';badge.className='rp-badge';badge.style.color='rgba(212,168,32,0.85)';}
    const rpBody=document.getElementById('rpBody');
    if(rpBody){
      const mId='mmd_'+Date.now();
      rpBody.innerHTML=`
        <div class="rp-row"><span class="rp-label">TIPO</span><span class="rp-value">${escHtml(d.data?.type||'flowchart')}</span></div>
        <div class="rp-mermaid" id="${mId}"><pre>${escHtml(mermaidCode)}</pre></div>
        <div style="margin-top:6px">
          <button class="md-copy-btn" style="position:static;display:inline-block" onclick="navigator.clipboard?.writeText(${JSON.stringify(mermaidCode)})">COPIAR MERMAID</button>
        </div>`;
      // Try to render with mermaid.js
      setTimeout(()=>{
        try{
          if(window.mermaid){
            const wrap=document.getElementById(mId);
            if(wrap){wrap.innerHTML=`<div class="mermaid">${escHtml(mermaidCode)}</div>`;window.mermaid.run({nodes:[wrap.querySelector('.mermaid')]});}
          }
        }catch(me){console.warn('Mermaid render:',me);}
      },300);
    }
    addEvent('ok','Diagrama Mermaid gerado');
  }catch(e){addEvent('err','DIAGRAM ERROR: '+e.message);}
}

// ── #11: GERAR TESTES v8.0 ────────────────────────────────────────────────────
async function runGenerateTests(filePath){
  if(!filePath)return;
  openRichPanel('GERANDO TESTES','testing');
  addEvent('ai','GENERATE TESTS: '+filePath.substring(0,40));
  try{
    const d=await fetch(`${API_URL}/generate/tests`,{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({file_path:filePath}),
      signal:AbortSignal.timeout(90000)
    }).then(r=>r.json());
    if(d.voice_response)showResponse(d.voice_response);
    document.getElementById('rpTitle').textContent='TESTES GERADOS';
    const rpBody=document.getElementById('rpBody');
    if(rpBody&&d.data?.code){
      const fw=d.data.framework||'pytest';
      rpBody.innerHTML=`
        <div class="rp-row"><span class="rp-label">FRAMEWORK</span><span class="rp-value">${escHtml(fw)}</span></div>
        <div style="position:relative;margin-top:6px">
          <button class="md-copy-btn" style="position:static;display:block;margin-bottom:3px" onclick="navigator.clipboard?.writeText(document.getElementById('testCodePre').innerText)">COPIAR TESTES</button>
          <pre class="rp-gen-code" id="testCodePre">${escHtml(d.data.code)}</pre>
        </div>`;
    }
    addEvent('ok','Testes gerados com '+d.data?.framework);
  }catch(e){addEvent('err','TESTS ERROR: '+e.message);}
}

// ── #12: THREAT SCORE NO PAINEL OSINT ────────────────────────────────────────
function _appendThreatScore(data){
  if(!data||!data.threat_score)return'';
  const ts=data.threat_score;
  const cls={'safe':'threat-safe','low':'threat-low','medium':'threat-medium','high':'threat-high','critical':'threat-critical'}[ts.level]||'threat-low';
  const reasons=(ts.reasons||[]).map(r=>`<div style="font-size:5px;color:rgba(180,210,240,0.55);margin-top:1px">• ${escHtml(r)}</div>`).join('');
  return`<div style="margin-top:6px;padding:5px;background:rgba(0,10,20,0.5);border:1px solid rgba(0,229,255,0.06)">
    <div style="display:flex;justify-content:space-between;align-items:center">
      <span style="font-size:5.5px;letter-spacing:1.5px;color:rgba(0,229,255,0.3)">THREAT SCORE</span>
      <span class="threat-badge ${cls}">${ts.level?.toUpperCase()||'LOW'} — ${ts.score||0}/100</span>
    </div>${reasons}</div>`;
}

// Patch renderOsintPanel to include threat score
const _origRenderOsint=window.renderOsintPanel;
if(typeof renderOsintPanel==='function'){
  window.renderOsintPanel=(data)=>{
    _origRenderOsint?.(data);
    const body=document.getElementById('rpBody');
    if(body&&data.threat_score){body.insertAdjacentHTML('afterbegin',_appendThreatScore(data));}
  };
}

// ── #13: RENDER MERMAID NO PAINEL ARQUITETURA ─────────────────────────────────
const _origRenderArch=window.renderArchitectPanel;
if(typeof renderArchitectPanel==='function'){
  window.renderArchitectPanel=(data)=>{
    _origRenderArch?.(data);
    // Inject mermaid ERD and flow diagrams
    const body=document.getElementById('rpBody');
    if(body&&(data.mermaid_erd||data.mermaid_flow)){
      const mermaidHtml=(mCode,title)=>{
        if(!mCode)return'';
        const mid='merm_'+Math.random().toString(36).slice(2);
        setTimeout(()=>{
          try{
            if(window.mermaid){
              const el=document.getElementById(mid);
              if(el){el.innerHTML=`<div class="mermaid">${escHtml(mCode)}</div>`;window.mermaid.run({nodes:[el.querySelector('.mermaid')]});}
            }
          }catch(e){}
        },400);
        return`<div class="rp-section-title" style="margin-top:10px">${title}</div><div class="rp-mermaid" id="${mid}"><pre style="font-size:5px;color:rgba(0,229,255,0.35)">${escHtml(mCode)}</pre></div>`;
      };
      body.insertAdjacentHTML('beforeend',
        mermaidHtml(data.mermaid_erd,'DIAGRAMA ERD')+mermaidHtml(data.mermaid_flow,'ARQUITETURA'));
    }
  };
}

// ── #14: FONT SIZE CONTROL ────────────────────────────────────────────────────
function applyFontSize(val){
  document.documentElement.style.setProperty('--base-font-size',val+'px');
  const el=document.getElementById('fontSizeVal');if(el)el.textContent=val+'px';
  localStorage.setItem('jarvis_font_size',val);
}
(()=>{const saved=localStorage.getItem('jarvis_font_size');if(saved){applyFontSize(saved);const sl=document.getElementById('fontSizeSlider');if(sl)sl.value=saved;}})();

// ── #15: VOICE SPEED CONTROL ─────────────────────────────────────────────────
let _voiceSpeed=1.0;
function applyVoiceSpeed(val){
  _voiceSpeed=parseFloat(val);
  const el=document.getElementById('voiceSpeedVal');if(el)el.textContent=_voiceSpeed.toFixed(1)+'×';
  localStorage.setItem('jarvis_voice_speed',val);
}
(()=>{const saved=localStorage.getItem('jarvis_voice_speed');if(saved){applyVoiceSpeed(saved);const sl=document.getElementById('voiceSpeedSlider');if(sl)sl.value=saved;}})();

// ── #16: AUTO-SCROLL TOGGLE ───────────────────────────────────────────────────
let _autoScroll=true;
function toggleAutoScroll(v){
  _autoScroll=v;
  const el=document.getElementById('autoScrollVal');if(el)el.textContent=v?'ATIVO':'INATIVO';
  localStorage.setItem('jarvis_auto_scroll',v?'1':'0');
}
(()=>{const saved=localStorage.getItem('jarvis_auto_scroll');if(saved==='0'){_autoScroll=false;const cb=document.getElementById('autoScrollCb');if(cb)cb.checked=false;const el=document.getElementById('autoScrollVal');if(el)el.textContent='INATIVO';}})();

// Patch appendResponse para respeitar auto-scroll
const _origAppendResponse=window.appendResponse;
window.appendResponse=function(chunk){
  _origAppendResponse?.(chunk)||appendResponse(chunk);
  if(_autoScroll){const rp=document.getElementById('respanel');if(rp)rp.scrollTop=rp.scrollHeight;}
};

// ── #17: NOTIFICATION SOUNDS ──────────────────────────────────────────────────
let _soundsEnabled=false;
function toggleSounds(v){
  _soundsEnabled=v;
  const el=document.getElementById('soundVal');if(el)el.textContent=v?'ATIVO':'INATIVO';
  localStorage.setItem('jarvis_sounds',v?'1':'0');
}
function _playSound(type){
  if(!_soundsEnabled||!window.AudioContext)return;
  try{
    const ctx=new(window.AudioContext||window.webkitAudioContext)();
    const osc=ctx.createOscillator();const gain=ctx.createGain();
    osc.connect(gain);gain.connect(ctx.destination);
    const freqs={ok:880,warn:440,err:220,done:1046};
    osc.frequency.setValueAtTime(freqs[type]||880,ctx.currentTime);
    gain.gain.setValueAtTime(0.08,ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001,ctx.currentTime+0.15);
    osc.start(ctx.currentTime);osc.stop(ctx.currentTime+0.15);
  }catch(e){}
}
(()=>{const saved=localStorage.getItem('jarvis_sounds');if(saved==='1'){_soundsEnabled=true;const cb=document.getElementById('soundCb');if(cb)cb.checked=true;const el=document.getElementById('soundVal');if(el)el.textContent='ATIVO';}})();

// ── #18: KEYBOARD SHORTCUT MODAL ─────────────────────────────────────────────
function openKbModal(){const m=document.getElementById('kbModal');if(m)m.classList.add('show');}
function closeKbModal(){const m=document.getElementById('kbModal');if(m)m.classList.remove('show');}
document.addEventListener('keydown',e=>{
  if(e.key==='F9'){e.preventDefault();openKbModal();}
  if(e.key==='F5'){e.preventDefault();const d=window.prompt('Gerar código — Descreva o que precisa:');if(d)runGenerateCode(d.trim());}
  if(e.key==='F6'){e.preventDefault();const d=window.prompt('Resumir — Cole o texto ou arquivo:');if(d)runSummarize(d.trim());}
  if(e.key==='F7'){e.preventDefault();const d=window.prompt('Gerar Testes — Caminho do arquivo:');if(d)runGenerateTests(d.trim());}
  if(e.key==='F8'){e.preventDefault();const d=window.prompt('Diagrama Mermaid — Descreva o diagrama:');if(d)runGenerateDiagram(d.trim());}
  if(e.key==='Escape'){closeKbModal();const dz=document.getElementById('dropZone');if(dz)dz.classList.remove('active');}
},{capture:true,passive:false});

// ── #19: FILE DRAG & DROP PARA ANÁLISE ───────────────────────────────────────
const dropZone=document.getElementById('dropZone');
document.addEventListener('dragover',e=>{e.preventDefault();if(dropZone)dropZone.classList.add('active');});
document.addEventListener('dragleave',e=>{if(e.relatedTarget===null&&dropZone)dropZone.classList.remove('active');});
document.addEventListener('drop',e=>{
  e.preventDefault();
  if(dropZone)dropZone.classList.remove('active');
  const files=[...e.dataTransfer.files];
  if(files.length===0)return;
  const file=files[0];
  const reader=new FileReader();
  reader.onload=(ev)=>{
    const code=ev.target.result;
    const ext=file.name.split('.').pop()||'';
    const langMap={py:'python',js:'javascript',ts:'typescript',java:'java',go:'go',rs:'rust',php:'php',rb:'ruby',cs:'csharp',cpp:'cpp',c:'c',sh:'shell',sql:'sql',html:'html',css:'css',yaml:'yaml',yml:'yaml',json:'json'};
    const lang=langMap[ext]||'';
    addEvent('ok','Arquivo arrastado: '+file.name+' ('+lang+')');
    // Open code analysis panel with snippet
    openRichPanel('ANALISANDO ARQUIVO','code_analysis');
    fetch(`${API_URL}/analyze`,{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({code_snippet:code.substring(0,5000),language:lang,query:file.name}),
      signal:AbortSignal.timeout(90000)
    }).then(r=>r.json()).then(d=>{
      if(d.voice_response)showResponse(d.voice_response);
      if(typeof renderCodePanel==='function')renderCodePanel(d.data||{});
    }).catch(err=>addEvent('err','Análise falhou: '+err.message));
  };
  reader.readAsText(file);
});

// ── #20: TASK PROGRESS BAR ────────────────────────────────────────────────────
let _taskPollInterval=null;
function setTaskProgress(pct,show=true){
  const bar=document.getElementById('taskProgressBar');
  if(bar)bar.style.width=(pct||0)+'%';
  const container=document.getElementById('taskProgress');
  if(container)container.style.background=show&&pct<100?'rgba(0,0,0,0.1)':'transparent';
}
async function pollTask(taskId,onDone){
  let polls=0;
  const poll=async()=>{
    polls++;if(polls>120)return; // max 2 min polling
    try{
      const d=await fetch(`${API_URL}/tasks/${taskId}`,{signal:AbortSignal.timeout(3000)}).then(r=>r.json());
      setTaskProgress(d.progress||0);
      if(d.status==='completed'){setTaskProgress(100);setTimeout(()=>setTaskProgress(0,false),1500);onDone?.(d.result);}
      else if(d.status==='failed'){setTaskProgress(0,false);addEvent('err','Tarefa falhou: '+(d.error||''));showToast('Tarefa falhou','error');}
      else if(d.status==='cancelled'){setTaskProgress(0,false);addEvent('warn','Tarefa cancelada');}
      else{setTimeout(poll,1000);}
    }catch(e){setTimeout(poll,2000);}
  };
  setTaskProgress(5);
  setTimeout(poll,500);
}

// ── #21: LATENCY DISPLAY PER-MESSAGE ─────────────────────────────────────────
(()=>{
  const origDone=window.appendResponse;
  // Patch WS done message handler to show latency
  const origConnectWS=window.connectWS;
})();

// ── #22: SETTINGS CONV COUNT UPDATE ──────────────────────────────────────────
function updateSettingsConvCount(){
  const el=document.getElementById('sConvCount');
  if(el)el.textContent=convHistory.length+' mensagens';
}
setInterval(updateSettingsConvCount,3000);

// ── #23: MODEL BADGE IN STATUS BAR ────────────────────────────────────────────
async function refreshModelBadge(){
  try{
    const d=await fetch(`${API_URL}/status`,{signal:AbortSignal.timeout(2000)}).then(r=>r.json());
    const el=document.getElementById('stModelBadge');
    if(el){
      const m=(d.model||'—').replace('mistral:','m:').replace('llama','ll').replace('qwen2','qw').replace(':latest','');
      el.textContent='['+m+']';
    }
  }catch(e){}
}
setTimeout(refreshModelBadge,2000);setInterval(refreshModelBadge,60000);

// ── #24: QUICK BAR SHOW ON FOCUS ─────────────────────────────────────────────
(()=>{
  if(cmdText){
    cmdText.addEventListener('focus',()=>{const qb=document.getElementById('quickBar');if(qb)qb.classList.add('show');});
    document.addEventListener('click',e=>{
      const qb=document.getElementById('quickBar');
      if(qb&&!e.target.closest('#cmdinput')&&!e.target.closest('#quickBar'))qb.classList.remove('show');
    });
  }
})();

// ── #25: SCROLL-TO-TOP VISIBILITY ─────────────────────────────────────────────
(()=>{
  const w0=document.getElementById('w0');
  if(w0){
    w0.addEventListener('scroll',()=>{
      const btn=document.getElementById('scrollTopBtn');
      if(btn)btn.classList.toggle('show',w0.scrollTop>200);
    },{passive:true});
  }
})();

// ── #26: F-KEY INTENT DETECTION UPGRADE ──────────────────────────────────────
// Update existing runCmd to detect v8.0 intents
const _origRunCmd=window.runCmd;
window.runCmd=function(raw){
  if(!raw)return;
  const msg=raw.toLowerCase().trim();
  // v8.0 intents
  if(msg.startsWith('gera ')||msg.startsWith('cria o código')||msg.startsWith('generate ')){
    const desc=raw.replace(/^(gera|cria o código|generate)\s+/i,'').trim();
    if(desc){runGenerateCode(desc);return;}
  }
  if(msg.startsWith('resume ')||msg.startsWith('summarize ')||msg.startsWith('resumo de ')){
    const t=raw.replace(/^(resume|summarize|resumo de)\s+/i,'').trim();
    if(t){runSummarize(t);return;}
  }
  if(msg.startsWith('explica ')||msg.startsWith('explain ')){
    const t=raw.replace(/^(explica|explain)\s+/i,'').trim();
    if(t){runExplain(t);return;}
  }
  if(msg.startsWith('diagrama ')||msg.startsWith('cria diagrama ')||msg.startsWith('diagram ')){
    const t=raw.replace(/^(diagrama|cria diagrama|diagram)\s+/i,'').trim();
    if(t){runGenerateDiagram(t);return;}
  }
  if(msg.startsWith('testes para ')||msg.startsWith('generate tests ')){
    const t=raw.replace(/^(testes para|generate tests)\s+/i,'').trim();
    if(t){runGenerateTests(t);return;}
  }
  // Fall through to original runCmd
  _origRunCmd(raw);
};

// ── BOOT v8.0 ──────────────────────────────────────────────────────────────────
setTimeout(()=>{
  // Init mermaid
  try{if(window.mermaid){window.mermaid.initialize({startOnLoad:false,theme:'dark',securityLevel:'loose',themeVariables:{primaryColor:'#00e5ff',primaryTextColor:'#fff',primaryBorderColor:'#00e5ff',lineColor:'#00e5ff',sectionBkgColor:'#000',altSectionBkgColor:'#001428',gridColor:'rgba(0,229,255,0.1)',clusterBkg:'#001428',titleColor:'rgba(0,229,255,0.7)'}});addEvent('ok','Mermaid.js: diagramas prontos');}}catch(e){}
  addEvent('ok','JARVIS v8.0 — 100+ melhorias ativas');
  addEvent('ok','NEW: F5=Gerar Código | F6=Resumir | F7=Testes | F8=Diagrama | F9=Atalhos');
  addEvent('ok','NEW: Arrastar ficheiro → análise automática | Histórico ↑↓ | Export chat');
  _playSound('ok');
},2000);

// ══════════════════════════════════════════════════════════════════════════════
// JARVIS v9.0 — 90 FEATURES PREMIUM
// ══════════════════════════════════════════════════════════════════════════════

// ── STATS TRACKING ────────────────────────────────────────────────────────────
const _stats = JSON.parse(localStorage.getItem('jarvis_stats') || '{}');
function _initStats(){
  const today = new Date().toDateString();
  if(!_stats.totalMessages)_stats.totalMessages=0;
  if(!_stats.totalChars)_stats.totalChars=0;
  if(!_stats.sessionCount)_stats.sessionCount=0;
  if(!_stats.voiceCommands)_stats.voiceCommands=0;
  if(!_stats.codesGenerated)_stats.codesGenerated=0;
  if(!_stats.firstUse)_stats.firstUse=Date.now();
  if(!_stats.lastUse)_stats.lastUse=Date.now();
  if(!_stats.streak)_stats.streak=0;
  if(!_stats.lastDay)_stats.lastDay='';
  if(!_stats.pomodorosDone)_stats.pomodorosDone=0;
  if(!_stats.todoDone)_stats.todoDone=0;
  // Streak logic
  if(_stats.lastDay !== today){
    const yesterday = new Date(Date.now()-86400000).toDateString();
    if(_stats.lastDay === yesterday){_stats.streak=(_stats.streak||0)+1;}
    else if(_stats.lastDay !== today){_stats.streak=1;}
    _stats.lastDay=today;
    _stats.sessionCount=(_stats.sessionCount||0)+1;
    _saveStats();
  }
  _updateStreakBadge();
}
function _saveStats(){localStorage.setItem('jarvis_stats',JSON.stringify(_stats));}
function _trackMessage(text){
  _stats.totalMessages=(_stats.totalMessages||0)+1;
  _stats.totalChars=(_stats.totalChars||0)+(text||'').length;
  _stats.lastUse=Date.now();
  _saveStats();
  _checkAchievements();
  _updateAdaptLevel();
}
function _updateStreakBadge(){
  const el=document.getElementById('streakBadge');
  if(el)el.textContent=`🔥 ${_stats.streak||0}D`;
}
function _updateAdaptLevel(){
  const msgs=_stats.totalMessages||0;
  const pct=Math.min(Math.round((msgs/500)*100),100);
  const el=document.getElementById('adaptLevel');
  if(el)el.textContent=`ADAPT: ${pct}%`;
}
// Patch sendMessage to track stats
const _origSendMsg=window.sendMessage;
window.sendMessage=function(msg){
  _trackMessage(msg);
  return _origSendMsg(msg);
};
// Open stats modal
function openStats(){
  const modal=document.getElementById('statsModal');
  const grid=document.getElementById('statsGrid');
  if(!modal||!grid)return;
  const daysSince=Math.floor((Date.now()-(_stats.firstUse||Date.now()))/86400000)+1;
  const cards=[
    {val:_stats.totalMessages||0,label:'MENSAGENS'},
    {val:_stats.streak||0,label:'STREAK (DIAS)'},
    {val:_stats.sessionCount||0,label:'SESSÕES'},
    {val:_stats.voiceCommands||0,label:'COMANDOS VOZ'},
    {val:_stats.codesGenerated||0,label:'CÓDIGOS GERADOS'},
    {val:Math.min(Math.round(((_stats.totalMessages||0)/500)*100),100)+'%',label:'NÍVEL ADAPTAÇÃO'},
    {val:_stats.pomodorosDone||0,label:'POMODOROS'},
    {val:daysSince+'d',label:'DESDE 1ª USO'},
  ];
  grid.innerHTML=cards.map(c=>`<div class="stats-card"><div class="stats-card-val">${c.val}</div><div class="stats-card-label">${c.label}</div></div>`).join('');
  const s2=document.getElementById('statsSection2');
  if(s2){
    const adapt=Math.min(Math.round(((_stats.totalMessages||0)/500)*100),100);
    s2.innerHTML=`<div class="stats-title" style="font-size:6px;margin-top:4px">NÍVEL DE ADAPTAÇÃO DO JARVIS</div>
      <div style="margin-top:6px">
        <div class="stats-bar-row"><span class="stats-bar-label">Estilo pessoal</span><div class="stats-bar-track"><div class="stats-bar-fill" style="width:${adapt}%"></div></div><span class="stats-bar-val">${adapt}%</span></div>
        <div class="stats-bar-row"><span class="stats-bar-label">Preferências</span><div class="stats-bar-track"><div class="stats-bar-fill" style="width:${Math.min(adapt*1.1,100)}%"></div></div><span class="stats-bar-val">${Math.min(Math.round(adapt*1.1),100)}%</span></div>
        <div class="stats-bar-row"><span class="stats-bar-label">Vocabulário</span><div class="stats-bar-track"><div class="stats-bar-fill" style="width:${Math.min(adapt*0.9,100)}%"></div></div><span class="stats-bar-val">${Math.min(Math.round(adapt*0.9),100)}%</span></div>
      </div>`;
  }
  modal.classList.add('show');
}
function closeStats(){document.getElementById('statsModal')?.classList.remove('show');}

// ── ACHIEVEMENTS SYSTEM ───────────────────────────────────────────────────────
const ACHIEVEMENTS=[
  {id:'first_msg',name:'PRIMEIRO CONTATO',desc:'Enviou a primeira mensagem',check:()=>_stats.totalMessages>=1},
  {id:'msg10',name:'CONVERSADOR',desc:'10 mensagens enviadas',check:()=>_stats.totalMessages>=10},
  {id:'msg100',name:'USUÁRIO DEDICADO',desc:'100 mensagens enviadas',check:()=>_stats.totalMessages>=100},
  {id:'streak3',name:'CONSISTENTE',desc:'3 dias consecutivos',check:()=>_stats.streak>=3},
  {id:'streak7',name:'SEMANA JARVIS',desc:'7 dias consecutivos',check:()=>_stats.streak>=7},
  {id:'voice5',name:'VOZ DE COMANDO',desc:'5 comandos de voz',check:()=>_stats.voiceCommands>=5},
  {id:'code5',name:'GERADOR DE CÓDIGO',desc:'5 códigos gerados',check:()=>_stats.codesGenerated>=5},
  {id:'pomo5',name:'FOCO TOTAL',desc:'5 pomodoros completados',check:()=>_stats.pomodorosDone>=5},
];
const _unlockedAch=new Set(JSON.parse(localStorage.getItem('jarvis_achievements')||'[]'));
function _checkAchievements(){
  ACHIEVEMENTS.forEach(a=>{
    if(!_unlockedAch.has(a.id)&&a.check()){
      _unlockedAch.add(a.id);
      localStorage.setItem('jarvis_achievements',JSON.stringify([..._unlockedAch]));
      _showAchievement(a);
    }
  });
}
function _showAchievement(a){
  const popup=document.getElementById('achievePopup');
  if(!popup)return;
  document.getElementById('achieveName').textContent=a.name;
  document.getElementById('achieveDesc').textContent=a.desc;
  popup.classList.add('show');
  _playSound('ok');
  setTimeout(()=>popup.classList.remove('show'),4500);
  addEvent('ok','🏆 CONQUISTA: '+a.name);
}

// ── PROMPT TEMPLATES ──────────────────────────────────────────────────────────
const PROMPT_TEMPLATES=[
  {icon:'💻',name:'GERAR CÓDIGO',desc:'Descreva o que precisa',prompt:'Gera o código para: '},
  {icon:'🔍',name:'ANALISAR',desc:'Analise este código/arquivo',prompt:'Analise o código: '},
  {icon:'🐛',name:'CORRIGIR BUG',desc:'Encontre e corrija o erro',prompt:'Corrija o bug neste código: '},
  {icon:'📝',name:'RESUMIR',desc:'Resuma um texto/tópico',prompt:'Resumo de: '},
  {icon:'🏗️',name:'ARQUITETURA',desc:'Plano de sistema completo',prompt:'Cria a arquitetura para: '},
  {icon:'🧪',name:'GERAR TESTES',desc:'Crie testes automatizados',prompt:'Gera testes para: '},
  {icon:'📚',name:'EXPLICAR',desc:'Explique um conceito',prompt:'Explique detalhadamente: '},
  {icon:'🔄',name:'CONVERTER',desc:'Converter entre linguagens',prompt:'Converta este código para '},
  {icon:'📊',name:'DIAGRAMA',desc:'Crie um diagrama Mermaid',prompt:'Cria um diagrama de: '},
  {icon:'🛡️',name:'CODE REVIEW',desc:'Revisão de segurança/qualidade',prompt:'Revise este código: '},
  {icon:'⚡',name:'OTIMIZAR',desc:'Otimize performance',prompt:'Otimize este código: '},
  {icon:'📄',name:'DOCUMENTAR',desc:'Gere documentação',prompt:'Documenta este código: '},
];
function openPromptTemplates(){
  const grid=document.getElementById('ptGrid');
  if(grid)grid.innerHTML=PROMPT_TEMPLATES.map((t,i)=>`
    <div class="pt-item" onclick="useTemplate(${i})">
      <div class="pt-item-icon">${t.icon}</div>
      <div class="pt-item-name">${t.name}</div>
      <div class="pt-item-desc">${t.desc}</div>
    </div>`).join('');
  const panel=document.getElementById('promptTemplates');
  if(panel)panel.classList.toggle('show');
}
function closePromptTemplates(){document.getElementById('promptTemplates')?.classList.remove('show');}
function useTemplate(idx){
  const t=PROMPT_TEMPLATES[idx];if(!t)return;
  const inp=document.getElementById('cmdtext');
  if(inp){inp.value=t.prompt;inp.focus();const n=inp.value.length;const cc=document.getElementById('charCounter');if(cc)cc.textContent=n;}
  const ci=document.getElementById('cmdinput');if(ci)ci.classList.add('show');
  closePromptTemplates();
}

// ── SUGGESTION CHIPS ──────────────────────────────────────────────────────────
const _suggCache={};
async function generateSuggestions(lastResponse){
  if(!lastResponse||lastResponse.length<20)return;
  const container=document.getElementById('suggChips');
  if(!container)return;
  // Simple heuristic suggestions based on content
  const suggestions=[];
  const txt=lastResponse.toLowerCase();
  if(txt.includes('código')||txt.includes('function')||txt.includes('def ')){
    suggestions.push('Gera testes para este código');
    suggestions.push('Otimize esta função');
    suggestions.push('Explique linha por linha');
  } else if(txt.includes('erro')||txt.includes('bug')||txt.includes('problema')){
    suggestions.push('Como evitar este erro?');
    suggestions.push('Quais outros bugs podem existir?');
  } else if(txt.includes('arquitetura')||txt.includes('sistema')||txt.includes('banco')){
    suggestions.push('Crie o diagrama desta arquitetura');
    suggestions.push('Estime o custo deste sistema');
  } else {
    suggestions.push('Aprofunde este tópico');
    suggestions.push('Dê exemplos práticos');
    suggestions.push('Resuma em 3 pontos');
  }
  // Always offer these
  suggestions.push('Continue...');
  container.innerHTML=suggestions.slice(0,4).map(s=>`<button class="sugg-chip" onclick="useSugg(this)">${escHtml(s)}</button>`).join('');
  container.classList.add('show');
  setTimeout(()=>container.classList.remove('show'),18000);
}
function useSugg(btn){
  const text=btn.textContent;
  const inp=document.getElementById('cmdtext');
  const ci=document.getElementById('cmdinput');
  if(inp){inp.value=text;inp.focus();}
  if(ci)ci.classList.add('show');
  document.getElementById('suggChips')?.classList.remove('show');
}
// Patch showResponse to generate suggestions
const _origShowResp2=window.showResponse;
window.showResponse=function(text){
  _origShowResp2(text);
  setTimeout(()=>generateSuggestions(text),800);
  // Add action buttons inside response
  _injectNextActions(text);
};
function _injectNextActions(text){
  const resPanel=document.getElementById('respanel');
  if(!resPanel)return;
  let na=resPanel.querySelector('#nextActions');
  if(!na){na=document.createElement('div');na.id='nextActions';resPanel.appendChild(na);}
  const hasCode=text.includes('```');
  na.innerHTML=`
    <button class="nact-btn" onclick="copyResponse()">⎘ COPIAR</button>
    <button class="nact-btn" onclick="shareResponse()">↗ COMPARTILHAR</button>
    <button class="nact-btn" onclick="exportResponse()">↓ SALVAR</button>
    ${hasCode?'<button class="nact-btn" onclick="_tryLivePreview()">▶ PREVIEW</button>':''}
    <button class="nact-btn" onclick="clearResponse()">✕ FECHAR</button>`;
}

// ── PERSONA SYSTEM ────────────────────────────────────────────────────────────
let _currentPersona=localStorage.getItem('jarvis_persona')||'tecnico';
const PERSONA_PROMPTS={
  tecnico:'Seja técnico e preciso. Use terminologia de programação. Mostre código quando relevante.',
  amigavel:'Seja amigável e caloroso. Use analogias simples. Incentive o usuário.',
  formal:'Seja formal e profissional. Respostas concisas e estruturadas.',
  criativo:'Seja criativo e use analogias inesperadas. Pense fora da caixa.',
  direto:'Seja extremamente direto. Responda em 1-2 frases. Zero enrolação.',
};
const PERSONA_LABELS={tecnico:'⚙ TÉCNICO',amigavel:'😊 AMIGÁVEL',formal:'👔 FORMAL',criativo:'🎨 CRIATIVO',direto:'⚡ DIRETO'};
function setPersona(p){
  _currentPersona=p;
  localStorage.setItem('jarvis_persona',p);
  document.querySelectorAll('.persona-opt').forEach(el=>el.classList.toggle('active',el.dataset.persona===p));
  const badge=document.getElementById('personaBadge');
  if(badge)badge.textContent=PERSONA_LABELS[p]||p;
  document.getElementById('personaSelect')?.classList.remove('show');
  addEvent('ok','Persona: '+PERSONA_LABELS[p]);
  showToast('Persona: '+PERSONA_LABELS[p],'info');
}
function openPersonaSelect(){document.getElementById('personaSelect')?.classList.toggle('show');}
// Init persona badge
(()=>{
  const badge=document.getElementById('personaBadge');
  if(badge)badge.textContent=PERSONA_LABELS[_currentPersona]||_currentPersona;
  document.querySelectorAll('.persona-opt').forEach(el=>el.classList.toggle('active',el.dataset.persona===_currentPersona));
})();

// ── FOCUS MODE ────────────────────────────────────────────────────────────────
let _focusMode=false;
function toggleFocusMode(){
  _focusMode=!_focusMode;
  document.body.classList.toggle('focus-mode',_focusMode);
  const btn=document.getElementById('focusBtn');
  if(btn)btn.textContent=_focusMode?'SAIR FOCO':'FOCO';
  showToast(_focusMode?'MODO FOCO ATIVO':'MODO NORMAL','info');
}

// ── POMODORO TIMER ────────────────────────────────────────────────────────────
let _pomoState=null; // null | 'work' | 'break'
let _pomoTimer=null;
let _pomoSecs=25*60;
const POMO_WORK=25*60, POMO_BREAK=5*60;
function togglePomodoro(){
  if(_pomoState){
    clearInterval(_pomoTimer);_pomoTimer=null;_pomoState=null;
    const b=document.getElementById('pomoBadge');if(b){b.textContent='🍅 POMO';b.className='seg';b.classList.remove('active','break');}
    showToast('Pomodoro pausado','warn');
  }else{
    _startPomo('work');showToast('Pomodoro iniciado — 25min FOCO','success');
  }
}
function _startPomo(type){
  _pomoState=type;
  _pomoSecs=type==='work'?POMO_WORK:POMO_BREAK;
  const b=document.getElementById('pomoBadge');
  if(b){b.className='seg '+(type==='work'?'active':'break');}
  clearInterval(_pomoTimer);
  _pomoTimer=setInterval(()=>{
    _pomoSecs--;
    const m=Math.floor(_pomoSecs/60),s=_pomoSecs%60;
    const b2=document.getElementById('pomoBadge');
    if(b2)b2.textContent=`🍅 ${m}:${String(s).padStart(2,'0')}`;
    if(_pomoSecs<=0){
      clearInterval(_pomoTimer);
      if(_pomoState==='work'){
        _stats.pomodorosDone=(_stats.pomodorosDone||0)+1;_saveStats();_checkAchievements();
        showToast('🍅 POMODORO COMPLETO! Pausa de 5min','success',5000);
        addEvent('ok','Pomodoro completo! Iniciando pausa.');
        _startPomo('break');
      }else{
        _pomoState=null;
        showToast('☕ Pausa terminada! Pronto para foco?','info',4000);
        const b3=document.getElementById('pomoBadge');if(b3){b3.textContent='🍅 POMO';b3.className='seg';}
      }
    }
  },1000);
}

// ── TODO LIST ─────────────────────────────────────────────────────────────────
let _todos=JSON.parse(localStorage.getItem('jarvis_todos')||'[]');
function renderTodos(){
  const list=document.getElementById('todoList');if(!list)return;
  if(!_todos.length){list.innerHTML='<div class="todo-empty">Sem tarefas. Adicione abaixo.</div>';return;}
  list.innerHTML=_todos.map((t,i)=>`
    <div class="todo-item ${t.done?'done':''}" onclick="toggleTodoItem(${i})">
      <div class="todo-cb">${t.done?'✓':''}</div>
      <span>${escHtml(t.text)}</span>
      <button class="todo-del" onclick="event.stopPropagation();deleteTodo(${i})">✕</button>
    </div>`).join('');
}
function addTodo(){
  const inp=document.getElementById('todoInput');if(!inp||!inp.value.trim())return;
  _todos.unshift({text:inp.value.trim(),done:false,ts:Date.now()});
  inp.value='';
  localStorage.setItem('jarvis_todos',JSON.stringify(_todos));
  renderTodos();
}
function toggleTodoItem(i){
  if(_todos[i]){
    _todos[i].done=!_todos[i].done;
    if(_todos[i].done){_stats.todoDone=(_stats.todoDone||0)+1;_saveStats();}
    localStorage.setItem('jarvis_todos',JSON.stringify(_todos));
    renderTodos();
  }
}
function deleteTodo(i){
  _todos.splice(i,1);
  localStorage.setItem('jarvis_todos',JSON.stringify(_todos));
  renderTodos();
}
function toggleTodo(){
  const p=document.getElementById('todoPanel');
  if(!p)return;
  p.classList.toggle('show');
  if(p.classList.contains('show'))renderTodos();
}

// ── SESSION MANAGER ───────────────────────────────────────────────────────────
const _sessions=JSON.parse(localStorage.getItem('jarvis_sessions')||'[]');
function _initSessions(){
  const sel=document.getElementById('sessionDropdown');if(!sel)return;
  // Add current session
  if(_sessionId&&!_sessions.includes(_sessionId)){
    _sessions.unshift(_sessionId);
    if(_sessions.length>10)_sessions.pop();
    localStorage.setItem('jarvis_sessions',JSON.stringify(_sessions));
  }
  sel.innerHTML=`<option value="${_sessionId||''}">SESSÃO ATUAL</option>`+
    _sessions.filter(s=>s!==_sessionId).slice(0,6).map(s=>`<option value="${s}">${s.substring(0,18)}...</option>`).join('');
}
function switchSession(sid){
  if(!sid||sid===_sessionId)return;
  if(confirm('Trocar para sessão '+sid.substring(0,16)+'?')){
    localStorage.setItem('jarvis_session',sid);
    location.reload();
  }
}

// ── SHARE RESPONSE ────────────────────────────────────────────────────────────
async function shareResponse(){
  const text=document.getElementById('restext')?.innerText||_fullResponseText;
  if(!text)return;
  if(navigator.share){
    try{await navigator.share({title:'JARVIS — Resposta',text:text.substring(0,2000)});showToast('COMPARTILHADO!','success');}
    catch(e){if(e.name!=='AbortError')copyResponse();}
  }else{copyResponse();showToast('URL COPIADA (Web Share não disponível)','info');}
}

// ── VOICE MUTE ────────────────────────────────────────────────────────────────
let _ttsIsMuted=false;
function toggleMute(){
  _ttsIsMuted=!_ttsIsMuted;
  const btn=document.getElementById('muteBtn');
  if(btn){btn.textContent=_ttsIsMuted?'🔇':'🔊';btn.classList.toggle('muted',_ttsIsMuted);}
  showToast(_ttsIsMuted?'TTS SILENCIADO':'TTS ATIVADO','info');
}
// Patch playVoiceResponse to respect mute
const _origPlay=window.playVoiceResponse;
window.playVoiceResponse=function(path){
  if(_ttsIsMuted){addEvent('voice','TTS silenciado — sem áudio');return Promise.resolve();}
  return _origPlay(path);
};

// ── INCOGNITO MODE ────────────────────────────────────────────────────────────
let _incognito=false;
function toggleIncognito(){
  _incognito=!_incognito;
  document.body.classList.toggle('incognito',_incognito);
  showToast(_incognito?'MODO INCÓGNITO ATIVO — sem histórico':'MODO NORMAL ATIVO','warn');
  addEvent(_incognito?'warn':'ok','Modo incógnito: '+(_incognito?'ON':'OFF'));
}
// Patch addConvEntry to respect incognito
const _origAddConv=window.addConvEntry;
window.addConvEntry=function(role,text){
  if(_incognito&&role==='user')return 'incognito_'+Date.now();
  return _origAddConv(role,text);
};

// ── AUTO-LOCK ─────────────────────────────────────────────────────────────────
let _lockTimer=null;
const LOCK_TIMEOUT=15*60*1000; // 15 min
function _resetLockTimer(){
  clearTimeout(_lockTimer);
  _lockTimer=setTimeout(()=>{
    document.body.style.filter='blur(6px)';
    const overlay=document.createElement('div');
    overlay.id='lockOverlay';
    overlay.style.cssText='position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.9);cursor:pointer;flex-direction:column;gap:10px';
    overlay.innerHTML=`<div style="font-size:12px;letter-spacing:4px;color:rgba(0,229,255,0.6);text-transform:uppercase">JARVIS BLOQUEADO</div><div style="font-size:7px;color:rgba(0,229,255,0.3);letter-spacing:2px">CLIQUE PARA DESBLOQUEAR</div>`;
    overlay.onclick=()=>{overlay.remove();document.body.style.filter='';_resetLockTimer();};
    document.body.appendChild(overlay);
    addEvent('warn','Auto-lock ativado por inatividade');
  },LOCK_TIMEOUT);
}
['mousemove','keydown','click','touchstart'].forEach(ev=>document.addEventListener(ev,_resetLockTimer,{passive:true}));

// ── LIVE HTML PREVIEW ─────────────────────────────────────────────────────────
function openLivePreview(html){
  const backdrop=document.getElementById('livePreviewBackdrop');
  const preview=document.getElementById('livePreview');
  const frame=document.getElementById('livePreviewFrame');
  const srcDiv=document.getElementById('livePreviewSrc');
  if(!frame)return;
  frame.style.display='block';
  if(srcDiv){srcDiv.style.display='none';srcDiv.textContent=html;}
  frame.srcdoc=html;
  preview?.classList.add('show');
  backdrop?.classList.add('show');
}
function closeLivePreview(){
  document.getElementById('livePreview')?.classList.remove('show');
  document.getElementById('livePreviewBackdrop')?.classList.remove('show');
}
function togglePreviewSrc(){
  const frame=document.getElementById('livePreviewFrame');
  const src=document.getElementById('livePreviewSrc');
  const btn=document.getElementById('previewSrcBtn');
  if(!frame||!src)return;
  if(frame.style.display!=='none'){frame.style.display='none';src.style.display='block';if(btn)btn.textContent='VER PREVIEW';}
  else{frame.style.display='block';src.style.display='none';if(btn)btn.textContent='VER FONTE';}
}
function _tryLivePreview(){
  const text=_fullResponseText||'';
  const m=text.match(/```(?:html|HTML)?\n?([\s\S]*?)```/);
  if(m&&m[1]){openLivePreview(m[1]);}
  else if(text.includes('<html')||text.includes('<body')||text.includes('<div')){
    const start=text.indexOf('<');
    if(start>=0)openLivePreview(text.substring(start));
  }else{showToast('Nenhum HTML encontrado na resposta','warn');}
}
// Add preview button in code blocks
const _origRenderMd=window.renderMd;
window.renderMd=function(text){
  let result=_origRenderMd(text);
  // Replace COPIAR buttons in HTML code blocks with COPIAR + PREVIEW
  result=result.replace(/(<div class="md-code-wrap">.*?<button class="md-copy-btn"[^>]*>COPIAR<\/button>)/g,(match,p1)=>{
    // Only add preview for HTML blocks
    if(match.includes('html')||match.includes('HTML')){
      return match+'<button class="md-copy-btn" style="right:55px" onclick="_tryLivePreview()">▶</button>';
    }
    return match;
  });
  return result;
};

// ── SERVICE HEALTH CHECK ──────────────────────────────────────────────────────
async function checkServiceHealth(){
  const services=[
    {name:'Backend',url:`${API_URL}/health`,id:'svcBackend'},
    {name:'Ollama',url:`${API_URL}/health`,key:'ollama_ok',id:'svcOllama'},
    {name:'SQLite',url:`${API_URL}/health`,key:'sqlite_ok',id:'svcSqlite'},
    {name:'RAG',url:`${API_URL}/chat/rag/stats`,id:'svcRag'},
  ];
  const agentList=document.getElementById('agentList');
  if(!agentList)return;
  try{
    const health=await fetch(`${API_URL}/health`,{signal:AbortSignal.timeout(3000)}).then(r=>r.json());
    const svcHtml=`
      <div style="font-size:5px;letter-spacing:2px;color:rgba(0,229,255,0.22);margin-bottom:4px;text-transform:uppercase">SERVIÇOS</div>
      ${[
        {name:'Backend API',ok:health.status==='ok'},
        {name:'Ollama LLM',ok:health.ollama_ok!==false},
        {name:'SQLite DB',ok:health.sqlite_ok!==false},
        {name:'Memória',ok:true},
      ].map(s=>`<div class="svc-row"><span class="svc-dot ${s.ok?'ok':'err'}"></span>${s.name}</div>`).join('')}
      <div style="margin-top:6px;font-size:5px;letter-spacing:2px;color:rgba(0,229,255,0.22);margin-bottom:4px;text-transform:uppercase">AGENTES</div>`;
    // Prepend to agent list
    const existing=agentList.innerHTML;
    agentList.innerHTML=svcHtml+existing;
  }catch(e){}
}
setTimeout(checkServiceHealth,4000);
setInterval(checkServiceHealth,60000);

// ── AUTOCOMPLETE ──────────────────────────────────────────────────────────────
const AUTOCOMPLETE_TRIGGERS=[
  'analise o','analise este','gera o código','cria o código','explique','resume','arquitetura de',
  'diagram','cria diagrama','osint','investiga','testes para','corrija','otimize','documen',
];
let _acTimer=null,_acIdx=-1;
function _showAutocomplete(val){
  const ac=document.getElementById('autocomplete');
  if(!ac)return;
  if(!val||val.length<3){ac.classList.remove('show');ac.innerHTML='';return;}
  const matches=AUTOCOMPLETE_TRIGGERS.filter(t=>t.startsWith(val.toLowerCase())&&t!==val.toLowerCase()).slice(0,4);
  if(!matches.length){ac.classList.remove('show');return;}
  ac.innerHTML=matches.map((m,i)=>`<div class="ac-item" onmousedown="event.preventDefault();_useAcItem('${escHtml(m)}')">${escHtml(m)}</div>`).join('');
  ac.classList.add('show');
  _acIdx=-1;
}
function _useAcItem(val){
  const inp=document.getElementById('cmdtext');const cc=document.getElementById('charCounter');
  if(inp){inp.value=val+' ';inp.focus();if(cc)cc.textContent=inp.value.length;}
  const ac=document.getElementById('autocomplete');if(ac)ac.classList.remove('show');
}
if(document.getElementById('cmdtext')){
  document.getElementById('cmdtext').addEventListener('input',e=>{
    clearTimeout(_acTimer);_acTimer=setTimeout(()=>_showAutocomplete(e.target.value),200);
  });
  document.getElementById('cmdtext').addEventListener('keydown',e=>{
    const ac=document.getElementById('autocomplete');
    if(!ac?.classList.contains('show'))return;
    const items=ac.querySelectorAll('.ac-item');
    if(e.key==='ArrowDown'){e.preventDefault();_acIdx=Math.min(_acIdx+1,items.length-1);items.forEach((el,i)=>el.classList.toggle('ac-active',i===_acIdx));}
    else if(e.key==='ArrowUp'){e.preventDefault();_acIdx=Math.max(_acIdx-1,0);items.forEach((el,i)=>el.classList.toggle('ac-active',i===_acIdx));}
    else if(e.key==='Tab'&&_acIdx>=0){e.preventDefault();_useAcItem(items[_acIdx].textContent);}
    else if(e.key==='Escape'){ac.classList.remove('show');}
  });
  document.addEventListener('click',e=>{if(!e.target.closest('#cmdinput'))document.getElementById('autocomplete')?.classList.remove('show');});
}

// ── WAKE WORD VISUAL ──────────────────────────────────────────────────────────
function setWakeWordVisual(active){
  const led=document.getElementById('wakeWordLed');
  const dot=document.getElementById('wwlDot');
  const txt=document.getElementById('wwlTxt');
  if(!led)return;
  led.classList.add('show');
  if(dot)dot.classList.toggle('active',active);
  if(txt)txt.textContent=active?'ATIVADO':'WAKE';
}
// Connect to WS events for wake word
const _origWsMsg=ws?.onmessage;
setTimeout(()=>{
  if(ws){
    const origOnMsg=ws.onmessage;
    ws.onmessage=function(ev){
      try{
        const m=JSON.parse(ev.data);
        if(m.type==='wake_word'){setWakeWordVisual(true);setTimeout(()=>setWakeWordVisual(false),3000);}
      }catch(e){}
      if(origOnMsg)origOnMsg.call(ws,ev);
    };
  }
},2500);

// ── STICKER: PERSONA BADGE IN STATUS BAR ─────────────────────────────────────
(()=>{
  const stbar=document.getElementById('stbar');
  if(!stbar)return;
  const badge=document.createElement('span');
  badge.id='personaBadge';
  badge.className='seg';
  badge.textContent=PERSONA_LABELS[_currentPersona]||_currentPersona;
  badge.onclick=openPersonaSelect;
  stbar.appendChild(badge);
  const pomo=document.createElement('span');
  pomo.id='pomoBadge';pomo.className='seg';pomo.textContent='🍅 POMO';pomo.onclick=togglePomodoro;pomo.title='Iniciar Pomodoro 25min';
  stbar.appendChild(pomo);
  const streak=document.createElement('span');
  streak.id='streakBadge';streak.className='seg';streak.onclick=openStats;streak.title='Ver estatísticas';
  stbar.appendChild(streak);
  const adapt=document.createElement('span');
  adapt.id='adaptLevel';adapt.className='seg';adapt.onclick=openStats;adapt.title='Nível de adaptação';
  stbar.appendChild(adapt);
})();

// ── KEYBOARD SHORTCUTS v9.0 ───────────────────────────────────────────────────
document.addEventListener('keydown',e=>{
  if(e.target===document.getElementById('cmdtext'))return;
  if(e.ctrlKey||e.metaKey){
    if(e.key==='p'||e.key==='P'){e.preventDefault();openPromptTemplates();return;}
    if(e.key==='t'||e.key==='T'){e.preventDefault();toggleTodo();return;}
    if(e.key==='f'||e.key==='F'){e.preventDefault();toggleFocusMode();return;}
    if(e.key==='s'||e.key==='S'){e.preventDefault();openStats();return;}
    if(e.key==='k'||e.key==='K'){e.preventDefault();openKbModal();return;}
    if(e.key==='i'||e.key==='I'){e.preventDefault();toggleIncognito();return;}
    if(e.key==='m'||e.key==='M'){e.preventDefault();toggleMute();return;}
  }
},{passive:false});

// Update keyboard shortcuts modal with new shortcuts
const _kbBox=document.getElementById('kbBox');
if(_kbBox){
  const newSection=document.createElement('div');
  newSection.className='kb-section';
  newSection.innerHTML=`
    <div class="kb-section-title">v9.0 — NOVOS ATALHOS</div>
    <div class="kb-row"><span class="kb-key">CTRL+P</span><span class="kb-desc">Templates de prompt</span></div>
    <div class="kb-row"><span class="kb-key">CTRL+T</span><span class="kb-desc">Lista de tarefas (TODO)</span></div>
    <div class="kb-row"><span class="kb-key">CTRL+F</span><span class="kb-desc">Modo foco (oculta painéis)</span></div>
    <div class="kb-row"><span class="kb-key">CTRL+S</span><span class="kb-desc">Estatísticas de uso</span></div>
    <div class="kb-row"><span class="kb-key">CTRL+I</span><span class="kb-desc">Modo incógnito</span></div>
    <div class="kb-row"><span class="kb-key">CTRL+M</span><span class="kb-desc">Silenciar/ativar TTS</span></div>
    <div class="kb-row"><span class="kb-key">TAB</span><span class="kb-desc">Aceitar autocomplete</span></div>`;
  const closeBtn=_kbBox.querySelector('#kbClose');
  if(closeBtn)_kbBox.insertBefore(newSection,closeBtn);
  else _kbBox.appendChild(newSection);
}

// Update settings panel with new buttons
(()=>{
  const settingsPanel=document.getElementById('settingsPanel');
  if(!settingsPanel)return;
  const acSection=settingsPanel.querySelector('.s-section:last-of-type');
  if(!acSection)return;
  const newSection=document.createElement('div');
  newSection.innerHTML=`
    <div class="s-section">v9.0 — FUNCIONALIDADES</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:4px">
      <button class="sbtn" onclick="openStats()">📊 ESTATÍSTICAS</button>
      <button class="sbtn" onclick="openPromptTemplates()">⚡ TEMPLATES</button>
      <button class="sbtn" onclick="toggleTodo()">✅ TAREFAS</button>
      <button class="sbtn" onclick="toggleFocusMode()">🎯 MODO FOCO</button>
      <button class="sbtn" onclick="openPersonaSelect()">🎭 PERSONA</button>
      <button class="sbtn" onclick="toggleIncognito()">🕵 INCÓGNITO</button>
      <button class="sbtn" onclick="togglePomodoro()">🍅 POMODORO</button>
      <button class="sbtn" onclick="toggleMute()">🔊 MUTE TTS</button>
    </div>`;
  settingsPanel.appendChild(newSection);
})();

// ── BOOT v9.0 ─────────────────────────────────────────────────────────────────
setTimeout(()=>{
  _initStats();
  _initSessions();
  renderTodos();
  _updateAdaptLevel();
  // Show wake word LED
  document.getElementById('wakeWordLed')?.classList.add('show');
  addEvent('ok','JARVIS v9.0 — 90+ features ativas');
  addEvent('ok','NEW: Templates (Ctrl+P) | TODO (Ctrl+T) | Foco (Ctrl+F) | Stats (Ctrl+S)');
  addEvent('ok','NEW: Pomodoro 🍅 | Streak 🔥 | Achievements 🏆 | Autocomplete | Share');
  _checkAchievements();
  vibrateDevice([50,30,50]);
},2500);

// ── Laço de agente ──────────────────────────────────────────────────────────
// O agente lê arquivo, roda comando e se corrige sozinho. Isso leva tempo e o
// silêncio parece travamento: cada passo aparece no feed de eventos enquanto
// acontece, e a resposta final chega como token, igual a qualquer outra.

const _ROTULO_FERRAMENTA={
  read_file:'LENDO',write_file:'ESCREVENDO',edit_file:'EDITANDO',
  list_dir:'LISTANDO',search_code:'BUSCANDO',run_command:'EXECUTANDO',
  web_search:'PESQUISANDO',fetch_url:'ABRINDO',ask_stronger_model:'CONSULTANDO',
  recall:'LEMBRANDO',remember:'GRAVANDO',remember_preference:'GRAVANDO',
  search_knowledge:'CONSULTANDO MEMÓRIA'
};

function _alvoDaChamada(args){
  if(!args)return '';
  return String(args.command||args.path||args.query||args.pattern||args.url||'').slice(0,90);
}

function _onAgentEvent(m){
  if(m.event==='thinking'){
    const t=(m.text||'').trim();
    if(t)addEvent('ai','AGENTE: '+t.slice(0,120));
    return;
  }
  if(m.event==='tool_call'){
    const rotulo=_ROTULO_FERRAMENTA[m.name]||(m.name||'').toUpperCase();
    const alvo=_alvoDaChamada(m.arguments);
    addEvent('ai',rotulo+(alvo?' → '+alvo:''));
    const live=document.getElementById('stlive');
    if(live)live.textContent='STATUS: '+rotulo;
    return;
  }
  if(m.event==='tool_result'){
    if(m.error)addEvent('warn',(m.name||'?')+' FALHOU — o agente vai tentar outro caminho');
    return;
  }
  if(m.event==='escalating'){
    const motivos={repeticao:'repetindo a mesma chamada',erros:'erros em sequência',
                   vazio:'sem resposta',teto:'muitas iterações'};
    addEvent('warn','TRAVOU ('+(motivos[m.reason]||m.reason)+') — PEDINDO AJUDA A UM MODELO MAIOR');
    const live=document.getElementById('stlive');
    if(live)live.textContent='STATUS: CONSULTANDO MODELO MAIOR';
    return;
  }
  if(m.event==='escalated'){
    addEvent('ok',m.mode==='handover'
      ? 'MODELO MAIOR ASSUMIU A TAREFA'
      : 'ORIENTAÇÃO RECEBIDA — RETOMANDO SOZINHO');
    return;
  }
  if(m.event==='done'){
    const n=m.iterations||0;
    addEvent('ok',`AGENTE CONCLUIU — ${n} ${n===1?'passo':'passos'} (${m.reason||'completed'})`);
    const live=document.getElementById('stlive');
    if(live)live.textContent='STATUS: ONLINE';
  }
}

// ── Confirmação de ação irreversível ───────────────────────────────────────
// Nada de atalho de teclado para autorizar: aprovar exige clique deliberado.
// Esc nega, porque negar é sempre o lado seguro de errar.

let _confirmAtual=null,_confirmTimer=null;

function _elConfirm(){
  let el=document.getElementById('agentConfirm');
  if(el)return el;
  el=document.createElement('div');
  el.id='agentConfirm';
  el.setAttribute('role','alertdialog');
  el.setAttribute('aria-live','assertive');
  el.innerHTML=
    '<div class="ac-topo"><span class="ac-titulo">AÇÃO IRREVERSÍVEL</span>'+
    '<span class="ac-risco"></span></div>'+
    '<div class="ac-cmd"></div>'+
    '<div class="ac-motivo"></div>'+
    '<div class="ac-acoes">'+
      '<button type="button" class="ac-sim">AUTORIZAR</button>'+
      '<button type="button" class="ac-nao">NEGAR</button>'+
      '<span class="ac-dica">Esc nega</span>'+
    '</div>'+
    '<div class="ac-prazo"><i></i></div>';
  document.body.appendChild(el);
  el.querySelector('.ac-sim').addEventListener('click',()=>_responderConfirmacao(true));
  el.querySelector('.ac-nao').addEventListener('click',()=>_responderConfirmacao(false));
  return el;
}

function _pedirConfirmacao(m){
  const el=_elConfirm();
  _confirmAtual=m.id;
  const risco=(m.risk||'high').toLowerCase();
  el.classList.remove('risco-critical','risco-high','risco-medium');
  el.classList.add('risco-'+risco);
  el.querySelector('.ac-risco').textContent=risco.toUpperCase();
  el.querySelector('.ac-cmd').textContent=m.preview||m.name||'';
  el.querySelector('.ac-motivo').textContent=
    (m.reason?m.reason.charAt(0).toUpperCase()+m.reason.slice(1):'Ação sem desfazer.')+
    ' Nada acontece até você decidir.';
  el.classList.add('on');
  el.querySelector('.ac-nao').focus();

  addEvent('warn','AGUARDANDO SUA AUTORIZAÇÃO — '+(m.preview||m.name||''));
  try{window.JarvisTTS&&window.JarvisTTS.falar('Preciso da sua autorização, senhor.');}catch(e){}

  // Barra de prazo: responde "quanto tempo eu tenho", não é decoração.
  const prazo=Number(m.timeout_s)||120;
  const barra=el.querySelector('.ac-prazo i');
  barra.style.transition='none';barra.style.transform='scaleX(1)';
  requestAnimationFrame(()=>{
    barra.style.transition='transform '+prazo+'s linear';
    barra.style.transform='scaleX(0)';
  });
  clearTimeout(_confirmTimer);
  _confirmTimer=setTimeout(()=>_fecharConfirmacao(),prazo*1000+1500);
}

function _responderConfirmacao(aprovado){
  if(!_confirmAtual)return;
  const id=_confirmAtual;
  try{
    ws.send('__confirm__:'+id+':'+(aprovado?'yes':'no'));
    addEvent(aprovado?'ok':'warn',(aprovado?'AUTORIZADO':'NEGADO')+' — '+id);
  }catch(e){
    addEvent('err','NÃO CONSEGUI RESPONDER — conexão caiu');
  }
  _fecharConfirmacao();
}

function _fecharConfirmacao(){
  _confirmAtual=null;
  clearTimeout(_confirmTimer);
  const el=document.getElementById('agentConfirm');
  if(el)el.classList.remove('on');
}

document.addEventListener('keydown',(e)=>{
  if(e.key==='Escape'&&_confirmAtual)_responderConfirmacao(false);
});
