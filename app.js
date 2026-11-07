(() => {
  'use strict';
  const read = (key) => {
    try { return JSON.parse(sessionStorage.getItem(key)); } catch { return null; }
  };
  const write = (key, value) => {
    try { sessionStorage.setItem(key, JSON.stringify(value)); } catch { /* Navigation still works. */ }
  };
  const detail = document.querySelector('[data-detail]');
  if (detail) {
    const key = `brief:return:${detail.dataset.issueDate}:${detail.dataset.storyId}`;
    const saved = read(key);
    const home = new URL(detail.dataset.homeList, location.href);
    const issue = new URL(detail.dataset.issueList, location.href);
    const allowed = [home.pathname, home.pathname.replace(/index\.html$/, ''), issue.pathname];
    if (saved && saved.issueDate === detail.dataset.issueDate && typeof saved.path === 'string') {
      try {
        const target = new URL(saved.path, location.origin);
        if (target.origin === location.origin && allowed.includes(target.pathname) && !target.search) {
          target.hash = detail.dataset.storyId;
          document.querySelectorAll('[data-back-link]').forEach(link => {
            link.href = target.pathname + target.hash;
          });
        }
      } catch { /* Use the static link to this edition. */ }
    }
    return;
  }

  const controls = document.querySelector('[data-filters]');
  if (!controls) return;
  const main = document.querySelector('main[data-issue-date]');
  const cards = [...document.querySelectorAll('[data-story]')];
  const search = document.querySelector('#story-search');
  const count = document.querySelector('[data-result-count]');
  const empty = document.querySelector('[data-empty]');
  const key = `brief:list:${location.pathname}`;
  let category = 'all';
  let restoring = false;
  function selectCategory(value) {
    const buttons = [...controls.querySelectorAll('button[data-category]')];
    category = buttons.some(button => button.dataset.category === value) ? value : 'all';
    for (const button of buttons) {
      button.setAttribute('aria-pressed', String(button.dataset.category === category));
    }
  }
  function filter() {
    const query = search.value.trim().toLocaleLowerCase();
    let visible = 0;
    for (const card of cards) {
      const text = card.dataset.search || card.textContent;
      const match = (category === 'all' || card.dataset.category === category) &&
        (!query || text.toLocaleLowerCase().includes(query));
      card.hidden = !match;
      if (match) visible++;
    }
    count.textContent = `顯示 ${visible} 則精選`;
    empty.hidden = visible !== 0;
  }
  function save() {
    if (restoring) return;
    write(key, {issueDate: main.dataset.issueDate, category, query: search.value, y: scrollY});
  }
  function restore() {
    const saved = read(key);
    if (!saved || saved.issueDate !== main.dataset.issueDate) return;
    restoring = true;
    selectCategory(saved.category);
    search.value = typeof saved.query === 'string' ? saved.query.slice(0, 500) : '';
    filter();
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (Number.isFinite(saved.y)) scrollTo({top: Math.max(0, saved.y), behavior: 'instant'});
      restoring = false;
    }));
  }
  controls.addEventListener('click', event => {
    const button = event.target.closest('button[data-category]');
    if (!button) return;
    selectCategory(button.dataset.category);
    filter();
    save();
  });
  search.addEventListener('input', () => { filter(); save(); });
  document.addEventListener('click', event => {
    const link = event.target.closest('a[data-story-link]');
    if (!link) return;
    const card = link.closest('[data-story]');
    if (!card) return;
    save();
    write(`brief:return:${main.dataset.issueDate}:${card.id}`, {
      issueDate: main.dataset.issueDate, path: location.pathname
    });
  });
  window.addEventListener('pagehide', save);
  window.addEventListener('pageshow', restore);
  document.querySelector('[data-interactive]').hidden = false;
  const banner = document.querySelector('[data-freshness]');
  if (banner) {
    const taipeiDate = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit'
    }).format(new Date());
    if (banner.dataset.freshness < taipeiDate) banner.hidden = false;
  }
})();
