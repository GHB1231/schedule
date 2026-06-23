/**
 * calendar.js — FullCalendar 日历视图管理
 */

let calendar = null;

// 事件类型对应的 emoji
const TYPE_EMOJI = {
    task: '📋',
    meeting: '🤝',
    reminder: '🔔',
    job_search: '🎯',
    learning: '📚',
    other: '📌',
};

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

        // 事件源：从后端加载
        events: async function(fetchInfo, successCallback, failureCallback) {
            try {
                const startStr = fetchInfo.startStr;
                const endStr = fetchInfo.endStr;
                const events = await api.getEvents(startStr, endStr);

                // 转换事件格式为 FullCalendar 格式
                const fcEvents = events.map(ev => ({
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

                successCallback(fcEvents);
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
    if (calendar) {
        calendar.refetchEvents();
        await refreshLearningStats();
    }
}

// 初始化日历（在 app.js 的 DOMContentLoaded 中调用）
document.addEventListener('DOMContentLoaded', () => {
    initCalendar();
});
