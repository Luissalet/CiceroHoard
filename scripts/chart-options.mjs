export function chartOptions(req){
 const b=req.block,w=req.width,h=req.height,p=req.palette,g=req.font_scale||1;
 const fmt=v=>new Intl.NumberFormat(req.lang==='es'?'es-ES':'en-US',{maximumFractionDigits:3}).format(v);
 const colors=[p.accent,p.accent2,'#667B89','#C16B36','#547B55','#A56C90'];
 const cats=b.categories||[],series=b.series||[],horizontal=['bar_horizontal','dot','dumbbell'].includes(b.chart);
 const values=[...series.flatMap(s=>[...s.values,...(s.lower||[]),...(s.upper||[])]),...(b.references||[]).map(r=>r.value)].filter(v=>v!=null);if(!values.length)values.push(0);
 const limits=b.zero_baseline===false?[Math.min(...values),Math.max(...values)]:[Math.min(0,...values),Math.max(0,...values)];
 const option={animation:false,color:colors,backgroundColor:p.background,
 textStyle:{fontFamily:req.font,fontSize:18,color:p.text},aria:{enabled:true},
 grid:{left:horizontal?150:80,right:70,top:series.length>1&&b.show_legend!==false?65:26,bottom:70,containLabel:true},
 legend:{show:b.show_legend??(series.length>1),top:2,textStyle:{fontSize:18,color:p.text}},
 tooltip:{trigger:'axis'},xAxis:{type:horizontal?'value':'category',data:horizontal?undefined:cats,
 name:horizontal?(b.unit||''):(b.x_label||''),nameLocation:'middle',nameGap:44,
 axisLabel:{fontSize:18,color:p.text,interval:0,formatter:horizontal?fmt:undefined},axisLine:{show:false},axisTick:{show:false},
 splitLine:{show:horizontal,lineStyle:{color:'#DFE6EB'}},min:horizontal?limits[0]:undefined},
 yAxis:{type:horizontal?'category':'value',data:horizontal?cats:undefined,inverse:horizontal,
 name:horizontal?'':(b.y_label||b.unit||''),nameTextStyle:{fontSize:18,color:p.text},
 axisLabel:{fontSize:18,color:p.text,interval:0,formatter:horizontal?undefined:fmt},axisLine:{show:false},axisTick:{show:false},
 splitLine:{show:!horizontal,lineStyle:{color:'#DFE6EB'}},min:horizontal?undefined:limits[0],
 max:!horizontal&&b.chart==='band'?limits[1]:undefined},series:[]};
 const label={show:b.show_values??(cats.length*series.length<=14),fontSize:19,color:p.text,formatter:arg=>fmt(Array.isArray(arg.value)?arg.value[1]:arg.value)};
 const refs=(b.references||[]).map(r=>({[horizontal?'xAxis':'yAxis']:r.value,name:r.label}));
 for(let i=0;i<series.length;i++){
  const s=series[i],color=s.color||colors[i],data=s.values.map((v,j)=>({value:v,
    itemStyle:b.highlight?.length?{color:b.highlight.includes(j)?color:'#CFD9E0'}:undefined}));
  const item={name:s.name,type:['line','area','band'].includes(b.chart)?'line':'bar',data,
   itemStyle:{color},lineStyle:{width:4,color},symbol:'circle',symbolSize:9,
   connectNulls:false,label:{...label,position:horizontal?'right':'top'},barMaxWidth:70,
   stack:b.stacked?'total':undefined,markLine:refs.length?{symbol:'none',data:refs,
    lineStyle:{color:p.accent2,type:'dashed'},label:{formatter:'{b}',fontSize:17}}:undefined};
  if(['line','area','band','scatter','bubble'].includes(b.chart)&&s.x_values){
   const allX=series.flatMap(v=>v.x_values||[]);
   option.xAxis={...option.xAxis,type:'value',data:undefined,min:Math.min(...allX),max:Math.max(...allX),
     axisLabel:{fontSize:18,color:p.text,formatter:fmt}};
   item.data=s.values.map((v,j)=>v==null?null:[s.x_values[j],v]);
  }
  if(b.chart==='area')item.areaStyle={opacity:0.15};
  if(['scatter','bubble'].includes(b.chart)){item.type='scatter';item.symbolSize=b.chart==='bubble'?(value,params)=>55*Math.sqrt(s.sizes[params.dataIndex]/(Math.max(...s.sizes)||1)):13;}
  if(b.chart==='dot'){item.type='scatter';item.data=s.values.map((v,j)=>[v,j]).filter(v=>v[0]!=null);item.symbolSize=14;item.label={...label,formatter:a=>fmt(a.value[0]),position:'right'};}
  if(['pie','donut'].includes(b.chart)){
   option.xAxis=option.yAxis=undefined;option.grid=undefined;
   item.type='pie';item.radius=b.chart==='donut'?['48%','76%']:'75%';item.center=['43%','52%'];
   item.data=s.values.map((v,j)=>({name:cats[j],value:v})).filter(v=>v.value!=null);item.label={show:true,fontSize:18,formatter:a=>`${a.name}: ${fmt(a.value)}`};
   option.series=[item];break;
  }
  if(b.chart==='funnel'){
   option.xAxis=option.yAxis=undefined;option.legend.show=false;item.type='funnel';
   item.data=s.values.map((v,j)=>({name:cats[j],value:v})).filter(v=>v.value!=null);item.sort='none';item.left='18%';item.right='18%';item.top=20;item.bottom=20;item.gap=10;
   item.label={show:true,fontSize:21,color:p.text,position:'right',formatter:a=>`${a.name}: ${fmt(a.value)}`};option.series=[item];break;
  }
  if(b.chart==='band'){
   const points=s.x_values;
   option.series.push({type:'custom',name:`${s.name} intervalo`,silent:true,z:0,data:[0],renderItem:(params,api)=>{
    const children=[];let upper=[],lower=[];
    const flush=()=>{if(upper.length>1)children.push({type:'polygon',shape:{points:upper.concat(lower.reverse())},style:{fill:color,opacity:.14}});upper=[];lower=[];};
    for(let j=0;j<points.length;j++){if(s.values[j]==null||s.lower[j]==null||s.upper[j]==null){flush();continue;}upper.push(api.coord([points[j],s.upper[j]]));lower.push(api.coord([points[j],s.lower[j]]));}flush();
    return {type:'group',children};
   }});item.label.show=false;
  }
  option.series.push(item);
 }
 if(b.chart==='dumbbell'){
  option.legend={show:b.show_legend!==false,top:2,data:series.map(s=>s.name),textStyle:{fontSize:18,color:p.text}};
  option.series=[{type:'custom',data:cats.map((_,j)=>[series[0].values[j],series[1].values[j],j]).filter(v=>v[0]!=null&&v[1]!=null),renderItem:(params,api)=>{
   const a=api.coord([api.value(0),api.value(2)]),z=api.coord([api.value(1),api.value(2)]);
   return {type:'group',children:[{type:'line',shape:{x1:a[0],y1:a[1],x2:z[0],y2:z[1]},style:{stroke:'#A7B9C4',lineWidth:4}},
    ...[a,z].flatMap((pt,k)=>[{type:'circle',shape:{cx:pt[0],cy:pt[1],r:9*g},style:{fill:series[k].color||colors[k]}},
     {type:'text',style:{x:pt[0],y:pt[1]+(k?19:-19)*g,text:fmt(api.value(k)),font:`${19*g}px ${req.font}`,fill:p.text,align:'center',verticalAlign:k?'top':'bottom'}}]) ]};
  }},...series.map((s,i)=>({name:s.name,type:'scatter',data:s.values.map((v,j)=>[v,j]).filter(v=>v[0]!=null),symbolSize:18,itemStyle:{color:s.color||colors[i]}}))];
 }
 if(b.chart==='heatmap'){
  option.xAxis={type:'category',data:series.map(s=>s.name),axisLabel:{fontSize:18,color:p.text},axisTick:{show:false},axisLine:{show:false}};
  option.yAxis={type:'category',data:cats,inverse:true,axisLabel:{fontSize:18,color:p.text},axisTick:{show:false},axisLine:{show:false}};
  option.visualMap={min:Math.min(...values),max:Math.max(...values),show:false,inRange:{color:['#EDF4F7',p.accent]}};option.legend.show=false;
  option.series=[{type:'heatmap',data:series.flatMap((s,i)=>s.values.map((v,j)=>[i,j,v]).filter(v=>v[2]!=null)),
   label:{show:true,fontSize:23,formatter:a=>fmt(a.value[2])},itemStyle:{borderColor:p.background,borderWidth:5}}];
 }
 if(b.chart==='waterfall'){
  let running=0;const changes=series[0].values.map((v,j)=>{if(v==null)return null;const before=running;running+=v;return [j,before,running,v]}).filter(Boolean);
  option.yAxis.min=Math.min(0,...changes.flatMap(v=>[v[1],v[2]]));option.yAxis.max=Math.max(0,...changes.flatMap(v=>[v[1],v[2]]));
  option.series=[{name:series[0].name,type:'custom',data:changes,renderItem:(params,api)=>{
   const a=api.coord([api.value(0),api.value(1)]),z=api.coord([api.value(0),api.value(2)]),bw=Math.min(70,api.size([1,0])[0]*.6);
   return {type:'group',children:[{type:'rect',shape:{x:a[0]-bw/2,y:Math.min(a[1],z[1]),width:bw,height:Math.max(1,Math.abs(a[1]-z[1]))},style:{fill:api.value(3)>=0?p.accent:p.accent2}},
    {type:'text',style:{x:a[0],y:Math.min(a[1],z[1])-12,text:fmt(api.value(3)),font:`${19*g}px ${req.font}`,fill:p.text,align:'center',verticalAlign:'bottom'}}]};
  }}];option.legend.show=false;
 }
 for(const note of b.annotations||[]){
  const target=option.series.find(s=>s.name===series[note.series]?.name);
  if(target)target.markPoint={symbol:'pin',symbolSize:1,data:[...(target.markPoint?.data||[]),{coord:horizontal?[series[note.series].values[note.category],note.category]:[series[note.series].x_values?.[note.category]??note.category,series[note.series].values[note.category]],value:note.text}],
   label:{show:true,formatter:'{c}',fontSize:17,color:p.accent2,backgroundColor:p.background,padding:6,position:'top'}};
 }
 const scaleFields=new Set(['fontSize','nameGap','symbolSize','barMaxWidth','left','right','top','bottom']);
 function scaleOption(value){if(!value||typeof value!=='object')return;for(const [key,item] of Object.entries(value)){if(scaleFields.has(key)&&typeof item==='number')value[key]=item*g;else if(item&&typeof item==='object')scaleOption(item);}}
 scaleOption(option);
 return option;
}

