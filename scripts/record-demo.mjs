// Capture real local interactions. This replays existing evidence; it starts no model jobs.
import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
await fs.mkdir('.artifacts/demo-video', {recursive:true});
const browser = await chromium.launch({channel:'chrome',headless:true,args:['--use-angle=metal']});
const context = await browser.newContext({viewport:{width:1920,height:1080}, recordVideo:{dir:'.artifacts/demo-video',size:{width:1920,height:1080}}});
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const pause = milliseconds => page.waitForTimeout(milliseconds);
try {
  await page.goto('http://127.0.0.1:5173/demo.html');
  await page.waitForSelector('#office-viewer');
  const frame = await (await page.locator('#office-viewer').elementHandle()).contentFrame();
  await frame.waitForFunction(() => window.cleanroom?.ready, {}, {timeout:90000});
  await frame.locator('#presentation-before').click();
  await pause(2500);
  await frame.locator('#presentation-after').click();
  await pause(2500);
  await frame.locator('#viewport canvas').click({position:{x:500,y:180}});
  await page.keyboard.down('d'); await pause(900); await page.keyboard.up('d');
  await pause(1500);
  await frame.locator('#presentation-before').click(); await pause(2000);
  await frame.locator('#presentation-after').click(); await pause(2000);
  await page.locator('#compare-tab').click();
  await page.waitForFunction(() => [...document.images].every(image => image.complete && image.naturalWidth > 0));
  for (let value = 100; value >= 0; value -= 4) {
    await page.getByLabel('Before and after comparison').fill(String(value));
    await pause(45);
  }
  await pause(2000);
  await page.locator('summary').click();
  await pause(6000);
  await page.locator('summary').click();
  await page.locator('#explore-tab').click();
  await pause(4000);
} finally {
  const video = page.video();
  await context.close(); await browser.close();
  const path = await video.path();
  const output = '.artifacts/clean-room-imputation-demo.mp4';
  const result = spawnSync('ffmpeg',['-y','-i',path,'-c:v','libx264','-preset','fast','-crf','22','-pix_fmt','yuv420p','-movflags','+faststart',output],{encoding:'utf8'});
  if (result.status !== 0) throw new Error(result.stderr);
  await fs.writeFile('.artifacts/demo-video/recording.json',JSON.stringify({output,errors,narration:'silent screen recording',scope:'Actual 3D exploration, revision comparison and loop explanation; no model calls simulated'},null,2));
  if (errors.length) throw new Error(errors.join('\n'));
  console.log(output);
}
