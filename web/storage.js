import {empty,validate} from './model.js';
const request=r=>new Promise((resolve,reject)=>{r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});
let db;
export async function open(){
 const r=indexedDB.open('worship-guide',1);r.onupgradeneeded=()=>{r.result.createObjectStore('state');r.result.createObjectStore('files');};
 db=await request(r);db.onversionchange=()=>db.close();return (await request(db.transaction('state').objectStore('state').get('main')))||empty();
}
export async function save(state,files=[]){
 validate(state);return new Promise((resolve,reject)=>{
 const tx=db.transaction(['state','files'],'readwrite');const store=tx.objectStore('state');
 const read=store.get('main');read.onsuccess=()=>{if((read.result?.revision||0)!==(state.revision||0)){tx.abort();return;}if(read.result)store.put(read.result,'previous');store.put({...state,revision:(state.revision||0)+1},'main');};
 for(const [key,blob] of files)tx.objectStore('files').put(blob,key);
 tx.oncomplete=()=>{state.revision=(state.revision||0)+1;resolve();};tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error||Error('다른 창에서 자료가 변경됐거나 저장이 취소됐습니다. 새로고침 후 다시 시도하세요.'));
 });
}
export async function file(id){return request(db.transaction('files').objectStore('files').get(id));}
export async function persist(){return navigator.storage?.persist?await navigator.storage.persist():false;}
export async function pack(state){
 const assets={};for(const d of state.documents){const b=await file(d.id);if(b)assets[d.id]=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=reject;r.readAsDataURL(b);});}
 return {format:'worship-guide-backup',state,assets,exportedAt:new Date().toISOString()};
}
