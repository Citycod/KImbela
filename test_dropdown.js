const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  await page.goto('file:///home/uplix/uplix/KImbela/test_dropdown.html');
  
  // Check initial state
  const isHidden1 = await page.$eval('.dropdown-menu', el => el.classList.contains('hidden'));
  console.log('Initial hidden:', isHidden1);
  
  // Click the button
  await page.click('button');
  
  // Check state after click
  const isHidden2 = await page.$eval('.dropdown-menu', el => el.classList.contains('hidden'));
  console.log('After click hidden:', isHidden2);
  
  await browser.close();
})();
