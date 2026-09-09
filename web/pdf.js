export {exportPDF} from './export-pdf.js';
import * as pdfjs from './vendor/pdfjs/pdf.mjs';
pdfjs.GlobalWorkerOptions.workerSrc=new URL('./vendor/pdfjs/pdf.worker.mjs',import.meta.url).href;
const base=new URL('./vendor/',import.meta.url).href;
export async function loadPDF(blob){return pdfjs.getDocument({data:new Uint8Array(await blob.arrayBuffer()),cMapUrl:base+'cmaps/',cMapPacked:true,standardFontDataUrl:base+'standard_fonts/',wasmUrl:base+'wasm/'}).promise;}
export async function analyze(pdf,pageNumber,ocr,progress){
 const page=await pdf.getPage(pageNumber);const text=await page.getTextContent();
 let raw=text.items.map(x=>x.str+(x.hasEOL?'\n':' ')).join('').trim(),confidence=null,method='PDF 텍스트';
 if(raw.replace(/\s/g,'').length<8){
  if(!ocr)return {title:'',raw:'',key:'',confidence:null,method:'이미지 PDF · 수동 검수 필요'};
  const viewport=page.getViewport({scale:Math.min(2,2400/Math.max(page.view[2],page.view[3]))});
  const canvas=document.createElement('canvas');canvas.width=viewport.width;canvas.height=viewport.height;
  await page.render({canvasContext:canvas.getContext('2d'),viewport}).promise;
  const worker=await Tesseract.createWorker('kor+eng',1,{workerPath:base+'tesseract/worker.min.js',corePath:base+'tesseract-core',logger:m=>progress(m.status,m.progress)});
  try{const result=await worker.recognize(canvas);raw=result.data.text;confidence=result.data.confidence;method='한글·영문 OCR';}finally{await worker.terminate();canvas.width=canvas.height=0;}
 }
 page.cleanup();
 const lines=raw.split('\n').map(x=>x.trim()).filter(Boolean);
 const title=lines.find(x=>x.length>2&&!/^\d+$/.test(x))||'';
 const key=raw.match(/(?:Key|조성)\s*[:=]?\s*([A-G](?:#|b)?m?)(?=\s|$)/i)?.[1]||'';
 return {title:title.slice(0,150),raw,key,confidence,method};
}
