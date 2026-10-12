import * as echarts from 'echarts';
import {chartOptions} from './chart-options.mjs';
import ELK from 'elkjs/lib/elk.bundled.js';
let raw='';for await(const part of process.stdin)raw+=part;
const req=JSON.parse(raw);
if(req.kind==='diagram'){
 const graph={id:'root',layoutOptions:{'elk.algorithm':'layered','elk.direction':req.block.direction==='down'?'DOWN':'RIGHT',
 'elk.spacing.nodeNode':'36','elk.layered.spacing.nodeNodeBetweenLayers':'54','elk.edgeRouting':'ORTHOGONAL'},
 children:req.block.nodes.map(n=>({id:n.id,width:230,height:n.detail?132:86})),
 edges:req.block.edges.map((e,i)=>({id:`e${i}`,sources:[e.source],targets:[e.target],
  labels:e.label?[{text:e.label,width:Math.min(340,e.label.length*10+20),height:28}]:[]}))};
 process.stdout.write(JSON.stringify(await new ELK().layout(graph)));
}else{
 const option=chartOptions(req),w=req.width,h=req.height;
 const chart=echarts.init(null,null,{renderer:'svg',ssr:true,width:w,height:h});
 chart.setOption(option);process.stdout.write(chart.renderToSVGString());chart.dispose();
}
