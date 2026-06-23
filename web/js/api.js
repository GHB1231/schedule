/**
 * api.js — 替换 Eel 调用，桥接到 Flask REST API
 * 用法: api.getEvents(start, end) → 返回数据
 *        api.parseInput(text) → 返回解析结果
 */

const api = {
    // 通用请求方法
    async _fetch(url, options = {}) {
        const resp = await fetch(url, {
            headers: { 'Content-Type': 'application/json' },
            ...options,
        });
        if (resp.status === 401) {
            window.location.href = '/login.html';
            throw new Error('未登录');
        }
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ error: '请求失败' }));
            throw new Error(err.error || `HTTP ${resp.status}`);
        }
        return resp.json();
    },

    _get(url) {
        return this._fetch(url);
    },

    _post(url, data) {
        return this._fetch(url, {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    _put(url, data) {
        return this._fetch(url, {
            method: 'PUT',
            body: JSON.stringify(data),
        });
    },

    _delete(url) {
        return this._fetch(url, { method: 'DELETE' });
    },

    // === 事件 ===
    getEvents(start, end) {
        const params = new URLSearchParams();
        if (start) params.set('start', start);
        if (end) params.set('end', end);
        return this._get('/api/events?' + params.toString());
    },

    addEvent(data) {
        return this._post('/api/events', data);
    },

    updateEvent(id, data) {
        return this._put(`/api/events/${id}`, data);
    },

    deleteEvent(id) {
        return this._delete(`/api/events/${id}`);
    },

    // === 智能解析 ===
    parseInput(text) {
        return this._post('/api/parse', { text });
    },

    confirmParse(data) {
        return this._post('/api/parse/confirm', data);
    },

    correctParse(sampleId, correction) {
        return this._post('/api/parse/correct', {
            sample_id: sampleId,
            correction: correction,
        });
    },

    // === 校招 ===
    searchJobs(keywords) {
        return this._post('/api/jobs/search', { keywords });
    },

    getJobPanel() {
        return this._get('/api/jobs');
    },

    markJobApplied(jobId, isApplied) {
        return this._post(`/api/jobs/${jobId}/applied`, { is_applied: isApplied });
    },

    // === 统计 ===
    getLearningStats() {
        return this._get('/api/stats');
    },
};
