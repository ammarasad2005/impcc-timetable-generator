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

    // Refresh an expired access token using the refresh token (GoTrue refresh grant).
    async refresh() {
      if (!this.session || !this.session.refresh_token) return false;
      try {
        const j = await this._req("/auth/v1/token?grant_type=refresh_token", {
          method: "POST",
          headers: { "apikey": ANON, "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: this.session.refresh_token })
        });
        if (j && j.access_token) { this.session = j; this._save(); return true; }
      } catch (e) {}
      return false;
    },

    // Make sure the session token is still valid before an authenticated call;
    // refresh it if it's about to expire, or drop it (fall back to anon) on failure.
    async ensureSession() {
      if (!this.session) return false;
      const exp = this.session.expires_at || (this.session.expires_in ? Math.floor(Date.now()/1000) + this.session.expires_in : 0);
      if (exp && Math.floor(Date.now()/1000) < exp - 30) return true;
      const ok = await this.refresh();
      if (!ok) { this.session = null; this._save(); }
      return ok;
    },

    async _req(path, opts) {
      const res = await fetch(URL + path, opts);
      const text = await res.text();
      if (!res.ok) {
        let msg = "HTTP " + res.status;
        if (text) { try { const j = JSON.parse(text); msg = j.message || j.msg || msg; } catch (e) {} }
        throw new Error(msg);
      }
      if (!text) return null;                       // 201/204 with empty body
      try { return JSON.parse(text); } catch (e) { return text; }
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
      await this.ensureSession();
      const uid = this.user && this.user.id;
      if (!uid) return null;
      const rows = await this._req("/rest/v1/workspace?user_id=eq." + uid + "&select=*", {
        method: "GET", headers: this._headers()
      });
      return (Array.isArray(rows) && rows.length) ? rows[0] : null;
    },

    async saveWorkspace(allocation, constraints, faculty) {
      await this.ensureSession();
      const uid = this.user && this.user.id;
      if (!uid) throw new Error("not signed in");
      const body = { user_id: uid, allocation: allocation || {}, constraints: constraints || {}, faculty: faculty || [], updated_at: new Date().toISOString() };
      return this._req("/rest/v1/workspace?on_conflict=user_id", {
        method: "POST",
        headers: Object.assign({}, this._headers(), { "Prefer": "resolution=merge-duplicates,return=representation" }),
        body: JSON.stringify(body)
      });
    },

    // Global published state (allocation/constraints/faculty) — readable by EVERYONE,
    // writable only by signed-in users (RLS). Generated timetable combos are NOT stored.
    async loadPublished() {
      await this.ensureSession();
      const rows = await this._req("/rest/v1/published?id=eq.1&select=allocation,constraints,faculty,tweaks,updated_at", {
        method: "GET", headers: this._headers()
      });
      return (Array.isArray(rows) && rows.length) ? rows[0] : null;
    },

    async savePublished(allocation, constraints, faculty, tweaks) {
      await this.ensureSession();
      const body = { id: 1, allocation: allocation || {}, constraints: constraints || {}, faculty: faculty || [], tweaks: tweaks || [], updated_at: new Date().toISOString() };
      return this._req("/rest/v1/published?on_conflict=id", {
        method: "POST",
        headers: Object.assign({}, this._headers(), { "Prefer": "resolution=merge-duplicates,return=representation" }),
        body: JSON.stringify(body)
      });
    },

    // ---- saved timetables (admin's private, cross-device) ----
    async listSaved() {
      await this.ensureSession();
      const uid = this.user && this.user.id;
      if (!uid) return [];
      const rows = await this._req("/rest/v1/saved_timetables?user_id=eq." + uid + "&select=id,name,score,created_at,kind,parent_id,actions,archived&order=created_at.asc", {
        method: "GET", headers: this._headers()
      });
      return Array.isArray(rows) ? rows : [];
    },
    async getSaved(id) {
      await this.ensureSession();
      const rows = await this._req("/rest/v1/saved_timetables?id=eq." + id + "&select=*", {
        method: "GET", headers: this._headers()
      });
      return (Array.isArray(rows) && rows.length) ? rows[0] : null;
    },
    async saveTimetable(payload) {
      await this.ensureSession();
      const uid = this.user && this.user.id;
      if (!uid) throw new Error("not signed in");
      const body = {
        user_id: uid,
        name: payload.name || "",
        score: payload.score,
        timetable: payload.timetable,
        kind: payload.kind || "original",
        parent_id: payload.parent_id || null,
        actions: payload.actions || null,
        archived: !!payload.archived
      };
      return this._req("/rest/v1/saved_timetables", {
        method: "POST", headers: this._headers(), body: JSON.stringify(body)
      });
    },
    async deleteSaved(id) {
      await this.ensureSession();
      return this._req("/rest/v1/saved_timetables?id=eq." + id, { method: "DELETE", headers: this._headers() });
    },
    async archiveTimetable(id) {
      await this.ensureSession();
      return this._req("/rest/v1/saved_timetables?id=eq." + id, {
        method: "PATCH",
        headers: this._headers(),
        body: JSON.stringify({ archived: true })
      });
    },

    // ---- action history (append-only audit trail; survives version deletion) ----
    async recordHistory(entry) {
      await this.ensureSession();
      const uid = this.user && this.user.id;
      if (!uid) return null;
      const body = {
        user_id: uid,
        action: entry.action || "event",
        timetable_id: entry.timetable_id || null,
        parent_id: entry.parent_id || null,
        detail: entry.detail || null
      };
      return this._req("/rest/v1/timetable_history", {
        method: "POST", headers: this._headers(), body: JSON.stringify(body)
      });
    },
    async listHistory() {
      await this.ensureSession();
      const uid = this.user && this.user.id;
      if (!uid) return [];
      const rows = await this._req("/rest/v1/timetable_history?user_id=eq." + uid + "&select=*&order=created_at.desc", {
        method: "GET", headers: this._headers()
      });
      return Array.isArray(rows) ? rows : [];
    },
    async clearHistory() {
      await this.ensureSession();
      const uid = this.user && this.user.id;
      if (!uid) throw new Error("not signed in");
      return this._req("/rest/v1/timetable_history?user_id=eq." + uid, { method: "DELETE", headers: this._headers() });
    },

    // ---- pushed timetable (one, public read) ----
    async loadPushed() {
      await this.ensureSession();
      const rows = await this._req("/rest/v1/pushed_timetable?id=eq.1&select=score,timetable,pushed_at", {
        method: "GET", headers: this._headers()
      });
      return (Array.isArray(rows) && rows.length) ? rows[0] : null;
    },
    async pushTimetable(payload) {
      await this.ensureSession();
      const uid = this.user && this.user.id;
      const body = { id: 1, score: payload.score, timetable: payload.timetable, pushed_at: new Date().toISOString(), pushed_by: uid || null };
      return this._req("/rest/v1/pushed_timetable?on_conflict=id", {
        method: "POST",
        headers: Object.assign({}, this._headers(), { "Prefer": "resolution=merge-duplicates,return=representation" }),
        body: JSON.stringify(body)
      });
    },

    async unpushTimetable() {
      await this.ensureSession();
      return this._req("/rest/v1/pushed_timetable?id=eq.1", { method: "DELETE", headers: this._headers() });
    }
  };

  client._load();
  root.IMPCC_SUPABASE = client;
})(typeof window !== "undefined" ? window : this);
