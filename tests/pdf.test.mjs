import test from 'node:test';import assert from 'node:assert/strict';
import * as PDFLib from 'pdf-lib';import {exportPDF} from '../web/export-pdf.js';
globalThis.PDFLib=PDFLib;
test('PDF output preserves requested page order and multi-page ranges',async()=>{const src=await PDFLib.PDFDocument.create();src.addPage([200,300]);src.addPage([400,500]);src.addPage([600,700]);const blob=new Blob([await src.save()]);const result=await exportPDF([{documentId:'d',startPage:3,endPage:3},{documentId:'d',startPage:1,endPage:2}],async()=>blob);const parsed=await PDFLib.PDFDocument.load(await result.arrayBuffer());assert.deepEqual(parsed.getPages().map(p=>p.getWidth()),[600,200,400]);});
test('PDF output fails rather than silently dropping missing originals',async()=>{await assert.rejects(()=>exportPDF([{startPage:1,endPage:1}],async()=>null),/원본/);await assert.rejects(()=>exportPDF([],async()=>null),/추가/);});
