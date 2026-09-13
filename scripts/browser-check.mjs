import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
await fs.mkdir('.artifacts',{recursive:true});
const browser=await chromium.launch({channel:'chrome',headless:true,args:['--use-angle=metal']});
const errors=[];
try {
 const page=await browser.newPage({viewport:{width:1500,height:1000}});
 page.on('pageerror',error=>errors.push(error.message));
 await page.goto(process.env.VIEWER_URL??'http://127.0.0.1:5173/?workspace=1&scene=chair-probe');
 await page.waitForFunction(()=>window.cleanroom?.ready,{timeout:90000});
 await page.waitForTimeout(1500);
 const before=await page.evaluate(()=>window.cleanroom.metadata());
 assert.equal(before.scene_id,'chair-probe');assert.equal(before.revision_id,'original');
 assert.equal(before.objects.length,1);
 assert.ok(await page.evaluate(()=>window.cleanroom.pixelVariation())>10,'Scene must render visible, varying pixels');
 await page.screenshot({path:'.artifacts/workspace.png'});
 await page.getByRole('button',{name:'Three-quarter',exact:true}).click();
 assert.equal((await page.evaluate(()=>window.cleanroom.metadata())).camera_name,'Three-quarter');
 await page.getByLabel('Collision',{exact:true}).check();
 await page.screenshot({path:'.artifacts/collider.png'});
 await page.getByLabel('Collision',{exact:true}).uncheck();
 await page.setViewportSize({width:800,height:1000});
 await page.screenshot({path:'.artifacts/mobile.png'});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({passed:true,scene:before.scene_id,objects:before.objects,errors},null,2));
} finally {await browser.close();}
