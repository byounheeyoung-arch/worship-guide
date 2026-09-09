export async function exportPDF(scores,getFile,onProgress){
 if(!scores.length)throw Error('악보집에 악보를 추가해 주세요.');
 const out=await PDFLib.PDFDocument.create();
 for(let i=0;i<scores.length;i++){
  const score=scores[i];const blob=await getFile(score.documentId);if(!blob)throw Error('원본이 없는 악보가 있습니다. 해당 곡의 원본 PDF를 연결해 주세요.');
  const src=await PDFLib.PDFDocument.load(await blob.arrayBuffer());
  if(score.startPage<1||score.endPage>src.getPageCount())throw Error('출력 페이지 범위를 확인해 주세요.');
  const pages=await out.copyPages(src,Array.from({length:score.endPage-score.startPage+1},(_,n)=>n+score.startPage-1));pages.forEach(p=>out.addPage(p));onProgress?.(i+1,scores.length);
 }
 out.setProducer('Worship Guide 3.0');return new Blob([await out.save()],{type:'application/pdf'});
}
