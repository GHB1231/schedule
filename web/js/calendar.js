/**
 * calendar.js — FullCalendar 日历视图管理
 */

let calendar = null;

// 事件缓存: key="YYYY-MM~YYYY-MM" → events[]
const eventCache = {};
const CACHE_TTL = 60000; // 缓存 1 分钟

// 事件类型对应的 emoji
const TYPE_EMOJI = {
    task: '📋',
    meeting: '🤝',
    reminder: '🔔',
    job_search: '🎯',
    learning: '📚',
    other: '📌',
};

function cacheKey(startStr, endStr) {
    return startStr.substring(0, 10) + '~' + endStr.substring(0, 10);
}

function getCachedEvents(startStr, endStr) {
    const key = cacheKey(startStr, endStr);
    const cached = eventCache[key];
    if (cached && Date.now() - cached.time < CACHE_TTL) {
        return cached.events;
    }
    return null;
}

function setCachedEvents(startStr, endStr, events) {
    const key = cacheKey(startStr, endStr);
    eventCache[key] = { events, time: Date.now() };
}

function invalidateCache() {
    for (const k in eventCache) delete eventCache[k];
}

function initCalendar() {
    const calendarEl = document.getElementById('calendar');

    calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'dayGridMonth',
        headerToolbar: {
            left: 'prev,next today',
            center: 'title',
            right: 'dayGridMonth,timeGridWeek,timeGridDay',
        },
        buttonText: {
            today: '今天',
            month: '月',
            week: '周',
            day: '日',
        },
        locale: 'zh-cn',
        firstDay: 1,  // 周一作为一周的开始
        height: '100%',
        navLinks: true,
        editable: true,          // 允许拖拽
        selectable: true,        // 允许选择时间段
        selectMirror: true,
        dayMaxEvents: true,
        weekends: true,

        // 事件源：从后端加载（带缓存）
        events: async function(fetchInfo, successCallback, failureCallback) {
            try {
                const startStr = fetchInfo.startStr;
                const endStr = fetchInfo.endStr;

                // 1. 优先读缓存
                let events = getCachedEvents(startStr, endStr);
                if (events) {
                    successCallback(events);
                    return;
                }

                // 2. 缓存未命中，请求后端
                const rawEvents = await api.getEvents(startStr, endStr);

                // 转换格式
                const fcEvents = rawEvents.map(ev => ({
                    id: String(ev.id),
                    title: TYPE_EMOJI[ev.event_type] + ' ' + ev.title,
                    start: ev.start_time,
                    end: ev.end_time || ev.start_time,
                    backgroundColor: ev.color || '#4A90D9',
                    borderColor: ev.color || '#4A90D9',
                    textColor: '#ffffff',
                    extendedProps: {
                        event_type: ev.event_type,
                        description: ev.description,
                        location: ev.location,
                        priority: ev.priority,
                        tags: ev.tags,
                        source: ev.source,
                        raw: ev,
                    },
                }));

                setCachedEvents(startStr, endStr, fcEvents);
                successCallback(fcEvents);

                // 3. 后台预加载相邻月份（静默，不阻塞）
                preFetchNeighbors(fetchInfo);
            } catch (err) {
                console.error('加载事件失败:', err);
                failureCallback(err);
            }
        },

        // 点击事件 → 打开编辑弹窗
        eventClick: function(info) {
            const raw = info.event.extendedProps.raw;
            openModal(raw);
        },

        // 拖拽事件 → 更新时间
        eventDrop: async function(info) {
            const eventId = parseInt(info.event.id);
            const newStart = info.event.start;
            const newEnd = info.event.end || info.event.start;

            const pad = (n) => String(n).padStart(2, '0');
            const toISO = (d) =>
                `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:00`;

            const updates = {
                start_time: toISO(newStart),
                end_time: toISO(newEnd),
            };

            try {
                await api.updateEvent(eventId, updates);

                // 如果是自动解析的事件，记录修正
                const raw = info.event.extendedProps.raw;
                if (raw._sample_id) {
                    await api.correctParse(raw._sample_id, updates);
                }

                await refreshLearningStats();
            } catch (err) {
                console.error('更新失败:', err);
                info.revert();
                alert('更新失败，请重试');
            }
        },

        // 事件缩放 → 更新时长
        eventResize: async function(info) {
            const eventId = parseInt(info.event.id);
            const newEnd = info.event.end;

            if (newEnd) {
                const pad = (n) => String(n).padStart(2, '0');
                const endISO = `${newEnd.getFullYear()}-${pad(newEnd.getMonth()+1)}-${pad(newEnd.getDate())}T${pad(newEnd.getHours())}:${pad(newEnd.getMinutes())}:00`;

                try {
                    await api.updateEvent(eventId, { end_time: endISO });
                } catch (err) {
                    console.error('更新失败:', err);
                    info.revert();
                }
            }
        },

        // 选择时间段 → 手动创建
        select: function(info) {
            AppState.lastParsedData = {
                title: '',
                event_type: 'other',
                start_time: info.startStr,
                end_time: info.endStr,
                location: '',
                description: '',
                priority: 0,
                tags: [],
            };
            openModal(null);
            calendar.unselect();
        },
    });

    calendar.render();
}

async function refreshCalendar() {
    invalidateCache();  // 修改后清缓存
    if (calendar) {
        calendar.refetchEvents();
        await refreshLearningStats();
    }
}

// 后台预加载相邻月份
async function preFetchNeighbors(fetchInfo) {
    const monthMs = 30 * 86400 * 1000;
    const currentStart = new Date(fetchInfo.start);
    const currentEnd = new Date(fetchInfo.end);
    const range = currentEnd - currentStart;

    // 前一个月
    const prevStart = new Date(currentStart.getTime() - range);
    const prevEnd = new Date(currentStart);
    if (!getCachedEvents(prevStart.toISOString(), prevEnd.toISOString())) {
        try {
            const events = await api.getEvents(prevStart.toISOString(), prevEnd.toISOString());
            const fcEvents = events.map(ev => ({
                id: String(ev.id), title: TYPE_EMOJI[ev.event_type] + ' ' + ev.title,
                start: ev.start_time, end: ev.end_time || ev.start_time,
                backgroundColor: ev.color, borderColor: ev.color,
                textColor: '#ffffff',
                extendedProps: { raw: ev },
            }));
            setCachedEvents(prevStart.toISOString(), prevEnd.toISOString(), fcEvents);
        } catch(e) {}
    }

    // 后一个月
    const nextStart = new Date(currentEnd);
    const nextEnd = new Date(currentEnd.getTime() + range);
    if (!getCachedEvents(nextStart.toISOString(), nextEnd.toISOString())) {
        try {
            const events = await api.getEvents(nextStart.toISOString(), nextEnd.toISOString());
            const fcEvents = events.map(ev => ({
                id: String(ev.id), title: TYPE_EMOJI[ev.event_type] + ' ' + ev.title,
                start: ev.start_time, end: ev.end_time || ev.start_time,
                backgroundColor: ev.color, borderColor: ev.color,
                textColor: '#ffffff',
                extendedProps: { raw: ev },
            }));
            setCachedEvents(nextStart.toISOString(), nextEnd.toISOString(), fcEvents);
        } catch(e) {}
    }
}

// 初始化日历
document.addEventListener('DOMContentLoaded', () => {
    initCalendar();
});
