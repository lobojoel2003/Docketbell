// Take the README screenshots from a running demo server (see scripts/demo_server.py).
//   node scripts/screenshots.cjs http://127.0.0.1:8001 docs/images
const { chromium, devices } = require("playwright");

const [base = "http://127.0.0.1:8001", out = "docs/images"] = process.argv.slice(2);

async function login(context) {
  const page = await context.newPage();
  await page.goto(`${base}/accounts/login/`);
  await page.fill("#id_username", "demo");
  await page.fill("#id_password", "demo-password-1");
  await Promise.all([page.waitForNavigation(), page.click("button[type=submit]")]);
  return page;
}

async function shot(page, path, name, options = {}) {
  await page.goto(`${base}${path}`);
  await page.waitForLoadState("networkidle");
  if (options.hover) {
    await page.hover(options.hover);
  }
  await page.screenshot({ path: `${out}/${name}.png`, fullPage: options.fullPage ?? false });
  console.log(`saved ${out}/${name}.png`);
}

(async () => {
const browser = await chromium.launch();

// Desktop, light.
const desktop = await browser.newContext({
  viewport: { width: 1360, height: 900 },
  deviceScaleFactor: 2,
  colorScheme: "light",
  locale: "en-US",
});
let page = await login(desktop);
await shot(page, "/", "dashboard");
// A court date with a lively conversation.
await page.goto(`${base}/court-dates/?q=Hern%C3%A1ndez`);
const detail = await page.locator("a.row-link").first().getAttribute("href");
await shot(page, detail, "conversation");
await shot(page, "/messages/?lang=es", "messages-spanish");
await shot(page, "/results/", "results");
await shot(page, "/inbox/", "inbox");

// Desktop, dark.
const dark = await browser.newContext({
  viewport: { width: 1360, height: 900 },
  deviceScaleFactor: 2,
  colorScheme: "dark",
  locale: "en-US",
});
page = await login(dark);
await shot(page, "/", "dashboard-dark");

// Phone.
const phone = await browser.newContext({ ...devices["iPhone 13"], colorScheme: "light" });
page = await login(phone);
await shot(page, "/", "dashboard-mobile");

await browser.close();
})();
