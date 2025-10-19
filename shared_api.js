// Lightweight client for server.js API with graceful fallback to db.json/localStorage
(function(){
  const STORAGE_KEYS = {
    income: 'fallback.income.v1',
    expenses: 'fallback.expenses.v1',
    payroll: 'fallback.payroll.v1'
  };

  function loadLocalStorage(kind) {
    try {
      const raw = localStorage.getItem(STORAGE_KEYS[kind]);
      const arr = JSON.parse(raw || '[]');
      return Array.isArray(arr) ? arr : [];
    } catch { return []; }
  }

  function saveLocalStorage(kind, arr) {
    try { localStorage.setItem(STORAGE_KEYS[kind], JSON.stringify(arr || [])); }
    catch {}
  }

  function uid(){ return Math.random().toString(36).slice(2) + Date.now().toString(36); }

  const API = {
    available: false, // true when either server API or fallback is ready
    base: '',
    mode: 'server', // 'server' | 'local'
    local: { income: [], expenses: [], payroll: [] },

    async init(base=''){
      this.base = base || '';
      // Try live server first
      try {
        const r = await fetch(this.base + '/api/ping');
        if (r.ok) {
          this.available = true;
          this.mode = 'server';
          return true;
        }
      } catch {}

      // Fallback: try bundled db.json
      try {
        const r = await fetch((this.base || '') + '/db.json');
        if (r.ok) {
          const data = await r.json();
          this.local = {
            income: Array.isArray(data.income) ? data.income.slice() : [],
            expenses: Array.isArray(data.expenses) ? data.expenses.slice() : [],
            payroll: Array.isArray(data.payroll) ? data.payroll.slice() : []
          };
          // Merge any user changes stored in localStorage on top
          for (const kind of ['income','expenses','payroll']) {
            const extras = loadLocalStorage(kind);
            if (extras.length) {
              const byId = new Map(this.local[kind].map(x=>[x.id, x]));
              for (const rec of extras) byId.set(rec.id, rec);
              this.local[kind] = Array.from(byId.values());
            }
          }
          this.available = true;
          this.mode = 'local';
          return true;
        }
      } catch {}

      // Last fallback: only user data from localStorage
      try {
        this.local = {
          income: loadLocalStorage('income'),
          expenses: loadLocalStorage('expenses'),
          payroll: loadLocalStorage('payroll')
        };
        if (this.local.income.length || this.local.expenses.length || this.local.payroll.length) {
          this.available = true;
          this.mode = 'local';
          return true;
        }
      } catch {}

      this.available = false;
      return false;
    },

    async list(kind){
      if (this.mode === 'server') {
        const r = await fetch(this.base + '/api/' + kind);
        if (!r.ok) throw new Error('Request failed');
        return r.json();
      }
      return Promise.resolve((this.local[kind] || []).slice());
    },

    async upsert(kind, rec){
      if (this.mode === 'server') {
        const r = await fetch(this.base + '/api/' + kind, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(rec) });
        if(!r.ok) throw new Error('Upsert failed');
        return r.json();
      }
      const row = Object.assign({}, rec);
      if (!row.id) row.id = uid();
      const arr = this.local[kind] = (this.local[kind] || []).slice();
      const idx = arr.findIndex(x => x.id === row.id);
      if (idx >= 0) arr[idx] = row; else arr.push(row);
      saveLocalStorage(kind, arr);
      return Promise.resolve(row);
    },

    async remove(kind, id){
      if (this.mode === 'server') {
        const r = await fetch(this.base + '/api/' + kind + '/' + encodeURIComponent(id), { method:'DELETE' });
        return r.ok;
      }
      const arr = (this.local[kind] || []).filter(x => x.id !== id);
      this.local[kind] = arr;
      saveLocalStorage(kind, arr);
      return Promise.resolve(true);
    },

    async clear(kind){
      if (this.mode === 'server') {
        const r = await fetch(this.base + '/api/' + kind, { method:'DELETE' });
        return r.ok;
      }
      this.local[kind] = [];
      saveLocalStorage(kind, []);
      return Promise.resolve(true);
    },

    async export(kind){
      if (this.mode === 'server') {
        const r = await fetch(this.base + '/api/' + kind + '.csv');
        if(!r.ok) throw new Error('Export failed');
        return r.blob();
      }
      // Build CSV from local data
      const rows = this.local[kind] || [];
      const csv = ['id,date,source,processor,amount,fees,notes,category,seller,items,order_number,total'];
      for (const r of rows) {
        const line = [
          r.id||'', r.date||'', r.source||'', r.processor||'', r.amount||'', r.fees||'', r.notes||'',
          r.category||'', r.seller||'', r.items||'', (r.orderNumber||r.order_number||''), (r.total||'')
        ].map(v => {
          const s = String(v==null?'':v);
          return /[",\n]/.test(s) ? '"' + s.replace(/"/g,'""') + '"' : s;
        }).join(',');
        csv.push(line);
      }
      return Promise.resolve(new Blob([csv.join('\n')], { type: 'text/csv' }));
    },

    income:{ list(){ return API.list('income'); }, upsert(rec){ return API.upsert('income',rec); }, remove(id){ return API.remove('income',id); }, clear(){ return API.clear('income'); }, export(){ return API.export('income'); } },
    expenses:{ list(){ return API.list('expenses'); }, upsert(rec){ return API.upsert('expenses',rec); }, remove(id){ return API.remove('expenses',id); }, clear(){ return API.clear('expenses'); }, export(){ return API.export('expenses'); } },
    payroll:{ list(){ return API.list('payroll'); }, upsert(rec){ return API.upsert('payroll',rec); }, remove(id){ return API.remove('payroll',id); }, clear(){ return API.clear('payroll'); }, export(){ return API.export('payroll'); } },
  };
  window.API = API;
})();
