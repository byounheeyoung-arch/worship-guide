import {empty,id,keys,findScores,mergeBackup,approve,moveItem,validate} from './model.js';
import * as store from './storage.js';
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state,tab='library',filters={},collectionId=null,editId=null,previewURL=null,busy=false,pdfModule;
const pdf=()=>pdfModule??=import('./pdf.js');
const notify=(text,error=false)=>{$('#notice').textContent=text;$('#notice').className=error?'error':'';};
const run=fn=>async(...args)=>{try{await fn(...args);}catch(e){console.error(e);notify(e.message||'작업을 완료하지 못했습니다.',true);}};
const input=(label,name,value='',type='text',wide=false)=>`<label class="${wide?'wide':''}">${label}<input type="${type}" name="${name}" value="${esc(value)}"></label>`;
const select=(label,name,options,value='')=>`<label>${label}<select name="${name}"><option value="">전체</option>${options.map(v=>`<option value="${esc(v)}" ${v===value?'selected':''}>${esc(v)}</option>`).join('')}</select></label>`;
function download(blob,name){const u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),30000);}
async function commit(next,files=[]){await store.save(next,files);state=next;}
function navigate(next){if(busy){notify('현재 작업이 끝난 뒤 이동해 주세요.');return;}tab=next;render();}
function render(){
 const titles={library:'악보 보관함',import:'PDF 가져오기',review:'검수 대기',collections:'나의 악보집',settings:'백업 · 자료 이전'};
 $('#heading').textContent=titles[tab];document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.tab===tab));
 $('#pending').textContent=state.scores.filter(x=>x.status!=='reviewed'&&!x.archived).length;
 if(tab==='library'||tab==='review')renderLibrary();else if(tab==='import')renderImport();else if(tab==='collections')renderCollections();else renderSettings();
}
function renderLibrary(){
 const pending=state.scores.filter(x=>x.status!=='reviewed'&&!x.archived).length;
 $('#content').innerHTML=`<div class="stats"><div class="stat"><span>등록된 곡</span><strong>${state.songs.length}</strong></div><div class="stat"><span>Key별 악보</span><strong>${state.scores.length}</strong></div><div class="stat"><span>검수 대기</span><strong>${pending}</strong></div></div><form id="search" class="panel"><div class="filters">${input('제목 · 가사 · 작사/작곡 · 성경구절','query',filters.query||'')}${select('Key','key',keys,filters.key)}${select('검수 상태','review',['unreviewed','reviewed'],filters.review)}${input('주제 (쉼표로 여러 개)','themes',filters.themes||'')}</div><details><summary>상세 조건 · 분류, 분위기, 흐름, BPM</summary><div class="filters">${['category','mood','flow','bible'].map((k,i)=>input(['분류','분위기','예배 흐름','성경구절'][i],k,filters[k]||'')).join('')}${input('최소 BPM','bpmMin',filters.bpmMin||'','number')}${input('최대 BPM','bpmMax',filters.bpmMax||'','number')}${select('최대 난이도','difficulty',['1','2','3','4','5'],filters.difficulty)}<label><input name="favorite" type="checkbox" ${filters.favorite?'checked':''}> 즐겨찾기만</label></div><p class="muted">서로 다른 조건은 모두 충족하는 악보를 찾습니다. 쉼표로 나눈 값은 하나만 맞아도 포함합니다.</p></details><div class="row"><button class="primary">검색</button><button type="button" id="reset-search">초기화</button></div></form><div id="results"></div>`;
 $('#search').onsubmit=e=>{e.preventDefault();filters=Object.fromEntries(new FormData(e.target));renderResults();};$('#reset-search').onclick=()=>{filters={};renderLibrary();};renderResults();
}
function renderResults(){
 const f={...filters};let rows=findScores(state,f);if(tab==='review')rows=rows.filter(x=>x.score.status!=='reviewed');
 $('#results').innerHTML=`<div class="row between" style="margin-top:25px"><h2>${tab==='review'?'확인이 필요한 악보':'보관한 악보'} <span class="muted">${rows.length}개</span></h2><button id="manual">＋ 직접 등록</button></div>`+(rows.length?`<div class="table-wrap"><table><thead><tr><th>곡명 / 편곡</th><th>Key</th><th>주제 / BPM</th><th>상태</th><th>작업</th></tr></thead><tbody>${rows.map(({song,arrangement,score})=>`<tr><td><strong>${esc(song.title)}</strong><small>${esc(arrangement.name)} · ${score.startPage}–${score.endPage}p</small></td><td class="key">${esc(score.key||'미확인')}</td><td>${esc(song.themes||'—')}<br><small>${song.bpm?esc(song.bpm)+' BPM':'BPM 미입력'}</small></td><td><span class="badge ${score.status!=='reviewed'?'pending':''}">${score.status==='reviewed'?'검수 완료':'검수 대기'}</span></td><td><div class="row"><button data-edit="${esc(score.id)}">열기</button><button data-star="${esc(song.id)}" aria-label="즐겨찾기 ${song.favorite?'해제':'추가'}">${song.favorite?'★':'☆'}</button><button data-add="${esc(score.id)}">악보집 ＋</button></div></td></tr>`).join('')}</tbody></table></div>`:`<div class="panel empty"><h2>${state.scores.length?'조건에 맞는 악보가 없습니다':'첫 악보를 보관해 보세요'}</h2><p>${state.scores.length?'검색 조건을 줄여 다시 찾아보세요.':'PDF를 가져오면 페이지별 제목과 Key를 확인하고 악보집으로 모을 수 있어요.'}</p><button class="primary" id="empty-import">PDF 가져오기</button></div>`);
 $('#manual').onclick=run(async()=>{const next=structuredClone(state),song={id:id(),title:'새 곡'},arr={id:id(),songId:song.id,name:'Original'},score={id:id(),arrangementId:arr.id,key:'',startPage:1,endPage:1,status:'unreviewed'};next.songs.push(song);next.arrangements.push(arr);next.scores.push(score);await commit(next);render();await openEditor(score.id);});
 $('#empty-import')?.addEventListener('click',()=>navigate('import'));
 document.querySelectorAll('[data-edit]').forEach(b=>b.onclick=run(()=>openEditor(b.dataset.edit)));
 document.querySelectorAll('[data-star]').forEach(b=>b.onclick=run(async()=>{const n=structuredClone(state),s=n.songs.find(x=>x.id===b.dataset.star);s.favorite=!s.favorite;await commit(n);renderResults();}));
 document.querySelectorAll('[data-add]').forEach(b=>b.onclick=run(()=>addToCollection(b.dataset.add)));
}
async function addToCollection(scoreId){
 const n=structuredClone(state);let c=n.collections.find(x=>x.id===collectionId);
 if(!c&&n.collections.length===1)c=n.collections[0];
 if(!c){const name=prompt('추가할 악보집 이름을 입력하세요. 기존 이름이면 해당 악보집에 추가합니다.','주일 예배');if(!name?.trim())return;c=n.collections.find(x=>x.name===name.trim());if(!c){c={id:id(),name:name.trim(),scoreIds:[]};n.collections.push(c);}}
 if(!c.scoreIds.includes(scoreId))c.scoreIds.push(scoreId);await commit(n);collectionId=c.id;notify(`「${c.name}」에 추가했습니다.`);
}
function renderImport(){
 $('#content').innerHTML=`<div class="panel"><h2>PDF에서 악보 가져오기</h2><p class="muted">한 페이지씩 초안을 만듭니다. 여러 페이지인 곡은 검수에서 끝 페이지를 조정해 주세요.</p><form id="import-form"><div class="drop"><h2>악보 PDF를 선택하세요</h2><p>원본 파일은 이 브라우저에 보관됩니다.</p><input type="file" id="pdf-file" accept="application/pdf,.pdf" required></div><div class="filters">${input('시작 페이지','start','1','number')}${input('끝 페이지 (비우면 마지막)','end','','number')}<label><input type="checkbox" name="ocr" checked> 이미지 PDF 한글·영문 OCR</label></div><p class="warning">OCR 제목과 Key는 초안입니다. 특히 오선의 조표는 자동 판독을 보장하지 않으므로 원본과 비교해 확인해 주세요. OCR 언어 파일은 최초 실행 때 인터넷으로 받습니다.</p><button class="primary">분석 시작</button></form><div id="import-progress"></div></div>`;
 $('#import-form').onsubmit=run(async e=>{
 e.preventDefault();const form=e.target,blob=$('#pdf-file').files[0],data=new FormData(form);if(!blob)return;
 busy=true;form.querySelector('button').disabled=true;let doc;
 try{
  const api=await pdf();doc=await api.loadPDF(blob);const start=Number(data.get('start')),end=data.get('end')?Number(data.get('end')):doc.numPages;
  if(!Number.isInteger(start)||!Number.isInteger(end)||start<1||end<start||end>doc.numPages)throw Error(`1~${doc.numPages} 사이의 페이지를 입력하세요.`);
  const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await blob.arrayBuffer()))).map(x=>x.toString(16).padStart(2,'0')).join('');
  let document=state.documents.find(x=>x.sha256===digest),n=structuredClone(state);
  if(!document){document={id:id(),name:blob.name,sha256:digest,pageCount:doc.numPages};n.documents.push(document);await commit(n,[[document.id,blob]]);}
  let added=0,skipped=0,ocrFailures=0;
  for(let page=start;page<=end;page++){
   if(state.scores.some(x=>x.documentId===document.id&&x.startPage<=page&&x.endPage>=page)){skipped++;continue;}
   const progress=(msg,pct)=>{$('#import-progress').textContent=`${page}/${end}페이지 · ${msg} ${Math.round((pct||0)*100)}%`;};progress('분석 중',0);
   let result;try{result=await api.analyze(doc,page,data.has('ocr'),progress);}catch(error){ocrFailures++;result={title:'',raw:'OCR 실패: '+error.message,key:'',confidence:null,method:'OCR 실패 · 수동 검수 필요'};}
   const song={id:id(),title:result.title||`${blob.name.replace(/\.pdf$/i,'')} · ${page}페이지`},arr={id:id(),songId:song.id,name:'Original'};
   const score={id:id(),arrangementId:arr.id,documentId:document.id,startPage:page,endPage:page,key:keys.includes(result.key)?result.key:'',status:'unreviewed',rawOcr:result.raw,ocrConfidence:result.confidence,ocrMethod:result.method};
   n=structuredClone(state);n.songs.push(song);n.arrangements.push(arr);n.scores.push(score);await commit(n);added++;
  }
  notify(`${added}개 악보 초안 저장 · 중복 ${skipped}페이지 건너뜀${ocrFailures?` · OCR 실패 ${ocrFailures}개는 원본을 보며 수동 검수해 주세요.`:''}`);tab='review';
 }finally{await doc?.destroy();busy=false;render();}
 });
}
async function openEditor(scoreId){
 editId=scoreId;const score=state.scores.find(x=>x.id===scoreId),arr=state.arrangements.find(x=>x.id===score.arrangementId),song=state.songs.find(x=>x.id===arr.songId);
 const fields=[['제목','title'],['원제','originalTitle'],['작곡','composer'],['작사','lyricist'],['분류','category'],['주제','themes'],['분위기','mood'],['예배 흐름','flow'],['성경구절','bible']];
 $('#fields').innerHTML=`<label>기존 곡에 연결 (동일 곡의 다른 Key)<select name="songId">${state.songs.map(s=>`<option value="${esc(s.id)}" ${s.id===song.id?'selected':''}>${esc(s.title)}</option>`).join('')}</select></label><div class="form-grid">${fields.map(([l,k])=>input(l,k,song[k]||'')).join('')}${input('BPM','bpm',song.bpm??'','number')}${input('난이도 1–5','difficulty',song.difficulty??'','number')}${input('편곡 이름','arrangement',arr.name)}<label>Key<select name="key"><option value="">미확인</option>${keys.map(k=>`<option ${k===score.key?'selected':''}>${k}</option>`).join('')}</select></label>${input('시작 페이지','startPage',score.startPage,'number')}${input('끝 페이지','endPage',score.endPage,'number')}<label class="wide">가사<textarea name="lyrics">${esc(song.lyrics||'')}</textarea></label><label class="wide">메모<textarea name="notes">${esc(song.notes||'')}</textarea></label><label class="wide">원본 PDF 연결 · 교체<input name="attachment" type="file" accept="application/pdf,.pdf"></label></div>`;
 $('#fields [name=songId]').onchange=e=>{const target=state.songs.find(x=>x.id===e.target.value);for(const k of ['title','originalTitle','composer','lyricist','category','themes','mood','flow','bible','bpm','difficulty','lyrics','notes'])$('#fields [name='+k+']').value=target[k]??'';};
 if(previewURL)URL.revokeObjectURL(previewURL);const b=score.documentId?await store.file(score.documentId):null;
 $('#preview').removeAttribute('src');$('#preview').srcdoc=b?'':'<p>연결된 원본 PDF가 없습니다. 오른쪽에서 원본을 연결해 주세요.</p>';
 if(b){$('#preview').removeAttribute('srcdoc');previewURL=URL.createObjectURL(b);$('#preview').src=previewURL+'#page='+score.startPage;}
 $('#ocr-info').textContent=`${score.ocrMethod||'직접 등록'} · ${score.ocrConfidence==null?'신뢰도 없음':'OCR 신뢰도 '+Math.round(score.ocrConfidence)+'%'} · Key는 원본과 비교해 주세요.`;
 $('#ocr-text').textContent=score.rawOcr||'OCR 원문이 없습니다.';if(!$('#editor').open)$('#editor').showModal();
}
$('#edit-form').onsubmit=run(async e=>{
 e.preventDefault();const button=e.target.querySelector('[type=submit]');button.disabled=true;
 try{
  const n=structuredClone(state),data=Object.fromEntries(new FormData(e.target)),files=[];
  if(data.difficulty&&(Number(data.difficulty)<1||Number(data.difficulty)>5))throw Error('난이도는 1~5로 입력하세요.');
  if(data.attachment?.size){const api=await pdf(),d=await api.loadPDF(data.attachment);try{const meta={id:id(),name:data.attachment.name,pageCount:d.numPages};n.documents.push(meta);n.scores.find(x=>x.id===editId).documentId=meta.id;files.push([meta.id,data.attachment]);}finally{await d.destroy();}}
  approve(n,editId,data);await commit(n,files);$('#editor').close();render();notify('검수 내용을 저장했습니다.');
 }finally{button.disabled=false;}
});
$('#archive-score').onclick=run(async()=>{if(!confirm('목차·빈 페이지 또는 중복 초안을 보관함에서 제외할까요? 원본과 백업에는 유지됩니다.'))return;const n=structuredClone(state);n.scores.find(x=>x.id===editId).archived=true;await commit(n);$('#editor').close();render();notify('보관함에서 제외했습니다. 원본과 백업에는 남아 있습니다.');});
$('#close-editor').onclick=()=>$('#editor').close();$('#next-review').onclick=run(async()=>{const list=state.scores.filter(s=>s.status!=='reviewed'&&!s.archived),i=list.findIndex(s=>s.id===editId);const next=list[(i+1)%list.length];if(next)await openEditor(next.id);else notify('모든 악보를 검수했습니다.');});
function renderCollections(){
 let c=state.collections.find(x=>x.id===collectionId)||state.collections[0];collectionId=c?.id;
 $('#content').innerHTML=`<div class="split"><div><form id="new-collection" class="panel"><h2>새 악보집</h2><label>악보집 이름<input name="name" required placeholder="예: 9월 주일 예배"></label><button class="primary">만들기</button></form><div class="collection-list" style="margin-top:18px">${state.collections.map(x=>`<button data-collection="${esc(x.id)}" class="${x.id===collectionId?'selected':''}">${esc(x.name)} <small>· ${x.scoreIds.length}곡</small></button>`).join('')}</div></div><div class="panel">${c?`<div class="row between"><h2>${esc(c.name)}</h2><div class="row"><button id="rename-collection">이름 변경</button><button id="export-pdf" class="primary">PDF 출력</button></div></div><p class="muted">순서대로 원본 악보를 합칩니다. 선택한 Key와 페이지 범위가 그대로 출력됩니다.</p><button id="add-library">보관함에서 악보 추가</button><div>${c.scoreIds.map((sid,i)=>{const score=state.scores.find(x=>x.id===sid),arr=state.arrangements.find(x=>x.id===score.arrangementId),song=state.songs.find(x=>x.id===arr.songId);return `<div class="item"><span class="muted">${String(i+1).padStart(2,'0')}</span><div class="grow"><strong>${esc(song.title)}</strong><div class="muted">${esc(score.key||'Key 미확인')} · ${esc(arr.name)} · ${score.startPage}–${score.endPage}p</div></div><button data-up="${i}" aria-label="위로 이동">↑</button><button data-down="${i}" aria-label="아래로 이동">↓</button><button data-remove="${i}" aria-label="악보집에서 제외">✕</button></div>`;}).join('')||'<div class="empty">보관함에서 원하는 Key 악보를 추가하세요.</div>'}</div>`:'<div class="empty"><h2>예배에 맞는 악보집을 만들어 보세요</h2><p>곡과 Key를 선택하고 순서를 정하면 하나의 PDF로 출력할 수 있어요.</p></div>'}</div></div>`;
 $('#new-collection').onsubmit=run(async e=>{e.preventDefault();const name=new FormData(e.target).get('name').trim();if(!name)return;const n=structuredClone(state),c={id:id(),name,scoreIds:[]};n.collections.push(c);await commit(n);collectionId=c.id;render();});
 document.querySelectorAll('[data-collection]').forEach(b=>b.onclick=()=>{collectionId=b.dataset.collection;renderCollections();});
 $('#add-library')?.addEventListener('click',()=>navigate('library'));
 $('#rename-collection')?.addEventListener('click',run(async()=>{const name=prompt('악보집 이름',c.name);if(!name?.trim())return;const n=structuredClone(state);n.collections.find(x=>x.id===c.id).name=name.trim();await commit(n);render();}));
 for(const action of ['up','down','remove'])document.querySelectorAll('[data-'+action+']').forEach(b=>b.onclick=run(async()=>{const n=structuredClone(state),target=n.collections.find(x=>x.id===c.id),i=Number(b.dataset[action]);if(action==='remove')target.scoreIds.splice(i,1);else moveItem(target,i,action==='up'?-1:1);await commit(n);render();}));
 $('#export-pdf')?.addEventListener('click',run(async()=>{const b=$('#export-pdf');b.disabled=true;try{const api=await pdf();const blob=await api.exportPDF(c.scoreIds.map(k=>state.scores.find(x=>x.id===k)),store.file,(i,total)=>notify(`악보집 출력 중 ${i}/${total}`));download(blob,c.name+'.pdf');notify('악보집 PDF를 만들었습니다.');}finally{b.disabled=false;}}));
}
function renderSettings(){
 $('#content').innerHTML=`<div class="panel"><h2>전체 자료 백업</h2><p>곡 정보, 검수 기록, 악보집과 원본 PDF를 하나의 파일로 저장합니다.</p><div class="row"><button class="primary" id="backup">전체 백업 다운로드</button><button id="persist">브라우저 영구 저장 요청</button><button id="csv">메타데이터 CSV</button></div><p class="warning">이 브라우저의 같은 주소에서 자료가 유지됩니다. 브라우저 데이터 삭제·다른 PC·다른 배포 주소로 이동할 때는 백업 파일을 복원하세요. 중요한 작업 후 백업을 권장합니다.</p></div><div class="panel" style="margin-top:22px"><h2>백업 복원 · 기존 버전 자료 가져오기</h2><p>현재 자료에 합칩니다. 같은 ID의 내용이 달라지면 별도 항목으로 보존합니다.</p><input type="file" id="restore-file" accept=".json,application/json"><button id="restore" style="margin-top:12px">선택한 파일 합치기</button><details><summary>v2.0.2 SQLite에서 이전하기</summary><p>프로젝트의 <code>scripts/migrate_legacy.py</code>로 기존 DB를 백업 형식으로 변환한 뒤 위에서 가져오세요. DB 원본은 읽기 전용으로 열며 변경하지 않습니다.</p><code>python scripts/migrate_legacy.py 기존자료.db 이전백업.json</code><p class="muted">PDF 경로가 바뀌었다면 변환 시 --asset-root 옵션을 사용하거나, 가져온 뒤 검수 화면에서 원본을 연결하세요.</p></details></div>`;
 $('#backup').onclick=run(async()=>{notify('원본 PDF를 포함한 백업 생성 중…');download(new Blob([JSON.stringify(await store.pack(state))],{type:'application/json'}),'worship-guide-backup-'+new Date().toISOString().slice(0,10)+'.json');notify('전체 백업을 만들었습니다.');});
 $('#persist').onclick=run(async()=>notify(await store.persist()?'브라우저 영구 저장이 허용됐습니다.':'브라우저가 영구 저장을 허용하지 않았습니다. 전체 백업을 보관해 주세요.'));
 $('#restore').onclick=run(async()=>{
  const b=$('#restore-file').files[0];if(!b)throw Error('백업 파일을 선택하세요.');const data=JSON.parse(await b.text());if(data.format!=='worship-guide-backup')throw Error('Worship Guide 백업 파일이 아닙니다.');validate(data.state);
  // Remap conflicting document identities before merge so asset bytes cannot overwrite existing files.
  const incoming=structuredClone(data.state),assets=data.assets||{},files=[];if(data.legacyTables)incoming.legacyImports=[...(incoming.legacyImports||[]),data.legacyTables];
  for(const d of incoming.documents){
   const old=d.id,encoded=assets[old];
   if(encoded&&!/^data:application\/pdf;base64,/.test(encoded))throw Error('백업 PDF 형식이 올바르지 않습니다.');
   const blob=encoded?await (await fetch(encoded)).blob():null;
   if(state.documents.some(x=>x.id===old)){
    const existing=await store.file(old);let same=!blob;
    if(existing&&blob){const a=new Uint8Array(await existing.arrayBuffer()),b=new Uint8Array(await blob.arrayBuffer());same=a.length===b.length&&a.every((v,i)=>v===b[i]);}
    if(!same||JSON.stringify(state.documents.find(x=>x.id===old))!==JSON.stringify(d)){d.id=id();for(const score of incoming.scores)if(score.documentId===old)score.documentId=d.id;}
   }
   if(blob)files.push([d.id,blob]);
  }
  const n=mergeBackup(state,incoming);await commit(n,files);render();notify('기존 자료를 보존하며 백업을 합쳤습니다.');
 });
 $('#csv').onclick=()=>{const rows=[['곡 ID','제목','편곡','Key','주제','성경구절','BPM','상태'],...findScores(state).map(({song,arrangement,score})=>[song.id,song.title,arrangement.name,score.key,song.themes,song.bible,song.bpm,score.status])];const cell=v=>'"'+String(v??'').replace(/^[=+@-]/,"'$&").replace(/"/g,'""')+'"';download(new Blob(['\ufeff'+rows.map(r=>r.map(cell).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'}),'worship-guide-metadata.csv');};
}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>navigate(b.dataset.tab));$('#top-import').onclick=()=>navigate('import');
try{state=await store.open();validate(state);render();}catch(e){notify('자료를 열지 못했습니다. '+e.message,true);$('#content').innerHTML='<div class="panel">브라우저 저장소를 사용할 수 있는 일반 창에서 다시 열어 주세요. 기존 데이터는 자동으로 초기화하지 않습니다.</div>';}
