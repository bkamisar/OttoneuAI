// Paste into the browser console on the Ottoneu transactions page
// (https://ottoneu.fangraphs.com/1648/transactions). Read-only. Slow on purpose:
// one page every 6 s, and it stops on any non-200 (Cloudflare rate limit) —
// rerun later with START set to the page it stopped on; rows persist in
// localStorage.__tx_rows. When done it downloads
// ottoneu_1648_transactions.csv → move it to data/transactions.csv.
//
// Final standings for a past season use the same approach, via
//   fetch('/1648/standings?date=YYYY-09-28')  (no page navigation needed).
(async () => {
  const START = 1;
  const base = '/1648/transactions?teamfilter=-1&filters%5B%5D=add&filters%5B%5D=cut&filters%5B%5D=move&filters%5B%5D=increase&active_transactions=no&page=';
  const rows = START === 1 ? [] : JSON.parse(localStorage.getItem('__tx_rows') || '[]');
  for (let p = START; p < 500; p++) {
    const res = await fetch(base + p);
    if (res.status !== 200) { console.warn('HTTP ' + res.status + ' at page ' + p + ' — rerun later with START = ' + p); return; }
    const d = new DOMParser().parseFromString(await res.text(), 'text/html');
    const trs = [...d.querySelectorAll('main table tr')].slice(1);
    if (!trs.length) break;
    for (const r of trs) {
      const c = [...r.cells];
      rows.push({ date: c[0].textContent.trim(), type: c[1].textContent.trim(), player: c[2].textContent.trim(),
        playerHref: c[2].querySelector('a')?.getAttribute('href') || '', team: c[3].textContent.trim(),
        teamHref: c[3].querySelector('a')?.getAttribute('href') || '', fromTeam: c[4].textContent.trim(),
        fromHref: c[4].querySelector('a')?.getAttribute('href') || '', salary: c[5].textContent.trim() });
    }
    localStorage.setItem('__tx_rows', JSON.stringify(rows));
    console.log('page', p, rows.length, 'rows');
    await new Promise(s => setTimeout(s, 6000));
  }
  const id = (h, k) => { const m = (h || '').match(new RegExp('/' + k + '/(\\d+)')); return m ? m[1] : ''; };
  const iso = s => {
    const m = s.match(/^(\w{3}) (\d+) (\d{4}) (\d+):(\d+):(\d+) (AM|PM)$/);
    const mo = { Jan: 1, Feb: 2, Mar: 3, Apr: 4, May: 5, Jun: 6, Jul: 7, Aug: 8, Sep: 9, Oct: 10, Nov: 11, Dec: 12 }[m[1]];
    const h = +m[4] % 12 + (m[7] === 'PM' ? 12 : 0); const p = n => String(n).padStart(2, '0');
    return `${m[3]}-${p(mo)}-${p(m[2])}T${p(h)}:${m[5]}:${m[6]}`;
  };
  const q = v => (/[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v);
  const lines = ['date,type,player,ottoneuId,teamId,team,fromTeamId,fromTeam,salary'];
  for (const r of rows) lines.push([iso(r.date), r.type, r.player, id(r.playerHref, 'players'), id(r.teamHref, 'team'), r.team, id(r.fromHref, 'team'), r.fromTeam, r.salary.replace(/[$,]/g, '')].map(q).join(','));
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([lines.join('\n') + '\n'], { type: 'text/csv' }));
  a.download = 'ottoneu_1648_transactions.csv'; document.body.appendChild(a); a.click();
})();
