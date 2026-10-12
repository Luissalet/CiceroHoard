import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import * as echarts from 'echarts';

const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
function scene(el){
  const b=JSON.parse(el.dataset.scene),world=new THREE.Scene();world.background=new THREE.Color(b.background||'#f4f6f8');
  const canvas=document.createElement('canvas');el.append(canvas);
  let renderer;try{renderer=new THREE.WebGLRenderer({canvas,antialias:true,preserveDrawingBuffer:true});}catch(error){el.dataset.error=String(error);return;}
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.outputColorSpace=THREE.SRGBColorSpace;
  const camera=new THREE.PerspectiveCamera(45,1,.05,1000);
  const ambient=new THREE.HemisphereLight(0xffffff,0x667788,2);world.add(ambient);
  const light=new THREE.DirectionalLight(0xffffff,3);light.position.set(5,9,7);world.add(light);
  const shapes={box:()=>new THREE.BoxGeometry(1,1,1),sphere:()=>new THREE.SphereGeometry(.5,32,24),
    cylinder:()=>new THREE.CylinderGeometry(.5,.5,1,32),cone:()=>new THREE.ConeGeometry(.5,1,32),torus:()=>new THREE.TorusGeometry(.5,.15,20,48)};
  const labels=[];
  for(const o of b.objects){const mesh=new THREE.Mesh(shapes[o.shape||'box'](),new THREE.MeshStandardMaterial({color:o.color||'#278C8C',roughness:o.roughness??.65,metalness:o.metalness??.1}));
    mesh.name=o.id;mesh.position.fromArray(o.position||[0,0,0]);mesh.rotation.set(...(o.rotation||[0,0,0]));mesh.scale.fromArray(o.scale||[1,1,1]);world.add(mesh);}
  for(const o of b.objects)if(o.label){const label=document.createElement('span');label.textContent=o.label;label.style.cssText='position:absolute;font:18px sans-serif;color:#17212b;background:#ffffffdd;padding:3px 6px;pointer-events:none;transform:translate(-50%,-100%);white-space:nowrap';el.append(label);labels.push({label,position:new THREE.Vector3().fromArray(o.position||[0,0,0])});}
  if(b.grid)world.add(new THREE.GridHelper(12,12,0x8094a0,0xcad4da));
  const path=b.camera_path||[{time:0,position:[6,5,8],target:[0,0,0]}],initial=path[0];camera.position.fromArray(initial.position);camera.lookAt(...(initial.target||[0,0,0]));
  const controls=new OrbitControls(camera,canvas);controls.enabled=b.orbit!==false;controls.enableDamping=true;controls.target.fromArray(initial.target||[0,0,0]);
  let touched=false;controls.addEventListener('start',()=>{touched=true;});
  const resize=()=>{const w=Math.max(1,el.clientWidth),h=Math.max(1,el.clientHeight);renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();};
  new ResizeObserver(resize).observe(el);resize();const start=performance.now();
  function draw(){
    if(!document.documentElement.contains(el)){renderer.dispose();controls.dispose();return;}
    const hidden=el.closest('section')?.classList.contains('past')||el.closest('section')?.classList.contains('future');
    if(!hidden){
      if(!reduced&&!touched&&path.length>1){const duration=path.at(-1).time;const elapsed=(performance.now()-start)/1000;
        const t=b.loop===false?Math.min(duration,elapsed):elapsed%duration;let end=path.findIndex(p=>p.time>=t);if(end<1)end=1;
        const a=path[end-1],z=path[end],mix=THREE.MathUtils.smoothstep(t,a.time,z.time);
        camera.position.fromArray(a.position).lerp(new THREE.Vector3().fromArray(z.position),mix);
        controls.target.fromArray(a.target||[0,0,0]).lerp(new THREE.Vector3().fromArray(z.target||[0,0,0]),mix);
      }
      controls.update();renderer.render(world,camera);el.dataset.ready='true';el.dataset.camera=JSON.stringify(camera.position.toArray());el.dataset.frame=String(Number(el.dataset.frame||0)+1);
      for(const item of labels){const p=item.position.clone().project(camera);item.label.style.display=p.z>1||Math.abs(p.x)>1||Math.abs(p.y)>1?'none':'';item.label.style.left=(p.x+1)*el.clientWidth/2+'px';item.label.style.top=(1-p.y)*el.clientHeight/2+'px';}
    }
    requestAnimationFrame(draw);
  }draw();
}