export function animatedOptions(req){
 const b=req.block,option=chartOptions(req),cats=b.categories||[],series=b.series||[];
 option.animation=true;option.animationDuration=b.animation_ms||1000;option.animationDurationUpdate=b.animation_ms||1000;
 option.animationEasing='cubicOut';option.animationEasingUpdate='cubicInOut';
 const category=j=>cats[j]??String(j);
 const occurrence=(items,j)=>items.slice(0,j).filter(v=>v===items[j]).length;
 for(let i=0;i<option.series.length;i++){
  const item=option.series[i],source=series.find(s=>s.name===item.name)||series[Math.min(i,series.length-1)];
  item.id=(item.name||b.chart)+':'+i;
  item.data=(item.data||[]).map((point,j)=>{
   const value=point&&typeof point==='object'&&!Array.isArray(point)?point.value:point;
   let identity;
   if(b.chart==='heatmap')identity=`${series[value[0]].name}:${category(value[1])}`;
   else if(b.chart==='waterfall')identity=category(value[0]);
   else if(['dot','dumbbell'].includes(b.chart))identity=category(value[value.length-1]);
   else if(['pie','donut','funnel'].includes(b.chart))identity=point.name;
   else if(source?.x_values)identity=String(source.x_values[j]);
   else identity=category(j)+':'+occurrence(cats,j);
   return {...(point&&typeof point==='object'&&!Array.isArray(point)?point:{value}),id:identity,name:point?.name||identity};
  });
  item.animationDelay=b.animation==='series'?i*250:b.animation==='points'?j=>j*80:0;
  item.animationDelayUpdate=item.animationDelay;
  item.universalTransition=item.type!=='custom';
  if(item.renderItem){
   const render=item.renderItem;
   item.renderItem=(params,api)=>{
    const result=render(params,api);
    function motion(node,path='root'){
     if(!node)return node;node.name=path;
     if(node.children){node.children.forEach((child,k)=>motion(child,path+':'+k));return node;}
     if(node.shape){node.transition=['shape'];node.enterFrom={shape:{...node.shape}};
      if(node.type==='rect')node.enterFrom.shape.height=0;
      if(node.type==='circle')node.enterFrom.shape.r=0;
      if(node.type==='line'){node.enterFrom.shape.x2=node.shape.x1;node.enterFrom.shape.y2=node.shape.y1;}
     }
     if(node.type==='polygon'||node.type==='text'){node.transition=['style'];node.enterFrom={style:{opacity:0}};}
     return node;
    }
    return motion(result);
   };
  }
 }
 return option;
}
