(function () {
  'use strict';

  const root = document.querySelector('.case-page');
  if (!root) return;

  const pageSize = 9;
  const cards = Array.from(root.querySelectorAll('.case-card'), element => ({
    element,
    kind: element.dataset.kind,
    categories: element.dataset.categories.split(' '),
    searchableText: element.textContent.toLocaleLowerCase()
  }));
  const search = root.querySelector('#case-search');
  const result = root.querySelector('#case-results');
  const empty = root.querySelector('.case-empty');
  const pagination = root.querySelector('.case-pagination');
  const kindButtons = root.querySelectorAll('[data-kind-filter]');
  const categoryButtons = root.querySelectorAll('[data-category-filter]');

  let kind = 'all';
  let category = 'all';
  let page = 1;

  function pageButton(label, targetPage, options = {}) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = label;
    button.disabled = Boolean(options.disabled);
    if (options.ariaLabel) button.setAttribute('aria-label', options.ariaLabel);
    if (options.current) button.setAttribute('aria-current', 'page');
    button.addEventListener('click', () => {
      if (page === targetPage) return;
      page = targetPage;
      render();
      result.focus({ preventScroll: true });
      result.scrollIntoView({ block: 'start' });
    });
    return button;
  }

  function render() {
    const query = search.value.trim().toLocaleLowerCase();
    const matches = cards.filter(card =>
      (kind === 'all' || card.kind === kind) &&
      (category === 'all' || card.categories.includes(category)) &&
      card.searchableText.includes(query)
    );
    const total = matches.length;
    const pageCount = Math.max(1, Math.ceil(total / pageSize));
    const start = (page - 1) * pageSize;
    const end = Math.min(start + pageSize, total);
    const visible = new Set(matches.slice(start, end));
    cards.forEach(card => { card.element.hidden = !visible.has(card); });
    kindButtons.forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.kindFilter === kind));
    });
    categoryButtons.forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.categoryFilter === category));
    });
    result.textContent = total
      ? (start + 1) + '–' + end + ' / ' + total + ' ' + result.dataset.countLabel
      : '0 ' + result.dataset.countLabel;
    empty.hidden = total !== 0;

    pagination.hidden = pageCount <= 1;
    pagination.replaceChildren();
    if (pagination.hidden) return;

    pagination.append(pageButton(pagination.dataset.previous, page - 1, { disabled: page === 1 }));
    for (let number = 1; number <= pageCount; number++) {
      pagination.append(pageButton(String(number), number, {
        current: number === page,
        ariaLabel: pagination.dataset.pageLabel.replace('{page}', String(number))
      }));
    }
    pagination.append(pageButton(pagination.dataset.next, page + 1, { disabled: page === pageCount }));
  }

  function resetPage() {
    page = 1;
    render();
  }

  kindButtons.forEach(button => button.addEventListener('click', () => {
    kind = button.dataset.kindFilter;
    resetPage();
  }));
  categoryButtons.forEach(button => button.addEventListener('click', () => {
    category = button.dataset.categoryFilter;
    resetPage();
  }));
  search.addEventListener('input', resetPage);
  root.querySelector('.case-reset').addEventListener('click', () => {
    kind = 'all';
    category = 'all';
    search.value = '';
    resetPage();
    search.focus();
  });
  render();
})();