function animatedChart(el){
  const b=JSON.parse(el.dataset.chart);if(!b.animation||b.animation==='none'||reduced)return;
  const palette=JSON.parse(el.dataset.palette),horizontal=b.chart==='bar_horizontal';
  if(!['bar','bar_horizontal','line','area','scatter','bubble'].includes(b.chart))return;
  const key='cicero-chart:'+location.pathname+':'+el.dataset.chartId,previous=sessionStorage.getItem(key);
  el.innerHTML='';const chart=echarts.init(el,null,{renderer:'svg'});
  const option=data=>({animation:true,animationDuration:b.animation_ms||1000,animationDurationUpdate:b.animation_ms||1000,
    animationEasingUpdate:'cubicInOut',color:[palette.accent,palette.accent2,'#b36b44','#528d6a'],
    title:{text:data.title===b.title?'':data.title||'',textStyle:{fontSize:22,color:palette.text}},
    legend:{show:b.show_legend??data.series.length>1,bottom:0,textStyle:{fontSize:18,color:palette.text}},
    tooltip:{trigger:'item',valueFormatter:value=>`${value}${b.unit?' '+b.unit:''}`},
    textStyle:{fontSize:18,color:palette.text},grid:{left:horizontal?110:70,right:100,bottom:90,top:data.title?60:35,containLabel:true},
    xAxis:{type:horizontal||['scatter','bubble'].includes(b.chart)?'value':'category',name:b.x_label||(horizontal?b.unit:'')||'',nameGap:25,nameTextStyle:{fontSize:18},data:horizontal?undefined:data.categories,axisLabel:{color:palette.text,fontSize:18}},
    yAxis:{type:horizontal?'category':'value',name:b.y_label||(!horizontal?b.unit:'')||'',nameTextStyle:{fontSize:18},data:horizontal?data.categories:undefined,inverse:horizontal,scale:b.zero_baseline===false,axisLabel:{color:palette.text,fontSize:18}},
    series:data.series.map((s,i)=>({id:s.name||String(i),name:s.name,type:['line','area'].includes(b.chart)?'line':b.chart==='scatter'||b.chart==='bubble'?'scatter':'bar',
      stack:b.stacked?'total':undefined,itemStyle:s.color?{color:s.color}:undefined,symbolSize:(value,params)=>b.chart==='bubble'?Math.max(6,Math.sqrt(s.sizes[params.dataIndex]||0)*4):10,
      data:s.values.map((value,j)=>({id:data.categories[j]+':'+j,value:s.x_values?[s.x_values[j],value]:value,
        itemStyle:b.highlight?.length&&!b.highlight.includes(j)?{opacity:.45}:undefined})),
      areaStyle:b.chart==='area'?{opacity:.15}:undefined,label:{show:b.show_values!==false,position:horizontal?'right':'top',fontSize:18,color:palette.text,formatter:p=>`${Array.isArray(p.value)?p.value[1]:p.value}${b.unit?' '+b.unit:''}`},
      markLine:i===0?{symbol:'none',label:{fontSize:18,formatter:p=>p.name},data:(b.references||[]).map(r=>({name:r.label,[horizontal?'xAxis':'yAxis']:r.value}))}:undefined,
      markPoint:{symbol:'pin',symbolSize:20,label:{fontSize:18,position:'top',formatter:p=>p.name},data:(b.annotations||[]).filter(a=>a.series===i&&a.category<s.values.length).map(a=>({name:a.text,coord:s.x_values?[s.x_values[a.category],s.values[a.category]]:horizontal?[s.values[a.category],data.categories[a.category]]:[data.categories[a.category],s.values[a.category]]}))},
      animationDelay:b.animation==='series'?i*250:b.animation==='points'?j=>j*80:0,universalTransition:true}))});
  if(previous)try{chart.setOption(option(JSON.parse(previous)));}catch{}
  let current=b;
  requestAnimationFrame(()=>{chart.setOption(option(b),{replaceMerge:['series']});sessionStorage.setItem(key,JSON.stringify(b));el.dataset.animationReady='true';});
  const states=b.states||[];let state=0;
  if(states.length)setInterval(()=>{const section=el.closest('section');if(!section?.classList.contains('past')&&!section?.classList.contains('future')){current={...b,...states[state++%states.length]};chart.setOption(option(current),{replaceMerge:['series']});sessionStorage.setItem(key,JSON.stringify(current));el.dataset.state=String(state);}},Math.max(2000,(b.animation_ms||1000)*2));
  new ResizeObserver(()=>chart.resize()).observe(el);
  addEventListener('beforeunload',()=>sessionStorage.setItem(key,JSON.stringify(current)));
}

async function poll(el){
  const b=JSON.parse(el.dataset.poll);if(!b.poll_url)return;
  const url=b.poll_url;let participant=sessionStorage.getItem('cicero-participant');if(!participant){participant=crypto.randomUUID();sessionStorage.setItem('cicero-participant',participant);}
  const status=el.querySelector('[role=status]');
  el.querySelectorAll('button').forEach((button,i)=>button.addEventListener('click',async()=>{try{
    const r=await fetch(url+'/vote',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({participant,choice:i})});
    if(!r.ok)throw Error((await r.json()).error);el.querySelectorAll('button').forEach(other=>other.setAttribute('aria-pressed',String(other===button)));status.textContent=document.documentElement.lang==='es'?'Voto guardado':'Vote saved';await refresh();
  }catch(error){status.textContent=error.message;}}));
  async function refresh(){try{const r=await fetch(url);if(!r.ok)return;const data=await r.json();el.querySelectorAll('button').forEach((button,i)=>{button.disabled=!data.open;button.querySelector('span').textContent=data.counts[i]||0;});}catch{}}
  await refresh();setInterval(refresh,3000);
}

document.querySelectorAll('[data-scene]').forEach(scene);
document.querySelectorAll('[data-chart]').forEach(animatedChart);
document.querySelectorAll('[data-poll]').forEach(poll);
