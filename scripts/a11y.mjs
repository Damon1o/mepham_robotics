// Accessibility check: loads each page in Chromium, light and dark, and runs axe-core.
// Fails on serious or critical violations. Start scripts/a11y_server.py first.
//
//   npm install --no-save playwright@1.53.0 @axe-core/playwright@4.10.2
//   npx playwright install --with-deps chromium
//   node scripts/a11y.mjs [base-url]
import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

const BASE = process.argv[2] || 'http://127.0.0.1:5099';
const PAGES = ['/', '/about', '/achievements', '/events', '/alumni', '/contact', '/donate',
    '/safety-quiz', '/privacy', '/credits', '/login', '/signup', '/team/77628A', '/team/media'];
const BLOCKING = new Set(['serious', 'critical']);

const browser = await chromium.launch();
let failures = 0;
for (const theme of ['light', 'dark']) {
    const context = await browser.newContext({ reducedMotion: 'reduce' });
    await context.addInitScript(t => localStorage.setItem('mepham-theme', t), theme);
    const page = await context.newPage();
    for (const path of PAGES) {
        await page.goto(BASE + path, { waitUntil: 'networkidle' });
        const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
        for (const v of violations.filter(v => BLOCKING.has(v.impact))) {
            failures++;
            console.log(`\n[${theme}] ${path}  ${v.impact}: ${v.id} - ${v.help}`);
            for (const node of v.nodes.slice(0, 5)) console.log(`    ${node.target.join(' ')}`);
            if (v.nodes.length > 5) console.log(`    ...and ${v.nodes.length - 5} more`);
        }
    }
    await context.close();
}
await browser.close();
console.log(failures ? `\n${failures} blocking accessibility issue(s).` : 'No serious or critical issues.');
process.exit(failures ? 1 : 0);
