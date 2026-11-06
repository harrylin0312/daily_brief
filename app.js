(() => {
  'use strict';
  const controls = document.querySelector('[data-filters]');
  if (!controls) return;
  const cards = [...document.querySelectorAll('[data-story]')];
  const search = document.querySelector('#story-search');
  const count = document.querySelector('[data-result-count]');
  const empty = document.querySelector('[data-empty]');
  let category = 'all';
  function filter() {
    const query = search.value.trim().toLocaleLowerCase();
    let visible = 0;
    for (const card of cards) {
      const match = (category === 'all' || card.dataset.category === category) &&
        (!query || card.textContent.toLocaleLowerCase().includes(query));
      card.hidden = !match;
      if (match) visible++;
    }
    count.textContent = `顯示 ${visible} 則精選`;
    empty.hidden = visible !== 0;
  }
  controls.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-category]');
    if (!button) return;
    category = button.dataset.category;
    for (const item of controls.querySelectorAll('button')) {
      item.setAttribute('aria-pressed', String(item === button));
    }
    filter();
  });
  search.addEventListener('input', filter);
  document.querySelector('[data-interactive]').hidden = false;
  const banner = document.querySelector('[data-freshness]');
  if (banner) {
    const taipeiDate = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit'
    }).format(new Date());
    if (banner.dataset.freshness < taipeiDate) banner.hidden = false;
  }
})();
