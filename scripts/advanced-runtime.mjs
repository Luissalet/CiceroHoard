import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {DRACOLoader} from 'three/addons/loaders/DRACOLoader.js';
import {KTX2Loader} from 'three/addons/loaders/KTX2Loader.js';
import {MeshoptDecoder} from 'three/addons/libs/meshopt_decoder.module.js';
import * as echarts from 'echarts';
import {animatedOptions} from './chart-options.mjs';

const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
const readSession=key=>{try{return sessionStorage.getItem(key);}catch{return null;}};
const writeSession=(key,value)=>{try{sessionStorage.setItem(key,value);}catch{}};
function fittedPath(world,camera,path,aspect){
  world.updateMatrixWorld(true);const bounds=new THREE.Box3();
  world.traverse(node=>{if(node.isMesh)bounds.expandByObject(node);});
  if(bounds.isEmpty())return path;
  const center=bounds.getCenter(new THREE.Vector3()),tan=Math.tan(THREE.MathUtils.degToRad(camera.fov)/2),corners=[];
  for(const x of [bounds.min.x,bounds.max.x])for(const y of [bounds.min.y,bounds.max.y])for(const z of [bounds.min.z,bounds.max.z])corners.push(new THREE.Vector3(x,y,z));
  return path.map(p=>{
    const direction=new THREE.Vector3().fromArray(p.position).sub(new THREE.Vector3().fromArray(p.target||[0,0,0]));
    if(direction.lengthSq()<1e-9)direction.set(6,5,8);direction.normalize();
    const rotation=new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().lookAt(direction,new THREE.Vector3(),camera.up)).invert();
    let distance=.1;
    for(const corner of corners){const v=corner.clone().sub(center).applyQuaternion(rotation);distance=Math.max(distance,Math.abs(v.x)/(tan*aspect)+v.z,Math.abs(v.y)/tan+v.z);}
    return {...p,position:center.clone().addScaledVector(direction,distance*1.16).toArray(),target:center.toArray()};
  });
}
async function scene(el){
  const b=JSON.parse(el.dataset.scene),world=new THREE.Scene();world.background=new THREE.Color(b.background||'#f4f6f8');
  const canvas=document.createElement('canvas');el.append(canvas);
  let renderer;try{renderer=new THREE.WebGLRenderer({canvas,antialias:true,preserveDrawingBuffer:true});}catch(error){el.dataset.error=String(error);return;}
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.outputColorSpace=THREE.SRGBColorSpace;
  renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=b.exposure||1;
  renderer.shadowMap.enabled=!!b.shadows;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
  const camera=new THREE.PerspectiveCamera(45,1,.05,1000);
  for(const l of b.lights||[{type:'hemisphere',intensity:2},{type:'directional',intensity:3,position:[5,9,7]}]){
    const constructors={hemisphere:()=>new THREE.HemisphereLight(l.color||'#ffffff',l.ground_color||'#667788',l.intensity),
      ambient:()=>new THREE.AmbientLight(l.color,l.intensity),directional:()=>new THREE.DirectionalLight(l.color||'#ffffff',l.intensity),
      point:()=>new THREE.PointLight(l.color,l.intensity,l.distance||0),spot:()=>new THREE.SpotLight(l.color,l.intensity,l.distance||0,l.angle||Math.PI/3)};
    const light=constructors[l.type]();light.position.fromArray(l.position||[5,9,7]);light.castShadow=!!l.cast_shadow;
    if(light.target){light.target.position.fromArray(l.target||[0,0,0]);world.add(light.target);}world.add(light);
  }
  const shapes={box:()=>new THREE.BoxGeometry(1,1,1),sphere:()=>new THREE.SphereGeometry(.5,32,24),
    cylinder:()=>new THREE.CylinderGeometry(.5,.5,1,32),cone:()=>new THREE.ConeGeometry(.5,1,32),torus:()=>new THREE.TorusGeometry(.5,.15,20,48)};
  const labels=[],mixers=[];
  const manager=new THREE.LoadingManager();manager.setURLModifier(url=>b._decoders?.[url.split('/').at(-1)]||url);
  const draco=new DRACOLoader(manager).setDecoderPath('cicero-decoder/');
  const ktx=new KTX2Loader(manager).setTranscoderPath('cicero-decoder/').detectSupport(renderer);
  const loader=new GLTFLoader(manager).setDRACOLoader(draco).setKTX2Loader(ktx).setMeshoptDecoder(MeshoptDecoder);
  await Promise.all(b.objects.map(async o=>{
    let mesh;
    if(o.shape==='model'){
      const data=b._models?.[o.id];if(!data?.document)throw Error(data?.error||'Missing model resource');
      const gltf=await loader.parseAsync(JSON.stringify(data.document),'');mesh=gltf.scene;
      if(o.fit!==false){const bounds=new THREE.Box3().setFromObject(mesh),size=bounds.getSize(new THREE.Vector3());const scale=2/Math.max(size.x,size.y,size.z,1e-9);
        const centered=new THREE.Group();mesh.position.sub(bounds.getCenter(new THREE.Vector3()));centered.add(mesh);centered.scale.setScalar(scale);mesh=centered;}
      if(o.animation_clip!=null){if(!gltf.animations[o.animation_clip])throw Error('Missing animation clip '+o.animation_clip);const mixer=new THREE.AnimationMixer(gltf.scene);mixer.clipAction(gltf.animations[o.animation_clip]).play();mixer.timeScale=o.animation_speed??1;mixers.push(mixer);}
    }else mesh=new THREE.Mesh(shapes[o.shape||'box'](),new THREE.MeshStandardMaterial({color:o.color||'#278C8C',roughness:o.roughness??.65,metalness:o.metalness??.1}));
    mesh.traverse(node=>{if(!node.isMesh)return;node.castShadow=!!o.cast_shadow;node.receiveShadow=!!o.receive_shadow;
      if(o.material){const apply=m=>{const next=m.clone();for(const [key,value] of Object.entries(o.material)){if(value==null)continue;if(key==='color')next.color?.set(value);else next[key]=value;}if(o.material.opacity!=null)next.transparent=o.material.opacity<1;return next;};node.material=Array.isArray(node.material)?node.material.map(apply):apply(node.material);}});
    mesh.name=o.id;mesh.position.fromArray(o.position||[0,0,0]);mesh.rotation.set(...(o.rotation||[0,0,0]));mesh.scale.multiply(new THREE.Vector3().fromArray(o.scale||[1,1,1]));world.add(mesh);
  }));
  el.dataset.modelsLoaded=String(b.objects.filter(o=>o.shape==='model').length);
  for(const o of b.objects)if(o.label){const label=document.createElement('span');label.textContent=o.label;label.style.cssText='position:absolute;font:18px sans-serif;color:#17212b;background:#ffffffdd;padding:3px 6px;pointer-events:none;transform:translate(-50%,-100%);white-space:nowrap';el.append(label);labels.push({label,position:new THREE.Vector3().fromArray(o.position||[0,0,0])});}
  if(b.grid)world.add(new THREE.GridHelper(12,12,0x8094a0,0xcad4da));
  const authored=b.camera_path||[{time:0,position:[6,5,8],target:[0,0,0]}];
  const path=b.auto_frame?fittedPath(world,camera,authored,el.clientWidth/Math.max(1,el.clientHeight)):authored;
  const initial=path[0];camera.position.fromArray(initial.position);camera.lookAt(...(initial.target||[0,0,0]));
  const controls=new OrbitControls(camera,canvas);controls.enabled=b.orbit!==false;controls.enableDamping=true;controls.target.fromArray(initial.target||[0,0,0]);
  let touched=false;controls.addEventListener('start',()=>{touched=true;});
  const resize=()=>{const w=Math.max(1,el.clientWidth),h=Math.max(1,el.clientHeight);renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();};
  const observer=new ResizeObserver(resize);observer.observe(el);resize();let lastFrame=performance.now(),elapsed=0;
  function draw(){
    if(!document.documentElement.contains(el)){observer.disconnect();renderer.dispose();controls.dispose();draco.dispose();ktx.dispose();for(const mixer of mixers)mixer.stopAllAction();world.traverse(node=>{node.geometry?.dispose();for(const m of Array.isArray(node.material)?node.material:[node.material])if(m){for(const value of Object.values(m))if(value?.isTexture)value.dispose();m.dispose();}});return;}
    const hidden=el.closest('section')?.classList.contains('past')||el.closest('section')?.classList.contains('future');
    const now=performance.now(),delta=(now-lastFrame)/1000;lastFrame=now;
    if(!hidden){
      elapsed+=delta;
      if(!reduced)for(const mixer of mixers)mixer.update(delta);
      if(!reduced&&!touched&&path.length>1){const duration=path.at(-1).time;
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
  const palette=JSON.parse(el.dataset.palette);
  const key='cicero-chart:'+location.pathname+':'+el.dataset.chartId,previous=readSession(key);
  const section=el.closest('section'),isPresented=()=>!el.closest('.reveal')||section?.classList.contains('present');
  let chart=null,visible=false,activation=0,generation=0,animationFrame=null,stateTimer=null;
  const option=data=>animatedOptions({block:data,palette,font:getComputedStyle(el).fontFamily,lang:document.documentElement.lang,
    width:el.clientWidth,height:el.clientHeight,font_scale:Number(el.dataset.fontScale)||1});
  let current=b,state=0;
  const states=b.states||[],dwell=Math.max(2000,(b.animation_ms||1000)*2);
  const animationSpan=data=>(b.animation_ms||1000)+(b.animation==='series'?Math.max(0,data.series.length-1)*250:b.animation==='points'?Math.max(0,data.categories.length-1)*80:0);
  function stop(){generation++;if(animationFrame!==null)cancelAnimationFrame(animationFrame);if(stateTimer!==null)clearTimeout(stateTimer);animationFrame=stateTimer=null;}
  function nextState(token){
    if(token!==generation||!isPresented())return;
    current={...b,...states[state++%states.length]};chart.setOption(option(current),{replaceMerge:['series']});writeSession(key,JSON.stringify(current));el.dataset.state=String(state);
    stateTimer=setTimeout(()=>nextState(token),animationSpan(current)+dwell);
  }
  function activate(){
    const now=isPresented();
    if(now!==visible)stop();
    if(now&&!visible){
      const token=generation;
      const first=!chart;
      if(first){el.innerHTML='';chart=echarts.init(el,null,{renderer:'svg'});}else chart.clear();
      current=b;state=0;el.dataset.state='0';el.dataset.animationReady='false';
      if(first&&b.animation==='update'&&previous)try{chart.setOption({...option(JSON.parse(previous)),animation:false});}catch{}
      animationFrame=requestAnimationFrame(()=>{if(token!==generation||!isPresented())return;animationFrame=null;chart.resize();chart.setOption(option(b),{replaceMerge:['series']});writeSession(key,JSON.stringify(b));el.dataset.animationReady='true';el.dataset.animationActivation=String(++activation);if(states.length)stateTimer=setTimeout(()=>nextState(token),animationSpan(b)+dwell);});
    }
    visible=now;
  }
  if(section)new MutationObserver(activate).observe(section,{attributes:true,attributeFilter:['class']});
  activate();
  new ResizeObserver(()=>chart?.resize()).observe(el);
  addEventListener('beforeunload',()=>writeSession(key,JSON.stringify(current)));
}

async function poll(el){
  const b=JSON.parse(el.dataset.poll);if(!b.poll_url)return;
  const url=b.poll_url;let participant=readSession('cicero-participant');if(!participant){participant=crypto.randomUUID();writeSession('cicero-participant',participant);}
  const status=el.querySelector('[role=status]');
  el.querySelectorAll('button').forEach((button,i)=>button.addEventListener('click',async()=>{try{
    const r=await fetch(url+'/vote',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({participant,choice:i})});
    if(!r.ok)throw Error((await r.json()).error);el.querySelectorAll('button').forEach(other=>other.setAttribute('aria-pressed',String(other===button)));status.textContent=document.documentElement.lang==='es'?'Voto guardado':'Vote saved';await refresh();
  }catch(error){status.textContent=error.message;}}));
  async function refresh(){try{const r=await fetch(url);if(!r.ok)return;const data=await r.json();el.querySelectorAll('button').forEach((button,i)=>{button.disabled=!data.open;button.querySelector('span').textContent=data.counts[i]||0;});}catch{}}
  await refresh();setInterval(refresh,3000);
}

document.querySelectorAll('[data-scene]').forEach(el=>scene(el).catch(error=>{el.dataset.error=String(error).replace(/data:[^"\s]+/g,'[embedded model resource]').slice(0,400);}));
document.querySelectorAll('[data-chart]').forEach(animatedChart);
document.querySelectorAll('[data-poll]').forEach(poll);
