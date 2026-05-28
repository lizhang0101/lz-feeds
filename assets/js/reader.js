/* Reader page: per-entry "mark as read" with localStorage persistence.
 *
 * Storage keys:
 *   lz-feeds-read       : { "<entry-link>": <unix-ms>, ... }
 *   lz-feeds-show-read  : "1" | "0"  (toggle state)
 *
 * Entries older than 90 days are garbage-collected from the read set on load.
 */
(function () {
  'use strict';

  var READ_KEY = 'lz-feeds-read';
  var SHOW_KEY = 'lz-feeds-show-read';
  var GC_MAX_AGE_MS = 90 * 24 * 60 * 60 * 1000;

  function loadRead() {
    try {
      var raw = localStorage.getItem(READ_KEY);
      if (!raw) return {};
      var obj = JSON.parse(raw);
      return (obj && typeof obj === 'object') ? obj : {};
    } catch (e) {
      return {};
    }
  }

  function saveRead(map) {
    try {
      localStorage.setItem(READ_KEY, JSON.stringify(map));
    } catch (e) {
      // quota or disabled; ignore
    }
  }

  function gc(map) {
    var now = Date.now();
    var changed = false;
    Object.keys(map).forEach(function (k) {
      var ts = map[k];
      if (typeof ts !== 'number' || (now - ts) > GC_MAX_AGE_MS) {
        delete map[k];
        changed = true;
      }
    });
    if (changed) saveRead(map);
    return map;
  }

  function getShowRead() {
    return localStorage.getItem(SHOW_KEY) === '1';
  }

  function setShowRead(val) {
    localStorage.setItem(SHOW_KEY, val ? '1' : '0');
  }

  // Find all entry <li> elements inside the reader page and the link
  // they point at (used as the unique key).
  function collectEntries(root) {
    var items = root.querySelectorAll('ul > li');
    var out = [];
    items.forEach(function (li) {
      var a = li.querySelector('a[href]');
      if (!a) return;
      out.push({ li: li, link: a.getAttribute('href') });
    });
    return out;
  }

  function applyReadState(entries, readMap) {
    entries.forEach(function (e) {
      if (readMap[e.link]) {
        e.li.classList.add('entry-read');
      } else {
        e.li.classList.remove('entry-read');
      }
    });
  }

  function applyVisibility(root, showRead) {
    if (showRead) {
      root.classList.add('show-read');
    } else {
      root.classList.remove('show-read');
    }
  }

  function updateReadCount(root, entries, readMap) {
    var el = root.querySelector('#reader-read-count');
    if (!el) return;
    var read = entries.filter(function (e) { return readMap[e.link]; }).length;
    var total = entries.length;
    el.textContent = total ? '已读 ' + read + ' / ' + total : '';
  }

  function makeButton(label, title) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'mark-read-btn';
    btn.textContent = label;
    btn.setAttribute('aria-label', title);
    btn.title = title;
    return btn;
  }

  function init() {
    var root = document.querySelector('.reader-page');
    if (!root) return;

    var readMap = gc(loadRead());
    var entries = collectEntries(root);

    // Inject per-entry "mark as read" buttons.
    entries.forEach(function (e) {
      var btn = makeButton('✓', '标记已读');
      btn.addEventListener('click', function () {
        if (readMap[e.link]) {
          delete readMap[e.link];
        } else {
          readMap[e.link] = Date.now();
        }
        saveRead(readMap);
        applyReadState(entries, readMap);
        updateReadCount(root, entries, readMap);
      });
      // Place into the first <div> child if present so the button sits
      // next to the title; fall back to appending to the <li>.
      var titleRow = e.li.querySelector(':scope > div');
      (titleRow || e.li).appendChild(btn);
    });

    // Inject "mark all read" buttons on each source <h3>.
    var headings = root.querySelectorAll('h3');
    headings.forEach(function (h3) {
      // Find the <ul> that follows this h3.
      var ul = h3.nextElementSibling;
      while (ul && ul.tagName !== 'UL') ul = ul.nextElementSibling;
      if (!ul) return;

      var btn = makeButton('全部已读', '将此源下所有条目标记为已读');
      btn.classList.add('mark-all-btn');
      btn.addEventListener('click', function () {
        var now = Date.now();
        ul.querySelectorAll(':scope > li').forEach(function (li) {
          var a = li.querySelector('a[href]');
          if (!a) return;
          readMap[a.getAttribute('href')] = now;
        });
        saveRead(readMap);
        applyReadState(entries, readMap);
        updateReadCount(root, entries, readMap);
      });
      h3.appendChild(btn);
    });

    // Wire the show-read toggle.
    var toggle = root.querySelector('#show-read-toggle');
    if (toggle) {
      toggle.checked = getShowRead();
      applyVisibility(root, toggle.checked);
      toggle.addEventListener('change', function () {
        setShowRead(toggle.checked);
        applyVisibility(root, toggle.checked);
      });
    }

    applyReadState(entries, readMap);
    updateReadCount(root, entries, readMap);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
