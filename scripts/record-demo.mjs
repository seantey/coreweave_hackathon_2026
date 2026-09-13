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
  await page.waitForSelector('[data-chapter]');
  const count = await page.locator('[data-chapter]').count();
  for (let i = 0; i < count; i++) {
    await page.locator(`[data-chapter="${i}"]`).click();
    await page.waitForFunction(() => [...document.images].every(image => image.complete && image.naturalWidth > 0));
    await page.getByLabel('Before and after comparison').fill('100');
    await pause(3500);
    for (let value = 100; value >= 0; value -= 4) {
      await page.getByLabel('Before and after comparison').fill(String(value));
      await pause(45);
    }
    await pause(4500);
  }
  await page.locator('#world-link').click();
  await page.waitForFunction(() => window.cleanroom?.ready, {timeout:90000});
  await pause(3000);
  await page.getByRole('button',{name:'Right',exact:true}).click();
  await pause(3000);
  const chair = page.locator('.asset-row').filter({hasText:'Chair candidate'}).first().getByRole('button',{name:'Inspect'});
  if (await chair.count()) {
    await chair.click(); await pause(4000);
    await page.getByLabel('Collision',{exact:true}).check();
    await page.getByLabel('Appearance',{exact:true}).uncheck(); await pause(3000);
    await page.getByLabel('Appearance',{exact:true}).check();
    await page.getByLabel('Collision',{exact:true}).uncheck();
    await page.getByRole('button',{name:'Show room',exact:true}).click();
  }
  await page.getByRole('button',{name:'Forward',exact:true}).click();
  await pause(2500);
  await page.goto('http://127.0.0.1:5173/demo.html');
  await page.waitForSelector('#image-stage');
  await page.getByLabel('Before and after comparison').fill('0');
  await pause(5000);
} finally {
  const video = page.video();
  await context.close(); await browser.close();
  const path = await video.path();
  const output = '.artifacts/clean-room-imputation-demo.mp4';
  const result = spawnSync('ffmpeg',['-y','-i',path,'-c:v','libx264','-preset','fast','-crf','22','-pix_fmt','yuv420p','-movflags','+faststart',output],{encoding:'utf8'});
  if (result.status !== 0) throw new Error(result.stderr);
  await fs.writeFile('.artifacts/demo-video/recording.json',JSON.stringify({output,errors,narration:'silent screen recording',scope:'Recorded evidence replay and current 3D workspace; no model calls simulated'},null,2));
  if (errors.length) throw new Error(errors.join('\n'));
  console.log(output);
}
