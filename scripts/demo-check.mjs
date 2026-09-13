import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
await fs.mkdir('.artifacts', {recursive:true});
const browser = await chromium.launch({channel:'chrome',headless:true});
try {
  const page = await browser.newPage({viewport:{width:1920,height:1080}});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('http://127.0.0.1:5173/demo.html');
  await page.waitForSelector('[data-chapter]');
  const count = await page.locator('[data-chapter]').count();
  assert.ok(count >= 4);
  for (let index = 0; index < count; index++) {
    await page.locator(`[data-chapter="${index}"]`).click();
    await page.waitForFunction(() => [...document.images].every(i => i.complete && i.naturalWidth > 0));
    await page.getByLabel('Before and after comparison').fill('25');
    assert.match(await page.locator('#before-image').getAttribute('style'), /75%/);
  }
  await page.screenshot({path:'.artifacts/demo-desktop.png'});
  await page.getByRole('button', {name:'Play recorded sequence'}).click();
  assert.equal(await page.locator('#play').innerText(), 'Pause replay');
  await page.getByRole('button', {name:'Pause replay'}).click();
  await page.setViewportSize({width:800,height:1000});
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await page.screenshot({path:'.artifacts/demo-mobile.png'});
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({passed:true,chapters:count,errors}));
} finally {await browser.close();}
