import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
await fs.mkdir('.artifacts', {recursive:true});
const browser = await chromium.launch({channel:'chrome',headless:true});
try {
  const page = await browser.newPage({viewport:{width:1440,height:1080}});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  for (const path of ['/', '/demo.html', '/?scene=office-rebuild']) {
    await page.goto('http://127.0.0.1:8000' + path);
    await page.waitForSelector('[data-comparison]');
    assert.equal(await page.locator('[data-comparison]').count(), 2);
    for (const index of [0, 1]) {
      await page.locator(`[data-comparison="${index}"]`).click();
      await page.waitForFunction(() => [...document.images].every(i => i.complete && i.naturalWidth > 0));
      await page.getByLabel('Before and after comparison').fill('25');
      assert.match(await page.locator('#before-image').getAttribute('style'), /75%/);
    }
    await page.getByLabel('Before and after comparison').fill('50');
    assert.equal(await page.locator('#loop').getAttribute('open'), null);
    await page.locator('summary').click();
    await page.locator('.loop-diagram').waitFor({state:'visible'});
    await page.locator('summary').click();
    assert.match(await page.locator('#world-link').getAttribute('href'), /immersive=1&scene=office-rebuild/);
  }
  await page.screenshot({path:'.artifacts/demo-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await page.screenshot({path:'.artifacts/demo-mobile.png',fullPage:true});
  await page.locator('summary').click();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  assert.deepEqual(errors, []);
  console.log('Simple demo: both comparisons load, slider and loop disclosure work, desktop/mobile fit, no page errors.');
} finally {await browser.close();}
