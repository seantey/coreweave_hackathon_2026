import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import fs from 'node:fs/promises';
const browser=await chromium.launch({channel:'chrome',headless:true,args:['--use-angle=metal']});
try {
 const page=await browser.newPage({viewport:{width:1600,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8000/?workspace=1&scene=office-rebuild');
 await page.waitForFunction(()=>window.cleanroom?.ready,{}, {timeout:90000});
 await page.waitForTimeout(1500);
 const after=await page.evaluate(()=>window.cleanroom.metadata());
 assert.equal(after.scene_id,'office-rebuild');
 for (const id of ['grounded-folding-table','folding-chair-left','folding-chair-right']) assert.ok(after.objects.some(o=>o.id===id));
 assert.ok(!after.objects.some(o=>o.id==='layer-0-object-00'));
 await page.click('#original');
 const original=await page.evaluate(()=>window.cleanroom.metadata());
 assert.equal(original.revision_id,'original');
 assert.ok(original.objects.some(o=>o.id==='layer-0-object-00'));
 assert.ok(!original.objects.some(o=>o.id==='grounded-folding-table'));
 await page.click('#current');
 assert.equal((await page.evaluate(()=>window.cleanroom.metadata())).revision_id,after.revision_id);
 await page.locator('[data-camera="Table side"]').click();
 await page.waitForTimeout(1500);
 await page.screenshot({path:'.artifacts/office-direct-repair-workspace.png'});
 assert.deepEqual(errors,[]);
 await fs.writeFile('.artifacts/office-direct-browser-check.json',JSON.stringify({scene:after.scene_id,revision:after.revision_id,originalToggle:true,acceptedToggle:true,errors},null,2));
 console.log('Production office viewer: repaired table and two chairs visible; original/accepted toggles preserve revisions; no page errors');
} finally {await browser.close();}
