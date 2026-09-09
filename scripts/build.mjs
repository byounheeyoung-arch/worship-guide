import {cp,mkdir,rm} from 'node:fs/promises';
import {createRequire} from 'node:module';
import path from 'node:path';
const require=createRequire(import.meta.url);
const root=p=>path.dirname(require.resolve(p+'/package.json'));
await rm('dist',{recursive:true,force:true}); await mkdir('dist/vendor',{recursive:true});
await cp('web','dist',{recursive:true});
for(const [pkg,src,dest] of [['pdf-lib','dist/pdf-lib.min.js','pdf-lib.js'],['pdfjs-dist','build','pdfjs'],['pdfjs-dist','cmaps','cmaps'],['pdfjs-dist','standard_fonts','standard_fonts'],['pdfjs-dist','wasm','wasm'],['tesseract.js','dist','tesseract'],['tesseract.js-core','','tesseract-core']]) await cp(path.join(root(pkg),src),'dist/vendor/'+dest,{recursive:true});
console.log('Built dist: local PDF, OCR runtime, and application assets.');
