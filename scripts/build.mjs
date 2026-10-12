import { build as buildClient } from 'vite';
import { build as bundle } from 'esbuild';
import {mkdir,copyFile,writeFile,readFile} from 'node:fs/promises';

await buildClient();
const html='cicero_hoard/static/index.html';
await writeFile(html,(await readFile(html,'utf8')).replace(/\r\n?/g,'\n'));
const root='cicero_hoard/static/visual-runtime';
await mkdir(root,{recursive:true});
await bundle({entryPoints:['scripts/advanced-runtime.mjs'],outfile:root+'/advanced.js',bundle:true,platform:'browser',format:'iife',target:'es2022',minify:true,
  define:{'import.meta.url':'"https://cicero.invalid/embedded/advanced.js"'}});
await mkdir(root+'/decoders',{recursive:true});
for(const [folder,names] of [['draco/gltf',['draco_decoder.js','draco_wasm_wrapper.js','draco_decoder.wasm']],['basis',['basis_transcoder.js','basis_transcoder.wasm']]]){
  for(const name of names)await copyFile('node_modules/three/examples/jsm/libs/'+folder+'/'+name,root+'/decoders/'+name);
}
await bundle({entryPoints:['scripts/collaboration-engine.mjs'],outfile:root+'/collaboration.mjs',bundle:true,platform:'node',format:'esm',target:'node22',minify:true});
await bundle({entryPoints:['scripts/visual-engine.mjs'],outfile:root+'/engine.mjs',bundle:true,platform:'node',
  format:'esm',target:'node22',minify:true,banner:{js:'import {createRequire} from "node:module";const require=createRequire(import.meta.url);'}});
for(const name of ['reveal.js','reveal.css'])await copyFile('node_modules/reveal.js/dist/'+name,root+'/'+name);
const licenses=[];
for(const [name,file] of [['echarts','LICENSE'],['elkjs','LICENSE.md'],['reveal.js','LICENSE'],['three','LICENSE'],['yjs','LICENSE'],['y-protocols','LICENSE']]){
  licenses.push(name+'\n'+await readFile('node_modules/'+name+'/'+file,'utf8'));
}
for(const name of ['DRACO-LICENSE.txt','BASIS-LICENSE.txt','MESHOPT-LICENSE.txt']){
  const source='scripts/licenses/'+name;licenses.push(name+'\n'+await readFile(source,'utf8'));await copyFile(source,root+'/'+name);
}
await writeFile(root+'/LICENSES.txt',licenses.join('\n\n'));
console.log('Packaged chart, diagram and presentation runtimes.');
