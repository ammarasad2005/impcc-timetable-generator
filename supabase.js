/* supabase.js — minimal Supabase client (Auth + PostgREST via fetch).
   No CDN dependency. RLS on the workspace table keeps each user's data private. */
(function (root) {
  "use strict";

  const URL = "https://xdckubhqhglmorwmxtfs.supabase.co";
  const ANON = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhkY2t1YmhxaGdsbW9yd214dGZzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY2NDY5NTksImV4cCI6MjEwMjIyMjk1OX0.a8Apb7KaEumAxDEb0ojgGDjizGaVseK6O28DsSWRpys";
  const SESSION_KEY = "impcc-supabase-session-v1";

  const client = {
    url: URL,
    session: null,   // { access_token, refresh_token, user }

    _load() {
      try { this.session = JSON.parse(localStorage.getItem(SESSION_KEY)); } catch (e) { this.session = null; }
      return this.session;
    },
    _save() {
      try { if (this.session) localStorage.setItem(SESSION_KEY, JSON.stringify(this.session)); else localStorage.removeItem(SESSION_KEY); } catch (e) {}
    },

    get user() { return this.session && this.session.user; },
    get loggedIn() { return !!(this.session && this.session.access_token); },
    _headers() {
      const h = { "apikey": ANON, "Content-Type": "application/json" };
      if (this.session && this.session.access_token) h["Authorization"] = "Bearer " + this.session.access_token;
      return h;
    },

    async _req(path, opts) {
      const res = await fetch(URL + path, opts);
      if (!res.ok) {
        let msg = "HTTP " + res.status;
        try { const j = await res.json(); msg = j.message || j.msg || msg; } catch (e) {}
        throw new Error(msg);
      }
      if (res.status === 204) return null;
      return res.json();
    },

    async signup(email, password) {
      const j = await this._req("/auth/v1/signup", {
        method: "POST",
        headers: this._headers(),
        body: JSON.stringify({ email: email, password: password })
      });
      if (j.session) { this.session = j.session; this._save(); }
      return j;
    },

    async login(email, password) {
      const j = await this._req("/auth/v1/token?grant_type=password", {
        method: "POST",
        headers: this._headers(),
        body: JSON.stringify({ email: email, password: password })
      });
      this.session = j; this._save();
      return j;
    },

    async logout() {
      try { await this._req("/auth/v1/logout", { method: "POST", headers: this._headers() }); } catch (e) {}
      this.session = null; this._save();
    },

    async loadWorkspace() {
      const uid = this.user && this.user.id;
      if (!uid) return null;
      const rows = await this._req("/rest/v1/workspace?user_id=eq." + uid + "&select=*", {
        method: "GET", headers: this._headers()
      });
      return (Array.isArray(rows) && rows.length) ? rows[0] : null;
    },

    async saveWorkspace(allocation, constraints) {
      const uid = this.user && this.user.id;
      if (!uid) throw new Error("not signed in");
      const body = { user_id: uid, allocation: allocation || {}, constraints: constraints || {}, updated_at: new Date().toISOString() };
      return this._req("/rest/v1/workspace?on_conflict=user_id", {
        method: "POST",
        headers: Object.assign({}, this._headers(), { "Prefer": "resolution=merge-duplicates,return=representation" }),
        body: JSON.stringify(body)
      });
    }
  };

  client._load();
  root.IMPCC_SUPABASE = client;
})(typeof window !== "undefined" ? window : this);
