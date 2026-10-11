import { build as buildClient } from 'vite';
import { build as bundle } from 'esbuild';
import {mkdir,copyFile,writeFile,readFile} from 'node:fs/promises';

await buildClient();
const html='cicero_hoard/static/index.html';
await writeFile(html,(await readFile(html,'utf8')).replace(/\r\n?/g,'\n'));
const root='cicero_hoard/static/visual-runtime';
await mkdir(root,{recursive:true});
await bundle({entryPoints:['scripts/visual-engine.mjs'],outfile:root+'/engine.mjs',bundle:true,platform:'node',
  format:'esm',target:'node22',minify:true,banner:{js:'import {createRequire} from "node:module";const require=createRequire(import.meta.url);'}});
for(const name of ['reveal.js','reveal.css'])await copyFile('node_modules/reveal.js/dist/'+name,root+'/'+name);
const licenses=[];
for(const [name,file] of [['echarts','LICENSE'],['elkjs','LICENSE.md'],['reveal.js','LICENSE']]){
  licenses.push(name+'\n'+await readFile('node_modules/'+name+'/'+file,'utf8'));
}
await writeFile(root+'/LICENSES.txt',licenses.join('\n\n'));
console.log('Packaged chart, diagram and presentation runtimes.');
