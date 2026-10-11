const fs = require('fs');
const source = fs.readFileSync(process.argv[2], 'utf8');
const runtime = source.split("runtime='''<script>")[1].split("</script>'''")[0]
  .replace('BASE', JSON.stringify('/live')).replace('CONTENT_VERSION', '1').replace('MONITOR', 'false');

// Exercise the generated audience runtime with controllable, pending play promises.
async function scenario(action, errorName) {
  let elements = [], activeIndex = 0, remote, poll, rejectPlay, playCalls = 0;
  const media = {
    play() { playCalls++; return new Promise((_, reject) => { rejectPlay = reject; }); },
    pause() {}, addEventListener() {},
  };
  const slides = [
    { contains: m => activeIndex === 0 && m === media, querySelectorAll: () => [media] },
    { contains: () => false, querySelectorAll: () => [] },
  ];
  global.document = {
    documentElement: { lang: 'es' },
    createElement(tag) {
      const element = { tag, style: {}, handlers: {}, setAttribute() {}, append() {},
        addEventListener(name, fn) { this.handlers[name] = fn; } };
      elements.push(element); return element;
    },
    body: { append() {}, classList: { toggle() {} } },
    querySelectorAll: selector => selector === '.slide-media' ? [media] : [],
    addEventListener() {},
  };
  global.deck = { configure() {}, on() {}, slide(i) { activeIndex = i; },
    getCurrentSlide() { return slides[activeIndex]; }, isOverview() { return false; } };
  global.requestAnimationFrame = fn => fn();
  global.setInterval = fn => { poll = fn; };
  global.fetch = async () => ({ ok: true, json: async () => remote });
  global.location = { reload() {} };
  eval(runtime);
  remote = { content_version: 1, version: 2, slide_index: 0, fragment_index: -1,
    slides: [{ id: 's0' }, { id: 's1' }],
    media_command: { version: 2, slide_id: 's0', media_index: 0, action: 'play' } };
  await poll();
  remote = { ...remote, version: 3, slide_index: action === 'navigate' ? 1 : 0,
    media_command: action === 'navigate' ? null
      : { version: 3, slide_id: 's0', media_index: 0, action: 'pause' } };
  await poll();
  rejectPlay({ name: errorName });
  await new Promise(resolve => setImmediate(resolve));
  const staleNotice = elements[1].style.display === 'block';
  elements[3].handlers.click();
  return { action, errorName, staleNotice, playCalls, passed: !staleNotice && playCalls === 1 };
}

(async () => {
  const results = [];
  for (const action of ['navigate', 'pause']) {
    for (const errorName of ['AbortError', 'NotAllowedError']) {
      results.push(await scenario(action, errorName));
    }
  }
  console.log(JSON.stringify(results, null, 2));
  process.exitCode = results.every(result => result.passed) ? 0 : 1;
})().catch(error => { console.error(error); process.exitCode = 2; });
