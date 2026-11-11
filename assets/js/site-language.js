(function () {
  'use strict';
  const languages = [
    { code: 'zh-Hans', label: '简体中文', short: '简体', root: '/' },
    { code: 'zh-Hant', label: '繁體中文', short: '繁體', root: '/zh-hant/' },
    { code: 'en', label: 'English', short: 'English', root: '/en/' }
  ];
  const lang = document.documentElement.lang;
  const active = languages.find(item => item.code === lang) || languages[0];
  const label = active.code === 'en' ? 'Language' : active.code === 'zh-Hant' ? '語言' : '语言';
  const homeLabel = active.code === 'en' ? 'home' : '首頁';
  const variants = new Map(Array.from(document.querySelectorAll('link[rel="alternate"][hreflang]'),
    item => [item.hreflang, item.href]));
  const menus = [];
  for (const host of document.querySelectorAll('#sticky-header .header-info, .mobile-menu-area')) {
    const menu = document.createElement('details');
    menu.className = 'site-language';
    const button = document.createElement('summary');
    button.textContent = active.short;
    button.setAttribute('aria-label', label + ': ' + active.label);
    menu.append(button);
    const links = document.createElement('div');
    links.className = 'site-language-options';
    for (const item of languages) {
      const link = document.createElement('a');
      const fallback = !variants.has(item.code) && item.code !== active.code;
      const target = variants.get(item.code);
      link.href = target && /^https?:$/.test(location.protocol)
        ? new URL(target).pathname
        : target || (fallback ? item.root : location.href);
      link.lang = item.code;
      link.hreflang = item.code;
      link.textContent = item.label + (fallback ? ' (' + homeLabel + ')' : '');
      if (item.code === active.code) link.setAttribute('aria-current', 'page');
      links.append(link);
    }
    menu.append(links);
    host.append(menu);
    menus.push(menu);
    menu.addEventListener('toggle', () => {
      if (menu.open) menus.forEach(other => { if (other !== menu) other.open = false; });
    });
  }
  document.addEventListener('click', event => {
    menus.forEach(menu => { if (menu.open && !menu.contains(event.target)) menu.open = false; });
  });
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    menus.forEach(menu => {
      if (menu.open) { menu.open = false; menu.querySelector('summary').focus(); }
    });
  });
})();
