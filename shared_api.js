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
      function defaultBase(){
        try {
          if (typeof location !== 'undefined' && /^https?:/i.test(location.protocol)) return location.origin || '';
        } catch {}
        return 'http://127.0.0.1:3000';
      }
      this.base = base || defaultBase();
      // Try live server first (try current base, then localhost if different)
      const basesToTry = [this.base];
      if (!/^https?:/i.test(this.base)) basesToTry.push('http://127.0.0.1:3000');
      else if (!/127\.0\.0\.1|localhost/.test(this.base)) basesToTry.push('http://127.0.0.1:3000');
      for (const b of basesToTry) {
        try { const r = await fetch(b + '/api/ping'); if (r.ok) { this.base = b; this.available = true; this.mode = 'server'; return true; } } catch {}
      }

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
        if (!r.ok) {
          const t = await r.text().catch(()=>r.statusText);
          throw new Error(`List failed (${r.status}): ${t}`);
        }
        return r.json();
      }
      return Promise.resolve((this.local[kind] || []).slice());
    },

    async upsert(kind, rec){
      if (this.mode === 'server') {
        const r = await fetch(this.base + '/api/' + kind, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(rec) });
        if(!r.ok) {
          const t = await r.text().catch(()=>r.statusText);
          throw new Error(`Upsert failed (${r.status}): ${t}`);
        }
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
    expenses:{
      list(){ return API.list('expenses'); },
      upsert(rec){ return API.upsert('expenses',rec); },
      remove(id){ return API.remove('expenses',id); },
      clear(){ return API.clear('expenses'); },
      export(){ return API.export('expenses'); },
      async scanReceipt(file){
        if (!file) throw new Error('No file provided');
        if (API.mode !== 'server') throw new Error('Receipt scanning requires the backend server');
        const fd = new FormData();
        fd.append('file', file);
        const res = await fetch(API.base + '/api/expenses/scan', { method: 'POST', body: fd });
        if (!res.ok) {
          let msg = `Receipt scan failed (${res.status})`;
          let detail = null;
          try { detail = await res.json(); if (detail?.error) msg = detail.error; }
          catch {}
          const error = new Error(msg);
          if (detail) error.details = detail;
          error.status = res.status;
          throw error;
        }
        return await res.json();
      }
    },
    payroll:{ list(){ return API.list('payroll'); }, upsert(rec){ return API.upsert('payroll',rec); }, remove(id){ return API.remove('payroll',id); }, clear(){ return API.clear('payroll'); }, export(){ return API.export('payroll'); } },

    attachments: {
      async list(kind, recordId){
        if (API.mode === 'server') {
          const r = await fetch(API.base + `/api/${encodeURIComponent(kind)}/${encodeURIComponent(recordId)}/attachments`);
          if (!r.ok) throw new Error('Failed to list attachments');
          return r.json();
        }
        return [];
      },
      async upload(kind, recordId, files){
        if (!files || files.length === 0) return [];
        if (API.mode === 'server') {
          const fd = new FormData();
          for (const f of Array.from(files)) fd.append('files', f);
          const r = await fetch(API.base + `/api/${encodeURIComponent(kind)}/${encodeURIComponent(recordId)}/attachments`, { method: 'POST', body: fd });
          if (!r.ok) throw new Error('Failed to upload attachments');
          return r.json();
        }
        return [];
      },
      async remove(attachmentId){
        if (API.mode === 'server'){
          const r = await fetch(API.base + `/api/attachments/${encodeURIComponent(attachmentId)}`, { method: 'DELETE' });
          return r.ok;
        }
        return true;
      }
    },

    settings: {
      async all(){
        if (API.mode !== 'server') return {};
        const res = await fetch(API.base + '/api/settings');
        if (!res.ok) throw new Error('Failed to load settings');
        const body = await res.json().catch(()=>({}));
        return body.settings || {};
      },
      async get(key){
        if (API.mode !== 'server') return '';
        const res = await fetch(API.base + `/api/settings/${encodeURIComponent(key)}`);
        if (!res.ok) throw new Error('Failed to load setting');
        const body = await res.json().catch(()=>({}));
        return body.value ?? '';
      },
      async set(key, value){
        if (API.mode !== 'server') throw new Error('Settings changes require the backend server');
        const res = await fetch(API.base + `/api/settings/${encodeURIComponent(key)}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ value })
        });
        if (!res.ok) {
          let msg = `Failed to save setting (${res.status})`;
          try { const err = await res.json(); if (err?.error) msg = err.error; } catch {}
          throw new Error(msg);
        }
        const body = await res.json().catch(()=>({}));
        return body.value ?? '';
      },
      async remove(key){
        if (API.mode !== 'server') return true;
        const res = await fetch(API.base + `/api/settings/${encodeURIComponent(key)}`, { method: 'DELETE' });
        return res.ok;
      }
    }
  };
  window.API = API;
})();
