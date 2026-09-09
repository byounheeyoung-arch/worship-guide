export const SCHEMA=1;
export const id=()=>crypto.randomUUID();
export const empty=()=>({schemaVersion:SCHEMA,songs:[],arrangements:[],scores:[],documents:[],collections:[],reviews:[]});
export const normalize=s=>String(s||'').normalize('NFKC').trim().toLocaleLowerCase();
export const keys=['C','Db','D','Eb','E','F','Gb','G','Ab','A','Bb','B','Cm','C#m','Dm','Ebm','Em','Fm','F#m','Gm','G#m','Am','Bbm','Bm'];
export function validate(s){
 if(!s||s.schemaVersion!==SCHEMA)throw Error('지원하지 않는 백업 형식입니다.');
 for(const name of ['songs','arrangements','scores','documents','collections','reviews']){
  if(!Array.isArray(s[name]))throw Error(name+' 자료가 올바르지 않습니다.');
  const ids=new Set();for(const row of s[name]){if(!row.id||ids.has(row.id))throw Error(name+' ID가 중복되거나 없습니다.');ids.add(row.id);}
 }
 const has=(t,k)=>s[t].some(x=>x.id===k);
 for(const x of s.songs)if(!String(x.title||'').trim())throw Error('곡 제목이 없습니다.');
 for(const x of s.arrangements)if(!has('songs',x.songId))throw Error('편곡의 곡 연결이 없습니다.');
 for(const x of s.scores){
  if(!has('arrangements',x.arrangementId))throw Error('악보의 편곡 연결이 없습니다.');
  if(x.documentId&&!has('documents',x.documentId))throw Error('원본 PDF 연결이 없습니다.');
  if(!Number.isInteger(x.startPage)||!Number.isInteger(x.endPage)||x.startPage<1||x.endPage<x.startPage)throw Error('페이지 범위가 올바르지 않습니다.');
  const d=s.documents.find(d=>d.id===x.documentId);if(d?.pageCount&&x.endPage>d.pageCount)throw Error('원본의 페이지 수를 초과했습니다.');
 }
 for(const c of s.collections)if(!Array.isArray(c.scoreIds)||c.scoreIds.some(k=>!has('scores',k)))throw Error('악보집 연결이 올바르지 않습니다.');
 return s;
}
export function findScores(s,f={}){
 const terms=v=>String(v||'').split(',').map(normalize).filter(Boolean);
 const match=(v,q)=>!q||terms(q).some(t=>normalize(v).includes(t));
 return s.scores.filter(score=>!score.archived).map(score=>{const arrangement=s.arrangements.find(a=>a.id===score.arrangementId);const song=s.songs.find(x=>x.id===arrangement.songId);return {score,arrangement,song};}).filter(({score,song,arrangement})=>
 match([song.title,song.originalTitle,song.lyrics,song.composer,song.lyricist,song.bible,song.notes,arrangement.name].join(' '),f.query)&&
 ['category','themes','mood','flow','bible'].every(k=>match(song[k],f[k]))&&(!f.key||terms(f.key).includes(normalize(score.key)))&&
 (!f.review||score.status===f.review)&&(!f.favorite||song.favorite)&&
 (!f.bpmMin||(Number.isFinite(song.bpm)&&song.bpm>=Number(f.bpmMin)))&&(!f.bpmMax||(Number.isFinite(song.bpm)&&song.bpm<=Number(f.bpmMax)))&&
 (!f.difficulty||(song.difficulty!=null&&song.difficulty<=Number(f.difficulty)))
 ).sort((a,b)=>a.song.title.localeCompare(b.song.title,'ko'));
}
export function mergeBackup(current,incoming){
 validate(current);validate(incoming);const out=structuredClone(current);const maps={};
 // Same identity + same content is idempotent; conflicting identity preserves BOTH records.
 for(const table of ['documents','songs','arrangements','scores','collections','reviews']){
  maps[table]=new Map();
  for(const original of incoming[table]){
   const row=structuredClone(original);
   if(table==='arrangements')row.songId=maps.songs.get(row.songId);
   if(table==='scores'){row.arrangementId=maps.arrangements.get(row.arrangementId);if(row.documentId)row.documentId=maps.documents.get(row.documentId);}
   if(table==='collections')row.scoreIds=row.scoreIds.map(k=>maps.scores.get(k));
   if(table==='reviews'&&row.scoreId)row.scoreId=maps.scores.get(row.scoreId)||row.scoreId;
   const existing=out[table].find(x=>x.id===row.id);
   if(existing&&JSON.stringify(existing)!==JSON.stringify(row))row.id=id();
   maps[table].set(original.id,row.id);
   if(!out[table].some(x=>x.id===row.id))out[table].push(row);
  }
 }
 out.legacyImports=[...(current.legacyImports||[]),...(incoming.legacyImports||[])].filter((x,i,a)=>a.findIndex(y=>JSON.stringify(y)===JSON.stringify(x))===i);
 if(!out.legacyImports.length)delete out.legacyImports;
 return validate(out);
}
export function approve(s,scoreId,data){
 const score=s.scores.find(x=>x.id===scoreId);if(!score)throw Error('악보를 찾을 수 없습니다.');
 if(!String(data.title||'').trim())throw Error('제목을 입력해 주세요.');
 if(data.key&&!keys.includes(data.key))throw Error('Key를 확인해 주세요.');
 const previous=structuredClone(score);const oldArr=s.arrangements.find(x=>x.id===score.arrangementId);
 let song=data.songId?s.songs.find(x=>x.id===data.songId):s.songs.find(x=>x.id===oldArr.songId);
 if(!song)throw Error('연결할 곡이 없습니다.');
 for(const k of ['title','originalTitle','lyrics','composer','lyricist','category','themes','mood','flow','bible','notes'])if(k in data)song[k]=String(data[k]).trim();
 for(const k of ['bpm','difficulty'])if(k in data){const v=data[k];song[k]=v===''||v==null?null:Number(v);if(song[k]!=null&&(!Number.isFinite(song[k])||song[k]<0))throw Error('숫자 입력을 확인해 주세요.');}
 let arr=s.arrangements.find(x=>x.songId===song.id&&x.name===(data.arrangement||'Original'));
 if(!arr){arr={id:id(),songId:song.id,name:data.arrangement||'Original'};s.arrangements.push(arr);}
 Object.assign(score,{arrangementId:arr.id,key:data.key||'',startPage:Number(data.startPage),endPage:Number(data.endPage),status:'reviewed'});
 s.reviews.push({id:id(),scoreId,at:new Date().toISOString(),previous,next:structuredClone(score),song:structuredClone(song)});validate(s);return s;
}
export function moveItem(c,index,delta){const to=index+delta;if(to<0||to>=c.scoreIds.length)return;c.scoreIds.splice(to,0,c.scoreIds.splice(index,1)[0]);}
